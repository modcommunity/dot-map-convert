#!/usr/bin/env python3
"""A Dangerous Delivery route document from a converted map: the longest drivable road, as segments.

    python3 -P adapters/mg-dangerous-delivery/bsp_route.py <prefix> <out.json> [--id ID] [--name N]
        [--blurb B] [--cargo C] [--start X,Z] [--end X,Z] [--cell 2] [--max-length 3000]

`<prefix>` names a converted map's `<prefix>.json` and `<prefix>.bin` (dotbsp.mesh). A route in
that game is not geometry: it is a list of segments (length, turn, climb, walls, rails) the game
builds its own terrain from, so this reads the shape of the map's road and writes that shape.

1. Floors: every upward triangle (not sky, water, glass, foliage or tool textures) is rasterised
   into a 2.5D grid of floor levels, each marked road or not. Road is a road, asphalt, street,
   alley, gravel or path texture. A blended displacement named for a road is road at any alpha
   (the alpha paints snow or dirt on it); any other blend is road where the layer its vertex alpha
   shows (`free` at alpha 0, `free2` at 1) is, so a grass field with a gravel track finds the track.
2. Room: steep and downward triangles mark the heights they occupy; a floor with something
   between 0.8 m and 3.5 m above it, or under more than 0.9 m of water, cannot take a truck.
3. Route: Dijkstra over the floors (a step of at most 0.5 m plus 45% of the distance), road costing
   less the further it is from the road's edge, so the path keeps to the middle; off-road costs six
   times as much. The ends are the two road floors furthest apart by that cost (a double sweep) in
   the floor network holding most road, or `--start`/`--end` (game metres, x,z) when given. A map
   whose roads give under 500 m (a snowfield round one paved square) is crossed off-road instead.
4. Segments: the path is resampled, smoothed and cut into straights and bends (20 to 160 m). Turns
   and climbs carry their error forward so no segment passes the hand routes' steepest (1.9 degrees
   per metre, 14% grade; the game allows 2.2 and 18%, but a truck slides off 18% snow); a map
   steeper than that gives a flatter route. Width follows the road,
   a side with ground or a building above the road is a wall, a side that drops away a rail.

Challenges (traffic, boulders, works) are left to the game's overlay or a hand edit: they are
gameplay, not something the map says. Only the shape is read from the map.
"""
import heapq
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from dotbsp import mesh as _mesh  # noqa: E402

ROAD_WORDS = ("road", "asphalt", "tarmac", "street", "intsect", "alley")
SURFACE_WORDS = ROAD_WORDS + ("gravel", "path")   # a road in a non-blended texture; on a blend only the layer says
NOT_ROAD = ("barrier", "grate", "drain", "underwater", "sidewalk", "curb", "kerb", "sign")
SKIP_FLOOR = ("tools/", "skybox", "nodraw", "foliage", "generated:water", "generated:glass")
MOVERS = ("func_door", "func_button", "func_movelinear", "func_rotating", "func_tracktrain", "trigger")

FLOOR_NY = 0.7          # steeper than ~45 degrees is not a floor
WALL_NY = 0.5           # a triangle under this (or facing down) takes room
MERGE_Y = 0.8           # floor samples this close in one cell are one level
ROOM = (0.8, 3.5)       # a truck needs this band above the floor clear
MAX_LEVELS = 8
FORD = 0.9              # water a truck can drive through
OFF_ROAD = 6.0
SEG_MIN, SEG_MAX = 20.0, 160.0
BEND = 0.35             # degrees per metre: above this a sample is in a bend
MAX_TURN, MAX_GRADE = 2.2, 0.18   # game/dd_route_doc.gd's limits
DRIVE_TURN, DRIVE_GRADE = 1.9, 0.14   # the hand routes' steepest: a stand-in falls on 18% snow
OPEN_WIDTH = 9.0        # a route with no road under it (across country)
WIDTH = (6.0, 12.0)
CHECKPOINT_EVERY = 450.0
MIN_ROUTE = 500.0       # metres; roads shorter than this are crossed off-road instead


def is_road(name, words=SURFACE_WORDS):
    n = (name or "").lower()
    return any(w in n for w in words) and not any(w in n for w in NOT_ROAD)


def _skip(s, rec):
    if s.sky3d or s.water or s.glass or s.classname.startswith(MOVERS):
        return True
    names = (s.material or "").lower() + " " + str(rec.get("free") or s.generic or "").lower()
    return any(w in names for w in SKIP_FLOOR)


def _tris(s):
    v, idx = s.verts, s.index
    for t in range(0, len(idx), 3):
        a, b, c = idx[t], idx[t + 1], idx[t + 2]
        yield (a, b, c), (v[a][0], v[b][0], v[c][0])


def _normal(s, idx):
    """The stored vertex normals' mean: the winding follows the engine's front face, not y up."""
    n = [sum(s.verts[i][1][k] for i in idx) for k in range(3)]
    ln = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
    return (n[0] / ln, n[1] / ln, n[2] / ln) if ln > 1e-9 else None


class Grid:
    """Floor levels per cell: [y, road samples, all samples, snow samples]; room taken as whole metres."""

    def __init__(self, lo, hi, cell):
        self.cell, self.ox, self.oz = cell, lo[0], lo[1]
        self.nx = max(1, int(math.ceil((hi[0] - lo[0]) / cell)))
        self.nz = max(1, int(math.ceil((hi[1] - lo[1]) / cell)))
        self.levels = {}
        self.taken = {}
        self.water = {}

    def key(self, x, z):
        i, j = int((x - self.ox) / self.cell), int((z - self.oz) / self.cell)
        return i * self.nz + j if 0 <= i < self.nx and 0 <= j < self.nz else None

    def centre(self, k):
        return self.ox + (k // self.nz + 0.5) * self.cell, self.oz + (k % self.nz + 0.5) * self.cell

    def cover(self, p):
        """(cell, y) at each cell centre inside the triangle; the centroid's cell when none is."""
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = p
        den = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
        c = self.cell
        hit = False
        if abs(den) > 1e-9:
            i0 = max(0, int((min(ax, bx, cx) - self.ox) / c))
            i1 = min(self.nx - 1, int((max(ax, bx, cx) - self.ox) / c))
            j0 = max(0, int((min(az, bz, cz) - self.oz) / c))
            j1 = min(self.nz - 1, int((max(az, bz, cz) - self.oz) / c))
            for i in range(i0, i1 + 1):
                px = self.ox + (i + 0.5) * c
                for j in range(j0, j1 + 1):
                    pz = self.oz + (j + 0.5) * c
                    l1 = ((bz - cz) * (px - cx) + (cx - bx) * (pz - cz)) / den
                    l2 = ((cz - az) * (px - cx) + (ax - cx) * (pz - cz)) / den
                    l3 = 1.0 - l1 - l2
                    if l1 < -1e-6 or l2 < -1e-6 or l3 < -1e-6:
                        continue
                    hit = True
                    yield i * self.nz + j, l1 * ay + l2 * by + l3 * cy
        if not hit:
            k = self.key((ax + bx + cx) / 3.0, (az + bz + cz) / 3.0)
            if k is not None:
                yield k, (ay + by + cy) / 3.0

    def add_floor(self, k, y, road, snow):
        lv = self.levels.setdefault(k, [])
        for L in lv:
            if abs(L[0] - y) <= MERGE_Y:
                L[0] = max(L[0], y)
                L[1] += road
                L[2] += 1
                L[3] += snow
                return
        if len(lv) < MAX_LEVELS:
            lv.append([y, road, 1, snow])

    def add_taken(self, p):
        """Samples a steep or downward triangle at half a cell and marks the whole metres it fills."""
        edge = max(math.dist(p[0], p[1]), math.dist(p[1], p[2]), math.dist(p[2], p[0]))
        n = max(1, int(math.ceil(edge / (self.cell * 0.5))))
        for a in range(n + 1):
            for b in range(n + 1 - a):
                u, v = a / n, b / n
                w = 1.0 - u - v
                x = u * p[0][0] + v * p[1][0] + w * p[2][0]
                z = u * p[0][2] + v * p[1][2] + w * p[2][2]
                k = self.key(x, z)
                if k is not None:
                    self.taken.setdefault(k, set()).add(int(math.floor(u * p[0][1] + v * p[1][1] + w * p[2][1])))

    def open(self, k, y):
        t = self.taken.get(k)
        if t and any(m in t for m in range(int(math.floor(y + ROOM[0])), int(math.floor(y + ROOM[1])) + 1)):
            return False
        w = self.water.get(k)
        return w is None or w < y + FORD


def build_grid(doc, m, cell=2.0):
    """Rasterises the map's floors and the room above them."""
    floors, steep, water = [], [], []
    for s, rec in zip(m.surfaces, doc["surfaces"]):
        if s.sky3d:
            continue
        if s.water:
            water.extend(p for _, p in _tris(s))
            continue
        skip = _skip(s, rec)
        foliage = "foliage" in str(rec.get("free") or s.generic or "")
        blend = rec.get("free2") is not None
        for idx, p in _tris(s):
            n = _normal(s, idx)
            if n is None:
                continue
            if n[1] >= FLOOR_NY and not skip:
                if blend:
                    al = [s.alpha[i] if i < len(s.alpha) and s.alpha[i] is not None else 0.0 for i in idx]
                    layer = rec.get("free2") if sum(al) / 3.0 > 0.5 else rec.get("free")
                    road = is_road(s.material, ROAD_WORDS) or is_road(layer)
                else:
                    layer = rec.get("free") or ""
                    road = is_road(s.material) or is_road(layer)
                snow = "snow" in ((s.material or "") + " " + str(layer)).lower()
                floors.append((p, road, snow))
            elif n[1] < WALL_NY and not foliage and not s.glass:
                steep.append(p)
    if not floors:
        raise ValueError("no drivable floor in this map")
    lo = [min(min(q[0] for q in p) for p, _, _ in floors), min(min(q[2] for q in p) for p, _, _ in floors)]
    hi = [max(max(q[0] for q in p) for p, _, _ in floors), max(max(q[2] for q in p) for p, _, _ in floors)]
    g = Grid(lo, hi, cell)
    for p, road, snow in floors:
        for k, y in g.cover(p):
            g.add_floor(k, y, 1 if road else 0, 1 if snow else 0)
    for p in steep:
        g.add_taken(p)
    for p in water:
        for k, y in g.cover(p):
            g.water[k] = max(g.water.get(k, -1e9), y)
    return g


class Graph:
    """Nodes are cell * MAX_LEVELS + level, for the open floors."""

    def __init__(self, g):
        self.g = g
        self.y, self.road, self.snow = {}, set(), set()
        for k, lv in g.levels.items():
            for li, L in enumerate(lv):
                if g.open(k, L[0]):
                    nd = k * MAX_LEVELS + li
                    self.y[nd] = L[0]
                    if L[1] * 2 >= L[2]:
                        self.road.add(nd)
                    if L[3] * 2 >= L[2]:
                        self.snow.add(nd)
        self._adj = {}
        self.depth = self._depth()

    def neighbours(self, nd):
        out = self._adj.get(nd)
        if out is not None:
            return out
        g, out = self.g, []
        k, y = nd // MAX_LEVELS, self.y[nd]
        i, j = k // g.nz, k % g.nz
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if (di or dj) and 0 <= i + di < g.nx and 0 <= j + dj < g.nz:
                    kk = (i + di) * g.nz + j + dj
                    d = g.cell * (1.4142 if di and dj else 1.0)
                    best = None
                    for li in range(len(g.levels.get(kk, ()))):
                        nn = kk * MAX_LEVELS + li
                        yy = self.y.get(nn)
                        if yy is not None and abs(yy - y) <= 0.5 + 0.45 * d and (best is None or abs(yy - y) < abs(self.y[best] - y)):
                            best = nn
                    if best is not None:
                        out.append((best, d))
        self._adj[nd] = out
        return out

    def _depth(self):
        """Cells from each road floor to the nearest floor that is not road (or to nowhere)."""
        depth, frontier = {}, []
        for nd in self.road:
            nb = self.neighbours(nd)
            if len(nb) < 8 or any(n not in self.road for n, _ in nb):
                depth[nd] = 1
                frontier.append(nd)
        while frontier:
            nxt = []
            for nd in frontier:
                for n, _ in self.neighbours(nd):
                    if n in self.road and n not in depth:
                        depth[n] = depth[nd] + 1
                        nxt.append(n)
            frontier = nxt
        return depth

    def cost(self, nd, d):
        if nd in self.road:
            return d * (1.0 + 2.0 / (1.0 + self.depth.get(nd, 1)))
        return d * OFF_ROAD

    def dijkstra(self, src):
        dist, prev, heap = {src: 0.0}, {}, [(0.0, src)]
        while heap:
            c, nd = heapq.heappop(heap)
            if c > dist[nd]:
                continue
            for n, d in self.neighbours(nd):
                nc = c + self.cost(n, d)
                if nc < dist.get(n, 1e30):
                    dist[n], prev[n] = nc, nd
                    heapq.heappush(heap, (nc, n))
        return dist, prev

    def components(self, nodes):
        seen, comps = set(), []
        for s in nodes:
            if s in seen:
                continue
            comp, stack = [], [s]
            seen.add(s)
            while stack:
                nd = stack.pop()
                comp.append(nd)
                for n, _ in self.neighbours(nd):
                    if n in nodes and n not in seen:
                        seen.add(n)
                        stack.append(n)
            comps.append(comp)
        return sorted(comps, key=len, reverse=True)

    def nearest(self, x, z, among):
        return min(among, key=lambda nd: math.hypot(self.g.centre(nd // MAX_LEVELS)[0] - x, self.g.centre(nd // MAX_LEVELS)[1] - z))


def _far_pair(gr, pool, a=None, b=None):
    if a is None:
        dist, _ = gr.dijkstra(b if b is not None else next(iter(pool)))
        a = max((nd for nd in pool if nd in dist), key=dist.get)
    dist, prev = gr.dijkstra(a)
    if b is None:
        b = max((nd for nd in pool if nd in dist), key=dist.get)
    if b not in dist:
        raise ValueError("the route's ends are not connected")
    path = [b]
    while path[-1] != a:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def _metres(gr, path):
    return sum(math.dist((*gr.g.centre(p // MAX_LEVELS), gr.y[p]), (*gr.g.centre(q // MAX_LEVELS), gr.y[q])) for p, q in zip(path, path[1:]))


def longest_path(gr, start=None, end=None):
    """The road floors furthest apart (by cost, so along the road) in the floor network holding most road.

    A map's road texture breaks at fords, bridges and blends, so the ends may lie in different road
    patches; the off-road cost bridges the gaps. Patches under a tenth of the largest (a painted yard) are no end.
    A map whose roads give less than MIN_ROUTE (a snowfield with one paved square) is driven across
    country instead: the ends are then the floors furthest apart, and the cost still keeps to road on the way."""
    comps = gr.components(set(gr.y))
    comp = set(max(comps[:8], key=lambda c: (sum(1 for nd in c if nd in gr.road), len(c))))
    road = gr.road & comp
    pool = comp
    if road:
        wide = road | {n for nd in road for n, _ in gr.neighbours(nd)}
        patches = gr.components(wide)
        keep = max(50, 0.1 * len(patches[0]))
        pool = {nd for c in patches if len(c) >= keep for nd in c if nd in road} or road
    a = gr.nearest(*start, comp) if start else None
    b = gr.nearest(*end, comp) if end else None
    path = _far_pair(gr, pool, a, b)
    if pool is not comp and (a is None or b is None) and _metres(gr, path) < MIN_ROUTE:
        path = _far_pair(gr, comp, a, b)
    return path


def _resample(pts, step):
    out, carry = [pts[0]], 0.0
    for p, q in zip(pts, pts[1:]):
        d = math.hypot(q[0] - p[0], q[2] - p[2])
        t = step - carry
        while t <= d:
            f = t / d
            out.append(tuple(p[k] + (q[k] - p[k]) * f for k in range(3)))
            t += step
        carry = (carry + d) % step if d > 0 else carry
    if math.hypot(out[-1][0] - pts[-1][0], out[-1][2] - pts[-1][2]) > step * 0.3:
        out.append(pts[-1])
    return out


def _smooth(vals, r):
    n = len(vals)
    return [sum(vals[max(0, i - r):min(n, i + r + 1)]) / (min(n, i + r + 1) - max(0, i - r)) for i in range(n)]


def heading(dx, dz):
    """Degrees from -Z toward +X, so a turn to the right increases it."""
    return math.degrees(math.atan2(dx, -dz))


def _side(gr, x, z, y):
    """'high' (ground or a building above the road), 'low' (it drops away) or '' at a point beside the road."""
    g = gr.g
    k = g.key(x, z)
    lv = g.levels.get(k, []) if k is not None else []
    if any(y + 2.5 < L[0] for L in lv) or any(y + 1 <= t <= y + 6 for t in g.taken.get(k, ())):
        return "high"
    if any(abs(L[0] - y) <= 2.5 for L in lv):
        return ""
    return "low"


def _sides(left, right, kind):
    lf = left.count(kind) * 2 > len(left)
    rt = right.count(kind) * 2 > len(right)
    return "both" if lf and rt else "left" if lf else "right" if rt else "none"


def segments(gr, path, max_length=3000.0):
    """The path as the game's segments, and how much of it is road and snow."""
    g = gr.g
    pts = [(g.centre(nd // MAX_LEVELS)[0], gr.y[nd], g.centre(nd // MAX_LEVELS)[1]) for nd in path]
    halfw = [min(gr.depth.get(nd, 0), 8) * g.cell for nd in path]
    rs = _resample(pts, 2.0)
    xs, ys, zs = _smooth(_smooth([p[0] for p in rs], 6), 6), _smooth([p[1] for p in rs], 5), _smooth(_smooth([p[2] for p in rs], 6), 6)
    n = len(xs)
    if n < 4:
        raise ValueError("the route is too short to drive")
    ds = [0.0] + [math.hypot(xs[i] - xs[i - 1], zs[i] - zs[i - 1]) for i in range(1, n)]
    hd, prev = [], None
    for i in range(n):
        a, b = max(0, i - 2), min(n - 1, i + 2)
        h = heading(xs[b] - xs[a], zs[b] - zs[a])
        if prev is not None:
            h = prev + ((h - prev + 180.0) % 360.0 - 180.0)
        hd.append(h)
        prev = h
    bend = []
    for i in range(n):
        a, b = max(0, i - 3), min(n - 1, i + 3)
        span = sum(ds[a + 1:b + 1]) or 1.0
        bend.append(abs(hd[b] - hd[a]) / span > BEND)
    runs, start = [], 0
    for i in range(1, n):
        if bend[i] != bend[start] or i == n - 1:
            runs.append([start, i])
            start = i
    merged = []
    for r in runs:
        if merged and (sum(ds[r[0] + 1:r[1] + 1]) < SEG_MIN or sum(ds[merged[-1][0] + 1:merged[-1][1] + 1]) < SEG_MIN):
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    cuts = []
    for a, b in merged:
        ln = sum(ds[a + 1:b + 1])
        parts = max(1, int(math.ceil(ln / SEG_MAX)))
        idx = [a]
        acc, want = 0.0, ln / parts
        for i in range(a + 1, b + 1):
            acc += ds[i]
            if acc >= want * len(idx) and len(idx) < parts:
                idx.append(i)
        idx.append(b)
        cuts.extend(zip(idx, idx[1:]))
    # path index per resampled point, for width and road share
    cum_p = [0.0]
    for p, q in zip(pts, pts[1:]):
        cum_p.append(cum_p[-1] + math.hypot(q[0] - p[0], q[2] - p[2]))
    scale = cum_p[-1] / max(sum(ds), 1e-6)
    cum_r, acc = [], 0.0
    for d in ds:
        acc += d
        cum_r.append(acc * scale)
    pi, at = [], 0
    for c in cum_r:
        while at < len(cum_p) - 1 and cum_p[at + 1] <= c:
            at += 1
        pi.append(at)
    out, emitted_h, emitted_y, total = [], 0.0, 0.0, 0.0
    for a, b in cuts:
        ln = sum(ds[a + 1:b + 1])
        if ln < 2.0:
            continue
        want_h, want_y = hd[b] - hd[0], ys[b] - ys[0]
        turn = max(-DRIVE_TURN * ln, min(DRIVE_TURN * ln, want_h - emitted_h))
        climb = max(-DRIVE_GRADE * ln, min(DRIVE_GRADE * ln, want_y - emitted_y))
        emitted_h += turn
        emitted_y += climb
        widths = sorted(2.0 * halfw[pi[i]] + g.cell for i in range(a, b + 1) if path[pi[i]] in gr.road)
        width = widths[len(widths) // 2] if widths else OPEN_WIDTH
        width = round(max(WIDTH[0], min(WIDTH[1], width)) * 2.0) / 2.0
        left, right = [], []
        for i in range(a, b + 1, 2):
            r = math.radians(hd[i])
            rx, rz = math.cos(r), math.sin(r)
            off = width * 0.5 + 2.5
            left.append(_side(gr, xs[i] - rx * off, zs[i] - rz * off, ys[i]))
            right.append(_side(gr, xs[i] + rx * off, zs[i] + rz * off, ys[i]))
        seg = {"length": round(ln, 1), "turn": round(turn, 1), "climb": round(climb, 1),
               "wall": _sides(left, right, "high"), "rail": _sides(left, right, "low"), "width": float(width)}
        out.append(seg)
        total += ln
        if total >= max_length:
            break
    road = sum(1 for nd in path if nd in gr.road) / len(path)
    snow = sum(1 for nd in path if nd in gr.snow) / len(path)
    return out, {"road_share": round(road, 3), "snow_share": round(snow, 3),
                 "start": [round(pts[0][0], 1), round(pts[0][1], 1), round(pts[0][2], 1)],
                 "end": [round(pts[-1][0], 1), round(pts[-1][1], 1), round(pts[-1][2], 1)]}


def _float_safe(seg):
    """Turn and climb rounding must not push a segment past the game's limits."""
    ln = seg["length"]
    seg["turn"] = float(max(-MAX_TURN * ln, min(MAX_TURN * ln, seg["turn"])))
    seg["climb"] = float(max(-MAX_GRADE * ln, min(MAX_GRADE * ln, seg["climb"])))
    seg["length"] = float(ln)
    return seg


def route_doc(doc, m, rid=None, name=None, blurb=None, cargo="crates", start=None, end=None, cell=2.0, max_length=3000.0):
    """(route document, stats) for a read map."""
    mapname = str(doc.get("name") or "map")
    rid = rid or "dd_" + re.sub(r"[^a-z0-9_]", "_", mapname.lower())
    gr = Graph(build_grid(doc, m, cell))
    path = longest_path(gr, start, end)
    segs, stats = segments(gr, path, max_length)
    zone = {"name": name or mapname}
    if stats["snow_share"] > 0.3:
        zone.update(snow=round(min(1.0, stats["snow_share"]), 2), wind=0.3)
    total, mark = 0.0, CHECKPOINT_EVERY
    for i, s in enumerate(segs):
        _float_safe(s)
        s["zone"] = "map"
        total += s["length"]
        if total >= mark and i < len(segs) - 1:
            s["checkpoint"] = True
            mark += CHECKPOINT_EVERY
    climb = sum(abs(s["climb"]) for s in segs)
    widths = sorted(s["width"] for s in segs)
    route = {"format": 1, "kind": "route", "id": rid, "name": name or mapname,
             "author": "dot-map-convert bsp_route", "blurb": blurb or ("The longest road through %s." if stats["road_share"] >= 0.5 else "Across country over %s.") % mapname,
             "level": max(1, min(9, 1 + int(total // 700) + int(climb // 60))),
             "pay": int(max(300, round(total * 0.3 / 10.0) * 10)), "width": float(widths[len(widths) // 2]),
             "cargo": cargo, "zones": {"map": zone}, "segments": segs}
    stats.update(length=round(total, 1), segments=len(segs), nodes=len(gr.y), road_nodes=len(gr.road))
    return route, stats


def _xz(text):
    x, z = (float(v) for v in text.split(","))
    return x, z


def main(argv):
    args, opts, i = [], {}, 0
    while i < len(argv):
        if argv[i].startswith("--"):
            opts[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            args.append(argv[i])
            i += 1
    if len(args) != 2:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    doc, m = _mesh.read(args[0])
    route, stats = route_doc(doc, m, rid=opts.get("id"), name=opts.get("name"), blurb=opts.get("blurb"),
                             cargo=opts.get("cargo", "crates"),
                             start=_xz(opts["start"]) if "start" in opts else None,
                             end=_xz(opts["end"]) if "end" in opts else None,
                             cell=float(opts.get("cell", 2.0)), max_length=float(opts.get("max-length", 3000.0)))
    os.makedirs(os.path.dirname(os.path.abspath(args[1])), exist_ok=True)
    with open(args[1], "w") as f:
        json.dump(route, f, indent=1)
        f.write("\n")
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
