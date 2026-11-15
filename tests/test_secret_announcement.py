"""AIs are told which secrets exist (names only) and what changes: python3 -m unittest discover -s tests"""
import os, sys, tempfile, unittest
from pathlib import Path

os.environ.setdefault("RAIDPOINT_HOME", tempfile.mkdtemp(prefix="devraid-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from raidpoint import core   # noqa: E402

class Announce(unittest.TestCase):
    def setUp(self):
        for f in (core.SECRETS_REV, core.SECRETS_SEEN): f.unlink(missing_ok=True)
        self.names = []
        orig = core.secret_names; self.addCleanup(setattr, core, "secret_names", orig)
        core.secret_names = lambda project: sorted(self.names)
        self.bump = lambda: core._bump_rev("p")

    def test_session_start_lists_names_and_how_to_use_them(self):
        self.names = ["B_KEY", "A_KEY"]
        out = core.secret_announcement("s1", "p", "SessionStart")
        self.assertIn("Available by name: A_KEY, B_KEY.", out); self.assertIn("run_with_secrets", out)
        self.assertEqual(core.secret_announcement("s1", "p", "SessionStart").count("A_KEY"), 1)   # a restart repeats the list
        self.names = []; self.assertEqual(core.secret_announcement("s2", "p", "SessionStart"), "")   # nothing to say

    def test_added_and_removed_are_announced_once_per_session(self):
        self.names = ["A"]; core.secret_announcement("s1", "p", "SessionStart")
        self.assertEqual(core.secret_announcement("s1", "p", "UserPromptSubmit"), "")             # no change: silent
        self.names = ["A", "NEW"]; self.bump()
        out = core.secret_announcement("s1", "p", "UserPromptSubmit")
        self.assertIn("Added: NEW.", out); self.assertIn("run_with_secrets", out); self.assertNotIn("Removed", out)
        self.assertEqual(core.secret_announcement("s1", "p", "UserPromptSubmit"), "")             # told once
        self.names = ["NEW"]; self.bump()
        out = core.secret_announcement("s1", "p", "UserPromptSubmit")
        self.assertIn("Removed: A.", out); self.assertNotIn("Added", out)

    def test_each_session_is_told_separately_and_late_sessions_get_the_full_list(self):
        self.names = ["A"]; self.bump()
        # a session that never saw SessionStart (hook installed mid-session) learns the full list on its first prompt
        self.assertIn("Available by name: A.", core.secret_announcement("late", "p", "UserPromptSubmit"))
        self.assertEqual(core.secret_announcement("late", "p", "UserPromptSubmit"), "")
        self.names = ["A", "B"]; self.bump()
        self.assertIn("Added: B.", core.secret_announcement("late", "p", "UserPromptSubmit"))
        self.assertIn("Available by name: A, B.", core.secret_announcement("other", "p", "UserPromptSubmit"))   # a new session: full list

    def test_values_never_appear_and_no_project_means_silence(self):
        self.names = ["TOKEN"]; out = core.secret_announcement("s", "p", "SessionStart")
        self.assertNotIn("=", out.split("\n")[1])                                                  # names only, no NAME=value
        self.assertEqual(core.secret_announcement("s", None, "SessionStart"), ""); self.assertEqual(core.secret_announcement(None, "p", "SessionStart"), "")

    def test_seen_state_is_bounded(self):
        self.names = ["A"]
        for i in range(230): core.secret_announcement(f"sess{i}", "p", "SessionStart")
        self.assertLessEqual(len(core._json_file(core.SECRETS_SEEN)), 200)

if __name__ == "__main__":
    unittest.main()
