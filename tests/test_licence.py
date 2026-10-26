"""The licence pass, the raw store, and the environment and sound data.
Run: python3 -I tools/bsp/tests/test_licence.py
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                              # noqa: E402
from dotbsp import environment, importer, licence, props, reader, texturemap, textures  # noqa: E402

ENTS = [{"classname": "worldspawn", "skyname": "sky_day01"},
        {"classname": "light_environment", "origin": "0 0 100", "pitch": "-45", "angles": "0 90 0",
         "_light": "255 240 200 300", "_ambient": "100 120 140 50"},
        {"classname": "env_fog_controller", "fogenable": "1", "fogcolor": "100 150 200", "fogstart": "500", "fogend": "2000"},
        {"classname": "env_cubemap", "origin": "10 20 30", "cubemapsize": "6"},
        {"classname": "ambient_generic", "message": "Ambient\\Wind_Loop.wav", "health": "5", "radius": "1000",
         "origin": "0 0 0", "spawnflags": "16"},
        {"classname": "env_soundscape", "soundscape": "Streets.Quiet", "radius": "512", "origin": "5 5 5"},
        {"classname": "prop_physics", "model": "models/Props_c17/Chair.mdl", "origin": "8 8 8"},
        {"classname": "info_player_terrorist", "origin": "16 16 1"}]
MATS = ("concrete/concretefloor001", "carpet/hall_carpet_blue", "zz_unknown/never_heard_of_it")


def load():
    return reader.Bsp("t.bsp", data=synth.build(entities=ENTS, materials=MATS, faces=True)).load()


class Environment(unittest.TestCase):
    def test_sun_fog_sky_and_probes(self):
        e = environment.environment(load())
        self.assertEqual(e["sky"]["name"], "sky_day01")
        self.assertEqual(e["sun"]["pitch"], -45.0)
        self.assertEqual(e["sun"]["colour"][:3], [1.0, 0.9412, 0.7843])
        self.assertAlmostEqual(e["fog"][0]["end"], 2000 * 0.01905, 3)
        self.assertTrue(e["fog"][0]["enabled"])
        self.assertEqual(len(e["cubemaps"]), 1)

    def test_sound_is_data_with_an_empty_stand_in(self):
        s = environment.sounds(load())
        a = s["ambient"][0]
        self.assertEqual((a["message"], a["volume"], a["start_silent"], a["looped"], a["stand_in"]),
                         ("Ambient/Wind_Loop.wav", 0.5, True, True, ""))
        self.assertEqual(s["soundscapes"][0]["soundscape"], "Streets.Quiet")
        self.assertIn("ambient/wind_loop.wav", s["files"])


class Free(unittest.TestCase):
    def test_every_generic_id_has_a_free_row(self):
        table = licence.load()
        ids = {r.material for r in texturemap.load().rows}
        self.assertEqual(sorted(i for i in ids if i not in table), [])
        for g, r in table.items():
            self.assertIn(r["licence"], licence.ALLOWED, g)
            if r["kind"] != "generated":
                self.assertTrue(os.path.isdir(os.path.join(HERE, "..", "..", "..", "addons", "dot_map", "surfaces", r["kind"])), g)

    def test_photo_sets_are_complete_and_credited(self):
        root = os.path.join(HERE, "..", "..", "..", "addons", "dot_map", "surfaces")
        credits = open(os.path.join(root, "CREDITS.md")).read()
        for r in licence.load().values():
            if r["kind"] == "generated":
                continue
            for f in ("albedo.jpg", "normal.jpg", "roughness.jpg"):
                self.assertTrue(os.path.isfile(os.path.join(root, r["kind"], f)), (r["kind"], f))
            self.assertIn("| %s |" % r["kind"], credits)
            self.assertIn(r["url"], credits)

    def test_carpet_and_snow_names_choose_a_photo(self):
        from dotbsp import nearest
        self.assertEqual(nearest.by_name("de_chateau/carpet01"), "carpet_grey")
        self.assertEqual(nearest.by_name("nature/snowfloor001"), "snow")
        self.assertIsNone(nearest.by_name("props/drugstore"))

    def test_generated_texture_is_deterministic_and_a_png(self):
        a, b = textures.generate("carpet", [0.2, 0.3, 0.8]), textures.generate("carpet", [0.2, 0.3, 0.8])
        self.assertEqual(a, b)
        self.assertTrue(a.startswith(b"\x89PNG"))
        self.assertNotEqual(a, textures.generate("carpet", [0.8, 0.3, 0.2]))


class Defects(unittest.TestCase):
    def test_skybox_model_is_recognised(self):
        from dotbsp import standins
        self.assertFalse(standins.is_skybox("models/props/crate.mdl"))
        for ok in ("models/props/sky_scraper01.mdl", "models/props/de_sky_sign.mdl", "models/props/sky_cube.mdl"):
            self.assertFalse(standins.is_skybox(ok), ok)
        for sky in ("models/props/skybox/city.mdl", "models/sky/tree.mdl", "models/props/skybox_tower.mdl"):
            self.assertTrue(standins.is_skybox(sky), sky)

    def test_size_classes_by_name(self):
        from dotbsp import standins
        sz = standins.Sizes()
        small = {"props_junk/popcan01a.mdl": 0.13, "props_junk/garbage_can01a.mdl": None, "props_junk/trashcan01a.mdl": None,
                 "props_junk/bottle001a.mdl": 0.28, "props_junk/beach_ball01.mdl": None, "props_junk/wrecking_ball01.mdl": None,
                 "props_street/phone_booth01.mdl": None, "props_c17/phone01a.mdl": 0.15, "props_junk/ball001a.mdl": 0.1,
                 "props_c17/storage_w_shelf01.mdl": None, "props_street/food_stand01.mdl": None, "props_junk/food01.mdl": 0.25,
                 "weapons/w_pistol.mdl": 0.25, "props_junk/watermelon01.mdl": 0.22, "props/cup01.mdl": 0.1}
        for name, want in small.items():
            self.assertEqual(sz.get(name), want, name)

    def test_shape_match_neutral_blocks_only(self):
        from dotbsp import standins
        cat = standins.ShapeCatalogue()
        props_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "addons", "dot_map", "props")
        for cid in cat.dims:
            self.assertTrue(os.path.exists(os.path.join(props_dir, cid + ".glb")), cid)
            self.assertIn(cid, cat.rows, cid)                       # a credit row to ship with it
        self.assertEqual(cat.match([0.6, 0.9, 0.6])[0], "barrel")
        self.assertEqual(cat.match([0.5, 0.5, 0.5])[0], "crate")
        self.assertIsNone(cat.match([0.02, 0.02, 0.02]))             # a decal
        self.assertIsNone(cat.match([8.0, 3.0, 8.0]))                # a building
        self.assertIsNone(cat.match([2.4, 0.4, 2.4]))                # a flat truss
        self.assertIsNone(cat.match([0.1, 2.0, 1.9]))                # a wall decal

    def test_shape_match_turns_to_the_long_side(self):
        from dotbsp import standins
        cat = standins.ShapeCatalogue()
        # crate_large is long on its z; after the viewer's 90 degrees that is the source's x
        self.assertEqual(cat.match([1.0, 0.5, 0.5]), ("crate_large", 0))
        self.assertEqual(cat.match([0.5, 0.5, 1.0]), ("crate_large", 1))

    def test_a_library_placement_carries_its_measured_box(self):
        from dotbsp import standins
        k = 1 / 0.01905
        packed = {"models/x/shelf.mdl": {"size": [1.0, 1.5, 0.4], "centre": [0.0, 0.75, 0.0], "min": [-0.5, 0.0, -0.2]}}
        pick = {"stand_in": "lib/ph_shelf", "turns": 0, "size": 1.5, "centre": [0.0, 0.0, 0.0], "base": 0.0, "row": None}
        shaped = {"models/x/shelf.mdl": pick, "models/x/stock.mdl": dict(pick)}
        spots = [("models/x/shelf.mdl", [k, 0, 0], [0, 90, 0], None, 6), ("models/x/shelf.mdl", [2 * k, 0, 0], [0, 0, 0], None, 0),
                 ("models/x/stock.mdl", [3 * k, 0, 0], [0, 0, 0], None, 0)]
        solid, loose, stock = standins._shaped_placements(spots, shaped, 0.01905, 0.0, packed=packed)
        self.assertEqual(solid["collide"]["box"], [1.0, 1.5, 0.4])
        self.assertNotIn("bounds", solid)                            # collide is already the box a client draws
        self.assertEqual(loose["bounds"]["box"], [1.0, 1.5, 0.4])     # drawn when the model is missing, never collided
        self.assertNotIn("collide", loose)
        self.assertNotIn("bounds", stock)                            # no measure anywhere: nothing to draw

    def test_a_thing_resting_on_a_packed_model_gets_a_block_of_its_size(self):
        from dotbsp import standins
        k = 1 / 0.01905
        # a 1.8 x 0.7 x 0.6 m table at the origin (its z runs 0 to -0.6), a bottle on top, a bottle on the floor
        packed = {"models/x/tbl.mdl": {"size": [1.8, 0.7, 0.6], "centre": [0.0, 0.35, -0.3], "min": [-0.9, 0.0, -0.6]}}
        spots = [("models/x/tbl.mdl", [0, 0, 0], [0, 0, 0], None, 0),
                 ("models/x/bottle.mdl", [0.1 * k, 0.3 * k, 0.7 * k], [0, 0, 0], None, 0)]
        got = standins._support_boxes(spots, packed, None, 0.01905, 0.0)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["box"], [1.8, 0.7, 0.6])
        self.assertAlmostEqual(got[0]["at"][1], 0.35, places=3)
        floor = spots[:1] + [("models/x/bottle.mdl", [0.1 * k, 0.3 * k, 0.0], [0, 0, 0], None, 0)]
        self.assertEqual(standins._support_boxes(floor, packed, None, 0.01905, 0.0), [])
        far = spots[:1] + [("models/x/bottle.mdl", [3.0 * k, 0.3 * k, 0.7 * k], [0, 0, 0], None, 0)]
        self.assertEqual(standins._support_boxes(far, packed, None, 0.01905, 0.0), [])

    def test_natural_stand_ins_take_a_packed_models_size_and_base(self):
        from dotbsp import standins
        tree = {"size": [11.0, 5.0, 8.8], "min": [-7.5, 0.0, -4.7]}
        rec = {"stand_in": "tree", "at": [1.0, 2.0, 3.0]}
        standins._fit_natural(rec, tree, None)
        self.assertEqual(rec["size"], 5.0)                          # height: a wide crown is not a taller tree
        rock = {"stand_in": "rock", "at": [0.0, 1.0, 0.0]}
        standins._fit_natural(rock, {"size": [15.5, 7.1, 7.8], "min": [-7.7, 0.0, -3.9]}, None)
        self.assertEqual(rock["size"], 15.5)
        palm = {"stand_in": "pirate/palm", "at": [0.0, 10.0, 0.0]}
        standins._fit_natural(palm, {"size": [7.2, 14.2, 7.6], "min": [-3.6, -3.59, -3.8]}, 2.0)
        self.assertAlmostEqual(palm["at"][1], 10.0 - 7.18)                # origin mid-trunk: stood on its own base
        chair = {"stand_in": "chair", "at": [0.0, 0.0, 0.0]}
        standins._fit_natural(chair, {"size": [2.0, 2.0, 2.0], "min": [0, 0, 0]}, None)
        self.assertNotIn("size", chair)                             # furniture keeps its stand-in's own size
        none = {"stand_in": "tree", "at": [0.0, 0.0, 0.0]}
        standins._fit_natural(none, None, None)
        self.assertNotIn("size", none)                              # a stock model cannot be measured
        sprite = {"stand_in": "tree", "at": [0.0, 0.0, 0.0]}
        standins._fit_natural(sprite, {"size": [0.01, 0.01, 0.01], "min": [0, 0, 0]}, None)
        self.assertNotIn("size", sprite)
        sz = standins.Sizes()
        self.assertIsNone(sz.get("plants/bananatree.mdl"))          # a banana tree is not a banana
        self.assertEqual(sz.get("props/banana01.mdl"), 0.1)

    def test_carparts_have_sizes(self):
        from dotbsp import standins
        sz, fm = standins.Sizes(), standins.models()
        self.assertEqual(sz.get("props_vehicles/carparts_wheel01a.mdl"), 0.8)
        self.assertEqual(fm.get("props_vehicles/carparts_wheel01a")["stand_in"], "barrel")
        self.assertEqual(fm.get("props_vehicles/carparts_door01a")["stand_in"], "crate")
        self.assertEqual(fm.get("props_vehicles/car001a")["stand_in"], "vehicles/sedan")

    def test_junk_and_light_names_have_stand_ins_and_effects_are_left_out(self):
        from dotbsp import standins
        fm, sz = standins.models(), standins.Sizes()
        self.assertEqual(fm.get("props_junk/glassbottle01a.mdl")["stand_in"], "pirate/bottle")
        self.assertEqual(fm.get("props/de_nuke/wall_light.mdl")["stand_in"], "ceiling_light")
        self.assertEqual(fm.get("props_junk/shoe001a.mdl")["stand_in"], "cardboard_box")
        self.assertEqual(sz.get("props_junk/shoe001a.mdl"), 0.22)
        for m in ("effects/vol_light64x128.mdl", "humans/charple02.mdl", "props_vents/vent_medium_grill002.mdl",
                  "props_buildings/buildingskybox_002a.mdl", "props_furniture/picture_frame8.mdl"):
            self.assertTrue(standins.is_skybox(m) or standins.is_detail(m), m)
        self.assertFalse(standins.is_detail("props_c17/furniturechair001a.mdl"))

    def test_measured_block_for_a_packed_model_no_stand_in_fits(self):
        from dotbsp import standins
        self.assertTrue(standins._box_ok("models/propper/x/widget.mdl", [0.3, 0.6, 0.4]))
        self.assertFalse(standins._box_ok("models/propper/x/ceilinglamp.mdl", [0.3, 0.6, 0.4]))    # hung: would shade the room
        self.assertFalse(standins._box_ok("models/propper/x/poster.mdl", [1.2, 0.8, 0.01]))        # a decal
        self.assertFalse(standins._box_ok("models/propper/x/hall.mdl", [9.0, 3.0, 6.0]))           # a building
        rec = standins._box_record("models/a/b.mdl", [100.0, 200.0, 50.0], [0, 90, 0], 1.0,
                                   {"dims": [0.3, 0.6, 0.4], "centre": [0.0, 0.3, 0.0]}, 0.01905, 0.0)
        self.assertEqual(rec["box"], [0.3, 0.6, 0.4])
        self.assertAlmostEqual(rec["at"][1], 50 * 0.01905 + 0.3, 3)

    def test_unmeasured_stock_debris_is_not_drawn(self):
        from dotbsp import standins
        self.assertTrue(standins.UNMEASURED_DEBRIS.search("models/props_debris/walldestroyed08a.mdl"))
        self.assertFalse(standins.UNMEASURED_DEBRIS.search("models/props_c17/oildrum001a.mdl"))

    def test_black_name_keeps_dark_colour(self):
        self.assertLess(licence.name_colour("tools/black")[0], 0.1)
        self.assertGreater(licence.name_colour("metal/white")[0], 0.8)


class Import(unittest.TestCase):
    def test_raw_store_is_outside_the_repo_and_plain(self):
        with tempfile.TemporaryDirectory() as root:
            d = importer.store_raw(load(), "t", "zz", root=root)
            self.assertEqual(d, os.path.join(root, "zz", "raw", "t"))
            for f in ("mesh.json", "mesh.bin", "intermediate.json", "census.json", "entities.json", "SOURCE.txt"):
                self.assertTrue(os.path.exists(os.path.join(d, f)), f)
            with open(os.path.join(d, "mesh.json")) as f:
                raw = json.load(f)
            self.assertNotIn("licence", raw)                      # plain: nothing replaced yet
            self.assertIn("concrete/concretefloor001", {s["material"] for s in raw["surfaces"]})
            self.assertIn("sounds", raw)

    def test_raw_names_cannot_escape(self):
        for bad in ("..", "a/b", "", "x y"):
            with self.assertRaises(ValueError):
                importer.raw_dir("zz", bad, "/tmp")
        self.assertTrue(importer.raw_dir("hideseek", "ph_hotel~720da13f", "/tmp").endswith("ph_hotel~720da13f"))   # the store's duplicate-name suffix
        self.assertIsNone(importer._safe("../etc/passwd"))
        self.assertIsNone(importer._safe("c:/x"))
        self.assertEqual(importer._safe("\\materials\\a.vtf"), "materials/a.vtf")

    def test_pak_view_reads_a_zip_in_place(self):
        import io, zipfile
        from dotbsp import reader
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("a.vmt", "x" * 50)
            z.writestr("b.mdl", "y" * 50)
        blob = b"junk" + b.getvalue() + b"tail"
        z = zipfile.ZipFile(reader._View(blob, 4, len(b.getvalue())))
        self.assertEqual(sorted(z.namelist()), ["a.vmt", "b.mdl"])
        self.assertEqual(z.read("b.mdl"), b"y" * 50)

    def test_hard_models_have_stand_ins_or_are_left_out(self):
        from dotbsp import standins
        fm = standins.models()
        for name, want in (("props/de_piranesi/pi_apc.mdl", "vehicles/truck"), ("spongebob/ketchup.mdl", "food/bottle-ketchup"),
                           ("johny-srka/arcade_machine.mdl", "arcade/arcade-machine"), ("props_c17/trappropeller_engine.mdl", "space/machine_generator"),
                           ("firewavezzmodels/cargocontainer_green.mdl", "watercraft/cargo-container-a"), ("props/cs_office/exit_wall.mdl", "ceiling_light")):
            self.assertEqual(fm.get(name)["stand_in"], want, name)
        for name in ("knight3.mdl", "stegosaurus/stegosaurus.mdl", "props_c17/overhaingcluster_001a.mdl", "props_canal/canalmap001.mdl"):
            self.assertIsNone(fm.get(name), name)
            self.assertTrue(standins.is_detail(name), name)

    def test_model_and_sound_stand_ins_are_free_and_exist(self):
        from dotbsp import standins
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "addons", "dot_map")
        m, s = standins.models(), standins.sounds()
        self.assertEqual(m.get("props/cs_office/sofa.mdl")["stand_in"], "sofa")
        self.assertIsNone(m.get("props_junk/sewer_grate01.mdl"))     # no sensible match: stays a box
        self.assertEqual(s.get("ambient/water/wave2.wav")["stand_in"], "water_run")
        self.assertEqual(s.get("music/dust.mp3")["stand_in"], "")               # music and voices are never replaced
        for rx, row in m.rows:
            self.assertIn(row["licence"], licence.ALLOWED)
            self.assertTrue(os.path.exists(os.path.join(root, "props", row["stand_in"] + ".glb")), row["stand_in"])
        for rx, row in s.rows:
            if row["stand_in"]:
                self.assertIn(row["licence"], licence.ALLOWED)
                if not row["stand_in"].startswith("amb_"):
                    self.assertTrue(os.path.exists(os.path.join(root, "sounds", row["stand_in"] + ".ogg")), row["stand_in"])

    def test_unset_hdr_colour_is_absent(self):
        from dotbsp import environment
        self.assertIsNone(environment._colour("-1 -1 -1 1"))
        self.assertEqual(environment._colour("255 0 0 200"), [1.0, 0.0, 0.0, 200.0])

    def test_unmapped_texture_goes_to_the_nearest_photo(self):
        from dotbsp import nearest
        table = licence.load()
        self.assertEqual(nearest.nearest("custom/brickwall12", None), ("brick", "name"))
        self.assertEqual(nearest.nearest("zz/dawall_07", [0.97, 0.97, 0.96])[1], "colour")
        self.assertEqual(nearest.nearest("zz/qq", [0.0, 0.9, 0.0]), (None, None))          # too far from every photo: flat
        r = licence.replacement(None, [0.5, 0.4, 0.3], table, "custom/rusty_barrel_a")
        self.assertEqual((r["kind"], r["how"], r["licence"]), ("rust", "name", "CC0-1.0"))
        r = licence.replacement(None, [0.0, 0.9, 0.0], table, "zz/qq")
        self.assertEqual((r["kind"], r["generic"]), ("generated", "flat"))

    def test_shipped_map_has_only_free_textures(self):
        with tempfile.TemporaryDirectory() as out:
            doc, problems = importer.ship(load(), "t", os.path.join(out, "t"), allow_unknown=True,
                                          prop_table=props.PropTable({"models/props_c17/chair.mdl": "chair"}))
            self.assertEqual(problems, [])
            self.assertTrue(all("free" in s for s in doc["surfaces"]))
            self.assertTrue(all(t["licence"] in licence.ALLOWED for t in doc["licence"]["textures"]))
            unknown = [t for t in doc["licence"]["textures"] if "zz_unknown/never_heard_of_it" in t["sources"]]
            self.assertIn(unknown[0]["how"], ("colour", "flat"))    # an unmapped name still gets a free image
            for t in doc["licence"]["textures"]:
                if t["kind"] == "generated":
                    self.assertTrue(os.path.exists(os.path.join(out, t["file"])), t["file"])
            self.assertEqual(doc["licence"]["models"], [{"model": "models/props_c17/chair.mdl", "count": 1, "stand_in": "chair"}])
            self.assertTrue(os.path.exists(os.path.join(out, "CREDITS.md")))
            self.assertIn("sky", doc["environment"])
            self.assertEqual(len(doc["sounds"]["ambient"]), 1)

    def test_check_refuses_a_restricted_or_missing_replacement(self):
        with tempfile.TemporaryDirectory() as out:
            doc, _ = importer.ship(load(), "t", os.path.join(out, "t"), allow_unknown=True)
            doc["licence"]["textures"][0]["licence"] = "Valve proprietary"
            self.assertTrue(any("not free" in p for p in licence.check(doc)))
            doc["licence"]["textures"][0]["licence"] = "CC0-1.0"
            doc["surfaces"][0]["free"] = "none"
            self.assertTrue(any("no free replacement" in p for p in licence.check(doc)))
            del doc["licence"]
            self.assertTrue(licence.check(doc))


if __name__ == "__main__":
    unittest.main()
