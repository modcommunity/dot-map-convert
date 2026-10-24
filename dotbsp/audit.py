"""Brush census and floor audit: what the source map has, against what a converted output collides with.

`census(bsp)` counts every brush by its owner's class and its CONTENTS kind (solid, detail, window,
grate, playerclip, npcclip, ladder, water, slime, trigger, origin, sky, nodraw-only, areaportal/hint/skip
and the rest), so a converter that drops a whole kind shows it as a row, not as a missing corridor.

`floors(bsp)` samples every exposed top face a body can stand on: the tops of player-solid brushes
(the world, func_detail merged into it, and every solid brush entity), no steeper than 45 degrees, with
a standing body's room above them, not inside the 3D sky room. Displacement tops are sampled too.

`check(samples, solid_at)` asks an output "is there ground under this point within a step?" and returns
the misses grouped by source class, contents kind and material. `boxes_ground` and `hulls_ground` are the
two outputs the family writes: a document's `boxes` (`{at, size, yaw}` in metres) and a `dot-bsp-mesh`'s
convex hulls. The CLI is `bsp.py audit`.
"""

import collections
import math
import random

from . import reader, units as _units

CONTENTS_AREAPORTAL, CONTENTS_TRANSLUCENT = 0x8000, 0x10000000
CONTENTS_ORIGIN, CONTENTS_HITBOX = 0x1000000, 0x40000000
CONTENTS_CURRENT_ANY = 0xFC0000
CONTENTS_TEAM1, CONTENTS_TEAM2 = 0x800, 0x1000
STEP = 18.0           # map units a body steps up; a floor whose output ground is further down is a hole
BODY = 64.0           # head room for a standing body (crouched is 36; 64 rejects ceiling tops)
GRID = 24.0           # map units between floor samples


def contents_kind(contents, names=()):
    """One word for a brush's CONTENTS flags (and its side materials, for the tool brushes)."""
    up = [n.upper() for n in names]
    if contents & CONTENTS_ORIGIN:
        return "origin"
    if contents & CONTENTS_AREAPORTAL:
        return "areaportal"
    if contents & reader.CONTENTS_LADDER:
        return "ladder"
    if contents & reader.CONTENTS_SLIME:
        return "slime"
    if contents & reader.CONTENTS_WATER:
        return "water"
    if contents & reader.CONTENTS_PLAYERCLIP and contents & reader.CONTENTS_MONSTERCLIP and not contents & reader.CONTENTS_SOLID:
        return "clip"
    if contents & reader.CONTENTS_PLAYERCLIP and not contents & reader.CONTENTS_SOLID:
        return "playerclip"
    if contents & reader.CONTENTS_MONSTERCLIP and not contents & reader.CONTENTS_SOLID:
        return "npcclip"
    if contents & reader.CONTENTS_WINDOW:
        return "window"
    if contents & reader.CONTENTS_GRATE:
        return "grate"
    if contents & reader.CONTENTS_SOLID:
        if up and all(n.startswith("TOOLS/") for n in up):
            if any("SKYBOX" in n or "SKY" == n.rsplit("/", 1)[-1] for n in up):
                return "sky"
            if any("INVISIBLE" in n for n in up):
                return "invisible"
            if any("NODRAW" in n for n in up):
                return "nodraw"
            if any("CLIP" in n for n in up):
                return "clip"
            return "tool"
        return "detail" if contents & reader.CONTENTS_DETAIL else "solid"
    if contents & reader.CONTENTS_MOVEABLE:
        return "moveable"
    if contents & reader.CONTENTS_MONSTER:
        return "monster"
    if contents == 0:
        return "empty"
    return "other:%x" % contents


def _owners(bsp):
    owners = {}
    for i, e in enumerate(bsp.entities):
        m = str(e.get("model", ""))
        if m.startswith("*") and m[1:].isdigit():
            owners[int(m[1:])] = i
    return owners


def brush_owners(bsp):
    """{brush index: (model, entity index or None, classname)}; a brush reached by two models keeps the lowest."""
    out = {}
    owners = _owners(bsp)
    for mi in range(len(bsp.models)):
        if mi > 0 and mi not in owners:
            continue
        ei = owners.get(mi)
        cls = bsp.entities[ei].get("classname", "?") if ei is not None else "worldspawn"
        for bi in bsp.model_brushes(mi):
            if bi < len(bsp.brushes) and bi not in out:
                out[bi] = (mi, ei, cls)
    return out


def _names(bsp, bi):
    first, count, _ = bsp.brushes[bi]
    out = []
    for s in bsp.brushsides[first:first + count]:
        if s[3] or s[1] < 0 or s[1] >= len(bsp.texinfo):
            continue
        out.append(bsp.side_material(s)[0])
    return out


def census(bsp):
    """Counter of (classname, contents kind) over every brush the map's models reach."""
    out = collections.Counter()
    for bi, (_mi, _ei, cls) in brush_owners(bsp).items():
        out[(cls, contents_kind(bsp.brushes[bi][2], _names(bsp, bi)))] += 1
    return out


class _BrushGrid:
    def __init__(self, bsp, items, cell=256.0):
        self.bsp, self.cell, self.cells = bsp, cell, collections.defaultdict(list)
        for bi, off in items:
            pts = bsp.brush_hull(bi)
            if not pts:
                continue
            lo = [min(p[k] for p in pts) + off[k] for k in range(3)]
            hi = [max(p[k] for p in pts) + off[k] for k in range(3)]
            for x in range(int(lo[0] // cell), int(hi[0] // cell) + 1):
                for y in range(int(lo[1] // cell), int(hi[1] // cell) + 1):
                    self.cells[(x, y)].append((bi, off, lo, hi))

    def inside(self, p, skip=None, eps=-0.5):
        for bi, off, lo, hi in self.cells.get((int(p[0] // self.cell), int(p[1] // self.cell)), ()):
            if bi == skip or not (lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1] and lo[2] <= p[2] <= hi[2]):
                continue
            if self.bsp.point_in_brush(bi, (p[0] - off[0], p[1] - off[1], p[2] - off[2]), eps):
                return True
        return False


def solid_brushes(bsp, solid_classes=None):
    """[(brush, offset, model, entity, classname)] for every player-solid brush of the world and of a solid brush entity."""
    from . import mesh as _mesh
    solid_classes = _mesh.SOLID_BRUSH_ENTITIES if solid_classes is None else solid_classes
    out = []
    for bi, (mi, ei, cls) in sorted(brush_owners(bsp).items()):
        if mi > 0 and cls not in solid_classes:
            continue
        if not bsp.brushes[bi][2] & reader.MASK_PLAYERSOLID:
            continue
        off = tuple(reader.entity_vec(bsp.entities[ei])) if ei is not None else (0.0, 0.0, 0.0)
        out.append((bi, off, mi, ei, cls))
    return out


def floors(bsp, grid=GRID, solid_classes=None, max_samples=200000, seed=1):
    """[(point in map units, classname, kind, material)] on every exposed standable top."""
    from . import mesh as _mesh
    items = solid_brushes(bsp, solid_classes)
    bg = _BrushGrid(bsp, [(bi, off) for bi, off, *_ in items])
    sky = _mesh.skybox_of(bsp)
    room = sky[2] if sky is not None else None
    out = []
    for bi, off, mi, ei, cls in items:
        names = _names(bsp, bi)
        kind = contents_kind(bsp.brushes[bi][2], names)
        if kind == "sky":
            continue
        pts = bsp.brush_hull(bi)
        if len(pts) < 4:
            continue
        planes = bsp.brush_planes(bi, off)
        tops = [pl for pl in planes if pl[2] >= 0.7071]
        if not tops:
            continue
        lo = [min(p[k] for p in pts) + off[k] for k in range(2)]
        hi = [max(p[k] for p in pts) + off[k] for k in range(2)]
        nx, ny = max(1, int((hi[0] - lo[0]) // grid)), max(1, int((hi[1] - lo[1]) // grid))
        top_name = _top_material(bsp, bi) or (names[0] if names else "?")
        for ix in range(nx):
            for iy in range(ny):
                x = lo[0] + (ix + 0.5) * (hi[0] - lo[0]) / nx
                y = lo[1] + (iy + 0.5) * (hi[1] - lo[1]) / ny
                z = min((d - a * x - b * y) / c for a, b, c, d in tops)
                p = (x, y, z)
                if not all(a * x + b * y + c * (z - 1.0) - d <= 0.6 for a, b, c, d in planes):
                    continue        # the top plane's line is outside the brush here (a wedge's corner)
                if room is not None and all(room[0][k] <= p[k] <= room[1][k] for k in range(3)):
                    continue
                if bg.inside((x, y, z + 2.0)) or bg.inside((x, y, z + BODY / 2)) or bg.inside((x, y, z + BODY - 2.0)):
                    continue
                if not _in_world(bsp, (x, y, z + 8.0)):
                    continue
                out.append(((x, y, z), cls, kind, top_name))
    if len(out) > max_samples:
        out = random.Random(seed).sample(out, max_samples)
    return out


def _top_material(bsp, bi):
    first, count, _ = bsp.brushes[bi]
    best = None
    for s in bsp.brushsides[first:first + count]:
        if s[3] or s[1] < 0 or s[1] >= len(bsp.texinfo):
            continue
        pl = bsp.planes[s[0]]
        if pl[2] > 0.7 and (best is None or pl[2] > best[0]):
            best = (pl[2], bsp.side_material(s)[0])
    return best[1] if best else None


def _in_world(bsp, p):
    """False in the void outside the sealed map (leaf -1's solid area or a leaf no cluster sees)."""
    from . import mesh as _mesh
    if not bsp.nodes:
        return True         # no tree to walk (a hand-built map): nothing tells the void apart
    leaf = _mesh.leaf_of(bsp, p)
    if leaf < 0 or leaf >= len(bsp.leafs):
        return False
    lf = bsp.leafs[leaf]
    return not (lf[0] & reader.CONTENTS_SOLID) and lf[1] != -1


def to_game(p, scale=_units.VISUAL, y0=0.0):
    return (p[0] * scale, p[2] * scale - y0, -p[1] * scale)


COLLIDES = frozenset(("solid", "detail", "window", "grate", "playerclip", "clip", "invisible", "nodraw", "tool", "ladder"))
"""Contents kinds a player is stopped by; water, slime, npcclip, triggers, origin, areaportal and the sky are not."""


def region(within=None, band=None, skips=()):
    """A `keep(game point)` from comma lists (see `bsp.py audit --within/--band/--skip`), or None for everything."""
    nums = lambda t: [float(v) for v in t.split(",")]  # noqa: E731
    w, b, sk = nums(within) if within else None, nums(band) if band else None, [nums(t) for t in skips]
    if not (w or b or sk):
        return None

    def keep(g):
        if w and not (w[0] <= g[0] <= w[2] and w[1] <= g[2] <= w[3]):
            return False
        if b and not b[0] <= g[1] <= b[1]:
            return False
        return not any(all(c[k] <= g[k] <= c[k + 3] for k in range(3)) for c in sk)
    return keep


def check(samples, out, scale=_units.VISUAL, y0=0.0, step=STEP):
    """{(class, kind, material): [missed, sampled]} and the missed game-space points; `out.ground(x, y, z, depth)`
    answers whether the output has solid within `depth` metres under the point."""
    res = collections.defaultdict(lambda: [0, 0])
    missed = []
    depth = step * scale
    for p, cls, kind, mat in samples:
        g = to_game(p, scale, y0)
        key = (cls, kind, mat)
        res[key][1] += 1
        if not out.ground(g[0], g[1] + 0.02, g[2], depth):
            res[key][0] += 1
            missed.append((g, cls, kind, mat))
    return dict(res), missed


def brush_points(bsp, bi, off, n=5):
    """Up to `n` points well inside one brush (its corner mean, then towards each corner), map units."""
    pts = bsp.brush_hull(bi)
    if len(pts) < 4:
        return []
    c = [sum(p[k] for p in pts) / len(pts) for k in range(3)]
    out = [c] + [[c[k] + 0.6 * (p[k] - c[k]) for k in range(3)] for p in pts[:n - 1]]
    return [(q[0] + off[0], q[1] + off[1], q[2] + off[2]) for q in out if bsp.point_in_brush(bi, q, -0.25)]


def brushes(bsp, out, scale=_units.VISUAL, y0=0.0, classes_of=None, keep=None):
    """{(class, kind): [brushes, collidable expected, collided]}: every brush the map's models reach, and
    of the player-solid ones whose owner should collide, how many the output holds (a point well inside
    each, in the output's solid). `classes_of(cls)` says whether a brush entity class should collide."""
    from . import mesh as _mesh
    classes_of = classes_of or (lambda c: c == "worldspawn" or c in _mesh.SOLID_BRUSH_ENTITIES)
    sky = _mesh.skybox_of(bsp)
    room = sky[2] if sky is not None else None
    table = collections.defaultdict(lambda: [0, 0, 0])
    lost = []
    for bi, (mi, ei, cls) in sorted(brush_owners(bsp).items()):
        kind = contents_kind(bsp.brushes[bi][2], _names(bsp, bi))
        row = table[(cls, kind)]
        row[0] += 1
        if kind not in COLLIDES or not classes_of(cls) or not bsp.brushes[bi][2] & reader.MASK_PLAYERSOLID:
            continue
        off = tuple(reader.entity_vec(bsp.entities[ei])) if ei is not None else (0.0, 0.0, 0.0)
        qs = brush_points(bsp, bi, off)
        if not qs or (room is not None and all(room[0][k] <= qs[0][k] <= room[1][k] for k in range(3))):
            continue
        if keep is not None and not keep(to_game(qs[0], scale, y0)):
            continue
        row[1] += 1
        if any(out.contains(*to_game(q, scale, y0)) for q in qs):
            row[2] += 1
        else:
            lost.append((bi, cls, kind, to_game(qs[0], scale, y0)))
    return dict(table), lost


class Boxes:
    """A document's boxes (`{at, size, yaw}`, metres, Godot axes; `solid: false` is skipped) as an output,
    with its terrain field (`terrain.Heightfield`) if it has one: anything under the field is buried and held."""

    def __init__(self, boxes, cell=4.0, terrain=None):
        self.cell, self.grid, self.terrain = cell, collections.defaultdict(list), terrain
        for b in boxes:
            if b.get("solid") is False:
                continue
            r = math.hypot(b["size"][0], b["size"][2]) / 2
            for gx in range(int((b["at"][0] - r) // cell), int((b["at"][0] + r) // cell) + 1):
                for gz in range(int((b["at"][2] - r) // cell), int((b["at"][2] + r) // cell) + 1):
                    self.grid[(gx, gz)].append(b)

    def _local(self, b, x, z):
        dx, dz = x - b["at"][0], z - b["at"][2]
        yaw = b.get("yaw", 0)
        if yaw:
            c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            dx, dz = c * dx - s * dz, s * dx + c * dz
        return dx, dz

    def _column(self, x, z, pad):
        for b in self.grid.get((int(x // self.cell), int(z // self.cell)), ()):
            dx, dz = self._local(b, x, z)
            if abs(dx) <= b["size"][0] / 2 + pad and abs(dz) <= b["size"][2] / 2 + pad:
                yield b

    def _terrain(self, x, z):
        return None if self.terrain is None else self.terrain.height(x, z)

    def contains(self, x, y, z, pad=0.05):
        h = self._terrain(x, z)
        if h is not None and y <= h + pad:
            return True
        return any(abs(y - b["at"][1]) <= b["size"][1] / 2 + pad for b in self._column(x, z, pad))

    def ground(self, x, y, z, depth):
        h = self._terrain(x, z)
        if h is not None and h >= y - depth:
            return True
        for b in self._column(x, z, 0.02):
            top, bottom = b["at"][1] + b["size"][1] / 2, b["at"][1] - b["size"][1] / 2
            if bottom - 0.02 <= y and top >= y - depth:
                return True
        return False


class Hulls:
    """A `dot-bsp-mesh`'s convex hulls (planes `n.p <= d` in metres) as an output."""

    def __init__(self, hulls, cell=4.0, kinds=("solid", "clip", "glass")):
        self.cell, self.grid = cell, collections.defaultdict(list)
        for h in hulls:
            if h.get("kind", "solid") not in kinds or not h["points"]:
                continue
            lo = [min(p[k] for p in h["points"]) for k in range(3)]
            hi = [max(p[k] for p in h["points"]) for k in range(3)]
            for gx in range(int(lo[0] // cell), int(hi[0] // cell) + 1):
                for gz in range(int(lo[2] // cell), int(hi[2] // cell) + 1):
                    self.grid[(gx, gz)].append((lo, hi, h["planes"]))

    def _near(self, x, z, pad):
        for lo, hi, planes in self.grid.get((int(x // self.cell), int(z // self.cell)), ()):
            if lo[0] - pad <= x <= hi[0] + pad and lo[2] - pad <= z <= hi[2] + pad:
                yield lo, hi, planes

    def contains(self, x, y, z, pad=0.05):
        return any(lo[1] - pad <= y <= hi[1] + pad and all(a * x + b * y + c * z - d <= pad for a, b, c, d in planes)
                   for lo, hi, planes in self._near(x, z, pad))

    def ground(self, x, y, z, depth):
        for lo, hi, planes in self._near(x, z, 0.02):
            if hi[1] < y - depth or lo[1] > y:
                continue
            # the hull's span on this vertical line, exactly: a thin slab falls between sampled heights
            bottom, top = -1e9, 1e9
            for a, b, c, d in planes:
                r = d + 0.02 - a * x - c * z
                if abs(b) < 1e-6:
                    if r < 0:
                        break
                elif b > 0:
                    top = min(top, r / b)
                else:
                    bottom = max(bottom, r / b)
            else:
                if bottom <= top and bottom <= y and top >= y - depth:
                    return True
        return False


def collision_hulls(hulls, sel, kinds=("solid", "clip", "glass")):
    """The hulls of `kinds` a document's `world_collision` selects: `models` whole, `flat` only hulls at
    most `flat_height` tall, none with its centre in a `skip` region [x0,y0,z0,x1,y1,z1], and, for a document
    cropped on purpose, only those touching `within` [x0,z0,x1,z1] and `band` [lo,hi] (game metres)."""
    within, band = sel.get("within"), sel.get("band")
    models, flat, fh = set(sel.get("models", [])), set(sel.get("flat", [])), float(sel.get("flat_height", 0.5))
    out = []
    for h in hulls:
        if not h["points"] or h.get("kind", "solid") not in kinds or (h["model"] not in models and h["model"] not in flat):
            continue
        lo = [min(p[k] for p in h["points"]) for k in range(3)]
        hi = [max(p[k] for p in h["points"]) for k in range(3)]
        if h["model"] not in models and hi[1] - lo[1] > fh:
            continue
        if within and (hi[0] < within[0] or lo[0] > within[2] or hi[2] < within[1] or lo[2] > within[3]):
            continue
        if band and (hi[1] <= band[0] or lo[1] >= band[1]):
            continue
        c = [(lo[k] + hi[k]) / 2 for k in range(3)]
        if any(r[0] <= c[0] <= r[3] and r[1] <= c[1] <= r[4] and r[2] <= c[2] <= r[5] for r in sel.get("skip", [])):
            continue
        out.append(h)
    return out


class Union:
    """Several outputs as one: a point is held when any of them holds it."""

    def __init__(self, *parts):
        self.parts = parts

    def contains(self, x, y, z, pad=0.05):
        return any(p.contains(x, y, z, pad) for p in self.parts)

    def ground(self, x, y, z, depth):
        return any(p.ground(x, y, z, depth) for p in self.parts)


def audit(bsp, out, scale=_units.VISUAL, y0=0.0, classes_of=None, grid=GRID, keep=None):
    """The whole report of one output: the brush table, the floor misses, and totals; `keep(game point)`
    limits both to where the output means to be whole."""
    table, lost = brushes(bsp, out, scale, y0, classes_of, keep)
    from . import mesh as _mesh
    solid = None
    if classes_of is not None:
        solid = {cls for (cls, _k) in table if cls != "worldspawn" and classes_of(cls)}
    samples = floors(bsp, grid=grid, solid_classes=solid if solid is not None else _mesh.SOLID_BRUSH_ENTITIES)
    if keep is not None:
        samples = [x for x in samples if keep(to_game(x[0], scale, y0))]
    fl, missed = check(samples, out, scale, y0)
    exp = sum(r[1] for r in table.values())
    got = sum(r[2] for r in table.values())
    return {"brushes": {"%s|%s" % k: v for k, v in sorted(table.items())},
            "brushes_expected": exp, "brushes_collided": got, "brushes_lost": lost,
            "floors": {"%s|%s|%s" % k: v for k, v in sorted(fl.items()) if v[0]},
            "floor_samples": len(samples), "floor_missed": len(missed), "floor_missed_points": missed}
