"""Which tool-only brushes and brush entities a box document keeps. Run: python3 -P tests/test_solid_tools.py"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                   # noqa: E402
from dotbsp import docboxes, reader            # noqa: E402

PLAYERCLIP, SOLID, NPCCLIP = 0x10000, 0x1, 0x20000


def load(contents, material, **kw):
    kw.setdefault("boxes", ((0, 0, 0, 64, 64, 64),))
    return reader.Bsp("synth.bsp", data=synth.build(materials=(material,), contents=contents, **kw)).load()


class ToolSolids(unittest.TestCase):
    def stops(self, contents, material):
        bsp = load(contents, material)
        return docboxes.stops_player(bsp, 0, docboxes.brush_material_names(bsp, 0))

    def test_clip_nodraw_and_sky_stop_a_player(self):
        self.assertTrue(self.stops(PLAYERCLIP, "TOOLS/TOOLSPLAYERCLIP"))
        self.assertTrue(self.stops(PLAYERCLIP | NPCCLIP, "TOOLS/TOOLSCLIP"))
        self.assertTrue(self.stops(SOLID, "TOOLS/TOOLSNODRAW"))          # nodraw is a render flag
        self.assertTrue(self.stops(SOLID, "TOOLS/TOOLSINVISIBLE"))
        self.assertTrue(self.stops(SOLID, "TOOLS/TOOLSSKYBOX"))

    def test_what_a_player_walks_through_is_left_out(self):
        self.assertFalse(self.stops(NPCCLIP, "TOOLS/TOOLSNPCCLIP"))
        self.assertFalse(self.stops(0, "TOOLS/TOOLSTRIGGER"))
        self.assertFalse(self.stops(0x20, "TOOLS/TOOLSNODRAW"))          # water


class EntityBrushes(unittest.TestCase):
    def world(self, cls, keys=None):
        return load(SOLID, "CONCRETE/WALL", entity_box=(0, 0, 0, 16, 16, 16), entity_origin=(100, 200, 0),
                    entity_class=cls, entity_keys=keys)

    def test_world_class_entity_is_carried_with_its_origin(self):
        got = docboxes.world_brushes(self.world("func_wall"))
        self.assertEqual(got, [(0, (0.0, 0.0, 0.0)), (1, (100.0, 200.0, 0.0))])

    def test_movers_and_hidden_entities_are_not(self):
        self.assertEqual(len(docboxes.world_brushes(self.world("func_door"))), 1)
        self.assertEqual(len(docboxes.world_brushes(self.world("func_illusionary"))), 1)
        self.assertEqual(len(docboxes.world_brushes(self.world("func_brush", {"StartDisabled": "1"}))), 1)
        self.assertEqual(len(docboxes.world_brushes(self.world("func_brush", {"Solidity": "1"}))), 1)
        self.assertEqual(len(docboxes.world_brushes(self.world("func_breakable"))), 2)

    def test_never_solid_is_solidity_1_only(self):
        self.assertTrue(docboxes.entity_never_solid({"classname": "func_brush", "Solidity": "1"}))
        self.assertFalse(docboxes.entity_never_solid({"classname": "func_brush", "Solidity": "2"}))
        # An output may enable a StartDisabled brush (a walkway that appears), so it is hidden but not never solid.
        self.assertFalse(docboxes.entity_never_solid({"classname": "func_brush", "StartDisabled": "1"}))
        self.assertFalse(docboxes.entity_never_solid({"classname": "func_wall", "Solidity": "1"}))
        self.assertTrue(docboxes.entity_starts_hidden({"classname": "func_brush", "Solidity": "1"}))


if __name__ == "__main__":
    unittest.main()
