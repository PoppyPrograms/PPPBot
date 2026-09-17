from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import storage


class StealBurgaStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.patches = [
            patch.object(storage, "DATABASE_FILE", database_path),
            patch.object(
                storage,
                "LEGACY_BALANCE_FILE",
                Path(self.temp_dir.name) / "missing-burga.csv",
            ),
            patch.object(
                storage,
                "LEGACY_GAMBLE_STATS_FILE",
                Path(self.temp_dir.name) / "missing-gamble-stats.csv",
            ),
        ]
        for active_patch in self.patches:
            active_patch.start()
        self.addCleanup(self.cleanup_storage)
        storage.initialize_database()

    def cleanup_storage(self):
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temp_dir.cleanup()

    def test_steal_transfers_one_burga_and_enforces_daily_limit(self):
        storage.write_balances({"thief": 0, "victim": 2, "other": 1})

        first = storage.steal_burga("thief", "victim", day="2026-09-17")
        second = storage.steal_burga("thief", "other", day="2026-09-17")
        next_day = storage.steal_burga("thief", "other", day="2026-09-18")

        self.assertEqual(first["stolen"], True)
        self.assertEqual(first["thief_balance"], 1)
        self.assertEqual(first["victim_balance"], 1)
        self.assertEqual(second["reason"], "daily_limit")
        self.assertEqual(next_day["stolen"], True)
        self.assertEqual(
            storage.read_balances(),
            {"thief": 2, "victim": 1, "other": 0},
        )

    def test_empty_target_does_not_consume_daily_steal(self):
        storage.write_balances({"thief": 0, "empty": 0, "victim": 1})

        empty = storage.steal_burga("thief", "empty", day="2026-09-17")
        success = storage.steal_burga("thief", "victim", day="2026-09-17")

        self.assertEqual(empty["reason"], "victim_empty")
        self.assertEqual(success["stolen"], True)

    def test_self_steal_is_rejected(self):
        storage.write_balances({"thief": 1})

        result = storage.steal_burga("thief", "thief", day="2026-09-17")

        self.assertEqual(result["reason"], "self_target")
        self.assertEqual(storage.read_balances(), {"thief": 1})


if __name__ == "__main__":
    unittest.main()
