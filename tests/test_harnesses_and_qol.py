"""Tests for multi-harness integration (Claude, Antigravity/agy, Aider, Codex) and QoL features (pin, note, resume)."""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


def _load_cli(home_dir):
    os.environ["RAIDPOINT_HOME"] = str(home_dir)
    for m in list(sys.modules):
        if m == "raidpoint" or m.startswith("raidpoint."):
            del sys.modules[m]
    loader = SourceFileLoader("raidpoint_cli_test", str(ROOT / "bin" / "raidpoint"))
    spec = importlib.util.spec_from_loader("raidpoint_cli_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class HarnessAndQoLTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="devraid-hq-"))
        self.proj_dir = self.tmp / "repo"
        self.proj_dir.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.proj_dir, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.local"], cwd=self.proj_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.proj_dir, check=True)
        (self.proj_dir / "README.md").write_text("# hi\n")
        subprocess.run(["git", "add", "."], cwd=self.proj_dir, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.proj_dir, check=True)

        self.rp_home = self.tmp / "rp_home"
        self.cli = _load_cli(self.rp_home)
        self.core = self.cli.core
        self.core.update_projects(lambda db: db.update({
            "alpha": {"dir": str(self.proj_dir), "startup": []},
            "beta": {"dir": str(self.proj_dir), "startup": []},
        }))

    def test_launch_cmds_all_harnesses(self):
        # agy without hooks gets briefing pointer and -i
        with mock.patch.object(self.core, "_agy_has_hooks", return_value=False):
            cmd, keys = self.core.agent_launch_cmd({"name": "Antigravity", "cmd": "agy"}, "fix bug", "alpha")
            self.assertFalse(keys)
            self.assertIn("agy -i ", cmd)
            self.assertIn("briefing/alpha.md", cmd)
            self.assertIn("fix bug", cmd)

        # agy with hooks does not wrap prompt with briefing pointer
        with mock.patch.object(self.core, "_agy_has_hooks", return_value=True):
            cmd, keys = self.core.agent_launch_cmd({"name": "Antigravity", "cmd": "agy"}, "fix bug", "alpha")
            self.assertFalse(keys)
            self.assertEqual(cmd, "agy -i 'fix bug'")
            cmd_empty, keys_empty = self.core.agent_launch_cmd({"name": "Antigravity", "cmd": "agy"}, "", "alpha")
            self.assertFalse(keys_empty)
            self.assertEqual(cmd_empty, "agy")

        # aider gets --read <briefing> and uses send-keys for prompt
        cmd_a, keys_a = self.core.agent_launch_cmd({"name": "Aider", "cmd": "aider"}, "do x", "alpha")
        self.assertTrue(keys_a)
        self.assertIn("--read ", cmd_a)
        self.assertIn("briefing/alpha.md", cmd_a)

        # codex gets briefing pointer as positional prompt arg
        cmd_c, keys_c = self.core.agent_launch_cmd({"name": "Codex", "cmd": "codex"}, "do y", "alpha")
        self.assertFalse(keys_c)
        self.assertIn("briefing/alpha.md", cmd_c)
        self.assertIn("do y", cmd_c)

    def test_agy_hooks_inject_briefing_and_log_memory(self):
        # SessionStart
        buf = io.StringIO()
        payload = {"hookEventName": "SessionStart", "conversationId": "conv-123456",
                   "cwd": str(self.proj_dir), "transcriptPath": "/tmp/t.jsonl"}
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), redirect_stdout(buf):
            self.cli.cmd_hook()
        out = json.loads(buf.getvalue())
        self.assertIn("injectSteps", out)
        msg = out["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("project 'alpha'", msg)

        # PreInvocation -> logs UserPromptSubmit so sessions() & mem_backfill() see it
        buf2 = io.StringIO()
        p2 = {"hookEventName": "PreInvocation", "conversationId": "conv-123456",
              "cwd": str(self.proj_dir), "lastUserInput": "implement agy hooks"}
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(p2))), redirect_stdout(buf2):
            self.cli.cmd_hook()
        self.assertEqual(json.loads(buf2.getvalue()), {})

        # Stop
        buf3 = io.StringIO()
        p3 = {"hookEventName": "Stop", "conversationId": "conv-123456", "cwd": str(self.proj_dir)}
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(p3))), redirect_stdout(buf3):
            self.cli.cmd_hook()
        self.assertEqual(json.loads(buf3.getvalue()), {})

        S = self.core.sessions("alpha")
        self.assertIn("conv-123456", S)
        self.assertEqual(S["conv-123456"]["harness"], "agy")
        self.assertEqual(S["conv-123456"]["status"], "idle")

        # Backfill with idle_s=0 turns agy session into project memory
        added = self.core.mem_backfill(idle_s=0)
        self.assertEqual(added.get("alpha"), 1)
        mems = self.core.mem_recent("alpha")
        self.assertTrue(any("implement agy hooks" in m["text"] for m in mems))

    def test_pin_note_and_resume(self):
        self.core.pin_project("beta", True)
        self.assertEqual(self.core.ordered_projects(), ["beta", "alpha"])
        self.core.pin_project("beta", False)
        self.assertEqual(self.core.ordered_projects(), ["alpha", "beta"])

        self.core.set_project_note("alpha", "check auth middleware")
        self.assertIn("Sticky note: check auth middleware", self.core.briefing("alpha"))
        res = self.core.project_resume("alpha")
        self.assertIn("# Resume: alpha", res)
        self.assertIn("Note: check auth middleware", res)
        self.assertIn("Branch:", res)

        self.core.set_project_note("alpha", "")
        self.assertNotIn("Sticky note:", self.core.briefing("alpha"))

    def test_agy_orchestrator_provider(self):
        from raidpoint import orchestrator
        prov = orchestrator.get_provider({"provider": "agy"}, project="alpha")
        self.assertEqual(prov.name, "Antigravity")
        r1 = mock.Mock(returncode=0, stdout=json.dumps({"session_id": "s1", "result": "ok1"}), stderr="")
        r2 = mock.Mock(returncode=0, stdout=json.dumps({"session_id": "s1", "result": "ok2"}), stderr="")
        with mock.patch("shutil.which", return_value="/usr/bin/agy"), \
             mock.patch("subprocess.run", side_effect=[r1, r2]) as run_mock:
            self.assertEqual(prov.send("hello"), "ok1")
            self.assertEqual(prov.send("follow up"), "ok2")
            self.assertEqual(prov.session, "s1")
            self.assertIn("--resume", run_mock.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
