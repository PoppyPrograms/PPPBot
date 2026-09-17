import discord

from commands.gamble import reserve_wager, settle_wager


WINNING_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


def winner(board):
    for first, second, third in WINNING_LINES:
        if board[first] and board[first] == board[second] == board[third]:
            return board[first]
    return None


def available_positions(board):
    return [position for position, mark in enumerate(board) if mark is None]


def find_winning_move(board, mark):
    for position in available_positions(board):
        board[position] = mark
        is_winning = winner(board) == mark
        board[position] = None
        if is_winning:
            return position
    return None


def choose_bot_move(board):
    winning_move = find_winning_move(board, "O")
    if winning_move is not None:
        return winning_move

    blocking_move = find_winning_move(board, "X")
    if blocking_move is not None:
        return blocking_move

    for position in (4, 0, 2, 6, 8, 1, 3, 5, 7):
        if board[position] is None:
            return position

    return None


class TicTacToeView(discord.ui.View):
    def __init__(self, player_id, wager):
        super().__init__(timeout=90)
        self.player_id = player_id
        self.wager = wager
        self.board = [None] * 9
        self.buttons = []
        self.settled = False
        self.message = None

        for position in range(9):
            button = discord.ui.Button(
                label=str(position + 1),
                style=discord.ButtonStyle.secondary,
                row=position // 3,
            )
            button.callback = self.make_move_callback(position)
            self.add_item(button)
            self.buttons.append(button)

    def make_move_callback(self, position):
        async def callback(interaction):
            await self.make_move(interaction, position)

        return callback

    async def interaction_check(self, interaction):
        if interaction.user.id != self.player_id:
            await interaction.response.send_message(
                "This is someone else's tic-tac-toe game <:killsyou:1511341401277989005>", ephemeral=True
            )
            return False
        return True

    def content(self, status="Your turn — pick a square."):
        return (
            f"**Tic-Tac-Toe** — wager: {self.wager} burgas\n"
            "You are **X**. The bot is **O**.\n\n"
            f"{status}"
        )

    def disable_buttons(self):
        for button in self.buttons:
            button.disabled = True

    def mark_button(self, position, mark):
        button = self.buttons[position]
        button.label = mark
        button.disabled = True
        button.style = (
            discord.ButtonStyle.success
            if mark == "X"
            else discord.ButtonStyle.danger
        )

    async def finish(self, interaction, outcome, status):
        if self.settled:
            return

        self.settled = True
        self.stop()
        self.disable_buttons()
        new_balance = settle_wager(self.player_id, self.wager, outcome)
        await interaction.response.edit_message(
            content=self.content(
                f"{status} Your balance is now {new_balance} burgas <:burga:1493907112542077092>"
            ),
            view=self,
        )

    async def make_move(self, interaction, position):
        if self.board[position] is not None:
            await interaction.response.send_message(
                "That square is already taken <:killsyou:1511341401277989005>", ephemeral=True
            )
            return

        self.board[position] = "X"
        self.mark_button(position, "X")

        if winner(self.board) == "X":
            await self.finish(interaction, "win", f"You win {self.wager} burgas! <:good:1364955467016831056>")
            return

        if not available_positions(self.board):
            await self.finish(interaction, "draw", "Draw — your wager is refunded <:goon:1505288457017229312>")
            return

        bot_position = choose_bot_move(self.board)
        if bot_position is not None:
            self.board[bot_position] = "O"
            self.mark_button(bot_position, "O")

        if winner(self.board) == "O":
            await self.finish(interaction, "loss", f"The bot wins; you lose {self.wager} burgas <:indiar:1396971369220276365>")
        elif not available_positions(self.board):
            await self.finish(interaction, "draw", "Draw — your wager is refunded <:goon:1505288457017229312>")
        else:
            await interaction.response.edit_message(
                content=self.content(), view=self
            )

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
                        f"Time's up — your wager was refunded. <:goon:1505288457017229312>"
                        f"Your balance is now {new_balance} burgas."
                    ),
                    view=self,
                )
            except discord.DiscordException:
                pass


async def tictactoe(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        await interaction.response.send_message(
            "The wager must be greater than zero <:killsyou:1511341401277989005>", ephemeral=True
        )
        return

    user_id = str(interaction.user.id)
    reserved, balance = reserve_wager(user_id, amount)
    if not reserved:
        await interaction.response.send_message(
            f"You only have {balance} burgas, so you cannot wager {amount} <:killsyou:1511341401277989005>",
            ephemeral=True,
        )
        return

    view = TicTacToeView(interaction.user.id, amount)
    await interaction.response.send_message(view.content(), view=view)
    view.message = await interaction.original_response()


module = {
    "type": "command",
    "name": "tictactoe",
    "description": "Play tic-tac-toe for burgas",
    "callback": tictactoe,
}
