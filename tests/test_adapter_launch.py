"""A map or game repository's launcher finds its adapter under the repository's current name or a former one.
Run: python3 -P tests/test_adapter_launch.py
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "adapters"))

import adapter_launch  # noqa: E402


class AdapterLaunch(unittest.TestCase):
    def test_every_former_name_points_at_an_adapter_directory(self):
        for old, new in adapter_launch.FORMER.items():
            self.assertTrue(os.path.isdir(os.path.join(ROOT, "adapters", new)), "%s -> %s" % (old, new))
            self.assertFalse(os.path.exists(os.path.join(ROOT, "adapters", old)), "%s still has a directory of its own" % old)

    def test_a_launcher_under_the_old_name_runs_the_same_file_as_the_new(self):
        # legacy id: launchers in checkouts made before a rename still pass the old name.
        for old, new, name in (("game-g2gfast", "game-airdrift", "bsp_import.py"),
                               ("game-playground-maps", "playlot-maps", "import_bsp.py")):
            path = adapter_launch.adapter_path(new, name)
            self.assertTrue(os.path.isfile(path), path)
            self.assertEqual(adapter_launch.adapter_path(old, name), path)

    def test_run_executes_the_adapter_in_the_launchers_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "adapters", "game-airdrift"))
            with open(os.path.join(tmp, "adapters", "game-airdrift", "probe.py"), "w", encoding="utf-8") as f:
                f.write('"""Probe."""\nRAN = __file__\n')
            kept = adapter_launch.ROOT
            adapter_launch.ROOT = tmp
            try:
                for repo in ("game-airdrift", "game-g2gfast"):
                    g = {"__file__": "/launcher/tools/probe.py", "__name__": "__main__"}
                    adapter_launch.run(g, repo, "probe.py")
                    self.assertEqual(g["RAN"], "/launcher/tools/probe.py", repo)
                    self.assertEqual(g["__doc__"], "Probe.", repo)
            finally:
                adapter_launch.ROOT = kept


if __name__ == "__main__":
    unittest.main()
