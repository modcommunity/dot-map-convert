"""The model library mapper: size matching, picking by name words, shipping a pick.
Run: python3 -I tools/bsp/tests/test_modelmap.py
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import modelmap  # noqa: E402


def rec(ident, dims, source="Poly Haven"):
    return {"id": ident, "source": source, "url": "https://x/" + ident, "author": "A", "licence": "CC0-1.0",
            "dims": dims, "file": ident + "/" + ident + ".glb", "own": False}


class ModelMap(unittest.TestCase):
    def test_distance_exact_and_turned(self):
        d, s, t = modelmap.distance((0.6, 1.0, 0.4), (0.4, 1.0, 0.6))
        self.assertEqual(t, 0)
        self.assertAlmostEqual(s, 1.0, places=3)
        d1, s1, t1 = modelmap.distance((0.4, 1.0, 0.6), (0.4, 1.0, 0.6))
        self.assertEqual(t1, 1)
        self.assertLess(d, 0.01)

    def test_distance_prefers_closer_scale(self):
        near = modelmap.distance((1, 1, 1), (1.1, 1.1, 1.1))[0]
        far = modelmap.distance((1, 1, 1), (4, 4, 4))[0]
        self.assertLess(near, far)

    def test_pick_by_name_word(self):
        cat = {"lib": [modelmap.re.compile(r"(?<![a-z0-9])(?:chair)(?![a-z0-9])")]}
        lib = [rec("ph_chair_01", (0.5, 0.9, 0.5)), rec("ph_table_01", (0.5, 0.9, 0.5))]
        got = modelmap.pick("models/props/chair.mdl", (0.5, 0.9, 0.5), cat, lib)
        self.assertEqual(got[0]["id"], "ph_chair_01")
        self.assertIsNone(modelmap.pick("x", (0.5, 0.9, 0.5), {"lib": [modelmap.re.compile("sofa")]}, lib))

    def test_thin_target_ignores_thickness(self):
        d, _s, turns = modelmap.distance((0.91, 2.06, 0.04), (0.9, 2.0, 0.12))
        self.assertEqual(turns, 1)
        self.assertLess(d, 0.2)

    def test_category_ignores_extension_and_folder(self):
        cats = modelmap.categories()
        self.assertIsNotNone(modelmap.category_of("props/x/kk_barrel.mdl", cats))
        self.assertIsNone(modelmap.category_of("props/de_inferno/zzzz.mdl", cats))

    def test_generic_shape_pick_skips_weapons(self):
        lib = [rec("ph_stick_grenade", (0.08, 0.33, 0.08)), rec("ph_candle_holder", (0.08, 0.33, 0.08))]
        got = modelmap.pick("m", (0.08, 0.33, 0.08), modelmap.GENERIC, lib)
        self.assertEqual(got[0]["id"], "ph_candle_holder")

    def test_own_model_and_ship(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as store:
            r = modelmap.own_model(root, "box", (0.5, 0.2, 0.3), "e8e8e0")
            self.assertTrue(os.path.isfile(os.path.join(root, r["file"])))
            self.assertEqual(r["licence"], "CC0-1.0")
            self.assertEqual(modelmap.ship(r, store, root), r["file"])
            self.assertTrue(os.path.isfile(os.path.join(store, r["file"])))


if __name__ == "__main__":
    unittest.main()
