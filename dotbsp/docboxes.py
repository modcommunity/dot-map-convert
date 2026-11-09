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
* `prune_far_scenery`, `prune_pockets`, `scatter_cover`, `walk_flood`, `walked_spots`, `scatter_walked`: pruning and furnishing a finished document.

`prune_pockets` is a 0.1 m flat flood of one floor height, the importers' version. It is *not*
`flood.Flood`, which is multi-storey; see the README before swapping.
"""

import json
import math
import random
import re
import zlib

from . import passledger
from . import audit as _audit, classes as _classes, flood as _flood_mod, reader, terrain as _terrain

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


# Contents kinds (`audit.contents_kind`) of a brush made only of tool textures that still stops a body: the skybox
# wall, clip and playerclip, and a nodraw or invisible solid. Nodraw is a render flag (the compiler hides the face), not a
# reason to drop what is solid; a clip brush is the author's invisible wall.
TOOL_SOLIDS = frozenset(("sky", "clip", "playerclip", "invisible", "nodraw", "tool"))


def stops_player(bsp, index, names=None):
    """Whether a brush with no real material (`majority_material` is None) is still solid to a player, so a document
    carries it as a box that is not drawn (the importers set `visible: false`)."""
    names = brush_material_names(bsp, index) if names is None else names
    if any("TOOLSSKYBOX" in n for n in names):
        return True
    contents = bsp.brushes[index][2]
    return bool(contents & reader.MASK_PLAYERSOLID) and _audit.contents_kind(contents, names) in TOOL_SOLIDS


def entity_starts_hidden(e):
    """Whether a brush entity starts not solid or not there: `rendermode 10`, StartDisabled, a func_brush with
    Solidity 1 (never solid), or a func_wall_toggle that starts off (spawnflag 1)."""
    def flag(k):
        return str(e.get(k, "0")).strip()
    cls = e.get("classname")
    return (flag("rendermode") == "10" or flag("StartDisabled") == "1"
            or (cls == "func_brush" and flag("Solidity") == "1")
            or (cls == "func_wall_toggle" and flag("spawnflags").isdigit() and int(flag("spawnflags")) & 1 == 1))


def world_brushes(bsp):
    """[(brush index, (x, y, z) offset in map units)] to turn into boxes: the world's own (offset 0, func_detail
    merged in) and then every brush of an entity the class table treats as `world` (func_wall, func_brush, func_breakable,
    func_physbox...: drawn and solid where they stand), shifted by the entity's origin. Doors, lifts and other movers
    are the importers' own; an entity that starts hidden is left out."""
    out = [(bi, (0.0, 0.0, 0.0)) for bi in sorted(bsp.model_brushes(0))]
    seen = set(bi for bi, _o in out)
    for mi, e in sorted((int(str(e["model"])[1:]), e) for e in bsp.entities
                        if str(e.get("model", "")).startswith("*") and str(e["model"])[1:].isdigit()):
        if mi == 0 or mi >= len(bsp.models) or _classes.treatment(e.get("classname", ""))[0] != "world" or entity_starts_hidden(e):
            continue
        off = tuple(reader.entity_vec(e))
        for bi in sorted(bsp.model_brushes(mi)):
            if bi not in seen:
                seen.add(bi)
                out.append((bi, off))
    return out


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



@passledger.tracked("widen_doors", lambda boxes, *a, **k: boxes)
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



@passledger.tracked("drop_door_leaves", lambda boxes, *a, **k: boxes)
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



@passledger.tracked("drop_small", lambda boxes, *a, **k: boxes)
def drop_small(boxes, min_size):
    """Drops boxes whose longest side is under `min_size` metres (trim, rails, clutter) and returns how many; a map over the game's wire limit shrinks most here."""
    keep = [b for b in boxes if max(b["size"]) >= min_size]
    n = len(boxes) - len(keep)
    boxes[:] = keep
    return n


def pad_spawns(doc, sides, mat="concrete", pad=2.5, reach=0.4):
    """Lays a flat pad under each spawn that has no solid top within `reach` metres below it (a start
    the author stood on terrain this converter leaves out), one pad per pad-sized cell, and returns the count."""
    solid = [b for b in doc["boxes"] if b.get("solid", True)]
    cells = {}
    for side in sides:
        for o in doc.get("spawns", {}).get(side, []):
            x, y, z = o["at"]
            if any(b["at"][1] + b["size"][1] / 2 <= y + 0.02 and b["at"][1] + b["size"][1] / 2 >= y - reach and within(b, x, z) for b in solid):
                continue
            cells.setdefault((round(x / pad), round(z / pad), round(y, 1)), []).append(o["at"])
    for pts in cells.values():
        x0, x1 = min(p[0] for p in pts) - 0.8, max(p[0] for p in pts) + 0.8
        z0, z1 = min(p[2] for p in pts) - 0.8, max(p[2] for p in pts) + 0.8
        top = min(p[1] for p in pts) - 0.05
        doc["boxes"].append({"at": [round((x0 + x1) / 2, 3), round(top - 0.15, 3), round((z0 + z1) / 2, 3)],
                             "size": [round(x1 - x0, 3), 0.3, round(z1 - z0, 3)], "mat": mat})
    return len(cells)


@passledger.tracked("prune_far_scenery", lambda boxes, *a, **k: boxes)
def prune_far_scenery(boxes, starts, reach=12.0, log=print, join=3.0):
    """Drops the boxes of every cluster that is out of reach of the starts. A community map keeps
    its 3D skybox scenery (a distant city, a crane) in the same world as the play space, and the
    overview camera frames all of it, so the real map shrank to a corner of the frame. Boxes are
    grouped by touching (a quarter metre of slack); a group is kept when one of its boxes comes
    within `reach` metres of a start; the author's sky-box walls that bound the play space are
    big enough to pass, and a second, sealed sky cell holding the scenery is dropped with it.

    [b]A cluster within `join` metres of what is kept stays.[/b] A room of the building that touches nothing
    by the quarter metre (ph_wolfsmanor's upstairs parquet hall stood 2.2 m from the rest) was dropped as
    scenery, though it sits inside the house. Real scenery is separated from the play space by more than that
    (measured with tools/audit_passes.py: the nearest pruned cluster of ph_westerncity is 14 m off, of
    ph_restaurant_os 44 m, and none of their floor can be walked to from a spawn). `join` 0 is the old rule."""
    if not starts:
        return 0
    n = len(boxes)

    def box_range(b, slack):
        h = [b["size"][0] / 2, b["size"][1] / 2, b["size"][2] / 2]
        if b.get("yaw"):
            # The turned box's own bounds, so its slack is not the box's corner sticking out.
            c, sn = abs(math.cos(math.radians(b["yaw"]))), abs(math.sin(math.radians(b["yaw"])))
            h = [h[0] * c + h[2] * sn, h[1], h[0] * sn + h[2] * c]
        return [(b["at"][i] - h[i] - slack, b["at"][i] + h[i] + slack) for i in range(3)]

    def groups(slack):
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        rng = [box_range(b, slack) for b in boxes]
        order = sorted(range(n), key=lambda i: rng[i][0][0])
        for ai, a in enumerate(order):
            for b in order[ai + 1:]:
                if rng[b][0][0] > rng[a][0][1]:
                    break
                if all(rng[a][k][0] <= rng[b][k][1] and rng[b][k][0] <= rng[a][k][1] for k in (1, 2)):
                    parent[find(a)] = find(b)
        return find, rng

    find, rng = groups(0.25)
    keep = set()
    for i, b in enumerate(boxes):
        near = any(rng[i][0][0] - reach <= sx <= rng[i][0][1] + reach and rng[i][2][0] - reach <= sz <= rng[i][2][1] + reach
                   for sx, _sy, sz in starts)
        if near:
            keep.add(find(i))
    if join:
        # The groups within `join` metres of a kept group, and what those are within `join` of in turn.
        find2, _ = groups(join / 2)
        keep2 = {find2(i) for i in range(n) if find(i) in keep}
        keep |= {find(i) for i in range(n) if find2(i) in keep2}
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


def walk_flood(boxes, start, tris=None, mat="grass", tint=None, budget=24000, scale=0.01905, cell=0.5):
    """`flood.Flood` from `start` (x, y, z) over a box list still holding `--terrain`'s stepped field:
    the field is walked as the heightfield `swap_terrain` will make of it (by slope, not by step), so a
    hillside a 1.5 m stepped cell makes a wall of is ground. Jumps and drops are capped at 0.9 m both
    ways, so what is reached can also walk back. None when no ground is within 3 m of the start."""
    ground, rest = None, boxes
    if tris:
        probe = {"boxes": list(boxes)}
        ground = _terrain.swap_terrain(probe, tris, mat, tint, budget, scale=scale, skirt=False)
        rest = probe["boxes"]
    fl = _flood_mod.Flood(rest, cell=cell, jump=0.9, drop=0.9, terrain=ground).run([start])
    if not fl.seen:
        # A start over a hole gets a pad later (pad_spawns): seed from the nearest ground within 3 m.
        ix, iz = fl.cell_of(start[0], start[2])
        reach = int(math.ceil(3.0 / cell))
        near = [((dx * dx + dz * dz), abs(h - start[1]), ix + dx, iz + dz, h)
                for dx in range(-reach, reach + 1) for dz in range(-reach, reach + 1)
                for h in fl.surf.get((ix + dx, iz + dz), ()) if start[1] - 1.5 <= h <= start[1] + 0.6]
        if not near:
            return None
        _, _, jx, jz, h = min(near)
        x, z = fl.centre_of(jx, jz)
        fl.run([(x, h, z)])
        if not fl.seen:
            return None
    fl.ground = ground
    return fl


def walked_spots(fl, margin=2):
    """(x, y, z) at the middle of every walked cell with `margin` cells round it walked at a step's height:
    open ground, level or a gentle slope, on any floor or terrain, in a fixed order."""
    out = []
    for (ix, iz), h in sorted(fl.deep_cells(margin).items()):
        x, z = fl.centre_of(ix, iz)
        out.append((round(x, 3), h, round(z, 3)))
    return out


def level_on(ground, x, z, reach, level):
    """Whether heightfield `ground` is near level at (x, z): its corners `reach` metres out differ by at most
    `level` metres. True off the field (and with no field): a floor box is level."""
    if ground is None:
        return True
    hs = [ground.height(x + dx, z + dz) for dx in (-reach, reach) for dz in (-reach, reach)]
    return all(v is None for v in hs) or (None not in hs and max(hs) - min(hs) <= level)


def scatter_walked(m, spots, count, seed, kinds, spacing=2.5, avoid=(), rest=None, level=0.25, ground=None):
    """`scatter_cover` over `walked_spots`, for the cover `scatter_cover` found no level floor for (terrain,
    terraces off the seekers' floor). `rest(x, z, y)` gives the height a prop is set at (the stepped
    field's top, which `swap_terrain` lands on the heightfield) or None; on `ground` a spot whose corners
    differ by more than `level` metres is skipped, so a piece does not hang off a slope."""
    rng = random.Random(seed)
    spots = list(spots)
    rng.shuffle(spots)
    taken = [(q["at"][0], q["at"][2]) for q in m.props]
    placed = 0
    for x, h, z in spots:
        if placed >= count:
            break
        if not all((x - a) ** 2 + (z - b) ** 2 >= rad ** 2 for a, b, rad in avoid) or not all((x - a) ** 2 + (z - b) ** 2 >= spacing ** 2 for a, b in taken):
            continue
        if not level_on(ground, x, z, 0.75, level):
            continue
        y = rest(x, z, h) if rest else h
        if y is None:
            continue
        m.prop(rng.choice(kinds), x, z, yaw=rng.choice((0.0, 90.0, 180.0, 270.0)), y=y)
        taken.append((x, z))
        placed += 1
    return placed


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
        gx, gy, gz = gd(reader.door_hinge(e)[0])
        hx, hy, hz = gx - ox, gy - oy, gz - oz
        if any(abs(hx - a) < 0.8 and abs(hz - b) < 0.8 for a, b in skip):
            continue
        fy = max([b["at"][1] + b["size"][1] / 2 for b in doc["boxes"] if b.get("solid", True) and within(b, hx, hz) and b["at"][1] + b["size"][1] / 2 <= hy + 0.1] or [0.0])
        # The hinge stands on the wall line, often a hair's gap between floor boxes: a floor up to 0.15 m
        # above the one found there is the room's (a door hung on the slab below had its panel in it).
        fy = max([t for t in (b["at"][1] + b["size"][1] / 2 for b in doc["boxes"] if b.get("solid", True) and within(b, hx, hz, 0.02))
                  if fy <= t <= min(fy + 0.15, hy + 0.1)] or [fy])
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


@passledger.tracked("merge_touching", lambda boxes, *a, **k: boxes)
def merge_touching(boxes, tol=0.002):
    """Merges axis-aligned boxes of one material that touch face to face with the same cross-section.

    Repeats along each axis until nothing joins; a turned box is left alone. Returns how many boxes went."""
    start = len(boxes)
    keep = [b for b in boxes if b.get("yaw")]
    work = [b for b in boxes if not b.get("yaw")]
    changed = True
    while changed:
        changed = False
        for ax in (1, 0, 2):
            o1, o2 = [a for a in (0, 1, 2) if a != ax]
            groups = {}
            for b in work:
                attrs = tuple(sorted((k, repr(v)) for k, v in b.items() if k not in ("at", "size")))
                key = (attrs, round(b["at"][o1] / tol), round(b["size"][o1] / tol),
                       round(b["at"][o2] / tol), round(b["size"][o2] / tol))
                groups.setdefault(key, []).append(b)
            out = []
            for grp in groups.values():
                grp.sort(key=lambda b: b["at"][ax] - b["size"][ax] / 2)
                cur = grp[0]
                for b in grp[1:]:
                    lo, hi = cur["at"][ax] - cur["size"][ax] / 2, cur["at"][ax] + cur["size"][ax] / 2
                    blo, bhi = b["at"][ax] - b["size"][ax] / 2, b["at"][ax] + b["size"][ax] / 2
                    if blo <= hi + tol:
                        top = max(hi, bhi)
                        cur = dict(cur)
                        cur["at"] = list(cur["at"])
                        cur["size"] = list(cur["size"])
                        cur["at"][ax] = round((lo + top) / 2, 3)
                        cur["size"][ax] = round(top - lo, 3)
                        changed = True
                    else:
                        out.append(cur)
                        cur = b
                out.append(cur)
            work = out
    boxes[:] = keep + work
    return start - len(boxes)


@passledger.tracked("drop_trim", lambda boxes, *a, **k: boxes)
def drop_trim(boxes, min_volume=0.0, min_thickness=0.0, panel=1.0, walkable=0.25):
    """Drops detail boxes below a volume or thinner than a thickness (a moulding, a skirting, a frame).

    A box whose longest side reaches `panel` metres, or whose footprint (x by z) reaches `walkable` square
    metres, is a wall, header, floor or stair step and stays; an unseen collision box (visible false) always
    stays. Returns how many went."""
    def trim(b):
        if b.get("visible", True) is False:
            return False
        s = b["size"]
        # A long box (a wall, a header, a floor panel) and a walkable top (a stair step) are structure, not trim.
        if max(s) >= panel or s[0] * s[2] >= walkable:
            return False
        if min_volume > 0.0 and s[0] * s[1] * s[2] < min_volume:
            return True
        return min_thickness > 0.0 and min(s) < min_thickness
    n = len(boxes)
    boxes[:] = [b for b in boxes if not trim(b)]
    return n - len(boxes)


def floor_islands(boxes, cell=0.25, step=0.4, head=1.4):
    """Labels the walkable floor of a document: (islands, state_of), no body radius, any height.

    A surface is a solid box's top with nothing solid between 0.3 m and `head` above it; two
    neighbouring cells join when their surfaces differ by at most `step` (the bots' climb).
    `islands` is [(cells, [states])] largest first; `state_of(x, z, y)` is the state index of the
    surface under a point (within 0.3 m of y), or None. A state is (zi, xi, top)."""
    solid = [b for b in boxes if b.get("solid", True)]
    if not solid:
        return [], lambda x, z, y: None
    x0 = min(b["at"][0] - b["size"][0] / 2 for b in solid) - 1.0
    z0 = min(b["at"][2] - b["size"][2] / 2 for b in solid) - 1.0
    W = int((max(b["at"][0] + b["size"][0] / 2 for b in solid) + 1.0 - x0) / cell) + 1
    H = int((max(b["at"][2] + b["size"][2] / 2 for b in solid) + 1.0 - z0) / cell) + 1
    spans = {}

    def over(b, grow):
        hx, hz = b["size"][0] / 2, b["size"][2] / 2
        if b.get("yaw"):
            hx = hz = math.hypot(hx, hz)
        for zi in range(max(0, int((b["at"][2] - hz - z0) / cell)), min(H, int((b["at"][2] + hz - z0) / cell) + 2)):
            for xi in range(max(0, int((b["at"][0] - hx - x0) / cell)), min(W, int((b["at"][0] + hx - x0) / cell) + 2)):
                if grow or within(b, x0 + (xi + 0.5) * cell, z0 + (zi + 0.5) * cell):
                    yield zi * W + xi

    for b in solid:
        lo, hi = round(b["at"][1] - b["size"][1] / 2, 3), round(b["at"][1] + b["size"][1] / 2, 3)
        thin = min(b["size"][0], b["size"][2]) < cell
        for i in over(b, thin):
            spans.setdefault(i, []).append((lo, hi, thin))
    surfaces = {}
    for i, sp in spans.items():
        for lo, hi, thin in sp:
            if thin and hi - lo < 0.5:
                continue
            if not any(l2 < hi + head and h2 > hi + 0.3 for l2, h2, _t in sp):
                if hi not in surfaces.setdefault(i, []):
                    surfaces[i].append(hi)
    label = {}
    islands = []
    for i0 in sorted(surfaces):
        for t0 in surfaces[i0]:
            if (i0, t0) in label:
                continue
            members = [(i0, t0)]
            label[(i0, t0)] = len(islands)
            k = 0
            while k < len(members):
                i, t = members[k]
                k += 1
                zi, xi = divmod(i, W)
                for dz, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nz, nx = zi + dz, xi + dx
                    if not (0 <= nz < H and 0 <= nx < W):
                        continue
                    n = nz * W + nx
                    for t2 in surfaces.get(n, ()):
                        if abs(t2 - t) <= step and (n, t2) not in label:
                            label[(n, t2)] = len(islands)
                            members.append((n, t2))
            islands.append(members)
    order = sorted(range(len(islands)), key=lambda k: -len(islands[k]))
    rank = {k: r for r, k in enumerate(order)}
    ranked = [[(divmod(i, W), t) for i, t in islands[k]] for k in order]

    def state_of(x, z, y):
        zi, xi = int((z - z0) / cell), int((x - x0) / cell)
        if not (0 <= zi < H and 0 <= xi < W):
            return None
        i = zi * W + xi
        best = min(((abs(t - y), t) for t in surfaces.get(i, ()) if abs(t - y) <= 0.3), default=None)
        return None if best is None else (rank[label[(i, best[1])]], zi, xi, best[1])

    return [(len(m), m) for m in ranked], state_of, (x0, z0, cell)


@passledger.tracked("start_island", lambda doc, *a, **k: doc["boxes"])
def restart_on_largest_island(doc, size_of, footprint, props_wanted=8, hunters_wanted=3, spacing=3.0, log=print):
    """Puts the start and hunter spawns on the largest connected floor island (--start-island).

    A map whose author starts are scattered by order can put the props' first start on a small
    isolated platform while the hiding places are on the big floor, and every place then reads
    as cut off. Spawns already on it stay; the rest are dropped and topped up
    from its clearest open floor, `spacing` m apart. Toys off the island follow to its spots.
    The island is the largest one that holds at least one author spawn (all of them if none do).
    Returns the number of spawns moved, or None when the document has no floor."""
    islands, state_of, (x0, z0, cell) = floor_islands(doc["boxes"])
    if not islands:
        return None
    log("floor islands: %s cells (largest first)" % ", ".join(str(n) for n, _m in islands[:6]))
    # Roofs and wall tops are islands too, so the biggest must be one an author start stands on.
    own = {s[0] for side in doc["spawns"].values() for sp in side
           for s in [state_of(sp["at"][0], sp["at"][2], sp["at"][1] - 0.05)] if s is not None}
    top = min(own) if own else 0
    members = islands[top][1]
    cells = {(zi, xi, t) for (zi, xi), t in members}
    flat = {}
    for zi, xi, t in cells:
        flat.setdefault((zi, xi), []).append(t)

    def on_island(at, base=0.05):
        s = state_of(at[0], at[2], at[1] - base)
        return s is not None and s[0] == top

    props = [q for q in doc["props"]]

    def clear_of_props(x, y, z):
        for q in props:
            sx, sy, sz = size_of(q["id"])
            fw, fd = footprint(q["id"], q.get("yaw", 0.0))
            if q["at"][1] < y + 1.4 and q["at"][1] + sy > y + 0.1 and abs(x - q["at"][0]) < fw / 2 + 0.5 and abs(z - q["at"][2]) < fd / 2 + 0.5:
                return False
        return True

    def room(zi, xi, t, r):
        """How many of the (2r+1)^2 cells round this one are the same island at about this level."""
        return sum(1 for dz in range(-r, r + 1) for dx in range(-r, r + 1)
                   if any(abs(t2 - t) <= 0.4 for t2 in flat.get((zi + dz, xi + dx), ())))

    cx = sum(zi for zi, xi, t in cells) / len(cells)
    cz = sum(xi for zi, xi, t in cells) / len(cells)
    r = max(1, int(1.5 / cell))
    full = (2 * r + 1) ** 2
    cand = sorted(((zi, xi, t) for zi, xi, t in cells if room(zi, xi, t, r) == full),
                  key=lambda c: ((c[0] - cx) ** 2 + (c[1] - cz) ** 2, c[0], c[1]))
    kept = {side: [sp for sp in doc["spawns"][side] if on_island(sp["at"])] for side in ("props", "hunters")}
    taken = [(sp["at"][0], sp["at"][2]) for side in kept.values() for sp in side]
    moved = sum(len(doc["spawns"][s]) - len(kept[s]) for s in kept)
    for side, want in (("props", props_wanted), ("hunters", hunters_wanted)):
        for zi, xi, t in cand:
            if len(kept[side]) >= want:
                break
            x, z = x0 + (xi + 0.5) * cell, z0 + (zi + 0.5) * cell
            if all((x - a) ** 2 + (z - b) ** 2 >= spacing ** 2 for a, b in taken) and clear_of_props(x, t, z):
                kept[side].append({"at": [round(x, 3), round(t + 0.05, 3), round(z, 3)], "yaw": 0})
                taken.append((x, z))
    doc["spawns"].update(kept)
    for toy in doc.get("toys", []):
        if on_island(toy["at"], 0.0):
            continue
        for zi, xi, t in cand:
            x, z = x0 + (xi + 0.5) * cell, z0 + (zi + 0.5) * cell
            if all((x - a) ** 2 + (z - b) ** 2 >= 4.0 for a, b in taken) and clear_of_props(x, t, z):
                toy["at"] = [round(x, 3), round(t, 3), round(z, 3)]
                taken.append((x, z))
                break
    return moved


@passledger.tracked("drop_other_terrain", lambda doc, *a, **k: doc["boxes"])
def drop_other_terrain(doc, material="grass", min_cells=2000, log=print):
    """Drops ground slabs of a big floor island no spawn stands on (--start-island).

    A terrace below a cliff is a pit: the bots drop into it, nothing climbs out, and the nav query
    for any goal beyond fails. Only `material` slabs go, and only when their island is larger than
    `min_cells`, so a roof or a small platform stays. Props left standing on nothing are dropped
    by the audit that follows. Returns the number of slabs dropped."""
    islands, state_of, _grid = floor_islands(doc["boxes"])
    own = {s[0] for side in doc["spawns"].values() for sp in side
           for s in [state_of(sp["at"][0], sp["at"][2], sp["at"][1] - 0.05)] if s is not None}
    if not own:
        return 0
    big = {n for n, (cells, _m) in enumerate(islands) if cells >= min_cells and n not in own}
    keep = []
    for b in doc["boxes"]:
        if b.get("mat") == material and b.get("solid", True):
            s = state_of(b["at"][0], b["at"][2], b["at"][1] + b["size"][1] / 2)
            if s is not None and s[0] in big:
                continue
        keep.append(b)
    gone = len(doc["boxes"]) - len(keep)
    doc["boxes"][:] = keep
    if gone and log:
        log("dropped %d ground slabs of islands no spawn stands on" % gone)
    return gone


def budget_flag(arg, opts):
    """Reads --merge-boxes, --min-box-volume=<m3>, --min-box-thickness=<m>, --max-boxes=<n>, --max-wire=<bytes>, --drop-sky-slab and --keep-reach into opts; True when arg was one."""
    if arg == "--merge-boxes":
        opts["merge"] = True
    elif arg.startswith("--min-box-volume="):
        opts["volume"] = float(arg.split("=", 1)[1])
    elif arg.startswith("--min-box-thickness="):
        opts["thickness"] = float(arg.split("=", 1)[1])
    elif arg.startswith("--max-boxes="):
        opts["max"] = int(arg.split("=", 1)[1])
    elif arg.startswith("--max-wire="):
        opts["wire"] = int(arg.split("=", 1)[1])
    elif arg == "--drop-sky-slab":
        opts["sky"] = True
    elif arg == "--keep-reach":
        opts["keep_reach"] = True
    else:
        return False
    return True


def apply_budget(boxes, opts, doc=None):
    """Runs the opt-in box budget (sky slab, merge, trim) and prints the counts; nothing happens with no flag.

    --drop-sky-slab needs `doc` (it looks at the spawns, props and lights). --keep-reach (needs `doc` too)
    measures where the spawns can walk before and after, and puts back the trimmed boxes a lost route needs."""
    if not any(k in opts for k in ("merge", "volume", "thickness", "sky")):
        return
    before = len(boxes)
    sky = drop_sky_slab(doc, boxes) if opts.get("sky") and doc is not None else 0
    snapshot = list(boxes) if opts.get("keep_reach") and doc is not None else None
    merged = merge_touching(boxes) if opts.get("merge") else 0
    trimmed = drop_trim(boxes, opts.get("volume", 0.0), opts.get("thickness", 0.0))
    print("box budget: %d boxes, sky slab %d, merged %d, dropped %d trim, %d left" % (before, sky, merged, trimmed, len(boxes)))
    if snapshot is not None and (merged or trimmed):
        keep_reach(doc, boxes, snapshot)


@passledger.tracked("drop_sky_slab", lambda doc, boxes=None, **k: doc["boxes"] if boxes is None else boxes)
def drop_sky_slab(doc, boxes=None, thick=1.0, share=0.25, clear=1.8):
    """Drops the author's sky ceiling: an unseen (visible false) solid slab, thin, covering `share` of the map's
    footprint, whose underside is `clear` metres over every spawn, prop and light. It is one big box the physics
    and the bots' mesh carry, over a map whose walls already close it. Unseen side walls stay.
    Returns how many went."""
    boxes = doc["boxes"] if boxes is None else boxes
    solid = [b for b in boxes if b.get("solid", True)]
    if not solid:
        return 0
    x0 = min(b["at"][0] - b["size"][0] / 2 for b in solid)
    x1 = max(b["at"][0] + b["size"][0] / 2 for b in solid)
    z0 = min(b["at"][2] - b["size"][2] / 2 for b in solid)
    z1 = max(b["at"][2] + b["size"][2] / 2 for b in solid)
    area = max((x1 - x0) * (z1 - z0), 1e-6)
    top = max([a[1] for a in _anchors(doc)] or [-1e9])

    def sky(b):
        return (b.get("visible", True) is False and b.get("solid", True) and not b.get("yaw")
                and b["size"][1] <= thick and b["size"][0] * b["size"][2] >= share * area
                and b["at"][1] - b["size"][1] / 2 >= top + clear)
    n = len(boxes)
    boxes[:] = [b for b in boxes if not sky(b)]
    return n - len(boxes)


@passledger.tracked("keep_reach", lambda doc, boxes, *a, **k: boxes)
def keep_reach(doc, boxes, original, log=print):
    """After a trim, restores the boxes the trim cut that a walkable route needs (largest first, the fewest).

    A place the first seeker start could walk to before (a coarse metre cell and floor height) that is no longer
    reached is a lost route: a spiral stair's thin steps that the trim took, leaving the top floor joined to
    nothing. `boxes` is the trimmed list (edited in place), `original` what it was; only boxes that are not in
    `boxes` by identity are candidates (a merge makes new ones). Returns how many came back."""
    start = _first_start(doc)
    if start is None:
        return 0
    have = {id(b) for b in boxes}
    cut = [b for b in original if id(b) not in have]
    if not cut:
        return 0
    want = _reach_keys(original, start)

    def lacks(extra):
        return want - _reach_keys(boxes + extra, start)

    if not lacks([]):
        return 0
    cut.sort(key=lambda b: -(b["size"][0] * b["size"][1] * b["size"][2]))
    if lacks(cut):
        log("keep reach: %d places lost to the merge could not be restored (merge changes shapes)" % len(lacks(cut)))
        return 0
    lo, hi = 1, len(cut)
    while lo < hi:
        mid = (lo + hi) // 2
        if lacks(cut[:mid]):
            lo = mid + 1
        else:
            hi = mid
    boxes.extend(cut[:lo])
    log("keep reach: restored %d trimmed boxes that join %d places" % (lo, len(want)))
    return lo


def _first_start(doc):
    """The seekers' first start (the walk's origin), else the first start of any team."""
    sp = doc.get("spawns", {})
    for key in ("seekers", *sp):
        if sp.get(key):
            return tuple(sp[key][0]["at"])
    return None


def _reach_keys(boxes, start):
    """{(x metre, z metre, floor metre)} of the places a body walking from `start` reaches: a coarse key, so a
    box swapped for a near neighbour does not read as a lost place."""
    _, seen, _ = _flood(boxes, start, 0.25, 0.45, 1.7)
    return {(int(xi * 0.25 // 1), int(zi * 0.25 // 1), int(t // 1)) for xi, zi, t in seen}


def _intervals(boxes, cell):
    """{(xi, zi): [(lo, hi, box index)]} of the solid boxes over a grid of `cell` metres (a turned box by its bounding square)."""
    cols = {}
    for i, b in enumerate(boxes):
        if not b.get("solid", True):
            continue
        hx, hz = b["size"][0] / 2, b["size"][2] / 2
        if b.get("yaw"):
            hx = hz = math.hypot(hx, hz)
        lo, hi = b["at"][1] - b["size"][1] / 2, b["at"][1] + b["size"][1] / 2
        for xi in range(int((b["at"][0] - hx) // cell), int((b["at"][0] + hx) // cell) + 1):
            for zi in range(int((b["at"][2] - hz) // cell), int((b["at"][2] + hz) // cell) + 1):
                if not b.get("yaw") or within(b, (xi + 0.5) * cell, (zi + 0.5) * cell):
                    cols.setdefault((xi, zi), []).append((lo, hi, i))
    return cols


def _anchors(doc):
    """The points that need ground under them: every spawn, prop and light, as (x, y, z)."""
    pts = [tuple(s["at"]) for lst in doc.get("spawns", {}).values() for s in lst]
    pts += [tuple(q["at"]) for q in doc.get("props", [])]
    pts += [tuple(q["at"]) for q in doc.get("lights", [])]
    return pts


def cap_protected(doc, grid=2.0):
    """Indices of the boxes --max-boxes never cuts: a floor or stair, a door's frame, the ground under an anchor.

    A floor or stair is a box with a walkable top (footprint 0.25 m2 or more, no side under 0.3 m) and
    headroom over it; a door's frame is any box within 0.15 m of a door's leaf; the ground under a
    spawn, prop or light is the highest top within 0.35 m above its feet."""
    boxes = doc["boxes"]
    keep = set()
    cols = {}
    for i, b in enumerate(boxes):
        if not b.get("solid", True):
            continue
        for xi in range(int((b["at"][0] - b["size"][0] / 2) // grid) - 1, int((b["at"][0] + b["size"][0] / 2) // grid) + 2):
            for zi in range(int((b["at"][2] - b["size"][2] / 2) // grid) - 1, int((b["at"][2] + b["size"][2] / 2) // grid) + 2):
                cols.setdefault((xi, zi), []).append(i)

    def near(x0, x1, z0, z1):
        seen = set()
        for xi in range(int(x0 // grid), int(x1 // grid) + 1):
            for zi in range(int(z0 // grid), int(z1 // grid) + 1):
                seen.update(cols.get((xi, zi), ()))
        return seen

    def reach_of(b):
        hx, hz = b["size"][0] / 2, b["size"][2] / 2
        return (math.hypot(hx, hz),) * 2 if b.get("yaw") else (hx, hz)

    def walkable(i):
        """True when nothing that replaces box i's top lies within head height above it."""
        b = boxes[i]
        hx, hz = reach_of(b)
        top = b["at"][1] + b["size"][1] / 2
        x, z = b["at"][0], b["at"][2]
        area = 4 * hx * hz
        over = 0.0
        for j in near(x - hx, x + hx, z - hz, z + hz):
            o = boxes[j]
            if j == i or o.get("yaw") or o["at"][1] - o["size"][1] / 2 >= top + 1.8 or o["at"][1] + o["size"][1] / 2 <= top + 0.05:
                continue
            w = min(x + hx, o["at"][0] + o["size"][0] / 2) - max(x - hx, o["at"][0] - o["size"][0] / 2)
            d = min(z + hz, o["at"][2] + o["size"][2] / 2) - max(z - hz, o["at"][2] - o["size"][2] / 2)
            if w > 0.05 and d > 0.05:
                over += w * d
        return over < 0.5 * area

    steps = []      # shallow or turned treads, kept only when they chain to a neighbouring height
    for i, b in enumerate(boxes):
        if not b.get("solid", True):
            continue
        sx, sy, sz = b["size"]
        if sx * sz < 0.25 or min(sx, sz) < 0.3:
            if sx * sz >= 0.05 and min(sx, sz) >= 0.15 and walkable(i):
                steps.append(i)
            continue
        if walkable(i):
            keep.add(i)
    for i in steps:
        b = boxes[i]
        hx, hz = reach_of(b)
        r = math.hypot(hx, hz)
        top = b["at"][1] + b["size"][1] / 2
        for j in near(b["at"][0] - r - 0.1, b["at"][0] + r + 0.1, b["at"][2] - r - 0.1, b["at"][2] + r + 0.1):
            o = boxes[j]
            if j == i or not o.get("solid", True) or min(o["size"][0], o["size"][2]) < 0.15:
                continue
            ot = o["at"][1] + o["size"][1] / 2
            ro = math.hypot(o["size"][0] / 2, o["size"][2] / 2)
            if 0.03 <= abs(ot - top) <= 0.5 and math.hypot(o["at"][0] - b["at"][0], o["at"][2] - b["at"][2]) <= r + ro + 0.1:
                keep.add(i)
                break
    for d in doc.get("doors", []):
        dx, dy, dz = d["at"]
        hx, hy, hz = d["size"][0] / 2 + 0.15, d["size"][1] / 2 + 0.15, d["size"][2] / 2 + 0.15
        if abs(math.sin(math.radians(d.get("yaw", 0.0)))) > 0.7071:
            hx, hz = hz, hx         # a door in a z wall is turned: its width runs along z
        for j in near(dx - hx, dx + hx, dz - hz, dz + hz):
            o = boxes[j]
            if abs(o["at"][0] - dx) <= hx + o["size"][0] / 2 and abs(o["at"][1] - dy) <= hy + o["size"][1] / 2 and abs(o["at"][2] - dz) <= hz + o["size"][2] / 2:
                keep.add(j)
    def hold(x, y, z):
        """Keeps the ground at (x, z) for feet at y: the highest top at or under y + 0.35 and the support one step below it."""
        under = sorted(((o["at"][1] + o["size"][1] / 2, j) for j in near(x, x, z, z) for o in (boxes[j],)
                        if o["at"][1] + o["size"][1] / 2 <= y + 0.35 and within(o, x, z)), reverse=True)
        if not under:
            return
        best = under[0][0]
        keep.update(j for t, j in under if t >= best - 0.05)
        lower = [(t, j) for t, j in under if best - 0.5 <= t < best - 0.05]
        if lower:
            nxt = lower[0][0]
            keep.update(j for t, j in lower if t >= nxt - 0.05)

    for x, y, z in _anchors(doc):
        hold(x, y, z)
    for lst in doc.get("spawns", {}).values():
        for sp in lst:
            x, y, z = sp["at"]
            for ox, oz in ((0.75, 0), (-0.75, 0), (0, 0.75), (0, -0.75)):
                hold(x + ox, y, z + oz)
    return keep


def _flood(boxes, start_pt, cell, step, head):
    """(places, seen, find): the standing places per grid column, the set of (xi, zi, top) reached from
    `start_pt`, and find(point) -> the (xi, zi, top) a point stands on or None."""
    cols = _intervals(boxes, cell)
    places = {}
    for k, iv in cols.items():
        iv.sort()
        merged = []
        for lo, hi, _ in iv:
            if merged and lo <= merged[-1][1] + 0.02:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        places[k] = [m[1] for n, m in enumerate(merged) if n + 1 == len(merged) or merged[n + 1][0] - m[1] >= head]

    def find(p):
        xi, zi = int(p[0] // cell), int(p[2] // cell)
        best = None
        for dx in (0, -1, 1):
            for dz in (0, -1, 1):
                for t in places.get((xi + dx, zi + dz), ()):
                    if t <= p[1] + 0.5 and (best is None or t > best[2]):
                        best = (xi + dx, zi + dz, t)
        return best

    start = find(start_pt)
    seen = set()
    if start is not None:
        seen.add((start[0], start[1], round(start[2], 3)))
        stack = [start]
        while stack:
            xi, zi, t = stack.pop()
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                for t2 in places.get((xi + dx, zi + dz), ()):
                    key = (xi + dx, zi + dz, round(t2, 3))
                    if abs(t2 - t) <= step and key not in seen:
                        seen.add(key)
                        stack.append((xi + dx, zi + dz, t2))
    return places, seen, find


def reach_report(doc, boxes=None, cell=0.25, step=0.45, head=1.7):
    """Which spawns a body could walk to from the first one, over the document's boxes (or `boxes`).

    A multi-storey flood on a `cell` grid: a column's standing places are the tops of its solid boxes with
    `head` metres clear above, and two neighbouring places join when their tops differ by `step` or less.
    Props and body radius are left out (prune_pockets owns those): this is for comparing a document
    before and after boxes are cut. Returns (reached, total, unreached spawn indices in list order)."""
    boxes = doc["boxes"] if boxes is None else boxes
    spawns = [s["at"] for lst in doc.get("spawns", {}).values() for s in lst]
    if not spawns:
        return 0, 0, []
    places, seen, find = _flood(boxes, spawns[0], cell, step, head)
    if find(spawns[0]) is None:
        return 0, len(spawns), list(range(len(spawns)))
    lost = []
    for n, p in enumerate(spawns):
        f = find(p)
        if f is None or (f[0], f[1], round(f[2], 3)) not in seen:
            lost.append(n)
    return len(spawns) - len(lost), len(spawns), lost


@passledger.tracked("box_cap", lambda doc, *a, **k: doc["boxes"])
def cap_boxes(doc, limit, log=print):
    """Cuts the least important boxes until `limit` or fewer are left (--max-boxes); returns how many were cut.

    Smallest volume first, never a box cap_protected names. The spawns' reach is measured before and
    after (reach_report); a loss restores the cut boxes needed to reconnect, or exits non-zero. A document already at or under `limit` is not touched."""
    boxes = doc["boxes"]
    if len(boxes) <= limit:
        return 0
    before = len(boxes)
    reach0 = reach_report(doc)
    keep = cap_protected(doc)
    order = sorted((i for i in range(len(boxes)) if i not in keep), key=lambda i: (boxes[i]["size"][0] * boxes[i]["size"][1] * boxes[i]["size"][2], i))
    cut = order[:max(0, before - limit)]
    vol = lambda i: boxes[i]["size"][0] * boxes[i]["size"][1] * boxes[i]["size"][2]
    lost0 = set(reach0[2])

    def lost_after(restored):
        gone = set(cut) - set(restored)
        return set(reach_report(doc, [b for i, b in enumerate(boxes) if i not in gone])[2]) - lost0

    restored = []
    if lost_after([]):
        # Restore the fewest cut boxes, largest first: the smallest prefix of that order that
        # brings every spawn back (binary search; the full set is the document as it was).
        big = sorted(cut, key=lambda i: (-vol(i), i))
        lo, hi = 1, len(big)
        while lo < hi:
            mid = (lo + hi) // 2
            if lost_after(big[:mid]):
                lo = mid + 1
            else:
                hi = mid
        restored = big[:lo]
        if lost_after(restored):
            raise SystemExit("box cap: reach dropped and restoring every cut box did not bring it back")
        log("box cap: cutting lost reach, restored %d of %d cut boxes (largest first)" % (len(restored), len(cut)))
    gone = set(cut) - set(restored)
    biggest = max((boxes[i] for i in gone), key=lambda b: b["size"][0] * b["size"][1] * b["size"][2], default=None)
    doc["boxes"][:] = [b for i, b in enumerate(boxes) if i not in gone]
    msg = "box cap: %d boxes over --max-boxes=%d, cut %d, %d left (%d protected)" % (before, limit, len(gone), len(doc["boxes"]), len(keep))
    if biggest is not None:
        s = biggest["size"]
        msg += "; largest cut %.2f m3 at (%.1f, %.1f, %.1f) size %.2f x %.2f x %.2f" % (s[0] * s[1] * s[2], *biggest["at"], *s)
    log(msg)
    if len(doc["boxes"]) > limit:
        log("box cap: STILL OVER by %d: the rest are floors, stairs, door frames, the ground under a spawn, prop or light, or boxes a route needs" % (len(doc["boxes"]) - limit))
    reach1 = reach_report(doc)
    log("box cap: spawns reachable from the first: %d of %d before, %d of %d after" % (reach0[0], reach0[1], reach1[0], reach1[1]))
    return len(gone)


def place_hiders(doc, per_level=4, spacing=3.0, seeker_gap=4.0, min_area=4.0, log=print):
    """Puts the hiders on floor the seekers can walk to, a few on every storey.

    The flood runs from the first seeker start over the document's boxes (reach_report's rules). A hider start the
    seekers cannot reach is dropped; a storey is a floor height (to 0.1 m) with `min_area` m2 or more of reachable floor, and
    each is topped up to `per_level` hiders on open floor (a half metre of reachable floor all round) `spacing` m
    from the other hiders and `seeker_gap` m from the seekers. Returns {floor height: hiders on it}, empty with no
    seeker start or nothing reachable (the document is then not touched)."""
    start = _first_start(doc)
    if start is None or not doc.get("spawns", {}).get("seekers"):
        return {}
    cell = 0.25
    _, seen, find = _flood(doc["boxes"], start, cell, 0.45, 1.7)
    if not seen:
        return {}
    bins = {}
    for xi, zi, t in seen:
        bins.setdefault(round(t / 0.1), []).append((xi, zi, t))
    levels = []
    for k in sorted(bins):
        if len(bins[k]) * cell * cell < min_area:
            continue        # a stair's treads or a ledge: too little floor at one height to be a storey
        if levels and k - levels[-1][0] <= 3:
            levels[-1][1].extend(bins[k])
            levels[-1][0] = k
        else:
            levels.append([k, list(bins[k])])
    levels = [cells for _, cells in levels]
    hiders = doc["spawns"].setdefault("hiders", [])
    kept = []
    for h in hiders:
        f = find(h["at"])
        if f is not None and (f[0], f[1], round(f[2], 3)) in seen:
            kept.append(h)
    if len(kept) != len(hiders):
        log("hiders: %d of %d starts were not walkable from the seekers, dropped" % (len(hiders) - len(kept), len(hiders)))
    hiders[:] = kept
    seekers = [s["at"] for s in doc["spawns"]["seekers"]]
    out = {}
    for cells in levels:
        ts = sorted(t for _, _, t in cells)
        floor = ts[len(ts) // 2]
        have = [h for h in hiders if abs(h["at"][1] - 0.05 - floor) < 0.8]
        out[round(floor, 2)] = len(have)
        flat = {(xi, zi): t for xi, zi, t in cells if abs(t - floor) <= 0.3}
        want = per_level - len(have)
        if want <= 0:
            continue
        pts = [h["at"] for h in hiders]
        for xi, zi in sorted(flat, key=lambda c: (c[0] * 7919 + c[1] * 104729) % 1009):
            if want <= 0:
                break
            if not all((xi + dx, zi + dz) in flat for dx in (-2, 0, 2) for dz in (-2, 0, 2)):
                continue
            x, z = (xi + 0.5) * cell, (zi + 0.5) * cell
            if any((x - q[0]) ** 2 + (z - q[2]) ** 2 < seeker_gap ** 2 for q in seekers) \
                    or any((x - q[0]) ** 2 + (z - q[2]) ** 2 < spacing ** 2 and abs(q[1] - floor - 0.05) < 1.0 for q in pts):
                continue
            # on the cell's own walkable height, not the storey's median: a carpet or rug 5 cm up is a box a start at the median stands in
            hiders.append({"at": [round(x, 3), round(flat[(xi, zi)] + 0.05, 3), round(z, 3)], "yaw": 0.0})
            pts.append(hiders[-1]["at"])
            out[round(floor, 2)] += 1
            want -= 1
    log("hiders: %d storeys, starts per storey %s" % (len(levels), sorted(out.items())))
    return out


def wire_size(doc):
    """Bytes the document takes on the wire: compact JSON, deflated (what the games' WIRE_LIMIT counts)."""
    return len(zlib.compress(json.dumps(doc, separators=(",", ":")).encode()))


def fit_wire(doc, budget, log=print):
    """Cuts the smallest unprotected boxes until the document deflates to `budget` bytes or fewer (--max-wire); returns how many were cut.

    A game sends a map in one WebSocket message with a hard size limit, and the box count alone does not hold a
    detailed map under it (gm_villa: 5500 boxes are 88 KB deflated). Boxes are rounded to centimetres first, then
    the box cap (`cap_boxes`, so floors, stairs, door frames and the ground under anchors stay and lost reach is
    restored) is run to the largest count that fits, found by bisection on the cut count."""
    for b in doc["boxes"]:
        b["at"] = [round(v, 2) for v in b["at"]]
        b["size"] = [round(max(v, 0.01), 2) for v in b["size"]]
    start = wire_size(doc)
    if start <= budget:
        return 0
    keep = cap_protected(doc)
    boxes = doc["boxes"]
    order = sorted((i for i in range(len(boxes)) if i not in keep), key=lambda i: (boxes[i]["size"][0] * boxes[i]["size"][1] * boxes[i]["size"][2], i))
    base = dict(doc)

    def size_cutting(n):
        gone = set(order[:n])
        base["boxes"] = [b for i, b in enumerate(boxes) if i not in gone]
        return wire_size(base)

    lo, hi = 0, len(order)
    while lo < hi:
        mid = (lo + hi) // 2
        if size_cutting(mid) > budget:
            lo = mid + 1
        else:
            hi = mid
    if size_cutting(lo) > budget:
        log("wire budget: STILL OVER: %d bytes with every cuttable box gone (budget %d)" % (size_cutting(lo), budget))
    total = 0
    n = len(boxes) - lo
    while True:
        total += cap_boxes(doc, n, log)
        # cap_boxes restores boxes a route needs, so the result can be a few over: tighten and repeat.
        now = wire_size(doc)
        if now <= budget or len(doc["boxes"]) <= len(keep) or n <= 0:
            break
        n = len(doc["boxes"]) - max(1, (now - budget) // 8)
    log("wire budget: %d -> %d bytes deflated (--max-wire=%d), %d boxes left" % (start, wire_size(doc), budget, len(doc["boxes"])))
    return total


def drop_unsupported_props(doc, size_of, footprint, log=print):
    """Removes the props a budget left without ground or buried; returns how many went.

    The budget cuts small boxes, and a prop set on a cut tread, sill or table-top then hangs in the air (the game's
    audit casts nine rays down from the base, from 0.04 m inside to 0.12 m below) or has the centre of its body in
    a wall. Lowest first, so a lamp on a kept table stays; a prop standing on another kept prop counts as supported."""
    solid = [b for b in doc["boxes"] if b.get("solid", True)]
    cell = 2.0
    grid = {}

    def reach(b):
        hx, hz = b["size"][0] / 2, b["size"][2] / 2
        return (math.hypot(hx, hz),) * 2 if b.get("yaw") else (hx, hz)

    for b in solid:
        hx, hz = reach(b)
        for xi in range(int((b["at"][0] - hx) // cell), int((b["at"][0] + hx) // cell) + 1):
            for zi in range(int((b["at"][2] - hz) // cell), int((b["at"][2] + hz) // cell) + 1):
                grid.setdefault((xi, zi), []).append(b)

    def hit(x, z, y0, y1):
        """True when a solid box covers (x, z) at some height between y0 and y1."""
        for b in grid.get((int(x // cell), int(z // cell)), ()):
            hx, hz = reach(b)
            if abs(x - b["at"][0]) <= hx and abs(z - b["at"][2]) <= hz and b["at"][1] - b["size"][1] / 2 <= y1 and b["at"][1] + b["size"][1] / 2 >= y0:
                return True
        return False

    kept = []
    gone = []
    for q in sorted(doc["props"], key=lambda q: q["at"][1]):
        x, y, z = q["at"]
        fw, fd = footprint(q["id"], q.get("yaw", 0.0))
        sy = size_of(q["id"])[1]
        if hit(x, z, y + sy * 0.5 - 0.01, y + sy * 0.5 + 0.01):
            gone.append(q)
            continue
        ok = "ceiling" in q["id"] or "lily" in q["id"]
        for dx in (-0.3, 0.0, 0.3):
            for dz in (-0.3, 0.0, 0.3):
                if ok:
                    break
                px, pz = x + dx * fw, z + dz * fd
                ok = hit(px, pz, y - 0.12, y + 0.04) or any(
                    abs(px - k[0]) <= k[3] / 2 and abs(pz - k[2]) <= k[4] / 2 and y - 0.12 <= k[1] + k[5] <= y + 0.04 for k in kept)
        if ok:
            kept.append((x, y, z, fw, fd, sy))
        else:
            gone.append(q)
    if gone:
        ids = set(map(id, gone))
        doc["props"][:] = [q for q in doc["props"] if id(q) not in ids]
        log("budget: %d props left hanging or buried by the cut boxes removed" % len(gone))
    return len(gone)


def apply_cap(doc, opts, log=print, size_of=None, footprint=None):
    """Runs the opt-in --max-boxes cap, then the --max-wire fit, last of the passes that add or remove boxes; nothing happens without the flags.

    With `size_of` and `footprint` (the adapter's prop tables) the props the cut left hanging or buried are removed after."""
    if "max" in opts:
        cap_boxes(doc, opts["max"], log)
    if "wire" in opts:
        fit_wire(doc, opts["wire"], log)
    if size_of and footprint and ("max" in opts or "wire" in opts):
        drop_unsupported_props(doc, size_of, footprint, log)


def lend_starts(spawns, src, dst, want=3):
    """Moves starts from `src` to `dst` while `dst` has none and `src` keeps at least one (a small map whose
    top-up of `src` took every spot). Returns how many moved."""
    n = 0
    if spawns[dst]:
        return 0
    while len(spawns[src]) > 1 and n < want:
        spawns[dst].append(spawns[src].pop())
        n += 1
    return n
