"""mg-deathrun bsp_to_course fit_cap: under the cap nothing changes; over it, buried boxes go first, then scenery far from every path."""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("DOTBSP_PATH", ROOT)
sys.path.insert(0, ROOT)
GAME_TOOLS = os.path.join(os.path.expanduser("~"), "godot", "mg-deathrun-maps", "tools")  # bsp_read lives in the game repo
if not os.path.isdir(GAME_TOOLS):
    raise unittest.SkipTest("mg-deathrun-maps checkout not found")
sys.path.insert(0, GAME_TOOLS)
spec_ = importlib.util.spec_from_file_location("bsp_to_course", os.path.join(ROOT, "adapters", "mg-deathrun-maps", "bsp_to_course.py"))
M = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(M)


def piece(x, z, s=1.0, y=0.0, kind="box"):
    return {"kind": kind, "at": [x, y, z], "size": [s, s, s], "visible": True}


def importer():
    imp = M.Importer.__new__(M.Importer)
    imp.notes = {"not portable": [], "flattened": [], "dropped": []}
    imp.g = lambda p: [float(p[0]), float(p[1]), float(p[2])]
    return imp


class FitCap(unittest.TestCase):
    def test_under_cap_untouched(self):
        ps = [piece(i * 2, 0) for i in range(10)]
        self.assertIs(importer().fit_cap(ps, {"route": []}), ps)

    def test_buried_box_goes(self):
        ps = [piece(0, 0, 10), piece(0, 0, 1), piece(30, 0, 1)]
        out = importer().fit_cap(ps, {"max_pieces": 2, "route": [{"at": [0, 0, 0]}, {"at": [30, 0, 0]}]})
        self.assertEqual(len(out), 2)

    def test_far_scenery_goes_and_triggers_stay(self):
        near = [piece(i * 3, 0) for i in range(10)]
        far = [piece(i * 3, 500) for i in range(10)]
        trig = [piece(900, 900, kind="kill")]
        imp = importer()
        out = imp.fit_cap(near + far + trig, {"max_pieces": 11, "route": [{"at": [0, 0, 0]}, {"at": [30, 0, 0]}]})
        self.assertEqual(len(out), 11)
        self.assertTrue(all(p["at"][2] == 0 or p["kind"] == "kill" for p in out))
        self.assertTrue(any("further than" in n for n in imp.notes["dropped"]))


if __name__ == "__main__":
    unittest.main()
