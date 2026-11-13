"""dotbsp.ramps: a solid staircase prop in a worlds/ regen collides as one ramp hull where the game draws it.
Run: python3 -P tests/test_ramps.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotbsp import ramps  # noqa: E402

STAIRS = "lib/kenney_furniture-kit_stairs"
# cp_orange_x3's first staircase as the regen places it (metres, Godot axes), and the wall it climbs (brush 240).
REC = {"at": [9.1338, -39.1097, -101.2698], "stand_in": STAIRS, "size": 6.457, "scale": 1.0, "yaw": 450.0, "solid": 6}
M = 0.01905
WALL = ([252 * M, -2073 * M, -5585 * M], [310 * M, -1804 * M, -5050 * M])


class Ramps(unittest.TestCase):
    def test_hull_replaces_the_tread_boxes(self):
        rec, hulls = dict(REC), []
        done = ramps.add_ramp_hulls([rec, {"stand_in": STAIRS, "at": [0, 0, 0], "yaw": 0, "size": 6}], hulls)
        self.assertEqual(len(done), 1)       # the second is not solid: drawn, no ramp
        self.assertEqual(len(hulls), 1)
        self.assertNotIn("solid", rec)       # the game boxes no treads for it
        self.assertTrue(rec["ramp"])
        h = hulls[0]
        self.assertEqual((h["kind"], h["model"], len(h["points"]), len(h["planes"])), ("solid", 0, 8, 6))
        for p in h["points"]:
            for nx, ny, nz, d in h["planes"]:
                self.assertLessEqual(nx * p[0] + ny * p[1] + nz * p[2], d + 1e-6)
        # bottom on the floor, top 249 u up, flush with the wall face (x = 310 u)
        ys = [p[1] for p in h["points"]]
        self.assertAlmostEqual(min(ys), REC["at"][1], places=4)
        self.assertAlmostEqual(max(ys) - min(ys), 249 * M, delta=0.02)
        self.assertAlmostEqual(min(p[0] for p in h["points"]), 310 * M, delta=0.02)

    def test_landing_gap(self):
        pts = ramps.godot_points(REC, ramps.WALK_RAMPS[STAIRS])
        self.assertEqual(ramps.landing_gap(pts, [WALL]), 0.0)
        far = ([WALL[0][0] - 3.0, WALL[0][1], WALL[0][2]], [WALL[1][0] - 3.0, WALL[1][1], WALL[1][2]])
        self.assertAlmostEqual(ramps.landing_gap(pts, [far]), 3.0 - ramps.LANDING_REACH, delta=0.06)
        self.assertIsNone(ramps.landing_gap(pts, []))


if __name__ == "__main__":
    unittest.main()
