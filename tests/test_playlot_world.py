"""PLAYLOT adapter: the box document names a world pack built by the mesh route, in the same frame and crop as the boxes."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]
os.environ.setdefault("DOTBSP_PATH", ROOT)

try:
    import synth
    from dotbsp import reader
    # The adapter imports the maps repo's bsp_read, a thin wrapper over dotbsp's reader.
    stub = types.ModuleType("bsp_read")
    stub.Bsp = reader.Bsp
    sys.modules.setdefault("bsp_read", stub)
    spec = importlib.util.spec_from_file_location(
        "playlot_import_bsp", os.path.join(ROOT, "adapters", "playlot-maps", "import_bsp.py"))
    I = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(I)
except ImportError:
    I = None

REGION = ((-5.0, 15.0), (-5.0, 10.0), (-15.0, 5.0))
CFG = {"id": "pgc_t", "name": "T", "blurb": "b", "author": "A",
       "source": "gm_t, https://example.invalid/t", "spawn_at": 0, "region": REGION}


def load(path):
    with open(path) as f:
        return json.load(f)


@unittest.skipIf(I is None, "adapter or numpy did not import")
class PlaylotWorld(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        I.CONFIGS["t"] = dict(CFG)
        # A floor under the spawn and a box far outside the region.
        self.bsp = os.path.join(self.tmp, "t.bsp")
        with open(self.bsp, "wb") as f:
            f.write(synth.build(
                boxes=((0, 0, 0, 512, 512, 16), (2000, 2000, 0, 2100, 2100, 64)), faces=True,
                entities=[{"classname": "worldspawn", "skyname": "sky_day01_01"},
                          {"classname": "info_player_start", "origin": "64 64 17", "angles": "0 90 0"}]))
        os.makedirs(os.path.join(self.tmp, "repo", "maps"))
        self.out = os.path.join(self.tmp, "repo", "maps", "pgc_t.json")

    def tearDown(self):
        I.CONFIGS.pop("t", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_spec_matches_box_frame(self):
        y_off = (17 - 1) * I.S
        spec = I.world_spec(I.CONFIGS["t"], y_off)
        self.assertEqual(spec["pack"], "pg_world_t")
        self.assertEqual(spec["metres_per_unit"], I.S)
        self.assertEqual(spec["offset"], [0.0, round(-y_off, 5), 0.0])
        # The pack frame is the box frame raised by y_off, so only the height bounds move.
        self.assertEqual(spec["crop"], [-5.0, -15.0, 15.0, 5.0, round(-5.0 + y_off, 5), round(10.0 + y_off, 5)])

    def test_no_region_no_crop(self):
        cfg = dict(CFG)
        del cfg["region"]
        self.assertNotIn("crop", I.world_spec(cfg, 0.3))
        self.assertIsNone(I.world_crop(cfg, 0.3))

    def test_whole_is_default(self):
        self.assertNotIn("region", I.config("t"))
        self.assertEqual(I.config("t", whole=False)["region"], REGION)
        doc = I.build(self.bsp, "t")
        self.assertNotIn("crop", doc["world"])
        self.assertEqual(len(doc["boxes"]), 2)   # the far box too: nothing is cut away
        self.assertTrue(doc["unedited"])
        self.assertNotIn("unedited", I.build(self.bsp, "t", whole=False))

    def test_orig_variant_names_and_regen(self):
        cfg = I.config("t", orig=True)
        self.assertEqual(cfg["id"], "pgc_t_orig")
        spec = I.world_spec(cfg, 0.0)
        self.assertEqual(spec["pack"], "pg_world_t_orig")
        _, regen = I.world_commands(self.bsp, cfg, spec, self.tmp, orig_max_side=1024)
        self.assertIn("--orig-textures", regen)
        self.assertEqual(regen[regen.index("--name") + 1], "t_orig")
        self.assertEqual(regen[regen.index("--orig-max-side") + 1], "1024")
        _, plain = I.world_commands(self.bsp, I.config("t"), I.world_spec(I.config("t"), 0.0), self.tmp)
        self.assertNotIn("--orig-textures", plain)
        self.assertIn("--no-omit", regen)              # the unedited map leaves nothing out
        self.assertNotIn("--no-omit", plain)
        _, kept = I.world_commands(self.bsp, I.config("t"), I.world_spec(I.config("t"), 0.0), self.tmp, no_omit=True)
        self.assertIn("--no-omit", kept)

    def test_orig_refuses_course(self):
        self.assertEqual(I.main(["x", self.bsp, "t", "--out=" + self.out, "--orig", "--course", "--no-world"]), 2)

    def test_main_builds_cropped_pack(self):
        rc = I.main(["x", self.bsp, "t", "--course", "--out=" + self.out, "--store=" + os.path.join(self.tmp, "store")])
        self.assertIn(rc, (0, 4), "regen exit code")
        doc = load(self.out)
        world = doc["world"]
        pack = os.path.join(self.tmp, "repo", "maps", "world", world["pack"])
        man = load(os.path.join(pack, "pgc_t.json"))
        self.assertTrue(os.path.isfile(os.path.join(pack, "pgc_t.bin")))
        self.assertTrue(os.path.isfile(os.path.join(pack, "CREDITS.md")))
        self.assertAlmostEqual(man["units"]["metres_per_unit"], world["metres_per_unit"])
        self.assertEqual(man["units"]["y0"], 0.0)
        # The far box is outside the region in both outputs.
        self.assertEqual(len(doc["boxes"]), 1)
        self.assertGreater(man["skipped"].get("crop:face", 0), 0)
        self.assertGreater(man["counts"]["surfaces"], 0)
        self.assertIn("world pack", doc["attribution"])

    def test_no_world_keeps_key_without_pack(self):
        rc = I.main(["x", self.bsp, "t", "--out=" + self.out, "--no-world"])
        self.assertEqual(rc, 0)
        doc = load(self.out)
        self.assertEqual(doc["world"]["pack"], "pg_world_t")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "repo", "maps", "world")))


if __name__ == "__main__":
    unittest.main()
