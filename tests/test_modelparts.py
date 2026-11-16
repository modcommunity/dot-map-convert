"""Combined models measured piece by piece, the 3D skybox room and the PLAYLOT detail patterns.
Run: python3 -P tests/test_modelparts.py
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import modeldims, modelparts, standins  # noqa: E402


def cube(x0, y0, z0, s):
    """One mesh: two triangles spanning a cube's diagonal corners, enough for a box."""
    vs = [(x0, y0, z0), (x0 + s, y0, z0), (x0 + s, y0 + s, z0 + s)]
    return ("m", vs, [0, 1, 2])


class Pieces(unittest.TestCase):
    def test_two_apart_pieces_are_two_boxes_in_godot_axes(self):
        got = sorted(modelparts.pieces([cube(0, 0, 0, 1), cube(10, 0, 0, 2)], weld=0.1, scale=1.0))
        self.assertEqual(len(got), 2)
        lo, hi = got[0]
        self.assertEqual([round(v, 3) for v in lo], [0.0, 0.0, -1.0])     # source y is Godot -z, source z is Godot y
        self.assertEqual([round(v, 3) for v in hi], [1.0, 1.0, 0.0])

    def test_a_coarse_weld_joins_near_pieces(self):
        meshes = [cube(0, 0, 0, 1), cube(1.5, 0, 0, 1)]
        self.assertEqual(len(modelparts.pieces(meshes, weld=0.1, scale=1.0)), 2)
        self.assertEqual(len(modelparts.pieces(meshes, weld=4.0, scale=1.0)), 1)

    def test_keep_drops_lines_and_inner_pieces_and_thickens_flat_ones(self):
        boxes = [([0, 0, 0], [2, 2, 2]),            # the big piece
                 ([0.5, 0.5, 0.5], [1, 1, 1]),      # inside it
                 ([5, 0, 0], [5.01, 0.01, 3]),      # a cable
                 ([8, 0, 0], [9, 2, 8])]            # a wall drawn one-sided: 1 x 2 x 8
        got = modelparts.keep(boxes + [([10, 0, 0], [12, 2, 10])], min_side=0.05)
        self.assertEqual(len(got), 3)
        flat = modelparts.keep([([0, 0, 0], [3, 2, 0])], min_side=0.05)
        self.assertEqual(flat, [([1.5, 1.0, 0.0], [3.0, 2.0, 0.05])])
        self.assertEqual(len(modelparts.keep(boxes, min_side=0)), 3)   # 0 keeps lines; only the inner piece goes

    def test_write_replaces_the_given_models_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, modelparts.PARTS)
            modelparts.write({"models/a.mdl": [([0, 0, 0], [1, 1, 1])], "models/b.mdl": [([1, 2, 3], [1, 1, 1])]}, p)
            modelparts.write({"models/a.mdl": [([0, 1, 0], [2, 2, 2]), ([4, 0, 0], [1, 1, 1])]}, p)
            got = modelparts.load(p)
            self.assertEqual(sorted(got), ["models/a.mdl", "models/b.mdl"])
            self.assertEqual(len(got["models/a.mdl"]), 2)
            self.assertEqual(got["models/b.mdl"], [([1.0, 2.0, 3.0], [1.0, 1.0, 1.0])])


class Placement(unittest.TestCase):
    def test_one_block_per_part_turned_with_the_prop(self):
        shaped = {"models/street.mdl": {"stand_in": "parts", "parts": [([1.0, 0.5, 0.0], [2.0, 1.0, 1.0]),
                                                                       ([-3.0, 0.5, 0.0], [1.0, 1.0, 1.0])], "row": None}}
        spots = [("models/street.mdl", [100.0, 0.0, 0.0], [0, 90, 0], None, 6)]
        got = standins._shaped_placements(spots, shaped, scale=0.01, y0=0.0)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["box"], [2.0, 1.0, 1.0])
        self.assertEqual(got[0]["at"], [1.0, 0.5, -1.0])       # +x turned 90 degrees is -z
        self.assertEqual(got[0]["solid"], 6)
        self.assertEqual(got[1]["at"], [1.0, 0.5, 3.0])


class FakeBsp:
    entities = []

    def __init__(self, props):
        self.props = props

    def static_props(self):
        return self.props


class SkyRoom(unittest.TestCase):
    def test_props_in_the_sky_room_are_dropped_and_sky_only_models_marked(self):
        bsp = FakeBsp([{"model": "models/city/tower.mdl", "origin": [5000, 0, 5000]},
                       {"model": "models/props/crate.mdl", "origin": [5000, 0, 5000]},
                       {"model": "models/props/crate.mdl", "origin": [0, 0, 0]}])
        room = ([4000, -1000, 4000], [6000, 1000, 6000])
        used = {}
        props = [{"at": [50.0, 50.0, 0.0]}, {"at": [0.0, 0.0, 0.0]}]
        kept = standins.sky_room(bsp, room, props, used, scale=0.01, y0=0.0)
        self.assertEqual(kept, [{"at": [0.0, 0.0, 0.0]}])
        self.assertEqual(used, {"city/tower.mdl": "skybox"})


class Patterns(unittest.TestCase):
    def test_skybox_and_detail(self):
        self.assertTrue(standins.is_skybox("models/props/3dsky/tower.mdl"))
        self.assertTrue(standins.is_skybox("models/x/cloudperimeter01.mdl"))
        self.assertFalse(standins.is_skybox("models/props/skyboxes_frame.mdl"))
        for m in ("models/deadbodies/x.mdl", "models/dimidrol/fauna/dead_body_shhc_001.mdl",
                  "models/props_lab/banklasers2.mdl", "models/underwater/c_expos_water_fracture01.mdl"):
            self.assertTrue(standins.is_detail(m), m)
        self.assertFalse(standins.is_detail("models/props/crate.mdl"))

    def test_has_parts_takes_either_name_form(self):
        saved = list(standins._PARTS)
        standins._PARTS[:] = [{"models/city/street.mdl": [([0, 0, 0], [1, 1, 1])]}]
        try:
            self.assertTrue(standins.has_parts("models/city/street.mdl"))
            self.assertTrue(standins.has_parts("City/Street.mdl"))     # how the coverage tables name it
            self.assertFalse(standins.has_parts("props/crate.mdl"))
        finally:
            standins._PARTS[:] = saved

    def test_listed_models_take_the_last_column(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("# header\nrp_asheville\tModels/A/B.mdl\nprops/c.mdl\n\n")
        try:
            self.assertEqual(modeldims._listed(f.name), {"models/a/b.mdl", "models/props/c.mdl"})
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
