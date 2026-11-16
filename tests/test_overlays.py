"""info_overlay decals (lump 45) and dprp detail sprites: read, cut to their faces, and drawn only when asked
(mesh.build overlays= / detail=, regen --overlays / --detail / --no-omit), so a map built without them is unchanged.
Run: python3 -P tests/test_overlays.py
"""

import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from dotbsp import mesh, overlays, reader  # noqa: E402
import synth                                # noqa: E402

MATS = ("dev/dev_measuregeneric01", "OVERLAYS/DARKEDGE")
TOP = 4      # synth's faces per box: +x, -x, +y, -y, +z, -z


def _overlay(texinfo=1, faces=(TOP,), order=0, origin=(32.0, 32.0, 64.0), half=16.0):
    # basis u is map x on an up-facing face, so basis v (normal x u) is map y
    corners = ((-half, -half), (-half, half), (half, half), (half, -half))
    bu = (1.0, 0.0, 0.0)
    pts = b"".join(struct.pack("<3f", c[0], c[1], bu[k] if k < 3 else 0.0) for k, c in enumerate(corners))
    fs = list(faces) + [0] * (64 - len(faces))
    return (struct.pack("<ihH", 0, texinfo, len(faces) | (order << 14)) + struct.pack("<64i", *fs)
            + struct.pack("<4f", 0.0, 1.0, 0.0, 1.0) + pts + struct.pack("<3f", *origin) + struct.pack("<3f", 0, 0, 1))


def _dprp(origin=(32.0, 32.0, 64.0), yaw=0.0, kind=1):
    data = struct.pack("<i", 0) + struct.pack("<i", 1) + struct.pack("<8f", -8, 16, 8, 0, 0, 0, 1, 1)
    prop = struct.pack("<3f3fHH", *origin, 0.0, yaw, 0.0, 0, 0).ljust(40, b"\0")
    prop += bytes((2, 0, 0, 0, kind, 0, 0, 0)) + struct.pack("<f", 1.0)
    return data + struct.pack("<i", 1) + prop


def load(mats=MATS, **kw):
    ents = [{"classname": "worldspawn", "detailmaterial": "detail/detailsprites"}]
    return reader.Bsp("synth.bsp", data=synth.build(faces=True, materials=mats, box_material=[0], entities=ents,
                                                    **kw)).load()


def _of(m, cls):
    return [s for s in m.surfaces if s.classname == cls]


class Reader(unittest.TestCase):
    def test_overlay_record(self):
        o = load(extra_lumps={45: _overlay(order=2)}).overlays()[0]
        self.assertEqual((o["texinfo"], o["faces"], o["order"]), (1, [TOP], 2))
        self.assertEqual(o["basis_v"], (0.0, 1.0, 0.0))

    def test_detail_record(self):
        sprites, props = load(detail=_dprp(yaw=30.0)).detail_sprites()
        self.assertEqual(len(sprites), 1)
        self.assertEqual((props[0]["type"], props[0]["index"], props[0]["angles"][1]), (1, 0, 30.0))

    def test_none_without_the_lumps(self):
        b = load()
        self.assertEqual((b.overlays(), b.detail_sprites()), ([], ([], [])))


class Geometry(unittest.TestCase):
    def test_clip_keeps_the_overlap(self):
        quad = [(0, 0), (0, 1), (1, 1), (1, 0)]
        got = overlays.clip([(0.5, 0.5, 7.0), (2, 0.5, 7.0), (2, 2, 7.0), (0.5, 2, 7.0)], quad)
        xs = sorted({(round(p[0], 6), round(p[1], 6)) for p in got})
        self.assertEqual(xs, [(0.5, 0.5), (0.5, 1.0), (1.0, 0.5), (1.0, 1.0)])
        self.assertTrue(all(p[2] == 7.0 for p in got))

    def test_quad_params_inverts_the_bilinear_map(self):
        quad = [(0, 0), (0, 2), (4, 2), (4, 0)]
        a, b = overlays.quad_params(quad, 1.0, 1.5)
        self.assertAlmostEqual(a, 0.25)
        self.assertAlmostEqual(b, 0.75)


class Build(unittest.TestCase):
    def test_off_by_default_and_unchanged(self):
        plain = mesh.build(load())
        m = mesh.build(load(extra_lumps={45: _overlay()}, detail=_dprp()))
        self.assertEqual([(s.material, s.index) for s in m.surfaces], [(s.material, s.index) for s in plain.surfaces])
        self.assertFalse(_of(m, "info_overlay") or _of(m, "detail_sprite"))

    def test_overlay_drawn_on_its_face_lifted_by_order(self):
        scale = 0.02
        for order in (0, 2):
            m = mesh.build(load(extra_lumps={45: _overlay(order=order)}), scale=scale, overlays=True)
            (s,) = _of(m, "info_overlay")
            self.assertEqual(s.glass, "glass_frosted")      # the row: a dark see-through sheet
            ys = {round(v[0][1], 6) for v in s.verts}
            self.assertEqual(ys, {round((64 + overlays.LIFT * (1 + order)) * scale, 6)})
            uvs = [v[2] for v in s.verts]
            self.assertEqual((min(u for u, _ in uvs), max(u for u, _ in uvs)), (0.0, 1.0))
            self.assertEqual(len(s.index), 6)

    def test_decal_row_draws_a_decal_not_glass(self):
        m = mesh.build(load(mats=(MATS[0], "FORK/PARKINGLINES01A"), extra_lumps={45: _overlay()}), scale=1.0, overlays=True)
        (s,) = _of(m, "info_overlay")
        self.assertEqual((s.decal, s.glass), ("decal_lines", None))
        self.assertIn("1 decal surfaces (kinds decal_lines)", m.notes)

    def test_overlay_cut_to_its_face(self):
        m = mesh.build(load(extra_lumps={45: _overlay(origin=(64.0, 32.0, 64.0))}), scale=1.0, overlays=True)
        (s,) = _of(m, "info_overlay")
        self.assertEqual(max(v[0][0] for v in s.verts), 64.0)                 # the box's edge, not 80
        self.assertEqual({round(v[2][0], 6) for v in s.verts}, {0.0, 0.5})

    def test_detail_sprite_is_two_crossed_cards(self):
        m = mesh.build(load(detail=_dprp()), scale=1.0, detail=True)
        (s,) = _of(m, "detail_sprite")
        self.assertEqual((len(s.verts), len(s.index)), (8, 12))
        self.assertEqual(s.material, reader.clean_material("detail/detailsprites"))
        self.assertEqual({round(v[0][1], 6) for v in s.verts}, {64.0, 80.0})

    def test_detail_cropped_away(self):
        m = mesh.build(load(detail=_dprp()), scale=1.0, detail=True, crop=[1000, 1000, 2000, 2000])
        self.assertFalse(_of(m, "detail_sprite"))
        self.assertEqual(m.skipped["detail:outside"], 1)

    def test_sky_room_detail_left_out_on_request(self):
        # a sprite in the 3D skybox room is drawn moved out and scaled up, unless sky_detail=False
        room = ((0.0, 0.0, 64.0), 16.0, ((-1000.0, -1000.0, -1000.0), (1000.0, 1000.0, 1000.0)))
        real = mesh.skybox_of
        mesh.skybox_of = lambda bsp: room
        try:
            drawn = mesh.build(load(detail=_dprp()), scale=1.0, detail=True)
            left = mesh.build(load(detail=_dprp()), scale=1.0, detail=True, sky_detail=False)
        finally:
            mesh.skybox_of = real
        (s,) = _of(drawn, "detail_sprite")
        self.assertTrue(s.sky3d)
        self.assertFalse(_of(left, "detail_sprite"))
        self.assertEqual(left.skipped["detail:sky"], 1)

    def test_view_of_stands_over_the_ground(self):
        flat = lambda x, z: 0.0
        cam = overlays.view_of((0.0, 0.0, 0.0), flat)
        self.assertEqual(round(cam[1], 6), 4.0)                                   # `above` over the decal
        self.assertAlmostEqual(abs(complex(cam[0], cam[2])), 8.0)

    def test_view_of_rises_over_a_hill(self):
        # a hollow 5 m across in a 20 m hill: from 22.5 m up, 8 m out, the rim hides the decal
        hill = lambda x, z: 0.0 if x * x + z * z < 25.0 else 20.0
        cam = overlays.view_of((0.0, 0.0, 0.0), hill)
        self.assertTrue(30.0 <= cam[1] <= 34.0, cam)
        self.assertIsNone(overlays.view_of((0.0, 0.0, 0.0), hill, rise=0.0))

    def test_overlay_views_aim_at_the_drawn_decal(self):
        bsp = load(extra_lumps={45: _overlay()})
        ((name, cam, at),) = overlays.overlay_views(bsp, "darkedge", lambda p: (p[0], p[2], -p[1]), "x")
        self.assertEqual((name, at), ("x_0", (32.0, 64.0, -32.0)))
        self.assertGreater(cam[1], at[1])
        self.assertEqual(overlays.overlay_views(bsp, "nothing", lambda p: p), [])

    def test_overlay_views_follow_the_skybox_room_out(self):
        # the decal's face lies in a 3D skybox room round (0, 0, 64) at scale 16: aimed where the pack
        # draws it, (p - camera) * 16, and from 16 times as far
        bsp = load(extra_lumps={45: _overlay()})
        sky = ((0.0, 0.0, 64.0), 16.0, ((-1000.0, -1000.0, -1000.0), (1000.0, 1000.0, 1000.0)))
        ((_name, cam, at),) = overlays.overlay_views(bsp, "darkedge", lambda p: (p[0], p[2], -p[1]), "x", sky=sky)
        self.assertEqual(at, (512.0, 0.0, -512.0))
        self.assertAlmostEqual(abs(complex(cam[0] - at[0], cam[2] - at[2])), 128.0)
        move, inside = overlays.sky_move(None)
        self.assertEqual(move((1.0, 2.0, 3.0)), (1.0, 2.0, 3.0))
        self.assertFalse(inside([(0.0, 0.0, 0.0)]))


if __name__ == "__main__":
    unittest.main()
