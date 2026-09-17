import unittest
from unittest.mock import AsyncMock, Mock, patch

from commands.burger import (
    BELLYACHE_USER_ID,
    BURGA_MILESTONES,
    BURGA_QUEEN_USER_ID,
    BURGA_THIEF_USER_ID,
    UNLUCKY_USER_ID,
    eatburga,
    is_big_milestone,
)


class BurgaMilestoneTests(unittest.TestCase):
    def test_big_milestones_include_initial_and_repeating_thresholds(self):
        for count in (*BURGA_MILESTONES, 2000, 3000):
            with self.subTest(count=count):
                self.assertTrue(is_big_milestone(count))

    def test_non_milestones_stay_quiet(self):
        for count in (1, 9, 11, 20, 99, 101, 999, 1001):
            with self.subTest(count=count):
                self.assertFalse(is_big_milestone(count))


class EatBurgaCommandTests(unittest.IsolatedAsyncioTestCase):
    def make_interaction(self):
        interaction = Mock()
        interaction.user.id = 42
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        return interaction

    async def test_routine_use_shows_a_private_count_confirmation(self):
        interaction = self.make_interaction()

        with patch("commands.burger.adjust_balance", return_value=11):
            await eatburga(interaction)

        interaction.response.send_message.assert_awaited_once()
        self.assertIn("logged", interaction.response.send_message.await_args.args[0])
        self.assertIn("11 burgas now", interaction.response.send_message.await_args.args[0])
        self.assertTrue(interaction.response.send_message.await_args.kwargs["ephemeral"])
        interaction.response.defer.assert_not_awaited()
        interaction.followup.send.assert_not_awaited()

    async def test_milestone_is_announced_publicly_after_private_confirmation(self):
        interaction = self.make_interaction()

        with patch("commands.burger.adjust_balance", return_value=100):
            await eatburga(interaction)

        interaction.response.defer.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(
            interaction.response.send_message.await_args.kwargs["ephemeral"]
        )
        self.assertIn("100", interaction.response.send_message.await_args.args[0])
        interaction.followup.send.assert_awaited_once()
        self.assertIn("reached 100 burgas", interaction.followup.send.await_args.args[0])
        self.assertIn("<@42>", interaction.followup.send.await_args.args[0])
        self.assertFalse(interaction.followup.send.await_args.kwargs["ephemeral"])

    async def test_bellyache_user_is_reminded_every_fifth_burga(self):
        interaction = self.make_interaction()
        interaction.user.id = int(BELLYACHE_USER_ID)

        with patch("commands.burger.adjust_balance", return_value=15):
            await eatburga(interaction)

        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(
            interaction.response.send_message.await_args.kwargs["ephemeral"]
        )
        self.assertIn("bellyache", interaction.response.send_message.await_args.args[0])
        interaction.followup.send.assert_not_awaited()

    async def test_queen_can_receive_two_burgas(self):
        interaction = self.make_interaction()
        interaction.user.id = int(BURGA_QUEEN_USER_ID)
        adjust = Mock(return_value=12)

        with patch("commands.burger.adjust_balance", adjust), patch(
            "commands.burger.random.random", return_value=0.1
        ):
            await eatburga(interaction)

        adjust.assert_called_once_with(BURGA_QUEEN_USER_ID, 2)
        self.assertIn("12 burgas now", interaction.response.send_message.await_args.args[0])
        interaction.followup.send.assert_not_awaited()

    async def test_unlucky_user_can_lose_the_burga_just_eaten(self):
        interaction = self.make_interaction()
        interaction.user.id = int(UNLUCKY_USER_ID)
        adjust = Mock(side_effect=[10, 9])

        with patch("commands.burger.adjust_balance", adjust), patch(
            "commands.burger.random.random", return_value=0.01
        ):
            await eatburga(interaction)

        self.assertEqual(
            adjust.call_args_list,
            [
                unittest.mock.call(UNLUCKY_USER_ID, 1),
                unittest.mock.call(UNLUCKY_USER_ID, -1),
            ],
        )
        self.assertIn("9 burgas now", interaction.response.send_message.await_args.args[0])
        interaction.followup.send.assert_not_awaited()

    async def test_designated_thief_can_steal_from_a_target(self):
        interaction = self.make_interaction()
        interaction.user.id = int(BURGA_THIEF_USER_ID)
        target = Mock(id=99, bot=False, display_name="Victim")
        result = {"stolen": True, "thief_balance": 4, "victim_balance": 0}

        with patch("commands.burger.steal_burga", return_value=result) as steal:
            await eatburga(interaction, target)

        steal.assert_called_once_with(BURGA_THIEF_USER_ID, 99)
        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(
            interaction.response.send_message.await_args.kwargs["ephemeral"]
        )
        self.assertIn("Victim", interaction.response.send_message.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
