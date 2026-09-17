from collections import Counter

import discord

from commands.cards import (
    CARD_BACK,
    RANKS,
    card_text,
    hand_text,
    new_deck,
)
from commands.gamble import reserve_wager, settle_wager


RANK_VALUES = dict(
    zip(RANKS, (14, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13))
)

HAND_NAMES = {
    0: "High card",
    1: "Pair",
    2: "Two pair",
    3: "Three of a kind",
    4: "Straight",
    5: "Flush",
    6: "Full house",
    7: "Four of a kind",
    8: "Straight flush",
}

CARD_COUNT = 5


def _straight_high(values):
    unique_values = sorted(set(values), reverse=True)
    if len(unique_values) != CARD_COUNT:
        return None
    if unique_values == [14, 5, 4, 3, 2]:
        return 5
    if unique_values[0] - unique_values[-1] == CARD_COUNT - 1:
        return unique_values[0]
    return None


def evaluate_hand(hand):
    """Return a comparable ``(category, tie_breakers)`` poker hand rank."""

    if len(hand) != CARD_COUNT:
        raise ValueError("Poker hands must contain exactly five cards.")

    values = [RANK_VALUES[rank] for rank, _ in hand]
    counts = Counter(values)
    groups = sorted(
        ((count, value) for value, count in counts.items()),
        reverse=True,
    )
    flush = len({suit for _, suit in hand}) == 1
    straight_high = _straight_high(values)

    if flush and straight_high is not None:
        return 8, (straight_high,)
    if groups[0][0] == 4:
        four = groups[0][1]
        kicker = groups[1][1]
        return 7, (four, kicker)
    if groups[0][0] == 3 and groups[1][0] == 2:
        return 6, (groups[0][1], groups[1][1])
    if flush:
        return 5, tuple(sorted(values, reverse=True))
    if straight_high is not None:
        return 4, (straight_high,)
    if groups[0][0] == 3:
        kickers = sorted(
            (value for value in values if counts[value] == 1),
            reverse=True,
        )
        return 3, (groups[0][1], *kickers)
    if groups[0][0] == 2 and groups[1][0] == 2:
        pairs = sorted((groups[0][1], groups[1][1]), reverse=True)
        kicker = groups[2][1]
        return 2, (*pairs, kicker)
    if groups[0][0] == 2:
        pair = groups[0][1]
        kickers = sorted(
            (value for value in values if counts[value] == 1),
            reverse=True,
        )
        return 1, (pair, *kickers)
    return 0, tuple(sorted(values, reverse=True))


def hand_rank(hand):
    return evaluate_hand(hand)


def compare_hands(left_hand, right_hand):
    left_rank = evaluate_hand(left_hand)
    right_rank = evaluate_hand(right_hand)
    return (left_rank > right_rank) - (left_rank < right_rank)


def dealer_keep_positions(hand):
    """Choose the cards a simple draw-poker dealer should keep."""

    category, _ = evaluate_hand(hand)
    if category >= 4:
        return set(range(CARD_COUNT))

    values = [RANK_VALUES[rank] for rank, _ in hand]
    counts = Counter(values)
    return {
        position
        for position, value in enumerate(values)
        if counts[value] > 1
    }


def hand_name(hand_or_rank):
    is_rank = (
        isinstance(hand_or_rank, tuple)
        and len(hand_or_rank) == 2
        and isinstance(hand_or_rank[0], int)
    )
    rank = hand_or_rank if is_rank else evaluate_hand(hand_or_rank)
    category, tie_breakers = rank
    if category == 8 and tie_breakers[0] == 14:
        return "Royal flush"
    return HAND_NAMES[category]


class PokerView(discord.ui.View):
    def __init__(self, player_id, wager):
        super().__init__(timeout=90)
        self.player_id = player_id
        self.wager = wager
        self.deck = new_deck()
        self.player_hand = [self.deck.pop() for _ in range(CARD_COUNT)]
        self.dealer_hand = [self.deck.pop() for _ in range(CARD_COUNT)]
        self.held_positions = set()
        self.drawn = False
        self.settled = False
        self.message = None
        self.channel = None
        self.card_buttons = []

        for position, card in enumerate(self.player_hand):
            button = discord.ui.Button(
                label=card_text(card),
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            button.callback = self.make_hold_callback(position)
            self.add_item(button)
            self.card_buttons.append(button)

        self.draw_button = discord.ui.Button(
            label="Draw",
            style=discord.ButtonStyle.primary,
            row=1,
        )
        self.draw_button.callback = self.draw
        self.add_item(self.draw_button)

    def make_hold_callback(self, position):
        async def callback(interaction):
            await self.toggle_hold(interaction, position)

        return callback

    async def interaction_check(self, interaction):
        if interaction.user.id != self.player_id:
            await interaction.response.send_message(
                "This is someone else's poker game <:300:1359772114751852554>",
                ephemeral=True,
            )
            return False
        return True

    def content(
        self,
        status="Select cards to keep, then press **Draw** <:tony:1450129761916551188>",
        reveal_dealer=False,
    ):
        player_cards = " ".join(
            f"{card_text(card)}{' ✅' if position in self.held_positions else ''}"
            for position, card in enumerate(self.player_hand)
        )
        if reveal_dealer:
            dealer_cards = hand_text(self.dealer_hand)
            dealer_name = f" — {hand_name(self.dealer_hand)}"
        else:
            dealer_cards = " ".join(CARD_BACK for _ in self.dealer_hand)
            dealer_name = ""

        return (
            f"**Poker** — wager: {self.wager} burgas\n"
            f"Dealer: {dealer_cards}{dealer_name}\n"
            f"You: {player_cards} — {hand_name(self.player_hand)}\n\n"
            f"{status}"
        )

    def disable_buttons(self):
        for child in self.children:
            child.disabled = True

    def public_result_content(self, status):
        return (
            f"**Poker result for <@{self.player_id}>**\n"
            f"{self.content(status, reveal_dealer=True)}"
        )

    def update_card_buttons(self):
        for position, button in enumerate(self.card_buttons):
            button.label = card_text(self.player_hand[position])
            button.style = (
                discord.ButtonStyle.success
                if position in self.held_positions
                else discord.ButtonStyle.secondary
            )

    async def toggle_hold(self, interaction, position):
        if self.drawn or self.settled:
            await interaction.response.send_message(
                "This poker hand is already over <:amongus:1533984742339514628>",
                ephemeral=True,
            )
            return

        if position in self.held_positions:
            self.held_positions.remove(position)
        else:
            self.held_positions.add(position)
        self.update_card_buttons()
        await interaction.response.edit_message(
            content=self.content(),
            view=self,
        )

    async def finish(self, interaction, outcome, status):
        if self.settled:
            return

        self.settled = True
        self.stop()
        self.disable_buttons()
        new_balance = settle_wager(self.player_id, self.wager, outcome)
        final_status = (
            f"{status} Your balance is now {new_balance} burgas "
            "<:burga:1493907112542077092>"
        )

        # The game itself is ephemeral, but the resolved hand is useful as a
        # public receipt. An ephemeral interaction response cannot be made
        # public by editing it, so replace the private view with a short note
        # and publish the revealed result through the interaction follow-up.
        await interaction.response.edit_message(
            content="Hand complete — the final result is posted publicly below.",
            view=self,
        )
        await interaction.followup.send(
            self.public_result_content(final_status),
            ephemeral=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def resolve(self, interaction):
        comparison = compare_hands(self.player_hand, self.dealer_hand)
        player_name = hand_name(self.player_hand)
        dealer_name = hand_name(self.dealer_hand)

        if comparison > 0:
            await self.finish(
                interaction,
                "win",
                f"You win {self.wager} burgas! Your {player_name.lower()} "
                f"beats the dealer's {dealer_name.lower()} "
                "<:bkdrool:1301252732023476374>",
            )
        elif comparison < 0:
            await self.finish(
                interaction,
                "loss",
                f"You lose {self.wager} burgas — the dealer's "
                f"{dealer_name.lower()} beats your {player_name.lower()} "
                "<:realhipster:1464647196891680879>",
            )
        else:
            await self.finish(
                interaction,
                "draw",
                f"Push — both hands are {player_name.lower()}, so your "
                "wager is refunded <:apdog:1355120388488560720>",
            )

    async def draw(self, interaction):
        if self.drawn or self.settled:
            await interaction.response.send_message(
                "You have already drawn this poker hand <:amongus:1533984742339514628>",
                ephemeral=True,
            )
            return

        self.drawn = True
        for position in range(CARD_COUNT):
            if position not in self.held_positions:
                self.player_hand[position] = self.deck.pop()
        dealer_kept = dealer_keep_positions(self.dealer_hand)
        for position in range(CARD_COUNT):
            if position not in dealer_kept:
                self.dealer_hand[position] = self.deck.pop()
        self.update_card_buttons()
        await self.resolve(interaction)

    async def on_timeout(self):
        if self.settled:
            return

        self.settled = True
        self.stop()
        self.disable_buttons()
        new_balance = settle_wager(self.player_id, self.wager, "draw")
        final_status = (
            f"Time's up — your wager was refunded "
            "<:amongus:1533984742339514628> "
            f"Your balance is now {new_balance} burgas."
        )
        if self.message is not None:
            try:
                await self.message.edit(
                    content="Time's up — the final result is posted publicly below.",
                    view=self,
                )
            except discord.DiscordException:
                pass

        if self.channel is not None:
            try:
                await self.channel.send(
                    self.public_result_content(final_status),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.DiscordException:
                pass


async def poker(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        await interaction.response.send_message(
            "The wager must be greater than zero <:tony:1450129761916551188>",
            ephemeral=True,
        )
        return

    user_id = str(interaction.user.id)
    reserved, balance = reserve_wager(user_id, amount)
    if not reserved:
        await interaction.response.send_message(
            f"You only have {balance} burgas, so you cannot wager {amount} "
            "<:puncher:1511285878427877446>",
            ephemeral=True,
        )
        return

    view = PokerView(interaction.user.id, amount)
    view.channel = interaction.channel
    await interaction.response.send_message(
        view.content(),
        view=view,
        ephemeral=True,
    )
    view.message = await interaction.original_response()


module = {
    "type": "command",
    "name": "poker",
    "description": "Play five-card draw poker for burgas",
    "callback": poker,
}
