"""exposure.add_wall_clusters: flush to a tall wall, never in a doorway, never closing a narrow lane."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DOTBSP_PATH", ROOT)

from dotbsp import exposure  # noqa: E402

SIZES = {"box_s": {"size": [0.5, 0.5, 0.5]}}


def room(door=False):
    """A 12 x 12 m floor with a 3 m wall along z = 0 (from x = -6 to 6), a door gap at x 2 to 3 when asked."""
    boxes = [{"at": [0, -0.15, 0], "size": [24, 0.3, 24], "mat": "floor"}]
    if door:
        boxes += [{"at": [-2.0, 1.5, 0], "size": [8.0, 3.0, 0.2], "mat": "wall"}, {"at": [4.5, 1.5, 0], "size": [3.0, 3.0, 0.2], "mat": "wall"}]
    else:
        boxes += [{"at": [0, 1.5, 0], "size": [12.0, 3.0, 0.2], "mat": "wall"}]
    return {"boxes": boxes, "props": [{"id": "box_s", "at": [8.0, 0.0, 8.0], "yaw": 0.0}],
            "spawns": {"props": [{"at": [0, 0.05, 5]}], "hunters": []}}


class TestWallClusters(unittest.TestCase):
    def test_cluster_stands_against_the_wall(self):
        doc = room()
        n = exposure.add_wall_clusters(doc, SIZES, count=1, max_exposure=1.0, separation=1.0, log=None)
        self.assertEqual(n, 1)
        new = doc["props"][1:]
        self.assertEqual(len(new), 3)
        for q in new:
            self.assertAlmostEqual(abs(q["at"][2]), 0.1 + 0.03 + 0.25, delta=0.06)
            self.assertAlmostEqual(q["at"][1], 0.0, places=2)

    def test_nothing_beside_a_doorway(self):
        doc = room(door=True)
        exposure.add_wall_clusters(doc, SIZES, count=20, max_exposure=1.0, separation=0.5, log=None)
        for q in doc["props"][1:]:
            if abs(q["at"][2]) < 1.0:
                self.assertFalse(1.0 < q["at"][0] < 4.0, q)

    def test_exposure_limit_refuses_the_open(self):
        doc = room()
        self.assertEqual(exposure.add_wall_clusters(doc, SIZES, count=5, max_exposure=-1.0, log=None), 0)


if __name__ == "__main__":
    unittest.main()
