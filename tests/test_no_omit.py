"""No-omission mode (regen --no-omit, modelmap --no-omit): skybox and detail models are kept, and props in the 3D
skybox room are moved out and scaled up the way the room's faces are.
Run: python3 -P tests/test_no_omit.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import standins  # noqa: E402

SKY = "models/props_buildings/project_building01_skybox.mdl"


class NoOmit(unittest.TestCase):
    def tearDown(self):
        standins.set_no_omit(False)

    def test_default_still_leaves_skybox_models_out(self):
        standins.set_no_omit(False)
        self.assertTrue(standins.is_skybox(SKY))

    def test_no_omit_keeps_skybox_and_detail_models(self):
        standins.set_no_omit(True)
        self.assertFalse(standins.is_skybox(SKY))
        self.assertFalse(standins.is_detail(SKY))
        self.assertFalse(standins.is_detail("models/props_c17/utilityconnecter002.mdl"))

    def test_sky_props_move_out_scaled_and_not_solid(self):
        standins.set_no_omit(True)
        scale, y0, k = 0.0254, 1.0, 16.0
        room = ((-100.0, -100.0, -100.0), (100.0, 100.0, 100.0))       # map units
        cam = (10.0, 20.0, 30.0)
        inside = {"model": SKY, "at": [0.0, 0.0, 0.0], "scale": 1.0, "box": [1.0, 2.0, 3.0], "solid": True}
        outside = {"model": "x", "at": [50.0, 0.0, 0.0], "scale": 1.0, "solid": True}
        got = standins._sky_moved([inside, outside], room, (cam, k), scale, y0)
        self.assertEqual(got[1], outside)
        q = got[0]
        c = (cam[0] * scale, cam[2] * scale - y0, -cam[1] * scale)
        want = [(0.0 - c[0]) * k, (0.0 - c[1]) * k - y0, (0.0 - c[2]) * k]
        for a in range(3):
            self.assertAlmostEqual(q["at"][a], want[a], places=3)
        self.assertEqual(q["scale"], 16.0)
        self.assertEqual(q["box"], [16.0, 32.0, 48.0])
        self.assertNotIn("solid", q)
        self.assertTrue(q["sky3d"])

    def test_sky_point_lands_where_the_room_faces_land(self):
        # a sky point at the camera itself draws at the world origin in source terms: Godot (0, -y0, 0)
        standins.set_no_omit(True)
        scale, y0 = 0.0254, 2.0
        cam = (40.0, -80.0, 12.0)
        at = [cam[0] * scale, cam[2] * scale - y0, -cam[1] * scale]
        room = ((-1000.0,) * 3, (1000.0,) * 3)
        q = standins._sky_moved([{"model": SKY, "at": at}], room, (cam, 16.0), scale, y0)[0]
        self.assertEqual([round(v, 3) for v in q["at"]], [0.0, -y0, 0.0])


if __name__ == "__main__":
    unittest.main()
