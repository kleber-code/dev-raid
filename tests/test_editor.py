"""Tests for CLI editor (nvim/micro) and file manager (ranger/nnn) commands, project files, and worktree lifecycle."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("RAIDPOINT_HOME", tempfile.mkdtemp(prefix="devraid-test-ed-"))
sys.path.insert(0, str(ROOT))

from raidpoint import core


class CliEditorAndWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="devraid-repo-"))
        subprocess.run(["git", "-C", str(self.tmp), "init", "-b", "main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.name", "Test"], check=True)
        (self.tmp / "app.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "util.js").write_text("const x = 42;\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "commit", "-m", "init"], check=True, capture_output=True)

    def test_project_files_and_line_diff(self):
        files = core.project_files(str(self.tmp))
        self.assertEqual(files, ["app.py", "sub/util.js"])
        (self.tmp / "app.py").write_text("def hello():\n    return 2\n    # added\n", encoding="utf-8")
        marks = core.git_line_diff(str(self.tmp), "app.py")
        self.assertIn(2, marks)
        self.assertIn(3, marks)
        self.assertEqual(core.git_first_changed_line(str(self.tmp), "app.py"), 2)

    def test_worktree_merge_and_remove(self):
        core.update_projects(lambda db: db.__setitem__("demo", {"dir": str(self.tmp), "startup": []}))
        wt_path, err = core.make_worktree("demo", "claude")
        self.assertIsNone(err)
        self.assertTrue(os.path.isdir(wt_path))
        (Path(wt_path) / "agent_feature.py").write_text("FEATURE = True\n", encoding="utf-8")
        ok, _ = core.git_commit(wt_path, "add agent feature")
        self.assertTrue(ok)
        merged, msg = core.git_merge_worktree(str(self.tmp), wt_path)
        self.assertTrue(merged, msg)
        self.assertTrue((self.tmp / "agent_feature.py").exists())
        removed, rmsg = core.git_remove_worktree(str(self.tmp), wt_path)
        self.assertTrue(removed, rmsg)
        self.assertFalse(os.path.exists(wt_path))

    def test_editor_and_file_manager_commands(self):
        orig_which = core.shutil.which
        self.addCleanup(setattr, core.shutil, "which", orig_which)
        core.shutil.which = lambda exe: f"/usr/bin/{exe}"

        cfg_nvim = {"tools": {"editor": "nvim", "file_manager": "ranger"}}
        self.assertEqual(core.configured_editor(cfg_nvim), "nvim")
        self.assertEqual(core.configured_file_manager(cfg_nvim), "ranger")
        self.assertIn("nvim +42 src/main.py", core.editor_cmd("src/main.py", 42, cfg_nvim))
        self.assertIn("EDITOR=nvim VISUAL=nvim ranger", core.file_manager_cmd(None, cfg_nvim))

        cfg_micro_nnn = {"tools": {"editor": "micro", "file_manager": "nnn"}}
        self.assertIn("micro +15:1 src/main.py", core.editor_cmd("src/main.py", 15, cfg_micro_nnn))
        self.assertIn("EDITOR=micro VISUAL=micro nnn -e", core.file_manager_cmd(None, cfg_micro_nnn))


if __name__ == "__main__":
    unittest.main()
