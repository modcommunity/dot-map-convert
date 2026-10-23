"""Displacement ground as a heightfield: what a game collides with and walks on a sculpted hill.

`boxes.terrain_cells` cuts terrain into a stepped box field, which a body cannot climb once a
slope rises more than a step per cell, so a hilly map's reachable ground ended at its first hill.
A `Heightfield` samples the displacement triangles on a regular grid instead; the game builds a
triangle shape from the same samples (dot-map's `DotMapTerrain`), so what collides and what the
flood walks are one surface. Everything here is in metres on Godot axes (y up).

A cell is split along its (i, j)-(i+1, j+1) diagonal, the same in `height` and in the shape. A
sample no triangle covers is a hole. Where triangles overlap (an overhang) the highest wins.

`encode` writes the dictionary `DotMapTerrain.from_dict` reads (format 1): heights quantised to
`step` metres, predicted from the left, upper and upper-left samples, the residuals as int16 LE
after a hole bitmask (LSB first, row-major, x fastest), zlib then base64, so a hilly yard of a few
hundred metres is a few kilobytes. `walk` is an optional mask in the same bit layout: the samples
a walker reached from the starts, which a game's AI graph takes as its ground.
"""

import base64
import math
import struct
import zlib

from . import boxes as _boxes

FORMAT = 1
# The steepest terrain a walker climbs, as rise per metre: 1.0 is 45 degrees, just under the
# family's 46 degree player slope limit.
WALK_RISE = 1.0
LEVELS = 10000


class Heightfield:
    def __init__(self, x0, z0, cell, nx, nz, heights):
        self.x0, self.z0, self.cell, self.nx, self.nz = float(x0), float(z0), float(cell), int(nx), int(nz)
        self.h = heights                       # list, row-major (x fastest), None for a hole

    @classmethod
    def from_tris(cls, tris, cell, bounds=None, min_ny=0.05):
        """Samples `tris` ([(x, y, z)] * 3, metres) every `cell` metres over `bounds`
        ((x0, z0, x1, z1), default the triangles' extent). Near-vertical triangles are skipped."""
        if not tris:
            return None
        if bounds is None:
            bounds = (min(p[0] for t in tris for p in t), min(p[2] for t in tris for p in t),
                      max(p[0] for t in tris for p in t), max(p[2] for t in tris for p in t))
        x0 = math.floor(bounds[0] / cell) * cell
        z0 = math.floor(bounds[1] / cell) * cell
        nx = int(math.ceil((bounds[2] - x0) / cell)) + 1
        nz = int(math.ceil((bounds[3] - z0) / cell)) + 1
        h = [None] * (nx * nz)
        eps = 1e-6
        for a, b, c in tris:
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            ny = uz * vx - ux * vz
            ln = math.sqrt((uy * vz - uz * vy) ** 2 + ny ** 2 + (ux * vy - uy * vx) ** 2)
            if ln < 1e-12 or abs(ny) / ln < min_ny:
                continue
            d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(d) < 1e-12:
                continue
            i0 = max(0, int(math.ceil((min(a[0], b[0], c[0]) - x0) / cell - eps)))
            i1 = min(nx - 1, int(math.floor((max(a[0], b[0], c[0]) - x0) / cell + eps)))
            j0 = max(0, int(math.ceil((min(a[2], b[2], c[2]) - z0) / cell - eps)))
            j1 = min(nz - 1, int(math.floor((max(a[2], b[2], c[2]) - z0) / cell + eps)))
            for j in range(j0, j1 + 1):
                pz = z0 + j * cell
                for i in range(i0, i1 + 1):
                    px = x0 + i * cell
                    l1 = ((b[2] - c[2]) * (px - c[0]) + (c[0] - b[0]) * (pz - c[2])) / d
                    l2 = ((c[2] - a[2]) * (px - c[0]) + (a[0] - c[0]) * (pz - c[2])) / d
                    l3 = 1.0 - l1 - l2
                    if l1 < -1e-4 or l2 < -1e-4 or l3 < -1e-4:
                        continue
                    y = l1 * a[1] + l2 * b[1] + l3 * c[1]
                    k = j * nx + i
                    if h[k] is None or y > h[k]:
                        h[k] = y
        if all(v is None for v in h):
            return None
        return cls(x0, z0, cell, nx, nz, h)

    def at(self, i, j):
        if 0 <= i < self.nx and 0 <= j < self.nz:
            return self.h[j * self.nx + i]
        return None

    def sample_pos(self, i, j):
        return self.x0 + i * self.cell, self.z0 + j * self.cell

    def height(self, x, z):
        """The surface's height at (x, z), or None over a hole or outside."""
        fx, fz = (x - self.x0) / self.cell, (z - self.z0) / self.cell
        i, j = int(math.floor(fx)), int(math.floor(fz))
        if i == self.nx - 1 and fx - i < 1e-9:
            i -= 1
        if j == self.nz - 1 and fz - j < 1e-9:
            j -= 1
        if i < 0 or j < 0 or i >= self.nx - 1 or j >= self.nz - 1:
            return None
        fx, fz = fx - i, fz - j
        h00, h11 = self.at(i, j), self.at(i + 1, j + 1)
        if fx >= fz:
            h10 = self.at(i + 1, j)
            if h00 is None or h10 is None or h11 is None:
                return None
            return h00 + fx * (h10 - h00) + fz * (h11 - h10)
        h01 = self.at(i, j + 1)
        if h00 is None or h01 is None or h11 is None:
            return None
        return h00 + fz * (h01 - h00) + fx * (h11 - h01)

    def count(self):
        return sum(1 for v in self.h if v is not None)

    def cropped(self, keep, margin):
        """A copy over the samples within `margin` samples of one `keep(i, j)` accepts, the rest
        holes, trimmed to their bounds. None when nothing is kept."""
        near = [False] * (self.nx * self.nz)
        any_kept = False
        for j in range(self.nz):
            for i in range(self.nx):
                if self.h[j * self.nx + i] is not None and keep(i, j):
                    any_kept = True
                    for jj in range(max(0, j - margin), min(self.nz, j + margin + 1)):
                        for ii in range(max(0, i - margin), min(self.nx, i + margin + 1)):
                            near[jj * self.nx + ii] = True
        if not any_kept:
            return None
        ks = [k for k in range(len(near)) if near[k] and self.h[k] is not None]
        i0, i1 = min(k % self.nx for k in ks), max(k % self.nx for k in ks)
        j0, j1 = min(k // self.nx for k in ks), max(k // self.nx for k in ks)
        nx, nz = i1 - i0 + 1, j1 - j0 + 1
        h = [None] * (nx * nz)
        for j in range(nz):
            for i in range(nx):
                k = (j + j0) * self.nx + i + i0
                if near[k]:
                    h[j * nx + i] = self.h[k]
        return Heightfield(self.x0 + i0 * self.cell, self.z0 + j0 * self.cell, self.cell, nx, nz, h)

    def encode(self, step=0.05, walk=None, mat=""):
        """The dictionary `DotMapTerrain.from_dict` reads. `walk` is a set of (i, j) samples."""
        known = [v for v in self.h if v is not None]
        base = min(known)
        step = max(step, (max(known) - base) / LEVELS)
        q = [None if v is None else int(round((v - base) / step)) for v in self.h]
        nx = self.nx
        mask = _bits(v is not None for v in q)
        res = bytearray()
        for k, v in enumerate(q):
            if v is None:
                continue
            res += struct.pack("<h", v - _predict(q, nx, k))
        raw = bytes(mask) + bytes(res)
        out = {"format": FORMAT, "origin": [round(self.x0, 4), round(self.z0, 4)], "cell": self.cell,
               "size": [self.nx, self.nz], "base": round(base, 4), "step": round(step, 6),
               "bytes": len(raw), "data": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}
        if walk is not None:
            wm = bytes(_bits((k % nx, k // nx) in walk for k in range(len(q))))
            out["walk"] = base64.b64encode(zlib.compress(wm, 9)).decode("ascii")
        if mat:
            out["mat"] = mat
        return out

    @classmethod
    def decode(cls, d):
        """The heightfield (quantised) and the walk set (or None) from `encode`'s dictionary."""
        nx, nz = int(d["size"][0]), int(d["size"][1])
        n = nx * nz
        raw = zlib.decompress(base64.b64decode(d["data"]))
        nmask = (n + 7) // 8
        q = [None] * n
        off = nmask
        for k in range(n):
            if raw[k >> 3] >> (k & 7) & 1:
                q[k] = struct.unpack_from("<h", raw, off)[0] + _predict(q, nx, k)
                off += 2
        base, step = float(d["base"]), float(d["step"])
        hf = cls(d["origin"][0], d["origin"][1], d["cell"], nx, nz, [None if v is None else base + v * step for v in q])
        walk = None
        if "walk" in d:
            wm = zlib.decompress(base64.b64decode(d["walk"]))
            walk = {(k % nx, k // nx) for k in range(n) if wm[k >> 3] >> (k & 7) & 1}
        return hf, walk


def _predict(q, nx, k):
    i = k % nx
    left = q[k - 1] if i > 0 else None
    up = q[k - nx] if k >= nx else None
    if left is not None and up is not None:
        ul = q[k - nx - 1] if i > 0 else None
        if ul is not None:
            return min(max(left + up - ul, 0), LEVELS)
    if left is not None:
        return left
    if up is not None:
        return up
    return 0


def _bits(flags):
    out = bytearray()
    for k, f in enumerate(flags):
        if k % 8 == 0:
            out.append(0)
        if f:
            out[-1] |= 1 << (k % 8)
    return out


def fit(tris, keep_bounds, budget, cells=(1.0, 1.5, 2.0, 3.0, 4.0, 6.0), margin_m=12.0, keep=None, step=0.05):
    """The finest heightfield over `keep_bounds` ((x0, z0, x1, z1) metres) whose encoding fits
    `budget` bytes, holes further than `margin_m` from a sample `keep(x, z)` accepts. Returns
    (heightfield, encoded size) or (None, 0)."""
    last = (None, 0)
    for cell in cells:
        b = (keep_bounds[0] - margin_m, keep_bounds[1] - margin_m, keep_bounds[2] + margin_m, keep_bounds[3] + margin_m)
        hf = Heightfield.from_tris(tris, cell, b)
        if hf is None:
            return None, 0
        if keep is not None:
            hf = hf.cropped(lambda i, j: keep(*hf.sample_pos(i, j)), max(1, int(math.ceil(margin_m / cell))))
            if hf is None:
                return None, 0
        size = len(hf.encode(step)["data"])
        last = (hf, size)
        if size <= budget:
            return last
    return last


def walk_points(hf, walk, spacing):
    """Points every `spacing` metres whose nearest sample is in `walk`, on the surface; the same
    ones `DotMapTerrain.walk_points` places (keep the arithmetic identical)."""
    out = []
    if not walk or spacing <= 0:
        return out
    count_x = int((hf.nx - 1) * hf.cell / spacing)
    count_z = int((hf.nz - 1) * hf.cell / spacing)
    for b in range(count_z):
        z = hf.z0 + (b + 0.5) * spacing
        j = math.floor((z - hf.z0) / hf.cell + 0.5)
        for a in range(count_x):
            x = hf.x0 + (a + 0.5) * spacing
            i = math.floor((x - hf.x0) / hf.cell + 0.5)
            if i >= hf.nx or j >= hf.nz or (i, j) not in walk:
                continue
            y = hf.height(x, z)
            if y is not None:
                out.append((x, y, z))
    return out


def game_tris(tris, scale, y0=0.0):
    """Map-unit displacement triangles to metres on Godot axes (units.to_game)."""
    return [tuple((p[0] * scale, p[2] * scale - y0, -p[1] * scale) for p in t) for t in tris]


def covered(hf, x, z, spans, head):
    """The terrain height at (x, z) when nothing in `spans` ((lo, hi) of boxes over the point)
    sits within `head` above it and it is not inside one; else None."""
    h = hf.height(x, z)
    if h is None:
        return None
    for lo, hi in spans:
        if lo < h + head and hi > h + 0.05:
            return None
    return h


def add_surfaces(hf, surf, spans_at, cell, head):
    """Puts the terrain's height at each flood cell's centre into `surf` ({(ix, iz): [heights]})
    and returns the set of (ix, iz, h) that are terrain. `spans_at(ix, iz)` gives the (lo, hi)
    of the boxes over a cell's centre: ground under a box within `head` is not stood on, a box
    floor within 0.12 m of the ground is that floor, and a box top buried less than `head` under
    it is no floor."""
    out = set()
    x1, z1 = hf.x0 + (hf.nx - 1) * hf.cell, hf.z0 + (hf.nz - 1) * hf.cell
    for ix in range(int(math.floor(hf.x0 / cell)), int(math.floor(x1 / cell)) + 1):
        for iz in range(int(math.floor(hf.z0 / cell)), int(math.floor(z1 / cell)) + 1):
            h = covered(hf, (ix + 0.5) * cell, (iz + 0.5) * cell, spans_at(ix, iz), head)
            if h is None:
                continue
            h = round(h, 2)
            have = surf.get((ix, iz), [])
            if any(abs(s - h) <= 0.12 for s in have):
                continue
            surf[(ix, iz)] = sorted([s for s in have if not (h - head < s < h)] + [h])
            out.add((ix, iz, h))
    return out


def move(dh, cell, drop):
    """Between two terrain surfaces `cell` apart: "walk" up or down a slope a walker climbs,
    "drop" down a steeper one (no further than `drop`), None up it."""
    if abs(dh) <= cell * WALK_RISE + 1e-6:
        return "walk"
    if -drop <= dh < 0:
        return "drop"
    return None


def walk_samples(hf, seen_terrain, cell):
    """The heightfield samples (i, j) beside a flood cell walked on terrain ({(ix, iz)})."""
    out = set()
    for j in range(hf.nz):
        for i in range(hf.nx):
            x, z = hf.sample_pos(i, j)
            ix, iz = int(math.floor(x / cell)), int(math.floor(z / cell))
            if any((ix + a, iz + b) in seen_terrain for a in (-1, 0) for b in (-1, 0)):
                out.add((i, j))
    return out


def _v3(x, y, z):
    return [round(x, 3), round(y, 3), round(z, 3)]


def terrain_tris(bsp):
    """The map's displacement triangles, in map units."""
    tris = []
    for f in bsp.model_faces(0):
        if f[6] >= 0:
            tris += bsp.displacement_tris(f)
    return tris


def swap_terrain(doc, tris, mat, tint, budget=24000, scale=0.01905):
    """Replaces the stepped box field `--terrain` cut with dot-map's heightfield (`doc["terrain"]`).

    The field is found in the finished document by cutting it again and matching boxes, which also
    gives the shift the importer moved the map by, so this runs on a fresh import and on a
    committed document (`--graft-terrain`) alike. What stood on a box of the field is set down on
    the heightfield instead; the rest of the document is untouched."""
    cells = []
    for c in _boxes.terrain_cells(tris):
        (x0, x1), (y0, y1), (z0, z1) = c["x"], c["z"], c["y"]
        x0, x1, y0, y1, z0, z1 = x0 * scale, x1 * scale, y0 * scale, y1 * scale, -z1 * scale, -z0 * scale
        if x1 - x0 <= 0.001 or y1 - y0 <= 0.001 or z1 - z0 <= 0.001:
            continue
        cells.append((_v3((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), _v3(x1 - x0, y1 - y0, z1 - z0)))
    want_tint = list(tint) if tint else None
    by_size = {}
    for b in doc["boxes"]:
        if b.get("mat") == mat and b.get("tint") == want_tint and b.get("solid", True):
            by_size.setdefault(tuple(b["size"]), []).append(b)
    votes = {}
    for at, size in cells[::max(1, len(cells) // 300)]:
        for b in by_size.get(tuple(size), ()):
            k = tuple(round(b["at"][i] - at[i], 3) for i in range(3))
            votes[k] = votes.get(k, 0) + 1
    if not votes:
        raise SystemExit("swap_terrain: no box of the document matches the stepped field (mat %s)" % mat)
    shift = max(votes, key=votes.get)
    index = {(tuple(round(b["at"][i], 3) for i in range(3)), tuple(b["size"])): b for bs in by_size.values() for b in bs}
    old = []
    for at, size in cells:
        b = index.get((tuple(round(at[i] + shift[i], 3) for i in range(3)), tuple(size)))
        if b is not None:
            old.append(b)
    if len(old) < max(20, len(cells) * 0.25):
        raise SystemExit("swap_terrain: only %d of %d field boxes found; the document was not cut with this field" % (len(old), len(cells)))
    gone = {id(b) for b in old}
    doc["boxes"][:] = [b for b in doc["boxes"] if id(b) not in gone]
    lo = [min(b["at"][i] - b["size"][i] / 2 for b in old) for i in range(3)]
    hi = [max(b["at"][i] + b["size"][i] / 2 for b in old) for i in range(3)]
    moved = [tuple(p[i] + shift[i] for i in range(3)) for t in game_tris(tris, scale) for p in t]
    gtris = [tuple(moved[k:k + 3]) for k in range(0, len(moved), 3)]
    # Only where the document had field boxes: the importer left out the rest (far scenery, a
    # roof's snow) on purpose, and ground there would stand in a doorway.
    grid = {}
    for b in old:
        for gx in range(int((b["at"][0] - b["size"][0] / 2) // 4), int((b["at"][0] + b["size"][0] / 2) // 4) + 1):
            for gz in range(int((b["at"][2] - b["size"][2] / 2) // 4), int((b["at"][2] + b["size"][2] / 2) // 4) + 1):
                grid.setdefault((gx, gz), []).append(b)

    def under_field(x, z):
        return any(abs(x - b["at"][0]) <= b["size"][0] / 2 + 0.01 and abs(z - b["at"][2]) <= b["size"][2] / 2 + 0.01 for b in grid.get((int(x // 4), int(z // 4)), ()))

    # And only the layer the field had: displacements overlap (a roof's snow over the ground), and
    # the heightfield keeps the highest, a cliff in a doorway where the field took the ground.
    def on_layer(t):
        cx, cy, cz = (sum(p[i] for p in t) / 3 for i in range(3))
        return any(abs(cx - b["at"][0]) <= b["size"][0] / 2 + 0.01 and abs(cz - b["at"][2]) <= b["size"][2] / 2 + 0.01
                   and abs(cy - (b["at"][1] + b["size"][1] / 2)) <= 1.5 for b in grid.get((int(cx // 4), int(cz // 4)), ()))

    gtris = [t for t in gtris if on_layer(t)]
    hf, size = fit(gtris, (lo[0], lo[2], hi[0], hi[2]), budget, margin_m=0.5, keep=under_field)
    if hf is None:
        raise SystemExit("swap_terrain: the displacements produced no heightfield")
    enc = hf.encode(0.05, None, mat)
    if tint:
        enc["tint"] = list(tint)
    ground = Heightfield.decode(enc)[0]
    tops = [(b["at"][0] - b["size"][0] / 2, b["at"][0] + b["size"][0] / 2, b["at"][2] - b["size"][2] / 2, b["at"][2] + b["size"][2] / 2, b["at"][1] + b["size"][1] / 2) for b in old]

    def land(o, tag):
        x, y, z = o["at"]
        for x0, x1, z0, z1, top in tops:
            if x0 <= x <= x1 and z0 <= z <= z1 and abs(y - top) < 0.12:
                h = ground.height(x, z)
                if h is not None:
                    o["at"] = [x, round(h, 3), z]
                    counts[tag] = counts.get(tag, 0) + 1
                return

    counts = {}
    for o in doc.get("props", []):
        land(o, "props")
    for side in doc.get("spawns", {}).values():
        for o in side:
            land(o, "spawns")
    for o in doc.get("toys", []):
        land(o, "toys")
    doc["terrain"] = enc
    print("terrain: %d field boxes -> %dx%d heightfield at %.1f m, %d bytes; set down on it: %s" % (len(old), ground.nx, ground.nz, ground.cell, size, counts or "nothing"))
    return ground
