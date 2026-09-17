import unittest
from unittest.mock import AsyncMock, Mock, patch

from commands.bingo import (
    BOARD_SIDE,
    CARD_SIZE,
    FREE_POSITION,
    NUMBER_MAX,
    BingoView,
    board_text,
    bingo,
    has_bingo,
    new_card,
    number_label,
)


class BingoLogicTests(unittest.TestCase):
    def test_card_has_column_ranges_and_free_center(self):
        card = new_card()

        self.assertEqual(len(card), CARD_SIZE)
        numbers = [number for number in card if number is not None]
        self.assertEqual(len(numbers), 24)
        self.assertEqual(len(set(numbers)), 24)
        self.assertIsNone(card[FREE_POSITION])

        for column in range(BOARD_SIDE):
            column_numbers = [
                card[row * BOARD_SIDE + column]
                for row in range(BOARD_SIDE)
                if card[row * BOARD_SIDE + column] is not None
            ]
            lower = column * 15 + 1
            upper = lower + 14
            self.assertTrue(all(lower <= number <= upper for number in column_numbers))

    def test_bingo_detects_rows_columns_and_diagonals(self):
        self.assertTrue(has_bingo({0, 1, 2, 3, 4, FREE_POSITION}))
        self.assertTrue(has_bingo({0, 5, 10, 15, 20, FREE_POSITION}))
        self.assertTrue(has_bingo({0, 6, 12, 18, 24}))
        self.assertFalse(has_bingo({0, 1, 2, 3, FREE_POSITION}))

    def test_number_label_uses_bingo_columns(self):
        self.assertEqual(number_label(1), "B-1")
        self.assertEqual(number_label(30), "I-30")
        self.assertEqual(number_label(45), "N-45")
        self.assertEqual(number_label(60), "G-60")
        self.assertEqual(number_label(NUMBER_MAX), "O-75")
        self.assertEqual(number_label(None), "—")

    def test_board_uses_fixed_width_boxes(self):
        board = board_text(list(range(1, 13)) + [None] + list(range(14, 26)), {FREE_POSITION})
        lines = board.removeprefix("```text\n").removesuffix("\n```").splitlines()

        self.assertEqual(len({len(line) for line in lines}), 1)
        self.assertTrue(all(line.startswith(("+", "|")) for line in lines))
        self.assertIn("✅", board)


class BingoCommandTests(unittest.IsolatedAsyncioTestCase):
    def make_interaction(self, user_id=42):
        interaction = Mock()
        interaction.user.id = user_id
        interaction.response.edit_message = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()
        return interaction

    async def test_bingo_starts_an_ephemeral_view(self):
        interaction = self.make_interaction()
        interaction.original_response = AsyncMock(return_value=Mock())

        with patch("commands.bingo.reserve_wager", return_value=(True, 10)), patch(
            "commands.bingo.BingoView"
        ) as view_class:
            view_class.return_value.content.return_value = "bingo game"

            await bingo(interaction, 5)

        interaction.response.send_message.assert_awaited_once_with(
            "bingo game",
            view=view_class.return_value,
            ephemeral=True,
        )

    async def test_calling_a_number_edits_the_existing_game_message(self):
        view = BingoView(42, 5)
        view.card = [
            1,
            16,
            31,
            46,
            61,
            2,
            17,
            32,
            47,
            62,
            3,
            18,
            None,
            48,
            63,
            4,
            19,
            34,
            49,
            64,
            5,
            20,
            35,
            50,
            65,
        ]
        interaction = self.make_interaction()

        with patch("commands.bingo.choice", return_value=75):
            await view.call_number(interaction)

        self.assertEqual(view.called_numbers, {75})
        interaction.response.edit_message.assert_awaited_once()
        interaction.response.send_message.assert_not_awaited()
        self.assertIn("O-75", interaction.response.edit_message.await_args.kwargs["content"])

    async def test_false_bingo_claim_is_ephemeral(self):
        view = BingoView(42, 5)
        interaction = self.make_interaction()

        await view.claim_bingo(interaction)

        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(
            interaction.response.send_message.await_args.kwargs["ephemeral"]
        )

    async def test_house_bingo_loses_the_wager(self):
        view = BingoView(42, 5)
        view.card = [None] * 25
        view.house_card = [None] * 25
        view.house_card[0] = 75
        view.house_marked_positions.update({1, 2, 3, 4})
        interaction = self.make_interaction()

        with patch("commands.bingo.choice", return_value=75), patch(
            "commands.bingo.settle_wager", return_value=10
        ) as settle:
            await view.call_number(interaction)

        settle.assert_called_once_with(42, 5, "loss")
        self.assertTrue(view.settled)
        self.assertIn("final result is posted publicly", interaction.response.edit_message.await_args.kwargs["content"])
        interaction.followup.send.assert_awaited_once()
        self.assertIn("house bot won", interaction.followup.send.await_args.args[0])
        self.assertLessEqual(len(interaction.followup.send.await_args.args[0]), 2000)
        self.assertFalse(interaction.followup.send.await_args.kwargs["ephemeral"])

    async def test_player_bingo_names_both_public_winner_and_loser(self):
        view = BingoView(42, 5)
        view.marked_positions.update({0, 1, 2, 3, 4})
        interaction = self.make_interaction()

        with patch("commands.bingo.settle_wager", return_value=15):
            await view.claim_bingo(interaction)

        result = interaction.followup.send.await_args.args[0]
        self.assertIn("<@42> won", result)
        self.assertIn("house bot lost", result)
        self.assertLessEqual(len(result), 2000)

    async def test_timeout_without_bingo_loses_the_wager(self):
        view = BingoView(42, 5)
        view.message = Mock()
        view.message.edit = AsyncMock()
        view.channel = Mock()
        view.channel.send = AsyncMock()

        with patch("commands.bingo.settle_wager", return_value=0) as settle:
            await view.on_timeout()

        settle.assert_called_once_with(42, 5, "loss")
        self.assertIn("final result is posted publicly", view.message.edit.await_args.kwargs["content"])
        view.channel.send.assert_awaited_once()
        self.assertIn("<@42> lost", view.channel.send.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
