"""The opt-in box budget keeps doors, stairs and floors, runs after door handling, and --bounds reaches starts and terrain."""
import copy
import importlib
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("DOTBSP_PATH", ROOT)
sys.path.insert(0, ROOT)
from dotbsp import docboxes as D  # noqa: E402


def box(x0, x1, y0, y1, z0, z1, mat="plaster"):
    return {"at": [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2], "size": [x1 - x0, y1 - y0, z1 - z0], "mat": mat}


def quiet(fn, *a, **k):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


class Trim(unittest.TestCase):
    def test_stairs_survive_volume(self):
        st = [box(0, 0.914, 0.152 * i, 0.152 * (i + 1), 0.305 * i, 0.305 * (i + 1), "concrete") for i in range(6)]
        quiet(D.apply_budget, st, {"volume": 0.05})
        self.assertEqual(len(st), 6)

    def test_floor_panel_survives(self):
        p = [box(0, 1.2, 0, 0.03, 0, 1.2)]
        quiet(D.apply_budget, p, {"volume": 0.05, "thickness": 0.15})
        self.assertEqual(len(p), 1)

    def test_header_survives(self):
        h = [box(3, 4.4, 2.0, 2.12, 0, 0.12)]
        quiet(D.apply_budget, h, {"volume": 0.05, "thickness": 0.15})
        self.assertEqual(len(h), 1)

    def test_small_detail_goes(self):
        d = [box(0, 0.1, 0, 0.1, 0, 0.3), box(0, 0.4, 0, 0.02, 0, 0.1)]
        quiet(D.apply_budget, d, {"volume": 0.05, "thickness": 0.15})
        self.assertEqual(d, [])

    def test_no_flag_changes_nothing(self):
        d = [box(0, 0.1, 0, 0.1, 0, 0.3)]
        quiet(D.apply_budget, d, {})
        self.assertEqual(len(d), 1)


class DoorOrder(unittest.TestCase):
    def jambs(self):
        return [box(0, 3, 0, 2.4, 0, 0.2), box(3.9, 7, 0, 2.4, 0, 0.2), box(3, 3.9, 2.0, 2.4, 0, 0.12)]

    def test_widen_then_budget_keeps_header(self):
        w = self.jambs()
        self.assertEqual(D.widen_doors(w), 1)
        quiet(D.apply_budget, w, {"thickness": 0.15, "volume": 0.05})
        self.assertTrue(any(abs(b["size"][0] - 1.4) < 0.01 and b["at"][1] > 2 for b in w))

    def test_merge_after_widen(self):
        w = [box(0, 3, 0, 2.4, 0, 0.2), box(3.9, 7, 0, 2.4, 0, 0.2), box(0, 3, 2.4, 5, 0, 0.2), box(3, 7, 2.4, 5, 0, 0.2)]
        self.assertEqual(D.widen_doors(w), 1)
        quiet(D.apply_budget, w, {"merge": True})

    def test_adapters_run_budget_last(self):
        for name, mark in (("murder-mystery-maps", "hang_doorways(m, doc)\n"),
                           ("hide-n-seek-maps", "docboxes.widen_doors(doc[\"boxes\"], doors=doc[\"doors\"])")):
            with open(os.path.join(ROOT, "adapters", name, "import_bsp.py")) as fh:
                src = fh.read()
            self.assertEqual(src.count("docboxes.apply_budget(doc["), 1)
            at = src.index("docboxes.apply_budget(doc[")
            self.assertGreater(at, src.index(mark, src.index("docboxes.add_doors(")), name)

    def test_one_way_pins_doors_hang_doorways_made(self):
        with open(os.path.join(ROOT, "adapters", "murder-mystery-maps", "import_bsp.py")) as fh:
            src = fh.read()
        self.assertGreater(src.index("    pin_one_way(doc)"), src.index("        hang_doorways(m, doc)\n"))
        self.assertLess(src.index("    pin_one_way(doc)"), src.index("docboxes.apply_budget(doc["))
        fn = src[src.index("def pin_one_way"):src.index("def hang_doorways")]
        ns = {"ONE_WAY": [(2.0, 3.0)]}
        exec(fn, ns)
        doc = {"doors": [{"at": [2.0, 0.0, 3.0]}, {"at": [9.0, 0.0, 3.0]}]}
        self.assertEqual(ns["pin_one_way"](doc), 1)
        self.assertIs(doc["doors"][0]["away"], False)
        self.assertNotIn("away", doc["doors"][1])


class LendStarts(unittest.TestCase):
    def test_hunters_filled_from_props(self):
        s = {"props": [{"at": [i, 0, 0]} for i in range(4)], "hunters": []}
        self.assertEqual(D.lend_starts(s, "props", "hunters"), 3)
        self.assertEqual((len(s["props"]), len(s["hunters"])), (1, 3))

    def test_untouched_when_hunters_exist(self):
        s = {"props": [{"at": [0, 0, 0]}, {"at": [1, 0, 0]}], "hunters": [{"at": [2, 0, 0]}]}
        self.assertEqual(D.lend_starts(s, "props", "hunters"), 0)

    def test_keeps_one_prop_start(self):
        s = {"props": [{"at": [0, 0, 0]}], "hunters": []}
        self.assertEqual(D.lend_starts(s, "props", "hunters"), 0)


class Bounds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path[:0] = [os.path.join(ROOT, "adapters", "mg-prop-hunt-maps"),
                        os.path.join(os.path.dirname(ROOT), "mg-prop-hunt-maps", "tools"),
                        os.path.expanduser("~/godot/mg-prop-hunt-maps/tools")]
        try:
            cls.I = importlib.import_module("import_bsp")
            cls.I.start_entities
        except Exception:
            cls.I = None

    def setUp(self):
        if self.I is None:
            self.skipTest("mg-prop-hunt-maps is not checked out beside this repository")

    class Bsp:
        def __init__(self, ents, tris=()):
            self.entities, self.tris = ents, list(tris)

        def model_faces(self, i):
            return [(0,) * 6 + (0,)] if self.tris else []

        def displacement_tris(self, f):
            return self.tris

    def test_start_entities_honour_bounds_and_missing_origin(self):
        cls = self.I.START_CLASSES[0]
        bsp = self.Bsp([{"classname": cls, "origin": "0 0 0"}, {"classname": cls, "origin": "5000 0 0"}, {"classname": cls}])
        self.assertEqual(len(self.I.start_entities(bsp)), 2)
        self.assertEqual(len(self.I.start_entities(bsp, lambda p: p[0] < 100)), 1)

    def test_terrain_field_is_cut_by_bounds(self):
        tri = lambda x: [((x, 0, 0), (x + 100, 0, 0), (x, 100, 0))]
        bsp = self.Bsp([], tri(0) + tri(9000))
        inside = lambda p: p[0] < 1000
        near = self.I.terrain_boxes(bsp, inside=inside)
        allf = self.I.terrain_boxes(bsp)
        self.assertLess(max(b[0][1] for b in near), 1000)
        self.assertGreater(max(b[0][1] for b in allf), 9000)


if __name__ == "__main__":
    unittest.main()
