from random import shuffle

import discord

from commands.gamble import reserve_wager, settle_wager


RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS = ("♠", "♥", "♦", "♣")
CARD_VALUES = {
    "A": 11,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 10,
    "Q": 10,
    "K": 10,
}


def new_deck():
    deck = [(rank, suit) for suit in SUITS for rank in RANKS]
    shuffle(deck)
    return deck


def card_text(card):
    return f"{card[0]}{card[1]}"


def hand_value(hand):
    value = sum(CARD_VALUES[rank] for rank, _ in hand)
    aces = sum(rank == "A" for rank, _ in hand)
    while value > 21 and aces:
        value -= 10
        aces -= 1
    return value


def hand_text(hand):
    return " ".join(card_text(card) for card in hand)


class BlackjackView(discord.ui.View):
    def __init__(self, player_id, wager):
        super().__init__(timeout=90)
        self.player_id = player_id
        self.wager = wager
        self.deck = new_deck()
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        self.settled = False
        self.message = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.player_id:
            await interaction.response.send_message(
                "This is someone else's blackjack game <:300:1359772114751852554>", ephemeral=True
            )
            return False
        return True

    def content(self, status="Choose **Hit** or **Stand** <:tony:1450129761916551188>", reveal_dealer=False):
        dealer_cards = (
            hand_text(self.dealer_hand)
            if reveal_dealer
            else f"{card_text(self.dealer_hand[0])} 🂠"
        )
        dealer_total = (
            hand_value(self.dealer_hand) if reveal_dealer else "?"
        )
        return (
            f"**Blackjack** — wager: {self.wager} burgas\n"
            f"Dealer: {dealer_cards} (`{dealer_total}`)\n"
            f"You: {hand_text(self.player_hand)} (`{hand_value(self.player_hand)}`)\n\n"
            f"{status}"
        )

    def disable_buttons(self):
        for child in self.children:
            child.disabled = True

    async def finish(self, interaction, outcome, status):
        if self.settled:
            return

        self.settled = True
        self.stop()
        self.disable_buttons()
        new_balance = settle_wager(self.player_id, self.wager, outcome)
        status = f"{status} Your balance is now {new_balance} burgas <:burga:1493907112542077092>"
        await interaction.response.edit_message(
            content=self.content(status, reveal_dealer=True), view=self
        )

    async def resolve(self, interaction):
        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())

        player_total = hand_value(self.player_hand)
        dealer_total = hand_value(self.dealer_hand)
        if dealer_total > 21 or player_total > dealer_total:
            await self.finish(interaction, "win", f"You win {self.wager} burgas <:bkdrool:1301252732023476374>")
        elif player_total < dealer_total:
            await self.finish(interaction, "loss", f"You lose {self.wager} burgas <:realhipster:1464647196891680879>")
        else:
            await self.finish(interaction, "draw", "Push — your wager is refunded <:apdog:1355120388488560720>")

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player_hand.append(self.deck.pop())
        player_total = hand_value(self.player_hand)
        if player_total > 21:
            await self.finish(
                interaction,
                "loss",
                f"Bust! You lose {self.wager} burgas <:WHYYYY:1171546567614926949>",
            )
        elif player_total == 21:
            await self.resolve(interaction)
        else:
            await interaction.response.edit_message(
                content=self.content(), view=self
            )

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.resolve(interaction)

    async def on_timeout(self):
        if self.settled:
            return

        self.settled = True
        self.stop()
        self.disable_buttons()
        new_balance = settle_wager(self.player_id, self.wager, "draw")
        if self.message is not None:
            try:
                await self.message.edit(
                    content=self.content(
                        f"Time's up — your wager was refunded <:amongus:1533984742339514628>"
                        f"Your balance is now {new_balance} burgas.",
                        reveal_dealer=True,
                    ),
                    view=self,
                )
            except discord.DiscordException:
                pass


async def blackjack(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        await interaction.response.send_message(
            "The wager must be greater than zero <:tony:1450129761916551188>", ephemeral=True
        )
        return

    user_id = str(interaction.user.id)
    reserved, balance = reserve_wager(user_id, amount)
    if not reserved:
        await interaction.response.send_message(
            f"You only have {balance} burgas, so you cannot wager {amount} <:puncher:1511285878427877446>",
            ephemeral=True,
        )
        return

    view = BlackjackView(interaction.user.id, amount)
    await interaction.response.send_message(view.content(), view=view)
    view.message = await interaction.original_response()


module = {
    "type": "command",
    "name": "blackjack",
    "description": "Play blackjack for burgas",
    "callback": blackjack,
}
