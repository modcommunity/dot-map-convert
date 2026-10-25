"""The lightmap reader: RGBE decode, RGB9E5 packing, placement, UV2 on a face (no map needed)."""
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from dotbsp import lightmap


def unpack(v):
    v = int(v)
    e = (v >> 27) - 15 - 9
    return [((v >> s) & 511) * 2.0 ** e for s in (0, 9, 18)]


class FakeBsp:
    """One 3x2 face, lit: texel (x, y) holds mantissa 10*x+y and exponent 1, base sample only."""

    def __init__(self, flags=0):
        raw = bytearray()
        for y in range(2):
            for x in range(3):
                raw += bytes((10 * x + y, 10 * x + y, 10 * x + y, 1))
        self.light = bytes(raw)
        self.texinfo = [(1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, flags, 0)]
        self.faces = [(0, 0, 0, 0, 4, 0, -1, 0, bytes((0, 255, 255, 255)), 0, 1.0, 0, 0, 2, 1, 0, 0, 0, 0)]

    def _lump(self, i):
        return self.light if i == 8 else b""


class LightmapTest(unittest.TestCase):
    def test_rgb9e5_round_trip(self):
        for v in (0.0, 0.001, 0.5, 1.0, 3.7, 250.0):
            got = unpack(lightmap.rgb9e5(np.array([[v, v * 0.5, 0.0]]))[0])
            self.assertAlmostEqual(got[0], v, delta=max(v / 256, 1e-4))
            self.assertAlmostEqual(got[1], v * 0.5, delta=max(v / 256, 1e-4))

    def test_decode_is_mantissa_times_exponent_over_255(self):
        b = FakeBsp()
        lx = lightmap.luxels(b, b.faces[0], (b.light, b.faces))
        self.assertEqual(lx.shape, (2, 3, 3))
        self.assertAlmostEqual(lx[1, 2, 0], 21 * 2 / 255.0)

    def test_nolight_face_has_no_luxels(self):
        b = FakeBsp(flags=lightmap.SURF_NOLIGHT)
        self.assertIsNone(lightmap.luxels(b, b.faces[0], (b.light, b.faces)))

    def test_uv2_hits_texel_centres_and_clamps(self):
        b = FakeBsp()
        a = lightmap.pack(b, b.faces)
        f, ti = b.faces[0], b.texinfo[0]
        page, (u, v) = lightmap.uv2(a, f, ti, (0, 0, 0))
        px, py = a.place[id(f)][1:]
        self.assertEqual(page, 0)
        self.assertAlmostEqual(u * lightmap.PAGE, px + 0.5)
        self.assertAlmostEqual(v * a.heights[0], py + 0.5)
        _, (u2, _v2) = lightmap.uv2(a, f, ti, (99, 0, 0))
        self.assertAlmostEqual(u2 * lightmap.PAGE, px + 2.5)
        texel = unpack(a.pages[0][py + 1, px + 2])[0]
        self.assertAlmostEqual(texel, 21 * 2 / 255.0, delta=0.001)

    def test_unlit_face_reads_white_patch(self):
        b = FakeBsp()
        a = lightmap.pack(b, b.faces)
        other = (0,) * 9 + (-1,) + (0,) * 9
        page, (u, v) = lightmap.uv2(a, other, b.texinfo[0], (5, 5, 5))
        self.assertEqual(unpack(a.pages[0][int(v * a.heights[0]), int(u * lightmap.PAGE)]), [1.0, 1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
