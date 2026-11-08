#!/usr/bin/env python3 -P
"""Convert a compiled map (dotbsp intermediate JSON) into a Look At Me house layout, automatically.

Look At Me draws its houses from rooms on a 4 m grid (doors, keys, witch walks and the
furniture proof all read that grid), so a converted house is the source's plan, not its
meshes: every storey's walkable, roofed floor is rasterised, pinched apart at its doorways,
labelled into rooms, and each room is laid on the grid. Which room opens into which is the
source's (a door is only cut where the source had an opening), the rooms come out in a tree
from the source's player start, and the builder (mg-look-at-me tools/build_levels.py) then
deals puzzles, furniture and witches on it.

    python3 -P bsp_house.py intermediate.json spec.json --out layout.json [--ascii]

The spec (in the game's repository, next to the layout it makes) holds every choice: the scale,
the storeys, the stairs and the alterations (mirror, rooms dropped or renamed). The same
intermediate and spec give the same layout, byte for byte. Needs numpy only.
"""
import argparse, hashlib, json, math, sys
from collections import deque
import numpy as np

CELL = 4.0
RES = 0.25  # raster cell, source metres
DIRS = {"n": (0, 1), "e": (1, 0), "s": (0, -1), "w": (-1, 0)}
# Brush entities that are walls; doors, glass and triggers are openings or nothing.
WALL_CLASSES = {None, "func_brush", "func_wall", "func_detail", "func_wall_toggle"}
EYE = 56  # map units over a floor where a wall is looked for (about knee to chest)


def shift(m, dy, dx):
    out = np.zeros_like(m)
    h, w = m.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = m[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def erode(m, r):
    for _ in range(r):
        m = m & shift(m, 1, 0) & shift(m, -1, 0) & shift(m, 0, 1) & shift(m, 0, -1)
    return m


def label(m):
    """4-connected components of a boolean raster, numbered from 1 in raster order."""
    lab = np.zeros(m.shape, np.int32)
    h, w = m.shape
    n = 0
    for start in zip(*np.nonzero(m)):
        if lab[start]:
            continue
        n += 1
        lab[start] = n
        q = deque([start])
        while q:
            y, x = q.popleft()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                v, u = y + dy, x + dx
                if 0 <= v < h and 0 <= u < w and m[v, u] and not lab[v, u]:
                    lab[v, u] = n
                    q.append((v, u))
    return lab, n


def grow_labels(lab, inside, steps):
    """Labels spread back over the pixels the erosion took, never across a wall."""
    for _ in range(steps):
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            src = shift(lab, dy, dx)
            lab = np.where(inside & (lab == 0) & (src > 0), src, lab)
    return lab


class Raster:
    def __init__(self, doc, spec):
        self.S = spec["scale"]
        self.walls = []
        ent = {e["index"]: e["classname"] for e in doc["entities"]}
        owner = {m["index"]: ent.get(m["entity"]) for m in doc["models"]}
        for b in doc["brushes"]:
            cls = None if b["model"] == 0 else owner.get(b["model"])
            if b["player_solid"] and cls in WALL_CLASSES:
                self.walls.append((b["mins"], b["maxs"]))
        mn = np.array([w[0] for w in self.walls]) * self.S
        mx = np.array([w[1] for w in self.walls]) * self.S
        x0, y0, x1, y1 = spec.get("bbox") or (mn[:, 0].min(), mn[:, 1].min(), mx[:, 0].max(), mx[:, 1].max())
        self.x0, self.y0 = x0, y0
        self.nx, self.ny = int(math.ceil((x1 - x0) / RES)), int(math.ceil((y1 - y0) / RES))

    def span(self, mins, maxs):
        S = self.S
        i0 = max(0, int(math.floor((mins[0] * S - self.x0) / RES))); i1 = min(self.nx, int(math.ceil((maxs[0] * S - self.x0) / RES)))
        j0 = max(0, int(math.floor((mins[1] * S - self.y0) / RES))); j1 = min(self.ny, int(math.ceil((maxs[1] * S - self.y0) / RES)))
        return (slice(j0, j1), slice(i0, i1)) if i1 > i0 and j1 > j0 else None

    def storey(self, lo, hi):
        """Walkable, roofed and not wall: the pixels whose floor top is from lo to hi map units."""
        return self.storey_parts(lo, hi)[0]

    def storey_parts(self, lo, hi):
        """The storey's inside, each pixel's floor top (map units) and its outside: walkable, not wall, open to the sky."""
        top = np.full((self.ny, self.nx), -1e9)
        for mins, maxs in self.walls:
            if lo <= maxs[2] <= hi:
                s = self.span(mins, maxs)
                if s:
                    top[s] = np.maximum(top[s], maxs[2])
        floor = top > -1e9
        wall = np.zeros_like(floor)
        roof = np.zeros_like(floor)
        for mins, maxs in self.walls:
            s = self.span(mins, maxs)
            if not s:
                continue
            t = top[s]
            wall[s] |= (mins[2] <= t + EYE) & (maxs[2] >= t + EYE) & (maxs[2] - t >= 40)
            roof[s] |= (mins[2] > t + 72) & (mins[2] <= t + 640)
        return floor & ~wall & roof, top, floor & ~wall & ~roof


def rects(cells):
    """A set of cells as rectangles, biggest first (so a hall stays one room)."""
    left = set(cells)
    out = []
    while left:
        best = None
        for (cx, cz) in sorted(left):
            for w in range(1, 64):
                if (cx + w - 1, cz) not in left:
                    break
                d = 1
                while all((cx + t, cz + d) in left for t in range(w)):
                    d += 1
                key = (w * d, -abs(w - d))
                if best is None or key > best[0]:
                    best = (key, cx, cz, w, d)
        _, cx, cz, w, d = best
        out.append((cx, cz, w, d))
        for t in range(w):
            for u in range(d):
                left.discard((cx + t, cz + u))
    return out


def stair_cells(st):
    return {(st["x"] + i, st["z"] + j) for i in range(st["w"]) for j in range(st["d"])}


def landing(st, high):
    """The cells at a stair's foot (or head), as the builder's stair_landing reads them (its n is -z)."""
    x, z, w, d, up = st["x"], st["z"], st["w"], st["d"], st["up"]
    if up in "ew":
        col = (x + w - 1 if up == "e" else x) if high else (x if up == "e" else x + w - 1)
        return {(col, z + j) for j in range(d)}
    row = (z + d - 1 if up == "s" else z) if high else (z if up == "s" else z + d - 1)
    return {(x + i, row) for i in range(w)}


NAME_WORDS = [  # a source prop in a room -> what the room is called (the furniture is ours)
    ("bed", "Ward"), ("toilet", "Washroom"), ("sink", "Washroom"), ("bath", "Bath House"), ("shower", "Shower Room"),
    ("treatment", "Treatment Room"), ("wheel_chair", "Day Room"), ("desk", "Office"), ("filing", "Records"), ("book", "Library"),
    ("stove", "Kitchen"), ("fridge", "Kitchen"), ("pipe", "Boiler Room"), ("powerbox", "Plant Room"), ("gasmeter", "Plant Room"),
    ("camera", "Night Station"), ("chair", "Day Room"), ("table", "Refectory"),
]
ROOM_NAMES = ["Day Room", "Ward", "Refectory", "Office", "Linen Store", "Treatment Room", "Visiting Room", "Dispensary", "Records",
              "Isolation Room", "Matron's Room", "Chapel", "Laundry", "Kitchen", "Library", "Hydrotherapy", "Workshop", "Porter's Lodge"]
CORRIDORS = ["Corridor", "Ward Corridor", "Service Corridor", "Long Corridor"]
ROMAN = ["", "", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def convert(doc, spec):
    """The layout and a few counts; every choice is the spec's."""
    ras = Raster(doc, spec)
    S, grow = spec["scale"], spec["grow"]
    per = CELL / grow / RES  # raster pixels per game cell
    gw, gh = int(math.ceil(ras.nx / per)), int(math.ceil(ras.ny / per))
    mirror = spec.get("mirror", False)
    alter = spec.get("alter", {})
    stairs = spec.get("stairs", [])
    r_px = int(round(spec.get("erode", 0.5) / RES))

    pieces = []
    linked = set()
    for st in spec["storeys"]:
        f = st["floor"]
        inside = ras.storey(*st["z"])
        lab, n = label(erode(inside, r_px))
        sizes = np.bincount(lab.ravel(), minlength=n + 1)
        keep = sizes * RES * RES >= spec.get("min_area", 3.0)
        keep[0] = False
        lab = np.where(keep[lab], lab, 0)
        lab = grow_labels(lab, inside, r_px + 2)
        # Two source rooms open into each other where their pixels meet along half a metre or more.
        for dy, dx in ((1, 0), (0, 1)):
            b = shift(lab, -dy, -dx)
            m = (lab > 0) & (b > 0) & (lab != b)
            if m.any():
                pairs, counts = np.unique(np.stack([lab[m], b[m]], 1), axis=0, return_counts=True)
                for (p, q), c in zip(pairs.tolist(), counts.tolist()):
                    if c >= 2:
                        linked |= {(p + f * 100000, q + f * 100000), (q + f * 100000, p + f * 100000)}
        # Each game cell takes the source room most of its pixels are in, if enough of it is inside.
        owner = {}
        for cz in range(gh):
            for cx in range(gw):
                blk = lab[int(cz * per):int((cz + 1) * per), int(cx * per):int((cx + 1) * per)]
                v = blk[blk > 0]
                if v.size and v.size >= spec.get("fill", 0.4) * blk.size:
                    owner[(gw - 1 - cx if mirror else cx, cz)] = int(np.bincount(v).argmax()) + f * 100000
        for s in stairs:  # a stairwell is carved out of both floors it spans
            if s["floor"] in (f, f - 1):
                for c in stair_cells(s):
                    owner.pop(c, None)
        for c in alter.get("carve", []):  # cells the alteration takes out of the plan
            if c[2] == f:
                owner.pop((c[0], c[1]), None)
        by_label = {}
        for c, l in owner.items():
            by_label.setdefault(l, set()).add(c)
        for l, cells in sorted(by_label.items()):
            for (x, z, w, d) in rects(cells):
                pieces.append({"floor": f, "x": x, "z": z, "w": w, "d": d, "label": l})

    cellmap = {}
    for i, p in enumerate(pieces):
        for t in range(p["w"]):
            for u in range(p["d"]):
                cellmap[(p["x"] + t, p["z"] + u, p["floor"])] = i

    def storey_of(z):
        for st in spec["storeys"]:
            if st["z"][0] - 16 <= z <= st["z"][1] + 160:
                return st["floor"]
        return None

    def piece_at(o):
        f = storey_of(o[2])
        if f is None:
            return None
        cx = int(((o[0] * S - ras.x0) / RES) // per)
        cz = int(((o[1] * S - ras.y0) / RES) // per)
        return cellmap.get((gw - 1 - cx if mirror else cx, cz, f))

    # What stood in each piece in the source: names, lights, the start.
    hints, lit, starts = {}, set(), []
    for sp in doc["static_props"]:
        i = piece_at(sp["origin"])
        if i is not None:
            hints.setdefault(i, []).append(sp["model"].lower())
    for e in doc["entities"]:
        o = e.get("origin")
        if not o:
            continue
        cls = e["classname"]
        i = piece_at([o[0], o[1], o[2] - 96] if cls.startswith("light") else o)
        if i is None:
            continue
        if cls.startswith("light"):
            lit.add(i)
        elif cls in ("info_player_start", "info_player_human"):
            starts.append(i)
        elif cls.startswith("prop_"):
            hints.setdefault(i, []).append(e["keys"].get("model", "").lower())

    # A door may be cut between two pieces of one source room, or of two the source opens between.
    adj = {i: set() for i in range(len(pieces) + len(stairs))}
    for (cx, cz, f), i in cellmap.items():
        for dx, dz in DIRS.values():
            j = cellmap.get((cx + dx, cz + dz, f))
            if j is not None and j != i:
                a, b = pieces[i]["label"], pieces[j]["label"]
                if a == b or (a, b) in linked:
                    adj[i].add(j)
    for k, s in enumerate(stairs):
        si = len(pieces) + k
        for f, cells in ((s["floor"], landing(s, False)), (s["floor"] + 1, landing(s, True))):
            for (cx, cz) in sorted(cells):
                for dx, dz in DIRS.values():
                    j = cellmap.get((cx + dx, cz + dz, f))
                    if j is not None and (cx + dx, cz + dz) not in stair_cells(s):
                        adj[si].add(j)
                        adj[j].add(si)
    if spec.get("start"):
        start = cellmap[tuple(spec["start"])]
    else:
        ground = [i for i in starts if pieces[i]["floor"] == 0]
        start = max(sorted(set(ground)), key=ground.count)
    parent = {start: None}
    order = [start]
    q = deque([start])
    min_cells = spec.get("min_cells", 2)
    while q:
        i = q.popleft()
        for j in sorted(adj[i]):
            if j in parent or (j < len(pieces) and pieces[j]["w"] * pieces[j]["d"] < min_cells):
                continue  # a cupboard of one cell: the builder's rooms are bigger than that
            parent[j] = i
            order.append(j)
            q.append(j)

    # A nook (one wide, two cells or less) that leads nowhere is the leftover of an L-shaped
    # source room, not a room: pruned, leaf by leaf.
    while True:
        kids = {}
        for j, i in parent.items():
            if i is not None:
                kids[i] = kids.get(i, 0) + 1
        nooks = [j for j in order if j < len(pieces) and parent[j] is not None and not kids.get(j)
                 and min(pieces[j]["w"], pieces[j]["d"]) == 1 and pieces[j]["w"] * pieces[j]["d"] <= 2]
        if not nooks:
            break
        for j in nooks:
            del parent[j]
        order = [j for j in order if j in parent]
    used, rooms, name_of = {}, [], {}
    for i in order:
        if i >= len(pieces):
            s = stairs[i - len(pieces)]
            room = {"name": s.get("name", "Stairs"), "kind": "stair", "x": s["x"], "z": s["z"], "w": s["w"], "d": s["d"],
                    "floor": s["floor"], "up": s["up"], "light": 0.35}
        else:
            p = pieces[i]
            corridor = min(p["w"], p["d"]) == 1
            if i == start:
                name = spec.get("start_name", "Entrance Hall")
            elif corridor:
                name = CORRIDORS[len(rooms) % len(CORRIDORS)] if p["w"] * p["d"] >= 3 else "Passage"
            else:
                text = " ".join(hints.get(i, []))
                name = next((n for w, n in NAME_WORDS if w in text), None) or ROOM_NAMES[len(rooms) % len(ROOM_NAMES)]
            room = {"name": name, "kind": "corridor" if corridor else "room", "x": p["x"], "z": p["z"], "w": p["w"], "d": p["d"],
                    "floor": p["floor"], "light": 0.8 if i == start else (0.35 if i in lit else 0.0)}
        base = room["name"]
        used[base] = used.get(base, 0) + 1
        if used[base] > 1:
            room["name"] = "%s %s" % (base, ROMAN[used[base]] if used[base] < len(ROMAN) else used[base])
        room["name"] = alter.get("rename", {}).get(room["name"], room["name"])
        name_of[i] = room["name"]
        if parent[i] is not None:
            room["from"] = name_of[parent[i]]
        rooms.append(room)
    x0 = min(r["x"] for r in rooms)
    z0 = min(r["z"] for r in rooms)
    for r in rooms:
        r["x"] -= x0
        r["z"] -= z0
    return rooms, len(pieces) + len(stairs) - len(order)


# --- Mesh mode: the source's own walls are the house ------------------------------------------
# The game draws the converted mesh and collides with its hulls, so the rooms are only where things
# are dealt: a fine grid (spec "cell", 1 m) in true metres, every door where the source has its
# doorway (exact centre and width), and every other opening listed so the builder can board it up.
GAME_DIRS = {"n": (0, -1), "s": (0, 1), "w": (-1, 0), "e": (1, 0)}  # the builder's: n is -z


def clusters(points, reach=2.0):
    """Points (x, z, side) grouped where they lie within [reach] of each other, in a fixed order."""
    left = sorted(points)
    out = []
    while left:
        group = [left.pop(0)]
        k = 0
        while k < len(group):
            px, pz = group[k][:2]
            near = [q for q in left if abs(q[0] - px) <= reach and abs(q[1] - pz) <= reach]
            for q in near:
                left.remove(q)
            group += near
            k += 1
        out.append(group)
    return out


def opening(group, res):
    """One opening from its boundary points: the centre, the width across it and the side it faces."""
    sides = [s for _, _, s in group]
    side = max(sorted(set(sides)), key=sides.count)
    xs = [p[0] for p in group if p[2] == side]
    zs = [p[1] for p in group if p[2] == side]
    along = xs if side in "ns" else zs
    return {"c": [round(float(sum(xs)) / len(xs), 2), round(float(sum(zs)) / len(zs), 2)], "w": round(float(max(along) - min(along) + res), 2), "side": side}


OPPOSITE = {"n": "s", "s": "n", "e": "w", "w": "e"}


def convert_mesh(doc, spec):
    """The layout of a mesh-mode house (see the note above) and a few counts."""
    if spec.get("mirror"):
        raise SystemExit("mesh mode: the drawn source cannot be mirrored")
    ras = Raster(doc, spec)
    S, cell = spec["scale"], spec.get("cell", 1.0)
    per = int(round(cell / RES))
    gw, gh = int(math.ceil(ras.nx / per)), int(math.ceil(ras.ny / per))
    alter = spec.get("alter", {})
    stairs = spec.get("stairs", [])
    r_px = int(round(spec.get("erode", 0.5) / RES))
    min_open = spec.get("min_opening", 0.75)

    def local(xi, yj):
        """Raster pixel corner (i, j) to grid-local metres (x, z): the raster's +y is the game's -z."""
        return xi * RES, gh * cell - yj * RES

    pieces, labs, tops, outs, yards = [], {}, {}, {}, {}
    for st in spec["storeys"]:
        f = st["floor"]
        inside, top, outdoor = ras.storey_parts(*st["z"])
        if st.get("yard"):  # a walled yard is walked like a room: it is how the source's wings meet
            yards[f] = outdoor
            inside, outdoor = inside | outdoor, outdoor & False
        lab, n = label(erode(inside, r_px))
        sizes = np.bincount(lab.ravel(), minlength=n + 1)
        keep = sizes * RES * RES >= spec.get("min_area", 3.0)
        keep[0] = False
        lab = np.where(keep[lab], lab, 0)
        lab = grow_labels(lab, inside, r_px + 2)
        # What the erosion took whole (a vestibule, a narrow passage) is a room of its own when big
        # enough; the crumbs join a neighbour. Either way no doorway is left unwalkable.
        rest, m = label(inside & (lab == 0))
        big = np.bincount(rest.ravel(), minlength=m + 1) * RES * RES >= spec.get("min_area", 3.0)
        big[0] = False
        lab = np.where(big[rest], rest + lab.max(), lab)
        lab = grow_labels(lab, inside, 4 * per)
        labs[f], tops[f], outs[f] = lab, top, outdoor & (lab == 0)
        owner = {}
        for r in range(gh):
            for cx in range(gw):
                blk = lab[r * per:(r + 1) * per, cx * per:(cx + 1) * per]
                v = blk[blk > 0]
                if v.size and v.size >= spec.get("fill", 0.5) * per * per:
                    owner[(cx, gh - 1 - r)] = int(np.bincount(v).argmax())
        for s in stairs:
            if s["floor"] in (f, f - 1):
                for c in stair_cells(s):
                    owner.pop(c, None)
        for c in alter.get("carve", []):
            if c[2] == f:
                owner.pop((c[0], c[1]), None)
        by_label = {}
        for c, l in owner.items():
            by_label.setdefault(l, set()).add(c)
        for l, cells in sorted(by_label.items()):
            for (x, z, w, d) in rects(cells):
                pieces.append({"floor": f, "x": x, "z": z, "w": w, "d": d, "label": l})

    # Each piece's pixels: those of its own source room in its cells, then spread over the rest of
    # that room (a doorway's pixels may lie in a neighbour's cell).
    P = len(pieces)
    pm = {}
    for f, lab in labs.items():
        m = np.zeros(lab.shape, np.int32)
        for k, p in enumerate(pieces):
            if p["floor"] != f:
                continue
            for cx in range(p["x"], p["x"] + p["w"]):
                for cz in range(p["z"], p["z"] + p["d"]):
                    r = gh - 1 - cz
                    blk = (slice(r * per, (r + 1) * per), slice(cx * per, (cx + 1) * per))
                    m[blk] = np.where(lab[blk] == p["label"], k + 1, m[blk])
        lab_of = np.array([0] + [p["label"] if p["floor"] == f else -1 for p in pieces])
        for _ in range(2 * per):
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                src = shift(m, dy, dx)
                m = np.where((m == 0) & (lab > 0) & (src > 0) & (lab_of[src] == lab), src, m)
        pm[f] = m

    # Openings: where two pieces' pixels meet, or a piece meets the open sky at its own floor.
    meet, sky = {}, {}
    for f, m in pm.items():
        for dy, dx in ((1, 0), (0, 1)):
            b = shift(m, -dy, -dx)
            o = shift(outs[f].astype(np.int32), -dy, -dx)
            ob = shift(m, dy, dx)
            for j, i in zip(*np.nonzero((m > 0) & (b > 0) & (m != b))):
                p, q = int(m[j, i]) - 1, int(b[j, i]) - 1
                x, z = local(i + 0.5 + dx * 0.5, j + 0.5 + dy * 0.5)
                side = "n" if dy else "e"  # from p to q
                if p < q:
                    meet.setdefault((p, q), []).append((x, z, side))
                else:
                    meet.setdefault((q, p), []).append((x, z, OPPOSITE[side]))
            # piece then sky (forward) and sky then piece (backward)
            for j, i in zip(*np.nonzero((m > 0) & (o > 0))):
                x, z = local(i + 0.5 + dx * 0.5, j + 0.5 + dy * 0.5)
                sky.setdefault(int(m[j, i]) - 1, []).append((x, z, "n" if dy else "e"))
            back = shift(outs[f].astype(np.int32), dy, dx)
            for j, i in zip(*np.nonzero((m > 0) & (back > 0))):
                x, z = local(i + 0.5 - dx * 0.5, j + 0.5 - dy * 0.5)
                sky.setdefault(int(m[j, i]) - 1, []).append((x, z, "s" if dy else "w"))
    def cellmap_of(x, z, f):
        for k, p in enumerate(pieces):
            if p["floor"] == f and p["x"] * cell <= x < (p["x"] + p["w"]) * cell and p["z"] * cell <= z < (p["z"] + p["d"]) * cell:
                return k
        return None

    openings = {k: [] for k in range(P + len(stairs))}
    # A doorway between two source rooms may straddle a cell edge and so touch two pieces: it is
    # measured whole, per pair of rooms, and goes to the pair of pieces that hold most of it.
    by_room = {}
    for (p, q), pts in sorted(meet.items()):
        lp, lq = pieces[p]["label"], pieces[q]["label"]
        if lp == lq:
            by_room[(p, q)] = [(x, z, side, p, q) for x, z, side in pts]
        else:
            flip = lp > lq
            key = (pieces[p]["floor"], min(lp, lq), max(lp, lq))
            by_room.setdefault(key, []).extend((x, z, OPPOSITE[side] if flip else side, q if flip else p, p if flip else q) for x, z, side in pts)
    for key, pts in sorted(by_room.items()):
        for g in clusters([pt[:3] + (pt[3:],) for pt in pts]):
            pair = max(sorted({pt[3] for pt in g}), key=[pt[3] for pt in g].count)
            o = opening([pt[:3] for pt in g], RES)
            if o["w"] < min_open:
                continue
            p, q = pair
            same = pieces[p]["label"] == pieces[q]["label"]
            openings[p].append(dict(o, to=q, open=same))
            openings[q].append(dict(o, side=OPPOSITE[o["side"]], to=p, open=same))
    for ex in spec.get("exits", []):  # [x, z, side] in grid-local metres: a way out the raster cannot see
        k = cellmap_of(ex[0], ex[1], 0)
        if k is not None:
            sky.setdefault(k, []).extend((ex[0] + t * 0.25 * (ex[2] in "ns"), ex[1] + t * 0.25 * (ex[2] in "ew"), ex[2]) for t in range(-3, 4))
    for p, pts in sorted(sky.items()):
        for g in clusters(pts):
            o = opening(g, RES)
            if o["w"] >= spec.get("min_exit", 1.0):
                openings[p].append(dict(o, to=None, out=True))

    cellmap = {}
    for i, p in enumerate(pieces):
        for t in range(p["w"]):
            for u in range(p["d"]):
                cellmap[(p["x"] + t, p["z"] + u, p["floor"])] = i
    # A stair opens off its landings, a cell-wide arch on each edge into a piece.
    for k, s in enumerate(stairs):
        si = P + k
        own = stair_cells(s)
        for f, cells in ((s["floor"], landing(s, False)), (s["floor"] + 1, landing(s, True))):
            by = {}
            for (cx, cz) in sorted(cells):
                for side, (dx, dz) in sorted(GAME_DIRS.items()):
                    j = cellmap.get((cx + dx, cz + dz, f))
                    if j is not None and (cx + dx, cz + dz) not in own:
                        by.setdefault((j, side), []).append((cx, cz))
            for (j, side), cs in sorted(by.items()):
                mid = cs[len(cs) // 2]
                dx, dz = GAME_DIRS[side]
                c = [round((mid[0] + 0.5 + dx * 0.5) * cell, 2), round((mid[1] + 0.5 + dz * 0.5) * cell, 2)]
                w = round(min(len(cs) * cell, spec.get("stair_door", 1.6)), 2)
                openings[si].append({"c": c, "w": w, "side": side, "to": j, "open": True, "top": f > s["floor"], "span": len(cs) * cell})
                openings[j].append({"c": c, "w": w, "side": OPPOSITE[side], "to": si, "open": True})

    # What stood in each piece in the source: names, lights, the start.
    def piece_at(o):
        for st in spec["storeys"]:
            if st["z"][0] - 16 <= o[2] <= st["z"][1] + 160:
                cx = int(((o[0] * S - ras.x0) / RES) // per)
                r = int(((o[1] * S - ras.y0) / RES) // per)
                return cellmap.get((cx, gh - 1 - r, st["floor"]))
        return None

    hints, lit, starts = {}, set(), []
    for sp in doc["static_props"]:
        i = piece_at(sp["origin"])
        if i is not None:
            hints.setdefault(i, []).append(sp["model"].lower())
    for e in doc["entities"]:
        o = e.get("origin")
        if not o:
            continue
        cls = e["classname"]
        i = piece_at([o[0], o[1], o[2] - 96] if cls.startswith("light") else o)
        if i is None:
            continue
        if cls.startswith("light"):
            lit.add(i)
        elif cls in ("info_player_start", "info_player_human"):
            starts.append(i)
        elif cls.startswith("prop_"):
            hints.setdefault(i, []).append(e["keys"].get("model", "").lower())

    min_cells = spec.get("min_cells", 6)

    def is_yard(k):
        sky_px = yards.get(pieces[k]["floor"])
        return sky_px is not None and sky_px[pm[pieces[k]["floor"]] == k + 1].mean() > 0.5

    def small(j):
        return j < P and pieces[j]["w"] * pieces[j]["d"] < min_cells

    if spec.get("start"):
        start = cellmap[tuple(spec["start"])]
    else:
        # The source's players may start outdoors: the start is the biggest ground piece nearest them.
        spawn = [e["origin"] for e in doc["entities"] if e["classname"] in ("info_player_start", "info_player_human") and e.get("origin")]
        sx = sum(o[0] for o in spawn) / len(spawn) * S - ras.x0
        sz = gh * cell - (sum(o[1] for o in spawn) / len(spawn) * S - ras.y0)

        def far(k):
            p = pieces[k]
            dx = max(p["x"] * cell - sx, 0, sx - (p["x"] + p["w"]) * cell)
            dz = max(p["z"] * cell - sz, 0, sz - (p["z"] + p["d"]) * cell)
            return (round(math.hypot(dx, dz) / 4), -p["w"] * p["d"], k)
        start = min((k for k in range(P) if pieces[k]["floor"] == 0 and not small(k) and not is_yard(k)), key=far)
    # A source room cut into pieces is walked whole before the next doorway: an arch between two
    # pieces is never a door, so no piece of a room is behind a lock another piece is not.
    parent, via = {start: None}, {start: None}
    order = [start]
    q = deque([start])
    while q:
        i = q.popleft()
        for o in sorted(openings[i], key=lambda o: (not o.get("open"), -o["w"], str(o["to"]))):
            j = o["to"]
            if j is None or j in parent or small(j):
                continue
            parent[j], via[j] = i, o
            order.append(j)
            (q.appendleft if o.get("open") else q.append)(j)
    while True:  # a nook that leads nowhere is the leftover of an odd-shaped room
        kids = {}
        for j, i in parent.items():
            if i is not None:
                kids[i] = kids.get(i, 0) + 1
        nooks = [j for j in order if j < P and parent[j] is not None and not kids.get(j)
                 and min(pieces[j]["w"], pieces[j]["d"]) * cell <= 1.0 and pieces[j]["w"] * pieces[j]["d"] * cell * cell <= 3.0]
        if not nooks:
            break
        for j in nooks:
            del parent[j]
        order = [j for j in order if j in parent]

    def floor_y(i):
        """A piece's floor height, metres over the source's ground: the most common top under it."""
        p = pieces[i]
        t = tops[p["floor"]][pm[p["floor"]] == i + 1]
        t = t[t > -1e8]
        if not t.size:
            return None
        vals, counts = np.unique(np.round(t), return_counts=True)
        return float(vals[counts.argmax()])

    base = min(y for y in (floor_y(i) for i in order if i < P and pieces[i]["floor"] == 0) if y is not None)
    used, rooms, name_of = {}, [], {}
    for i in order:
        if i >= P:
            s = stairs[i - P]
            room = {"name": s.get("name", "Stairs"), "kind": "stair", "x": s["x"], "z": s["z"], "w": s["w"], "d": s["d"],
                    "floor": s["floor"], "up": s["up"], "light": 0.35, "y": round((s["y"][0] - base) * S, 2), "y2": round((s["y"][1] - base) * S, 2)}
        else:
            p = pieces[i]
            corridor = min(p["w"], p["d"]) * cell <= spec.get("corridor_width", 2.5) and max(p["w"], p["d"]) >= 2 * min(p["w"], p["d"])
            yard = is_yard(i)
            if i == start:
                name = spec.get("start_name", "Entrance Hall")
            elif yard:
                name = "Courtyard"
            elif corridor:
                name = CORRIDORS[len(rooms) % len(CORRIDORS)] if max(p["w"], p["d"]) * cell >= 6 else "Passage"
            else:
                text = " ".join(hints.get(i, []))
                name = next((n for w, n in NAME_WORDS if w in text), None) or ROOM_NAMES[len(rooms) % len(ROOM_NAMES)]
            y = floor_y(i)
            room = {"name": name, "kind": "corridor" if corridor else "room", "x": p["x"], "z": p["z"], "w": p["w"], "d": p["d"],
                    "floor": p["floor"], "y": round(((y if y is not None else base) - base) * S, 2),
                    "light": 0.8 if i == start else (0.35 if i in lit else 0.0)}
            if yard:
                room["sky"] = True
        b = room["name"]
        used[b] = used.get(b, 0) + 1
        if used[b] > 1:
            room["name"] = "%s %s" % (b, ROMAN[used[b]] if used[b] < len(ROMAN) else used[b])
        room["name"] = alter.get("rename", {}).get(room["name"], room["name"])
        name_of[i] = room["name"]
        rooms.append(room)
    x0 = min(r["x"] for r in rooms)
    z0 = min(r["z"] for r in rooms)

    def shifted(c):
        return [round(c[0] - x0 * cell, 2), round(c[1] - z0 * cell, 2)]

    for i, room in zip(order, rooms):
        room["x"] -= x0
        room["z"] -= z0
        if parent[i] is not None:
            o = via[i]  # as seen from the parent: its side faces this room
            room["from"] = name_of[parent[i]]
            dx, dz = GAME_DIRS[o["side"]]
            pc = [int(math.floor((o["c"][0] - dx * 0.25) / cell)), int(math.floor((o["c"][1] - dz * 0.25) / cell))]
            room["door"] = {"cell": [pc[0] - x0, pc[1] - z0], "side": o["side"], "c": shifted(o["c"]), "w": min(o["w"], spec.get("door_max", 2.4))}
            if o.get("open"):
                room["door"]["open"] = True
        ops = []
        for o in openings[i]:
            entry = {"c": shifted(o["c"]), "w": o["w"], "side": o["side"], "to": name_of.get(o["to"], "")}
            if o.get("open"):
                entry["open"] = True
            if o.get("out"):
                entry["out"] = True
            # A stairwell's arches: off its upper landing or its lower, and the whole edge it shares.
            if "top" in o:
                entry.update({"top": o["top"], "span": o["span"]})
            ops.append(entry)
        room["openings"] = ops
    # The pack is in Godot axes (x, z, -y) at its own metres per unit; the grid's local z of a
    # source y is gh*cell - (y*S - y0) - z0*cell.
    world = {"pack": spec["pack"], "scale": round(S / spec["pack_metres_per_unit"], 6),
             "origin": [round(float(-(ras.x0 + x0 * cell)), 3), round(float(-base * S), 3), round(float(gh * cell + ras.y0 - z0 * cell), 3)]}
    return rooms, P + len(stairs) - len(order), world


def ascii_plan(rooms):
    out = []
    for f in sorted({r["floor"] for r in rooms} | {r["floor"] + 1 for r in rooms if r["kind"] == "stair"}):
        grid = {}
        for k, r in enumerate(rooms):
            if r["floor"] == f or (r["kind"] == "stair" and r["floor"] + 1 == f):
                for t in range(r["w"]):
                    for u in range(r["d"]):
                        grid[(r["x"] + t, r["z"] + u)] = "^" if r["kind"] == "stair" else "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQR"[k % 54]
        if grid:
            W = max(x for x, _ in grid) + 1
            H = max(z for _, z in grid) + 1
            out.append("floor %d (z grows down the page, as in the game)" % f)
            out += ["".join(grid.get((x, z), " ") for x in range(W)) for z in range(H)]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("intermediate")
    ap.add_argument("spec")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ascii", action="store_true")
    a = ap.parse_args()
    raw = open(a.intermediate, "rb").read()
    spec = json.load(open(a.spec))
    mesh = spec.get("mode") == "mesh"
    if mesh:
        rooms, lost, world = convert_mesh(json.loads(raw), spec)
    else:
        rooms, lost = convert(json.loads(raw), spec)
    out = {"format": 1, "name": spec["name"], "title": spec["title"]}
    if mesh:
        out["cell"] = spec.get("cell", 1.0)
        out["world"] = world
    for k in ("mood", "author"):
        if spec.get(k):
            out[k] = spec[k]
    out["converted"] = {"source": spec["source"], "sha256": hashlib.sha256(raw).hexdigest(), "grow": spec["grow"],
                        "mirror": spec.get("mirror", False), "pieces_not_reached": lost}
    out["rooms"] = rooms
    open(a.out, "w").write(json.dumps(out, indent=1) + "\n")
    floors = sorted({r["floor"] for r in rooms})
    cell = out.get("cell", CELL)
    print("%d rooms (%s), %d pieces not reached, %d m2" % (len(rooms), ", ".join("floor %d: %d" % (f, sum(r["floor"] == f for r in rooms)) for f in floors),
          lost, sum(r["w"] * r["d"] for r in rooms) * cell * cell))
    if a.ascii:
        print(ascii_plan(rooms))
    return 0


if __name__ == "__main__":
    sys.exit(main())
