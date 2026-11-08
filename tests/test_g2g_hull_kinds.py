"""The game-g2gfast importer writes a kind per collision hull (collision.hull_kinds), from the same rule the drawn mesh uses.
Run: python3 -I tests/test_g2g_hull_kinds.py   (DOTBSP_TEST_MAPS=<dir of .bsp> adds real maps)
"""

import os
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "adapters", "game-g2gfast"))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
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
import synth  # noqa: E402
from dotbsp import materials  # noqa: E402

MATS = ("dev/dev_measuregeneric01", "metal/chainlink_fence01", "TOOLS/TOOLSSKYBOX", "TOOLS/TOOLSPLAYERCLIP")


def collide(boxes, box_material, contents=1):
    raw = synth.build(boxes=boxes, materials=MATS, box_material=box_material, contents=contents)
    with tempfile.NamedTemporaryFile(suffix=".bsp", delete=False) as fh:
        fh.write(raw)
    try:
        bsp = bsp_import.Bsp(fh.name).load()
    finally:
        os.unlink(fh.name)
    return bsp_import.build_collision(bsp, [], [])


class Rule(unittest.TestCase):
    def test_kinds(self):
        hk = materials.hull_kind
        self.assertEqual(hk(["DEV/WALL"], 1), "solid")
        self.assertEqual(hk(["TOOLS/TOOLSPLAYERCLIP"], 1), "clip")
        self.assertEqual(hk(["TOOLS/TOOLSSKYBOX"], 1), "sky")
        self.assertEqual(hk(["DEV/WALL"], 0x10000), "clip")
        self.assertEqual(hk(["DEV/WALL"], 0x10000 | 1), "solid")
        self.assertEqual(hk(["DEV/WALL"], 2), "glass")
        self.assertEqual(hk(["DEV/WALL"], 8), "fence")
        self.assertEqual(hk(["METAL/CHAINLINK_FENCE01"], 1), "fence")


class Import(unittest.TestCase):
    def test_hull_kinds_by_index(self):
        boxes = [(0, 0, 0, 64, 64, 64), (200, 0, 0, 264, 64, 64), (400, 0, 0, 464, 64, 64), (600, 0, 0, 664, 64, 64)]
        blob, info, _skipped, _solids = collide(boxes, [0, 1, 2, 3])
        self.assertEqual(info["hull_count"], 4)
        kinds = {k: sorted(v) for k, v in info["hull_kinds"].items()}
        # the hulls come out in merge order, so compare the sets of kinds, and the indexes must partition the non-solid hulls
        self.assertEqual(sorted(kinds), ["clip", "fence", "sky"])
        self.assertEqual(sum(len(v) for v in kinds.values()), 3)
        self.assertEqual(len({i for v in kinds.values() for i in v}), 3)

    def test_blob_is_unchanged_by_kinds(self):
        # the bin layout is the old one: <count><points> per hull, nothing in front
        blob, info, _s, _o = collide([(0, 0, 0, 64, 64, 64)], [0])
        self.assertEqual(struct.unpack_from("<I", blob, 0)[0], 8)
        self.assertEqual(info["hull_kinds"], {})
        self.assertEqual(info["hull_offset"], 0)

    def test_glass_contents(self):
        _b, info, _s, _o = collide([(0, 0, 0, 64, 64, 64)], [0], contents=2)
        self.assertEqual(info["hull_kinds"], {"glass": [0]})

    def test_a_fence_is_not_merged_into_the_wall_beside_it(self):
        # two boxes sharing a face would merge into one hull if they had the same kind
        _b, same, _s, _o = collide([(0, 0, 0, 64, 64, 64), (64, 0, 0, 128, 64, 64)], [0, 0])
        _b, mixed, _s, _o = collide([(0, 0, 0, 64, 64, 64), (64, 0, 0, 128, 64, 64)], [0, 1])
        self.assertEqual(same["hull_count"], 1)
        self.assertEqual(mixed["hull_count"], 2)
        self.assertEqual({k: len(v) for k, v in mixed["hull_kinds"].items()}, {"fence": 1})


@unittest.skipUnless(os.environ.get("DOTBSP_TEST_MAPS"), "DOTBSP_TEST_MAPS not set")
class RealMaps(unittest.TestCase):
    def test_counts_match_the_blob(self):
        d = os.environ["DOTBSP_TEST_MAPS"]
        found = [f for f in sorted(os.listdir(d)) if f.lower().endswith(".bsp")][:3]
        self.assertTrue(found)
        for f in found:
            bsp = bsp_import.Bsp(os.path.join(d, f)).load()
            blob, info, _s, _o = bsp_import.build_collision(bsp, [], [])
            n, off = 0, info["hull_offset"]
            while n < info["hull_count"]:
                off += 4 + 12 * struct.unpack_from("<I", blob, off)[0]
                n += 1
            self.assertEqual(off, info["displacement_vertex_offset"], f)
            idx = [i for v in info["hull_kinds"].values() for i in v]
            self.assertEqual(len(idx), len(set(idx)), f)
            self.assertTrue(all(0 <= i < info["hull_count"] for i in idx), f)


if __name__ == "__main__":
    unittest.main()
