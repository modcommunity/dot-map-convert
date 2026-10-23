import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

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


class Automatic(unittest.TestCase):
    """store and regen write the starter file for every map that sends commands, without being asked."""

    def test_store_and_regen_emit_the_starter(self):
        import argparse
        import synth
        from dotbsp import regen, store
        ents = [{"classname": "worldspawn"}, {"classname": "info_player_start", "origin": "16 16 1"},
                {"classname": "trigger_once", "origin": "0 0 0", "OnTrigger": "cmd,Command,sv_airaccelerate 150,0,-1"},
                {"classname": "point_servercommand", "targetname": "cmd", "origin": "8 8 8"}]
        root = tempfile.mkdtemp()
        h, _ = store.put(root, "t", "surf_fix", synth.build(entities=ents, materials=("ZZQ/WALL",), faces=True),
                         {"author": "A", "page": "https://example.invalid/a"})
        with open(os.path.join(root, h, "mapcfg.yml")) as f:
            self.assertIn("# sv_airaccelerate: 150", f.read())
        out = os.path.join(tempfile.mkdtemp(), "m")
        args = argparse.Namespace(entry="t/surf_fix", out=out, root=root, addon_rules=None, game_rules=None,
                                  map_rules=None, ratchet=False, baseline=None, coverage=None, catalogue=None,
                                  name="surf_fix", scale="visual", y0=0.0)
        self.assertIn(regen.cmd(args), (0, 4))
        with open(os.path.join(os.path.dirname(out), "dot_map", "map", "surf_fix.yml")) as f:
            self.assertIn("# sv_airaccelerate: 150", f.read())


if __name__ == "__main__":
    unittest.main()
