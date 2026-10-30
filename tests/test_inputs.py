"""Implemented inputs read from the GDScript. Run: python3 -I tools/bsp/tests/test_inputs.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from dotbsp import coverage, inputs, movers   # noqa: E402


class Bsp:
    def __init__(self, entities):
        self.entities = entities


class InputTests(unittest.TestCase):
    def test_components_come_from_the_registration_table(self):
        self.assertEqual(inputs.component_of("logic_relay"), "DotMapRelay")
        self.assertEqual(inputs.component_of("func_door"), "DotMapMoverNode")      # the loop-registered ones
        self.assertEqual(inputs.component_of("zz_nothing"), "DotMapEntity")

    def test_a_component_answers_its_cases_and_every_entity_answers_the_base_ones(self):
        relay = inputs.implemented("logic_relay")
        self.assertIn("trigger", relay)
        self.assertIn("kill", relay)
        self.assertNotIn("open", relay)
        self.assertIn("open", inputs.implemented("func_door"))
        self.assertIn("break", inputs.implemented("func_physbox"))      # inherited: DotMapPhysbox extends DotMapBreakable
        self.assertEqual(inputs.implemented("zz_nothing"), inputs.implemented("info_target"))

    def test_the_unimplemented_list_names_class_and_input(self):
        bsp = Bsp([
            {"classname": "logic_relay", "targetname": "r", "OnTrigger": "d,Open,,0,-1\nd,Frobnicate,,0,-1\n!activator,Whatever,,0,-1"},
            {"classname": "func_door", "targetname": "d"},
            {"classname": "info_target", "targetname": "t", "OnUser1": "r,Trigger,,0,-1\nr,Explode,,0,-1"},
        ])
        self.assertEqual(inputs.unimplemented(bsp, movers.links(bsp)), ["func_door.Frobnicate", "logic_relay.Explode"])
        self.assertIn("inputs_unimplemented", coverage.LISTS)


if __name__ == "__main__":
    unittest.main()
