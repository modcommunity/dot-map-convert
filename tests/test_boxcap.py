"""--max-boxes: cuts smallest first, keeps floors, stairs, door frames and the ground under anchors, reports reach, and does nothing unasked."""
import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("DOTBSP_PATH", ROOT)
sys.path.insert(0, ROOT)
from dotbsp import docboxes as D  # noqa: E402


def box(x0, x1, y0, y1, z0, z1, mat="plaster", **kw):
    b = {"at": [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2], "size": [x1 - x0, y1 - y0, z1 - z0], "mat": mat}
    b.update(kw)
    return b


def doc_of(boxes, **kw):
    d = {"boxes": boxes, "props": [], "lights": [], "doors": [], "spawns": {"players": [{"at": [1.0, 1.0, 1.0], "yaw": 0}]}}
    d.update(kw)
    return d


def quiet(fn, *a, **k):
    out = []
    r = fn(*a, log=out.append, **k)
    return r, out


def trim(n, at=5.0):
    """n small, separated bits of clutter high on a wall, far from everything."""
    return [box(at + i, at + i + 0.1, 1.0, 1.1, 30, 30.1) for i in range(n)]


class Flag(unittest.TestCase):
    def test_parsed(self):
        o = {}
        self.assertTrue(D.budget_flag("--max-boxes=5500", o))
        self.assertEqual(o, {"max": 5500})

    def test_cap_alone_is_not_the_trim(self):
        b = trim(3)
        D.apply_budget(b, {"max": 1})
        self.assertEqual(len(b), 3)

    def test_no_flag_changes_nothing(self):
        d = doc_of(trim(10) + [box(0, 4, -0.2, 0, 0, 4)])
        before = copy.deepcopy(d)
        D.apply_cap(d, {})
        D.apply_cap(d, {"merge": True})
        self.assertEqual(d, before)

    def test_under_limit_untouched(self):
        d = doc_of(trim(4))
        before = copy.deepcopy(d)
        r, _ = quiet(D.cap_boxes, d, 4)
        self.assertEqual((r, d), (0, before))


class Cut(unittest.TestCase):
    def test_smallest_go_first_and_report(self):
        bits = [box(5 + i, 5 + i + 0.1 * (i + 1), 1, 1.1, 30, 30.1) for i in range(5)]
        d = doc_of(bits + [box(0, 4, -0.2, 0, 0, 4)])
        r, out = quiet(D.cap_boxes, d, 3)
        self.assertEqual(r, 3)
        self.assertEqual(len(d["boxes"]), 3)
        sizes = sorted(round(b["size"][0], 2) for b in d["boxes"] if b["size"][0] < 1)
        self.assertEqual(sizes, [0.4, 0.5])
        self.assertTrue(any("largest cut" in m for m in out))

    def test_floor_survives_a_cap_of_zero(self):
        d = doc_of(trim(4) + [box(0, 4, -0.2, 0, 0, 4)])
        quiet(D.cap_boxes, d, 0)
        self.assertEqual(len(d["boxes"]), 1)
        self.assertEqual(d["boxes"][0]["size"][0], 4)

    def test_stairs_survive(self):
        st = [box(0, 0.914, 0, 0.152 * (i + 1), 0.305 * i, 0.305 * (i + 1), "concrete") for i in range(6)]
        d = doc_of(st + trim(5), spawns={"players": [{"at": [0.4, 1.0, 0.2], "yaw": 0}]})
        quiet(D.cap_boxes, d, 0)
        self.assertEqual(len(d["boxes"]), 6)

    def test_roofed_slab_is_not_a_floor(self):
        d = doc_of([box(0, 4, 0, 0.5, 0, 4), box(0, 4, 2.2, 2.5, 0, 4)], spawns={"players": []})
        keep = D.cap_protected(d)
        self.assertEqual(keep, {1})

    def test_door_frame_kept(self):
        jamb = box(2.9, 3.0, 0, 0.1, 0, 0.1)
        far = box(9, 9.1, 0, 0.1, 9, 9.1)
        d = doc_of([jamb, far], doors=[{"at": [2.5, 1.0, 0.05], "size": [1.0, 2.0, 0.06]}], spawns={"players": []})
        quiet(D.cap_boxes, d, 0)
        self.assertEqual(d["boxes"], [jamb])

    def test_ground_under_anchors_kept(self):
        step = box(0, 0.2, 0, 0.1, 0, 0.2)
        other = box(5, 5.2, 0, 0.1, 5, 5.2)
        under_light = box(7, 7.2, 0, 0.1, 7, 7.2)
        under_prop = box(9, 9.2, 0, 0.1, 9, 9.2)
        d = doc_of([step, other, under_light, under_prop], spawns={"players": [{"at": [0.1, 0.8, 0.1], "yaw": 0}]},
                   lights=[{"at": [7.1, 2.5, 7.1]}], props=[{"id": "p", "at": [9.1, 0.1, 9.1]}])
        quiet(D.cap_boxes, d, 0)
        self.assertEqual(d["boxes"], [step, under_light, under_prop])

    def test_reports_still_over(self):
        d = doc_of([box(0, 4, -0.2, 0, 0, 4), box(4, 8, -0.2, 0, 0, 4)])
        _, out = quiet(D.cap_boxes, d, 1)
        self.assertTrue(any("STILL OVER" in m for m in out))


class Reach(unittest.TestCase):
    def test_walled_room_connected_then_cut_off(self):
        floor = box(0, 10, -0.2, 0, 0, 10)
        wall = box(4.9, 5.1, 0, 3, 0, 10)
        d = doc_of([floor, wall], spawns={"players": [{"at": [1, 1, 5], "yaw": 0}, {"at": [9, 1, 5], "yaw": 0}]})
        self.assertEqual(D.reach_report(d)[:2], (1, 2))
        gap = [floor, box(4.9, 5.1, 0, 3, 0, 4.0), box(4.9, 5.1, 0, 3, 6.0, 10)]
        d["boxes"] = gap
        self.assertEqual(D.reach_report(d), (2, 2, []))

    def test_a_cut_floor_is_reported(self):
        a, b = box(0, 5, -0.2, 0, 0, 5), box(5, 10, -0.2, 0, 0, 5)
        d = doc_of([a, b], spawns={"players": [{"at": [1, 1, 1], "yaw": 0}, {"at": [9, 1, 1], "yaw": 0}]})
        self.assertEqual(D.reach_report(d)[:2], (2, 2))
        d["boxes"] = [a]
        self.assertEqual(D.reach_report(d)[2], [1])

    def test_stairs_join_floors(self):
        low = box(0, 3, -0.2, 0, 0, 3)
        steps = [box(3 + 0.3 * i, 3.3 + 0.3 * i, 0, 0.15 * (i + 1), 0, 3) for i in range(10)]
        high = box(6, 9, -0.2, 1.5, 0, 3)
        d = doc_of([low] + steps + [high], spawns={"players": [{"at": [1, 1, 1], "yaw": 0}, {"at": [8, 2.5, 1], "yaw": 0}]})
        self.assertEqual(D.reach_report(d)[:2], (2, 2))

    def test_cap_reports_lost_reach(self):
        a = box(0, 5, -0.2, 0, 0, 5)
        link = box(5, 6, -0.2, 0, 2, 2.2)
        b = box(6, 10, -0.2, 0, 0, 5)
        d = doc_of([a, link, b], spawns={"players": [{"at": [1, 1, 2.1], "yaw": 0}, {"at": [9, 1, 2.1], "yaw": 0}]})
        self.assertEqual(D.reach_report(d)[:2], (2, 2))
        _, out = quiet(D.cap_boxes, d, 2)
        self.assertEqual(len(d["boxes"]), 3)
        self.assertEqual(D.reach_report(d)[:2], (2, 2))
        self.assertTrue(any("restored 1 of 1" in m for m in out), out)
        self.assertTrue(any("STILL OVER by 1" in m for m in out), out)

    def test_restores_the_fewest_largest_first(self):
        a = box(0, 5, -0.2, 0, 0, 5)
        links = [box(5, 6, -0.2, 0, 2 + 0.01 * i, 2.2) for i in range(2)]
        b = box(6, 10, -0.2, 0, 0, 5)
        junk = trim(3)
        d = doc_of([a, b] + links + junk, spawns={"players": [{"at": [1, 1, 2.1], "yaw": 0}, {"at": [9, 1, 2.1], "yaw": 0}]})
        quiet(D.cap_boxes, d, 2)
        self.assertEqual(D.reach_report(d)[:2], (2, 2))
        self.assertEqual(len(d["boxes"]), 3)
        self.assertIn(links[0], d["boxes"])


class Gaps(unittest.TestCase):
    def test_slab_with_a_crate_is_still_a_floor(self):
        slab = box(0, 10, -0.2, 0, 0, 10)
        crate = box(4, 5, 0, 1, 4, 5)
        d = doc_of([slab, crate], spawns={"players": []})
        self.assertIn(0, D.cap_protected(d))

    def test_slab_replaced_by_a_bigger_one_is_not(self):
        d = doc_of([box(0, 4, 0, 0.3, 0, 4), box(0, 4, 0.2, 1.0, 0, 4)], spawns={"players": []})
        self.assertNotIn(0, D.cap_protected(d))

    def test_turned_floor_kept(self):
        f = box(0, 4, -0.2, 0, 0, 4, yaw=30.0)
        d = doc_of([f] + trim(3), spawns={"players": []})
        quiet(D.cap_boxes, d, 0)
        self.assertEqual(d["boxes"], [f])

    def test_shallow_treads_kept_in_a_chain_but_not_alone(self):
        treads = [box(0, 1.0, 0, 0.15 * (i + 1), 0.2 * i, 0.2 * (i + 1), "concrete") for i in range(5)]
        d = doc_of(treads + [box(30, 31, 0, 0.2, 30, 30.2)], spawns={"players": []})
        self.assertEqual(D.cap_protected(d), {0, 1, 2, 3, 4})

    def test_turned_stair_run_kept(self):
        treads = [box(0, 1.0, 0, 0.15 * (i + 1), 0.2 * i, 0.2 * (i + 1), "concrete", yaw=45.0) for i in range(5)]
        d = doc_of(treads, spawns={"players": []})
        self.assertEqual(D.cap_protected(d), {0, 1, 2, 3, 4})

    def test_door_in_a_z_wall_keeps_its_jambs(self):
        jamb = box(0, 0.2, 0, 2.2, 3.25, 3.45)
        far = box(0, 0.2, 0, 2.2, 0.0, 0.2)
        d = doc_of([jamb, far], doors=[{"at": [0.1, 1.0, 2.5], "size": [1.4, 2.0, 0.06], "yaw": 90.0}], spawns={"players": []})
        quiet(D.cap_boxes, d, 0)
        self.assertEqual(d["boxes"], [jamb])

    def test_kerb_keeps_the_ground_one_step_down(self):
        slab = box(-5, 5, -0.2, 0, -5, 5)
        kerb = box(-0.3, 0.3, 0, 0.2, -0.3, 0.3)
        tile = box(0.5, 1.0, -0.2, 0.0, -0.2, 0.2)
        d = doc_of([kerb, tile, slab] + trim(3), spawns={"players": [{"at": [0.0, 0.2, 0.0], "yaw": 0}]})
        keep = D.cap_protected(d)
        self.assertTrue({0, 1, 2} <= keep, keep)


class Adapters(unittest.TestCase):
    def test_three_adapters_take_the_flag_and_cap_last(self):
        for name in ("murder-mystery-maps", "mg-prop-hunt-maps", "hide-n-seek-maps"):
            with open(os.path.join(ROOT, "adapters", name, "import_bsp.py")) as f:
                src = f.read()
            self.assertIn("docboxes.budget_flag(a, box_budget)", src, name)
            self.assertIn("docboxes.apply_cap(doc, box_budget", src, name)
            self.assertLess(src.index("docboxes.apply_budget(doc"), src.index("docboxes.apply_cap(doc"), name)
            self.assertLess(src.index("docboxes.apply_cap(doc"), src.index('f.write(json.dumps(doc, indent=1)', src.index("docboxes.apply_cap(doc")), name)
            self.assertIn("--max-boxes=", src.split("import ")[0], name)


class Wire(unittest.TestCase):
    def noisy(self, n):
        import random
        r = random.Random(3)
        return [box(5 + 2 * i, 5 + 2 * i + r.uniform(0.05, 0.6), 1.0, 1.0 + r.uniform(0.05, 0.6), 30, 30 + r.uniform(0.05, 0.6)) for i in range(n)]

    def test_parsed(self):
        o = {}
        self.assertTrue(D.budget_flag("--max-wire=57000", o))
        self.assertEqual(o, {"wire": 57000})

    def test_fits_the_budget_and_keeps_the_floor(self):
        d = doc_of(self.noisy(800) + [box(0, 4, -0.2, 0, 0, 4)])
        budget = 5000
        D.fit_wire(d, budget, log=lambda m: None)
        self.assertLessEqual(D.wire_size(d), budget)
        self.assertIn(4.0, [b["size"][0] for b in d["boxes"]])
        self.assertLess(len(d["boxes"]), 801)

    def test_under_budget_only_rounds(self):
        d = doc_of([box(0, 4.0004, -0.2, 0, 0, 4)])
        D.fit_wire(d, 10 ** 6, log=lambda m: None)
        self.assertEqual(len(d["boxes"]), 1)
        self.assertEqual(d["boxes"][0]["size"][0], 4.0)

    def test_no_flag_no_change(self):
        d = doc_of(self.noisy(50))
        before = copy.deepcopy(d)
        D.apply_cap(d, {})
        self.assertEqual(d, before)


class DropUnsupportedProps(unittest.TestCase):
    def test_hanging_and_buried_props_go_standing_ones_stay(self):
        size_of = lambda pid: (0.4, 0.4, 0.4)
        footprint = lambda pid, yaw: (0.4, 0.4)
        floor = box(-5, 5, -0.2, 0.0, -5, 5)
        table = box(1, 2, 0.0, 0.7, 1, 2)
        d = doc_of([floor, table], props=[
            {"id": "on_floor", "at": [-3.0, 0.0, -3.0]},
            {"id": "on_table", "at": [1.5, 0.7, 1.5]},
            {"id": "on_prop", "at": [-3.0, 0.4, -3.0]},
            {"id": "hanging", "at": [3.0, 1.0, -3.0]},
            {"id": "buried", "at": [1.5, 0.3, 1.5]},
        ])
        n, out = quiet(D.drop_unsupported_props, d, size_of, footprint)
        self.assertEqual(n, 2)
        self.assertEqual(sorted(q["id"] for q in d["props"]), ["on_floor", "on_prop", "on_table"])

    def test_only_with_a_budget_flag(self):
        d = doc_of([box(-5, 5, -0.2, 0.0, -5, 5)], props=[{"id": "hanging", "at": [0.0, 2.0, 0.0]}])
        D.apply_cap(d, {}, size_of=lambda p: (1, 1, 1), footprint=lambda p, y: (1, 1))
        self.assertEqual(len(d["props"]), 1)


class TerrainReach(unittest.TestCase):
    def test_spawn_across_a_heightfield_is_reached(self):
        from dotbsp.terrain import Heightfield
        hf = Heightfield(10.0, 0.0, 2.0, 6, 4, [0.0] * 24)
        floor = box(-3, 3, -0.2, 0.0, -3, 3)
        d = doc_of([floor], spawns={"players": [{"at": [0.0, 0.0, 0.0], "yaw": 0}, {"at": [15.0, 0.0, 3.0], "yaw": 0}]})
        self.assertEqual(D.reach_report(d)[2], [1])
        d["boxes"].append(box(2.5, 10.5, -0.2, 0.0, -1, 1))
        d["terrain"] = hf.encode()
        self.assertEqual(D.reach_report(d)[2], [])


if __name__ == "__main__":
    unittest.main()
