"""The game-g2gfast importer gives a solid prop_dynamic drawn as a library staircase a walkable ramp (stair_hulls).
Run: python3 -P tests/test_stair_ramps.py
"""

import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "adapters", "game-g2gfast"))
sys.path.insert(0, ROOT)
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
    raise unittest.SkipTest("bsp_read not found (set G2G_TOOLS): %s" % err)

STAIRS = "models/props_trainyard/portable_stairs001.mdl"
WALL_TOP = 249.0   # cp_orange_x3: the sniper walls stand 249 u over the floor the stairs are on


class Bsp:
    def __init__(self, *entities):
        self.entities = list(entities)


def stairs(origin, yaw, **keys):
    return dict({"classname": "prop_dynamic", "model": STAIRS, "solid": "6", "origin": "%g %g %g" % origin,
                 "angles": "0 %g 0" % yaw}, **keys)


class StairRamps(unittest.TestCase):
    def ramp(self, origin, yaw):
        hulls = bsp_import.stair_hulls(Bsp(stairs(origin, yaw)))
        self.assertEqual(len(hulls), 1)
        return hulls[0]

    def check(self, hull, origin, wall_x):
        floor = origin[2]
        top = [p for p in hull if p[2] > floor + 1]
        low = [p for p in hull if p[2] <= floor + 1]
        self.assertAlmostEqual(min(p[2] for p in top), floor + WALL_TOP, delta=1.0)
        # The top ends flush with the wall face, so the climb steps straight onto the wall.
        near = min(top, key=lambda p: abs(p[0] - wall_x))
        self.assertLess(abs(near[0] - wall_x), 1.0)
        # Shallower than the steepest floor a player walks (45 degrees).
        crest = max(top, key=lambda p: abs(p[0] - wall_x))
        foot = max(low, key=lambda p: abs(p[0] - wall_x))
        run = abs(foot[0] - crest[0])
        self.assertLess(math.degrees(math.atan2(WALL_TOP, run)), 40.0)
        # As wide as the drawn stairs and centred on the prop.
        ys = [p[1] for p in hull]
        self.assertAlmostEqual((min(ys) + max(ys)) / 2.0, origin[1], delta=1.0)
        self.assertGreater(max(ys) - min(ys), 100.0)

    def test_both_cp_orange_x3_stairs_rise_to_their_wall(self):
        # The two prop_dynamics of cp_orange_x3 and the wall face each one stands 172 u from.
        self.check(self.ramp((482, 5316, -2053), 270), (482, 5316, -2053), 310.0)
        self.check(self.ramp((-1997, 1808, -2053), 90), (-1997, 1808, -2053), -1825.0)

    def test_ramp_is_under_the_drawn_stairs(self):
        # The ramp is where the game draws the model: the worlds/ placement (standins._shaped_placements, in metres)
        # put through dot-map's bottom-centre rooting (ramps.godot_points) gives the same corners as the Hammer hull.
        from dotbsp import ramps, standins
        pick = standins.picks()[STAIRS]
        for origin, yaw in (((482, 5316, -2053), 270), ((-1997, 1808, -2053), 90)):
            spots = [(STAIRS, origin, (0, yaw, 0), "1", 6)]
            rec = standins._shaped_placements(spots, {STAIRS: pick}, bsp_import.METRES_PER_UNIT, 0.0)[0]
            drawn = ramps.godot_points(rec, ramps.WALK_RAMPS[pick["stand_in"]])
            hull = self.ramp(origin, yaw)
            for (hx, hy, hz), (gx, gy, gz) in zip(hull, drawn):
                m = bsp_import.METRES_PER_UNIT
                self.assertAlmostEqual(hx * m, gx, delta=0.01)
                self.assertAlmostEqual(hz * m, gy, delta=0.01)
                self.assertAlmostEqual(-hy * m, gz, delta=0.01)

    def test_a_ramp_that_stops_short_of_its_wall_is_noted(self):
        origin = (482, 5316, -2053)
        hull = self.ramp(origin, 270)
        wall = ([252.0, 5050.0, -2073.0], [310.0, 5585.0, -1804.0])     # cp_orange_x3 brush 240, the wall it climbs
        notes = []
        self.assertEqual(bsp_import.stair_landings([hull], [wall], notes), [0.0])
        self.assertEqual(notes, [])
        moved = ([wall[0][0] - 170, wall[0][1], wall[0][2]], [wall[1][0] - 170, wall[1][1], wall[1][2]])
        gaps = bsp_import.stair_landings([hull], [moved], notes)
        self.assertGreater(gaps[0], 160)
        self.assertIn("short of its landing", notes[0])

    def test_modelmap_rerun_keeps_the_hand_set_stairs_row(self):
        # 724a483 reran modelmap and the row went (the model is in no ranking): the stairs lost their collision.
        from dotbsp import modelmap
        kept = modelmap.unranked_rows(os.path.join(modelmap.RULES, modelmap.PICKS), set())
        self.assertIn(STAIRS, [r[0] for r in kept])
        self.assertNotIn(STAIRS, [r[0] for r in modelmap.unranked_rows(os.path.join(modelmap.RULES, modelmap.PICKS), {STAIRS})])

    def test_not_solid_or_not_a_staircase_has_no_ramp(self):
        self.assertEqual(bsp_import.stair_hulls(Bsp(stairs((0, 0, 0), 0, solid="0"))), [])
        self.assertEqual(bsp_import.stair_hulls(Bsp(dict(stairs((0, 0, 0), 0), model="models/props_c17/chair02a.mdl"))), [])


if __name__ == "__main__":
    unittest.main()
