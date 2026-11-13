"""doorway_pairs: the binned search finds exactly the pairs the old scan of every point against every point did."""
import math
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, os.path.join(ROOT, "adapters", "zombie-zone-maps")]
os.environ.setdefault("DOTBSP_PATH", ROOT)

try:
    import import_bsp as I  # noqa: E402
except ImportError:
    I = None


def scan_all(pts, big, link_dy):
    reach = []
    for i, pa_ in enumerate(pts):
        if big[i]:
            continue
        for j, pb_ in enumerate(pts):
            if not big[j] or abs(pa_[0] - pb_[0]) > 5 or abs(pa_[2] - pb_[2]) > 5:
                continue
            dd = math.dist(pa_, pb_)
            if dd <= 5.0 and abs(pa_[1] - pb_[1]) <= link_dy:
                reach.append((dd, i, j))
    reach.sort()
    return reach


@unittest.skipIf(I is None, "import_bsp did not import")
class DoorwayPairs(unittest.TestCase):
    def test_matches_scan_of_all(self):
        rng = random.Random(3)
        found = 0
        for _ in range(30):
            n = rng.randint(50, 400)
            # Points on a grid (as the graph lays them) plus some off it, some exactly on the 5 m bin edges.
            pts = []
            for _k in range(n):
                if rng.random() < 0.3:
                    pts.append((rng.randrange(-6, 7) * 5.0, rng.choice([0.0, 0.3, 1.0]), rng.randrange(-6, 7) * 5.0))
                else:
                    pts.append((rng.uniform(-30, 30), rng.choice([0.0, 0.3, 0.6, 2.0]), rng.uniform(-30, 30)))
            big = [rng.random() < 0.6 for _k in pts]
            dy = rng.choice([0.5, 1.0])
            want = scan_all(pts, big, dy)
            self.assertEqual(I.doorway_pairs(pts, big, dy), want)
            found += len(want)
        self.assertGreater(found, 100)


if __name__ == "__main__":
    unittest.main()
