"""Teleports resolve to where the map sends them: the audit, pit separation and finish teleports.
Run: python3 -P tests/test_teleport_audit.py
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "adapters", "game-g2gfast"))
sys.path.insert(0, ROOT)

# bsp_import reads through game-airdrift's `bsp_read` shim, which lives in that game's repo.
os.environ.setdefault("DOTBSP_PATH", ROOT)
for READER in (os.environ.get("G2G_TOOLS", ""),
               os.path.join(os.path.dirname(ROOT), "game-g2gfast", "tools"),
               "/home/gamedev/godot/game-g2gfast/tools"):
    if READER and os.path.isfile(os.path.join(READER, "bsp_read.py")):
        sys.path.append(READER)
        break
try:
    import bsp_import  # noqa: E402
except ModuleNotFoundError as err:
    raise unittest.SkipTest("bsp_read not found (set G2G_TOOLS): %s" % err)


def dest(name, x, y, z):
    return {"classname": "info_teleport_destination", "targetname": name,
            "origin": "%g %g %g" % (x, y, z), "angles": "0 0 0"}


def pit(lo, hi, to, track=0, original=None):
    o = original or (lo, hi)
    return {"kind": "RESPAWN", "track": track, "min": list(lo), "max": list(hi),
            "original_min": list(o[0]), "original_max": list(o[1]), "destination": list(to)}


def zoner(entities, solids=None):
    z = bsp_import.Zoner(types.SimpleNamespace(entities=entities, brushes=[]), solids=solids)
    return z


class SeparatePits(unittest.TestCase):
    def test_grown_neighbours_are_cut_at_the_gap(self):
        a = pit((0, 0, 0), (192, 64, 64), (1000, 0, 0), original=((0, 0, 0), (64, 64, 64)))
        b = pit((96, 0, 0), (288, 64, 64), (2000, 0, 0), original=((128, 0, 0), (192, 64, 64)))
        self.assertEqual(bsp_import.separate_pits([a, b]), 1)
        self.assertEqual(a["max"][0], 96)
        self.assertEqual(b["min"][0], 96)

    def test_same_destination_or_drawn_overlapping_are_left(self):
        a = pit((0, 0, 0), (192, 64, 64), (1000, 0, 0), original=((0, 0, 0), (64, 64, 64)))
        b = pit((96, 0, 0), (288, 64, 64), (1000, 0, 0), original=((128, 0, 0), (192, 64, 64)))
        self.assertEqual(bsp_import.separate_pits([a, b]), 0)
        c = pit((0, 0, 0), (100, 64, 64), (1, 0, 0))
        d = pit((50, 0, 0), (150, 64, 64), (2, 0, 0))
        self.assertEqual(bsp_import.separate_pits([c, d]), 0)
        self.assertEqual(c["max"][0], 100)

    def test_no_side_is_cut_thinner_than_a_tick(self):
        a = pit((0, 0, 0), (40, 64, 64), (1000, 0, 0), original=((0, 0, 0), (16, 64, 64)))
        b = pit((20, 0, 0), (200, 64, 64), (2000, 0, 0), original=((24, 0, 0), (192, 64, 64)))
        self.assertEqual(bsp_import.separate_pits([a, b]), 1)
        self.assertEqual(a["max"][0], bsp_import.TICK_DEPTH)
        self.assertEqual(b["min"][0], bsp_import.TICK_DEPTH)
        c = pit((0, 0, 0), (40, 64, 64), (1000, 0, 0), original=((0, 0, 0), (16, 64, 64)))
        d = pit((20, 0, 0), (50, 64, 64), (2000, 0, 0), original=((24, 0, 0), (40, 64, 64)))
        self.assertEqual(bsp_import.separate_pits([c, d]), 0)

    def test_other_tracks_are_left(self):
        a = pit((0, 0, 0), (192, 64, 64), (1, 0, 0), track=0, original=((0, 0, 0), (64, 64, 64)))
        b = pit((96, 0, 0), (288, 64, 64), (2, 0, 0), track=1, original=((128, 0, 0), (192, 64, 64)))
        self.assertEqual(bsp_import.separate_pits([a, b]), 0)


class Audit(unittest.TestCase):
    def setUp(self):
        self.ents = [
            {"classname": "trigger_teleport", "target": "a"},
            {"classname": "trigger_teleport", "target": "b"},
            {"classname": "trigger_teleport", "target": "nowhere"},
            {"classname": "trigger_teleport", "target": "a"},
            dest("a", 1000, 0, 0),
            dest("b", 2000, 0, 0),
        ]

    def audit(self, z):
        return bsp_import.teleport_audit(z)

    def build(self, zones_by_entity, solids=None):
        z = zoner(self.ents, solids)
        for i, made in zones_by_entity.items():
            z.claimed.add(i)
            z.pit_zones[i] = made
            z.zones.extend(made)
        return z

    def test_clean_map_has_no_broken(self):
        z = self.build({0: [pit((0, 0, 0), (64, 64, 64), (1000, 0, 0))],
                        1: [pit((200, 0, 0), (264, 64, 64), (2000, 0, 0))]})
        z.claimed.add(3)
        out = self.audit(z)
        self.assertEqual(out["broken"], [])
        self.assertEqual(out["teleports"], 4)
        self.assertEqual(out["pits"], 2)
        self.assertEqual(out["claimed"], 1)
        self.assertEqual(out["no_volume"], 1)

    def test_unresolved_and_gone(self):
        z = self.build({2: [pit((0, 0, 0), (64, 64, 64), (0, 0, 0))]})
        z.pit_zones[0] = [pit((300, 0, 0), (364, 64, 64), (1000, 0, 0))]
        problems = {b["entity"]: b["problem"] for b in self.audit(z)["broken"]}
        self.assertEqual(problems, {2: "unresolved", 0: "gone"})

    def test_shadowed_by_a_pit_grown_over_it(self):
        z = self.build({0: [pit((0, 0, 0), (128, 64, 64), (1000, 0, 0), original=((0, 0, 0), (32, 64, 64)))],
                        1: [pit((64, 0, 0), (96, 64, 64), (2000, 0, 0))]})
        broken = self.audit(z)["broken"]
        self.assertEqual([(b["entity"], b["problem"]) for b in broken], [(1, "shadowed")])

    def test_a_trigger_drawn_inside_another_is_counted_not_broken(self):
        z = self.build({0: [pit((0, 0, 0), (128, 64, 64), (1000, 0, 0))],
                        1: [pit((32, 0, 0), (96, 64, 64), (2000, 0, 0))]})
        out = self.audit(z)
        self.assertEqual(out["broken"], [])
        self.assertEqual(out["drawn_overlap"], 1)

    def test_name_filtered_stack_is_counted_not_broken(self):
        self.ents[0]["filtername"] = "f1"
        self.ents[1]["filtername"] = "f2"
        z = self.build({0: [pit((0, 0, 0), (128, 64, 64), (1000, 0, 0), original=((0, 0, 0), (32, 64, 64)))],
                        1: [pit((64, 0, 0), (96, 64, 64), (2000, 0, 0))]})
        out = self.audit(z)
        self.assertEqual(out["broken"], [])
        self.assertEqual(out["filter_stack"], 1)

    def test_one_that_starts_off_under_an_always_on_trigger_is_counted(self):
        self.ents[1]["StartDisabled"] = "1"
        z = self.build({0: [pit((0, 0, 0), (128, 64, 64), (1000, 0, 0), original=((0, 0, 0), (32, 64, 64)))],
                        1: [pit((64, 0, 0), (96, 64, 64), (2000, 0, 0))]})
        out = self.audit(z)
        self.assertEqual(out["broken"], [])
        self.assertEqual(out["filter_stack"], 1)

    def test_loop(self):
        p = pit((0, 0, 0), (64, 64, 64), (1000, 0, 0))
        p["looped"] = True
        z = self.build({0: [p]})
        self.assertEqual([b["problem"] for b in self.audit(z)["broken"]], ["loop"])

    def test_a_holding_cell_is_counted_not_broken(self):
        p = pit((0, 0, 0), (64, 64, 64), (1000, 0, 0))
        p["looped"] = True
        cell = pit((950, -50, 0), (1050, 50, 100), (1000, 0, 0))
        cell["looped"] = True
        out = self.audit(self.build({0: [p], 3: [cell]}))
        self.assertEqual(out["broken"], [])
        self.assertEqual(out["hold"], 2)

    def solid_at(self, z, lo, hi):
        z.solids = [(lo, hi)]
        z.bsp.brushes = [(0, 0, bsp_import.MASK_PLAYERSOLID)]
        z.bsp.model_brushes = lambda model: {0} if model == 0 else set()
        real = bsp_import.point_in_brush
        bsp_import.point_in_brush = lambda bsp, i, p, eps: all(lo[k] < p[k] < hi[k] for k in range(3))
        self.addCleanup(setattr, bsp_import, "point_in_brush", real)

    def test_in_solid_unless_a_door_takes_them_on(self):
        # The pit was chained on to (1500, 0, 0): our destination, not the map's.
        z = self.build({0: [pit((0, 0, 0), (64, 64, 64), (1500, 0, 0))]})
        self.solid_at(z, (1400, -100, 0), (1600, 100, 200))
        self.assertEqual([b["problem"] for b in self.audit(z)["broken"]], ["in_solid"])
        z.add("TELEPORT", 0, box=((1400, -100, 0), (1600, 100, 200)), destination=(2000, 0, 0))
        self.assertEqual(self.audit(z)["broken"], [])

    def test_a_map_aiming_into_a_solid_is_counted_not_broken(self):
        z = self.build({0: [pit((0, 0, 0), (64, 64, 64), (1000, 0, 0))]})
        self.solid_at(z, (900, -100, 0), (1100, 100, 200))
        out = self.audit(z)
        self.assertEqual(out["broken"], [])
        self.assertEqual(out["authored_solid"], 1)

    def test_landmark_is_counted(self):
        self.ents[0]["landmark"] = "lm"
        z = self.build({0: [pit((0, 0, 0), (64, 64, 64), (1000, 0, 0))]})
        self.assertEqual(self.audit(z)["landmark"], 1)


class FinishTeleports(unittest.TestCase):
    def test_the_trigger_inside_the_end_still_sends(self):
        inside = {"classname": "trigger_teleport", "target": "end", "_box": ((10, 10, 0), (50, 50, 40))}
        outside = {"classname": "trigger_teleport", "target": "end", "_box": ((500, 0, 0), (540, 40, 40))}
        z = zoner([inside, outside, dest("end", 3000, 0, 0)])
        real = bsp_import.brush_box
        bsp_import.brush_box = lambda bsp, e: e.get("_box")
        try:
            bsp_import.finish_teleports(z, {"teleport_to": "END"}, 0, ((0, 0, 0), (64, 64, 64)))
        finally:
            bsp_import.brush_box = real
        self.assertEqual(len(z.zones), 1)
        zone = z.zones[0]
        self.assertEqual(zone["kind"], "TELEPORT")
        self.assertTrue(zone["finish"])
        self.assertEqual(zone["destination"][0], 3000)


class SendsOutOfSolid(unittest.TestCase):
    """Zoner.sends: a destination inside a brush is followed to where the player really arrives."""

    def setUp(self):
        self.boxes = {}
        self._brush_box = bsp_import.brush_box
        bsp_import.brush_box = lambda bsp, e: self.boxes.get(e.get("targetname"))

    def tearDown(self):
        bsp_import.brush_box = self._brush_box

    def zoner(self, entities, solid):
        z = zoner(entities)
        z.stuck = lambda at, lift=0.0: any(bsp_import.box_contains(b, at) for b in solid)
        return z

    def test_clear_destination_is_kept(self):
        door = {"classname": "trigger_teleport", "targetname": "door", "target": "a"}
        z = self.zoner([door, dest("a", 100, 0, 0)], [])
        self.assertEqual(list(z.sends(door)[0]), [100.0, 0.0, 0.0])
        self.assertEqual(z.resent, {})

    def test_destination_in_a_cell_goes_where_the_cell_sends(self):
        door = {"classname": "trigger_teleport", "targetname": "door", "target": "in"}
        cell = {"classname": "trigger_teleport", "targetname": "cell", "target": "out", "StartDisabled": "1"}
        self.boxes["cell"] = ((-64, -64, -64), (64, 64, 64))
        z = self.zoner([door, cell, dest("in", 0, 0, 0), dest("out", 500, 0, 0)],
                       [((-32, -32, -32), (32, 32, 32))])
        self.assertEqual(list(z.sends(door)[0]), [500.0, 0.0, 0.0])
        self.assertEqual(z.resent[id(door)], "cell")

    def test_an_enabled_cell_is_left_to_the_pits_follow_pass(self):
        door = {"classname": "trigger_teleport", "targetname": "door", "target": "in"}
        cell = {"classname": "trigger_teleport", "targetname": "cell", "target": "out"}
        self.boxes["cell"] = ((-64, -64, -64), (64, 64, 64))
        z = self.zoner([door, cell, dest("in", 0, 0, 0), dest("out", 500, 0, 0)],
                       [((-32, -32, -32), (32, 32, 32))])
        self.assertEqual(list(z.sends(door)[0]), [0.0, 0.0, 0.0])
        self.assertEqual(z.resent, {})

    def test_landmark_teleport_takes_the_nearest_clear_offset(self):
        door = {"classname": "trigger_teleport", "targetname": "door", "target": "to", "landmark": "door"}
        mark = {"classname": "info_landmark", "targetname": "door", "origin": "0 0 0"}
        self.boxes["door"] = ((-64, 0, 0), (64, 0, 0))
        # The authored point and the landmark itself are inside walls; 48 units to +x (the 16-unit grid) both are clear.
        z = self.zoner([door, mark, dest("to", 1000, 0, 0)],
                       [((960, -8, -8), (1040, 8, 8)), ((-80, -8, -8), (40, 8, 8))])
        at = z.sends(door)[0]
        self.assertEqual(list(at), [1048.0, 0.0, 0.0])
        self.assertEqual(z.resent[id(door)], "landmark")

    def test_unresolved_destination_is_left_for_the_audit(self):
        door = {"classname": "trigger_teleport", "targetname": "door", "target": "a"}
        # Solid for 200 units round: nothing within reach to step out to.
        z = self.zoner([door, dest("a", 0, 0, 0)], [((-200, -200, -8), (200, 200, 8))])
        self.assertEqual(list(z.sends(door)[0]), [0.0, 0.0, 0.0])
        self.assertEqual(z.resent, {})

    def test_destination_in_a_small_solid_steps_out_of_it(self):
        door = {"classname": "trigger_teleport", "targetname": "door", "target": "a"}
        z = self.zoner([door, dest("a", 0, 0, 0)], [((-13, -16, -8), (13, 16, 8))])
        self.assertEqual(list(z.sends(door)[0]), [-16.0, 0.0, 0.0])
        self.assertEqual(z.resent[id(door)], "step out")

    def test_destination_in_a_func_wall_steps_out_of_it(self):
        door = {"classname": "trigger_teleport", "targetname": "door", "target": "a"}
        wall = {"classname": "func_wall", "targetname": "wall", "model": "*5"}
        self.boxes["wall"] = ((-16, -8, 0), (16, 8, 80))
        z = self.zoner([door, wall, dest("a", 0, 0, 0)], [])
        self.assertTrue(z.walled((0, 0, 0)))
        self.assertFalse(z.walled((0, 40, 0)))
        self.assertEqual(list(z.sends(door)[0]), [-16.0, 0.0, 0.0])
        self.assertEqual(z.resent[id(door)], "step out")

    def test_parented_teleport_that_starts_disabled_is_dropped(self):
        moving = {"classname": "trigger_teleport", "targetname": "t1", "target": "a",
                  "parentname": "mover", "StartDisabled": "1"}
        fixed = {"classname": "trigger_teleport", "targetname": "t2", "target": "a", "StartDisabled": "1"}
        live = {"classname": "trigger_teleport", "targetname": "t3", "target": "a", "parentname": "mover"}
        z = zoner([moving, fixed, live, dest("a", 0, 0, 0)])
        bsp_import.parented_teleports(z)
        self.assertEqual(sorted(z.claimed), [0])
        self.assertTrue(any("start disabled on a moving parent" in n for n in z.notes))

    def test_stuck_probes_the_lifted_point(self):
        z = zoner([])
        z.bsp.model_brushes = lambda m: [0]
        z.bsp.brushes = [(0, 1, bsp_import.MASK_PLAYERSOLID)]
        inside = self._point_in_brush = bsp_import.point_in_brush
        bsp_import.point_in_brush = lambda bsp, i, p, eps: p[2] < 20  # a floor 20 units thick
        try:
            self.assertTrue(z.stuck((0, 0, 0)))
            self.assertFalse(z.stuck((0, 0, 0), bsp_import.DESTINATION_LIFT))
        finally:
            bsp_import.point_in_brush = inside


if __name__ == "__main__":
    unittest.main()
