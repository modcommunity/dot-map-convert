"""The zombie-zone nav flood must walk a 12-inch stair flight even when a spec asks for flood_step 0.3."""
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


def box(x0, x1, y0, y1):
    return {"at": [(x0 + x1) / 2, (y0 + y1) / 2, 3.0], "size": [x1 - x0, y1 - y0, 6.0], "mat": "concrete"}


def stairs(rise):
    """A floor with a flight of six 0.6 m treads climbing to a landing."""
    boxes = [box(0, 14, -1, 0)]
    for i in range(6):
        boxes.append(box(4 + i * 0.6, 4.6 + i * 0.6, -1, rise * (i + 1)))
    top = rise * 6
    boxes.append(box(7.6, 14, -1, top))
    return boxes, top


@unittest.skipIf(I is None, "zombie-zone-maps is not checked out beside this repository")
class FloodStep(unittest.TestCase):
    def test_floor(self):
        self.assertEqual(I.flood_step(0.3), I.STAIR_RISE)
        self.assertEqual(I.flood_step(0.55), 0.55)

    def test_flight_reaches_landing(self):
        boxes, top = stairs(0.3048)
        saved = I.STEP, I.JUMP
        try:
            I.STEP = I.JUMP = I.flood_step(0.3)
            floors, *_ = I.build_nav(boxes, [[1.0, 0.0, 3.0]])
        finally:
            I.STEP, I.JUMP = saved
        self.assertTrue(any(abs(f[4] - top) < 0.05 and f[2] > 8 for f in floors), floors)


@unittest.skipIf(I is None, "zombie-zone-maps is not checked out beside this repository")
class FloorSnap(unittest.TestCase):
    """A floor must stay within the 0.12 m the game's graph forgives between a box's top and the floor over it."""

    def test_snapped_floor_keeps_its_slab(self):
        import nav_emulate
        # A 12-inch tread's top (-0.9144, a centimetre-rounded -0.91) beside a surface at -0.79: 0.12 apart rounded, 0.1244 really.
        boxes = [box(0, 4, -2, -0.9144), box(4, 8, -2, -0.79)]
        floors, *_ = I.build_nav(boxes, [[1.0, -0.9144, 3.0]])
        self.assertTrue(any(f[2] > 5 for f in floors), floors)
        for b in boxes:
            self.assertTrue(nav_emulate._is_floor(nav_emulate._bounds(b), floors), (b, floors))
        graph = nav_emulate.Graph(boxes, [], {}, floors)
        self.assertTrue(any(p[0] < 4 for p in graph.pts), "the lower slab blocked its own points")

    def test_close_heights_are_one_floor(self):
        boxes = [box(0, 4, -2, 0.0), box(4, 8, -2, 0.1)]
        floors, *_ = I.build_nav(boxes, [[1.0, 0.0, 3.0]])
        self.assertEqual({f[4] for f in floors}, {0.1})


@unittest.skipIf(I is None, "zombie-zone-maps is not checked out beside this repository")
class ExtraFloors(unittest.TestCase):
    """A spec's centre strip puts a graph point in a doorway the metre grid misses."""

    def test_strip_is_sampled_on_its_centre_line(self):
        import nav_emulate
        # A wall along z = 5 with a 1.1 m door at x 1.65..2.75: the grid's x = 2.5 is 0.25 m from the right jamb.
        wall = [{"at": [0.825, 1.0, 5.0], "size": [1.65, 2.0, 0.3], "mat": "concrete"},
                {"at": [5.375, 1.0, 5.0], "size": [5.25, 2.0, 0.3], "mat": "concrete"}]
        floors = [[0.0, 0.0, 8.0, 10.0, 0.0]]
        bare = nav_emulate.Graph(wall, [], {}, floors)
        self.assertFalse(any(abs(p[2] - 5.0) < 0.4 for p in bare.pts), "the grid already stands in the door")
        strip = I.extra_floors({"extra_floors": [[2.1, 3.6, 2.3, 6.6, 0.0]]})
        graph = nav_emulate.Graph(wall, [], {}, floors + strip)
        inside = [p for p in graph.pts if abs(p[0] - 2.2) < 1e-6]
        self.assertEqual(sorted(round(p[2], 2) for p in inside), [4.1, 5.1, 6.1])

    def test_bad_rectangle_is_refused(self):
        with self.assertRaises(ValueError):
            I.extra_floors({"extra_floors": [[2.3, 3.6, 2.1, 6.6, 0.0]]})

    def test_add_links_appends_once(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            spec, doc = os.path.join(tmp, "spec.json"), os.path.join(tmp, "doc.json")
            with open(spec, "w") as f:
                json.dump({"id": "t", "extra_floors": [[2.1, 3.6, 2.3, 6.6, 0]]}, f)
            with open(doc, "w") as f:
                json.dump({"id": "t", "boxes": [], "nav": {"floors": [[0.0, 0.0, 8.0, 10.0, 0.0]], "links": []}}, f)
            for _ in range(2):
                self.assertEqual(I.add_links(["import_bsp.py", "--add-links", spec, doc]), 0)
            with open(doc) as f:
                self.assertEqual(json.load(f)["nav"]["floors"], [[0.0, 0.0, 8.0, 10.0, 0.0], [2.1, 3.6, 2.3, 6.6, 0.0]])


if __name__ == "__main__":
    unittest.main()
