"""cut_blocked holds a link to the game's prune body, not only to its rays: a join that grazes a door jamb is replaced by one through the door's middle."""
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

# 0.15 m from the jamb at z 4.3: the rays at 0.4 and 0.9 m pass the opening, a 0.32 m body does not.
GRAZE = [8.5, 0.0, 4.45, 12.1, 0.0, 4.45]


def doc():
    """Two rooms either side of a 0.6 m wall at x 10..10.6 with a 0.9 m door (z 4.3..5.2); the grid's z 4.75 row runs down its middle."""
    def wall(z0, z1):
        return {"at": [10.3, 1.2, (z0 + z1) / 2], "size": [0.6, 2.4, z1 - z0], "mat": "concrete"}
    return {"id": "t", "boxes": [wall(0.0, 4.3), wall(5.2, 10.0)], "props": [], "solid_props": [], "spawns": {},
            "nav": {"spacing": 1.0, "clearance": 0.35, "floors": [[0, 0.25, 10, 10, 0.0], [10.6, 0.25, 20, 10, 0.0]],
                    "links": [list(GRAZE)]}}


@unittest.skipIf(I is None, "zombie-zone-maps is not checked out beside this repository")
class BodyLinks(unittest.TestCase):
    def test_body_test(self):
        s = I.link_solids(doc())
        self.assertFalse(s.blocked(GRAZE[:3], GRAZE[3:]))
        self.assertTrue(s.body_blocked(GRAZE[:3], GRAZE[3:]))
        self.assertFalse(s.body_blocked([9.5, 0.0, 4.75], [11.1, 0.0, 4.75]))

    def test_tight_only_join_replaced(self):
        d = doc()
        n, _m, stuck = I.cut_blocked(d, None, [])
        self.assertEqual((n, stuck), (1, 0))
        self.assertEqual(d["nav"]["links"], [[9.5, 0.0, 4.75, 11.1, 0.0, 4.75]])
        self.assertEqual(I.cut_blocked(d, None, [])[:3], (0, 0, 0))

    def test_fixed_link_stays(self):
        d = doc()
        I.cut_blocked(d, None, [GRAZE])
        self.assertEqual(d["nav"]["links"], [GRAZE])


if __name__ == "__main__":
    unittest.main()
