"""The stand-in coverage report: tiers, ranking, stale picks, strict exit.
Run: python3 -I tools/bsp/tests/test_standinreport.py
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import standinreport  # noqa: E402


def world(path, models):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"licence": {"models": [{"model": m, "stand_in": s, "count": n} for m, s, n in models]}}, f)


class Report(unittest.TestCase):
    def test_tiers(self):
        t = standinreport.tier
        self.assertEqual(t("lib/ph_chair"), "free")
        self.assertEqual(t("lib/sf_lamp_ab12"), "free")
        self.assertEqual(t("lib/dm_wood_crate_cube"), "free")
        self.assertEqual(t("lib/kenney_food-kit_mug"), "kenney")
        self.assertEqual(t("lib/own_box_1x1x1_ffffff"), "generated")
        self.assertEqual(t("placeholder_box"), "placeholder")
        self.assertEqual(t("detail"), "placeholder")
        self.assertEqual(t("tree"), "kenney")

    def test_rank_and_stale(self):
        with tempfile.TemporaryDirectory() as d:
            world(os.path.join(d, "a.json"), [("m/a.mdl", "lib/kenney_x", 5), ("m/b.mdl", "lib/ph_b", 9)])
            world(os.path.join(d, "b.json"), [("m/a.mdl", "lib/kenney_x", 2)])
            with open(os.path.join(d, "none.json"), "w") as f:
                json.dump({"x": 1}, f)
            rep = standinreport.build(standinreport.manifests([d]), {"m/a.mdl": "ph_better", "m/b.mdl": "ph_b"})
        self.assertEqual(rep["worlds"], 2)
        self.assertEqual([e["model"] for e in rep["models"]], ["m/a.mdl", "m/b.mdl"])
        a = rep["models"][0]
        self.assertEqual((a["maps"], a["instances"], a["tier"], a["stale"]), (2, 7, "kenney", True))
        self.assertFalse(rep["models"][1]["stale"])
        self.assertEqual(rep["instances"]["free"], 9)

    def test_real_picks_parse(self):
        self.assertGreater(len(standinreport.picks()), 1000)


if __name__ == "__main__":
    unittest.main(verbosity=1)
