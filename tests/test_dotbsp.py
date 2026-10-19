"""dotbsp's tests. Run: python3 -I tools/bsp/tests/test_dotbsp.py

Every map here is written by tests/synth.py. Set DOTBSP_TEST_MAPS to a directory of real
.bsp files to also convert each and check the document (slow; not run by default).
"""

import io
import json
import math
import os
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import bsp as cli                                     # noqa: E402
import synth                                          # noqa: E402
from dotbsp import boxes, intermediate, reader, sources  # noqa: E402


def cube_planes(x0, y0, z0, x1, y1, z1):
    return [(1, 0, 0, x1), (-1, 0, 0, -x0), (0, 1, 0, y1), (0, -1, 0, -y0), (0, 0, 1, z1), (0, 0, -1, -z0)]


def corners(x0, y0, z0, x1, y1, z1):
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def turned(pts, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(x * c - y * s, x * s + y * c, z) for x, y, z in pts]


def planes_of(pts_box, deg):
    """The six planes of a box turned `deg` about Z."""
    x0, y0, z0, x1, y1, z1 = pts_box
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    out = []
    for (nx, ny), d in (((1, 0), x1), ((-1, 0), -x0), ((0, 1), y1), ((0, -1), -y0)):
        out.append((nx * c - ny * s, nx * s + ny * c, 0.0, d))
    return out + [(0, 0, 1, z1), (0, 0, -1, -z0)]


class Reader(unittest.TestCase):
    def load(self, **kw):
        return reader.Bsp("t.bsp", data=synth.build(**kw)).load()

    def test_v20(self):
        b = self.load()
        self.assertEqual(b.version, 20)
        self.assertEqual(b.revision, 7)
        self.assertEqual(len(b.brushes), 1)
        self.assertEqual(b.model_brushes(0), {0})
        self.assertEqual(b.entities[0]["skyname"], "sky_test")

    def test_bevel_sides_are_dropped(self):
        b = self.load()
        self.assertEqual(len(b.brush_planes(0)), 6)
        hull = b.brush_hull(0)
        self.assertEqual(sorted(set(tuple(round(v) for v in p) for p in hull)), sorted(corners(0, 0, 0, 64, 64, 64)))

    def test_v19_leaf_size(self):
        b = self.load(version=19, boxes=[(0, 0, 0, 8, 8, 8), (16, 0, 0, 24, 8, 8)])
        self.assertEqual(b.model_brushes(0), {0, 1})

    def test_v21_swapped_directory(self):
        b = self.load(version=21, swapped=True)
        self.assertEqual(b.model_brushes(0), {0})
        self.assertEqual(b.entities[1]["classname"], "info_player_terrorist")

    def test_v21_plain_directory(self):
        self.assertEqual(self.load(version=21).model_brushes(0), {0})

    def test_rejects_other_files(self):
        with self.assertRaises(ValueError):
            reader.Bsp("x", data=b"IBSP" + b"\0" * 2000)
        with self.assertRaises(ValueError):
            reader.Bsp("x", data=b"VBSP")
        bad = bytearray(synth.build())
        bad[4:8] = (29).to_bytes(4, "little")
        with self.assertRaises(ValueError):
            reader.Bsp("x", data=bytes(bad))

    def test_latin1_material(self):
        b = self.load(materials=("customs/Früchte/wall",))
        self.assertEqual(b.side_material(b.brushsides[0])[0], "customs/Früchte/wall")

    def test_no_static_props_or_pak(self):
        b = self.load()
        self.assertEqual(b.static_props(), [])
        self.assertEqual(b.pak_names(), [])

    def test_helpers(self):
        self.assertEqual(reader.entity_vec({"origin": "1 2 3"}), [1.0, 2.0, 3.0])
        self.assertEqual(reader.entity_vec({}, default=(4, 5, 6)), [4, 5, 6])
        self.assertAlmostEqual(reader.entity_yaw({"angles": "0 90 0"}), 90.0)
        self.assertEqual(reader.to_godot((1, 2, 3)), (1, 3, -2))
        ents = reader.parse_entities('{\n"classname" "a"\n"k" "v"\n}\n{\n"classname" "b"\n}\n')
        self.assertEqual([e["classname"] for e in ents], ["a", "b"])


class Boxes(unittest.TestCase):
    def test_axis_box(self):
        out = boxes.decompose(cube_planes(0, 0, 0, 10, 20, 30), corners(0, 0, 0, 10, 20, 30))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["kind"], "box")
        self.assertEqual((out[0]["x"], out[0]["y"], out[0]["z"]), ((0, 10), (0, 20), (0, 30)))

    def test_thin_pane_is_a_box(self):
        out = boxes.decompose(cube_planes(0, 0, 0, 100, 0.25, 50), corners(0, 0, 0, 100, 0.25, 50))
        self.assertEqual([b["kind"] for b in out], ["box"])

    def test_wedge_is_not_a_box(self):
        pts = [(0, 0, 0), (64, 0, 0), (0, 256, 0), (64, 256, 0), (0, 256, 128), (64, 256, 128)]
        self.assertIsNone(boxes.box_in_frame(pts, 0.0, 0.5))

    def test_turned_box(self):
        pts = turned(corners(0, 0, 0, 100, 40, 10), 30)
        out = boxes.decompose(planes_of((0, 0, 0, 100, 40, 10), 30), pts)
        self.assertEqual(len(out), 1)
        b = out[0]
        self.assertAlmostEqual(abs(b["x"][1] - b["x"][0]) * abs(b["y"][1] - b["y"][0]), 4000, delta=5)
        self.assertAlmostEqual(b["z"][1] - b["z"][0], 10, places=3)

    def test_octagon_prism_is_one_box(self):
        r = 50
        ring = [(r * math.cos(math.radians(22.5 + 45 * k)), r * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]
        pts = [(x, y, z) for x, y in ring for z in (0, 100)]
        planes = [(math.cos(math.radians(45 * k)), math.sin(math.radians(45 * k)), 0, r * math.cos(math.radians(22.5)))
                  for k in range(8)] + [(0, 0, 1, 100), (0, 0, -1, 0)]
        out = boxes.decompose(planes, pts)
        self.assertEqual([b["kind"] for b in out], ["prism"])

    def test_prism(self):
        # a triangular column fills half its rectangle: slabs, never the rectangle
        tri = [(0, 0), (100, 0), (0, 100)]
        pts = [(x, y, z) for x, y in tri for z in (0, 50)]
        planes = [(0, -1, 0, 0), (-1, 0, 0, 0), (0.7071, 0.7071, 0, 70.71), (0, 0, 1, 50), (0, 0, -1, 0)]
        out = boxes.decompose(planes, pts)
        self.assertTrue(out)
        self.assertNotIn("prism", [b["kind"] for b in out])
        for b in out:
            self.assertGreaterEqual(b["z"][0], -0.01)
            self.assertLessEqual(b["z"][1], 50.01)

    def test_slope_slabs_follow_the_gradient(self):
        # a wedge rising along +Y: slabs cut along Y, each under the slope
        pts = [(0, 0, 0), (64, 0, 0), (0, 256, 0), (64, 256, 0), (0, 256, 128), (64, 256, 128)]
        planes = [(0, 0, -1, 0), (-1, 0, 0, 0), (1, 0, 0, 64), (0, 1, 0, 256), (0, -0.4472, 0.8944, 0)]
        out = boxes.decompose(planes, pts, slab=32)
        self.assertGreater(len(out), 4)
        for b in out:
            top_y = b["y"][1]
            self.assertLessEqual(b["z"][1], top_y * 0.5 + 0.6)

    def test_ramp_when_asked(self):
        pts = [(0, 0, 0), (64, 0, 0), (0, 256, 0), (64, 256, 0), (0, 256, 128), (64, 256, 128)]
        planes = [(0, 0, -1, 0), (-1, 0, 0, 0), (1, 0, 0, 64), (0, 1, 0, 256), (0, -0.4472, 0.8944, 0)]
        out = boxes.decompose(planes, pts, tilt=True)
        self.assertTrue(any(b["kind"] == "ramp" for b in out), [b["kind"] for b in out])


class Intermediate(unittest.TestCase):
    def doc(self, **kw):
        b = reader.Bsp("t.bsp", data=synth.build(**kw)).load()
        return intermediate.build(b, credit={"author": "someone", "page": "https://example.org/m", "licence": "x",
                                             "no_share_check": "2026-10-19, none", "credit_line": "Map by someone"})

    def test_document(self):
        d = self.doc()
        self.assertEqual(intermediate.check(d), [])
        self.assertEqual(d["format"], intermediate.FORMAT)
        self.assertEqual(d["counts"]["brushes"], 1)
        self.assertEqual(len(d["spawns"]), 2)
        self.assertEqual({s["team"] for s in d["spawns"]}, set(reader.SPAWN_CLASSES[c] for c in
                                                                ("info_player_terrorist", "info_player_counterterrorist")))
        self.assertEqual(len(d["lights"]), 1)
        self.assertEqual(d["brushes"][0]["boxes"][0]["kind"], "box")
        self.assertTrue(d["brushes"][0]["player_solid"])
        self.assertEqual(len(d["brushes"][0]["sides"]), 6)
        json.dumps(d)       # must serialise as is

    def test_credit_carried_through(self):
        c = self.doc()["credit"]
        self.assertEqual(c["author"], "someone")
        self.assertEqual(c["page"], "https://example.org/m")
        self.assertEqual(c["no_share_check"], "2026-10-19, none")
        self.assertEqual(c["credit_line"], "Map by someone")

    def test_brush_entity_moved_by_origin(self):
        d = self.doc(entity_box=(-8, -8, 0, 8, 8, 16), entity_origin=(100, 0, 0))
        door = [b for b in d["brushes"] if b["model"] == 1]
        self.assertEqual(len(door), 1)
        self.assertEqual(door[0]["mins"][0], 92)
        self.assertEqual(door[0]["maxs"][0], 108)
        box = door[0]["boxes"][0]
        self.assertEqual(box["x"], [92, 108])

    def test_check_finds_problems(self):
        d = self.doc()
        d["brushes"][0]["sides"][0]["material"] = 99
        self.assertTrue(intermediate.check(d))
        self.assertTrue(intermediate.check({"format": "other"}))


class Cli(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.main(["bsp.py"] + list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_convert_and_list(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "ze_test.bsp")
            open(p, "wb").write(synth.build())
            with zipfile.ZipFile(os.path.join(t, "surf_zipped.zip"), "w") as z:
                z.writestr("maps/surf_zipped.bsp", synth.build(version=21, swapped=True))
            out = os.path.join(t, "o", "ze_test.json")
            rc, _o, err = self.run_cli("convert", p, "--out", out, "--author", "A", "--page", "https://x")
            self.assertEqual(rc, 0, err)
            d = json.load(open(out))
            self.assertEqual(d["credit"]["author"], "A")
            self.assertEqual(d["source"]["bsp_version"], 20)
            rc, o, err = self.run_cli("--list", t, "--json")
            self.assertEqual(rc, 0)
            rows = {r["name"]: r for r in json.loads(o)["maps"]}
            self.assertEqual(set(rows), {"ze_test", "surf_zipped"})
            self.assertEqual(rows["ze_test"]["target"], "game-zombie-zone")
            self.assertEqual(rows["surf_zipped"]["version"], 21)
            self.assertEqual(rows["surf_zipped"]["entities"], 4)
            rc, o, _ = self.run_cli("list", t, "--markdown")
            self.assertIn("| surf_zipped | game-g2gfast |", o)

    def test_convert_warns_without_credit(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "a.bsp")
            open(p, "wb").write(synth.build())
            rc, _o, err = self.run_cli("convert", p, "--out", os.path.join(t, "a.json"))
            self.assertEqual(rc, 0)
            self.assertIn("no author or page", err)

    def test_converted_and_queue(self):
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(os.path.join(t, "zombie-zone-maps", "maps"))
            json.dump({"maps": [{"id": "ze_test"}]}, open(os.path.join(t, "zombie-zone-maps", "maps.json"), "w"))
            src = os.path.join(t, "in")
            os.makedirs(src)
            for n in ("ze_test", "ze_new"):
                open(os.path.join(src, n + ".bsp"), "wb").write(synth.build())
            rc, o, _ = self.run_cli("list", src, "--json", "--converted", t, "--queue")
            self.assertEqual([r["name"] for r in json.loads(o)["maps"]], ["ze_new"])

    def test_targets(self):
        self.assertEqual(sources.target("bhop_x"), "game-g2gfast")
        self.assertEqual(sources.target("ph_x"), "mg-prop-hunt")
        self.assertIsNone(sources.target("unknown_x"))


@unittest.skipUnless(os.environ.get("DOTBSP_TEST_MAPS"), "set DOTBSP_TEST_MAPS to a folder of real maps")
class RealMaps(unittest.TestCase):
    def test_each(self):
        root = os.environ["DOTBSP_TEST_MAPS"]
        for s in sources.find([root]):
            with self.subTest(map=s.name):
                b = reader.Bsp(s.label(), data=s.read()).load()
                d = intermediate.build(b, name=s.name)
                self.assertEqual(intermediate.check(d), [])
                self.assertGreater(d["counts"]["brushes"], 0)


if __name__ == "__main__":
    unittest.main()
