"""Terrain heightfield tests. Run: python3 -P tests/test_terrain.py

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

from dotbsp import boxes, docboxes, flood, paths, terrain  # noqa: E402

FIXTURE = os.path.join(paths.dot_map_dir(), "examples", "bsp_mesh", "terrain_fixture.json")


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


class TestWalkedCover(unittest.TestCase):
    """docboxes.walk_flood and scatter_walked: a hillside the importer cut as a stepped field (1.5 m cells,
    risers a body cannot step) still gets cover and hider starts, on the heightfield's slope."""

    class _Map:
        def __init__(self):
            self.props = []

        def prop(self, pid, x, z, yaw=0.0, y=0.0):
            self.props.append({"id": pid, "at": [x, y, z], "yaw": yaw})

    def test_hill(self):
        s, tint = 0.01905, [0.85, 0.9, 0.78]
        src = [tuple((p[0] / s, -p[2] / s, p[1] / s) for p in t) for t in grid_tris(lambda x, z: hill(x, z) * 1.7, 0, 0, 40, 40, 1.6)]
        field = []
        for c in boxes.terrain_cells(src):
            (x0, x1), (y0, y1), (z0, z1) = c["x"], c["z"], c["y"]
            field.append({"at": [round((x0 + x1) / 2 * s, 3), round((y0 + y1) / 2 * s, 3), round(-(z0 + z1) / 2 * s, 3)],
                          "size": [round((x1 - x0) * s, 3), round((y1 - y0) * s, 3), round((z1 - z0) * s, 3)], "mat": "grass", "tint": tint})
        walk = docboxes.walk_flood(field, (3, 0.2, 3), src, "grass", tint, scale=s)
        self.assertIsNotNone(walk.reachable(20, 10.5, 20), "the hilltop is walked")
        spots = docboxes.walked_spots(walk)
        self.assertTrue(any(h > 2.0 for _, h, _ in spots), "open ground up the slope")
        tops = [b["at"][1] + b["size"][1] / 2 for b in field]
        m = self._Map()

        def rest(x, z, h):
            got = [b["at"][1] + b["size"][1] / 2 for b in field if docboxes.within(b, x, z) and b["at"][1] + b["size"][1] / 2 <= h + 0.6]
            return max(got) if got else None
        n = docboxes.scatter_walked(m, spots, 12, 7, ("a", "b"), avoid=[(3, 3, 4.0)], rest=rest, ground=walk.ground)
        self.assertEqual(n, 12)
        for q in m.props:
            x, y, z = q["at"]
            self.assertGreaterEqual((x - 3) ** 2 + (z - 3) ** 2, 16.0)
            self.assertTrue(any(abs(y - t) < 1e-6 for t in tops), "set on a field top, which swap_terrain lands")
            hs = [walk.ground.height(x + dx, z + dz) for dx in (-0.75, 0.75) for dz in (-0.75, 0.75)]
            self.assertLessEqual(max(hs) - min(hs), 0.25)
        top = self._Map()
        self.assertGreater(docboxes.scatter_walked(top, [p for p in spots if p[1] > 5.0], 2, 7, ("a",), rest=rest, ground=walk.ground), 0, "and on the hilltop")
        self.assertTrue(all(q["at"][1] > 5.0 for q in top.props))
        self.assertIsNone(docboxes.walk_flood(field, (100, 0, 100), src, "grass", tint, scale=s), "a start on nothing")


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


class TestSwapTerrain(unittest.TestCase):
    """swap_terrain on a synthetic displacement: a gentle slope 2400 units square, in map units."""
    SCALE = 0.01905
    SHIFT = (5.0, 0.5, -3.0)

    def setUp(self):
        # grid_tris is (x, height, z); map units are (x, y, height)
        self.tris = [tuple((p[0], p[2], p[1]) for p in t) for t in grid_tris(lambda x, y: 200 + 0.05 * x, 0, 0, 2400, 2400, 240)]
        self.cells = boxes.terrain_cells(self.tris)
        self.assertGreater(len(self.cells), 20)
        self.doc_boxes = []
        for c in self.cells:
            (x0, x1), (y0, y1), (z0, z1) = c["x"], c["z"], c["y"]
            x0, x1, y0, y1, z0, z1 = [v * self.SCALE for v in (x0, x1, y0, y1, -z1, -z0)]
            at = [(x0 + x1) / 2 + self.SHIFT[0], (y0 + y1) / 2 + self.SHIFT[1], (z0 + z1) / 2 + self.SHIFT[2]]
            self.doc_boxes.append({"at": [round(v, 3) for v in at], "size": [round(x1 - x0, 3), round(y1 - y0, 3), round(z1 - z0, 3)], "mat": "grass", "tint": None})

    def doc(self):
        wall = {"at": [100.0, 5.0, 100.0], "size": [1.0, 2.0, 1.0], "mat": "brick", "tint": None}
        top = self.doc_boxes[len(self.doc_boxes) // 2]
        x, y, z = top["at"][0], top["at"][1] + top["size"][1] / 2, top["at"][2]
        return {"boxes": [dict(b) for b in self.doc_boxes] + [wall], "props": [{"at": [x, y, z]}, {"at": [x, y + 9, z]}],
                "spawns": {"a": [{"at": [x, y, z]}]}, "toys": []}, wall, (x, y, z)

    def test_replaces_field_with_heightfield(self):
        doc, wall, (x, y, z) = self.doc()
        ground = terrain.swap_terrain(doc, self.tris, "grass", None)
        self.assertEqual(doc["boxes"], [wall], "only the field boxes go")
        self.assertIn("terrain", doc)
        back, _ = terrain.Heightfield.decode(doc["terrain"])
        self.assertAlmostEqual(back.height(x, z), ground.height(x, z), places=6)
        self.assertIsNotNone(ground.height(x, z))

    def test_sets_down_what_stood_on_the_field(self):
        doc, _, (x, y, z) = self.doc()
        ground = terrain.swap_terrain(doc, self.tris, "grass", None)
        h = round(ground.height(x, z), 3)
        self.assertEqual(doc["props"][0]["at"], [x, h, z])
        self.assertEqual(doc["props"][1]["at"], [x, y + 9, z], "a prop in the air stays")
        self.assertEqual(doc["spawns"]["a"][0]["at"], [x, h, z])

    def test_spawn_over_a_hole_moves_to_ground(self):
        doc, _, (x, y, z) = self.doc()
        real = terrain.fit

        def holed(*a, **k):
            hf, size = real(*a, **k)
            for k2 in range(len(hf.h)):
                px, pz = hf.sample_pos(k2 % hf.nx, k2 // hf.nx)
                if abs(px - x) < 1.6 and abs(pz - z) < 1.6:
                    hf.h[k2] = None
            return hf, size
        terrain.fit = holed
        try:
            ground = terrain.swap_terrain(doc, self.tris, "grass", None)
        finally:
            terrain.fit = real
        self.assertIsNone(ground.height(x, z), "the fixture punched a hole under the spawn")
        sx, sy, sz = doc["spawns"]["a"][0]["at"]
        self.assertIsNotNone(ground.height(sx, sz), "the spawn is not over a hole")
        self.assertAlmostEqual(sy, ground.height(sx, sz), places=2)

    def test_wrong_material_or_no_field_refuses(self):
        doc, _, _ = self.doc()
        with self.assertRaises(SystemExit):
            terrain.swap_terrain(doc, self.tris, "snow", None)
        with self.assertRaises(SystemExit):
            terrain.swap_terrain({"boxes": doc["boxes"][-1:]}, self.tris, "grass", None)


def _rot(turn):
    """The rotation matrix a document's "turn" [ax, ay, az, degrees] stands for (Rodrigues)."""
    if not turn:
        return [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    x, y, z, deg = turn
    a = math.radians(deg)
    c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
    return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]


def tile_top(b, x, z):
    """The height of tile b's top face over (x, z), or None when (x, z) is outside its footprint."""
    r = _rot(b.get("turn"))
    n = [r[0][1], r[1][1], r[2][1]]
    top = [b["at"][k] + n[k] * b["size"][1] / 2 for k in range(3)]
    y = top[1] - (n[0] * (x - top[0]) + n[2] * (z - top[2])) / n[1]
    d = [x - top[0], y - top[1], z - top[2]]
    u = sum(r[k][0] * d[k] for k in range(3))
    v = sum(r[k][2] * d[k] for k in range(3))
    if abs(u) > b["size"][0] / 2 + 1e-3 or abs(v) > b["size"][2] / 2 + 1e-3:
        return None
    return y


class TestTiltedTiles(unittest.TestCase):
    def test_a_plane_is_one_tilted_slab_lying_in_it(self):
        f = lambda x, z: 1.0 + 0.2 * x + 0.1 * z  # noqa: E731
        hf = terrain.Heightfield.from_tris(grid_tris(f, 0, 0, 20, 20, 1.0), 2.0, bounds=(0, 0, 20, 20))
        tiles = terrain.tilted_tiles(hf, thick=1.0)
        self.assertEqual(len(tiles), 1)
        self.assertIn("turn", tiles[0])
        for x, z in ((1, 1), (10, 10), (19, 3), (4, 18)):
            self.assertAlmostEqual(tile_top(tiles[0], x, z), f(x, z), delta=0.06)
        self.assertIsNone(tile_top(tiles[0], 25, 10))

    def test_level_ground_has_no_turn(self):
        hf = terrain.Heightfield.from_tris(grid_tris(lambda x, z: 2.0, 0, 0, 10, 10, 1.0), 2.0,
                                           bounds=(0, 0, 10, 10))
        tiles = terrain.tilted_tiles(hf, thick=0.5)
        self.assertEqual(len(tiles), 1)
        self.assertNotIn("turn", tiles[0])
        self.assertAlmostEqual(tiles[0]["at"][1], 1.75, delta=0.03)
        self.assertAlmostEqual(tiles[0]["size"][0], 10.0, delta=0.01)

    def test_a_hill_is_covered_close_to_its_surface(self):
        hf = terrain.Heightfield.from_tris(grid_tris(hill, 0, 0, 40, 40, 1.6), 2.0, bounds=(0, 0, 40, 40))
        tiles = terrain.tilted_tiles(hf, thick=1.0)
        self.assertLess(len(tiles), (hf.nx - 1) * (hf.nz - 1))
        for i in range(hf.nx - 1):
            for j in range(hf.nz - 1):
                x, z = hf.x0 + (i + 0.5) * hf.cell, hf.z0 + (j + 0.5) * hf.cell
                tops = [t for t in (tile_top(b, x, z) for b in tiles) if t is not None]
                self.assertTrue(tops, (x, z))
                self.assertLess(min(abs(t - hill(x, z)) for t in tops), 0.35, (x, z))

    def test_a_cliff_steeper_than_the_limit_is_left_out(self):
        f = lambda x, z: 3.0 * x  # noqa: E731
        hf = terrain.Heightfield.from_tris(grid_tris(f, 0, 0, 10, 10, 1.0), 2.0, bounds=(0, 0, 10, 10))
        self.assertEqual(terrain.tilted_tiles(hf, max_slope=1.5), [])

    def test_a_cliff_can_stand_as_upright_columns_from_its_foot_to_its_top(self):
        f = lambda x, z: 3.0 * x  # noqa: E731
        hf = terrain.Heightfield.from_tris(grid_tris(f, 0, 0, 10, 10, 1.0), 2.0, bounds=(0, 0, 10, 10))
        cols = terrain.tilted_tiles(hf, thick=1.0, max_slope=1.5, cliff_columns=True)
        self.assertEqual(len(cols), (hf.nx - 1) * (hf.nz - 1))
        for b in cols:
            self.assertNotIn("turn", b)
            x0 = b["at"][0] - b["size"][0] / 2
            self.assertAlmostEqual(b["at"][1] + b["size"][1] / 2, f(x0 + b["size"][0], 0), delta=0.2)
            self.assertAlmostEqual(b["at"][1] - b["size"][1] / 2, f(x0, 0) - 1.0, delta=0.2)

    def test_pad_overlaps_neighbouring_slabs(self):
        f = lambda x, z: 0.3 * x if x < 10 else 3.0 + 0.6 * (x - 10)  # noqa: E731
        hf = terrain.Heightfield.from_tris(grid_tris(f, 0, 0, 20, 10, 1.0), 2.0, bounds=(0, 0, 20, 10))
        bare = terrain.tilted_tiles(hf, pad=0.0)
        padded = terrain.tilted_tiles(hf, pad=0.1)
        self.assertEqual(len(bare), len(padded))
        for a, b in zip(bare, padded):
            self.assertGreater(b["size"][0], a["size"][0] + 0.15)
            self.assertGreater(b["size"][2], a["size"][2] + 0.15)


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
