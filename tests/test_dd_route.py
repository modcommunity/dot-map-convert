"""adapters/mg-dangerous-delivery/bsp_route.py's tests. Run: python3 -P tests/test_dd_route.py

The maps are built in memory: an L of road (5 m tiles) on a tilted field with a grass verge.
"""

import importlib.util
import math
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import mesh  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "bsp_route", os.path.join(HERE, "..", "adapters", "mg-dangerous-delivery", "bsp_route.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

TILE = 5.0
GRADE = 0.04


def height(x, z):
    return GRADE * (300.0 - z)


def on_road(x, z):
    """Leg one runs along z (x in -5..5, z -10..300), leg two along +x (z -10..0, x -5..250)."""
    return (-5 <= x < 5 and -10 <= z < 300) or (-5 <= x < 250 and -10 <= z < 0)


def tile(s, x, z, alpha=None):
    corners = [(x, z), (x + TILE, z), (x + TILE, z + TILE), (x, z + TILE)]
    ids = [s.vertex((cx, height(cx, cz), cz), (0.0, 1.0, 0.0), (cx, cz), alpha=alpha) for cx, cz in corners]
    s.index += [ids[0], ids[2], ids[1], ids[0], ids[3], ids[2]]


def surface(material):
    return mesh.Surface(0, 0, "worldspawn", "", material)


def l_map():
    road, grass = surface("roads/asphalt01"), surface("nature/grass01")
    x = -20.0
    while x < 265:
        z = -25.0
        while z < 315:
            near = (-20 <= x < 20 and z < 315) or z < 15
            if near:
                tile(road if on_road(x + 1, z + 1) else grass, x, z)
            z += TILE
        x += TILE
    m = mesh.Mesh()
    m.surfaces = [road, grass]
    doc = {"name": "synth L", "surfaces": [{"free": "pbr:asphalt"}, {"free": "pbr:grass"}]}
    return doc, m


def check(test, route):
    """The limits game/dd_route_doc.gd puts on a route."""
    test.assertEqual(route["format"], 1)
    test.assertEqual(route["kind"], "route")
    test.assertRegex(route["id"], r"^[a-z_][a-z0-9_]*$")
    test.assertTrue(1 <= route["level"] <= 99)
    test.assertTrue(4 <= route["width"] <= 30)
    for s in route["segments"]:
        test.assertTrue(2 <= s["length"] <= 2000, s)
        test.assertLessEqual(abs(s["turn"]) / s["length"], 2.2, s)
        test.assertLessEqual(abs(s["climb"]) / s["length"], 0.18, s)
        test.assertLessEqual(abs(s["turn"]) / s["length"], B.DRIVE_TURN + 0.01, s)
        test.assertLessEqual(abs(s["climb"]) / s["length"], B.DRIVE_GRADE + 0.001, s)
        test.assertIn(s["wall"], ("none", "left", "right", "both"))
        test.assertIn(s["rail"], ("none", "left", "right", "both"))
        test.assertTrue(4 <= s["width"] <= 30)
        test.assertIn(s["zone"], route["zones"])


class LRoad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.route, cls.stats = B.route_doc(*l_map())

    def test_valid(self):
        check(self, self.route)
        self.assertEqual(self.route["id"], "dd_synth_l")

    def test_follows_the_road_end_to_end(self):
        total = sum(s["length"] for s in self.route["segments"])
        self.assertGreater(total, 500)
        self.assertLess(total, 580)
        self.assertGreater(self.stats["road_share"], 0.95)
        ends = sorted([self.stats["start"], self.stats["end"]], key=lambda p: p[2])
        self.assertGreater(ends[0][0], 220)   # the end of leg two
        self.assertGreater(ends[1][2], 280)   # the end of leg one

    def test_turn_and_climb(self):
        segs = self.route["segments"]
        turn = sum(s["turn"] for s in segs)
        climb = sum(s["climb"] for s in segs)
        down_z = self.stats["start"][2] > self.stats["end"][2]
        # facing -z then turning to +x is a right turn (positive); the field rises towards -z
        self.assertAlmostEqual(turn, 90.0 if down_z else -90.0, delta=12)
        self.assertAlmostEqual(climb, GRADE * 300 * (1 if down_z else -1), delta=2.5)

    def test_width_follows_the_road(self):
        self.assertTrue(8 <= self.route["width"] <= 12, self.route["width"])


class Floors(unittest.TestCase):
    def grid(self, material, free, free2, alpha):
        s = surface(material)
        tile(s, 0, 0, alpha=alpha)
        m = mesh.Mesh()
        m.surfaces = [s]
        g = B.build_grid({"surfaces": [{"free": free, "free2": free2}]}, m, 2.0)
        return [L for lv in g.levels.values() for L in lv]

    def test_blend_shows_the_layer_its_alpha_paints(self):
        on = self.grid("nature/blendgrassgravel", "pbr:grass", "pbr:gravel", 1.0)
        off = self.grid("nature/blendgrassgravel", "pbr:grass", "pbr:gravel", 0.0)
        self.assertTrue(all(L[1] == L[2] for L in on))
        self.assertTrue(all(L[1] == 0 for L in off))

    def test_road_blend_is_road_under_snow(self):
        lv = self.grid("boreas/nature/blendsnowroad01", "pbr:snow", "pbr:road", 0.0)
        self.assertTrue(all(L[1] == L[2] and L[3] == L[2] for L in lv))

    def test_not_road(self):
        self.assertFalse(B.is_road("metal/drain_grate_road"))
        self.assertTrue(B.is_road("pbr:Road008A"))
        self.assertFalse(B.is_road("nature/gravel01", B.ROAD_WORDS))

    def test_short_roads_go_across_country(self):
        road, grass = surface("roads/asphalt01"), surface("nature/grass01")
        for i in range(0, 120, 5):
            for j in range(0, 600, 5):
                tile(road if i < 10 and j < 40 else grass, i, j)
        m = mesh.Mesh()
        m.surfaces = [road, grass]
        route, stats = B.route_doc({"name": "field", "surfaces": [{"free": None}, {"free": None}]}, m)
        check(self, route)
        self.assertGreater(sum(s["length"] for s in route["segments"]), 500)
        self.assertLess(stats["road_share"], 0.2)


if __name__ == "__main__":
    unittest.main()
