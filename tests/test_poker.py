import unittest
from unittest.mock import AsyncMock, Mock, patch

from commands.cards import RANKS, SUITS, card_text, hand_text, new_deck
from commands.poker import PokerView, compare_hands, evaluate_hand, hand_name, poker


def card(rank, suit="♠"):
    return rank, suit


class PokerHandTests(unittest.TestCase):
    def test_deck_uses_the_shared_card_symbols(self):
        deck = new_deck()

        self.assertEqual(len(deck), 52)
        self.assertEqual(len(set(deck)), 52)
        self.assertEqual(set(rank for rank, _ in deck), set(RANKS))
        self.assertEqual(set(suit for _, suit in deck), set(SUITS))
        self.assertEqual(card_text(card("A", "♠")), "A♠")

    def test_evaluate_hand_orders_standard_poker_categories(self):
        hands = [
            [card("A"), card("K"), card("9"), card("5"), card("2", "♥")],
            [card("A"), card("A", "♥"), card("9"), card("5"), card("2", "♥")],
            [card("A"), card("A", "♥"), card("9"), card("9", "♥"), card("2", "♥")],
            [card("A"), card("A", "♥"), card("A", "♦"), card("5"), card("2", "♥")],
            [card("2"), card("3", "♥"), card("4"), card("5", "♥"), card("6", "♦")],
            [card("A"), card("J"), card("7"), card("5"), card("2")],
            [
                card("K"),
                card("K", "♥"),
                card("K", "♦"),
                card("8", "♥"),
                card("8", "♦"),
            ],
            [card("Q"), card("Q", "♥"), card("Q", "♦"), card("Q", "♣"), card("3")],
            [card("10"), card("J"), card("Q"), card("K"), card("A")],
        ]

        categories = [evaluate_hand(hand)[0] for hand in hands]

        self.assertEqual(categories, list(range(9)))
        self.assertEqual(hand_name(hands[-1]), "Royal flush")

    def test_ace_low_straight_is_ranked_below_six_high_straight(self):
        wheel = [
            card("A"),
            card("2", "♥"),
            card("3", "♦"),
            card("4", "♣"),
            card("5", "♠"),
        ]
        six_high = [
            card("2"),
            card("3", "♥"),
            card("4", "♦"),
            card("5", "♣"),
            card("6", "♠"),
        ]

        self.assertEqual(evaluate_hand(wheel), (4, (5,)))
        self.assertLess(compare_hands(wheel, six_high), 0)

    def test_evaluate_hand_requires_five_cards(self):
        with self.assertRaises(ValueError):
            evaluate_hand([card("A"), card("K")])


class PokerCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_poker_starts_an_ephemeral_view(self):
        interaction = Mock()
        interaction.user.id = 42
        interaction.response.send_message = AsyncMock()
        interaction.original_response = AsyncMock(return_value=Mock())

        with patch("commands.poker.reserve_wager", return_value=(True, 10)), patch(
            "commands.poker.PokerView"
        ) as view_class:
            view_class.return_value.content.return_value = "poker game"

            await poker(interaction, 5)

        interaction.response.send_message.assert_awaited_once_with(
            "poker game",
            view=view_class.return_value,
            ephemeral=True,
        )

    async def test_invalid_wager_is_ephemeral(self):
        interaction = Mock()
        interaction.response.send_message = AsyncMock()

        await poker(interaction, 0)

        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(
            interaction.response.send_message.await_args.kwargs["ephemeral"]
        )

    async def test_finished_hand_is_posted_publicly(self):
        view = PokerView(42, 5)
        interaction = Mock()
        interaction.response.edit_message = AsyncMock()
        interaction.followup.send = AsyncMock()

        with patch("commands.poker.settle_wager", return_value=15):
            await view.finish(interaction, "win", "You win 5 burgas")

        interaction.response.edit_message.assert_awaited_once()
        self.assertIn(
            "final result is posted publicly",
            interaction.response.edit_message.await_args.kwargs["content"],
        )
        interaction.followup.send.assert_awaited_once()
        result = interaction.followup.send.await_args.args[0]
        self.assertIn("Poker result for <@42>", result)
        self.assertIn(hand_text(view.dealer_hand), result)
        self.assertFalse(interaction.followup.send.await_args.kwargs["ephemeral"])


if __name__ == "__main__":
    unittest.main()
