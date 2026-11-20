import sys, os, json, time, tempfile, subprocess, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from raidpoint import core

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

class T(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"; self.repo.mkdir()
        for c in (["init", "-q"], ["remote", "add", "origin", "https://user:SEGREDO@github.com/x/y.git"]):
            subprocess.run(["git", "-C", str(self.repo), *c], check=True, env=ENV)
        (self.repo / "README.md").write_text("hi"); (self.repo / "AGENTS.md").write_text("# Meu arquivo\ntexto do usuario\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True, env=ENV)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "primeiro commit"], check=True, env=ENV)
        self.saved = (core.DATA, core.MEMDIR, core.BRIEFING_DIR, core.EVENTS, core.load_projects)
        core.DATA = self.tmp / "data"; core.DATA.mkdir(); core.MEMDIR = core.DATA / "memory"; core.BRIEFING_DIR = core.DATA / "briefing"
        core.EVENTS = core.DATA / "events.jsonl"
        self.projs = {"p": {"dir": str(self.repo), "startup": []}, "srv": {"dir": "", "host": "x", "startup": []}}
        core.load_projects = lambda: self.projs
    def tearDown(self):
        core.DATA, core.MEMDIR, core.BRIEFING_DIR, core.EVENTS, core.load_projects = self.saved

    def events(self, sid, prompts):
        now = time.time() - 600
        evs = [{"ts": now, "event": "SessionStart", "session_id": sid}] + \
              [{"ts": now + 10 + i, "event": "UserPromptSubmit", "session_id": sid, "prompt": p} for i, p in enumerate(prompts)]
        core.EVENTS.write_text("\n".join(json.dumps(e) for e in evs) + "\n")

    def test_briefing_has_context_tools_memory_and_hides_credentials(self):
        core.mem_add("p", "usar sqlite em vez de postgres porque offline", kind="decision")
        b = core.briefing("p")
        self.assertIn("project 'p'", b); self.assertIn("primeiro commit", b); self.assertIn("README.md", b)
        for tool in ("memory_add", "memory_search", "spawn_agent", "run_with_secrets"): self.assertIn(f"`{tool}`", b)
        self.assertIn("[decision] usar sqlite", b); self.assertIn("Memory protocol", b)
        self.assertNotIn("SEGREDO", b); self.assertIn("raidpoint mem", b)             # credentials never leak; CLI fallback present

    def test_empty_memory_tells_the_agent_to_start_it(self):
        self.assertIn("No memories recorded yet", core.briefing("p"))

    def test_curated_memories_come_before_session_logs(self):
        core.mem_add("p", "log automatico antigo", kind="session"); time.sleep(1.1); core.mem_add("p", "decisao importante", kind="decision")
        b = core.briefing("p"); self.assertLess(b.index("decisao importante"), b.index("log automatico"))

    def test_remote_project_briefing(self):
        b = core.briefing("srv"); self.assertIn("remote server `x`", b)

    def test_session_log_is_recorded_once(self):
        self.events("abcdef123456", ["corrige o bug do login", "agora os testes"])
        path = core.mem_session_log("p", "abcdef123456")
        self.assertTrue(path); m = core.mem_recent("p")[0]
        self.assertEqual(m["kind"], "session"); self.assertIn("corrige o bug do login", m["text"]); self.assertIn("2 prompt(s)", m["text"])
        self.assertIsNone(core.mem_session_log("p", "abcdef123456"))                  # SessionEnd twice: no duplicate
        self.assertEqual(len(core.mem_recent("p")), 1)

    def test_backfill_skips_live_sessions_and_is_idempotent(self):
        old, live = time.time() - 7200, time.time() - 30
        evs = [{"ts": old, "event": "UserPromptSubmit", "session_id": "oldsess11", "project": "p", "prompt": "tarefa antiga"},
               {"ts": live, "event": "UserPromptSubmit", "session_id": "livesess2", "project": "p", "prompt": "ainda rodando"},
               {"ts": old, "event": "UserPromptSubmit", "session_id": "ghostsess", "project": "removido", "prompt": "projeto que nao existe"}]
        core.EVENTS.write_text("\n".join(json.dumps(e) for e in evs) + "\n")
        self.assertEqual(core.mem_backfill(), {"p": 1})                  # live session and unknown project are skipped
        self.assertEqual(core.mem_backfill(), {})                        # second run adds nothing
        m = core.mem_recent("p"); self.assertEqual(len(m), 1); self.assertIn("tarefa antiga", m[0]["text"])
        self.assertTrue(m[0]["ts"].startswith(time.strftime("%Y-%m-%d", time.localtime(old))))

    def test_session_without_prompts_logs_nothing(self):
        self.events("zzzz0000", []); self.assertIsNone(core.mem_session_log("p", "zzzz0000"))
        self.assertIsNone(core.mem_session_log("p", None)); self.assertEqual(core.mem_recent("p"), [])

    def test_launch_per_harness(self):
        codex = {"name": "Codex", "cmd": "codex"}
        c, keys = core.agent_launch_cmd(codex, "", "p")
        self.assertIn("briefing/p.md", c); self.assertIn("wait for my instructions", c); self.assertFalse(keys)
        c, _ = core.agent_launch_cmd(codex, "faz X", "p"); self.assertIn("then do this task", c); self.assertIn("faz X", c)
        self.assertTrue((core.BRIEFING_DIR / "p.md").exists())
        c, _ = core.agent_launch_cmd({"name": "Aider", "cmd": "aider"}, "", "p"); self.assertIn("--read", c); self.assertIn("briefing/p.md", c)
        self.assertEqual(core.agent_launch_cmd({"name": "Claude", "cmd": "claude"}, "", "p"), ("claude", False))   # claude: via hook
        self.assertEqual(core.agent_launch_cmd(codex, "", "srv"), ("codex", False))      # remote: file is not there
        self.assertEqual(core.agent_launch_cmd(codex, ""), ("codex", False))              # no project: untouched
        self.assertEqual(core.agent_launch_cmd({"name": "Shell", "cmd": ""}, "", "p"), ("", False))

    def test_agents_md_is_idempotent_and_keeps_user_content(self):
        f, err = core.write_agents_md("p"); self.assertIsNone(err)
        t1 = Path(f).read_text(); self.assertIn("texto do usuario", t1); self.assertIn(core.AGENTS_BEGIN, t1)
        core.write_agents_md("p"); self.assertEqual(Path(f).read_text(), t1)               # second run: identical
        core.write_agents_md("p", remove=True); self.assertEqual(Path(f).read_text(), "# Meu arquivo\ntexto do usuario\n")      # back to the original
        self.assertIsNotNone(core.write_agents_md("srv")[1])                               # remote: refuses

if __name__ == "__main__": unittest.main()
