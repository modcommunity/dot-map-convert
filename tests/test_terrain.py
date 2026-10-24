"""Terrain heightfield tests. Run: python3 -I tools/bsp/tests/test_terrain.py

Also checks examples/bsp_mesh/terrain_fixture.json, which examples/bsp_mesh_demo.tscn reads to
hold DotMapTerrain to the same heights and walk points; `--write` rewrites it.
"""

import json
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import boxes, flood, terrain  # noqa: E402

FIXTURE = os.path.join(HERE, "..", "..", "..", "examples", "bsp_mesh", "terrain_fixture.json")


def grid_tris(f, x0, z0, x1, z1, step):
    """Triangles of y = f(x, z) on a grid, as a displacement would be."""
    out = []
    xs = [x0 + k * step for k in range(int(round((x1 - x0) / step)) + 1)]
    zs = [z0 + k * step for k in range(int(round((z1 - z0) / step)) + 1)]
    for a, b in zip(xs, xs[1:]):
        for c, d in zip(zs, zs[1:]):
            p = [(a, f(a, c), c), (b, f(b, c), c), (b, f(b, d), d), (a, f(a, d), d)]
            out += [(p[0], p[1], p[2]), (p[0], p[2], p[3])]
    return out


def hill(x, z):
    """A round hill 6 m high and about 30 m across, at most about 30 degrees steep."""
    return 6.0 * math.exp(-((x - 20) ** 2 + (z - 20) ** 2) / 120.0)


def fixture_field():
    tris = grid_tris(hill, 0, 0, 40, 40, 1.6)
    hf = terrain.Heightfield.from_tris(tris, 2.0)
    hf.h[hf.nx * 3 + 4] = None          # a hole the reader must keep
    hf.h[hf.nx * 5] = None              # a notch in the rim, which is rim
    return hf


class TestHeightfield(unittest.TestCase):
    def test_plane_is_exact(self):
        tris = grid_tris(lambda x, z: 0.5 * x - 0.25 * z + 3, -10, -10, 10, 10, 2.5)
        hf = terrain.Heightfield.from_tris(tris, 1.0)
        self.assertEqual((hf.nx, hf.nz), (21, 21))
        for x, z in ((0.3, 0.7), (-9.5, 9.9), (5.25, -3.75)):
            self.assertAlmostEqual(hf.height(x, z), 0.5 * x - 0.25 * z + 3, places=6)
        self.assertIsNone(hf.height(11, 0))

    def test_highest_wins_and_vertical_skipped(self):
        low = grid_tris(lambda x, z: 0.0, 0, 0, 4, 4, 2)
        high = grid_tris(lambda x, z: 2.0, 0, 0, 2, 2, 2)
        wall = [((1, 0, 1), (1, 5, 1), (1, 5, 3))]
        hf = terrain.Heightfield.from_tris(low + high + wall, 1.0)
        self.assertAlmostEqual(hf.at(1, 1), 2.0)
        self.assertAlmostEqual(hf.at(3, 3), 0.0)

    def test_round_trip(self):
        hf = fixture_field()
        walk = {(i, j) for i in range(5) for j in range(6)}
        d = hf.encode(walk=walk, mat="grass", skirt=hf.skirt_level())
        back, w = terrain.Heightfield.decode(d)
        self.assertEqual(w, walk)
        self.assertEqual(d["mat"], "grass")
        for a, b in zip(hf.h, back.h):
            self.assertEqual(a is None, b is None)
            if a is not None:
                self.assertLessEqual(abs(a - b), d["step"] / 2 + 1e-9)
        self.assertIsNone(back.height(4.5 * 2 + back.x0, 3.2 * 2 + back.z0))

    def test_cropped(self):
        hf = fixture_field()
        c = hf.cropped(lambda i, j: (i, j) == (10, 10), 2)
        self.assertEqual((c.nx, c.nz), (5, 5))
        self.assertAlmostEqual(c.height(*hf.sample_pos(10, 10)), hf.at(10, 10))

    def test_fit_meets_budget(self):
        tris = grid_tris(hill, 0, 0, 40, 40, 1.6)
        hf, size = terrain.fit(tris, (0, 0, 40, 40), 400, margin_m=0)
        self.assertLessEqual(size, 400)
        self.assertGreater(hf.cell, 1.0)


class TestFloodOnTerrain(unittest.TestCase):
    def test_climbs_a_hill_a_box_field_cannot(self):
        tris = grid_tris(hill, 0, 0, 40, 40, 1.6)
        top = (20.0, hill(20, 20), 20.0)
        start = (2.0, hill(2, 2), 2.0)
        hf = terrain.Heightfield.from_tris(tris, 1.0)
        fl = flood.Flood([], terrain=hf).run([start])
        self.assertIsNotNone(fl.reachable(*top), "the triangle ground reaches the top")
        self.assertEqual(fl.floor_rects(), [], "terrain is no flat floor")
        walk = fl.terrain_walk()
        self.assertGreater(len(walk), 0.9 * hf.count())
        # The stepped field the converter used to make: 2 m cells, 0.3 m steps.
        src = [tuple((p[0] / 0.0254, -p[2] / 0.0254, p[1] / 0.0254) for p in t) for t in tris]
        cells = boxes.terrain_cells(src, cell=80.0, quant=5.0)
        gb = [{"at": [(c["x"][0] + c["x"][1]) / 2 * 0.0254, (c["z"][0] + c["z"][1]) / 2 * 0.0254, -(c["y"][0] + c["y"][1]) / 2 * 0.0254],
               "size": [(c["x"][1] - c["x"][0]) * 0.0254, (c["z"][1] - c["z"][0]) * 0.0254, (c["y"][1] - c["y"][0]) * 0.0254]} for c in cells]
        old = flood.Flood(gb, step=0.3, jump=0.3).run([start])
        self.assertIsNone(old.reachable(*top), "the box field stops at the slope")

    def test_cliff_is_dropped_not_climbed(self):
        tris = grid_tris(lambda x, z: 0.0 if x < 10 else 3.0, 0, 0, 20, 10, 0.5)
        hf = terrain.Heightfield.from_tris(tris, 0.5)
        up = flood.Flood([], terrain=hf).run([(2, 0, 5)])
        self.assertIsNone(up.reachable(15, 3, 5))
        down = flood.Flood([], terrain=hf).run([(15, 3, 5)])
        self.assertIsNotNone(down.reachable(2, 0, 5))
        self.assertTrue(down.links)

    def test_box_over_ground_and_box_floor(self):
        tris = grid_tris(lambda x, z: 0.0, 0, 0, 20, 20, 2)
        hf = terrain.Heightfield.from_tris(tris, 1.0)
        crate = {"at": [10, 0.4, 10], "size": [4, 0.8, 4]}
        fl = flood.Flood([crate], terrain=hf).run([(2, 0, 2)])
        self.assertAlmostEqual(fl.reachable(10, 0.8, 10), 0.8, msg="the top is a box floor, jumped onto")
        self.assertFalse([t for t in fl.tsurf if t[:2] == fl.cell_of(10, 10)], "no ground inside the crate")


class TestSkirt(unittest.TestCase):
    def plane(self, n=6):
        return terrain.Heightfield(0, 0, 1.0, n, n, [1.0 + 0.1 * (k % n) for k in range(n * n)])

    def test_rim_of_a_square_is_its_perimeter(self):
        edges = self.plane().outer_edges()
        self.assertEqual(len(edges), 4 * 5)
        self.assertTrue(all(0 in (a[0], a[1], b[0], b[1]) or 5 in (a[0], a[1], b[0], b[1]) for a, b in edges))

    def test_enclosed_hole_is_not_rim(self):
        hf = self.plane()
        hf.h[2 * 6 + 2] = None
        self.assertEqual(len(hf.outer_edges()), 20, "a building's footprint keeps no wall")

    def test_notch_in_the_border_is_rim(self):
        hf = self.plane()
        hf.h[0] = None
        self.assertGreater(len(hf.outer_edges()), 20 - 2, "the corner is cut off, its two new edges are rim")
        hf = self.plane()
        hf.h[2 * 6 + 2] = None
        hf.h[3 * 6 + 2] = None
        hf.h[3 * 6 + 1] = None
        hf.h[3 * 6] = None
        self.assertGreater(len(hf.outer_edges()), 20, "a hole opened to the border by a channel is rim all round")

    def test_add_skirt_to_a_committed_document(self):
        hf = self.plane()
        doc = {"terrain": hf.encode(mat="grass")}
        before = {k: v for k, v in doc["terrain"].items()}
        self.assertAlmostEqual(terrain.add_skirt(doc), hf.skirt_level(), places=1)
        self.assertEqual({k: v for k, v in doc["terrain"].items() if k != "skirt"}, before)
        self.assertIsNone(terrain.add_skirt({}))

    def test_level_is_under_the_lowest_ground_and_only_a_float(self):
        hf = self.plane()
        lvl = hf.skirt_level()
        self.assertAlmostEqual(lvl, 1.0 - 2.0)
        plain, walled = hf.encode(), hf.encode(skirt=lvl)
        self.assertNotIn("skirt", plain)
        self.assertEqual(walled["skirt"], lvl)
        self.assertEqual({k: v for k, v in walled.items() if k != "skirt"}, plain, "heights, walk and size untouched")
        self.assertEqual(terrain.Heightfield.decode(walled)[0].h, terrain.Heightfield.decode(plain)[0].h)


def fixture():
    hf = fixture_field()
    walk = {(i, j) for j in range(hf.nz) for i in range(hf.nx) if hf.at(i, j) is not None and (i - 10) ** 2 + (j - 10) ** 2 < 40}
    d = hf.encode(walk=walk, mat="grass", skirt=hf.skirt_level())
    q, w = terrain.Heightfield.decode(d)
    probes = []
    for x, z in ((20.0, 20.0), (7.3, 11.9), (11.9, 7.3), (0.1, 39.5), (9.0, 7.0), (50.0, 5.0)):
        h = q.height(x, z)
        probes.append([x, z, None if h is None else round(h, 6)])
    pts = terrain.walk_points(q, w, 1.0)
    return {"terrain": d, "skirt_edges": ";".join("%d,%d,%d,%d" % (a + b) for a, b in hf.outer_edges()), "probes": probes, "walk_points": len(pts),
            "walk_first": [round(v, 6) for v in pts[0]], "walk_last": [round(v, 6) for v in pts[-1]],
            "faces": 3 * sum(1 for j in range(q.nz - 1) for i in range(q.nx - 1)
                             for c in ((q.at(i, j), q.at(i + 1, j), q.at(i + 1, j + 1)), (q.at(i, j), q.at(i, j + 1), q.at(i + 1, j + 1)))
                             if None not in c)}


class TestFixture(unittest.TestCase):
    def test_fixture_current(self):
        with open(FIXTURE) as f:
            self.assertEqual(json.load(f), json.loads(json.dumps(fixture())), "run test_terrain.py --write")


if __name__ == "__main__":
    if "--write" in sys.argv:
        with open(FIXTURE, "w") as f:
            json.dump(fixture(), f, indent=1)
            f.write("\n")
        sys.argv.remove("--write")
    unittest.main()
