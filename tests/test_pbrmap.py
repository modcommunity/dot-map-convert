"""The PBR library mapper: name categories, nearest colour in a category, shipping a set.
Run: python3 -I tools/bsp/tests/test_pbrmap.py
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import licence, pbrmap  # noqa: E402

MANIFEST = "\n".join([
    "#h",
    "\t".join(("Bricks1", "ambientCG", "https://x/b1", "A", "CC0-1.0", "bricks", "0.5", "0.3", "0.2", "Bricks1_2K-JPG_Color.jpg,Bricks1_2K-JPG_NormalGL.jpg,Bricks1_2K-JPG_Roughness.jpg,Bricks1_2K-JPG_AmbientOcclusion.jpg")),
    "\t".join(("Bricks2", "ambientCG", "https://x/b2", "A", "CC0-1.0", "bricks", "0.8", "0.8", "0.8", "Bricks2_2K-JPG_Color.jpg,Bricks2_2K-JPG_NormalGL.jpg,Bricks2_2K-JPG_Roughness.jpg")),
    "\t".join(("Metal9", "ambientCG", "https://x/m9", "A", "CC0-1.0", "metal", "0.4", "0.4", "0.4", "Metal9_2K-JPG_Color.jpg,Metal9_2K-JPG_NormalGL.jpg,Metal9_2K-JPG_Roughness.jpg")),
    "\t".join(("pizza_1", "polyhaven", "https://x/p", "B", "CC0-1.0", "", "0.5", "0.5", "0.5", "pizza_1_diff_2k.jpg")),
]) + "\n"


class PbrMap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = self.tmp.name
        with open(os.path.join(self.lib, "manifest.tsv"), "w") as f:
            f.write(MANIFEST)
        d = os.path.join(self.lib, "ambientcg", "Bricks1")
        os.makedirs(d)
        for o in ("Bricks2", "Metal9"):
            os.makedirs(os.path.join(self.lib, "ambientcg", o))
        for fn in ("Bricks1_2K-JPG_Color.jpg", "Bricks1_2K-JPG_NormalGL.jpg", "Bricks1_2K-JPG_Roughness.jpg", "Bricks1_2K-JPG_AmbientOcclusion.jpg"):
            with open(os.path.join(d, fn), "wb") as f:
                f.write(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_name_category(self):
        self.assertEqual(pbrmap.category("brick/brickwall012a"), "brick")
        self.assertEqual(pbrmap.category("metal/metalfloor005a"), "metal")
        self.assertEqual(pbrmap.category("props/metaldoor001"), "metal")
        self.assertEqual(pbrmap.category("zz/qq", "tile_dark"), "tile")
        self.assertIsNone(pbrmap.category("zz/qq"))

    def test_nearest_colour_inside_the_category_and_blocked_sets_left_out(self):
        lib = pbrmap.load_library(self.lib)
        self.assertNotIn("pizza_1", lib)
        self.assertEqual(pbrmap.pick(lib, "brick", (0.52, 0.3, 0.2))["id"], "Bricks1")
        self.assertEqual(pbrmap.pick(lib, "brick", (0.9, 0.9, 0.9))["id"], "Bricks2")
        self.assertEqual(pbrmap.pick(lib, "brick", (0.4, 0.4, 0.4))["id"], "Bricks1")

    def test_ship_copies_the_maps_and_replacement_names_the_file(self):
        out = os.path.join(self.lib, "out")
        pbrmap._cache.clear()
        d = pbrmap.ship("pbr_Bricks1", out, self.lib)
        self.assertEqual(sorted(os.listdir(d)), ["albedo.jpg", "ao.jpg", "normal.jpg", "roughness.jpg"])
        with self.assertRaises(ValueError):
            pbrmap.ship("pbr_Nope", out, self.lib)
        table = {"pbr_Bricks1": {"kind": "pbr", "source": "ambientCG", "url": "u", "author": "A", "licence": "CC0-1.0"}}
        r = licence.replacement("pbr_Bricks1", (0.5, 0.5, 0.5), table)
        self.assertEqual((r["file"], r["how"]), ("pbr/Bricks1", "table"))

    def test_shared_store_writes_a_set_once_per_tier_and_downsizes(self):
        from PIL import Image
        d = os.path.join(self.lib, "ambientcg", "Bricks1")
        for fn in os.listdir(d):
            Image.new("RGB", (1200, 1200), (120, 80, 60)).save(os.path.join(d, fn), "JPEG")
        store = os.path.join(self.lib, "store")
        pbrmap._cache.clear()
        a = pbrmap.ship_shared("pbr_Bricks1", store, "1k", self.lib)
        self.assertEqual(sorted(os.listdir(a)), ["albedo.webp", "ao.webp", "normal.webp", "roughness.webp"])
        with Image.open(os.path.join(a, "albedo.webp")) as im:
            self.assertEqual(im.size, (1024, 1024))
        stamp = os.path.getmtime(os.path.join(a, "albedo.webp"))
        pbrmap.ship_shared("pbr_Bricks1", store, "1k", self.lib)
        self.assertEqual(os.path.getmtime(os.path.join(a, "albedo.webp")), stamp)
        self.assertEqual((pbrmap.tier_for(0.2), pbrmap.tier_for(0.01)), ("2k", "1k"))


if __name__ == "__main__":
    unittest.main()
