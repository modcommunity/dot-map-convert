"""snap_spawns: a start sunk in its floor slab is raised to the slab's top."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DOTBSP_PATH", ROOT)

from dotbsp import docboxes  # noqa: E402


class SnapSpawns(unittest.TestCase):
    def doc(self, y):
        return {"boxes": [{"at": [0, -0.15, 0], "size": [10, 0.3, 10]}],
                "spawns": {"props": [{"at": [1.0, y, 1.0]}, {"at": [50.0, y, 1.0]}]}}

    def test_sunk_start_is_raised(self):
        d = self.doc(-0.1)
        self.assertEqual(docboxes.snap_spawns(d), 1)
        self.assertAlmostEqual(d["spawns"]["props"][0]["at"][1], 0.01)
        self.assertEqual(d["spawns"]["props"][1]["at"][1], -0.1)  # no floor under it: left for the pad

    def test_standing_start_stays(self):
        d = self.doc(0.05)
        self.assertEqual(docboxes.snap_spawns(d), 0)

    def test_roof_above_is_not_the_floor(self):
        d = self.doc(-0.1)
        d["boxes"].append({"at": [0, 2.0, 0], "size": [10, 0.3, 10]})
        docboxes.snap_spawns(d)
        self.assertAlmostEqual(d["spawns"]["props"][0]["at"][1], 0.01)


if __name__ == "__main__":
    unittest.main()
