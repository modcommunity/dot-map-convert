"""The convert-time prop fit pass (standins.fit_prop) and the converted-world prop audit (dotbsp/propaudit.py).
Run: python3 -P tests/test_propaudit.py
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import propaudit, standins  # noqa: E402


def measure(x, y, z):
    return {"size": [x, y, z], "centre": [0.0, y / 2.0, 0.0]}


class FitPass(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith(("DOT_PROP_FIT", "DOT_PROP_MISFIT"))}
        standins.FIT_STATS.clear()

    def tearDown(self):
        for k in [k for k in os.environ if k.startswith(("DOT_PROP_FIT", "DOT_PROP_MISFIT"))]:
            del os.environ[k]
        os.environ.update(self._env)

    def fit(self, rec, m, sc=1.0):
        return standins.fit_prop(rec, m, (0.0, 0.0, 0.0), 0.0, sc, 0.01905, 0.0)

    def test_table_has_the_kit(self):
        self.assertEqual(standins.standin_dims("fence"), (1.0, 0.345, 0.07))
        self.assertIsNotNone(standins.standin_dims("factory/window"))

    def test_native_fence_is_rescaled_to_the_source(self):
        # exterior_fence002e: 9.77 m long; the kit fence is 1 m
        rec = self.fit({"stand_in": "fence", "model": "m.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0}, measure(9.77, 3.0, 0.2))
        self.assertAlmostEqual(rec["size"], 9.77)
        self.assertEqual(standins.FIT_STATS.get("rescaled"), 1)

    def test_a_fitting_prop_is_left_alone(self):
        rec = {"stand_in": "fence", "model": "m.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0, "size": 2.0}
        self.assertIs(self.fit(rec, measure(2.1, 0.8, 0.1)), rec)
        self.assertEqual(rec["size"], 2.0)

    def test_the_wrong_shape_becomes_a_labelled_block(self):
        # window1.mdl: 12.2 x 2.4 x 0.08 m drawn through factory/window (1 x 3 x 2) at its longest side
        rec = {"stand_in": "factory/window", "model": "window1.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0, "size": 12.19, "solid": 6}
        out = self.fit(rec, measure(12.2, 2.4, 0.08))
        self.assertEqual(out["misfit"], "factory/window")
        self.assertEqual(out["box"], [12.2, 2.4, 0.08])
        self.assertEqual(out["solid"], 6)
        self.assertEqual(out["model"], "window1.mdl")

    def test_a_large_open_misfit_keeps_its_stand_in_fitted_inside(self):
        # streetlight_traffic_rev.mdl: 5.8 x 7.7 x 1.3 m (pole and arm) through ceiling_light; a block of that is a slab
        native = standins.standin_dims("ceiling_light")
        rec = {"stand_in": "ceiling_light", "model": "streetlight.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0, "size": 7.7}
        out = self.fit(rec, measure(5.8, 7.7, 1.3))
        self.assertNotIn("box", out)
        self.assertEqual(out["misfit"], "ceiling_light")
        drawn = sorted(v * out["size"] / max(native) for v in native)
        for d, s in zip(drawn, sorted([5.8, 7.7, 1.3])):
            self.assertLessEqual(d, s + 0.01)
        self.assertEqual(standins.FIT_STATS.get("fitted_in"), 1)
        os.environ["DOT_PROP_MISFIT"] = "box"
        self.assertIn("box", self.fit(dict(rec, size=7.7), measure(5.8, 7.7, 1.3)))
        os.environ["DOT_PROP_MISFIT"] = "bogus"
        with self.assertRaises(ValueError):
            self.fit(dict(rec, size=7.7), measure(5.8, 7.7, 1.3))
        del os.environ["DOT_PROP_MISFIT"]

    def test_trees_keep_their_height_fit_unless_far_off(self):
        rec = {"stand_in": "tree", "model": "t.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0, "size": 9.0}
        self.assertEqual(self.fit(rec, measure(12.0, 9.0, 12.0))["size"], 9.0)
        rec = {"stand_in": "lib/tree_pine", "model": "sky_cluster.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0, "size": 23.5}
        standins._STANDIN_DIMS = dict(standins._STANDIN_DIMS or {}, **{"lib/tree_pine": (4.0, 12.0, 4.0)})
        self.assertAlmostEqual(self.fit(rec, measure(0.5, 0.83, 0.5))["size"], 0.83)

    def test_off_and_fail_policies(self):
        rec = {"stand_in": "fence", "model": "m.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0}
        os.environ["DOT_PROP_FIT"] = "off"
        self.assertNotIn("size", self.fit(dict(rec), measure(9.77, 3.0, 0.2)))
        os.environ["DOT_PROP_FIT"] = "fail"
        with self.assertRaises(ValueError):
            self.fit(dict(rec), measure(9.77, 3.0, 0.2))
        os.environ["DOT_PROP_FIT"] = "bogus"
        with self.assertRaises(ValueError):
            self.fit(dict(rec), measure(9.77, 3.0, 0.2))

    def test_thresholds_are_configurable(self):
        os.environ["DOT_PROP_FIT_HIGH"] = "20"
        rec = self.fit({"stand_in": "fence", "model": "m.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0}, measure(0.2, 0.069, 0.014))
        self.assertNotIn("size", rec)   # 5x off but under the raised bound

    def test_unmeasured_is_counted_not_guessed(self):
        rec = {"stand_in": "fence", "model": "stock.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0}
        self.assertIs(self.fit(rec, None), rec)
        self.assertEqual(standins.FIT_STATS.get("unmeasured"), 1)


class Audit(unittest.TestCase):
    def test_judge(self):
        ratio, flags, cause = propaudit.judge({"scale": 1.0}, (12.0, 3.0, 0.2), (1.0, 0.345, 0.07))
        self.assertIn("outlier", flags)
        self.assertEqual(cause, "native")
        ratio, flags, cause = propaudit.judge({"size": 12.19, "scale": 1.0}, (12.2, 2.4, 0.08), (4.06, 12.19, 8.13))
        self.assertEqual(flags, ["distorted"])
        self.assertEqual(cause, "standin")

    def test_world_audit_and_thresholds(self):
        doc = {"props": [
            {"stand_in": "fence", "model": "f.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0,
             "bounds": {"box": [12.0, 3.0, 0.2], "at": [0, 0, 0], "yaw": 0}},
            {"stand_in": "fence", "model": "g.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0, "size": 2.0,
             "bounds": {"box": [2.0, 0.7, 0.1], "at": [0, 0, 0], "yaw": 0}},
            {"box": [1, 1, 1], "model": "b.mdl", "at": [0, 0, 0], "yaw": 0, "scale": 1.0},
        ]}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "pgc_test.json")
            with open(p, "w") as f:
                json.dump(doc, f)
            r = propaudit.audit_world(p, propaudit.StandIns(lib_root=d, props=""), {})
        self.assertEqual(r["outliers"], 1)
        self.assertEqual(r["blobs"], 1)
        self.assertTrue(propaudit.failures([r], max_outliers=0, max_blobs=0) == [])
        self.assertEqual(len(propaudit.failures([r], max_outliers=0, max_blobs=0, max_offscale_share=0.4)), 1)


if __name__ == "__main__":
    unittest.main()
