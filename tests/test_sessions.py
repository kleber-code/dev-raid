import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from raidpoint import core

S = "api\t3\t1\t1000\t1990\nold\t1\t0\t900\t100\nwork\t2\t0\t950\t1995\n"
P = ("api\tzsh\t/srv/api\t0\napi\tnvim\t/srv/api\t1\napi\tzsh\t/srv/api\t1\n"
     "old\tbash\t/tmp\t0\n"
     "work\tclaude\t/srv/w\t0\nwork\tclaude\t/srv/w\t1\nghost\tzsh\t/x\t0\n")

class T(unittest.TestCase):
    def test_states_and_counts(self):
        r = {d["name"]: d for d in core.parse_sessions(S, P, now=2000)}
        self.assertEqual(r["api"]["state"], "open")        # attached wins even if shells
        self.assertEqual(r["api"]["panes"], 3); self.assertEqual(r["api"]["busy"], ["nvim"])
        self.assertEqual(r["old"]["state"], "idle"); self.assertEqual(r["old"]["busy"], [])
        self.assertEqual(r["work"]["state"], "busy"); self.assertEqual(r["work"]["busy"], ["claude"])   # deduplicated
        self.assertEqual(r["old"]["age_s"], 1900); self.assertEqual(r["api"]["cwd"], "/srv/api")
        self.assertNotIn("ghost", r)                        # pane of an unknown session is ignored

    def test_sorted_and_garbage(self):
        self.assertEqual([d["name"] for d in core.parse_sessions(S, P, now=2000)], ["api", "old", "work"])
        self.assertEqual(core.parse_sessions("lixo\nx\ty\n", "", now=1), [])

    def test_ago(self):
        self.assertEqual([core.dur_short(x) for x in (3, 45, 600, 7300, 200000)], ["now", "45s", "10m", "2h", "2d"])

if __name__ == "__main__": unittest.main()
