"""drop_dead_links removes the nav links the game's builder cannot place, and only those."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, os.path.join(ROOT, "adapters", "zombie-zone-maps")]
os.environ.setdefault("DOTBSP_PATH", ROOT)

sys.path.append(os.path.join(os.path.dirname(ROOT), "zombie-zone-maps", "tools"))
try:
    import import_bsp as I  # noqa: E402
except ImportError:
    I = None
else:
    I.HERE = os.path.join(os.path.dirname(ROOT), "zombie-zone-maps", "tools")    # prop_sizes.json lives with the map repository

NOEND = [90.0, 0.0, 90.0, 1.5, 0.0, 1.5]
SAME = [2.5, 0.0, 2.5, 2.7, 0.0, 2.6]
GOOD = [2.5, 0.0, 6.5, 4.5, 0.0, 6.5]
ACROSS_WALL = [8.5, 0.0, 2.5, 11.5, 0.0, 2.5]
BRIDGE = [18.5, 0.0, 2.5, 26.5, 0.0, 2.5]


def doc():
    """Ground 0..20 split by a wall at x = 10 that leaves z 6..10 open, and an island 24..30 only BRIDGE reaches."""
    wall = {"at": [10.0, 1.0, 2.5], "size": [0.4, 2.0, 5.0], "mat": "concrete"}
    return {"boxes": [wall], "props": [], "solid_props": [],
            "nav": {"spacing": 1.0, "clearance": 0.35, "floors": [[0, 0, 20, 10, 0.0], [24, 0, 30, 10, 0.0]],
                    "links": [list(l) for l in (NOEND, SAME, GOOD, GOOD, ACROSS_WALL, BRIDGE)]}}


@unittest.skipIf(I is None, "zombie-zone-maps is not checked out beside this repository")
class DeadLinks(unittest.TestCase):
    def test_drops_only_dead(self):
        d = doc()
        self.assertEqual(I.drop_dead_links(d, None, []), 4)
        self.assertEqual(d["nav"]["links"], [GOOD, BRIDGE])

    def test_fixed_links_stay(self):
        d = doc()
        I.drop_dead_links(d, None, [NOEND, ACROSS_WALL])
        self.assertIn(NOEND, d["nav"]["links"])
        self.assertIn(ACROSS_WALL, d["nav"]["links"])

    def test_idempotent(self):
        d = doc()
        I.drop_dead_links(d, None, [])
        self.assertEqual(I.drop_dead_links(d, None, []), 0)


if __name__ == "__main__":
    unittest.main()
