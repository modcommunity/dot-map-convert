"""--start-island: drop_other_terrain removes the ground islands no spawn stands on."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DOTBSP_PATH", ROOT)

from dotbsp import docboxes  # noqa: E402


def slab(x0, x1, z0, z1, top, mat="grass"):
    return {"at": [(x0 + x1) / 2, top - 0.25, (z0 + z1) / 2], "size": [x1 - x0, 0.5, z1 - z0], "mat": mat}


class TestDropOtherTerrain(unittest.TestCase):
    def test_unspawned_big_island_goes(self):
        doc = {"boxes": [slab(0, 20, 0, 20, 0.0), slab(30, 50, 0, 20, -5.0), slab(60, 62, 0, 2, 8.0)],
               "props": [], "spawns": {"props": [{"at": [10, 0.05, 10]}], "hunters": []}}
        gone = docboxes.drop_other_terrain(doc, min_cells=100, log=None)
        self.assertEqual(gone, 1)
        self.assertEqual(len(doc["boxes"]), 2)


if __name__ == "__main__":
    unittest.main()
