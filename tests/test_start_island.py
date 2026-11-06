"""--start-island: spawns move onto the largest connected floor, not an isolated platform."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DOTBSP_PATH", ROOT)

from dotbsp import docboxes  # noqa: E402


def slab(x0, x1, z0, z1, top=0.0, thick=0.5):
    return {"at": [(x0 + x1) / 2, top - thick / 2, (z0 + z1) / 2], "size": [x1 - x0, thick, z1 - z0]}


def wall(x0, x1, z0, z1, top=3.0):
    return {"at": [(x0 + x1) / 2, top / 2, (z0 + z1) / 2], "size": [x1 - x0, top, z1 - z0]}


def doc():
    # A 20 x 20 ground floor with a 4 x 4 platform 5 m up that nothing links to, and a wall splitting the ground
    # in a 1.4 m doorway.
    boxes = [slab(0, 20, 0, 20), slab(30, 34, 0, 4, top=5.0), wall(10, 10.2, 0, 9), wall(10, 10.2, 10.4, 20)]
    return {"boxes": boxes, "props": [],
            "spawns": {"props": [{"at": [32, 5.05, 2], "yaw": 0}], "hunters": [{"at": [5, 0.05, 5], "yaw": 0}]},
            "toys": [{"toy": "football", "at": [32, 5.0, 1]}]}


def size_of(pid):
    return (1, 1, 1)


def footprint(pid, yaw):
    return 1, 1


class StartIsland(unittest.TestCase):
    def test_islands_split_by_height_and_walls(self):
        islands, state_of, _g = docboxes.floor_islands(doc()["boxes"])
        self.assertGreaterEqual(len(islands), 2)
        self.assertEqual(state_of(5, 5, 0.0)[0], 0)
        self.assertNotEqual(state_of(32, 2, 5.0)[0], 0)
        self.assertIsNone(state_of(25, 10, 0.0))

    def test_doorway_joins_the_halves(self):
        islands, state_of, _g = docboxes.floor_islands(doc()["boxes"])
        self.assertEqual(state_of(2, 2, 0.0)[0], state_of(18, 18, 0.0)[0])

    def test_spawns_leave_the_platform(self):
        d = doc()
        moved = docboxes.restart_on_largest_island(d, size_of, footprint, log=lambda *_a: None)
        self.assertEqual(moved, 1)
        self.assertEqual(len(d["spawns"]["props"]), 8)
        self.assertEqual(len(d["spawns"]["hunters"]), 3)
        for side in d["spawns"].values():
            for sp in side:
                x, y, z = sp["at"]
                self.assertTrue(0 <= x <= 20 and 0 <= z <= 20, sp)
                self.assertAlmostEqual(y, 0.05, places=2)
        self.assertEqual(d["spawns"]["hunters"][0]["at"], [5, 0.05, 5])
        self.assertTrue(0 <= d["toys"][0]["at"][0] <= 20)

    def test_good_map_unchanged(self):
        d = doc()
        d["spawns"]["props"] = [{"at": [3, 0.05, 3], "yaw": 0}] * 8
        d["spawns"]["hunters"] = [{"at": [5, 0.05, 5], "yaw": 0}] * 3
        d["toys"] = [{"toy": "football", "at": [8, 0.0, 8]}]
        before = repr(d)
        self.assertEqual(docboxes.restart_on_largest_island(d, size_of, footprint, log=lambda *_a: None), 0)
        self.assertEqual(repr(d), before)


if __name__ == "__main__":
    unittest.main()
