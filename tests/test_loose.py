"""Loose physics props and the breakables that hold them. Run: python3 -I tools/bsp/tests/test_loose.py"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import loose  # noqa: E402

S = 0.01905


def barrel(x, y, z, flags="256", cls="prop_physics_multiplayer", model="models/props_borealis/bluebarrel001.mdl"):
    return {"classname": cls, "model": model, "origin": "%s %s %s" % (x, y, z), "spawnflags": flags}


def placed(x, y, z, model="models/props_borealis/bluebarrel001.mdl"):
    return {"model": model, "stand_in": "barrel", "at": [x * S, z * S, -y * S], "yaw": 0.0}


class Loose(unittest.TestCase):
    def test_a_free_barrel_is_loose_and_a_frozen_one_is_not(self):
        ents = [barrel(0, 0, 10), barrel(500, 0, 10, flags="264")]
        recs = [placed(0, 0, 10), placed(500, 0, 10)]
        self.assertEqual(loose.mark(recs, ents, S, 0.0), 1)
        self.assertEqual(recs[0]["loose"], "barrel")
        self.assertNotIn("loose", recs[1])

    def test_furniture_and_static_models_stay_put(self):
        sofa = barrel(0, 0, 0, model="models/props/sofa.mdl")
        recs = [placed(0, 0, 0, model="models/props/sofa.mdl")]
        self.assertEqual(loose.mark(recs, [sofa, {"classname": "prop_dynamic", "model": "models/x/barrel.mdl", "origin": "0 0 0"}], S, 0.0), 0)

    def test_two_barrels_claim_two_records(self):
        ents = [barrel(0, 0, 10), barrel(40, 0, 10)]
        recs = [placed(40, 0, 10), placed(0, 0, 10)]
        self.assertEqual(loose.mark(recs, ents, S, 0.0), 2)

    def test_a_support_holds_what_rests_on_its_top_only(self):
        recs = [placed(0, 0, 80), placed(0, 0, 400), placed(900, 0, 80)]
        for r in recs:
            r["loose"] = "barrel"
        b = [{"model": 5, "health": 100.0}, {"model": 6, "health": 1.0}]
        boxes = {5: ([-40, -40, 0], [40, 40, 70]), 6: ([800, -40, 0], [1000, 40, 4])}
        loose.hold(b, recs, boxes.get, S, 0.0)
        self.assertEqual(b[0]["holds"], [0])
        self.assertEqual(b[1]["holds"], [])
        self.assertEqual(len(b[0]["bounds"]), 6)
        self.assertAlmostEqual(b[0]["bounds"][4], 70 * S, places=3)


if __name__ == "__main__":
    unittest.main()
