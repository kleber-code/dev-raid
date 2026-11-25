"""The bridge: restricted catalog over a unix socket, default project per host, and the remote shim relaying it."""
import json, os, socket, subprocess, sys, tempfile, threading, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["RAIDPOINT_HOME"] = tempfile.mkdtemp(prefix="devraid-bridge-")
sys.path.insert(0, str(ROOT))
from raidpoint import bridge, core

class Bridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core.CM.mkdir(parents=True, exist_ok=True)
        core.write_json_atomic(core.HOME / "projects.json", {"vps": {"dir": "/root", "host": "vps-x"}}) if hasattr(core, "write_json_atomic") else None
        cls.srv = bridge.Server("vps-x")
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def shim(self, msgs, sock=None):
        p = Path(tempfile.mkdtemp()) / "shim.py"; p.write_text(bridge.SHIM)
        env = {**os.environ, "DEVRAID_BRIDGE_SOCK": sock or str(self.srv.path)}
        inp = "".join(json.dumps(m) + "\n" for m in msgs)
        r = subprocess.run([sys.executable, str(p)], input=inp, text=True, capture_output=True, env=env, timeout=20)
        return [json.loads(l) for l in r.stdout.splitlines()]

    def test_socket_is_private(self):
        self.assertEqual(oct(os.stat(self.srv.path).st_mode & 0o777), "0o600")

    def test_catalog_is_restricted(self):
        out = self.shim([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
        names = {t["name"] for t in out[0]["result"]["tools"]}
        self.assertEqual(names, set(bridge.BRIDGE_TOOLS))
        for forbidden in ("spawn_agent", "run_with_secrets", "open_repo", "list_repos"):
            self.assertNotIn(forbidden, names)

    def test_forbidden_tool_is_refused(self):
        out = self.shim([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "run_with_secrets", "arguments": {"command": "id", "secrets": []}}}])
        self.assertTrue(out[0]["result"]["isError"])

    def test_default_project_is_the_hosts(self):
        self.assertEqual(bridge.default_project("vps-x"), "vps")
        self.assertEqual(bridge.default_project("other"), "")

    def test_notification_gets_no_reply_and_offline_is_explained(self):
        dead = str(Path(tempfile.mkdtemp()) / "none.sock")
        out = self.shim([{"jsonrpc": "2.0", "method": "notifications/initialized"},
                         {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_agents"}}], sock=dead)
        self.assertEqual(len(out), 1)
        self.assertIn("offline", out[0]["result"]["content"][0]["text"])

    def test_host_name_is_validated(self):
        for bad in ("-oProxyCommand=x", "a b", "", "a;b"):
            with self.assertRaises(ValueError): bridge.check_host(bad)

if __name__ == "__main__":
    unittest.main()
