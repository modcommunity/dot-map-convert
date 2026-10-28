"""Texture density report: the repeat length of a surface and the pixels per metre a set is drawn at.
Run: python3 -I tools/bsp/tests/test_texquality.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import licence, mesh, texquality  # noqa: E402


def quad(metres, repeats):
    """A square surface `metres` wide whose uv runs 0..`repeats`."""
    s = mesh.Surface(0, None, "worldspawn", "", "brick/x")
    n = (0.0, 1.0, 0.0)
    a = s.vertex((0.0, 0.0, 0.0), n, (0.0, 0.0))
    b = s.vertex((metres, 0.0, 0.0), n, (repeats, 0.0))
    c = s.vertex((metres, 0.0, metres), n, (repeats, repeats))
    d = s.vertex((0.0, 0.0, metres), n, (0.0, repeats))
    s.index = [a, b, c, a, c, d]
    return s


class TexQuality(unittest.TestCase):
    def test_repeat_is_metres_per_uv_unit(self):
        self.assertAlmostEqual(mesh.repeat_metres(quad(8.0, 2.0)), 4.0, places=5)

    def test_flat_uv_has_no_repeat(self):
        self.assertEqual(mesh.repeat_metres(quad(8.0, 0.0)), 0.0)

    def test_density_is_width_over_draw_metres(self):
        self.assertEqual(licence.SMALL_PX / texquality.DRAW_METRES, 64.0)
        self.assertLess(licence.SMALL_PX / texquality.DRAW_METRES, texquality.TARGET)
        self.assertGreaterEqual(1024 / texquality.DRAW_METRES, texquality.TARGET)

    def test_percentiles_weight_by_area(self):
        r = texquality.percentiles([(90.0, 100.0), (10.0, 900.0)])
        self.assertEqual((r["p5"], r["p50"], r["p95"]), (100, 100, 900))


if __name__ == "__main__":
    unittest.main()
