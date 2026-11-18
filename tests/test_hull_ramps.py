"""A ramp that is only a hull of the world pack (the budget cut its boxes) is a floor to the nav flood.

import_bsp.hull_surfaces puts the walkable top of each `world_collision` hull into the flood's surfaces, as
dterrain.add_surfaces does for terrain: a lower and an upper deck joined by a ramp of no boxes were two pieces,
and the prune cut the links the importer drew through the slab beside the ramp (gm_mallparking's garage levels).
Run: python3 -P tests/test_hull_ramps.py"""
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, os.path.join(ROOT, "adapters", "zombie-zone-maps")]
os.environ.setdefault("DOTBSP_PATH", ROOT)

try:
    import import_bsp as I  # noqa: E402
except ImportError:
    I = None


def deck(x0, x1, top):
    return {"at": [(x0 + x1) / 2, top - 0.1, 0.0], "size": [x1 - x0, 0.2, 4.0], "mat": "concrete"}


def ramp_hull(x0, x1, y0, y1):
    """A wedge rising from y0 at x0 to y1 at x1, 4 m wide, a metre thick; planes n.p <= d like the pack's hulls."""
    run, rise = x1 - x0, y1 - y0
    n = math.hypot(rise, run)
    top = (-rise / n, run / n, 0.0)
    planes = [(0, 0, 0, 0), (0, -1, 0, -(y0 - 1.0)), (-1, 0, 0, -x0), (1, 0, 0, x1), (0, 0, -1, 2.0), (0, 0, 1, 2.0)]
    # the top plane n.p <= d: -rise*x + run*y <= -rise*x0 + run*y0, divided by n
    planes[0] = (top[0], top[1], 0.0, (-rise * x0 + run * y0) / n)
    return {"points": [[x0, y0, -2], [x1, y1, 2], [x0, y0 - 1, 2], [x1, y1 - 1, -2]], "planes": planes, "model": 0, "kind": "solid"}


@unittest.skipIf(I is None, "import_bsp not importable")
class HullRamp(unittest.TestCase):
    def setUp(self):
        self.boxes = [deck(-10, 0, 0.0), deck(10, 20, 2.0)]    # the ramp between them has no box
        self.start = [[-5.0, 0.1, 0.0]]
        self.hulls = [ramp_hull(0.0, 10.0, 0.0, 2.0)]

    def tearDown(self):
        I.NAV_HULLS = []

    def reach(self):
        _floors, _surf, seen, _p, _d = I.build_nav(self.boxes, self.start)
        return seen

    def test_ramp_only_hull_joins_the_decks(self):
        I.NAV_HULLS = []
        before = self.reach()
        self.assertFalse(any(c[0] >= 22 for c in before), "no ramp floor, no way up")
        I.NAV_HULLS = self.hulls
        after = self.reach()
        self.assertTrue(any(c[0] >= 22 and abs(c[2] - 2.0) < 0.05 for c in after), "the upper deck is reached over the ramp")
        heights = sorted({c[2] for c in after if 0 <= c[0] < 20})
        self.assertGreater(len(heights), 6, "floors climb the ramp")

    def test_wall_face_is_not_a_floor(self):
        wall = {"points": [[0, 0, -2], [1, 3, 2]], "planes": [(1, 0, 0, 1.0), (-1, 0, 0, 0.0), (0, 1, 0, 3.0), (0, -1, 0, 0.0), (0, 0, 1, 2.0), (0, 0, -1, 2.0)],
                "model": 0, "kind": "solid"}
        surf = {}
        n = I.hull_surfaces([wall], surf, lambda a, b: [])
        self.assertTrue(all(h == 3.0 for hs in surf.values() for h in hs))    # its top is, its sides are not
        self.assertEqual(n, len(surf))

    def test_hull_under_a_deck_has_no_floor(self):
        surf = {}
        I.hull_surfaces(self.hulls, surf, lambda a, b: [(1.5, 1.7)] if a == 2 else [])
        self.assertFalse(any(k[0] == 2 for k in surf))


if __name__ == "__main__":
    unittest.main()
