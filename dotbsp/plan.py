"""A floor plan from a map's walls, for maps whose walls do not close.

Lifted from mg-look-at-me's `bsp_layout.py`, which needed numpy and scipy (the tool is standard
library only, and a game's CI has neither), and extended for what it could not do: a Workshop
building whose walls are not all world brushes. Some are `func_brush` or `func_detail`
entities, some are static props (a fence, a bookcase row), and the shell has doorways and
broken windows, so a flood from the outside leaks in through every gap.

The method, all on a raster of `res` metres:

1. **Walls.** A world brush that blocks the player and stands through a storey (at one of the
   sampled heights, at least `wall_height` units tall) is rasterised by its bounding box; so
   is each brush entity whose class is in `wall_classes`, and each rectangle in `wall_rects`.
   A static prop in `wall_props` ({model substring: (width, depth) in units}) is rasterised as
   that footprint turned by its yaw.
2. **Seal.** The walls grow by `seal` metres before the outside is flooded, so a gap narrower
   than twice that does not let the outside in. The inside it finds is grown back by the same
   amount (never into a wall), so the seal costs no floor.
3. **Outside.** Free space touching the raster's edge is outside; the rest is the building.
4. **Erode.** The building shrinks by `erode` metres, which pinches a doorway shut and parts
   the rooms; blobs under `min_area` m2 are cupboards and dropped; each blob grows back by
   `erode` within the building.
5. **Rooms.** Each blob becomes rectangles on a coarse grid of `cell` metres (4 m for a game
   whose rooms are modules): cells at least `fill` blob, covered greedily by the widest run
   grown down while the whole run stays full. A rectangle one cell wide is a corridor.

Units: the document is in map units; `scale` is metres per unit and `bbox` is metres at that
scale. The player hull is 1.83 m only at `units.HULL` (0.0254), which is why look-at-me passed
it; the intermediate's default 0.01905 gives rooms a quarter smaller.
"""

import math

from . import units as _units

CELL_M = 4.0
DEFAULT_WALL_CLASSES = ("func_brush", "func_wall", "func_detail", "func_breakable")


class Raster:
    def __init__(self, bbox, res):
        self.x0, self.y0, x1, y1 = bbox
        self.res = res
        self.nx, self.ny = max(1, int((x1 - self.x0) / res)), max(1, int((y1 - self.y0) / res))
        self.cells = bytearray(self.nx * self.ny)

    def rect(self, ax, ay, bx, by):
        """Fill the metre rectangle (any order, clipped)."""
        i0 = max(0, int((min(ax, bx) - self.x0) / self.res))
        i1 = min(self.nx, int(math.ceil((max(ax, bx) - self.x0) / self.res)))
        j0 = max(0, int((min(ay, by) - self.y0) / self.res))
        j1 = min(self.ny, int(math.ceil((max(ay, by) - self.y0) / self.res)))
        for j in range(j0, j1):
            row = j * self.nx
            for i in range(i0, i1):
                self.cells[row + i] = 1

    def turned_rect(self, cx, cy, w, d, yaw):
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        r = math.hypot(w, d) / 2
        i0 = max(0, int((cx - r - self.x0) / self.res))
        i1 = min(self.nx, int(math.ceil((cx + r - self.x0) / self.res)))
        j0 = max(0, int((cy - r - self.y0) / self.res))
        j1 = min(self.ny, int(math.ceil((cy + r - self.y0) / self.res)))
        for j in range(j0, j1):
            for i in range(i0, i1):
                px, py = self.x0 + (i + 0.5) * self.res - cx, self.y0 + (j + 0.5) * self.res - cy
                if abs(px * c + py * s) <= w / 2 and abs(-px * s + py * c) <= d / 2:
                    self.cells[j * self.nx + i] = 1


def _neighbours(i, nx, ny):
    x, y = i % nx, i // nx
    if x > 0:
        yield i - 1
    if x < nx - 1:
        yield i + 1
    if y > 0:
        yield i - nx
    if y < ny - 1:
        yield i + nx


def dilate(mask, nx, ny, steps, allowed=None):
    """`mask` grown `steps` cells (4-neighbour), only into cells `allowed` (all when None)."""
    out = bytearray(mask)
    frontier = [i for i, v in enumerate(mask) if v]
    for _ in range(steps):
        nxt = []
        for i in frontier:
            for n in _neighbours(i, nx, ny):
                if not out[n] and (allowed is None or allowed[n]):
                    out[n] = 1
                    nxt.append(n)
        frontier = nxt
        if not frontier:
            break
    return out


def erode(mask, nx, ny, steps):
    """`mask` shrunk `steps` cells (4-neighbour); the raster's edge counts as empty."""
    dist = [0 if not v else -1 for v in mask]
    frontier = [i for i, v in enumerate(mask) if not v]
    # cells on the edge are one step from outside
    for i, v in enumerate(mask):
        if v:
            x, y = i % nx, i // nx
            if x in (0, nx - 1) or y in (0, ny - 1):
                dist[i] = 1
                frontier.append(i)
    d = 0
    cur = frontier
    # multi-source BFS: dist = steps to the nearest empty cell or edge
    while cur and d <= steps:
        d += 1
        nxt = []
        for i in cur:
            base = dist[i]
            for n in _neighbours(i, nx, ny):
                if dist[n] == -1:
                    dist[n] = base + 1
                    nxt.append(n)
        cur = nxt
    return bytearray(1 if v and (dist[i] == -1 or dist[i] > steps) else 0 for i, v in enumerate(mask))


def label(mask, nx, ny):
    """(labels, count): 4-connected components of the set cells, numbered from 1."""
    lab = [0] * len(mask)
    n = 0
    for s, v in enumerate(mask):
        if v and not lab[s]:
            n += 1
            lab[s] = n
            stack = [s]
            while stack:
                i = stack.pop()
                for m in _neighbours(i, nx, ny):
                    if mask[m] and not lab[m]:
                        lab[m] = n
                        stack.append(m)
    return lab, n


def walls(doc, raster, scale, zs, wall_height=60.0, wall_classes=DEFAULT_WALL_CLASSES,
          wall_rects=(), wall_props=None):
    """Rasterise the wall sources into `raster`; returns {"world": n, "entities": n, "rects": n,
    "props": n} so a caller can see which source supplied what."""
    S = scale
    n = {"world": 0, "entities": 0, "rects": 0, "props": 0}
    classes = set(wall_classes or ())
    model_class = {r.get("model_index"): r["classname"] for r in doc["entities"] if r.get("model_index")}
    for b in doc["brushes"]:
        if not b.get("player_solid") or "mins" not in b:
            continue
        mn, mx = b["mins"], b["maxs"]
        if not any(mn[2] <= z <= mx[2] for z in zs) or mx[2] - mn[2] < wall_height:
            continue
        if b["model"] == 0:
            kind = "world"
        elif model_class.get(b["model"]) in classes:
            kind = "entities"
        else:
            continue
        raster.rect(mn[0] * S, mn[1] * S, mx[0] * S, mx[1] * S)
        n[kind] += 1
    for x0, y0, x1, y1 in wall_rects:
        raster.rect(x0 * S, y0 * S, x1 * S, y1 * S)
        n["rects"] += 1
    for sp in doc.get("static_props", []):
        for frag, (w, d) in (wall_props or {}).items():
            if frag in sp["model"]:
                raster.turned_rect(sp["origin"][0] * S, sp["origin"][1] * S, w * S, d * S, sp["angles"][1])
                n["props"] += 1
                break
    return n


def extract(doc, bbox, zs, scale=_units.HULL, res=0.25, erode_m=0.75, min_area=24.0, seal_m=0.0,
            cell=CELL_M, fill=0.6, wall_height=60.0, wall_classes=DEFAULT_WALL_CLASSES,
            wall_rects=(), wall_props=None):
    """The plan of the building inside `bbox` (x0, y0, x1, y1 metres at `scale`) as a dict:
    {"format": 1, "cell": cell, "scale": scale, "rooms": [{x, z, w, d, blob, kind}], "walls":
    {source counts}, "blobs": n, "plan_m2": area}. Room cells are `cell` metres, counted from
    the bbox corner. See the module docstring for the method and the parameters."""
    R = Raster(bbox, res)
    counts = walls(doc, R, scale, zs, wall_height, wall_classes, wall_rects, wall_props)
    nx, ny, wall = R.nx, R.ny, R.cells
    seal = int(round(seal_m / res))
    sealed = dilate(wall, nx, ny, seal) if seal else wall
    free = bytearray(0 if v else 1 for v in sealed)
    lab, n = label(free, nx, ny)
    edge = set()
    for i in range(nx):
        edge.add(lab[i]); edge.add(lab[(ny - 1) * nx + i])
    for j in range(ny):
        edge.add(lab[j * nx]); edge.add(lab[j * nx + nx - 1])
    edge.discard(0)
    inside_s = bytearray(1 if free[i] and lab[i] not in edge else 0 for i in range(nx * ny))
    notwall = bytearray(0 if v else 1 for v in wall)
    inside = dilate(inside_s, nx, ny, seal, notwall) if seal else inside_s
    r = int(round(erode_m / res))
    core = erode(inside, nx, ny, r)
    blobs, nb = label(core, nx, ny)
    per = max(1, int(round(cell / res)))
    rooms = []
    members = {}
    for i, k in enumerate(blobs):
        if k:
            members.setdefault(k, []).append(i)
    for k in range(1, nb + 1):
        if len(members[k]) * res * res < min_area:
            continue
        seed = bytearray(nx * ny)
        for i in members[k]:
            seed[i] = 1
        # grown freely and then cut to the building, as the original did: growing only through
        # `inside` would not reach a cell the far side of a thin wall within r cells
        m = bytearray(a and b for a, b in zip(dilate(seed, nx, ny, r), inside))
        cells = {}
        for j in range(0, ny, per):
            for i in range(0, nx, per):
                tot = hit = 0
                for jj in range(j, min(ny, j + per)):
                    row = jj * nx
                    seg = m[row + i:row + min(nx, i + per)]
                    tot += len(seg)
                    hit += sum(seg)
                if tot and hit / tot >= fill:
                    cells[(i // per, j // per)] = True
        left = dict(cells)
        while left:
            ci, cj = min(left, key=lambda c: (c[1], c[0]))
            w = 1
            while (ci + w, cj) in left:
                w += 1
            d = 1
            while all((ci + t, cj + d) in left for t in range(w)):
                d += 1
            if w * d >= 2:
                rooms.append({"x": ci, "z": cj, "w": w, "d": d, "blob": k,
                              "kind": "corridor" if min(w, d) == 1 else "room"})
            for t in range(w):
                for u in range(d):
                    left.pop((ci + t, cj + u), None)
    return {"format": 1, "source": doc.get("source", {}).get("name"), "cell": cell, "scale": scale,
            "origin_m": [bbox[0], bbox[1]], "rooms": rooms, "walls": counts, "blobs": nb,
            "plan_m2": sum(q["w"] * q["d"] for q in rooms) * cell * cell,
            "inside_m2": round(sum(inside) * res * res, 1)}


def ascii_plan(doc, bbox, zs, scale=_units.HULL, res=0.25, cell=CELL_M, threshold=0.12, **wall_kw):
    """The wall plan at the game's coarse cell as text, north (map +Y) on top: '#' is a cell at
    least `threshold` wall, '.' open. For laying rooms over by hand."""
    R = Raster(bbox, res)
    walls(doc, R, scale, zs, **wall_kw)
    per = max(1, int(round(cell / res)))
    rows = []
    for j in range(0, R.ny, per):
        line = []
        for i in range(0, R.nx, per):
            tot = hit = 0
            for jj in range(j, min(R.ny, j + per)):
                seg = R.cells[jj * R.nx + i:jj * R.nx + min(R.nx, i + per)]
                tot += len(seg)
                hit += sum(seg)
            line.append("#" if tot and hit / tot >= threshold else ".")
        rows.append("".join(line))
    return "\n".join(reversed(rows))
