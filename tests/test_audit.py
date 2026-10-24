"""dotbsp.audit's tests. Run: python3 -I tools/bsp/tests/test_audit.py"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                   # noqa: E402
from dotbsp import audit, boxes, mesh, reader, terrain, units  # noqa: E402

MATS = ("concrete/concretefloor001", "metal/metalwall001")


def load(**kw):
    kw.setdefault("materials", MATS)
    kw.setdefault("faces", True)
    return reader.Bsp("synth.bsp", data=synth.build(**kw)).load()


def box_of(b, scale=units.VISUAL):
    """A document box covering map box `b` (x0, y0, z0, x1, y1, z1), y0 = 0."""
    lo = audit.to_game(b[:3], scale)
    hi = audit.to_game(b[3:], scale)
    return {"at": [(lo[k] + hi[k]) / 2 for k in range(3)], "size": [abs(hi[k] - lo[k]) for k in range(3)], "yaw": 0}


class ContentsKind(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(audit.contents_kind(0x1, ["CONCRETE/FLOOR"]), "solid")
        self.assertEqual(audit.contents_kind(0x1 | 0x8000000, ["CONCRETE/FLOOR"]), "detail")
        self.assertEqual(audit.contents_kind(0x30000008), "ladder")
        self.assertEqual(audit.contents_kind(0x10000), "playerclip")
        self.assertEqual(audit.contents_kind(0x30000), "clip")
        self.assertEqual(audit.contents_kind(0x20000), "npcclip")
        self.assertEqual(audit.contents_kind(0x20), "water")
        self.assertEqual(audit.contents_kind(0x1, ["TOOLS/TOOLSINVISIBLE"]), "invisible")
        self.assertEqual(audit.contents_kind(0x1, ["TOOLS/TOOLSSKYBOX"]), "sky")
        self.assertIn("ladder", audit.COLLIDES)
        self.assertNotIn("water", audit.COLLIDES)


class ThinBoard(unittest.TestCase):
    def test_leaning_plank_is_kept(self):
        """A board one unit thick leaning at 45 degrees is slab-cut, and every slab is grown, not dropped."""
        r = 0.5 ** 0.5
        u, n = (r, 0.0, r), (-r, 0.0, r)            # along the board, and across it in x-z
        pts = [tuple(a * u[k] * 80 + b * n[k] * 6 + (c if k == 1 else 0) for k in range(3))
               for a in (0, 1) for b in (0, 1) for c in (0, 1)]
        planes = [(0.0, 1.0, 0.0, 1.0), (0.0, -1.0, 0.0, 0.0), u + (80.0,), (-u[0], 0.0, -u[2], 0.0),
                  n + (6.0,), (-n[0], 0.0, -n[2], 0.0)]
        out = boxes.decompose(planes, pts, slab=4.0, min_size=2.1)
        self.assertTrue(out)
        self.assertTrue(all(boxes.size(b)[1] >= 2.1 - 1e-6 for b in out))


class Audit(unittest.TestCase):
    BOXES = ((0, 0, 0, 256, 256, 16), (0, 0, 16, 64, 64, 48))

    def test_empty_output_loses_everything(self):
        bsp = load(boxes=self.BOXES)
        r = audit.audit(bsp, audit.Boxes([]))
        self.assertEqual(r["brushes_expected"], 2)
        self.assertEqual(r["brushes_collided"], 0)
        self.assertGreater(r["floor_samples"], 0)
        self.assertEqual(r["floor_missed"], r["floor_samples"])

    def test_full_output_keeps_everything(self):
        bsp = load(boxes=self.BOXES)
        for out in (audit.Boxes([box_of(b) for b in self.BOXES]), audit.Hulls(mesh.build(bsp).hulls)):
            r = audit.audit(bsp, out)
            self.assertEqual(r["brushes_collided"], r["brushes_expected"])
            self.assertEqual(r["floor_missed"], 0)

    def test_dropped_brush_is_named(self):
        bsp = load(boxes=self.BOXES)
        r = audit.audit(bsp, audit.Boxes([box_of(self.BOXES[0])]))
        self.assertEqual(r["brushes_collided"], 1)
        self.assertEqual([lost[0] for lost in r["brushes_lost"]], [1])
        self.assertGreater(r["floor_missed"], 0)       # the step's top

    def test_region_leaves_out_a_crop(self):
        bsp = load(boxes=self.BOXES)
        out = audit.Boxes([box_of(self.BOXES[0])])
        g = audit.to_game((32, 32, 32))
        skip = ",".join("%g" % v for v in (g[0] - 1, g[1] - 1, g[2] - 1, g[0] + 1, g[1] + 1, g[2] + 1))
        r = audit.audit(bsp, out, keep=audit.region(skips=[skip]))
        self.assertEqual(r["brushes_collided"], r["brushes_expected"])
        self.assertIsNone(audit.region())

    def test_terrain_holds_what_it_buries(self):
        """A document's terrain field stands for the brushes under it and is ground for the tops at it."""
        bsp = load(boxes=self.BOXES[:1])
        lo, hi = audit.to_game(self.BOXES[0][:3]), audit.to_game(self.BOXES[0][3:])
        x0, z0 = min(lo[0], hi[0]) - 1, min(lo[2], hi[2]) - 1
        field = terrain.Heightfield(x0, z0, 1.0, 10, 10, [max(lo[1], hi[1]) + 0.01] * 100)
        r = audit.audit(bsp, audit.Boxes([], terrain=field))
        self.assertEqual(r["brushes_collided"], r["brushes_expected"])
        self.assertEqual(r["floor_missed"], 0)

    def test_non_solid_box_does_not_count(self):
        bsp = load(boxes=self.BOXES[:1])
        b = dict(box_of(self.BOXES[0]), solid=False)
        self.assertEqual(audit.audit(bsp, audit.Boxes([b]))["brushes_collided"], 0)

    def test_brush_entity_class(self):
        bsp = load(boxes=self.BOXES[:1], entity_box=(0, 0, 0, 32, 32, 32), entity_origin=(100, 100, 16),
                   entity_class="func_breakable")
        r = audit.audit(bsp, audit.Boxes([box_of(self.BOXES[0])]), classes_of=lambda c: c in ("worldspawn", "func_breakable"))
        self.assertEqual(r["brushes_expected"], 2)
        self.assertEqual(r["brushes_collided"], 1)
        r = audit.audit(bsp, audit.Boxes([box_of(self.BOXES[0])]), classes_of=lambda c: c == "worldspawn")
        self.assertEqual(r["brushes_expected"], 1)


if __name__ == "__main__":
    unittest.main()
