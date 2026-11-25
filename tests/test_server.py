"""server (headless) pieces: file secrets backend, approvals from the terminal, `up` with startup panes, working rules"""
import sys, os, json, stat, tempfile, threading, time, subprocess, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from raidpoint import core

class T(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = {k: getattr(core, k) for k in ("DATA", "REQDIR", "SECRETS_DIR", "SECRETS_REV", "load_projects", "load_config",
                                                    "TMUX", "agents_cfg", "MEMDIR", "BRIEFING_DIR")}
        core.DATA = self.tmp; core.REQDIR = self.tmp / "req"; core.REQDIR.mkdir()
        core.SECRETS_DIR = self.tmp / "secrets"; core.SECRETS_REV = self.tmp / "rev.json"
        core.MEMDIR = self.tmp / "memory"; core.BRIEFING_DIR = self.tmp / "briefing"
        self.cfg = {"agents": {"git": "push", "rules": ""}, "secrets": {"backend": "file"}}
        core.load_config = lambda: self.cfg
        self.env = os.environ.pop("RAIDPOINT_SECRETS", None)
    def tearDown(self):
        for k, v in self.saved.items(): setattr(core, k, v)
        if self.env is not None: os.environ["RAIDPOINT_SECRETS"] = self.env

    # ---- secrets in files
    def test_file_backend_roundtrip_and_permissions(self):
        self.assertEqual(core.secrets_backend(), "file")
        self.assertTrue(core.secret_set("a/b ../x", "TOKEN", "v4lue\n"))
        self.assertTrue(core.secret_set("a/b ../x", "OTHER", "zz"))
        self.assertEqual(core.secret_get("a/b ../x", "TOKEN"), "v4lue\n")            # exact bytes
        self.assertEqual(core.secret_names("a/b ../x"), ["OTHER", "TOKEN"])
        files = list(core.SECRETS_DIR.iterdir())
        self.assertEqual(len(files), 1)                                               # the odd name did not escape the folder
        self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(core.SECRETS_DIR.stat().st_mode), 0o700)
        self.assertEqual(core.secret_names("other"), [])                              # projects are separate
        self.assertTrue(core.secret_rm("a/b ../x", "TOKEN")); self.assertFalse(core.secret_rm("a/b ../x", "TOKEN"))
        self.assertIsNone(core.secret_get("a/b ../x", "TOKEN"))
        self.assertTrue(core.secret_rm("a/b ../x", "OTHER"))
        self.assertEqual(list(core.SECRETS_DIR.iterdir()), [])                        # empty project leaves no file behind
        self.assertEqual(json.loads(core.SECRETS_REV.read_text())["a/b ../x"], 4)     # every change is announced to sessions

    def test_backend_default_and_env(self):
        self.cfg["secrets"]["backend"] = "keyring"; self.assertEqual(core.secrets_backend(), "keyring")
        self.cfg["secrets"] = {}; self.assertEqual(core.secrets_backend(), "keyring")
        os.environ["RAIDPOINT_SECRETS"] = "file"
        try: self.assertEqual(core.secrets_backend(), "file")
        finally: del os.environ["RAIDPOINT_SECRETS"]

    # ---- approvals without the app
    def test_approve_from_terminal(self):
        res = {}
        t = threading.Thread(target=lambda: res.update(ok=core.ask_approval("secret", "p", "Command: x", timeout=10))); t.start()
        for _ in range(50):
            reqs = core.pending_requests()
            if reqs: break
            time.sleep(0.1)
        self.assertEqual(len(reqs), 1); self.assertEqual(reqs[0]["kind"], "secret")
        self.assertIsNone(core.answer_request("zzzz", True))                          # not an id
        self.assertIsNone(core.answer_request("../../etc", True))
        self.assertEqual(core.answer_request(reqs[0]["id"][:4], True)["status"], "approved")     # unique prefix is enough
        t.join(5); self.assertTrue(res["ok"])
        self.assertEqual(core.pending_requests(), [])

    def test_deny_and_no_answer(self):
        res = {}
        t = threading.Thread(target=lambda: res.update(ok=core.ask_approval("send", "p", "x", timeout=10))); t.start()
        for _ in range(50):
            if core.pending_requests(): break
            time.sleep(0.1)
        rid = core.pending_requests()[0]["id"]
        self.assertTrue(core.answer_request(rid, False)); self.assertIsNone(core.answer_request(rid, True))   # only once
        t.join(5); self.assertFalse(res["ok"])
        self.assertFalse(core.ask_approval("send", "p", "x", timeout=1))              # nobody answers = denied
        (core.REQDIR / "0123456789.json").write_text(json.dumps({"id": "0123456789", "status": "pending", "ts": time.time() - 999}))
        self.assertEqual(core.pending_requests(), [])                                 # expired requests are not offered

    # ---- working rules in the briefing
    def test_working_rules(self):
        self.assertIn("git push", core.working_rules()[0])
        self.cfg["agents"] = {"git": "commit", "rules": "Never add AI attribution."}
        r = core.working_rules()
        self.assertIn("Do not push", r[0]); self.assertEqual(r[1], "Never add AI attribution.")
        self.assertEqual(core.working_rules(git=False), ["Never add AI attribution."])    # no git protocol outside a repository
        self.cfg["agents"] = {"git": "off", "rules": ""}; self.assertEqual(core.working_rules(), [])
        self.cfg = {}; self.assertIn("git push", core.working_rules()[0])              # old config without the section

    def test_briefing_has_rules_only_in_git_projects(self):
        repo = self.tmp / "repo"; repo.mkdir(); plain = self.tmp / "plain"; plain.mkdir()
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, env=env)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "x"], check=True, env=env)
        core.load_projects = lambda: {"g": {"dir": str(repo)}, "n": {"dir": str(plain)}}
        self.cfg["agents"] = {"git": "push", "rules": "HOUSE RULE"}
        b = core.briefing("g"); self.assertIn("## Working rules", b); self.assertIn("Git protocol", b); self.assertIn("HOUSE RULE", b)
        b = core.briefing("n"); self.assertNotIn("Git protocol", b); self.assertIn("HOUSE RULE", b)

    # ---- up
    def test_up_starts_only_what_should_run(self):
        if not __import__("shutil").which("tmux"): self.skipTest("no tmux")
        sock = f"devraid-test-{os.getpid()}"
        core.TMUX = ["tmux", "-L", sock, "-f", "/dev/null"]
        core.agents_cfg = lambda: [{"name": "Sleeper", "cmd": "sleep 300"}, {"name": "Shell", "cmd": ""}]
        d = str(self.tmp)
        projs = {"auto": {"dir": d, "startup": ["Sleeper", "sleep 301"]}, "plain": {"dir": d, "startup": []},
                 "flag": {"dir": d, "autostart": True}, "term": {"dir": d, "term": True}, "srv": {"dir": "", "host": "h"},
                 "gone": {"dir": d + "/nope", "startup": ["Sleeper"]}}
        core.load_projects = lambda: projs
        try:
            res = dict(core.up())
            self.assertEqual(set(res), {"auto", "flag", "gone"})
            self.assertTrue(res["auto"].startswith("started (2")); self.assertIn("folder not found", res["gone"])
            self.assertEqual(core.alive(), {"auto", "flag"})
            panes = core.list_panes("auto")
            self.assertEqual(sorted(p["title"] for p in panes), ["Sleeper", "sleep"])
            self.assertEqual(dict(core.up())["auto"], "already running")              # idempotent: never a second copy
            self.assertEqual(len(core.list_panes("auto")), 2)
            res = dict(core.up(["plain", "srv", "what"]))
            self.assertTrue(res["plain"].startswith("started (0")); self.assertIn("remote", res["srv"]); self.assertEqual(res["what"], "unknown project")
            self.assertEqual(set(dict(core.up(everything=True))), {"auto", "plain", "flag", "gone"})   # plain terminals stay out
        finally:
            subprocess.run(core.TMUX + ["kill-server"], capture_output=True)

    def test_startup_cmd(self):
        core.agents_cfg = lambda: [{"name": "Claude", "cmd": "claude"}]
        core.load_projects = lambda: {"p": {"dir": str(self.tmp)}}
        self.assertEqual(core.startup_cmd("p", "claude"), ("Claude", "claude"))      # preset, case-insensitive; Claude gets no briefing arg
        self.assertEqual(core.startup_cmd("p", "/usr/bin/htop -d 5"), ("htop", "/usr/bin/htop -d 5"))

if __name__ == "__main__":
    unittest.main()
