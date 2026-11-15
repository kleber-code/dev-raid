"""The MCP tool catalog is a public contract (other programs call these tools by name): lock it down.
Regenerate tests/golden_tools.json ONLY on purpose, and tell whoever depends on it first."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class Catalog(unittest.TestCase):
    def test_tools_list_matches_golden(self):
        env = {**os.environ, "RAIDPOINT_HOME": tempfile.mkdtemp(prefix="devraid-test-")}
        p = subprocess.Popen([sys.executable, str(ROOT / "bin" / "raidpoint"), "mcp"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
        def rpc(i, m):
            p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": m, "params": {}}) + "\n"); p.stdin.flush()
            return json.loads(p.stdout.readline())["result"]
        try:
            rpc(1, "initialize"); listing = rpc(2, "tools/list"); tools = listing["tools"]
        finally:
            p.stdin.close(); p.wait(10); p.stdout.close()
        golden = json.loads((ROOT / "tests" / "golden_tools.json").read_text())
        norm = lambda ts: sorted(ts, key=lambda t: t["name"])
        self.assertEqual(norm(tools), norm(golden))
        self.assertEqual(listing["_meta"]["devraid/catalogVersion"], "1")

if __name__ == "__main__":
    unittest.main()
