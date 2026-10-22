"""dotbsp.mesh's tests. Run: python3 -I tools/bsp/tests/test_mesh.py

Every map is written by tests/synth.py with `faces=True`, so the drawn faces are known exactly.
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                          # noqa: E402
from dotbsp import classes, mesh, movers, reader, units  # noqa: E402

MATS = ("concrete/concretefloor001", "metal/metalwall001")


def load(**kw):
    kw.setdefault("materials", MATS)
    kw.setdefault("faces", True)
    return reader.Bsp("synth.bsp", data=synth.build(**kw)).load()


def cross(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])


class Build(unittest.TestCase):
    def test_box_is_twelve_triangles_wound_as_stored(self):
        m = mesh.build(load())
        self.assertEqual(m.counts()["triangles"], 12)
        for s in m.surfaces:
            for t in range(0, len(s.index), 3):
                p = [s.verts[s.index[t + k]] for k in range(3)]
                c = cross(p[0][0], p[1][0], p[2][0])
                # clockwise seen from outside in Godot too: the cross points against the normal
                self.assertLess(sum(c[i] * p[0][1][i] for i in range(3)), 0.0)

    def test_axes_scale_and_floor(self):
        m = mesh.build(load(boxes=((0, 0, 0, 100, 200, 50),)), y0=0.5)
        pts = [v[0] for s in m.surfaces for v in s.verts]
        s = units.VISUAL
        self.assertAlmostEqual(max(p[0] for p in pts), 100 * s, places=5)
        self.assertAlmostEqual(max(p[1] for p in pts), 50 * s - 0.5, places=5)   # map z is up
        self.assertAlmostEqual(min(p[2] for p in pts), -200 * s, places=5)       # map y is -z

    def test_normals_are_the_planes(self):
        m = mesh.build(load())
        normals = {tuple(round(c, 3) for c in v[1]) for s in m.surfaces for v in s.verts}
        self.assertEqual(normals, {(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)})

    def test_uv_is_texture_space(self):
        # s = x / 64 and t = -y / 64 (synth's texinfo, 64-texel textures)
        m = mesh.build(load(boxes=((0, 0, 0, 128, 64, 64),)))
        for s in m.surfaces:
            for p, _n, uv in s.verts:
                self.assertAlmostEqual(uv[0], p[0] / units.VISUAL / 64.0, places=3)
                self.assertAlmostEqual(uv[1], p[2] / units.VISUAL / 64.0, places=3)

    def test_generic_ids_from_the_table(self):
        m = mesh.build(load())
        self.assertTrue(all(s.generic for s in m.surfaces), [(s.material, s.generic) for s in m.surfaces])
        self.assertEqual({s.texels[0] for s in m.surfaces}, {64})

    def test_brush_entity_is_offset_and_solid(self):
        bsp = load(entity_box=(-16, -16, -16, 16, 16, 16), entity_origin=(200, 0, 100))
        m = mesh.build(bsp)
        door = [s for s in m.surfaces if s.model == 1]
        self.assertTrue(door and door[0].classname == "func_door")
        xs = [v[0][0] for s in door for v in s.verts]
        self.assertAlmostEqual(min(xs), 184 * units.VISUAL, places=4)
        self.assertEqual(sorted(h["model"] for h in m.hulls), [0, 1])

    def test_illusionary_is_drawn_not_solid_and_hidden_is_neither(self):
        m = mesh.build(load(entity_box=(0, 0, 0, 8, 8, 8), entity_origin=(100, 0, 0), entity_class="func_illusionary"))
        self.assertIn(1, {s.model for s in m.surfaces})
        self.assertNotIn(1, {h["model"] for h in m.hulls})
        m = mesh.build(load(entity_box=(0, 0, 0, 8, 8, 8), entity_origin=(100, 0, 0), entity_class="func_brush",
                            entity_keys={"rendermode": "10"}))
        self.assertNotIn(1, {s.model for s in m.surfaces})
        self.assertEqual(m.skipped["model:func_brush"], 1)

    def test_trigger_is_neither(self):
        m = mesh.build(load(entity_box=(0, 0, 0, 8, 8, 8), entity_origin=(100, 0, 0), entity_class="trigger_hurt"))
        self.assertEqual({s.model for s in m.surfaces}, {0})
        self.assertEqual({h["model"] for h in m.hulls}, {0})

    def test_hull_planes_hold_its_points(self):
        m = mesh.build(load(boxes=((0, 0, 0, 64, 64, 64), (100, 0, 0, 164, 32, 16))), y0=0.25)
        self.assertEqual(len(m.hulls), 2)
        for h in m.hulls:
            self.assertEqual(len(h["points"]), 8)
            for p in h["points"]:
                for pl in h["planes"]:
                    self.assertLessEqual(pl[0] * p[0] + pl[1] * p[1] + pl[2] * p[2], pl[3] + 1e-4)
            c = [sum(p[k] for p in h["points"]) / 8 for k in range(3)]
            self.assertTrue(all(pl[0] * c[0] + pl[1] * c[1] + pl[2] * c[2] < pl[3] for pl in h["planes"]))

    def test_clip_hull_kind(self):
        m = mesh.build(load(materials=("TOOLS/TOOLSPLAYERCLIP",), contents=reader.CONTENTS_PLAYERCLIP))
        self.assertEqual([h["kind"] for h in m.hulls], ["clip"])


class RoundTrip(unittest.TestCase):
    def test_write_read(self):
        m = mesh.build(load(entity_box=(-16, -16, -16, 16, 16, 16), entity_origin=(200, 0, 100)))
        with tempfile.TemporaryDirectory() as d:
            doc = mesh.write(m, os.path.join(d, "w"), credit={"author": "a"}, name="w")
            self.assertEqual(doc["format"], mesh.FORMAT)
            self.assertEqual(os.path.getsize(os.path.join(d, "w.bin")), doc["bin"]["stored_bytes"])
            _doc, back = mesh.read(os.path.join(d, "w"))
        self.assertEqual(back.counts(), m.counts())
        a = sorted(tuple(round(c, 4) for p in t for c in p) for t in m.triangles())
        b = sorted(tuple(round(c, 4) for p in t for c in p) for t in back.triangles())
        self.assertEqual(a, b)


class Fixture(unittest.TestCase):
    def test_the_godot_fixture_is_current(self):
        # examples/bsp_mesh/ is what the Godot suite reads; a format change must rewrite it
        import mesh_fixture
        with tempfile.TemporaryDirectory() as d:
            mesh_fixture.write(os.path.join(d, "fixture"))
            for ext in (".json", ".bin"):
                with open(os.path.join(d, "fixture" + ext), "rb") as a, open(mesh_fixture.OUT + ext, "rb") as b:
                    self.assertEqual(a.read(), b.read(), "run tools/bsp/tests/mesh_fixture.py")


class Coverage(unittest.TestCase):
    def test_full_mesh_is_full(self):
        bsp = load(boxes=((0, 0, 0, 256, 256, 64), (0, 0, 64, 32, 256, 192)))
        m = mesh.build(bsp)
        c = mesh.coverage(bsp, m, per_m2=50.0, solid_samples=500)
        self.assertEqual(c["drawn"], 1.0)
        self.assertEqual(c["solid"], 1.0)
        self.assertTrue(all(v["kept"] == 1.0 for v in mesh.silhouette_diff(bsp, m).values()))

    def test_coverage_sees_a_missing_surface(self):
        bsp = load(boxes=((0, 0, 0, 256, 256, 64), (0, 0, 64, 32, 256, 192)))
        m = mesh.build(bsp)
        m.surfaces = m.surfaces[1:]
        self.assertLess(mesh.coverage(bsp, m, per_m2=50.0, solid_samples=0)["drawn"], 1.0)


class Movers(unittest.TestCase):
    def test_door_travels_its_size_less_lip(self):
        bsp = load(entity_box=(-8, -32, -64, 8, 32, 64), entity_origin=(100, 0, 64),
                   entity_keys={"movedir": "-90 0 0", "lip": "8", "speed": "200", "targetname": "gate"})
        bsp.entities.append({"classname": "func_button", "targetname": "b",
                             "OnPressed": "gate,Open,,0.5,-1\ngate\x1bLock\x1b\x1b0\x1b1"})
        r = [m for m in movers.movers(bsp) if m["classname"] == "func_door"][0]
        self.assertEqual(r["direction"], [0.0, 1.0, -0.0])                  # up, in Godot axes
        self.assertAlmostEqual(r["distance"], (128 - 2 - 8) * units.VISUAL, places=4)
        self.assertAlmostEqual(r["speed"], 200 * units.VISUAL, places=4)
        self.assertEqual([(o["input"], o["delay"]) for o in r["opened_by"]], [("Open", 0.5), ("Lock", 0.0)])

    def test_rotating_axis_flags(self):
        bsp = load(entity_box=(-8, -8, -8, 8, 8, 8), entity_class="func_rotating",
                   entity_keys={"spawnflags": "5", "maxspeed": "90"})
        r = movers.movers(bsp)[0]
        self.assertEqual((r["axis"], r["degrees_per_second"], r["start_on"]), ([1.0, 0.0, -0.0], 90.0, True))

    def test_trigger_is_a_volume_with_planes(self):
        bsp = load(entity_box=(0, 0, 0, 64, 64, 64), entity_class="trigger_hurt", entity_keys={"damage": "500"})
        v = [x for x in movers.volumes(bsp) if x["kind"] == "hurt"][0]
        self.assertEqual(v["damage"], 500.0)
        self.assertEqual(len(v["brushes"][0]), 6)


class Classes(unittest.TestCase):
    def test_every_row_has_a_known_treatment(self):
        self.assertTrue(all(t in classes.TREATMENTS for t, _m in classes.ROWS.values()))

    def test_prefix_and_unknown(self):
        self.assertEqual(classes.treatment("weapon_new_thing")[0:3:2], ("point", "prefix"))
        self.assertIsNone(classes.treatment("made_up_entity")[0])
        bsp = load()
        bsp.entities.append({"classname": "made_up_entity"})
        self.assertEqual(classes.report(bsp)["unknown"], {"made_up_entity": 1})

    def test_the_document_is_current(self):
        # docs/entity-classes.md is written from the table: every row is in it
        with open(os.path.join(os.path.dirname(HERE), "docs", "entity-classes.md")) as f:
            text = f.read()
        missing = [c for c in classes.ROWS if "| `%s` |" % c not in text]
        self.assertEqual(missing, [], "regenerate docs/entity-classes.md (bsp.py classes --markdown)")


if __name__ == "__main__":
    unittest.main()
