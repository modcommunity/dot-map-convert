"""Document-box helpers: what the box-document importers each do to the boxes after the brushes
are cut (`boxes.decompose`) and before the game's own document is written.

[b]Hide-and-seek, prop-hunt and murder-mystery importers carried byte-identical copies of most of
this[/b] (the differences are named below and are parameters here). Everything works on the
*document's* boxes, in metres and Godot axes: `{"at": [x, y, z], "size": [w, h, d], "yaw": degrees,
"mat": str, "solid": bool}`, not on `boxes.decompose`'s map-unit boxes. Behaviour is the copies':
each function is tested against them on real documents (`tests/test_lift.py`, `DocBoxes`).

* `classify_material(name)`, `brush_material_names(bsp, i)`, `majority_material(names, table, default)`:
  a brush's material by the majority of its sides; a tie follows the sorted name, not the hash seed;
* `within(box, x, z)`: is a point under the box's footprint (turned boxes included);
* `suburban_surface(at, size, palette)`: a developer-grid box's material by its shape;
* `widen_doors`, `drop_door_leaves`, `add_doors`: doorways;
* `prune_far_scenery`, `prune_pockets`, `scatter_cover`: pruning and furnishing a finished document.

`prune_pockets` is a 0.1 m flat flood of one floor height, the importers' version. It is *not*
`flood.Flood`, which is multi-storey; see the README before swapping.
"""

import math
import random
import re

# Dev-grid surface palette, the one three importers shared (RGB 0..1).
SUBURBAN_PALETTE = {
    "SIDING_BLUE": (0.80, 0.88, 1.00),
    "SIDING_GREEN": (0.82, 0.96, 0.84),
    "BRICK_RED": (1.00, 0.86, 0.80),
    "ROOF_RED": (1.00, 0.72, 0.62),
    "FENCE_WHITE": (1.00, 0.96, 0.90),
}


# Materials a door leaf or a trim post is made of, in the games' own ids and the shared list's
# (`source_textures.tsv`): `wood` and `parquet` are the older ids, the rest the generic ones.
LEAF_MATERIALS = ("wood", "parquet", "door_wood", "wood_planks", "wood_floor")
TRIM_MATERIALS = ("concrete", "stone_wall") + LEAF_MATERIALS


def classify_material(name):
    """A source material name without its per-map folder and cubemap suffix. A map-patched material
    is MAPS/<map>/<group>/<name>_<x>_<y>_<z>; the folder carries the map's own name, which must not
    decide a surface (a map called ph_school would match SCHOOL-anything)."""
    n = name.upper()
    if n.startswith("MAPS/"):
        n = n.split("/", 2)[-1]
    return re.sub(r"(_-?\d+){3}$", "", n)


def brush_material_names(bsp, index):
    """Upper-case material names of a brush's sides (bevel and unused sides skipped)."""
    first, count, _ = bsp.brushes[index]
    names = []
    for s in bsp.brushsides[first:first + count]:
        if s[3] or s[1] < 0:
            continue
        ti = bsp.texinfo[s[1]]
        td = int(ti[17])
        if 0 <= td < len(bsp.texdata):
            names.append(bsp.texnames[bsp.texdata[td][3]].upper())
    return names


def majority_material(names, table, default=None, classify=classify_material):
    """The (material, tint) of the brush's most common real material, or None for a tools-only brush.

    Developer-grid sides are ignored when anything else is there. `table` is [(substring, material,
    tint)] tried in order against the classified name; `default` is returned when none matches
    (importers used ("flat", None) or a config's own). `table` may instead be a `texturemap.TextureMap`
    (the shared `source_textures.tsv`), whose most specific row wins rather than the first.

    [b]A tie is broken by the sorted name[/b], not by set order, which follows the hash seed: the same
    map converted twice must give the same boxes.
    """
    real = [n for n in names if not n.startswith("TOOLS/")]
    if not real:
        return None
    pool = [n for n in real if not n.startswith("DEV/")] or real
    best = classify(max(sorted(set(pool)), key=pool.count))
    if hasattr(table, "lookup"):
        return table.lookup(best) or default
    for key, mat, tint in table:
        if key in best:
            return mat, tint
    return default


def within(b, x, z, slack=0.0):
    """Whether (x, z) is under box b's footprint, which a turned box (yaw) shares only in its own
    frame: the point is taken into it first (godot turns a box about +y)."""
    dx, dz = x - b["at"][0], z - b["at"][2]
    yaw = b.get("yaw", 0.0)
    if yaw:
        c, sn = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        dx, dz = dx * c - dz * sn, dx * sn + dz * c
    return abs(dx) <= b["size"][0] / 2 + slack and abs(dz) <= b["size"][2] / 2 + slack



def suburban_surface(at, size, palette=SUBURBAN_PALETTE):
    """(mat, tint) for a developer-grid box, from its centre `at` and `size` in metres."""
    w, h, d = size
    SIDING_BLUE, SIDING_GREEN, BRICK_RED, ROOF_RED, FENCE_WHITE = (palette[k] for k in (
        "SIDING_BLUE", "SIDING_GREEN", "BRICK_RED", "ROOF_RED", "FENCE_WHITE"))
    top = at[1] + h / 2
    if h < 0.7 and max(w, d) > 2.0:
        # A slab: high up it is a roof or a balcony, at the ground a path or the drive.
        return ("roof", ROOF_RED) if top > 5.0 else ("sidewalk", None)
    if min(w, d) < 0.6 and h > 2.0:
        return "wood", FENCE_WHITE          # slats and pickets
    if h >= 8.0:
        # A neighbour's house wall round the yard: brick on two sides, siding on the others.
        if d > w:
            return "brick", BRICK_RED
        return ("plaster", SIDING_BLUE) if at[2] < 0 else ("plaster", SIDING_GREEN)
    if h >= 4.5:
        return "plaster", SIDING_BLUE        # the upper storey of a house
    if abs(w - h) < 0.1 and abs(d - h) < 0.1:
        return "brick", BRICK_RED            # a shed block or a chimney stack
    return "wood", FENCE_WHITE



def widen_doors(boxes, want=1.4, doors=()):
    """Widens the doorways a flat's author made about a metre wide (--widen-doors).

    A door is a gap between two collinear wall slabs, a header box over it and a thin trim post
    either side (ph_apartment's are 0.91 m clear). The bots' mesh is eroded by the body radius
    on each side, a doorway that narrow bakes as a sliver or not at all, and every room behind
    one becomes an island. The game's own door convention is 1.4 m. Each slab end moves back,
    the header is stretched over the new gap, and the trim posts and lintels are dropped (they are
    what made the opening narrower than the wall's gap)."""
    walls = []
    for b in boxes:
        w, h, d = b["size"]
        if not b.get("solid", True) or b.get("yaw") or h < 2.3 or b["at"][1] - h / 2 > 0.5:
            continue
        if min(w, d) <= 0.4 < max(w, d):
            walls.append(b)
    done = 0
    for a in walls:
        axis = 2 if a["size"][2] > a["size"][0] else 0        # the run's axis; the other is across it
        cross = 0 if axis == 2 else 2
        for c in walls:
            if c is a or c["size"][axis] <= c["size"][cross] or abs(c["at"][cross] - a["at"][cross]) > 0.02:
                continue
            if abs(c["size"][1] - a["size"][1]) > 0.01 or abs(c["at"][1] - a["at"][1]) > 0.01:
                continue
            a_end = a["at"][axis] + a["size"][axis] / 2
            c_start = c["at"][axis] - c["size"][axis] / 2
            gap = c_start - a_end
            if not 0.8 <= gap <= 1.2:
                continue
            grow = (want - gap) / 2
            mid = (a_end + c_start) / 2
            for piece in (a, c):
                piece["size"][axis] = round(piece["size"][axis] - grow, 3)
            a["at"][axis] = round(a["at"][axis] - grow / 2, 3)
            c["at"][axis] = round(c["at"][axis] + grow / 2, 3)
            for b in list(boxes):
                if b is a or b is c or abs(b["at"][cross] - a["at"][cross]) > 0.3 or abs(b["at"][axis] - mid) > want / 2 + 0.2:
                    continue
                w, h, d = b["size"]
                if b["at"][1] - h / 2 > 1.8 and abs(b["size"][axis] - gap) < 0.1 and b["size"][cross] <= 0.4:
                    b["size"][axis] = round(want, 3)               # the header over the door
                    b["at"][axis] = round(mid, 3)
                elif b["mat"] in TRIM_MATERIALS and (min(w, d) < 0.1) and b["at"][1] - h / 2 < 2.2:
                    boxes.remove(b)                                 # a trim post or lintel
            # A door already hung in that gap (this runs after add_doors, which needs the author's
            # narrow doorway to find the hinge's wall) grows with it, or its panel would leave a
            # 0.25 m hole either side.
            for dr in doors:
                if abs(dr["at"][cross] - a["at"][cross]) < 0.2 and abs(dr["at"][axis] - mid) < 0.2:
                    dr["size"][0] = round(want - 0.02, 3)
                    dr["at"][axis] = round(mid, 3)
            done += 1
    return done



def drop_door_leaves(boxes):
    """Remove door leaves the author left standing ajar in a doorway.

    A leaf is a wood slab as tall as a door, about a door wide and under 15 cm thick. In the
    source it swings clear of the opening; here it is a fixed box in the middle of a gap that is
    then too narrow for the bots' nav (radius plus a cell either side), which cuts a whole room
    off. The frame and the wall stay, so the doorway reads as a doorway."""
    kept, dropped = [], 0
    for b in boxes:
        w, h, d = b["size"]
        thin, wide = sorted((w, d))
        # A hotel's double doors are two half leaves (0.4 m each, in wood or parquet).
        if b.get("mat") in LEAF_MATERIALS and 1.9 <= h <= 2.3 and thin < 0.15 and 0.35 <= wide <= 1.1:
            dropped += 1
            continue
        kept.append(b)
    boxes[:] = kept
    return dropped



def prune_far_scenery(boxes, starts, reach=12.0, log=print):
    """Drops the boxes of every cluster that is out of reach of the starts. A community map keeps
    its 3D skybox scenery (a distant city, a crane) in the same world as the play space, and the
    overview camera frames all of it, so the real map shrank to a corner of the frame. Boxes are
    grouped by touching (a quarter metre of slack); a group is kept when one of its boxes comes
    within `reach` metres of a start; the author's sky-box walls that bound the play space are
    big enough to pass, and a second, sealed sky cell holding the scenery is dropped with it."""
    if not starts:
        return 0
    n = len(boxes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def box_range(b):
        h = [b["size"][0] / 2, b["size"][1] / 2, b["size"][2] / 2]
        if b.get("yaw"):
            # The turned box's own bounds, so its slack is not the box's corner sticking out.
            c, sn = abs(math.cos(math.radians(b["yaw"]))), abs(math.sin(math.radians(b["yaw"])))
            h = [h[0] * c + h[2] * sn, h[1], h[0] * sn + h[2] * c]
        return [(b["at"][i] - h[i] - 0.25, b["at"][i] + h[i] + 0.25) for i in range(3)]

    rng = [box_range(b) for b in boxes]
    order = sorted(range(n), key=lambda i: rng[i][0][0])
    for ai, a in enumerate(order):
        for b in order[ai + 1:]:
            if rng[b][0][0] > rng[a][0][1]:
                break
            if all(rng[a][k][0] <= rng[b][k][1] and rng[b][k][0] <= rng[a][k][1] for k in (1, 2)):
                parent[find(a)] = find(b)
    keep = set()
    for i, b in enumerate(boxes):
        near = any(rng[i][0][0] - reach <= sx <= rng[i][0][1] + reach and rng[i][2][0] - reach <= sz <= rng[i][2][1] + reach
                   for sx, _sy, sz in starts)
        if near:
            keep.add(find(i))
    before = len(boxes)
    boxes[:] = [b for i, b in enumerate(boxes) if find(i) in keep]
    if len(boxes) != before and log:
        log("dropped %d boxes of scenery out of reach of the starts" % (before - len(boxes)))
    return before - len(boxes)



def prune_pockets(doc, size_of, footprint, rounds=4, spawn_key="hiders", cell=0.1, radius=0.35, beside=0.45):
    """Drops floor props that leave a pocket the bots cannot walk out of (--prune-pockets).

    mg-prop-hunt's headless_bots holds every hiding place reachable from the props' first start,
    and a place is "beside" a piece of floor furniture (0.45 m off its side). A bed, a bookcase
    or a table left a hand's width off a wall makes a sliver of floor that the bots' walkable mesh
    (eroded by the body radius, 0.35 m) cuts off from the rest, and a small flat has dozens. This
    does what the headless_bots trace asks for, in one pass over every prop instead of one
    whack-a-mole drop at a time: it finds the walkable cells on a 0.1 m grid (floor within a step's
    height, nothing solid between knee and head, nothing furniture), floods them from the start,
    and drops a prop whose every free side lands in a cell the flood did not reach.

    `size_of(prop_id)` -> (w, h, d) and `footprint(prop_id, yaw)` -> (w, d) are the game's prop
    catalogue; `spawn_key` names the spawn list the flood starts from ("hiders" in hide-and-seek,
    "props" in prop-hunt, "players" in murder-mystery: the only line the copies differed on)."""
    R, RAD, BESIDE = cell, radius, beside
    boxes = [b for b in doc["boxes"] if b.get("solid", True)]
    xs0 = min(b["at"][0] - b["size"][0] / 2 for b in boxes)
    xs1 = max(b["at"][0] + b["size"][0] / 2 for b in boxes)
    zs0 = min(b["at"][2] - b["size"][2] / 2 for b in boxes)
    zs1 = max(b["at"][2] + b["size"][2] / 2 for b in boxes)
    W, H = int((xs1 - xs0) / R) + 1, int((zs1 - zs0) / R) + 1
    total = 0
    for _ in range(rounds):
        floor = bytearray(W * H)
        block = bytearray(W * H)

        def cells(b, test):
            hx, hz = b["size"][0] / 2, b["size"][2] / 2
            reach = math.hypot(hx, hz) if b.get("yaw") else None
            ax, az = (reach, reach) if reach else (hx, hz)
            for zi in range(max(0, int((b["at"][2] - az - zs0) / R)), min(H, int((b["at"][2] + az - zs0) / R) + 2)):
                for xi in range(max(0, int((b["at"][0] - ax - xs0) / R)), min(W, int((b["at"][0] + ax - xs0) / R) + 2)):
                    if within(b, xs0 + (xi + 0.5) * R, zs0 + (zi + 0.5) * R):
                        test(zi * W + xi)

        for b in boxes:
            lo, hi = b["at"][1] - b["size"][1] / 2, b["at"][1] + b["size"][1] / 2
            if -0.05 <= hi <= 0.3:
                cells(b, lambda i: floor.__setitem__(i, 1))
            if hi > 0.3 and lo < 1.4:
                cells(b, lambda i: block.__setitem__(i, 1))
        for q in doc["props"]:
            if q["at"][1] > 0.3:
                continue
            sx, sy, sz = size_of(q["id"])
            if sy < 0.3:
                continue
            fw, fd = footprint(q["id"], q.get("yaw", 0.0))
            cells({"at": q["at"], "size": [fw, sy, fd]}, lambda i: block.__setitem__(i, 1))
        bad = bytearray(W * H)
        k = int(math.ceil(RAD / R))
        for i in range(W * H):
            if block[i] or not floor[i]:
                zi, xi = divmod(i, W)
                for dz in range(-k, k + 1):
                    for dx in range(-k, k + 1):
                        if dx * dx + dz * dz <= k * k and 0 <= zi + dz < H and 0 <= xi + dx < W:
                            bad[(zi + dz) * W + xi + dx] = 1
        sp = doc["spawns"][spawn_key][0]["at"]
        start = (int((sp[2] - zs0) / R), int((sp[0] - xs0) / R))
        near = next(((zi, xi) for rr in range(0, 15) for zi in range(start[0] - rr, start[0] + rr + 1)
                     for xi in range(start[1] - rr, start[1] + rr + 1)
                     if 0 <= zi < H and 0 <= xi < W and not bad[zi * W + xi]), None)
        if near is None:
            return total
        seen = bytearray(W * H)
        seen[near[0] * W + near[1]] = 1
        stack = [near]
        while stack:
            zi, xi = stack.pop()
            for dz, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nz, nx = zi + dz, xi + dx
                if 0 <= nz < H and 0 <= nx < W and not seen[nz * W + nx] and not bad[nz * W + nx]:
                    seen[nz * W + nx] = 1
                    stack.append((nz, nx))

        def nearest_free(x, z):
            """The closest walkable cell within 0.35 m of (x, z): (reached?, found?)."""
            ci, cj = int((z - zs0) / R), int((x - xs0) / R)
            best = None
            for zi in range(ci - 4, ci + 5):
                for xi in range(cj - 4, cj + 5):
                    if 0 <= zi < H and 0 <= xi < W and not bad[zi * W + xi]:
                        d2 = (zi - ci) ** 2 + (xi - cj) ** 2
                        if d2 <= 12 and (best is None or d2 < best[0]):
                            best = (d2, bool(seen[zi * W + xi]))
            return best

        gone = []
        for q in doc["props"]:
            if q["at"][1] > 0.3:
                continue
            sx, sy, sz = size_of(q["id"])
            fw, fd = footprint(q["id"], q.get("yaw", 0.0))
            ys = math.radians(q.get("yaw", 0.0))
            states = []
            for lx, lz in ((fw / 2 + BESIDE, 0), (-fw / 2 - BESIDE, 0), (0, fd / 2 + BESIDE), (0, -fd / 2 - BESIDE)):
                n = nearest_free(q["at"][0] + lx, q["at"][2] + lz)
                if n is not None:
                    states.append(n[1])
            if states and not any(states):
                gone.append(q)
        if not gone:
            break
        for q in gone:
            doc["props"].remove(q)
        total += len(gone)
    return total



def scatter_cover(m, count, seed, kinds, spacing=2.5, avoid=(), avoid_r=0.0, clear=2.0, floor_y=0.0):
    """Cover on the clearest open floor, the same every run: a seeded shuffle of the open floor's
    spots (2 m of clear floor round each, the 1.5 m grid), each at least `spacing` metres from the
    last, turned to face a wall's way at random. Placed before the build, so spawns settle round it."""
    rng = random.Random(seed)
    spots = [s for s in m.spots(y=floor_y, step=1.5, top=400) if s[0] >= clear]
    rng.shuffle(spots)
    placed = []
    for _size, x, z in spots:
        if len(placed) >= count:
            break
        if all((x - a) ** 2 + (z - b) ** 2 >= rad ** 2 for a, b, rad in avoid) and all((x - a) ** 2 + (z - b) ** 2 >= spacing ** 2 for a, b in placed):
            m.prop(rng.choice(kinds), x, z, yaw=rng.choice((0.0, 90.0, 180.0, 270.0)), y=floor_y)
            placed.append((x, z))
    return len(placed)



def add_doors(m, doc, entities, shift, slide=False, scale=0.01905, skip=(), log=print):
    """A real, usable door for each of the author's prop_door_rotating, hung where the doorway is.

    `entities` is the map's entity list, `shift` the (x, y, z) the importer moved the map by, `skip`
    [(x, z)] finished coordinates of a doorway to leave open (murder-mystery's --skip-door).

    The entity's origin is the hinge, but not which way the door lies, so the finished boxes say:
    from the hinge a ray along each horizontal axis, both ways, at three heights of a person,
    runs until it meets a wall; a doorway is a stretch of 0.7 to 1.7 m with a wall hard against
    the hinge end. The door takes the far wall's own centre line (a pillar thicker than a wall
    is no centre line, and the hinge's is used). Returns how many were hung; the others are
    reported through `log`, for a doorway the author's door did not stand in or that the conversion filled."""
    ox, oy, oz = shift

    def gd(p):
        return (p[0] * scale, p[2] * scale, -p[1] * scale)

    def vec(s):
        return [float(x) for x in s.split()]

    hung = missed = 0

    def solid(x, y, z):
        for b in doc["boxes"]:
            if b.get("solid", True) and within(b, x, z) and b["at"][1] - b["size"][1] / 2 <= y <= b["at"][1] + b["size"][1] / 2:
                return b
        return None

    for e in entities:
        if e.get("classname") != "prop_door_rotating":
            continue
        gx, gy, gz = gd(vec(e["origin"]))
        hx, hy, hz = gx - ox, gy - oy, gz - oz
        if any(abs(hx - a) < 0.8 and abs(hz - b) < 0.8 for a, b in skip):
            continue
        fy = max([b["at"][1] + b["size"][1] / 2 for b in doc["boxes"] if b.get("solid", True) and within(b, hx, hz) and b["at"][1] + b["size"][1] / 2 <= hy + 0.1] or [0.0])
        best = None
        for axis in (0, 2):
            for sign in (1, -1):
                def pt(d):
                    return (hx + sign * d, hz) if axis == 0 else (hx, hz + sign * d)
                heights = (fy + 0.5, fy + 1.2, fy + 1.9)
                back = pt(-0.08)
                if not any(solid(back[0], y, back[1]) for y in heights):
                    continue
                length, end = None, None
                d = 0.05
                while d < 2.0:
                    x, z = pt(d)
                    hit = next((solid(x, y, z) for y in heights if solid(x, y, z)), None)
                    if hit:
                        length, end = d, hit
                        break
                    d += 0.03
                if length is None or not 0.7 <= length <= 1.7:
                    continue
                if best is None or abs(length - 1.0) < abs(best[0] - 1.0):
                    best = (length, axis, sign, end)
        if best is None:
            missed += 1
            log("door at (%.1f, %.1f, %.1f): no doorway found beside the hinge" % (hx, fy, hz))
            continue
        length, axis, sign, end = best
        c0 = hx if axis == 0 else hz
        lo, hi = (c0, c0 + length) if sign > 0 else (c0 - length, c0)
        # Perpendicular centre: the far wall's, when it is a wall (under half a metre), else the hinge's.
        perp = hz if axis == 0 else hx
        pi = 2 if axis == 0 else 0
        if end["size"][2 if axis == 0 else 0] < 0.5 and not end.get("yaw"):
            perp = end["at"][pi]
        hinge = "start" if sign > 0 else "end"
        m.door("x" if axis == 0 else "z", lo, hi, perp, fy, fy + 2.06, name="door", hinge=hinge, motion="slide" if slide else None)
        hung += 1
        # The author's clutter beside a door (a table in the doorway's swing) was no trouble to
        # a door that never opened; here a body steps out of the swing to use it and a stand-in
        # lingered thirteen seconds against the panel, so props in the square the panel sweeps,
        # on both sides, are taken away.
        a0, a1 = lo - 0.15, hi + 0.15
        gone = []
        for q in doc["props"]:
            along, across = (q["at"][0], q["at"][2]) if axis == 0 else (q["at"][2], q["at"][0])
            pa, pb = (0.35, 0.35)
            if a0 - pa <= along <= a1 + pa and abs(across - perp) <= length + 0.2 + pb and abs(q["at"][1] - fy) < 1.5:
                gone.append(q)
        for q in gone:
            doc["props"].remove(q)
        if gone:
            log("  door at (%.1f, %.1f): %d props cleared from its swing" % (hx, hz, len(gone)))
    log("doors: %d hung, %d with no doorway" % (hung, missed))
    return hung
