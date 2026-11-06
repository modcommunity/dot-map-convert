"""--drop-sky-slab, --keep-reach and --reach-hiders: the thinning steps of a big import, on small synthetic maps."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("DOTBSP_PATH", ROOT)
sys.path.insert(0, ROOT)
from dotbsp import docboxes as D  # noqa: E402


def box(x0, x1, y0, y1, z0, z1, **kw):
    b = {"at": [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2], "size": [x1 - x0, y1 - y0, z1 - z0], "mat": "plaster"}
    b.update(kw)
    return b


def quiet(fn, *a, **k):
    out = []
    return fn(*a, log=out.append, **k), out


def two_storeys():
    """A 10 x 10 ground floor and an upper floor at 3 m over z 4.6 to 10, joined by a stair of 16 thin treads
    (0.1875 m rise, 0.26 m deep, 0.9 m wide: a footprint under the trim's 0.25 m2 walkable test)."""
    bx = [box(0, 10, -0.5, 0, 0, 10), box(0, 10, 2.5, 3.0, 4.6, 10)]
    for i in range(16):
        bx.append(box(6, 6.9, 0.1875 * (i + 1) - 0.1, 0.1875 * (i + 1), 0.4 + 0.26 * i, 0.4 + 0.26 * (i + 1)))
    return bx


def doc_of(boxes, seekers=((1.0, 0.05, 1.0),), hiders=()):
    return {"boxes": boxes, "props": [], "lights": [], "doors": [],
            "spawns": {"seekers": [{"at": list(p)} for p in seekers], "hiders": [{"at": list(p)} for p in hiders]}}


class SkySlab(unittest.TestCase):
    def sky(self, **kw):
        s = box(-20, 30, 12, 12.5, -20, 30, visible=False)
        s.update(kw)
        return s

    def test_unseen_ceiling_goes_and_walls_stay(self):
        wall = box(-20, -19.5, 0, 12.5, -20, 30, visible=False)
        d = doc_of([box(0, 10, -0.5, 0, 0, 10), self.sky(), wall])
        self.assertEqual(D.drop_sky_slab(d), 1)
        self.assertEqual(len(d["boxes"]), 2)
        self.assertIn(wall, d["boxes"])

    def test_a_drawn_roof_stays(self):
        d = doc_of([box(0, 10, -0.5, 0, 0, 10), self.sky(visible=True)])
        self.assertEqual(D.drop_sky_slab(d), 0)

    def test_slab_that_something_stands_under_closely_stays(self):
        d = doc_of([box(0, 10, -0.5, 0, 0, 10), self.sky(at=[5, 1.5, 5])], seekers=((1.0, 0.05, 1.0),))
        self.assertEqual(D.drop_sky_slab(d), 0)

    def test_budget_flag_reaches_it_only_with_a_doc(self):
        o = {}
        self.assertTrue(D.budget_flag("--drop-sky-slab", o))
        d = doc_of([box(0, 10, -0.5, 0, 0, 10), self.sky()])
        D.apply_budget(d["boxes"], o)
        self.assertEqual(len(d["boxes"]), 2)
        D.apply_budget(d["boxes"], o, d)
        self.assertEqual(len(d["boxes"]), 1)


class KeepReach(unittest.TestCase):
    def test_flag(self):
        o = {}
        self.assertTrue(D.budget_flag("--keep-reach", o))
        self.assertEqual(o, {"keep_reach": True})

    def test_trim_alone_cuts_the_stair(self):
        d = doc_of(two_storeys())
        D.apply_budget(d["boxes"], {"volume": 0.5, "thickness": 0.0}, d)
        self.assertFalse(D._reach_keys(d["boxes"], (1.0, 0.05, 1.0)) & {(8, 7, 3)})

    def test_keep_reach_puts_the_steps_back(self):
        d = doc_of(two_storeys())
        want = D._reach_keys(d["boxes"], (1.0, 0.05, 1.0))
        self.assertIn((8, 7, 3), want)
        D.apply_budget(d["boxes"], {"volume": 0.5, "keep_reach": True}, d)
        self.assertEqual(D._reach_keys(d["boxes"], (1.0, 0.05, 1.0)), want)
        self.assertLess(len(d["boxes"]), len(two_storeys()) + 1)

    def test_trims_that_cost_no_route_stay_cut(self):
        clutter = box(2, 2.1, 1, 1.1, 8, 8.1)
        d = doc_of(two_storeys() + [clutter])
        D.apply_budget(d["boxes"], {"volume": 0.5, "keep_reach": True}, d)
        self.assertNotIn(clutter, d["boxes"])
        self.assertLess(len(d["boxes"]), len(two_storeys()))


class Hiders(unittest.TestCase):
    def test_unreachable_dropped_and_each_storey_filled(self):
        d = doc_of(two_storeys(), hiders=[(5.0, 0.05, 5.0), (9.0, 3.05, 9.0), (40.0, 0.05, 40.0)])
        res, out = quiet(D.place_hiders, d, per_level=3)
        self.assertEqual(len(d["spawns"]["hiders"]), 6)
        self.assertEqual(sorted(res), [0.0, 3.0])
        self.assertEqual(sorted(res.values()), [3, 3])
        self.assertTrue(all(h["at"][0] < 20 for h in d["spawns"]["hiders"]))
        reached = D.reach_report(d)
        self.assertEqual(reached[0], reached[1])

    def test_top_floor_unjoined_gets_no_hiders(self):
        bx = [b for b in two_storeys() if b["size"][1] > 0.3]
        d = doc_of(bx)
        res, _ = quiet(D.place_hiders, d, per_level=3)
        self.assertEqual(sorted(res), [0.0])

    def test_none_without_seekers(self):
        d = doc_of(two_storeys(), seekers=())
        self.assertEqual(quiet(D.place_hiders, d)[0], {})

    def test_hiders_keep_clear_of_seekers(self):
        d = doc_of(two_storeys())
        quiet(D.place_hiders, d, per_level=4)
        self.assertTrue(all((h["at"][0] - 1) ** 2 + (h["at"][2] - 1) ** 2 >= 16 for h in d["spawns"]["hiders"]))


class Adapter(unittest.TestCase):
    def test_hns_adapter_wires_all_three(self):
        with open(os.path.join(ROOT, "adapters", "hide-n-seek-maps", "import_bsp.py")) as fh:
            src = fh.read()
        self.assertIn('docboxes.apply_budget(doc["boxes"], box_budget, doc)', src)
        self.assertIn("docboxes.place_hiders(doc, per_level=reach_hiders)", src)
        self.assertIn('"--reach-hiders"', src)


if __name__ == "__main__":
    unittest.main()
