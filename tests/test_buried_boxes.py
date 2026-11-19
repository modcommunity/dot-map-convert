"""A block whose whole top is under a floor slab resting on it is left out of the game's graph (import_bsp.buried_boxes).

The game's graph forgives a box only when its top is within 0.12 m of a floor and grows the rest by the clearance, so
the block under gm_valley's 15 cm start slab took every point off the slab and the import stopped with no ground
within 3 m of the survivor start. Run: python3 -P tests/test_buried_boxes.py"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, os.path.join(ROOT, "adapters", "zombie-zone-maps")]
os.environ.setdefault("DOTBSP_PATH", ROOT)
# ambient.py and nav_emulate.py live with the map repository: the sibling checkout, or $ZOMBIE_ZONE_MAPS_PATH.
ZZM = os.environ.get("ZOMBIE_ZONE_MAPS_PATH") or os.path.join(os.path.dirname(ROOT), "zombie-zone-maps")
sys.path.append(os.path.join(ZZM, "tools"))

try:
    import import_bsp as I  # noqa: E402
    import nav_emulate  # noqa: E402
except ImportError:
    I = None


def box(x, z, size, bottom, top, **kw):
    return dict({"at": [x, (bottom + top) / 2, z], "size": [size, top - bottom, size], "mat": "concrete"}, **kw)


@unittest.skipIf(I is None, "import_bsp or nav_emulate not importable")
class BuriedBoxes(unittest.TestCase):
    def setUp(self):
        self.floors = [[-5.0, -5.0, 5.0, 5.0, 0.02]]

    def points(self, boxes):
        return nav_emulate.Graph(boxes, [], {}, self.floors).pts

    def test_block_under_the_start_slab_gives_its_points_back(self):
        slab, block = box(0, 0, 9.75, -0.152, 0.0), box(0, 0, 9.75, -15.85, -0.152)
        self.assertEqual(self.points([slab, dict(block)]), [], "the block's clearance swallows the slab's points")
        boxes = [slab, block]
        self.assertEqual(I.buried_boxes(boxes, self.floors), 1)
        self.assertIs(block.get("nav"), False)
        self.assertNotIn("nav", slab)
        self.assertEqual(len(self.points(boxes)), 100)

    def test_block_wider_than_the_slab_stays(self):
        boxes = [box(0, 0, 4.0, -0.152, 0.0), box(0, 0, 9.75, -15.85, -0.152)]
        self.assertEqual(I.buried_boxes(boxes, self.floors), 0)

    def test_block_under_a_slab_that_is_no_floor_stays(self):
        boxes = [box(20, 20, 4.0, 1.0, 1.2), box(20, 20, 4.0, 0.0, 1.0)]
        self.assertEqual(I.buried_boxes(boxes, self.floors), 0)

    def test_block_with_a_gap_under_the_slab_stays(self):
        boxes = [box(0, 0, 9.75, -0.152, 0.0), box(0, 0, 9.75, -15.85, -0.4)]
        self.assertEqual(I.buried_boxes(boxes, self.floors), 0)

    def test_block_under_a_thick_slab_stays(self):
        boxes = [box(0, 0, 9.75, -1.0, 0.0), box(0, 0, 9.75, -15.85, -1.0)]
        self.assertEqual(I.buried_boxes(boxes, self.floors), 0)

    def test_wall_of_the_storey_under_a_ceiling_slab_stays(self):
        # a storey floor 3 m down beside the block: the block is that storey's wall, its clearance keeps points off it
        floors = self.floors + [[4.875, -5.0, 12.0, 5.0, -2.5]]
        boxes = [box(0, 0, 9.75, -0.152, 0.0), box(0, 0, 9.75, -2.6, -0.152)]
        self.assertEqual(I.buried_boxes(boxes, floors), 0)

    def test_storey_floor_at_the_block_corner_only_does_not_keep_it(self):
        # gm_valley 114,81: a 2.4 x 1 m tread 4.6 m down reaches 0.1 m past the block's corner, along no side of it
        floors = self.floors + [[-7.2, -5.9, -4.8, -4.9, -2.5]]
        boxes = [box(0, 0, 9.75, -0.152, 0.0), box(0, 0, 9.75, -2.6, -0.152)]
        self.assertEqual(I.buried_boxes(boxes, floors), 1)

    def test_block_under_a_slab_the_budget_dropped_gives_its_points_back(self):
        # max_boxes drops the thin slab (small by volume) and keeps the block: the slab remembered before it counts
        slab, block = box(0, 0, 9.75, -0.152, 0.0), box(0, 0, 9.75, -15.85, -0.152)
        boxes = [slab, block]
        self.assertEqual(I.remember_slabs(boxes), 1)
        boxes = [block]
        self.assertEqual(I.buried_boxes(boxes, self.floors), 1)
        self.assertIs(block.get("nav"), False)

    def test_remembered_slab_that_is_no_floor_keeps_the_block(self):
        slab, block = box(20, 20, 4.0, 1.0, 1.2), box(20, 20, 4.0, 0.0, 1.0)
        I.remember_slabs([slab, block])
        self.assertEqual(I.buried_boxes([block], self.floors), 0)


if __name__ == "__main__":
    unittest.main()
