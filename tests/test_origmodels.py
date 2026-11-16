"""The map's own models in an _orig pack: tilt variants, facing, re-rooting, sources, licence marking. Synthetic data only."""
import json
import math
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from dotbsp import licence, origmodels as O  # noqa: E402


def _ry(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]


def _source_angles(pitch, yaw, roll):
    """Source's full AngleMatrix (yaw about +Z, then pitch, then roll)."""
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return O._mul([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], O._source_tilt(pitch, roll))


class NoGame:
    def __bool__(self):
        return False


class Game:
    def __init__(self, files):
        self.files, self.asked = files, []

    def get(self, path):
        self.asked.append(path)
        return self.files.get(path)


class OrigModels(unittest.TestCase):
    def test_tilt_quantized(self):
        self.assertEqual(O.tilt([14.0, 33.0, -26.0]), (10.0, -30.0))
        self.assertEqual(O.tilt([0.4, 90.0, 359.0]), (0.0, 0.0))
        self.assertEqual(O.tilt([180.0, 0.0, 0.0]), (-180.0, 0.0))
        self.assertEqual(O.tilt([3.0, 0.0, 0.0], step=0), (3.0, 0.0))
        self.assertEqual(O.variant_name("a.b", 0.0, 0.0), "a.b")
        self.assertEqual(O.variant_name("a.b", 10.0, -20.0), "a.b~p10r-20")

    def test_facing_turns_source_forward_to_plus_z(self):
        f = O._apply(O.node_basis(0.0, 0.0), (1.0, 0.0, 0.0))
        self.assertEqual([round(v, 6) for v in f], [0.0, 0.0, 1.0])

    def test_settle_matches_source_placement(self):
        """A tilted, yawed, scaled prop drawn the runtime's way lands every vertex where Source puts it."""
        scale, y0 = 0.01905, 0.3
        o = (120.0, -340.0, 64.0)
        pitch, yaw, roll, k = 20.0, 37.0, -30.0, 1.5
        verts = [(-10.0, -6.0, 0.0), (30.0, 6.0, 48.0), (5.0, -6.0, 48.0), (30.0, 6.0, 2.0)]        # Source model units
        g = [O._apply(O._M, [c * scale for c in v]) for v in verts]                                  # the glb's (Godot axes)
        lo = [min(p[i] for p in g) for i in range(3)]
        hi = [max(p[i] for p in g) for i in range(3)]
        q = O.node_basis(pitch, roll)
        rec = {"at": [o[0] * scale, o[2] * scale - y0, -o[1] * scale], "yaw": yaw, "scale": k,
               "reroot": O.bottom_centre(q, lo, hi)}
        O.settle([rec])
        self.assertNotIn("reroot", rec)
        c = O.bottom_centre(q, lo, hi)
        turn = _ry(yaw + 90.0)
        for v, gv in zip(verts, g):
            local = [a - b for a, b in zip(O._apply(q, gv), c)]          # the runtime re-roots, then turns and scales
            got = [rec["at"][i] + k * O._apply(turn, local)[i] for i in range(3)]
            w = O._apply(_source_angles(pitch, yaw, roll), v)
            src = [o[i] + k * w[i] for i in range(3)]
            want = [src[0] * scale, src[2] * scale - y0, -src[1] * scale]
            for a, b in zip(got, want):
                self.assertAlmostEqual(a, b, places=3)

    def test_variant_gltf_shares_the_bin(self):
        doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "m"}],
               "meshes": [{"primitives": []}], "buffers": [{"byteLength": 8}]}
        v = O.variant_gltf(doc, "a.b.bin", O.node_basis(10.0, 0.0))
        self.assertEqual(v["buffers"], [{"byteLength": 8, "uri": "a.b.bin"}])
        self.assertEqual(v["scenes"], [{"nodes": [0]}])
        self.assertEqual(v["nodes"][0]["children"], [1])
        self.assertEqual(v["nodes"][1]["mesh"], 0)
        self.assertEqual(len(v["nodes"][1]["matrix"]), 16)
        self.assertNotIn("uri", doc["buffers"][0])              # the shared doc is not changed

    def test_split_glb(self):
        j = json.dumps({"asset": {"version": "2.0"}}).encode()
        j += b" " * (-len(j) % 4)
        b = b"\x01\x02\x03\x04"
        glb = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(j) + 8 + len(b)) + struct.pack("<II", len(j), 0x4E4F534A) + j \
            + struct.pack("<II", len(b), 0x004E4942) + b
        doc, blob = O.split_glb(glb)
        self.assertEqual(doc["asset"]["version"], "2.0")
        self.assertEqual(blob, b)
        j = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"byteLength": 3}]}).encode()
        j += b" " * (-len(j) % 4)
        glb = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(j) + 8 + len(b)) + struct.pack("<II", len(j), 0x4E4F534A) + j \
            + struct.pack("<II", len(b), 0x004E4942) + b
        self.assertEqual(O.split_glb(glb)[1], b[:3])             # the chunk's padding is not written into the .bin

    def test_sources_pak_then_content_then_base(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "Models", "x"))
            with open(os.path.join(d, "Models", "x", "A.mdl"), "wb") as f:
                f.write(b"loose")
            game = Game({"models/x/a.mdl": b"base", "models/x/b.mdl": b"base-b"})
            s = O.Sources({"models/x/c.mdl": b"pak"}, (d,), game)
            self.assertEqual(s.where("models/x/c.mdl"), "pak")
            self.assertEqual(s.where("models/x/a.mdl"), "content")
            self.assertEqual(s["models/x/a.mdl"], b"loose")
            self.assertEqual(s.where("models/x/b.mdl"), "base")
            self.assertIsNone(s.where("models/x/none.mdl"))
            self.assertNotIn("models/x/none.mdl", s)
            self.assertNotIn("models/x/a.mdl", game.asked)
            self.assertIsNone(O.Sources({}, (), NoGame()).where("models/x/b.mdl"))

    def test_merge_and_ship_licence(self):
        with tempfile.TemporaryDirectory() as d:
            lib = os.path.join(d, "lib")
            os.makedirs(os.path.join(lib, "m"))
            with open(os.path.join(lib, "m", "crate.glb"), "wb") as f:
                f.write(b"glb")
            props = [{"model": "models/a.mdl", "stand_in": "lib/crate"}, {"model": "models/b.mdl", "stand_in": "lib/crate"},
                     {"model": "models/c.mdl", "stand_in": "lib/barrel"}]
            recs = [{"model": "models/a.mdl", "stand_in": "lib/orig/a", "at": [0, 0, 0]},
                    {"model": "models/c.mdl", "stand_in": "lib/orig/c", "at": [0, 0, 0]}]
            merged = O.merge(props, recs)
            self.assertEqual([p["stand_in"] for p in merged], ["lib/crate", "lib/orig/a", "lib/orig/c"])
            doc = {"props": merged, "licence": {"model_store": "../lib", "model_stand_ins": [
                {"stand_in": "lib/crate", "store_file": "m/crate.glb"}, {"stand_in": "lib/barrel", "store_file": "m/barrel.glb"}]}}
            rows = [{"stand_in": "lib/orig/a", "internal_only": True}, {"stand_in": "lib/orig/c", "internal_only": True}]
            out = os.path.join(d, "pack")
            block = O.ship_licence(doc, rows, out, lib)
            self.assertEqual(block["model_store"], ".")
            self.assertEqual([r["stand_in"] for r in block["model_stand_ins"]], ["lib/crate", "lib/orig/a", "lib/orig/c"])
            self.assertTrue(os.path.isfile(os.path.join(out, "m", "crate.glb")))

    def test_check_skips_internal_rows_only_in_an_internal_pack(self):
        row = {"stand_in": "lib/orig/a", "source": "the original map", "licence": "internal-only", "url": "", "author": "x", "internal_only": True}
        doc = {"licence": {"textures": [], "model_stand_ins": [row]}, "surfaces": []}
        self.assertEqual(len(licence.check(doc)), 1)
        self.assertIn("not used", licence.credits_markdown(doc))
        doc["original_models"] = {"internal_only": True}
        self.assertEqual(licence.check(doc), [])
        self.assertIn("INTERNAL ONLY", licence.credits_markdown(doc))


if __name__ == "__main__":
    unittest.main()
