import sys, os, json, tempfile, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from raidpoint import core

A, B = "a" * 40, "b" * 40

class FakeGH:
    def __init__(self, head, cmp=None, fail_cmp=False):
        self.head, self.cmp, self.fail_cmp, self.calls = head, cmp, fail_cmp, []
    def __call__(self, path, accept="application/vnd.github+json"):
        self.calls.append(path)
        if path.startswith("commits/main"): return self.head + "\n"
        if path.startswith("compare/"):
            if self.fail_cmp: raise OSError("404")
            return json.dumps(self.cmp)
        if path.startswith("commits/"): return json.dumps({"commit": {"message": "msg do head\ncorpo"}})
        raise AssertionError(path)

class T(unittest.TestCase):
    def setUp(self):
        self.o = (core.install_mode, core.installed_commit, core._gh_api, core.UPDATE_STATE, core.load_config)
        self.tmp = tempfile.mkdtemp()
        core.install_mode = lambda: "release"; core.UPDATE_STATE = Path(self.tmp) / "update.json"
        core.load_config = lambda: {"updates": {"auto": True}}
    def tearDown(self):
        core.install_mode, core.installed_commit, core._gh_api, core.UPDATE_STATE, core.load_config = self.o

    def test_same_hash_is_current(self):
        core.installed_commit = lambda: A; core._gh_api = FakeGH(A)
        self.assertEqual(core.check_update()["status"], "current")
        self.assertEqual(core._gh_api.calls, ["commits/main"])           # a single cheap call

    def test_main_ahead_is_available_with_details(self):
        core.installed_commit = lambda: A
        core._gh_api = FakeGH(B, {"status": "ahead", "ahead_by": 3, "commits": [{"commit": {"message": "x"}}, {"commit": {"message": "novo recurso\nmais"}}]})
        r = core.check_update()
        self.assertEqual((r["status"], r["count"], r["subject"], r["from"], r["to"]), ("available", 3, "novo recurso", "aaaaaaa", "bbbbbbb"))

    def test_dev_build_ahead_of_main_is_not_an_update(self):
        core.installed_commit = lambda: A
        core._gh_api = FakeGH(B, {"status": "behind", "ahead_by": 0, "commits": []})     # main is BEHIND the install
        self.assertEqual(core.check_update()["status"], "current")

    def test_unknown_base_still_offers_update(self):
        core.installed_commit = lambda: A; core._gh_api = FakeGH(B, fail_cmp=True)
        r = core.check_update(); self.assertEqual((r["status"], r["subject"]), ("available", "msg do head"))

    def test_unknown_install_never_prompts_or_downgrades(self):
        core.installed_commit = lambda: None; core._gh_api = FakeGH(B)
        self.assertEqual(core.check_update()["status"], "skipped"); self.assertEqual(core._gh_api.calls, [])

    def test_garbage_answer_is_error(self):
        core.installed_commit = lambda: A; core._gh_api = FakeGH("<html>rate limited</html>")
        self.assertEqual(core.check_update()["status"], "error")

    def test_check_never_installs_and_skip_version_is_remembered(self):
        core.installed_commit = lambda: A
        core._gh_api = FakeGH(B, {"status": "ahead", "ahead_by": 1, "commits": [{"commit": {"message": "m"}}]})
        r = core.update_check_due(); self.assertEqual(r["status"], "available")
        core.skip_update(r["to"]); self.assertIsNone(core.update_check_due())          # same version: no more nagging
        core._gh_api = FakeGH("c" * 40, {"status": "ahead", "ahead_by": 2, "commits": [{"commit": {"message": "n"}}]})
        self.assertEqual(core.update_check_due()["status"], "available")                # a newer one asks again

    def test_auto_off_means_no_check(self):
        core.load_config = lambda: {"updates": {"auto": False}}; core.installed_commit = lambda: A; core._gh_api = FakeGH(B)
        self.assertIsNone(core.update_check_due()); self.assertEqual(core._gh_api.calls, [])

if __name__ == "__main__": unittest.main()
