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

    def test_generated_texture_is_deterministic_and_a_png(self):
        a, b = textures.generate("carpet", [0.2, 0.3, 0.8]), textures.generate("carpet", [0.2, 0.3, 0.8])
        self.assertEqual(a, b)
        self.assertTrue(a.startswith(b"\x89PNG"))
        self.assertNotEqual(a, textures.generate("carpet", [0.8, 0.3, 0.2]))


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
        self.assertIsNone(importer._safe("../etc/passwd"))
        self.assertIsNone(importer._safe("c:/x"))
        self.assertEqual(importer._safe("\\materials\\a.vtf"), "materials/a.vtf")

    def test_shipped_map_has_only_free_textures(self):
        with tempfile.TemporaryDirectory() as out:
            doc, problems = importer.ship(load(), "t", os.path.join(out, "t"), allow_unknown=True,
                                          prop_table=props.PropTable({"models/props_c17/chair.mdl": "chair"}))
            self.assertEqual(problems, [])
            self.assertTrue(all("free" in s for s in doc["surfaces"]))
            self.assertTrue(all(t["licence"] in licence.ALLOWED for t in doc["licence"]["textures"]))
            unknown = [t for t in doc["licence"]["textures"] if "zz_unknown/never_heard_of_it" in t["sources"]]
            self.assertEqual(unknown[0]["generic"], "flat")           # an unmapped name still gets a free image
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
