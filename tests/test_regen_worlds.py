"""tools/regen_worlds.sh finds a source BSP by the map id, hyphen or underscore. Run: python3 -P tests/test_regen_worlds.py"""

import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "tools", "regen_worlds.sh")
FAKE_BSP = """import os, sys
with open(os.path.join(os.path.dirname(sys.argv[0]), 'calls.log'), 'a') as f:
    f.write(' '.join(sys.argv[1:3]) + '\\n')
"""


class RegenWorldsSource(unittest.TestCase):
    def run_regen(self, sources, ids):
        d = tempfile.mkdtemp()
        repo, fake = os.path.join(d, "repo"), os.path.join(d, "fake")
        os.makedirs(os.path.join(repo, "sources"))
        os.makedirs(fake)
        with open(os.path.join(fake, "bsp.py"), "w") as f:
            f.write(FAKE_BSP)
        for name in sources:
            open(os.path.join(repo, "sources", name), "w").close()
        env = dict(os.environ, DOTBSP_PATH=fake, HEAVY="", TMPDIR=d)
        p = subprocess.run(["bash", SCRIPT, repo] + ids, env=env, capture_output=True, text=True)
        calls = os.path.join(fake, "calls.log")
        log = open(calls).read() if os.path.exists(calls) else ""
        return p, log

    def test_underscore_bsp_matches_hyphen_id(self):
        p, log = self.run_regen(["cp_orange_x3.bsp"], ["cp-orange-x3"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("NO SOURCE", p.stdout)
        self.assertIn("cp-orange-x3 exit 0", p.stdout)
        self.assertIn("regen arena/cp_orange_x3", log)

    def test_hyphen_bsp_still_matches(self):
        p, _ = self.run_regen(["gg-woods.bsp"], ["gg-woods"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("gg-woods exit 0", p.stdout)

    def test_missing_source_is_reported(self):
        p, _ = self.run_regen(["other.bsp"], ["cp-orange-x3"])
        self.assertEqual(p.returncode, 1)
        self.assertIn("cp-orange-x3 NO SOURCE", p.stdout)


if __name__ == "__main__":
    unittest.main()
