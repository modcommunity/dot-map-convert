"""Brush teleport destinations and func_tracktrain paths in the g2gfast importer.
Run: python3 -P tests/test_train_movers.py   (needs numpy, like the importer)
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "adapters", "game-g2gfast"))
sys.path.insert(0, ROOT)

# bsp_import reads through game-airdrift's `bsp_read` shim, which lives in that game's repo.
os.environ.setdefault("DOTBSP_PATH", ROOT)
for READER in (os.environ.get("G2G_TOOLS", ""),
               os.path.join(os.path.dirname(ROOT), "game-g2gfast", "tools"),
               "/home/gamedev/godot/game-g2gfast/tools"):
    if READER and os.path.isfile(os.path.join(READER, "bsp_read.py")):
        sys.path.append(READER)
        break
try:
    import bsp_import  # noqa: E402
except ModuleNotFoundError as err:
    raise unittest.SkipTest("bsp_read or numpy not found (set G2G_TOOLS): %s" % err)


class FakeBsp:
    """Just what brush_box asks of a map: model bounds relative to the entity origin."""
    def __init__(self, entities, bounds):
        self.entities = entities
        self.models = [None] * (max(bounds, default=-1) + 1)
        self._bounds = bounds

    def model_bounds(self, index):
        return self._bounds[index]


def pt(origin, **kw):
    return dict({"classname": "path_track", "origin": origin}, **kw)


class BrushDestinations(unittest.TestCase):
    """surf_i_hate_campers aims its pits at `trigger_teleport` brushes (t_spawn, b_site)."""

    def test_a_brush_with_an_origin_is_a_destination(self):
        z = bsp_import.Zoner(types.SimpleNamespace(entities=[
            {"classname": "trigger_teleport", "model": "*1", "target": "T_Spawn"},
            {"classname": "trigger_teleport", "model": "*2", "targetname": "t_spawn",
             "origin": "2524 -3412 628"}]))
        self.assertEqual(z.destinations("t_spawn"), [([2524.0, -3412.0, 628.0], 0.0)])

    def test_a_point_entity_still_wins_over_a_brush(self):
        z = bsp_import.Zoner(types.SimpleNamespace(entities=[
            {"classname": "trigger_teleport", "model": "*2", "targetname": "a", "origin": "1 1 1"},
            {"classname": "info_target", "targetname": "a", "origin": "9 9 9"}]))
        self.assertEqual(z.destinations("a"), [([9.0, 9.0, 9.0], 0.0)])

    def test_the_destination_brush_is_dropped_as_a_pit(self):
        # Left in, it is a pit with no destination of its own, and every pit aimed at it
        # reads as a loop and falls back to the spawn.
        z = bsp_import.Zoner(types.SimpleNamespace(entities=[
            {"classname": "trigger_teleport", "model": "*1", "target": "t_spawn"},
            {"classname": "trigger_teleport", "model": "*2", "targetname": "t_spawn",
             "origin": "2524 -3412 628"}]))
        bsp_import.targetless_teleports(z)
        self.assertEqual([i for i, _ in z.entities("trigger_teleport")], [0])


class TrackTrains(unittest.TestCase):
    def crusher(self, **kw):
        e = {"classname": "func_tracktrain", "model": "*1", "origin": "546 11326 -1360",
             "target": "1_2", "targetname": "crusher_1", "speed": "300", "startspeed": "1000",
             "dmg": "200"}
        e.update(kw)
        return e

    def bsp(self, *extra, **kw):
        ents = [self.crusher(**kw), pt("512 11360 -1360", targetname="1_1", target="1_2", speed="300"),
                pt("512 10704 -1360", targetname="1_2", target="1_1", speed="1000", wait="2")]
        ents.extend(extra)
        return FakeBsp(ents, {1: ([-64.0, -32.0, -16.0], [64.0, 32.0, 16.0])})

    def test_no_trains_no_movers(self):
        self.assertEqual(bsp_import.train_movers(FakeBsp([{"classname": "worldspawn"}], {})), [])

    def test_route_hull_and_numbers(self):
        (m,) = bsp_import.train_movers(self.bsp())
        self.assertEqual([c["name"] for c in m["path"]], ["1_2", "1_1"])
        self.assertTrue(m["loop"])
        self.assertEqual(m["path"][0], {"name": "1_2", "origin": [512.0, 10704.0, -1360.0],
                                        "speed": 1000.0, "wait": 2.0})
        self.assertNotIn("wait", m["path"][1])
        self.assertEqual((m["min"], m["max"]), ([-64.0, -32.0, -16.0], [64.0, 32.0, 16.0]))
        self.assertEqual((m["speed"], m["start_speed"], m["damage"]), (300.0, 1000.0, 200.0))
        self.assertTrue(m["solid"])

    def test_not_solid_flag(self):
        (m,) = bsp_import.train_movers(self.bsp(spawnflags="8"))
        self.assertFalse(m["solid"])

    def test_missing_corner_is_an_empty_path_not_a_crash(self):
        (m,) = bsp_import.train_movers(self.bsp(target="nowhere"))
        self.assertEqual(m["path"], [])
        self.assertFalse(m["loop"])

    def test_a_chain_that_ends_is_not_a_loop(self):
        b = self.bsp()
        b.entities[1].pop("target")
        (m,) = bsp_import.train_movers(b)
        self.assertEqual(len(m["path"]), 2)
        self.assertFalse(m["loop"])


if __name__ == "__main__":
    unittest.main()
