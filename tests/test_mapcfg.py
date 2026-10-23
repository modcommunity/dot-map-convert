import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotbsp import mapcfg


class MapCfg(unittest.TestCase):
    def test_every_value_is_commented_and_nothing_else_is_emitted(self):
        text = mapcfg.suggest("surf_x", [
            {"classname": "point_servercommand", "command": "sv_airaccelerate 150; say hi"},
            {"classname": "point_clientcommand", "command": "bind x +use"}])
        live = [l for l in text.splitlines() if not l.startswith("#")]
        self.assertEqual(live, [])
        self.assertIn("# sv_airaccelerate: 150", text)
        self.assertIn("skipped, never run: not a setting: say hi", text)
        self.assertIn("point_clientcommand", text)

    def test_last_value_wins_and_none_means_no_file(self):
        text = mapcfg.suggest("m", [{"classname": "point_servercommand", "command": "sv_gravity 800"},
                                    {"classname": "point_servercommand", "command": "sv_gravity 600"}])
        self.assertIn("# sv_gravity: 600", text)
        self.assertNotIn("800", text)
        self.assertIsNone(mapcfg.suggest("m", []))

    def test_an_authors_file_is_not_overwritten(self):
        cmds = [{"classname": "point_servercommand", "command": "sv_gravity 800"}]
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(mapcfg.write_suggestion(d, "m", cmds))
            with open(os.path.join(d, "m.yml"), "a") as f:
                f.write("mine: 1\n")
            self.assertIsNone(mapcfg.write_suggestion(d, "m", cmds))
            with open(os.path.join(d, "m.yml")) as f:
                self.assertIn("mine: 1", f.read())


if __name__ == "__main__":
    unittest.main()
