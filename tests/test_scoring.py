import importlib
import os
import tempfile
import unittest


class ScoringStorageTestCase(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

        import services.storage as storage
        import services.scoring as scoring

        self.storage = importlib.reload(storage)
        self.scoring = importlib.reload(scoring)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_add_points_and_profile(self):
        uid = 101
        self.scoring.upsert_user(uid, "Alice", "alice")
        self.scoring.add_points(uid, 7)
        self.scoring.add_points(uid, 5)

        total, today = self.scoring.get_profile(uid)
        self.assertEqual(total, 12)
        self.assertEqual(today, 12)
        self.assertEqual(self.scoring.get_user_display(uid), "@alice")

    def test_leaderboard_sorted(self):
        self.scoring.add_points(1, 2)
        self.scoring.add_points(2, 10)
        self.scoring.add_points(3, 5)

        board = self.scoring.get_leaderboard(limit=3)
        self.assertEqual(board, [(2, 10), (3, 5), (1, 2)])


if __name__ == "__main__":
    unittest.main()
