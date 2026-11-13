"""LinkObstacles: link_blocked over the binned obstacles answers as it does over the plain list."""
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


def box(rng):
    if rng.random() < 0.05:    # a slab wider than the WIDE bins
        x, z, w, d = rng.uniform(-40, 0), rng.uniform(-40, 0), rng.uniform(40, 80), rng.uniform(40, 80)
    else:
        x, z, w, d = rng.uniform(-40, 40), rng.uniform(-40, 40), rng.uniform(0.05, 6), rng.uniform(0.05, 6)
    y = rng.uniform(-1, 2)
    return (x, y, z, x + w, y + rng.uniform(0.1, 3), z + d)


@unittest.skipIf(I is None, "import_bsp did not import")
class LinkObstacles(unittest.TestCase):
    def test_same_answer_as_list(self):
        rng = random.Random(11)
        blocked = 0
        for _ in range(20):
            obs = [box(rng) for _k in range(rng.randint(20, 300))]
            idx = I.LinkObstacles(obs)
            self.assertEqual(list(idx), obs)
            for _k in range(300):
                a = (rng.uniform(-40, 40), rng.uniform(-0.5, 1.5), rng.uniform(-40, 40))
                c = (a[0] + rng.uniform(-5, 5), a[1] + rng.uniform(-0.5, 0.5), a[2] + rng.uniform(-5, 5))
                grow, min_h = rng.choice([(0.0, 0.55), (0.25, 0.4)])
                want = I.link_blocked(obs, a, c, grow=grow, min_h=min_h)
                self.assertEqual(I.link_blocked(idx, a, c, grow=grow, min_h=min_h), want)
                blocked += want
        self.assertGreater(blocked, 200)


if __name__ == "__main__":
    unittest.main()
