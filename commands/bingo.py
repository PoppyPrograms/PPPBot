from random import choice, sample

import discord

from commands.gamble import reserve_wager, settle_wager


BOARD_SIDE = 5
CARD_SIZE = BOARD_SIDE * BOARD_SIDE
FREE_POSITION = 12
NUMBER_MAX = 75
COLUMNS = ("B", "I", "N", "G", "O")
BINGO_CELL_WIDTH = 8

ROW_LINES = tuple(
    tuple(row * BOARD_SIDE + column for column in range(BOARD_SIDE))
    for row in range(BOARD_SIDE)
)
COLUMN_LINES = tuple(
    tuple(row * BOARD_SIDE + column for row in range(BOARD_SIDE))
    for column in range(BOARD_SIDE)
)
WINNING_LINES = ROW_LINES + COLUMN_LINES + (
    (0, 6, 12, 18, 24),
    (4, 8, 12, 16, 20),
)


def new_card():
    """Create a standard bingo card with a free center square."""

    columns = [
        sample(
            range(column * 15 + 1, column * 15 + 16),
            BOARD_SIDE,
        )
        for column in range(BOARD_SIDE)
    ]
    card = [
        columns[column][row]
        for row in range(BOARD_SIDE)
        for column in range(BOARD_SIDE)
    ]
    card[FREE_POSITION] = None
    return card


def number_label(number):
    if number is None:
        return "—"
    if not 1 <= number <= NUMBER_MAX:
        raise ValueError("Bingo numbers must be between 1 and 75.")
    return f"{COLUMNS[(number - 1) // 15]}-{number}"


def has_bingo(marked_positions):
    marked = set(marked_positions)
    return any(set(line).issubset(marked) for line in WINNING_LINES)


def board_text(card, marked_positions):
    if len(card) != CARD_SIZE:
        raise ValueError("Bingo cards must contain 25 squares.")

    marked = set(marked_positions)
    border = "+" + "+".join(
        "-" * (BINGO_CELL_WIDTH + 2) for _ in COLUMNS
    ) + "+"
    rows = [
        border,
        "| " + " | ".join(
            f"{column:^{BINGO_CELL_WIDTH}}" for column in COLUMNS
        ) + " |",
        border,
    ]
    for row in range(BOARD_SIDE):
        cells = []
        for column in range(BOARD_SIDE):
            position = row * BOARD_SIDE + column
            number = card[position]
            if number is None:
                cell = "✅ FREE" if position in marked else "FREE"
            elif position in marked:
                cell = f"✅ {number:02d}"
            else:
                cell = f"{number:02d}"
            cells.append(f"{cell:^{BINGO_CELL_WIDTH}}")
        rows.append("| " + " | ".join(cells) + " |")
        rows.append(border)
    return "```text\n" + "\n".join(rows) + "\n```"


def mark_number(card, marked_positions, number):
    for position, card_number in enumerate(card):
        if card_number == number:
            marked_positions.add(position)


class BingoView(discord.ui.View):
    def __init__(self, player_id, wager):
        super().__init__(timeout=180)
        self.player_id = player_id
        self.wager = wager
        self.card = new_card()
        self.house_card = new_card()
        self.called_numbers = set()
        self.marked_positions = {FREE_POSITION}
        self.house_marked_positions = {FREE_POSITION}
        self.last_called = None
        self.settled = False
        self.message = None
        self.channel = None

        self.call_button = discord.ui.Button(
            label="Call number",
            style=discord.ButtonStyle.primary,
            row=1,
        )
        self.call_button.callback = self.call_number
        self.add_item(self.call_button)

        self.claim_button = discord.ui.Button(
            label="Bingo!",
            style=discord.ButtonStyle.success,
            row=1,
        )
        self.claim_button.callback = self.claim_bingo
        self.add_item(self.claim_button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.player_id:
            await interaction.response.send_message(
                "This is someone else's bingo game <:300:1359772114751852554>",
                ephemeral=True,
            )
            return False
        return True

    def content(
        self,
        status="Press **Call number** to draw the next ball <:tony:1450129761916551188>",
        reveal_house=False,
    ):
        called = ", ".join(
            number_label(number) for number in sorted(self.called_numbers)
        )
        if not called:
            called = "none"
        house_progress = len(self.house_marked_positions - {FREE_POSITION})
        content = (
            f"**Bingo** — wager: {self.wager} burgas\n\n"
            f"{board_text(self.card, self.marked_positions)}\n\n"
            f"Last call: **{number_label(self.last_called)}**\n"
            f"Called: {called}\n\n"
            f"House bot: **{house_progress}/24** squares marked\n\n"
            f"{status}"
        )
        if reveal_house:
            content += f"\n\n**House bot's final card**\n{board_text(self.house_card, self.house_marked_positions)}"
        return content

    def disable_buttons(self):
        for child in self.children:
            child.disabled = True

    def public_result_content(self, outcome):
        if outcome == "win":
            return (
                "<:good:1364955467016831056> **Bingo:** "
                f"<@{self.player_id}> won {self.wager} burgas; "
                "the house bot lost."
            )
        return (
            "<:realhipster:1464647196891680879> **Bingo:** "
            f"the house bot won — <@{self.player_id}> lost {self.wager} burgas."
        )

    async def call_number(self, interaction):
        if self.settled:
            await interaction.response.send_message(
                "This bingo game is already over <:amongus:1533984742339514628>",
                ephemeral=True,
            )
            return

        remaining = [
            number
            for number in range(1, NUMBER_MAX + 1)
            if number not in self.called_numbers
        ]
        if not remaining:
            if has_bingo(self.marked_positions):
                await self.claim_bingo(interaction)
            else:
                await self.finish(
                    interaction,
                    "loss",
                )
            return

        self.last_called = choice(remaining)
        self.called_numbers.add(self.last_called)
        mark_number(self.card, self.marked_positions, self.last_called)
        mark_number(
            self.house_card,
            self.house_marked_positions,
            self.last_called,
        )

        house_has_bingo = has_bingo(self.house_marked_positions)
        player_has_bingo = has_bingo(self.marked_positions)
        if house_has_bingo:
            await self.finish(
                interaction,
                "loss",
            )
            return
        if player_has_bingo:
            self.call_button.disabled = True
            status = (
                "You have a bingo! Press **Bingo!** to claim it "
                "<:good:1364955467016831056>"
            )
        else:
            status = (
                f"Number **{number_label(self.last_called)}** called. "
                "Keep going <:tony:1450129761916551188>"
            )
        await interaction.response.edit_message(
            content=self.content(status),
            view=self,
        )

    async def claim_bingo(self, interaction):
        if self.settled:
            await interaction.response.send_message(
                "This bingo game is already over <:amongus:1533984742339514628>",
                ephemeral=True,
            )
            return
        if not has_bingo(self.marked_positions):
            await interaction.response.send_message(
                "No bingo yet — call more numbers first <:killsyou:1511341401277989005>",
                ephemeral=True,
            )
            return

        await self.finish(
            interaction,
            "win",
        )

    async def finish(self, interaction, outcome):
        if self.settled:
            return

        self.settled = True
        self.stop()
        self.disable_buttons()
        settle_wager(self.player_id, self.wager, outcome)
        await interaction.response.edit_message(
            content="Bingo is over — the final result is posted publicly below.",
            view=self,
        )
        await interaction.followup.send(
            self.public_result_content(outcome),
            ephemeral=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def on_timeout(self):
        if self.settled:
            return

        self.settled = True
        self.stop()
        self.disable_buttons()
        outcome = "win" if has_bingo(self.marked_positions) else "loss"
        settle_wager(self.player_id, self.wager, outcome)
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
                    self.public_result_content(outcome),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.DiscordException:
                pass


async def bingo(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        await interaction.response.send_message(
            "The wager must be greater than zero <:killsyou:1511341401277989005>",
            ephemeral=True,
        )
        return

    user_id = str(interaction.user.id)
    reserved, balance = reserve_wager(user_id, amount)
    if not reserved:
        await interaction.response.send_message(
            f"You only have {balance} burgas, so you cannot wager {amount} "
            "<:killsyou:1511341401277989005>",
            ephemeral=True,
        )
        return

    view = BingoView(interaction.user.id, amount)
    view.channel = interaction.channel
    await interaction.response.send_message(
        view.content(),
        view=view,
        ephemeral=True,
    )
    view.message = await interaction.original_response()


module = {
    "type": "command",
    "name": "bingo",
    "description": "Play bingo for burgas",
    "callback": bingo,
}
