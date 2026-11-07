"""nav_coverage.py: coverage raw and with the cells decor props block discounted, and the uncovered rest by cause."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "adapters", "zombie-zone-maps")]
import nav_coverage as N  # noqa: E402


def area(x, z, y=5.0, m2=4.0):
    return (x, z, y, m2)


class Classify(unittest.TestCase):
    def setUp(self):
        self.pts = [(0.0, 5.0, 0.0, 1), (20.0, 5.0, 0.0, 0)]
        # (x, z, y, m2): covered, prop-blocked, off-main, no point (y 5), no point (y 9)
        self.areas = [area(0.5, 0), area(10, 0), area(20.5, 0), area(40, 0), area(50, 0, y=9.0)]
        self.props = (0.5, [(10.0, 5.0, 0.0, 1.0)])

    def test_without_props(self):
        r = N.classify(self.areas, self.pts)
        self.assertEqual(r["covered"], 4.0)
        self.assertNotIn("prop_blocked", r)
        self.assertEqual(r["off_main"], 4.0)
        self.assertEqual(r["no_point_y4"], 8.0)
        self.assertEqual(r["no_point_y8"], 4.0)

    def test_prop_blocked_split_out(self):
        r = N.classify(self.areas, self.pts, self.props)
        self.assertEqual(r["prop_blocked"], 4.0)
        self.assertEqual(r["no_point_y4"], 4.0)
        self.assertEqual(r["covered"], 4.0)

    def test_prop_at_other_height_does_not_block(self):
        r = N.classify(self.areas, self.pts, (0.5, [(10.0, 8.0, 0.0, 1.0)]))
        self.assertNotIn("prop_blocked", r)

    def test_covered_wins_over_prop(self):
        r = N.classify([area(0.5, 0)], self.pts, (0.5, [(0.0, 5.0, 0.0, 1.0)]))
        self.assertEqual(r, {"covered": 4.0})

    def test_y0_offset(self):
        r = N.classify([area(0.5, 0, y=5.4)], self.pts, y0=0.4)
        self.assertEqual(r, {"covered": 4.0})

    def test_report(self):
        res = N.classify(self.areas, self.pts, self.props)
        text = N.report(res, 5)
        self.assertIn("raw coverage:            20.0%", text)
        self.assertIn("prop-discounted coverage: 25.0%", text)
        self.assertIn("off_main", text)

    def test_files_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            pp, bp = os.path.join(d, "p.json"), os.path.join(d, "b.json")
            json.dump([[0, 5, 0, 1], [20, 5, 0, 0]], open(pp, "w"))
            json.dump({"cell": 0.5, "blocks": [[10, 5, 0, 1.0]]}, open(bp, "w"))
            self.assertEqual(N.load_points(pp)[1], (20, 5, 0, 0))
            self.assertEqual(N.load_props(bp), (0.5, [(10, 5, 0, 1.0)]))


if __name__ == "__main__":
    unittest.main()
