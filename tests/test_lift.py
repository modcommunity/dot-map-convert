"""Tests for the pieces lifted out of the maps repositories' adapters: the flood, the entity
classifier, prop matching, lights, .gma reading, the game-lump and truncation guards, the
open-wall plan, the 0.0254 scale and the teleport helper. Run: python3 -I tools/bsp/tests/test_lift.py

Every map is written by synth.py; a .gma is written here and read by the real fastgmad (the
test skips when it is not installed).
"""

import json
import os
import struct
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import bsp as cli                                          # noqa: E402,F401
import synth                                               # noqa: E402
from dotbsp import (entities, flood, gamebox, gma, intermediate, lights, plan, props,  # noqa: E402
                    reader, sources, units)


def doc_of(**kw):
    credit = kw.pop("credit", None)
    scale = kw.pop("scale", None)
    return intermediate.build(reader.Bsp("t.bsp", data=synth.build(**kw)).load(), credit=credit, scale=scale)


class StemKeys(unittest.TestCase):
    def test_a_key_without_a_folder_matches_by_stem(self):
        tb = props.PropTable({"chair_office": "chair", "models/props/couch.mdl": "couch"})
        self.assertEqual(tb.get("models/Props_Interiors/Chair_Office.mdl"), "chair")
        self.assertEqual(tb.get("models/props/couch.mdl"), "couch")
        self.assertIsNone(tb.get("models/other/couch.mdl"))
        self.assertEqual(tb.unmatched(["models/x/chair_office.mdl", "models/q/z.mdl"]), [("models/q/z.mdl", 1)])


class GameLump(unittest.TestCase):
    def test_empty_and_short_lumps_are_no_props(self):
        for raw in (b"", b"\x00\x00", struct.pack("<i", 0)):
            b = reader.Bsp("t", data=synth.build(game_lump=raw)).load()
            self.assertEqual(b.game_lumps(), {})
            self.assertEqual(b.static_props(), [])

    def test_count_larger_than_the_lump_and_wild_entries(self):
        raw = struct.pack("<i", 50) + struct.pack("<4sHHii", b"prps", 0, 4, 10 ** 8, 40)
        b = reader.Bsp("t", data=synth.build(game_lump=raw)).load()
        self.assertEqual(b.game_lumps(), {})            # the one entry points outside the file
        self.assertEqual(b.static_props(), [])

    def test_static_props_still_read(self):
        b = reader.Bsp("t", data=synth.build(static_props=[("models/Props/Couch.mdl", (1, 2, 3), (0, 90, 0))])).load()
        self.assertEqual(b.static_props()[0]["model"], "models/props/couch.mdl")

    def test_cut_off_file_is_refused_by_name(self):
        data = synth.build()
        cut = bytearray(data)
        # the planes lump now points past the end of the file, as Helix's 4 MB piece of 23 did
        struct.pack_into("<iii", cut, 8 + 1 * 16, len(data) + 1000, 96, 0)
        b = reader.Bsp("helix.bsp", data=bytes(cut))
        self.assertEqual(b.truncated(), [1])
        with self.assertRaises(ValueError) as cm:
            b.load()
        self.assertIn("cut off", str(cm.exception))


class Scale(unittest.TestCase):
    def test_default_and_hull(self):
        self.assertEqual(doc_of()["units"]["metres_per_unit"], 0.01905)
        d = doc_of(scale="hull")
        self.assertEqual(d["units"]["metres_per_unit"], 0.0254)
        self.assertIn("0.0254", d["units"]["length"])
        self.assertEqual(doc_of(scale=0.03)["units"]["metres_per_unit"], 0.03)

    def test_bad_scale(self):
        for bad in ("huge", 0, -1, "0"):
            with self.assertRaises(ValueError):
                units.parse_scale(bad)

    def test_a_72_unit_player(self):
        self.assertAlmostEqual(72 * units.HULL, 1.83, 2)
        self.assertAlmostEqual(units.from_metres(0.4, units.HULL) * units.HULL, 0.4)
        self.assertEqual(units.to_game((10, 20, 30), 0.5, 1.0), (5.0, 14.0, -10.0))

    def test_cli_scale_flag(self):
        with tempfile.TemporaryDirectory() as t:
            p, out = os.path.join(t, "a.bsp"), os.path.join(t, "a.json")
            open(p, "wb").write(synth.build())
            self.assertEqual(cli.main(["bsp.py", "convert", p, "--out", out, "--scale", "hull", "--author", "a", "--page", "p"]), 0)
            self.assertEqual(json.load(open(out))["units"]["metres_per_unit"], 0.0254)

    def test_cli_cut_off_file_is_a_message(self):
        with tempfile.TemporaryDirectory() as t:
            data = bytearray(synth.build())
            struct.pack_into("<iii", data, 8 + 16, len(data) + 99, 96, 0)
            p = os.path.join(t, "a.bsp")
            open(p, "wb").write(bytes(data))
            self.assertEqual(cli.main(["bsp.py", "convert", p, "--out", os.path.join(t, "o.json")]), 1)


class Classifier(unittest.TestCase):
    def test_entities(self):
        k = entities.classify_entity
        self.assertEqual(k({"classname": "info_player_terrorist"}), entities.SPAWN)
        self.assertEqual(k({"classname": "light_environment"}), entities.LIGHT)
        self.assertEqual(k({"classname": "prop_physics_multiplayer"}), entities.PROP)
        self.assertEqual(k({"classname": "func_physbox"}), entities.PROP)
        self.assertEqual(k({"classname": "func_door_rotating"}), entities.DOOR)
        self.assertEqual(k({"classname": "momentary_rot_button"}), entities.BUTTON)
        self.assertEqual(k({"classname": "trigger_teleport"}), entities.TELEPORT)
        self.assertEqual(k({"classname": "trigger_multiple"}), entities.TRIGGER)
        self.assertEqual(k({"classname": "func_illusionary"}), entities.NONSOLID_BRUSH)
        self.assertEqual(k({"classname": "func_wall"}), entities.SOLID_BRUSH)
        self.assertEqual(k({"classname": "env_fire"}), entities.OTHER)
        self.assertEqual(k({"classname": "env_fire"}, extra={"env_fire": "hazard"}), "hazard")

    def test_brushes(self):
        solid = reader.CONTENTS_SOLID
        self.assertEqual(entities.classify_brush([(1.0, "Brick/Wall01")], solid), ("solid", "brick/wall01"))
        self.assertEqual(entities.classify_brush([(0.0, "tools/toolsclip")], solid)[0], "invisible")
        self.assertEqual(entities.classify_brush([(0.0, "tools/toolsskybox")], solid)[0], "sky")
        self.assertEqual(entities.classify_brush([(0.0, "glass/pane")], reader.CONTENTS_WINDOW)[0], "glass")
        self.assertEqual(entities.classify_brush([(0.0, "brick/x")], reader.CONTENTS_PLAYERCLIP)[0], "invisible")
        # the top face's material decides, not the first side's
        self.assertEqual(entities.classify_brush([(0.0, "side"), (1.0, "grass")], solid)[1], "grass")

    def test_document_classification(self):
        d = doc_of()
        kinds = entities.classify_all(d)
        self.assertEqual(len(kinds[entities.SPAWN]), 2)
        self.assertEqual(len(kinds[entities.LIGHT]), 1)
        d2 = doc_of(entity_box=(0, 0, 0, 8, 8, 8), entity_origin=(100, 0, 0))
        door = [r for r in d2["entities"] if r["classname"] == "func_door"][0]
        self.assertEqual(entities.classify_entity(door["keys"]), entities.DOOR)
        brush = [b for b in d2["brushes"] if b["model"] == 1][0]
        self.assertEqual(entities.classify_brush_record(d2, brush)[0], "solid")


def tele_doc(dest_name="dest", with_dest=True):
    ents = [{"classname": "worldspawn"},
            {"classname": "trigger_teleport", "model": "*1", "target": dest_name}]
    if with_dest:
        ents.append({"classname": "info_teleport_destination", "targetname": "dest", "origin": "500 600 70", "angles": "0 270 0"})
        ents.append({"classname": "info_target", "targetname": "dest", "origin": "1 1 1"})    # a decoy with the same name
    return doc_of(entities=ents, boxes=((0, 0, 0, 64, 64, 8),), entity_box=(100, 100, 0, 140, 140, 32))


class Teleports(unittest.TestCase):
    def test_resolves_the_destination_class_first(self):
        d = tele_doc()
        t = entities.teleports(d)
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0]["dest_origin"], [500.0, 600.0, 70.0])
        self.assertEqual(t[0]["dest_yaw"], 270.0)
        self.assertEqual(t[0]["destination"]["classname"], "info_teleport_destination")
        self.assertEqual(t[0]["mins"][:2], [100.0, 100.0])
        self.assertEqual(entities.teleport_destination(d, "*1"), ([500.0, 600.0, 70.0], 270.0))
        self.assertEqual(entities.teleport_destination(d, 1)[1], 270.0)

    def test_missing_destination_is_none_not_a_crash(self):
        d = tele_doc(dest_name="nowhere")
        t = entities.teleports(d)
        self.assertIsNone(t[0]["dest_origin"])
        self.assertIsNone(entities.teleport_destination(d, 1))
        self.assertIsNone(entities.teleport_destination(tele_doc(with_dest=False), "*1"))

    def test_pad_rect_widens_a_thin_trigger(self):
        t = {"mins": [100, 100, 0], "maxs": [104, 300, 10]}
        x0, x1, y0, y1 = entities.pad_rect(t)
        self.assertEqual((x1 - x0, y1 - y0), (48.0, 200))
        self.assertEqual((x0 + x1) / 2, 102)


class Props(unittest.TestCase):
    def doc(self):
        ents = [{"classname": "worldspawn"},
                {"classname": "prop_physics", "model": "Models/Props_C17/Chair.mdl", "origin": "10 20 0", "angles": "0 45 0"},
                {"classname": "prop_dynamic", "model": "models\\props\\table.mdl", "origin": "30 20 0"},
                {"classname": "prop_physics", "model": "models/unmapped.mdl", "origin": "0 0 0"},
                {"classname": "func_door", "model": "*1"}]
        return doc_of(entities=ents, static_props=[("models/props//Couch.mdl", (1, 2, 3), (0, 90, 0)),
                                                   ("models/props/lamp.mdl", (4, 5, 6), (0, 0, 0))],
                      entity_box=(0, 0, 0, 8, 8, 8))

    def test_matching_is_case_slash_and_source_blind(self):
        d = self.doc()
        table = {"models/props_c17/chair.mdl": "chair", "MODELS/PROPS/TABLE.MDL": "table", "models/props/couch.mdl": "sofa"}
        got = props.placed_props(d, table)
        self.assertEqual(sorted((p["id"], p["source"]) for p in got), [("chair", "entity"), ("sofa", "static"), ("table", "entity")])
        chair = [p for p in got if p["id"] == "chair"][0]
        self.assertEqual((chair["origin"], chair["yaw"]), ([10.0, 20.0, 0.0], 45.0))
        self.assertEqual([p["id"] for p in props.placed_props(d, table, include_static=False)].count("sofa"), 0)

    def test_prop_dynamic_solid_is_carried(self):
        d = self.doc()
        d["entities"][2]["keys"]["solid"] = "6"
        d["entities"][1]["keys"]["solid"] = "6"
        got = {p["id"]: p["solid"] for p in props.placed_props(d, {"models/props_c17/chair.mdl": "chair", "models/props/table.mdl": "table"})}
        self.assertEqual(got, {"chair": 6, "table": 6})

    def test_solidity_is_the_sources_own(self):
        self.assertEqual(props.entity_solid("prop_physics", {}), 6)
        self.assertEqual(props.entity_solid("prop_physics_multiplayer", {"spawnflags": "4"}), 0)
        self.assertEqual(props.entity_solid("prop_dynamic", {}), 0)
        self.assertEqual(props.entity_solid("prop_dynamic", {"solid": "2"}), 2)
        d = self.doc()
        d["static_props"][0]["solid"] = 6
        d["static_props"][1]["solid"] = 0
        got = {p["id"]: p["solid"] for p in props.placed_props(d, {"models/props/couch.mdl": "sofa", "models/props/lamp.mdl": "lamp"}) if p["source"] == "static"}
        self.assertEqual(got, {"sofa": 6, "lamp": 0})

    def test_unmatched_and_census(self):
        d = self.doc()
        t = props.PropTable({"models/props/couch.mdl": "sofa"})
        self.assertIn(("models/unmapped.mdl", 1), t.unmatched(m for m, _ in props.model_census(d)))
        self.assertNotIn("*1", [m for m, _ in props.model_census(d)])
        self.assertEqual(len(props.model_census(d)), 5)
        self.assertEqual(props.norm_model("/Models\\\\A//B.MDL"), "models/a/b.mdl")


class Lights(unittest.TestCase):
    def doc(self):
        ents = [{"classname": "worldspawn"},
                {"classname": "light", "origin": "0 0 100", "_light": "255 128 0 400"},
                {"classname": "light", "origin": "10 0 100", "_light": "255 255 255 100"},
                {"classname": "light_spot", "origin": "500 0 100", "_light": "255 255 255 200", "_cone": "40", "angles": "-90 0 0"},
                {"classname": "light_environment", "origin": "0 0 0", "_light": "255 250 240 300", "angles": "0 90 0", "pitch": "-90", "_ambient": "100 110 120 50"}]
        return doc_of(entities=ents)

    def test_to_game(self):
        lamps, suns = lights.to_game(self.doc()["lights"], scale=0.0254)
        self.assertEqual(len(lamps), 3)
        self.assertEqual(len(suns), 1)
        self.assertEqual(lamps[0]["at"], [0.0, 2.54, -0.0])
        self.assertEqual(lamps[0]["colour"], [1.0, 0.502, 0.0])
        self.assertEqual(lamps[0]["range"], 9.0)              # capped
        self.assertAlmostEqual(lamps[1]["range"], 3.5 + 100 / 60, 3)
        self.assertEqual(lamps[2]["spot"]["cone"], 40.0)
        self.assertEqual(suns[0]["direction"][1], -1.0)         # straight down in Godot's y
        self.assertEqual(suns[0]["ambient"], [0.392, 0.431, 0.471])

    def test_thin_is_deterministic_and_keeps_the_brightest(self):
        lamps, _ = lights.to_game(self.doc()["lights"])
        a = lights.thin(lamps, max_lights=2)
        self.assertEqual(a, lights.thin(lamps, max_lights=2))
        self.assertEqual(len(a), 2)
        self.assertIn(lamps[0], a)                              # brightest
        spaced = lights.thin(lamps, max_lights=10, min_spacing=1.0)
        self.assertEqual(len(spaced), 2)                        # the two 10-unit-apart lamps are 0.19 m apart
        self.assertEqual(len(lights.thin(lamps, max_lights=10)), 3)

    def test_spread_order_keeps_every_lamp_and_every_prefix_spread(self):
        # two clusters of 20 lamps 100 m apart: the first two of the order are one from each
        lamps = [{"at": [float(i) * 0.1, 3.0, 0.0], "range": 5.0, "energy": 1.0} for i in range(20)] + \
                [{"at": [100.0 + i * 0.1, 3.0, 0.0], "range": 5.0, "energy": 1.0} for i in range(20)]
        out = lights.spread_order(lamps)
        self.assertEqual(sorted(l["at"][0] for l in out), sorted(l["at"][0] for l in lamps))
        self.assertEqual(sorted(l["at"][0] > 50 for l in out[:2]), [False, True])
        self.assertEqual(out, lights.spread_order(lamps))
        self.assertEqual(lights.spread_order(lamps[:1]), lamps[:1])

    def test_auto_lights(self):
        cells = {(ix, iz): 0.0 for ix in range(0, 26) for iz in range(0, 26)}     # 13 m square of 0.5 m cells
        out = lights.auto(cells, spacing=6.0, height=2.3, maximum=100)
        self.assertEqual(len(out), 9)                           # 3 x 3 squares of 6 m over 13 m
        self.assertEqual(out[0]["at"], [0.25, 2.3, 0.25])       # (ix, iz) order: cell (0, 0) first
        self.assertEqual(len(lights.auto(cells, maximum=4)), 4)
        # order is by cell, not by position: with x-major cells the first four lamps are the x = 0 column
        first = lights.auto(cells, maximum=3)
        self.assertEqual([l["at"][0] for l in first], [0.25, 0.25, 0.25])
        self.assertEqual(lights.auto([(0, 0, 1.0), (0, 0, 1.0)], maximum=5)[0]["at"], [0.25, 3.3, 0.25])


def floor_box(x0, z0, x1, z1, y_top, thick=0.2):
    return {"at": [(x0 + x1) / 2, y_top - thick / 2, (z0 + z1) / 2], "size": [x1 - x0, thick, z1 - z0]}


class Flood(unittest.TestCase):
    def test_floor_and_step_limits(self):
        boxes = [floor_box(0, 0, 4, 4, 0.0),
                 floor_box(4, 0, 6, 4, 0.3),       # a kerb: walked
                 floor_box(6, 0, 8, 4, 1.1),       # 0.8 above the kerb: a jump, crossed
                 floor_box(8, 0, 10, 4, 3.0),      # 1.9 above: neither
                 floor_box(20, 0, 22, 4, 0.0)]     # an island
        f = flood.Flood(boxes).run([(1, 0.1, 1)])
        self.assertIsNotNone(f.reachable(7, 1.1, 1))
        self.assertIsNone(f.reachable(9, 3.0, 1))
        self.assertIsNone(f.reachable(21, 0.0, 1))
        self.assertIsNotNone(f.reachable(3, 0.0, 1))
        self.assertTrue(any(l[4] > l[1] for l in f.links.values()))     # the jump up is a link

    def test_a_drop_is_crossed_and_linked_a_cliff_is_not(self):
        boxes = [floor_box(0, 0, 4, 4, 2.5), floor_box(4, 0, 8, 4, 0.0), floor_box(8, 0, 12, 4, -4.0)]
        f = flood.Flood(boxes).run([(1, 2.5, 1)])
        self.assertIsNotNone(f.reachable(5, 0.0, 1))
        self.assertIsNone(f.reachable(9, -4.0, 1))
        self.assertTrue(any(l[4] < l[1] for l in f.links.values()))

    def test_headroom(self):
        boxes = [floor_box(0, 0, 4, 4, 0.0), floor_box(0, 0, 4, 4, 1.0)]    # a slab 1 m over the floor
        f = flood.Flood(boxes)
        self.assertEqual(f.surfaces_at(1, 1), [1.0])                         # the floor under it has no head room

    def test_wall_blocks_and_a_thin_wall_needs_thin_walls(self):
        boxes = [floor_box(0, 0, 8, 4, 0.0), {"at": [4.0, 1.0, 2.0], "size": [0.02, 2.0, 4.0]}]
        solid = flood.Flood(boxes, thin_walls=True).run([(1, 0, 1)])
        self.assertIsNone(solid.reachable(6, 0.0, 1))
        leaky = flood.Flood(boxes).run([(1, 0, 1)])                         # the old behaviour, kept as the default
        self.assertIsNotNone(leaky.reachable(6, 0.0, 1))

    def test_wide_rejects_a_one_cell_doorway(self):
        boxes = [floor_box(0, 0, 4, 4, 0.0), floor_box(4, 1.5, 6, 2.0, 0.0), floor_box(6, 0, 10, 4, 0.0)]
        self.assertIsNotNone(flood.Flood(boxes).run([(1, 0, 1)]).reachable(8, 0.0, 1))
        self.assertIsNone(flood.Flood(boxes).run([(1, 0, 1)], wide=True).reachable(8, 0.0, 1))

    def test_blocked_cells_and_lost(self):
        boxes = [floor_box(0, 0, 4, 4, 0.0), floor_box(4, 1.5, 5, 2.5, 0.0), floor_box(5, 0, 9, 4, 0.0)]
        free = flood.Flood(boxes).run([(1, 0, 1)])
        blocked = {(8, 3): [0.0], (8, 4): [0.0]}                           # a prop in the doorway cells
        shut = flood.Flood(boxes).run([(1, 0, 1)], blocked=blocked, wide=True)
        self.assertGreater(len(shut.lost(free)), 0)

    def test_turned_box_and_sky_and_nonsolid_are_ignored(self):
        boxes = [floor_box(0, 0, 4, 4, 0.0), dict(floor_box(0, 0, 4, 4, 5.0), _sky=True), dict(floor_box(0, 0, 4, 4, 6.0), solid=False)]
        self.assertEqual(flood.Flood(boxes).surfaces_at(1, 1), [0.0])
        turned = dict(floor_box(0, 0, 4, 2, 0.0), yaw=45)
        self.assertTrue(flood.inside_box(turned, 2.0, 1.0))
        self.assertFalse(flood.inside_box(turned, 0.1, 0.1) and flood.inside_box(turned, 3.9, 3.9))

    def test_floor_rects_cover_the_walked_cells_both_ways(self):
        boxes = [floor_box(0, 0, 4, 4, 0.0), floor_box(0, 4, 2, 6, 0.0)]       # an L
        f = flood.Flood(boxes).run([(1, 0, 1)])
        for greedy in (False, True):
            rects = f.floor_rects(greedy=greedy)
            area = sum((r[2] - r[0] + 0.1) * (r[3] - r[1] + 0.1) for r in rects)
            self.assertAlmostEqual(area, 4 * 4 + 2 * 2, 3)
        self.assertLessEqual(len(f.floor_rects(greedy=True)), len(f.floor_rects()))
        # heights 0.1 apart are one floor
        f2 = flood.Flood([floor_box(0, 0, 2, 2, 0.0), floor_box(2, 0, 4, 2, 0.1)]).run([(1, 0, 1)])
        self.assertEqual({r[4] for r in f2.floor_rects()}, {0.1})

    def test_keep_starts_drops_no_floor_and_far_below_the_median(self):
        f = flood.Flood([floor_box(0, 0, 4, 4, 0.0), floor_box(10, 0, 14, 4, -12.0)])
        starts = [(1, 0.1, 1), (2, 0.1, 2), (3, 0.1, 3), (11, -11.9, 1), (30, 0.1, 30)]
        kept, dropped = f.keep_starts(starts)
        self.assertEqual(kept, starts[:3])
        self.assertEqual(dropped, starts[3:])
        self.assertEqual(f.keep_starts([]), ([], []))

    def test_deep_cells_skip_the_edge(self):
        f = flood.Flood([floor_box(0, 0, 6, 6, 0.0)]).run([(3, 0, 3)])
        deep = f.deep_cells()
        self.assertEqual(len(f.cells()), 144)
        self.assertEqual(len(deep), 64)                 # 12 x 12 cells, 2 cells in from each side
        self.assertEqual(len(f.top_cells()), 144)

    def test_sky_shell_from_model_boxes_stays_out_of_the_flood(self):
        d = doc_of(boxes=((0, 0, 0, 400, 400, 8), (-8, -8, 200, 408, 408, 208)),
                   materials=("brick/wall", "tools/toolsskybox"), contents=1)
        # brush 1 uses only the skybox material on every side; brush 0 mixes, so give it its own
        d["brushes"][0]["sides"] = [dict(s, material=0) for s in d["brushes"][0]["sides"]]
        d["brushes"][1]["sides"] = [dict(s, material=1) for s in d["brushes"][1]["sides"]]
        out = gamebox.model_boxes(d, 0, scale=0.0254)
        sky = [b for b in out if b["kind"] == "sky"]
        self.assertEqual(len(sky), 1)
        self.assertTrue(sky[0]["_sky"] and sky[0]["visible"] is False)
        f = flood.Flood(out).run([(2.0, 0.3, -2.0)])
        self.assertGreater(len(f.cells()), 0)
        self.assertEqual(len({h for _, _, h in f.seen}), 1)   # one floor: never the sky lid on top

    def test_zero_thickness_slab_is_clamped_and_rounded(self):
        d = doc_of(boxes=((0, 0, 0, 100, 100, 1),))
        out = gamebox.model_boxes(d, 0, scale=0.01, min_m=0.0)      # 1 unit = 1 cm: a 1 cm slab
        self.assertTrue(out)
        for b in out:
            self.assertGreaterEqual(min(b["size"]), 0.02)
            for v in b["at"] + b["size"] + [b["yaw"]]:
                self.assertEqual(v, round(v, 3))

    def test_min_floor_y_drops_a_sump(self):
        f = flood.Flood([floor_box(0, 0, 4, 4, -2.0)], min_floor_y=-1.0)
        self.assertEqual(f.surf, {})

    def test_model_boxes_from_a_document(self):
        d = doc_of(boxes=((0, 0, 0, 200, 200, 8), (0, 0, 8, 200, 8, 80)),
                   materials=("brick/wall", "tools/toolsnodraw"), entity_box=(10, 10, 8, 20, 20, 30))
        out = gamebox.model_boxes(d, 0, scale=0.0254)
        self.assertEqual(len(out), 2)
        floor = out[0]
        self.assertAlmostEqual(floor["size"][0], 200 * 0.0254, 3)
        self.assertAlmostEqual(floor["at"][1], 4 * 0.0254, 3)
        self.assertEqual(floor["kind"], "solid")
        self.assertEqual(len(gamebox.model_boxes(d, 1)), 1)
        f = flood.Flood(gamebox.model_boxes(d, 0, scale=0.0254)).run([(2.0, 0.3, -2.0)])
        self.assertIsNotNone(f.reachable(1.0, 0.3, -1.0))


def room_doc(gap=False, entity_walls=False):
    """A 24 x 16 unit-block building: a shell, one partition with a doorway, and (optionally)
    a gap in the shell and walls that are brush entities rather than world brushes."""
    S = 100          # units per wall block; at scale 0.04 a unit is 4 cm
    walls = []
    # the world: shell 0..960 x 0..640, 16 thick, 128 tall
    def box(x0, y0, x1, y1):
        return (x0, y0, 0, x1, y1, 128)
    shell = [box(0, 0, 960, 16), box(0, 624, 960, 640), box(0, 0, 16, 640), box(944, 0, 960, 640)]
    if gap:
        shell[3] = box(944, 0, 960, 250)         # the east wall has a hole 1.2 m wide (30 units at 4 cm)
        shell.append(box(944, 280, 960, 640))
    part = [box(472, 0, 488, 285), box(472, 315, 488, 640)]    # a partition with a doorway 30 units (1.2 m) wide
    world = shell if not entity_walls else shell[:2] + shell[2:]
    ents = [{"classname": "worldspawn"}]
    d = doc_of(entities=ents, boxes=tuple(world + (part if not entity_walls else [])),
               entity_box=None)
    if entity_walls:
        # the partition as func_brush models: re-build with them as brush entities
        pass
    return d


class Plan(unittest.TestCase):
    BBOX = (-2.0, -2.0, 42.0, 28.0)          # metres at scale 0.04

    def test_two_rooms_split_by_a_doorway(self):
        d = room_doc()
        out = plan.extract(d, self.BBOX, [64], scale=0.04, res=0.25, erode_m=0.75, min_area=10, cell=4.0)
        self.assertEqual(out["blobs"], 2)
        self.assertEqual({r["blob"] for r in out["rooms"]}, {1, 2})
        self.assertEqual(out["walls"]["world"], 6)

    def test_open_wall_leaks_without_a_seal_and_not_with_one(self):
        d = room_doc(gap=True)
        leaky = plan.extract(d, self.BBOX, [64], scale=0.04, seal_m=0.0, min_area=10)
        sealed = plan.extract(d, self.BBOX, [64], scale=0.04, seal_m=0.75, min_area=10)
        self.assertEqual(leaky["rooms"], [])                  # the outside came in through the gap
        self.assertGreaterEqual(sealed["blobs"], 2)
        self.assertGreater(sealed["plan_m2"], 100)

    def test_wall_sources_entities_rects_and_props(self):
        d = room_doc()
        R = plan.Raster(self.BBOX, 0.25)
        n = plan.walls(d, R, 0.04, [64], wall_rects=[(0, 0, 100, 100)], wall_props={"fence": (200, 16)})
        self.assertEqual(n["rects"], 1)
        d["static_props"] = [{"model": "models/props/fence01.mdl", "origin": [480, 320, 0], "angles": [0, 0, 0]},
                             {"model": "models/props/tree.mdl", "origin": [0, 0, 0], "angles": [0, 0, 0]}]
        R = plan.Raster(self.BBOX, 0.25)
        self.assertEqual(plan.walls(d, R, 0.04, [64], wall_props={"fence": (200, 16)})["props"], 1)
        # a brush entity counts only when its class is named (synth's brush entity is a func_door)
        d2 = doc_of(boxes=((0, 0, 0, 16, 16, 128),), entity_box=(0, 100, 0, 16, 200, 128))
        R = plan.Raster(self.BBOX, 0.25)
        self.assertEqual(plan.walls(d2, R, 0.04, [64])["entities"], 0)
        R = plan.Raster(self.BBOX, 0.25)
        self.assertEqual(plan.walls(d2, R, 0.04, [64], wall_classes=("func_door",))["entities"], 1)

    def test_short_brushes_are_not_walls(self):
        d = doc_of(boxes=((0, 0, 0, 100, 100, 30),))
        R = plan.Raster(self.BBOX, 0.25)
        self.assertEqual(plan.walls(d, R, 0.04, [10])["world"], 0)

    def test_primitives(self):
        nx = ny = 9
        m = bytearray(nx * ny)
        for j in range(2, 7):
            for i in range(2, 7):
                m[j * nx + i] = 1
        self.assertEqual(sum(plan.erode(m, nx, ny, 1)), 9)              # the 3x3 core of a 5x5 square
        self.assertEqual(sum(plan.erode(m, nx, ny, 2)), 1)
        self.assertEqual(sum(plan.erode(m, nx, ny, 3)), 0)
        self.assertEqual(plan.label(m, nx, ny)[1], 1)
        grown = plan.dilate(m, nx, ny, 1, None)
        self.assertEqual(sum(grown), 25 + 20)
        self.assertEqual(sum(plan.erode(bytearray([1] * 16), 4, 4, 1)), 4)  # the raster's edge counts as empty

    def test_ascii_plan(self):
        txt = plan.ascii_plan(room_doc(), self.BBOX, [64], scale=0.04)
        rows = txt.splitlines()
        self.assertTrue(all(len(r) == len(rows[0]) for r in rows))
        self.assertIn("#", txt)
        self.assertIn(".", txt)


def make_gma(path, files):
    out = b"GMAD" + bytes([3]) + struct.pack("<QQ", 0, 0) + b"\0" + b"test\0" + b"{}\0" + b"x\0" + struct.pack("<i", 1)
    for i, (name, data) in enumerate(files, 1):
        out += struct.pack("<I", i) + name.encode() + b"\0" + struct.pack("<qI", len(data), zlib.crc32(data) & 0xFFFFFFFF)
    out += struct.pack("<I", 0)
    for _, data in files:
        out += data
    out += struct.pack("<I", zlib.crc32(out) & 0xFFFFFFFF)
    open(path, "wb").write(out)


@unittest.skipUnless(gma.find_fastgmad(), "fastgmad is not installed")
class Gma(unittest.TestCase):
    def test_maps_inside_a_gma(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "addon.gma")
            bs = synth.build()
            make_gma(p, [("maps/dr_test.bsp", bs), ("lua/autorun/x.lua", b"print(1)"), ("materials/a.vmt", b"x")])
            self.assertEqual([(m, len(d)) for m, d in gma.read_bsps(p)], [("maps/dr_test.bsp", len(bs))])
            found = sources.find([p])
            self.assertEqual([s.name for s in found], ["dr_test"])
            self.assertEqual(found[0].read(), bs)
            self.assertEqual(os.listdir(t), ["addon.gma"])                  # nothing left behind
            out = os.path.join(t, "o.json")
            self.assertEqual(cli.main(["bsp.py", "convert", p, "--out", out, "--author", "a", "--page", "p"]), 0)
            self.assertEqual(json.load(open(out))["source"]["name"], "dr_test")

    def test_a_directory_listing_includes_gma_and_survives_a_bad_one(self):
        with tempfile.TemporaryDirectory() as t:
            make_gma(os.path.join(t, "a.gma"), [("maps/dr_a.bsp", synth.build())])
            open(os.path.join(t, "bad.gma"), "wb").write(b"not an archive")
            self.assertEqual([s.name for s in sources.find([t])], ["dr_a"])

    def test_path_traversal_member_is_not_followed(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "evil.gma")
            make_gma(p, [("maps/../../escape.bsp", b"x")])
            try:
                gma.read_bsps(p)
            except gma.GmaError:
                pass
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(t), "escape.bsp")))

    def test_missing_fastgmad_exits_nonzero_in_list_and_convert(self):
        import contextlib, io
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "a.gma")
            make_gma(p, [("maps/dr_a.bsp", synth.build())])
            old = {k: os.environ.get(k) for k in ("PATH", "DOTBSP_FASTGMAD", "HOME")}
            try:
                os.environ["PATH"], os.environ["HOME"] = "/nonexistent", "/nonexistent"
                os.environ.pop("DOTBSP_FASTGMAD", None)
                for argv in (["bsp.py", "list", t], ["bsp.py", "list", p], ["bsp.py", "convert", p, "--out", os.path.join(t, "o.json")]):
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        self.assertEqual(cli.main(argv), 2, argv)
                    self.assertIn("fastgmad", err.getvalue())
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    def test_missing_fastgmad_is_a_clear_error(self):
        old = os.environ.get("PATH"), os.environ.get("DOTBSP_FASTGMAD"), os.environ.get("HOME")
        try:
            os.environ["PATH"], os.environ["HOME"] = "/nonexistent", "/nonexistent"
            os.environ.pop("DOTBSP_FASTGMAD", None)
            with self.assertRaises(gma.GmaError) as cm:
                gma.read_bsps("x.gma")
            self.assertIn("fastgmad", str(cm.exception))
        finally:
            for k, v in zip(("PATH", "DOTBSP_FASTGMAD", "HOME"), old):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
