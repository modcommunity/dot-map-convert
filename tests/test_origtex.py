"""Original textures of an _orig pack: pakfile first, base game second, missing listed; internal marking."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotbsp import origtex, vtf  # noqa: E402
from test_vpk import vtf_rgba  # noqa: E402


class FakeBsp:
    def __init__(self, pak):
        self.pak = pak

    def read_pak(self, notes, only=None):
        return self.pak


class NoGame:
    def __bool__(self):
        return False


class Cache:
    game = True

    def png(self, name):
        return b"PNGBASE" if name == "concrete/concretefloor001a" else None


class OrigTex(unittest.TestCase):
    def test_pak_then_base_then_missing(self):
        pak = {"materials/maps/m/wall.vmt": b'"LightmappedGeneric"\n{\n"$basetexture" "maps/m/wall"\n}\n',
               "materials/maps/m/wall.vtf": vtf_rgba()}
        doc = {"surfaces": [{"material": "maps/m/wall"}, {"material": "concrete/concretefloor001a"}, {"material": "nodraw/x"}]}
        with tempfile.TemporaryDirectory() as d:
            rec = origtex.ship(doc, FakeBsp(pak), d, cache=Cache())
            self.assertEqual((rec["from_pak"], rec["from_base"]), (1, 1))
            self.assertTrue(rec["internal_only"])
            self.assertEqual(rec["missing"], ["nodraw/x"])
            self.assertTrue(os.path.isfile(os.path.join(d, doc["surfaces"][0]["orig"])))
            self.assertNotIn("orig", doc["surfaces"][2])
            with open(os.path.join(d, doc["surfaces"][1]["orig"]), "rb") as f:
                self.assertEqual(f.read(), b"PNGBASE")

    def test_full_size_unless_capped(self):
        # Two mips, smallest stored first: 4x4 then 8x8.
        head = bytearray(vtf_rgba(8, 8)[:80])
        head[56] = 2
        data = bytes(head) + bytes((1, 2, 3, 255)) * 16 + bytes((200, 40, 40, 255)) * 64
        self.assertEqual(vtf.read(data, 0)[:2], (8, 8))
        self.assertEqual(vtf.read(data, 4)[:2], (4, 4))
        pak = {"materials/w.vtf": data}
        self.assertEqual(origtex.pak_material(pak, "w")[:2], (8, 8))
        self.assertEqual(origtex.pak_material(pak, "w", 4)[:2], (4, 4))

    def test_only_orig_names(self):
        self.assertTrue(origtex.is_orig_name("bhop_amor_orig"))
        self.assertFalse(origtex.is_orig_name("bhop_amor"))


if __name__ == "__main__":
    unittest.main()
