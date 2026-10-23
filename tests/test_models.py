"""The packed-model reader: a studio model written from scratch (one triangle, one material), a
DXT1 texture, the glb, shape matching and the pak extraction. Run: python3 -I tools/bsp/tests/test_models.py"""

import json
import os
import struct
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import mdl, models, vtf  # noqa: E402

# A triangle 100 x 50 source units standing on its base, facing +x (normal +x).
POINTS = [(0, 0, 0), (0, 100, 0), (0, 0, 50)]


def make_mdl():
    d = bytearray(1024)
    d[0:4] = b"IDST"
    struct.pack_into("<i", d, 4, 48)
    d[12:12 + 9] = b"crate.mdl"
    # texture 1 at 400, cdmaterials 1 at 480, skin table at 500, one bodypart at 520
    struct.pack_into("<ii", d, 204, 1, 400)
    struct.pack_into("<ii", d, 212, 1, 480)
    struct.pack_into("<iii", d, 220, 1, 1, 500)
    struct.pack_into("<ii", d, 232, 1, 520)
    struct.pack_into("<i", d, 400, 600 - 400)       # name offset relative to the texture record
    d[600:600 + 4] = b"wood"
    struct.pack_into("<i", d, 480, 660)
    cd = b"models\\props\\"
    d[660:660 + len(cd)] = cd
    struct.pack_into("<h", d, 500, 0)
    struct.pack_into("<iiii", d, 520, 0, 1, 0, 536 - 520)   # bodypart: nmodels 1, modelindex
    struct.pack_into("<ii", d, 536 + 72, 1, 700 - 536)      # model: nummeshes, meshindex
    struct.pack_into("<i", d, 536 + 84, 0)                  # vertexindex
    struct.pack_into("<i", d, 700, 0)                       # mesh material 0
    struct.pack_into("<i", d, 700 + 12, 0)                  # vertexoffset
    return bytes(d)


def make_vvd():
    d = bytearray(64 + 48 * 3)
    d[0:4] = b"IDSV"
    struct.pack_into("<i", d, 16, 3)
    struct.pack_into("<iii", d, 48, 0, 0, 64)
    for i, p in enumerate(POINTS):
        struct.pack_into("<3f3f2f", d, 64 + 48 * i + 16, *p, 1, 0, 0, 0.5, 0.5)
    return bytes(d)


def make_vtx():
    d = bytearray(36)
    struct.pack_into("<iihhiiiiii", d, 0, 7, 24, 3, 3, 3, 0, 1, 0, 1, 36)
    body = struct.pack("<ii", 1, 8)                                     # bodypart -> model
    model = struct.pack("<ii", 1, 8)                                    # model -> lod
    lod = struct.pack("<iif", 1, 12, 0.0)                               # lod -> mesh
    mesh = struct.pack("<iiB", 1, 9, 0)                                 # mesh -> strip group
    group_at = len(d) + len(body) + len(model) + len(lod) + len(mesh)
    verts = b"".join(struct.pack("<3BBh3B", 0, 0, 0, 1, i, 0, 0, 0) for i in range(3))
    indices = struct.pack("<3H", 0, 1, 2)
    group = struct.pack("<6iB", 3, 25, 3, 25 + len(verts), 1, 25 + len(verts) + len(indices), 0)
    strip = struct.pack("<iiiihBii", 3, 0, 3, 0, 1, 1, 0, 0)
    return bytes(d) + body + model + lod + mesh + group + verts + indices + strip


def make_vtf(w=4, h=4):
    # DXT1: one block of pure red (565 0xF800) twice, no mips, no thumbnail
    head = bytearray(80)
    head[0:4] = b"VTF\0"
    struct.pack_into("<IIIHHIH", head, 4, 7, 2, 80, w, h, 0, 1)
    struct.pack_into("<i", head, 52, 13)
    head[56] = 1
    struct.pack_into("<iBB", head, 57, -1, 0, 0)
    return bytes(head) + struct.pack("<HHI", 0xF800, 0xF800, 0)


class Models(unittest.TestCase):
    def test_studio_model(self):
        m = mdl.parse(make_mdl(), make_vvd(), make_vtx())
        self.assertEqual(m.triangles(), 1)
        self.assertEqual(m.materials, ["wood"])
        self.assertEqual(m.cdmaterials, ["models/props"])
        lo, hi = m.bounds()
        self.assertAlmostEqual(hi[0] - lo[0], 0.0)
        self.assertAlmostEqual(hi[2] - lo[2], 100 * 0.01905, places=4)   # source y is Godot -z
        self.assertAlmostEqual(hi[1] - lo[1], 50 * 0.01905, places=4)
        self.assertEqual(m.material_paths({"materials/models/props/wood.vmt"}), ["models/props/wood"])

    def test_rejects(self):
        with self.assertRaises(mdl.ModelError):
            mdl.parse(b"x" * 300, b"", b"")
        with self.assertRaises(mdl.ModelError):
            mdl.parse(make_mdl(), make_vvd(), b"\0" * 40)

    def test_glb_is_a_glb(self):
        glb = mdl.to_glb(mdl.parse(make_mdl(), make_vvd(), make_vtx()), {0: vtf.png(1, 1, [(1, 2, 3, 255)])})
        magic, ver, total = struct.unpack_from("<4sII", glb)
        self.assertEqual((magic, ver, total), (b"glTF", 2, len(glb)))
        n = struct.unpack_from("<I", glb, 12)[0]
        doc = json.loads(glb[20:20 + n])
        self.assertEqual(len(doc["meshes"][0]["primitives"]), 1)
        self.assertEqual(doc["images"][0]["mimeType"], "image/png")

    def test_vtf_dxt1(self):
        w, h, px = vtf.read(make_vtf())
        self.assertEqual((w, h, len(px)), (4, 4, 16))
        self.assertEqual(px[0], (255, 0, 0, 255))
        self.assertEqual(vtf.average(px), (1.0, 0.0, 0.0))
        data = vtf.png(w, h, px)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        with self.assertRaises(vtf.TextureError):
            vtf.read(b"nope" * 20)

    def test_vmt(self):
        t = '"LightmappedGeneric"\n{\n\t"$basetexture" "Models\\Props\\Wood" // note\n\t"$translucent" 1\n}\n'
        self.assertEqual(vtf.base_texture(t), "models/props/wood")
        self.assertIsNone(vtf.base_texture('"patch"\n{\n "include" "materials/a.vmt"\n}'))

    def test_convert_and_index(self):
        pak = {"models/props/crate.mdl": make_mdl(), "models/props/crate.vvd": make_vvd(),
               "models/props/crate.dx90.vtx": make_vtx(),
               "materials/models/props/wood.vmt": b'"VertexLitGeneric"\n{\n"$basetexture" "models/props/wood"\n}\n',
               "materials/models/props/wood.vtf": make_vtf()}
        glb, rec = models.convert(pak, "models/props/crate.mdl")
        self.assertTrue(glb.startswith(b"glTF"))
        self.assertEqual(rec["materials"][0]["average"], [1.0, 0.0, 0.0])
        self.assertEqual(rec["triangles"], 1)
        _, bare = models.convert(pak, "models/props/crate.mdl", glb=False)
        self.assertEqual(bare["size"], rec["size"])
        del pak["models/props/crate.vvd"]
        with self.assertRaises(mdl.ModelError):
            models.convert(pak, "models/props/crate.mdl")

    def test_index_file(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(len(models.load_index(t)), 0)
            os.makedirs(os.path.join(t, "models"))
            with open(os.path.join(t, "models", "models.json"), "w") as f:
                json.dump({"models": {"models/a.mdl": {"packed": True, "size": [1, 1, 1]}, "models/b.mdl": {"packed": False}}}, f)
            idx = models.load_index(t)
            self.assertEqual(len(idx), 1)
            self.assertIsNotNone(idx.get("Models\\A.MDL"))
            self.assertIsNone(idx.get("models/b.mdl"))

    def test_shape_match(self):
        cat = {"can": (0.08, 0.12, 0.08), "crate": (0.5, 0.5, 0.5), "plate": (0.27, 0.03, 0.27)}
        self.assertEqual(models.match_size((0.5, 0.52, 0.48), cat), "crate")
        self.assertEqual(models.match_size((0.28, 0.02, 0.26), cat), "plate")
        self.assertEqual(models.match_size((0.12, 0.5, 0.08), cat, limit=0.3), None)   # nothing close
        self.assertEqual(models.match_size((0.25, 0.25, 0.25), cat, scale=2.0), "crate")
        self.assertEqual(models.match_size((1, 1, 1), {"b": (1, 1, 1), "a": (1, 1, 1)}), "a")   # ties: the lower id
        self.assertFalse(models.compatible((0.91, 0.15, 0.91), cat["can"]))   # a flat disc is not a can
        self.assertTrue(models.compatible((0.49, 0.51, 0.61), cat["crate"]))


if __name__ == "__main__":
    unittest.main()
