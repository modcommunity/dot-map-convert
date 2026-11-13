"""VPK reader and the internal texture cache, on a synthetic archive (no Valve files needed)."""
import os
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from dotbsp import vpk  # noqa: E402


def vtf_rgba(w=4, h=4):
    head = bytearray(80)
    head[0:4] = b"VTF\0"
    struct.pack_into("<IIIHHIH", head, 4, 7, 2, 80, w, h, 0, 1)
    struct.pack_into("<i", head, 52, 0)
    head[56] = 1
    struct.pack_into("<iBB", head, 57, -1, 0, 0)
    return bytes(head) + bytes((200, 40, 40, 255)) * (w * h)


def build(files, split):
    """files {path: bytes}. split: data goes in a numbered part (000) instead of the _dir file."""
    tree, data = b"", b""
    by = {}
    for p, b in files.items():
        folder, leaf = p.rsplit("/", 1) if "/" in p else (" ", p)
        name, ext = leaf.rsplit(".", 1)
        by.setdefault(ext, {}).setdefault(folder, []).append((name, b))
    for ext, folders in by.items():
        tree += ext.encode() + b"\0"
        for folder, items in folders.items():
            tree += folder.encode() + b"\0"
            for name, b in items:
                pre, body = b[:3], b[3:]
                tree += name.encode() + b"\0" + struct.pack("<IHHIIH", zlib.crc32(b), len(pre), 0 if split else vpk.IN_DIR,
                                                            len(data), len(body), 0xFFFF) + pre
                data += body
            tree += b"\0"
        tree += b"\0"
    tree += b"\0"
    head = struct.pack("<III", vpk.SIG, 2, len(tree)) + struct.pack("<IIII", 0 if split else len(data), 0, 0, 0)
    return head + tree + (b"" if split else data), data


class VpkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "basegame")
        os.makedirs(os.path.join(self.root, "hl2"))
        self.files = {"materials/brick/brickwall001a.vmt": b'"LightmappedGeneric"\n{\n"$basetexture" "brick/brickwall001a"\n}\n',
                      "materials/brick/brickwall001a.vtf": vtf_rgba(), "readme.txt": b"hello"}

    def write(self, split):
        d, part = build(self.files, split)
        with open(os.path.join(self.root, "hl2", "hl2_textures_dir.vpk"), "wb") as f:
            f.write(d)
        if split:
            with open(os.path.join(self.root, "hl2", "hl2_textures_000.vpk"), "wb") as f:
                f.write(part)

    def test_reads_both_layouts(self):
        for split in (False, True):
            self.write(split)
            v = vpk.Vpk(os.path.join(self.root, "hl2", "hl2_textures_dir.vpk"))
            for p, b in self.files.items():
                self.assertEqual(v.get(p.upper()), b, (p, split))
            self.assertIsNone(v.get("materials/none.vtf"))

    def test_crc_checked(self):
        self.write(False)
        p = os.path.join(self.root, "hl2", "hl2_textures_dir.vpk")
        raw = bytearray(open(p, "rb").read())
        raw[-1] ^= 0xFF
        open(p, "wb").write(raw)
        with self.assertRaises(vpk.VpkError):
            vpk.Vpk(p).get("readme.txt")

    def test_garbage_refused(self):
        p = os.path.join(self.root, "x_dir.vpk")
        open(p, "wb").write(b"nope" * 8)
        with self.assertRaises(vpk.VpkError):
            vpk.Vpk(p)

    def test_cache_png_and_repo_refusal(self):
        self.write(True)
        g = vpk.BaseGame(self.root)
        self.assertTrue(g)
        c = vpk.TextureCache(g, max_side=8)
        png = c.png("BRICK/BrickWall001a")
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(c.png("brick/brickwall001a"), png)       # second call is the cached file
        self.assertTrue(os.listdir(c.dir))
        self.assertIsNone(c.png("brick/missing"))
        repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        with self.assertRaises(vpk.VpkError):
            vpk.TextureCache(g, cache_dir=os.path.join(repo, "cache"))


if __name__ == "__main__":
    unittest.main()
