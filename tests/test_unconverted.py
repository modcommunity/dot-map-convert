"""The unconverted-class check. Run: python3 -I tools/bsp/tests/test_unconverted.py"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                          # noqa: E402
from dotbsp import classes, reader, unconverted       # noqa: E402


def _bsp(*ents):
    base = [{"classname": "worldspawn"}] + list(ents)
    return reader.Bsp("t.bsp", data=synth.build(entities=base)).load()


class Unconverted(unittest.TestCase):
    def test_converted_classes_are_not_listed(self):
        b = _bsp({"classname": "logic_relay", "origin": "0 0 0"}, {"classname": "light", "origin": "0 0 0"},
                 {"classname": "trigger_multiple"}, {"classname": "game_score"}, {"classname": "env_shake"})
        self.assertEqual(unconverted.of_map(b), {})

    def test_data_with_no_component_and_unknown_classes_are_listed(self):
        b = _bsp({"classname": "multi_manager"}, {"classname": "multi_manager"}, {"classname": "phys_hinge"},
                 {"classname": "made_up_thing"})
        self.assertEqual(unconverted.of_map(b), {"multi_manager": 2, "phys_hinge": 1, "made_up_thing": 1})

    def test_the_ignore_list_splits_found_from_missing(self):
        listed, missing = unconverted.check({"phys_hinge": 1, "info_node_hint": 4, "multi_manager": 2, "made_up_thing": 1})
        self.assertEqual(sorted(listed), ["info_node_hint", "phys_hinge"])
        self.assertEqual(sorted(missing), ["made_up_thing", "multi_manager"])
        self.assertIn("UNCONVERTED, not on the ignore list: multi_manager 2, made_up_thing 1", unconverted.text({"multi_manager": 2, "made_up_thing": 1})[1])

    def test_the_shipped_ignore_list_has_no_stale_row_and_every_reason(self):
        self.assertEqual(unconverted.stale(), [])
        exact, prefixes = unconverted.load_ignore()
        self.assertTrue(all(exact.values()) and all(w for _p, w in prefixes))

    def test_a_row_without_a_reason_is_refused(self):
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as f:
            f.write("phys_hinge\n")
        try:
            with self.assertRaises(ValueError):
                unconverted.load_ignore(f.name)
        finally:
            os.unlink(f.name)

    def test_a_gameplay_class_stays_off_the_list(self):
        for c in ("multi_manager", "point_teleport", "trigger_look", "filter_activator_name", "game_text"):
            self.assertIsNone(unconverted.ignored(c, unconverted.load_ignore()), c)


if __name__ == "__main__":
    unittest.main()
