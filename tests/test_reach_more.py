"""reach_more: the wide flood under fewer prop blocks is the flood under more of them plus what reach_more walks on to.

convert()'s prop sweep used to flood the whole map once per prop; it now continues the kept flood into the
columns a prop's blocks leave, so the two must reach exactly the same cells."""
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


def random_map(rng, n=28):
    """Ground with raised decks, steps, and walls on a n x n metre plot."""
    boxes = [{"at": [n / 2, -0.1, n / 2], "size": [n, 0.2, n], "mat": "concrete"}]
    for _ in range(rng.randint(10, 30)):
        w, d = rng.uniform(0.3, 6), rng.uniform(0.3, 6)
        top = rng.choice([0.2, 0.35, 0.6, 1.0, 1.4, 3.0, 3.2])
        x, z = rng.uniform(1, n - 1), rng.uniform(1, n - 1)
        boxes.append({"at": [x, top / 2, z], "size": [w, top, d], "mat": "concrete"})
    return boxes


def random_blocks(rng, n=28, k=40):
    out = {}
    for _ in range(k):
        cx, cz = rng.randrange(int(n / I.CELL)), rng.randrange(int(n / I.CELL))
        out.setdefault((cx, cz), []).append(rng.choice([0.0, 0.2, 0.6, 1.0, 3.0]))
    return out


@unittest.skipIf(I is None, "import_bsp did not import")
class ReachMore(unittest.TestCase):
    def test_matches_whole_flood(self):
        rng = random.Random(7)
        opened = 0
        for _ in range(25):
            boxes = random_map(rng)
            geom = I.nav_geometry(boxes)
            starts = [[1.0, 0.0, 1.0], [20.0, 3.2, 20.0]]
            blk = random_blocks(rng)
            seen = set(I.build_nav(boxes, starts, blk, True, geom)[2])
            for col in rng.sample(sorted(blk), 8):
                fewer = {k: list(v) for k, v in blk.items()}
                fewer[col].pop(0)
                if not fewer[col]:
                    del fewer[col]
                whole = set(I.build_nav(boxes, starts, fewer, True, geom)[2])
                cols = {(col[0] + dx, col[1] + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
                more = I.reach_more(geom, seen, fewer, cols)
                self.assertFalse(more & seen)
                self.assertEqual(seen | more, whole)
                opened += 1 if more else 0
        self.assertGreater(opened, 5, "the random maps should open new ground now and then")


if __name__ == "__main__":
    unittest.main()
