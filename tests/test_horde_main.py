"""The zombie-zone importer's main ground leaves out a ledge the horde reaches only by a link it cannot climb.
Run: python3 -P tests/test_horde_main.py
"""
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, os.path.join(ROOT, "adapters", "zombie-zone-maps")]
os.environ.setdefault("DOTBSP_PATH", ROOT)
for TOOLS in (os.environ.get("ZZ_TOOLS", ""), os.path.join(os.path.dirname(ROOT), "zombie-zone-maps", "tools"),
              "/home/gamedev/godot/zombie-zone-maps/tools"):
    if TOOLS and os.path.isfile(os.path.join(TOOLS, "nav_emulate.py")):
        sys.path.append(TOOLS)
        break
try:
    import import_bsp as I  # noqa: E402
except ImportError as err:
    raise unittest.SkipTest("import_bsp not importable: %s" % err)


class G:
    """Points in pieces joined by union-find, as nav_emulate.Graph."""

    def __init__(self, pieces):
        self.pts, self.parent = [], []
        for pts in pieces:
            first = len(self.pts)
            for p in pts:
                self.parent.append(first)
                self.pts.append(p)

    def find(self, i):
        while self.parent[i] != i:
            i = self.parent[i]
        return i

    def union(self, i, j):
        self.parent[self.find(i)] = self.find(j)

    def nearest(self, x, y, z, r):
        best = min(range(len(self.pts)), key=lambda i: math.dist(self.pts[i], (x, y, z)))
        return best if math.dist(self.pts[best], (x, y, z)) <= r else -1

    def sizes(self):
        out = {}
        for i in range(len(self.pts)):
            out[self.find(i)] = out.get(self.find(i), 0) + 1
        return out


def piece(x0, n, y):
    return [(x0 + i, y, 0.0) for i in range(n)]


class HordeMain(unittest.TestCase):
    def test_roof_start_drops_to_the_ground(self):
        # zs_lens: every source start on a 4-point roof 2.5 m over a 20-point ground its links only drop to.
        g = G([piece(0, 4, 2.5), piece(-5, 20, 0.0)])
        roof = g.find(0)
        main = I.horde_main(g, roof, [(1, 2.5, 0)], [(3, 10)], g.sizes())
        self.assertEqual(g.find(10), main)
        self.assertNotEqual(g.find(0), main)

    def test_ground_drops_into_a_pit(self):
        # A pit under the ground is the horde's too: it drops in.
        g = G([piece(0, 20, 0.0), piece(30, 5, -3.0)])
        main = I.horde_main(g, g.find(0), [(1, 0, 0)], [(19, 20)], g.sizes())
        self.assertEqual(g.find(22), main)
        self.assertEqual(g.find(0), main)

    def test_ledge_over_the_ground_stays_out(self):
        # A ledge that only drops onto the ground is no main ground: no zombie climbs a 2.5 m link.
        g = G([piece(0, 20, 0.0), piece(30, 5, 2.5)])
        main = I.horde_main(g, g.find(0), [(1, 0, 0)], [(20, 19)], g.sizes())
        self.assertEqual(g.find(0), main)
        self.assertNotEqual(g.find(22), main)


if __name__ == "__main__":
    unittest.main()
