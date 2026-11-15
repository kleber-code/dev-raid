"""Orchestrator providers: python3 -m unittest discover -s tests"""
import json, os, stat, sys, tempfile, textwrap, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("RAIDPOINT_HOME", tempfile.mkdtemp(prefix="devraid-test-"))
sys.path.insert(0, str(ROOT))
from raidpoint import orchestrator as orch   # noqa: E402
from raidpoint.orchestrator import ProviderError   # noqa: E402

TOKEN = "tok-123"
SEEN = []            # (method, path, authorization)
DECIDED = []

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj=None, ctype="application/json", raw=None):
        body = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def _auth(self):
        SEEN.append((self.command, self.path, self.headers.get("Authorization")))
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._send(401, {"detail": "unauthorized\nX"}); return False
        return True
    def do_GET(self):
        if not self._auth(): return
        if self.path.startswith("/api/history"):
            self._send(200, {"messages": [{"role": "user", "text": "hi", "ts": 1}, {"role": "system", "text": "no"},
                                          {"role": "assistant", "text": "hello", "ts": 2}, {"role": "user"}, "junk"]})
        elif self.path == "/api/approvals":
            self._send(200, {"approvals": [{"id": 7, "kind": "raid_queue", "tool": "spawn", "summary": "run\x1b[31m 2 agents", "origin": "chat", "created": "t"},
                                           {"id": "../x", "kind": "evil"}]})
        else: self._send(404, {})
    def do_POST(self):
        if not self._auth(): return
        n = int(self.headers.get("Content-Length") or 0); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/chat":
            t = body.get("text")
            if t == "redirect": self.send_response(302); self.send_header("Location", "http://127.0.0.1:1/steal"); self.end_headers()
            elif t == "huge": self._send(200, {"text": "x" * (orch.MAX_BODY + 10)})
            elif t == "stream" and "text/event-stream" in self.headers.get("Accept", ""):
                ev = [{"delta": "he"}, {"delta": "llo"}, {"done": True, "text": "hello"}]
                self._send(200, ctype="text/event-stream", raw="".join(f"data: {json.dumps(e)}\n\n" for e in ev).encode())
            elif t == "streamerr":
                self._send(200, ctype="text/event-stream", raw=b'data: {"error": "boom"}\n\n')
            elif t == "badshape": self._send(200, {"nope": 1})
            else: self._send(200, {"text": "echo: " + str(t)})
        elif self.path.startswith("/api/approvals/") and self.path.endswith("/decide"):
            DECIDED.append((self.path, body)); self._send(200, {"ok": True})
        else: self._send(404, {})

class HttpCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/api"
        d = Path(tempfile.mkdtemp()); cls.tf = d / "token"; cls.tf.write_text(TOKEN + "\n"); cls.tf.chmod(0o600)
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown(); cls.srv.server_close()
    def prov(self, **kw): return orch.HttpProvider({"url": self.url, "token_file": str(self.tf), **kw}, timeout=5, chat_timeout=5)

class HttpProviderTests(HttpCase):
    def test_send_history_approvals_decide(self):
        p = self.prov()
        self.assertEqual(p.send("ping"), "echo: ping")
        self.assertEqual([m["role"] for m in p.history()], ["user", "assistant"])          # junk and 'system' dropped
        a = p.pending_approvals()
        self.assertEqual([x["id"] for x in a], ["7"]); self.assertNotIn("\x1b", a[0]["summary"])   # bad id and control chars gone
        p.decide("7", True); self.assertEqual(DECIDED[-1], ("/api/approvals/7/decide", {"approve": True}))
        with self.assertRaises(ProviderError): p.decide("../x", True)

    def test_streaming_is_optional_and_works(self):
        got = []
        self.assertEqual(self.prov().send("stream", on_delta=got.append), "hello"); self.assertEqual(got, ["he", "llo"])
        with self.assertRaisesRegex(ProviderError, "boom"): self.prov().send("streamerr")

    def test_hostile_or_broken_servers(self):
        p = self.prov()
        with self.assertRaisesRegex(ProviderError, "HTTP 302"): p.send("redirect")            # redirects are never followed
        with self.assertRaisesRegex(ProviderError, "too large"): p.send("huge")
        with self.assertRaisesRegex(ProviderError, "no 'text'"): p.send("badshape")

    def test_bad_token_reports_status_without_leaking(self):
        f = Path(tempfile.mkdtemp(), "t"); f.write_text("wrong"); f.chmod(0o600)
        with self.assertRaisesRegex(ProviderError, r"HTTP 401: unauthorized"):
            orch.HttpProvider({"url": self.url, "token_file": str(f)}, timeout=5).send("x")

    def test_token_is_sent_only_as_bearer_header(self):
        SEEN.clear(); self.prov().send("x")
        self.assertEqual(SEEN[-1][2], f"Bearer {TOKEN}"); self.assertNotIn(TOKEN, SEEN[-1][1])

class ConfigValidation(unittest.TestCase):
    def test_url_and_token_rules(self):
        tf = Path(tempfile.mkdtemp(), "t"); tf.write_text("abc"); tf.chmod(0o600)
        ok = {"url": "https://example.org/api", "token_file": str(tf)}
        orch.HttpProvider(ok)
        for bad in ("http://example.org/api", "ftp://x/api", "https://u:p@example.org/api", "https://example.org/api?x=1", "", "example.org"):
            with self.assertRaises(ProviderError, msg=bad): orch.HttpProvider({**ok, "url": bad})
        tf.chmod(0o644)
        with self.assertRaisesRegex(ProviderError, "chmod 600"): orch.HttpProvider(ok)
        tf.chmod(0o600); tf.write_text("a b")
        with self.assertRaisesRegex(ProviderError, "no usable token"): orch.HttpProvider(ok)
        with self.assertRaisesRegex(ProviderError, "no usable token"): orch.HttpProvider({"url": ok["url"], "token_env": "NOPE_NOT_SET"})
        os.environ["DEVRAID_TEST_TOKEN"] = "z"; self.addCleanup(os.environ.pop, "DEVRAID_TEST_TOKEN")
        orch.HttpProvider({"url": ok["url"], "token_env": "DEVRAID_TEST_TOKEN"})

    def test_get_provider_selection(self):
        self.assertIsInstance(orch.get_provider({}), orch.ClaudeCodeProvider)
        self.assertIsInstance(orch.get_provider({"provider": "claude-code"}), orch.ClaudeCodeProvider)
        with self.assertRaisesRegex(ProviderError, "unknown"): orch.get_provider({"provider": "nope"})

class ClaudeCodeTests(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp()); self.argv = d / "argv.log"
        exe = d / "claude"
        exe.write_text(textwrap.dedent(f'''\
            #!{sys.executable}
            import json, os, sys
            open({str(self.argv)!r}, "a").write(json.dumps(sys.argv[1:]) + "\\n")
            text = sys.stdin.read()
            if text == "fail": print(json.dumps({{"is_error": True, "result": "nope"}})); sys.exit(1)
            print(json.dumps({{"result": "re: " + text, "session_id": "s1"}}))
            '''))
        exe.chmod(0o755)
        old = os.environ["PATH"]; os.environ["PATH"] = f"{d}:{old}"; self.addCleanup(os.environ.__setitem__, "PATH", old)

    def test_conversation_continues_and_prompt_goes_through_stdin(self):
        p = orch.ClaudeCodeProvider()
        self.assertEqual(p.send("--dangerous-looking text"), "re: --dangerous-looking text")
        self.assertEqual(p.send("again"), "re: again")
        first, second = [json.loads(l) for l in self.argv.read_text().splitlines()]
        self.assertIn("--append-system-prompt", first); self.assertNotIn("--resume", first)
        self.assertEqual(second[second.index("--resume") + 1], "s1")
        self.assertEqual(first[first.index("--allowedTools") + 1], "mcp__raidpoint")      # only the raidpoint tools
        self.assertNotIn("--dangerous-looking text", first)                              # never on argv
        self.assertEqual([m["role"] for m in p.history()], ["user", "assistant"] * 2)

    def test_errors_surface(self):
        with self.assertRaisesRegex(ProviderError, "nope"): orch.ClaudeCodeProvider().send("fail")
        os.environ["PATH"] = "/nonexistent"
        with self.assertRaisesRegex(ProviderError, "not found"): orch.ClaudeCodeProvider().send("x")

if __name__ == "__main__":
    unittest.main()
