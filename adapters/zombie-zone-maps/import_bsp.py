#!/usr/bin/env python3
"""Convert a Source 1 .bsp into a zombie-zone map document (maps/<id>.json).

    python3 -I tools/import_bsp.py tools/bsp/zs_ravenstreet.json path/to/zs_ravenstreet_v1.bsp [out_dir]
    python3 -I tools/import_bsp.py tools/bsp/zs_ravenstreet.json zs_ravenstreet.json [out_dir]

The second form reads the family's intermediate document (dot-map-convert/bsp.py
convert`) instead of the map; the first builds that document in memory. Either way this file
is the game's adapter: reading the format and cutting brushes into boxes are dot-map's
(`tools/bsp/`, found beside this repository or at `$DOTBSP_PATH`), so a reader fix reaches
every game that converts maps.

The game's maps are boxes, not meshes, so this reads the *brushes* (the solid volume the
engine collides with) and writes each as a box, by dot-map's `boxes.decompose`:

  * an axis-aligned brush, a brush turned about the vertical, or an upright prism that fills
    most of a turned rectangle is one box (with `yaw`);
  * anything else (a ramp, a roof, a wedge) is sliced into 0.4 m slabs along its slope, each slab
    a box spanning what the brush covers at the slab's middle. An approximation, kept small;
  * a brush with a sky, clip or all-nodraw side is an invisible wall (box `kind` sky, clip or nodraw); glass is `glass`;
  * the author's textures are never used (the game draws its own procedural surfaces): a
    material name maps to the nearest surface by `MATERIALS`.

Entities become spawns (`survivor_class`, `zombie_classes`), items, caches, lights, props
(`prop_models`: model path -> Kenney catalogue id) and barricades (`barricade_class` brush
entities, drawn as boards over their opening). The nav floors are derived from the boxes: every
cell of a half-metre grid with headroom, flood-filled from the survivor spawns across steps a
body climbs, merged into rectangles per height.

The spec JSON (tools/bsp/<id>.json) names the map, author, page and licence; the author and the
removal-on-request line go into `author` and `attribution`. The .bsp itself is never committed.
"""

import collections
import json
import math
import os
import re
import sys
import zlib
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ambient  # noqa: E402


def _dotbsp_path():
    """dot-map-convert: $DOTBSP_PATH, else the sibling checkout dot-bootstrap makes."""
    for p in (os.environ.get("DOTBSP_PATH", ""), os.path.join(HERE, "..", "..", "dot-map-convert")):
        if p and os.path.isfile(os.path.join(p, "dotbsp", "reader.py")):
            return os.path.abspath(p)
    sys.exit("import_bsp: dot-map-convert was not found; clone dot-map beside this "
             "repository (dot-bootstrap does) or set DOTBSP_PATH to its checkout")


sys.path.insert(1, _dotbsp_path())
from dotbsp import boxes as dboxes, classes as dclasses, docboxes, intermediate, reader, texturemap  # noqa: E402
from dotbsp import lights as dlights  # noqa: E402
from dotbsp import terrain as dterrain  # noqa: E402
from dotbsp import flood as dflood, movers  # noqa: E402

TERRAIN_AUTO_M2 = 500.0    # displacement ground that turns the heightfield on for a spec that does not say
# The displacement ground (dotbsp.terrain.Heightfield) the floods walk by slope; None without terrain.
TERRAIN = None
# Its walk points after the last flood, which the game's graph is built on (nav_emulate mirrors it).
TERRAIN_PTS = []
FACES = []
GRAPH_MAIN = [0, 0]    # [points on the main ground, points] of the last conversion's game graph
MAIN_SHARE_MIN = 0.6    # a whole-map graph below this share falls back to the spec's drop_small/max_boxes (see budgeted)


# A map compiled with an empty game lump (no static props) crashes dot-map's reader; the fix
# belongs there, and until it is made this adapter reads such a map as having no props.
_game_lumps = reader.Bsp.game_lumps


def _safe_game_lumps(self):
    try:
        return _game_lumps(self)
    except Exception:
        return {}


reader.Bsp.game_lumps = _safe_game_lumps

S = 0.01905           # metres per Source unit
CELL = 0.5            # nav analysis grid
DROP = 3.0            # a body drops this far
JUMP = 0.9            # and jumps up this far
STAIR_RISE = 0.32     # a 12-inch stair riser (0.3048) is a walkable step whatever a spec asks for


def flood_step(value):
    """The spec's flood_step, never below a real stair riser: 0.3 cut every 12-inch flight out of the flood and left whole storeys as islands."""
    return max(float(value), STAIR_RISE)


STEP = 0.42           # a body climbs this between neighbouring cells
THIN_WALLS = False    # set from the spec: see _thin_wall_over
THIN_LINTELS = False   # set from the spec (`thin_lintels`): see _thin_wall_over
GREEDY_FLOORS = False  # set from the spec (`greedy_floors`): see build_nav
MIN_FLOOR_Y = None    # spec min_floor_y: a sump the horde drops into and cannot climb out of is no floor
HEAD = 1.7            # headroom a floor needs
SLAB = 0.4

# The surface of a brush comes from dot-map's shared list (dot-map-convert/dotbsp/source_textures.tsv), the one every
# conversion reads; a new texture goes there, never into this file. `bsp.py unmapped <bsp>` lists what it misses.
TEXTURE_MAP = texturemap.load()

# The list's ids say what a surface IS; the game draws these (ZzMaterials). Anything not here is already a game id
# (metal, concrete, ceiling, carpet, glass, grass, parquet, wood_floor, water) and passes through.
GAME_MATERIAL = {
    "wood_planks": "wood", "door_wood": "wood", "plaster_painted": "paint", "wallpaper": "paint",
    "plaster_worn": "plaster", "stone_wall": "stone", "roof_tiles": "roof", "tile_floor": "tile",
    "brick_red": "brick", "mud": "dirt", "snow": "concrete", "flat": "concrete",
    "rock": "stone", "stone_block": "stone", "roof_clay": "roof", "ceiling_tile": "ceiling", "foliage_card": "grass",
    # See-through generics (dot-map vis.SEE_THROUGH_GENERIC): the box keeps a metal or glass look, the drawn world cuts them out.
    "fence": "metal", "grate": "metal", "bars": "metal", "ladder": "metal", "chainlink": "metal", "shield": "glass", "invisible": "concrete",
}

# Where this game had a more specific surface than the list's id, and keeps it: a road and a pavement are not
# concrete here, and a glass window in a metal or tile folder is still glass (they are drawn with their own markings and colour). Tried on the name before the list.
OVERRIDES = [
    (r"glass", "glass"),
    (r"asphalt|road", "asphalt"),
    (r"sidewalk|pavement", "sidewalk"),
]


def material_for(name):
    for pat, mat in OVERRIDES:
        if re.search(pat, name):
            return mat
    hit = TEXTURE_MAP.lookup(docboxes.classify_material(name))
    if hit is None:
        return "concrete"
    return GAME_MATERIAL.get(hit[0], hit[0])


def world_pack(map_id):
    """The pack a converted map's drawn world is published as (tools/build_worlds.py)."""
    return "zz_world_" + map_id


def world_pack_built(map_id):
    """Whether `world/<pack>/<id>.json` exists, so the game collides with the drawn world's hulls too."""
    return os.path.isfile(os.path.join(HERE, "..", "world", world_pack(map_id), map_id + ".json"))


def name_world(doc, repo_root):
    """`doc` with `"world"` after its id when `world/<pack>/<id>.json` has been built, else as it is.
    The game draws that mesh in place of the boxes (which still collide); without it, the boxes."""
    pack = world_pack(doc["id"])
    if not os.path.isfile(os.path.join(repo_root, "world", pack, doc["id"] + ".json")):
        return doc
    out = {}
    for k, v in doc.items():
        if k != "world":
            out[k] = v
        if k == "id":
            out["world"] = pack
    return out


def aim_spawns(spawns, boxes, look=5.0, reach=14.0, floors=None, goals=()):
    """Turn a survivor start that faces a wall, a bare sky edge or the drop off a deck towards the map.
    The source's `angles` are kept when eye height is clear for `look` metres and the ground goes on
    ahead (`floors`); otherwise the heading is the one that keeps to the floor, is clear for 3 m and
    lies nearest the bearing of the closest goal (post, cache, objective, route point). A heading with
    something to look at (3 m to `reach`) outranks a bare one: openness alone picked the sky on a roof deck."""
    turned = 0
    for sp in spawns:
        x, y, z = sp["at"]
        near = []
        for b in boxes:
            if not b.get("solid", True) or b.get("kind") == "glass":
                continue
            bx, by, bz = b["at"]
            sx, sy, sz = b["size"]
            if by + sy / 2 < y + 0.3 or by - sy / 2 > y + 1.6:
                continue
            if abs(bx - x) > reach + max(sx, sz) or abs(bz - z) > reach + max(sx, sz):
                continue
            near.append(b)

        def clear(yaw):
            a = math.radians(yaw)
            fx, fz = -math.sin(a), -math.cos(a)
            d = 0.4
            while d <= reach:
                px, pz = x + fx * d, z + fz * d
                for b in near:
                    dx, dz = px - b["at"][0], pz - b["at"][2]
                    if b.get("yaw"):
                        c, s_ = math.cos(math.radians(b["yaw"])), math.sin(math.radians(b["yaw"]))
                        dx, dz = dx * c - dz * s_, dx * s_ + dz * c
                    if abs(dx) <= b["size"][0] / 2 and abs(dz) <= b["size"][2] / 2:
                        return d
                d += 0.25
            return reach

        def ground(yaw):
            """Share of the points 2, 4 and 6 m ahead that stand on a floor within 0.8 m of the feet."""
            if not floors:
                return 1.0
            a = math.radians(yaw)
            hit = 0
            for d in (2.0, 4.0, 6.0):
                px, pz = x - math.sin(a) * d, z - math.cos(a) * d
                if any(f[0] <= px <= f[2] and f[1] <= pz <= f[3] and abs(f[4] - y) <= 0.8 for f in floors):
                    hit += 1
            return hit / 3.0

        goals_far = [g for g in goals if (g[0] - x) ** 2 + (g[2] - z) ** 2 > 9.0]
        goals_far = [g for g in goals_far if abs(g[1] - y) <= 4.0] or goals_far

        def off_goal(yaw):
            if not goals_far:
                return 0.0
            g = min(goals_far, key=lambda g: (g[0] - x) ** 2 + (g[2] - z) ** 2)
            gx, gz = g[0], g[2]
            want = math.degrees(math.atan2(-(gx - x), -(gz - z)))
            return abs((yaw - want + 180.0) % 360.0 - 180.0)

        cur = sp.get("yaw", 0.0)
        # Bare open space ahead is kept only when it is roughly towards a goal: a deck facing the sea is sky.
        if clear(cur) >= look and ground(cur) >= 0.6 and (clear(cur) < reach or off_goal(cur) <= 90.0):
            continue
        heads = list(range(0, 360, 15))
        best = max(heads, key=lambda h: (ground(h) >= 0.6, 3.0 <= clear(h) < reach, -round(off_goal(h) / 15.0), round(clear(h), 1)))
        if (ground(best), clear(best)) != (ground(cur), clear(cur)) and (ground(best) > ground(cur) or clear(best) > clear(cur) + 1.0):
            sp["yaw"] = float(best)
            turned += 1
    return turned


def r3(v):
    return round(v, 3)


class Brush:
    def __init__(self, planes, pts, contents, sides):
        self.planes, self.pts, self.contents, self.sides = planes, pts, contents, sides


DROPS = []    # (stage, box) of every box a stage removed, for tools/coverage_report.py (ZZ_DROP_TRACE=path writes it)


def keep_only(boxes, new, stage):
    """`boxes[:] = new`, noting what the stage removed."""
    keep = {id(b) for b in new}
    DROPS.extend((stage, b) for b in boxes if id(b) not in keep)
    boxes[:] = new


def gpt(p, y0):
    """Source (x, y, z) units to game metres."""
    return (p[0] * S, p[2] * S - y0, -p[1] * S)


def read_brush(doc, rec):
    """One brush record of the intermediate. Its planes and hull are already where the map
    put its entity (the document moves a brush entity's brushes by the entity's origin)."""
    mats = doc["materials"]
    planes = [tuple(sd["plane"]) for sd in rec["sides"]]
    sides = [(tuple(sd["plane"]), sd["flags"], mats[sd["material"]]["name"].lower()) for sd in rec["sides"]]
    return Brush(planes, [tuple(p) for p in rec["hull"]], rec["contents"], sides)


def classify(br):
    """(kind, material): kind is 'solid', 'invisible', 'sky' (the world's own box) or 'glass'."""
    names = [n for _, f, n in br.sides]
    real = [(pl, f, n) for pl, f, n in br.sides if not n.startswith("tools/")]
    if not real:
        return ("sky" if any("skybox" in n for n in names) else "invisible"), "concrete"
    if br.contents & (reader.CONTENTS_PLAYERCLIP | 0x20000):
        return "invisible", "concrete"
    top = [n for pl, f, n in real if pl[2] > 0.5]
    name = (top or [n for _, _, n in real])[0]
    if br.contents & 0x2:
        return "glass", "glass"
    return "solid", material_for(name)


def hidden_kind(br):
    """What an invisible brush is, for the game's collision: 'clip' (player or monster clip), else 'nodraw'."""
    if br.contents & (reader.CONTENTS_PLAYERCLIP | 0x20000) or any("clip" in n for _, _, n in br.sides):
        return "clip"
    return "nodraw"


def boxes_from_brush(br, y0):
    out = []
    for b in dboxes.decompose(br.planes, br.pts, slab=SLAB / S, min_size=0.04 / S, max_slabs=40):
        sx, sy, sz = dboxes.size(b)
        out.append({"at": gpt(dboxes.centre(b), y0), "size": (sx * S, sz * S, sy * S), "yaw": b["phi"] % 90.0, "kind": b.get("kind")})
    return out


def parse_vec(s):
    return [float(t) for t in s.split()]


WIRE_LAMPS = 32    # a map with more than REALTIME_LAMPS lamps sends this many over the wire (`wire_lamps`); the rest stay in the file
REALTIME_LAMPS = 128    # ZzMap.realtime_lamps
AUTO_LIGHTS_BELOW = 12    # a map with at least this many point lamps keeps them; `auto_lights` is for maps without


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def source_lamps(ents, y0):
    """Every `light` and `light_spot` of the source as the document's compact lamp: {at, range,
    energy, colour} and, for a spot, `dir` (unit vector, game axes) and `cone` (half angle, degrees).
    No cap here: the document keeps all of them (the bake uses every one) and the game limits only the
    realtime lamps it lights at once."""
    out = []
    for e in ents:
        if e.get("classname") not in ("light", "light_spot"):
            continue
        col = parse_vec(e.get("_light", "255 255 255 200"))
        br = col[3] if len(col) > 3 else 200
        o = gpt(parse_vec(e["origin"]), y0)
        lamp = {"at": [r3(o[0]), r3(o[1]), r3(o[2])], "range": r3(min(9.0, 3.5 + br / 60.0)), "energy": r3(min(1.6, 0.4 + br / 220.0)),
                "colour": [r3(c / 255.0) for c in col[:3]]}
        if e.get("classname") == "light_spot":
            lamp["dir"] = list(dlights.sun_direction(parse_vec(e.get("angles", "0 0 0")), _num(e.get("pitch"))))
            lamp["cone"] = r3(min(90.0, max(5.0, _num(e.get("_cone")) or 45.0)))
        out.append(lamp)
    # Past REALTIME_LAMPS the wire carries only the first WIRE_LAMPS; in this order those cover the whole map.
    return dlights.spread_order(out) if len(out) > REALTIME_LAMPS else out


# --- nav floors ---------------------------------------------------------------------------

def inside_box(b, x, z):
    dx, dz = x - b["at"][0], z - b["at"][2]
    yaw = b.get("yaw", 0)
    if yaw:
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        lx, lz = dx * c - dz * s, dx * s + dz * c
    else:
        lx, lz = dx, dz
    return abs(lx) <= b["size"][0] / 2 and abs(lz) <= b["size"][2] / 2


def cell_index(boxes):
    grid = {}
    for bi, b in enumerate(boxes):
        if b.get("yaw"):
            r = math.hypot(b["size"][0], b["size"][2]) / 2
            x0, x1, z0, z1 = b["at"][0] - r, b["at"][0] + r, b["at"][2] - r, b["at"][2] + r
        else:
            x0, x1 = b["at"][0] - b["size"][0] / 2, b["at"][0] + b["size"][0] / 2
            z0, z1 = b["at"][2] - b["size"][2] / 2, b["at"][2] + b["size"][2] / 2
        for ix in range(int(math.floor(x0 / CELL)), int(math.floor(x1 / CELL)) + 1):
            for iz in range(int(math.floor(z0 / CELL)), int(math.floor(z1 / CELL)) + 1):
                grid.setdefault((ix, iz), []).append(bi)
    return grid


def _thin_wall_over(b, ix, iz):
    """A wall thinner than a cell that stands over part of it. The flood samples a cell's centre,
    so a one-unit-thick wall (Run For Your Life's dividers are 2 cm) fell between the samples:
    the flood walked through it and the route, items and spawns were put on the far side of a
    wall the body cannot pass. The cell is the wall's when the wall overlaps it at all. A spec opts
    in (`thin_walls`): Nuke's route was authored against the old flood, and its panes of glass and
    clip slivers would seal it until its authoring is redone."""
    if not THIN_WALLS or b.get("yaw") or min(b["size"][0], b["size"][2]) >= CELL:
        return False
    # A thin beam over a doorway (a lintel 7 cm thick, 1.5 m up) is as much in a body's way as a
    # wall; a thin plate on the floor is not. `thin_lintels` opts in, to leave converted maps as were.
    if b["size"][1] <= HEAD and not (THIN_LINTELS and b["at"][1] - b["size"][1] / 2 > 0.8):
        return False
    return (abs(b["at"][0] - (ix + 0.5) * CELL) < (b["size"][0] + CELL) / 2
            and abs(b["at"][2] - (iz + 0.5) * CELL) < (b["size"][2] + CELL) / 2)


def spans_at(boxes, grid, ix, iz):
    """(lo, hi) of every box over a cell's centre."""
    cx, cz = (ix + 0.5) * CELL, (iz + 0.5) * CELL
    spans = []
    for bi in grid.get((ix, iz), ()):
        b = boxes[bi]
        if inside_box(b, cx, cz) or _thin_wall_over(b, ix, iz):
            spans.append((b["at"][1] - b["size"][1] / 2, b["at"][1] + b["size"][1] / 2))
    return spans


def surfaces_at(boxes, grid, ix, iz):
    """Walkable heights in a cell: box tops with headroom."""
    spans = spans_at(boxes, grid, ix, iz)
    out = []
    for lo, hi in spans:
        if any(l2 < hi + HEAD and h2 > hi + 0.05 for l2, h2 in spans if (l2, h2) != (lo, hi)):
            continue
        out.append(round(hi, 2))
    return sorted(set(out))


def build_nav(boxes, starts, blocked=None, wide=False):
    solid = [b for b in boxes if b.get("solid", True) and b.get("nav", True) is not False and not b.get("_sky")]
    grid = cell_index(solid)
    surf = {}
    for ix, iz in list(grid.keys()):
        s = surfaces_at(solid, grid, ix, iz)
        if s:
            if MIN_FLOOR_Y is not None:
                s = [h for h in s if h >= MIN_FLOOR_Y]
            if s:
                surf[(ix, iz)] = s
    tsurf = dterrain.add_surfaces(TERRAIN, surf, lambda a, b: spans_at(solid, grid, a, b), CELL, HEAD) if TERRAIN else set()
    build_nav.tsurf = tsurf
    seen = set()
    parent = {}
    dist = {}
    dq = deque()
    blocked = blocked or {}

    def is_open(ix, iz, h):
        return not any(abs(by - h) <= 0.5 for by in blocked.get((ix, iz), ()))

    def is_wide(ix, iz, h):
        """The game's graph is a metre apart: a way narrower than two cells has no point in it, and
        a prop in the middle of a doorway takes the rest. Only a 2x2 block of open cells counts."""
        for ox in (-1, 0):
            for oz in (-1, 0):
                if all(any(abs(h2 - h) <= (CELL * dterrain.WALK_RISE * 2 if (ix, iz, h) in tsurf else STEP) and is_open(ix + ox + i, iz + oz + j, h2) for h2 in surf.get((ix + ox + i, iz + oz + j), ()))
                       for i in (0, 1) for j in (0, 1)):
                    return True
        return False

    for st in starts:
        ix, iz = int(math.floor(st[0] / CELL)), int(math.floor(st[2] / CELL))
        cands = [h for h in surf.get((ix, iz), []) if h <= st[1] + 0.6]
        if cands:
            h = max(cands)
            seen.add((ix, iz, h))
            dist[(ix, iz, h)] = 0
            dq.append((ix, iz, h))
    links = {}
    while dq:
        ix, iz, h = dq.popleft()
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for h2 in surf.get((ix + dx, iz + dz), ()):
                dh = h2 - h
                if (ix, iz, h) in tsurf and (ix + dx, iz + dz, h2) in tsurf:
                    kind = dterrain.move(dh, CELL, DROP)
                    if kind and (ix + dx, iz + dz, h2) not in seen and (
                            not wide or (is_open(ix + dx, iz + dz, h2) and is_wide(ix + dx, iz + dz, h2))):
                        if kind == "drop":
                            links.setdefault((ix // 3, iz // 3, round(h, 1), round(h2, 1)), [r3((ix + 0.5) * CELL), r3(h), r3((iz + 0.5) * CELL), r3((ix + dx + 0.5) * CELL), r3(h2), r3((iz + dz + 0.5) * CELL)])
                        seen.add((ix + dx, iz + dz, h2))
                        parent[(ix + dx, iz + dz, h2)] = (ix, iz, h)
                        dist[(ix + dx, iz + dz, h2)] = dist[(ix, iz, h)] + 1
                        dq.append((ix + dx, iz + dz, h2))
                    continue
                if (-DROP <= dh < -STEP or STEP < dh <= JUMP) and (ix + dx, iz + dz, h2) not in seen and (
                        not wide or (is_open(ix + dx, iz + dz, h2) and is_wide(ix + dx, iz + dz, h2))):
                    # a drop or a jump up: the body crosses it, the zombies by a link
                    key = (ix // 3, iz // 3, round(h, 1), round(h2, 1))
                    if key not in links:
                        links[key] = [r3((ix + 0.5) * CELL), r3(h), r3((iz + 0.5) * CELL), r3((ix + dx + 0.5) * CELL), r3(h2), r3((iz + dz + 0.5) * CELL)]
                if (abs(dh) <= STEP or -DROP <= dh <= JUMP) and (ix + dx, iz + dz, h2) not in seen and (
                        not wide or (is_open(ix + dx, iz + dz, h2) and is_wide(ix + dx, iz + dz, h2))):
                    seen.add((ix + dx, iz + dz, h2))
                    parent[(ix + dx, iz + dz, h2)] = (ix, iz, h)
                    dist[(ix + dx, iz + dz, h2)] = dist[(ix, iz, h)] + 1
                    dq.append((ix + dx, iz + dz, h2))
    # Surfaces within 0.12 m of each other (a kerb, a worn step) are one floor: the game joins
    # nav points by distance, and two floors 0.1 m apart that merely touch are not joined.
    hs = sorted({t[2] for t in seen if t not in tsurf})
    snap = {}
    i = 0
    while i < len(hs):
        j = i
        while j + 1 < len(hs) and hs[j + 1] - hs[i] <= 0.12:
            j += 1
        for k in range(i, j + 1):
            snap[hs[k]] = hs[j]
        i = j + 1
    byh = {}
    for ix, iz, h in seen:
        if (ix, iz, h) in tsurf:
            continue      # terrain ships as the heightfield's walk mask, not as flat floors
        byh.setdefault(snap[h], set()).add((ix, iz))
    floors = []
    if GREEDY_FLOORS:
        # A rectangle cover that takes the longest run from the first free cell and grows it down
        # while the whole run stays free, rather than merging only rows with identical runs: an
        # irregular plan fell into hundreds of slivers, over the document's 800 floors.
        for h, cells in sorted(byh.items()):
            free = set(cells)
            for iz, ix in sorted((c[1], c[0]) for c in cells):
                if (ix, iz) not in free:
                    continue
                xe = ix
                while (xe + 1, iz) in free:
                    xe += 1
                ze = iz
                while all((x, ze + 1) in free for x in range(ix, xe + 1)):
                    ze += 1
                for z in range(iz, ze + 1):
                    for x in range(ix, xe + 1):
                        free.discard((x, z))
                floors.append([r3(ix * CELL + 0.05), r3(iz * CELL + 0.05), r3((xe + 1) * CELL - 0.05), r3((ze + 1) * CELL - 0.05), r3(h)])
        build_nav.links = list(links.values())
        return floors, surf, seen, parent, dist
    for h, cells in sorted(byh.items()):
        rows = {}
        for ix, iz in cells:
            rows.setdefault(iz, []).append(ix)
        runs = {}
        for iz, xs_ in rows.items():
            xs_.sort()
            a = prev = xs_[0]
            for x in xs_[1:] + [None]:
                if x is not None and x == prev + 1:
                    prev = x
                    continue
                runs.setdefault((a, prev), []).append(iz)
                if x is not None:
                    a = prev = x
        for (a, bb), izs in runs.items():
            izs.sort()
            s = p = izs[0]
            for z in izs[1:] + [None]:
                if z is not None and z == p + 1:
                    p = z
                    continue
                floors.append([r3(a * CELL + 0.05), r3(s * CELL + 0.05), r3((bb + 1) * CELL - 0.05), r3((p + 1) * CELL - 0.05), r3(h)])
                if z is not None:
                    s = p = z
    build_nav.links = list(links.values())
    return floors, surf, seen, parent, dist


class LinkSolids:
    """What a body collides with, as convex pieces (planes n.p <= d), for the line a link draws.

    The game's physics world is the document's solid boxes, its props and the world pack's hulls, and
    its test of a link is a ray at 0.4 m and at 0.9 m above the higher end, shortened 0.15 m at both
    ends, that counts a start inside a solid as a hit (tools/link_check.gd in game-zombie-zone). This
    is that test here, so a link the importer keeps is one the game's world lets through."""

    HEIGHTS = (0.4, 0.9)
    TRIM = 0.15
    CELL = 4.0

    def __init__(self):
        self.cells = collections.defaultdict(list)
        self.count = 0

    def add(self, planes, lo, hi):
        self.count += 1
        item = (planes, lo, hi)
        for gx in range(int(lo[0] // self.CELL), int(hi[0] // self.CELL) + 1):
            for gz in range(int(lo[2] // self.CELL), int(hi[2] // self.CELL) + 1):
                self.cells[(gx, gz)].append(item)

    def add_box(self, b):
        if not b.get("solid", True) or b.get("gate") or b.get("kind") == "sky" or max(b["size"]) <= 0.3:
            return
        import nav_emulate
        nb = nav_emulate._bounds(b)
        yaw = math.radians(b.get("yaw", 0.0) or 0.0)
        c, sn = math.cos(yaw), math.sin(yaw)
        hx, hy, hz = b["size"][0] / 2, b["size"][1] / 2, b["size"][2] / 2
        at = b["at"]
        low = at[1] - hy
        if abs(at[1] + hy) < 0.05 and b["size"][1] <= 0.5:    # a ground slab collides 1.8 m deeper than drawn (ZzMap.GROUND_DEPTH)
            low -= 1.8
            nb[1] = low
        planes = [(0, 1, 0, at[1] + hy), (0, -1, 0, -low)]
        for ux, uz, h, c0 in ((c, -sn, hx, at[0] * c - at[2] * sn), (sn, c, hz, at[0] * sn + at[2] * c)):
            planes.append((ux, 0, uz, c0 + h))
            planes.append((-ux, 0, -uz, -(c0 - h)))
        self.add(planes, nb[:3], nb[3:])

    def add_hull(self, h):
        if not h["points"]:
            return
        lo = [min(p[k] for p in h["points"]) for k in range(3)]
        hi = [max(p[k] for p in h["points"]) for k in range(3)]
        self.add([tuple(p) for p in h["planes"]], lo, hi)

    @staticmethod
    def _crosses(planes, a, b):
        t0, t1 = 0.0, 1.0
        for nx, ny, nz, d in planes:
            dn = nx * (b[0] - a[0]) + ny * (b[1] - a[1]) + nz * (b[2] - a[2])
            num = d - (nx * a[0] + ny * a[1] + nz * a[2])
            if abs(dn) < 1e-9:
                if num < 0:
                    return False
            elif dn < 0:
                t0 = max(t0, num / dn)
            else:
                t1 = min(t1, num / dn)
            if t0 > t1:
                return False
        return True

    def blocked(self, p, q):
        top = max(p[1], q[1])
        if math.dist(p, q) < 0.5:
            return False
        for rise in self.HEIGHTS:
            a = [p[0], top + rise, p[2]]
            b = [q[0], top + rise, q[2]]
            d = math.dist(a, b)
            if d < 1e-6:        # a link straight down or up has no line at this height
                continue
            ux, uy, uz = [(b[k] - a[k]) / d for k in range(3)]
            a = [a[0] + ux * self.TRIM, a[1] + uy * self.TRIM, a[2] + uz * self.TRIM]
            b = [b[0] - ux * self.TRIM, b[1] - uy * self.TRIM, b[2] - uz * self.TRIM]
            for gx in range(int(min(a[0], b[0]) // self.CELL), int(max(a[0], b[0]) // self.CELL) + 1):
                for gz in range(int(min(a[2], b[2]) // self.CELL), int(max(a[2], b[2]) // self.CELL) + 1):
                    for planes, lo, hi in self.cells.get((gx, gz), ()):
                        if lo[1] > a[1] or hi[1] < a[1]:
                            continue
                        if hi[0] < min(a[0], b[0]) or lo[0] > max(a[0], b[0]) or hi[2] < min(a[2], b[2]) or lo[2] > max(a[2], b[2]):
                            continue
                        if self._crosses(planes, a, b):
                            return True
        return False


def link_solids(doc, extra_boxes=()):
    """The [LinkSolids] of a finished document: its boxes (and `extra_boxes`), solid props and the hulls its `world_collision` selects."""
    solids = LinkSolids()
    for b in list(doc["boxes"]) + list(extra_boxes):
        if not b.get("barricade"):
            solids.add_box(b)
    for rec in doc.get("solid_props", []):
        solids.add_box({"at": rec[:3], "size": rec[3:6], "yaw": rec[6]})
    sel = doc.get("world_collision")
    prefix = os.path.join(HERE, "..", "world", doc.get("world", ""), doc["id"])
    if sel and os.path.isfile(prefix + ".json"):
        from dotbsp import audit as daudit, mesh as dmesh
        _man, world = dmesh.read(prefix)
        for h in daudit.collision_hulls(world.hulls, sel):
            solids.add_hull(h)
    return solids


LINK_CLIP_MIN = 0.3    # the game's ZzNpcs.LINK_CLIP_MIN: less horizontal run inside a slab is a nick of its edge
LINK_STEEP = 1.2    # the game's ZzNpcs.LINK_STEEP: a link that changes level by more is tested against the floor slabs


def floor_slabs(boxes, floors):
    """The bounds of the solid boxes the game takes for floors (it does not make them walls for a link, but drops a level-changing link that pierces one)."""
    import nav_emulate
    out = []
    for b in boxes:
        if not b.get("solid", True) or b.get("gate") or b.get("kind") == "sky" or ("nav" in b and not b["nav"]) or b.get("barricade"):
            continue
        nb = nav_emulate._bounds(b)
        if "nav" not in b and nav_emulate._is_floor(nb, floors):
            out.append(nb)
    return out


def through_floor(slabs, l, trim=0.15):
    """Whether link `l` changes level and its line enters a floor slab through its underside, as ZzNpcs._link_through_floor drops it (a drop that only clips a ledge's edge stays)."""
    if abs(l[1] - l[4]) <= LINK_STEEP:
        return False
    d = math.dist(l[:3], l[3:])
    if d < 2 * trim + 1e-6:
        return False
    u = [(l[3 + k] - l[k]) / d for k in range(3)]
    a = [l[k] + u[k] * trim for k in range(3)]
    b = [l[3 + k] - u[k] * trim for k in range(3)]

    def entry(p, q, s):
        t0, t1 = 0.0, 1.0
        for k in range(3):
            dk = q[k] - p[k]
            lo, hi = s[k], s[k + 3]
            if abs(dk) < 1e-9:
                if p[k] < lo or p[k] > hi:
                    return None
                continue
            ta, tb = (lo - p[k]) / dk, (hi - p[k]) / dk
            if ta > tb:
                ta, tb = tb, ta
            t0, t1 = max(t0, ta), min(t1, tb)
        return [p[k] + (q[k] - p[k]) * t0 for k in range(3)] if t0 <= t1 else None

    short = math.hypot(l[3] - l[0], l[5] - l[2]) < LINK_CLIP_MIN
    for s in slabs:
        p, q = entry(a, b, s), entry(b, a, s)
        if p is not None and q is not None and min(p[1], q[1]) <= s[1] + 0.02 and (short or math.hypot(p[0] - q[0], p[2] - q[2]) >= LINK_CLIP_MIN):
            return True
    return False


POCKET = 40    # points: the importer's own line between a pocket and a part of the map (filter_wall_links)


def clear_join(G, solids, i, j, dy_max, reach=8.0):
    """A link between the components of points i and j that the physics world and a 0.25 m body let through, or None.

    The shortest one wins; a join the flood proposed through a prop is replaced by the way round it."""
    ri, rj = G.find(i), G.find(j)
    mx, mz = (G.pts[i][0] + G.pts[j][0]) / 2, (G.pts[i][2] + G.pts[j][2]) / 2
    A, B = [], []
    for k, p in enumerate(G.pts):
        if abs(p[0] - mx) <= reach and abs(p[2] - mz) <= reach:
            r = G.find(k)
            (A if r == ri else B if r == rj else []).append(k)
    cand = sorted((math.dist(G.pts[a], G.pts[b]), a, b) for a in A for b in B
                  if abs(G.pts[a][1] - G.pts[b][1]) <= max(0.5, dy_max))
    for d, a, b in cand[:4000]:
        if d > 6.0:
            break
        p, q = G.pts[a], G.pts[b]
        if d < 0.5 or solids.blocked(p, q):
            continue
        nx, nz = -(q[2] - p[2]) / max(math.hypot(q[0] - p[0], q[2] - p[2]), 1e-6), (q[0] - p[0]) / max(math.hypot(q[0] - p[0], q[2] - p[2]), 1e-6)
        if any(solids.blocked((p[0] + nx * o, p[1], p[2] + nz * o), (q[0] + nx * o, q[1], q[2] + nz * o)) for o in (-0.25, 0.25)):
            continue
        return [round(v, 3) for v in (*p, *q)]
    return None


def cut_blocked(doc, extra, fixed):
    """Cut the links the game's physics world blocks from `doc` (and the nav [param extra] dict, if any), where the ground stays joined without them.

    Returns [cut in doc, cut in extra, kept because they are the only join]. The spec's `extra_links`
    ([param fixed]) stay: they cross doors on purpose. Like filter_wall_links, a blocked link whose ends no
    other link joins is kept, so the cut never splits a map."""
    import nav_emulate
    xb = extra["boxes"] if extra else []
    xf = extra["floors"] if extra else []
    solids = link_solids(doc, xb)
    lists = [doc["nav"]["links"]] + ([extra["links"]] if extra else [])
    sizes = json.load(open(os.path.join(HERE, "prop_sizes.json")))["props"]
    floors = doc["nav"]["floors"] + xf
    nav = doc["nav"]
    G = nav_emulate.Graph(list(doc["boxes"]) + list(xb), doc.get("props", []), sizes, floors, spacing=float(nav.get("spacing", 1.0)), clearance=float(nav.get("clearance", 0.35)), solid_props=doc.get("solid_props", []))
    fixed_ = {tuple(l) for l in fixed}
    bars = [b["at"] for b in doc["boxes"] if b.get("barricade")]

    def at_barricade(l):
        # The game's world does not block these (its probe finds none), and cutting one seals the horde off the boards it walks to.
        return any(abs(e[0] - b[0]) < 2.5 and abs(e[2] - b[2]) < 2.5 for b in bars for e in (l[:3], l[3:]))

    def ends(l):
        r = float(nav.get("spacing", 1.0)) * 2.0
        return G.nearest(l[0], l[1], l[2], r), G.nearest(l[3], l[4], l[5], r)

    slabs = floor_slabs(list(doc["boxes"]) + list(xb), floors)
    bad = set()
    thru = set()
    for n, ls in enumerate(lists):
        for l in ls:
            if tuple(l) not in fixed_ and through_floor(slabs, l):
                bad.add(id(l))
                thru.add(id(l))     # the game drops it anyway; kept, it only claims a join that is not there
            elif tuple(l) not in fixed_ and not at_barricade(l) and solids.blocked(l[:3], l[3:]):
                bad.add(id(l))
            else:
                i, j = ends(l)
                if i >= 0 and j >= 0:
                    G.union(i, j)
    cut, stuck = [0, 0], 0
    out = []
    for n, ls in enumerate(lists):
        kept = []
        for l in ls:
            if id(l) in bad:
                i, j = ends(l)
                if i >= 0 and j >= 0 and G.find(i) == G.find(j):
                    cut[n] += 1
                    continue
                if i >= 0 and j >= 0:
                    r = clear_join(G, solids, i, j, abs(l[4] - l[1]))
                    if r:
                        cut[n] += 1
                        kept.append(r)
                        G.union(i, j)
                        continue
                    ri, rj = G.find(i), G.find(j)
                    sizes = collections.Counter(G.find(k) for k in range(len(G.pts)))
                    if min(sizes[ri], sizes[rj]) < POCKET:
                        cut[n] += 1     # a pocket the solids seal in: no body gets in, and no link that walks through them may
                        continue
                    if id(l) in thru:
                        cut[n] += 1     # no replacement and no pocket: still not a join the game keeps
                        continue
                    G.union(i, j)
                elif "terrain" not in doc or id(l) in thru:
                    cut[n] += 1     # an end with no graph point is a link the game's builder drops unlinked, but its physics check still counts
                    continue
                stuck += 1
            kept.append(l)
        out.append(kept)
    doc["nav"]["links"] = out[0]
    if extra:
        extra["links"] = out[1]
    return cut[0], cut[1], stuck


def reseat_spawns(doc):
    """Moves a survivor spawn, post or cache the finished document's graph seals off from the main ground (the physical link cut can seal a room the first pass joined) onto it."""
    import nav_emulate
    nav = doc["nav"]
    sizes = json.load(open(os.path.join(HERE, "prop_sizes.json")))["props"]
    G = nav_emulate.Graph(doc["boxes"], doc.get("props", []), sizes, nav["floors"], spacing=float(nav.get("spacing", 1.0)), clearance=float(nav.get("clearance", 0.35)), terrain_pts=TERRAIN_PTS, solid_props=doc.get("solid_props", []))
    for l in nav["links"]:
        i, j = G.nearest(l[0], l[1], l[2], 2.0), G.nearest(l[3], l[4], l[5], 2.0)
        if i >= 0 and j >= 0:
            G.union(i, j)
    if not G.pts:
        return doc
    main = collections.Counter(G.find(i) for i in range(len(G.pts))).most_common(1)[0][0]
    pts = [q for i, q in enumerate(G.pts) if G.find(i) == main]
    moved = 0
    spawns = doc["spawns"]["survivors"]
    for sp in spawns:
        at = sp["at"]
        k = G.nearest(at[0], at[1], at[2], 1.5)
        if k < 0 or G.find(k) == main:
            continue
        for q in sorted(pts, key=lambda q: (q[0] - at[0]) ** 2 + (q[2] - at[2]) ** 2 + (q[1] - at[1]) ** 2):
            if (q[0] - at[0]) ** 2 + (q[2] - at[2]) ** 2 > 144:
                break
            if abs(q[1] - at[1]) <= 0.6 and all((q[0] - o["at"][0]) ** 2 + (q[2] - o["at"][2]) ** 2 >= 1.96 for o in spawns if o is not sp):
                sp["at"] = [r3(q[0]), r3(q[1] + 0.1), r3(q[2])]
                moved += 1
                break
    if moved:
        print("  survivor spawns: %d in a room the finished graph seals off moved out of it" % moved)
    # Posts and caches are placed from the first graph; one the finished graph seals off is snapped to the nearest main-ground point (same height band), 6 m clear of its peers.
    for what, lst in (("posts", doc.get("posts", [])), ("caches", doc.get("caches", []))):
        snapped = 0
        for n, at in enumerate(lst):
            k = G.nearest(at[0], at[1], at[2], 1.5)
            if k >= 0 and G.find(k) == main:
                continue
            for q in sorted(pts, key=lambda q: (q[0] - at[0]) ** 2 + (q[2] - at[2]) ** 2 + (q[1] - at[1]) ** 2):
                if abs(q[1] - at[1]) <= 1.0 and all((q[0] - o[0]) ** 2 + (q[2] - o[2]) ** 2 >= 36 for m, o in enumerate(lst) if m != n):
                    print("  %s: %s %s is on an island, snapped %.1f m to the main ground" % (what, n, at, math.sqrt((q[0] - at[0]) ** 2 + (q[1] - at[1]) ** 2 + (q[2] - at[2]) ** 2)))
                    lst[n] = [r3(q[0]), r3(q[1]), r3(q[2])]
                    snapped += 1
                    break
            else:
                print("  %s: %s %s is on an island and no main-ground point is within reach" % (what, n, at))
    return doc


def cut_blocked_links(doc, fixed):
    """`doc` with the nav links the game's physics world blocks cut out (see [LinkSolids]); run on the finished document, so the boxes are the ones the game builds."""
    n, _m, stuck = cut_blocked(doc, None, fixed)
    if n or stuck:
        print("  physical links: %d cut (the game's world blocks them), %d kept as the only join" % (n, stuck))
    return doc


def cut_links(argv):
    """`--cut-links[-check] <spec> <doc>...`: cut the blocked links out of committed documents (and their `hulls/<id>.nav.json`) without a re-conversion, which would drag in box and light drift. The -check form writes nothing and returns 1 when a link would be cut."""
    spec = json.load(open(argv[2])) if os.path.isfile(argv[2]) else {}    # a hand-made map has no spec
    fixed = spec.get("extra_links", [])
    check = argv[1].endswith("-check")
    rc = 0
    with open(os.path.join(HERE, "link_allow.json")) as f:
        allow = json.load(f)["links"]
    for path in argv[3:]:
        with open(path) as f:
            doc = json.load(f)
        extra_path = os.path.join(os.path.dirname(path), "hulls", doc["id"] + ".nav.json")
        extra = None
        if os.path.isfile(extra_path):
            with open(extra_path) as f:
                extra = json.load(f)
        n, m, stuck = cut_blocked(doc, extra, fixed)
        print("%s: %d links blocked (%d in the nav extra), %d more kept as the only join" % (doc["id"], n + m, m, stuck))
        if stuck > allow.get(doc["id"], 0):
            print("  %s: %d kept links, only %d allowed (tools/link_allow.json)" % (doc["id"], stuck, allow.get(doc["id"], 0)))
            rc = 1
        if n + m:
            rc = 1
            if not check:
                with open(path, "w") as f:
                    json.dump(doc, f, indent=1)
                    f.write("\n")
                if m:
                    with open(extra_path, "w") as f:
                        json.dump(extra, f, separators=(",", ":"))
                        f.write("\n")
    return rc if check else 0


def add_links(argv):
    """`--add-links <spec> <doc>...`: append the spec's `extra_links` and `add_boxes` the committed documents lack, without a re-conversion (which drifts boxes and lights)."""
    spec = json.load(open(argv[2]))
    for path in argv[3:]:
        with open(path) as f:
            doc = json.load(f)
        have = {tuple(l) for l in doc["nav"]["links"]}
        new = [list(l) for l in spec.get("extra_links", []) if tuple(l) not in have]
        have_boxes = {(tuple(b["at"]), tuple(b["size"])) for b in doc["boxes"]}
        patches = [dict(b) for b in spec.get("add_boxes", []) if (tuple(b["at"]), tuple(b["size"])) not in have_boxes]
        print("%s: %d extra links, %d added boxes appended" % (doc["id"], len(new), len(patches)))
        if new or patches:
            doc["nav"]["links"].extend(new)
            doc["boxes"].extend(patches)
            with open(path, "w") as f:
                json.dump(doc, f, indent=1)
                f.write("\n")
    return 0


def link_obstacles(boxes, floors):
    """The solid boxes a link's line must not run through (floors a body stands on are not)."""
    import nav_emulate
    obs = []
    for b in boxes:
        if not b.get("solid", True) or b.get("gate") or b.get("nav", True) is False:
            continue
        nb = nav_emulate._bounds(b)
        if nav_emulate._is_floor(nb, floors):
            continue
        obs.append(nb)
    return obs


def link_blocked(obs, a, c, grow=0.0, min_h=0.55):
    """True when the line a-c passes through a solid that reaches 0.55 m above its lower end
    (a wall, a window sill) and neither end stands on that solid."""
    lo = min(a[1], c[1])
    n = max(2, int(math.dist(a, c) / 0.1))
    for nb in obs:
        if nb[4] <= lo + min_h or nb[1] >= lo + 1.5:
            continue
        if any(nb[0] - 0.05 <= e[0] <= nb[3] + 0.05 and nb[2] - 0.05 <= e[2] <= nb[5] + 0.05 for e in (a, c)):
            continue
        if max(a[0], c[0]) < nb[0] - grow or min(a[0], c[0]) > nb[3] + grow or max(a[2], c[2]) < nb[2] - grow or min(a[2], c[2]) > nb[5] + grow:
            continue
        for k in range(n + 1):
            t = k / n
            x, y, z = a[0] + (c[0] - a[0]) * t, a[1] + (c[1] - a[1]) * t, a[2] + (c[2] - a[2]) * t
            if nb[0] - grow <= x <= nb[3] + grow and nb[2] - grow <= z <= nb[5] + grow and nb[4] > y + 0.15:
                return True
    return False


def filter_wall_links(links, boxes, props, sizes, floors, strict=False, fixed=()):
    """Drop the links that run through a wall or over a sill, where the ground stays joined without them.

    The cell flood samples a cell's centre, so a window sill or a wall thinner than a cell is
    invisible to it and it proposes a 'drop or jump' link straight through (atix's window, nuke's
    sill doorway: the stand-ins walked into the sill and stood there, 50% of their goal time). A
    link is cut when its line passes through a solid box that reaches 0.55 m above the lower end
    and neither end stands on that box. Cut only when the graph's own points at the two ends are
    already joined by the other links and edges: a link that is the document's only connection
    stays (dropping all of them disconnected the ground on four maps). `fixed` are the spec's own links, which count as joins but are never cut."""
    import nav_emulate
    obs = link_obstacles(boxes, floors)
    def blocked(l):
        # strict: a body 0.25 m in radius, and a counter 0.4 m high (a window's) is a wall to a mover
        # that cannot jump. Not the default: it cut links the stand-ins on atix and nuke needed
        return link_blocked(obs, l[:3], l[3:], grow=0.25, min_h=0.4) if strict else link_blocked(obs, l[:3], l[3:])

    bad = [l for l in links if blocked(l)]
    if not bad:
        return links
    G = nav_emulate.Graph(boxes, props, sizes, floors, terrain_pts=TERRAIN_PTS)

    def ends(l):
        return G.nearest(l[0], l[1], l[2], 2.0), G.nearest(l[3], l[4], l[5], 2.0)

    badset = {id(l) for l in bad}
    for l in list(fixed) + links:
        if id(l) not in badset:
            i, j = ends(l)
            if i >= 0 and j >= 0:
                G.union(i, j)
    kept, cut = [], 0
    for l in links:
        if id(l) not in badset:
            kept.append(l)
            continue
        i, j = ends(l)
        if i >= 0 and j >= 0 and G.find(i) == G.find(j):
            cut += 1
            continue
        if i >= 0 and j >= 0:
            G.union(i, j)
        kept.append(l)
    print("  wall links: %d of %d cut (%d run through a wall but are the only join)" % (cut, len(links), len(bad) - cut))
    return kept


def floor_at(surf, seen, x, z, y):
    ix, iz = int(math.floor(x / CELL)), int(math.floor(z / CELL))
    hs = [h for h in surf.get((ix, iz), []) if (ix, iz, h) in seen and h <= y + 0.8]
    return max(hs) if hs else None


class Source:
    """The intermediate document, indexed the way this importer asks for it."""

    def __init__(self, doc):
        probs = intermediate.check(doc)
        if probs:
            sys.exit("import_bsp: not a usable intermediate document: " + "; ".join(probs[:5]))
        self.doc = doc
        self.entities = [e["keys"] for e in doc["entities"]]
        self.models = {m["index"]: m for m in doc["models"]}
        self.brushes = {b["id"]: b for b in doc["brushes"]}

    def model_bounds(self, model):
        """The model's own bounds, origin-relative as the format stores them."""
        m = self.models[model]
        o = m["origin"]
        return ([m["mins"][k] - o[k] for k in range(3)], [m["maxs"][k] - o[k] for k in range(3)])

    def terrain_tris(self):
        """The displacement triangles (the intermediate must be built with `bsp.py convert --displacements`)."""
        return [t for d in self.doc.get("displacements", []) for t in d["tris"]]

    def model_brushes(self, model):
        m = self.models.get(model)
        return [self.brushes[i] for i in m["brushes"]] if m else []


def load_source(path, terrain=False):
    if path.lower().endswith(".json"):
        with open(path) as f:
            return Source(json.load(f))
    return Source(intermediate.build(reader.Bsp(path).load(), name=os.path.splitext(os.path.basename(path))[0], displacements=terrain))


def model_boxes(bs, model, y0):
    out = []
    for rec in bs.model_brushes(model):
        if not rec["hull"]:
            continue
        br = read_brush(bs.doc, rec)
        if not br.pts or not (br.contents & (1 | 0x2 | 0x8 | 0x10000)):
            continue
        kind, mat = classify(br)
        made = boxes_from_brush(br, y0)
        # A brush cut into slabs along its slope is a ramp or a stair; how much it rises is how
        # a spec decides whether the horde's graph (a step of half a spacing at most) can use it.
        rise, walkable = 0.0, False
        if made and all(bx["kind"] == "slab" for bx in made):
            rise = max(bx["at"][1] + bx["size"][1] / 2 for bx in made) - min(bx["at"][1] - bx["size"][1] / 2 for bx in made)
            # Only a side a body could walk up (no steeper than 60 degrees) makes a ramp. A tunnel's
            # curved wall, an arch and a leaning wall are slab-cut too and rise just as far.
            walkable = any(0.5 <= pl[2] < 0.985 for pl in br.planes)
        for bx in made:
            b = {"at": [r3(v) for v in bx["at"]], "size": [r3(max(v, 0.02)) for v in bx["size"]], "mat": mat}
            if bx["yaw"]:
                b["yaw"] = r3(bx["yaw"])
            if rise:
                b["_rise"] = r3(rise)
                b["_walkable"] = walkable
                b["_brush"] = (model, rec.get("id", id(rec)))
            if kind in ("invisible", "sky"):
                b["visible"] = False
                b["kind"] = "sky" if kind == "sky" else hidden_kind(br)
            if kind == "sky":
                b["_sky"] = True
            out.append(b)
    return out


def water_volumes(bs, y0, floors, spec, boxes=(), kill_y=-1e9):
    """The map's water as game volumes `{at, size}` (centre and size, the top face is the surface).

    A water brush is CONTENTS_WATER (0x20) in any model: the world's, or a func_brush's (Jurassic
    Park's lakes). It was dropped before this, because the solid test above never passes it; the
    swim and the wading are the game's, so the importer only has to say where.

    Three filters, all about what a survivor or a zombie can meet. Shallower than `water_min_depth`
    (0.4 m, spec key) is a puddle: ankle deep, no wading in it. A pool no floor of the zombies'
    ground lies in (the nuke map's decorative planes, a sump under the level) is a picture, not
    a place; the spec's `water: "all"` keeps it, `water: false` drops every one. And two brushes
    of one pool that meet edge to edge at one level are one volume, because the swim mode asks
    which box the waist is in, and a seam between two is a place the player stops swimming.
    """
    mode = spec.get("water", True)
    if mode is False:
        return []
    min_depth = float(spec.get("water_min_depth", 0.4))
    found = []
    for rec in bs.doc["brushes"]:
        if not (rec["contents"] & reader.CONTENTS_WATER) or not rec["hull"]:
            continue
        pts = [gpt(p, y0) for p in rec["hull"]]
        xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
        box = [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]
        if box[4] - box[1] < min_depth or (box[3] - box[0]) * (box[5] - box[2]) < 1.0:
            continue
        found.append(box)

    def meets(a, b):
        if abs(a[4] - b[4]) > 0.05:
            return False
        x_same = abs(a[0] - b[0]) < 0.05 and abs(a[3] - b[3]) < 0.05
        z_same = abs(a[2] - b[2]) < 0.05 and abs(a[5] - b[5]) < 0.05
        x_touch = a[0] <= b[3] + 0.05 and b[0] <= a[3] + 0.05
        z_touch = a[2] <= b[5] + 0.05 and b[2] <= a[5] + 0.05
        return (x_same and z_touch) or (z_same and x_touch)

    merged = True
    while merged:
        merged = False
        for i in range(len(found)):
            for k in range(i + 1, len(found)):
                if meets(found[i], found[k]):
                    a, b = found[i], found[k]
                    found[i] = [min(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3]), a[4], max(a[5], b[5])]
                    del found[k]
                    merged = True
                    break
            if merged:
                break

    def over(b, v, pad):
        lo, hi = [b["at"][i] - b["size"][i] / 2 for i in range(3)], [b["at"][i] + b["size"][i] / 2 for i in range(3)]
        return lo[0] < v[3] + pad and hi[0] > v[0] - pad and lo[2] < v[5] + pad and hi[2] > v[2] - pad, hi[1]

    def reachable(v):
        # A nav floor [x0, z0, x1, z1, h] from the bed up to a storey above the surface, or a box
        # top at the waterline (a bed or a shore): the zombies' flood misses pools reached by a lift.
        if any(f[0] < v[3] + 2.0 and f[2] > v[0] - 2.0 and f[1] < v[5] + 2.0 and f[3] > v[2] - 2.0
               and v[1] - 0.1 <= f[4] <= v[4] + 12.0 for f in floors):
            return True
        return any(o and v[1] - 0.1 <= top <= v[4] + 0.5 for o, top in (over(b, v, 1.0) for b in boxes))

    def depth(v):
        # A brush sunk under the floor is only as deep as the water over its bed: the deepest of a
        # 5 x 5 sample, so an island or a step in a lake does not make it a puddle.
        deepest = 0.0
        for i in range(5):
            for k in range(5):
                x, z = v[0] + (v[3] - v[0]) * (i + 0.5) / 5, v[2] + (v[5] - v[2]) * (k + 0.5) / 5
                beds = [top for o, top in (over(b, [x, 0, z, x, 0, z], 0.0) for b in boxes) if o and v[1] - 0.1 <= top <= v[4]]
                deepest = max(deepest, v[4] - max([v[1]] + beds))
        return deepest

    out = []
    for v in sorted(found, key=lambda v: (v[4], v[0], v[2])):
        if mode != "all" and not reachable(v):
            continue
        if depth(v) < min_depth or v[4] < kill_y:
            continue
        out.append({"at": [r3((v[0] + v[3]) / 2), r3((v[1] + v[4]) / 2), r3((v[2] + v[5]) / 2)],
                    "size": [r3(v[3] - v[0]), r3(v[4] - v[1]), r3(v[5] - v[2])]})
    return out


# --- the document ---------------------------------------------------------------------------

def widen_doorways(boxes, width, min_gap=0.5, min_h=1.5):
    """Trims the facing ends of two upright wall boxes across a gap of min_gap..width so the gap is
    `width`; returns how many gaps were opened. A wall piece is a standing box (min_h or taller, not
    turned, not a gate) at most 0.6 m thick; both pieces must reach the floor of the gap together."""
    def wall(b):
        return b["size"][1] >= min_h and not b.get("yaw") and not b.get("gate") and b.get("solid", True)

    walls = [b for b in boxes if wall(b)]
    opened = 0
    for axis, thin in ((2, 0), (0, 2)):
        pieces = [b for b in walls if b["size"][thin] <= 0.6]
        for a in pieces:
            for c in pieces:
                if a is c or a["at"][axis] >= c["at"][axis]:
                    continue
                if abs(a["at"][thin] - c["at"][thin]) > 0.15 or abs(a["size"][thin] - c["size"][thin]) > 0.1:
                    continue
                if abs((a["at"][1] - a["size"][1] / 2) - (c["at"][1] - c["size"][1] / 2)) > 0.5:
                    continue
                gap = (c["at"][axis] - c["size"][axis] / 2) - (a["at"][axis] + a["size"][axis] / 2)
                if not min_gap <= gap < width - 0.01:
                    continue
                # A frame, bar or barrier across the gap at body height is not a doorway; a ramp's steps are.
                lo, hi = max(a["at"][1] - a["size"][1] / 2, c["at"][1] - c["size"][1] / 2), min(a["at"][1] + a["size"][1] / 2, c["at"][1] + c["size"][1] / 2)
                g0, g1 = a["at"][axis] + a["size"][axis] / 2, c["at"][axis] - c["size"][axis] / 2

                def across(o):
                    ob, ot = o["at"][1] - o["size"][1] / 2, o["at"][1] + o["size"][1] / 2
                    return (abs(o["at"][thin] - a["at"][thin]) < 0.4 and o["at"][axis] + o["size"][axis] / 2 > g0 + 0.05
                            and o["at"][axis] - o["size"][axis] / 2 < g1 - 0.05 and ob < lo + 1.8 and ot > lo + 0.3
                            and (ob >= lo + 0.3 or ot > lo + 1.8) and ob < hi - 0.3)

                if any(o is not a and o is not c and across(o) for o in boxes):
                    continue
                cut = (width - gap) / 2
                if a["size"][axis] - cut < 0.1 or c["size"][axis] - cut < 0.1:
                    continue
                a["size"][axis] = r3(a["size"][axis] - cut)
                a["at"][axis] = r3(a["at"][axis] - cut / 2)
                c["size"][axis] = r3(c["size"][axis] - cut)
                c["at"][axis] = r3(c["at"][axis] + cut / 2)
                opened += 1
    return opened


BREAKABLE = ("func_breakable", "func_breakable_surf", "func_physbox", "func_physbox_multiplayer")
TERRAIN_BUDGET = 1_500_000    # bytes of heightfield a document may carry: the wire sends a big map in pieces
TERRAIN_CELLS = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)    # finest first: a cliff face is only as steep as one cell lets it be
WIRE_BUDGET = 30_000_000   # ZzMapDoc.WIRE_LIMIT (32 MiB, a hostile-input bound; the wire sends a big map in pieces) less the header
LIMITS = {"boxes": 400000, "floors": 50000, "links": 50000}   # ZzMapDoc.MAX_BOXES, MAX_NAV_FLOORS, MAX_NAV_LINKS


def wire_size(path):
    """(boxes, compressed bytes, room) of a written document; room < 1 is over a limit by that ratio."""
    with open(path) as f:
        doc = json.load(f)
    size = len(zlib.compress(json.dumps(doc, separators=(",", ":")).encode(), 9))
    nav = doc.get("nav") or {}
    counts = {"boxes": len(doc.get("boxes", [])), "floors": len(nav.get("floors", [])), "links": len(nav.get("links", []))}
    room = min([WIRE_BUDGET / max(1, size)] + [LIMITS[k] / max(1, v) for k, v in counts.items()])
    return counts["boxes"], size, room


def fits(path):
    """Whether a written document fits on the wire and under every count the game reads."""
    return wire_size(path)[2] >= 1.0


def prune_extra(extra, floors):
    """Drops what the horde walks over or round: a box no taller than a step lying on a floor (trim, a sill, a tile)
    and a box of under 0.06 m3 (a pole, a rail, a shelf slab). As obstacles they cut every point within the clearance
    of them, and the doorway behind; the hull still stops the bodies."""

    def small(b):
        return b["size"][0] * b["size"][1] * b["size"][2] < 0.06

    def low_on_floor(b):
        if b["size"][1] > 0.35:
            return False
        top, rx, rz = b["at"][1] + b["size"][1] / 2, b["size"][0] / 2 + 0.5, b["size"][2] / 2 + 0.5
        return any(f[0] - rx < b["at"][0] < f[2] + rx and f[1] - rz < b["at"][2] < f[3] + rz and f[4] - 0.5 <= top <= f[4] + 0.15 for f in floors)

    return [b for b in extra if not small(b) and not low_on_floor(b)]


def write_nav_extra(path, full):
    """`hulls/<id>.nav.json`, server-only beside the hulls: the whole map's boxes the budget dropped, and
    its floors and links, which the horde's graph is built from (the wire document keeps the budgeted ones)."""
    with open(path) as f:
        doc = json.load(f)
    out = os.path.join(os.path.dirname(path), "hulls", doc["id"] + ".nav.json")
    if os.path.exists(out):
        os.remove(out)
    if not doc.get("world_collision"):
        return
    if not full:    # nothing was dropped by the budget: the hulls alone, and an empty extra so the server does not warn
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            f.write('{"boxes":[],"floors":[],"links":[]}\n')
        return
    have = collections.Counter(json.dumps(b, sort_keys=True) for b in doc["boxes"])
    extra = []
    for b in full["boxes"]:
        k = json.dumps(b, sort_keys=True)
        if have[k] > 0:
            have[k] -= 1
        else:
            extra.append(b)
    nav = full["nav"]
    extra = prune_extra(extra, nav["floors"] + doc["nav"]["floors"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump({"boxes": extra, "floors": nav["floors"], "links": nav["links"]}, f, separators=(",", ":"))
        f.write("\n")
    print("  nav extra: %d boxes, %d floors, %d links in hulls/%s.nav.json (the wire carries %d, %d, %d)" % (
        len(extra), len(nav["floors"]), len(nav["links"]), doc["id"], len(doc["boxes"]), len(doc["nav"]["floors"]), len(doc["nav"]["links"])))


def relight(argv):
    """`--lights-only[-check] <spec> <bsp or intermediate> <doc>`: replace only the `lights` of a
    committed document with the source's lamps, so a lamp change does not drag in a whole
    re-conversion (box drift, a new nav). A map keeps its lamps when the source has no more of
    them (the auto grid, or an older conversion, lit it at least as well), and a spec that forces
    the auto grid keeps it. The -check form writes nothing and returns 1 when a document would change."""
    spec = json.load(open(argv[2]))
    bs = load_source(argv[3], False)
    lamps = source_lamps(bs.entities, float(spec.get("y0", 0.0)))
    al = spec.get("auto_lights")
    with open(argv[4]) as f:
        doc = json.load(f)
    old = len(doc.get("lights", []))
    if (al and al.get("force")) or len(lamps) <= old or (al and len(lamps) < AUTO_LIGHTS_BELOW):
        print("%s: kept %d lamps (source has %d)" % (spec["id"], old, len(lamps)))
        return 0
    print("%s: lights %d -> %d" % (spec["id"], old, len(lamps)))
    if argv[1].endswith("-check"):
        return 1
    doc["lights"] = lamps
    doc.pop("wire_lamps", None)
    if len(lamps) > REALTIME_LAMPS:
        doc["wire_lamps"] = WIRE_LAMPS
    with open(argv[4], "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    return 0


def rewater(argv):
    """`--water-only[-check] <spec> <bsp or intermediate> <doc>`: replace only the `water` of a
    committed document, from its own boxes, floors and kill_y. The -check form writes nothing and
    returns 1 when a document would change."""
    spec = json.load(open(argv[2]))
    bs = load_source(argv[3], False)
    with open(argv[4]) as f:
        doc = json.load(f)
    nav = doc.get("nav", {}).get("floors", [])
    water = water_volumes(bs, float(spec.get("y0", 0.0)), nav, spec, doc.get("boxes", []), doc.get("kill_y", -1e9))
    if water == doc.get("water", []):
        print("%s: water unchanged (%d)" % (spec["id"], len(water)))
        return 0
    print("%s: water %d -> %d" % (spec["id"], len(doc.get("water", [])), len(water)))
    if argv[1].endswith("-check"):
        return 1
    doc.pop("water", None)
    if water:
        doc = {k2: v2 for k, v in doc.items() for k2, v2 in (((k, v), ("water", water)) if k == "barricades" else ((k, v),))}
        if "water" not in doc:
            doc["water"] = water
    with open(argv[4], "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    return 0


def under_feet_docs(argv):
    """`--under-feet[-check] <doc>...`: write `nav.under_feet` into committed documents a conversion would give it (nav_emulate.under_feet_for), by one inserted line, without a re-conversion. The -check form writes nothing and returns 1 when a document lacks it."""
    import nav_emulate
    sizes = json.load(open(os.path.join(HERE, "prop_sizes.json")))["props"]
    rc = 0
    for path in argv[2:]:
        text = open(path).read()
        doc = json.loads(text)
        extra_path = os.path.join(os.path.dirname(path), "hulls", doc["id"] + ".nav.json")
        extra = json.load(open(extra_path)) if os.path.isfile(extra_path) else {}
        nav = doc["nav"]
        feet = nav_emulate.under_feet_for(list(doc["boxes"]) + extra.get("boxes", []), doc.get("props", []), sizes, list(nav["floors"]) + extra.get("floors", []), float(nav.get("spacing", 1.0)), float(nav.get("clearance", 0.35)))
        print("%s: %s" % (doc["id"], "under_feet %.2f" % feet if feet else "default"), "(already set)" if "under_feet" in nav else "")
        if feet and "under_feet" not in nav:
            rc = 1
            if not argv[1].endswith("-check"):
                head, sep, tail = text.partition('"clearance"')
                line_end = tail.index("\n")
                indent = head[head.rindex("\n") + 1:]
                text = head + sep + tail[:line_end].rstrip(",") + "," + tail[line_end:line_end + 1] + indent + '"under_feet": %s' % feet + "," + tail[line_end:]
                open(path, "w").write(text)
    return rc


def main(argv):
    if len(argv) > 2 and argv[1] in ("--under-feet", "--under-feet-check"):
        return under_feet_docs(argv)
    if len(argv) > 4 and argv[1] in ("--water-only", "--water-only-check"):
        return rewater(argv)
    if len(argv) > 4 and argv[1] in ("--lights-only", "--lights-only-check"):
        return relight(argv)
    if len(argv) > 3 and argv[1] == "--add-links":
        return add_links(argv)
    if len(argv) > 3 and argv[1] in ("--cut-links", "--cut-links-check"):
        return cut_links(argv)
    full = {}
    rc = budgeted(argv, full)
    if not rc and len(argv) >= 3:
        spec = json.load(open(argv[1]))
        write_nav_extra(os.path.join(argv[3] if len(argv) > 3 else os.path.join(HERE, "..", "maps"), spec["id"] + ".json"), full)
    return rc


def budget_candidates(argv, spec, path):
    """Whole-map conversion is on disk. The drawn world collides through its own hulls, so the spec's `drop_small` and
    `max_boxes` are also the horde's obstacle list: small boxes cut points and doorways (roy_highway: 4192 of 12663 points on the
    main ground whole, 16626 of 16888 with the budget; Death Star Escape 2227 points whole, 2778 with it). Tries the spec's
    budget and a fifth and two fifths of its drops put back; keeps the whole map unless one gives the horde more than 3% more main ground (or the
    whole map's share is under MAIN_SHARE_MIN). Returns the rc when a budgeted one won, None to carry on with the whole map."""
    whole = tuple(GRAPH_MAIN)
    n_whole = wire_size(path)[0]
    cands = []    # (main points, total points, boxes, keep_small)
    for frac in (0, 0.2, 0.4):
        if frac and (len(cands) == 0 or n_whole - cands[0][2] < 200):
            break
        keep = int((n_whole - cands[0][2]) * frac) if frac else 0
        rc = convert(argv, keep_small=keep)
        if rc:
            return rc
        cands.append((GRAPH_MAIN[0], GRAPH_MAIN[1], wire_size(path)[0], keep))
        print("  budget candidate keep_small=%d: %d of %d points on the main ground, %d boxes" % (keep, GRAPH_MAIN[0], GRAPH_MAIN[1], cands[-1][2]))
    top = max(c[0] for c in cands)
    best = max((c for c in cands if c[0] >= 0.95 * top), key=lambda c: c[2])    # as many boxes as keep the graph within 5%
    if whole[0] >= MAIN_SHARE_MIN * whole[1] and top <= whole[0] * 1.03:
        print("  whole map kept: %d points on the main ground, the budgeted graphs give no more than 3%% extra" % whole[0])
        return convert(argv, skip=("drop_small", "max_boxes"))
    print("  using the spec's budget with keep_small=%d (whole map: %d of %d points on the main ground)" % (best[3], whole[0], whole[1]))
    if cands[-1] is best:
        return 0
    return convert(argv, keep_small=best[3])


def budgeted(argv, full):
    if len(argv) < 3:
        print(__doc__)
        return 2
    # `drop_small` and `max_boxes` are a budget: every box is drawn by the world pack, so a dropped one
    # is something a body walks through. The whole map is tried first, then the fewest drops that fit.
    spec = json.load(open(argv[1]))
    path = os.path.join(argv[3] if len(argv) > 3 else os.path.join(HERE, "..", "maps"), spec["id"] + ".json")
    rc = convert(argv, skip=("drop_small", "max_boxes"))
    if rc:
        return rc
    if (spec.get("drop_small") or spec.get("max_boxes")) and world_pack_built(spec["id"]):
        pick = budget_candidates(argv, spec, path)
        if pick is not None:
            return pick
    if fits(path):
        return rc
    full.update(json.load(open(path)))
    whole = wire_size(path)
    if spec.get("drop_small"):
        print("  over the wire budget with every box: dropping small ones")
        rc = convert(argv, skip=("max_boxes",))
        if rc:
            return rc
        if fits(path):
            return put_back(argv, path, whole)
    # Still over: keep the largest boxes the budget holds (the spec's `max_boxes` is only the first guess).
    n, _, room = wire_size(path)
    cap = min(int(spec.get("max_boxes") or n * room * 0.97), LIMITS["boxes"])
    best = None
    for _ in range(6):
        print("  over the wire budget: keeping the %d largest boxes" % cap)
        rc = convert(argv, max_boxes=cap)
        if rc:
            return rc
        trim_nav(path)
        room = wire_size(path)[2]
        if room >= 1.0:
            best = cap
            grown = min(int(cap * room * 0.97), LIMITS["boxes"])
            if grown < cap * 1.03:
                return 0
            cap = grown
        elif best is not None:
            rc = convert(argv, max_boxes=best)
            trim_nav(path)
            return rc
        else:
            cap = int(cap * room * 0.93)    # the boxes are only part of the bytes (terrain, nav, solid props), so a ratio of the whole undershoots
    if best is None:
        print("  still over the wire budget")
    return 0


def trim_nav(path):
    """Cuts the written document's floors and links to the game's counts, largest floors first: the whole graph is in the
    server-only nav extra, which replaces them before the horde's graph is built."""
    with open(path) as f:
        doc = json.load(f)
    nav = doc.get("nav") or {}
    if len(nav.get("floors", [])) <= LIMITS["floors"] and len(nav.get("links", [])) <= LIMITS["links"]:
        return
    nav["floors"] = sorted(nav["floors"], key=lambda f: -(f[2] - f[0]) * (f[3] - f[1]))[:LIMITS["floors"]]
    nav["links"] = nav["links"][:LIMITS["links"]]
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)


def put_back(argv, path, whole):
    """After dropping every small box fits: put back the largest of them as far as the budget goes."""
    dropped = wire_size(path)
    per_box = max(1.0, (whole[1] - dropped[1]) / max(1, whole[0] - dropped[0]))
    keep = min(int((WIRE_BUDGET * 0.98 - dropped[1]) / per_box), int(dropped[0] * (dropped[2] - 1.0)))
    for _ in range(3):
        if keep < 50:
            break
        print("  putting back the %d largest small boxes" % keep)
        rc = convert(argv, skip=("max_boxes",), keep_small=keep)
        if rc or fits(path):
            return rc
        n, _, room = wire_size(path)    # over: scale by what those boxes really cost
        keep = int(n * room * 0.97) - dropped[0]
    print("  over the wire budget with them: dropping every small box again")
    return convert(argv, skip=("max_boxes",))


def prior_world_collision(path):
    """Whether the previous document collided through its world's hulls: kept on a re-import, because boxes alone drop the
    slanted and cut brushes the hulls hold exactly (krusty_krab's wall_missing rose from 9 to 12 without them)."""
    try:
        with open(path) as f:
            return bool(json.load(f).get("world_collision"))
    except (OSError, ValueError):
        return False


def prior_solid_props(path):
    """The previous document's `solid_props` (tools/solid_props.sh), or []."""
    try:
        with open(path) as f:
            return json.load(f).get("solid_props", [])
    except (OSError, ValueError):
        return []


def write_hulls(doc, out_dir):
    """`<out_dir>/hulls/<id>.{json,bin}`: the hulls `world_collision` selects, in the server's maps pack,
    which carries no world. Removed when the document collides with its boxes alone."""
    from dotbsp import audit as daudit, mesh as dmesh
    prefix = os.path.join(out_dir, "hulls", doc["id"])
    for ext in (".json", ".bin"):
        if os.path.exists(prefix + ext):
            os.remove(prefix + ext)
    sel = doc.get("world_collision")
    if not sel:
        return
    world = os.path.join(HERE, "..", "world", doc["world"], doc["id"])
    man = dmesh.write_collision(world, prefix, lambda hulls: daudit.collision_hulls(hulls, sel))
    print("  world_collision: %d hulls in hulls/%s" % (len(man["hulls"]), doc["id"]))


def convert(argv, skip=(), keep_small=0, max_boxes=0):
    DROPS.clear()
    spec = json.load(open(argv[1]))
    for k in skip:
        spec.pop(k, None)
    if max_boxes:
        spec["max_boxes"] = max_boxes
    global THIN_WALLS, GREEDY_FLOORS, THIN_LINTELS
    THIN_LINTELS = bool(spec.get("thin_lintels"))
    THIN_WALLS = bool(spec.get("thin_walls"))
    GREEDY_FLOORS = bool(spec.get("greedy_floors"))
    global STEP, JUMP, MIN_FLOOR_Y, HEAD
    MIN_FLOOR_Y = spec.get("min_floor_y")
    HEAD = float(spec.get("head", 1.7))    # a crouching body fits under 1.3: a duck-under grate is part of the route
    if spec.get("flood_step"):
        STEP = JUMP = flood_step(spec["flood_step"])
    out_dir = argv[3] if len(argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "maps")
    bs = load_source(argv[2], spec.get("terrain") is not False)    # displacements are read unless the spec opts out, for the auto rule below
    ents = bs.entities
    surv = [e for e in ents if e.get("classname") == spec["survivor_class"]]
    y0 = float(spec.get("y0", 0.0))    # spec y0: metres the source floor sits above the game's y = 0 (the nav is flat at 0)

    boxes, skipped = [], 0
    dropped_any = False
    tread_ids, added_ids = set(), set()    # added_ids: authored stand-ins, never what the cap drops
    for b in model_boxes(bs, 0, y0):
        boxes.append(b)

    # A spec without `terrain` takes the heightfield when the source draws enough displacement ground: drawn terrain with no collision
    # is a floor the player falls through, and the stepped boxes it left were 0.35 to 3 m lower than the picture (collide_probe).
    # `"terrain": false` opts out (a map whose displacements are trim); `terrain_auto_m2` moves the threshold.
    if "terrain" not in spec and bs.terrain_tris():
        area = dterrain.Heightfield.from_tris(dterrain.game_tris(bs.terrain_tris(), S, y0), 1.0).count()
        if area >= float(spec.get("terrain_auto_m2", TERRAIN_AUTO_M2)):
            spec["terrain"] = True
            print("terrain: %d m2 of displacements, taken as the heightfield (spec \"terrain\": false opts out)" % area)

    # `terrain`: ground that is displacements (sculpted heightmaps, not brushes) has no box at all.
    # It ships as dot-map's heightfield (the game collides with its triangles) and the floods walk
    # it by slope; a stepped box field stopped them at the first hill. Optional {"budget": bytes}.
    global TERRAIN, TERRAIN_PTS
    TERRAIN, TERRAIN_PTS = None, []
    if spec.get("terrain"):
        topts = spec["terrain"] if isinstance(spec["terrain"], dict) else {}
        if not bs.terrain_tris():
            sys.exit("import_bsp: spec asks for terrain but the intermediate has no displacements; rebuild it with `bsp.py convert --displacements`")
        terrain_tris = dterrain.game_tris(bs.terrain_tris(), S, y0)
        TERRAIN = dterrain.Heightfield.from_tris(terrain_tris, 1.0)
        terrain_area = TERRAIN.count()
        print("terrain: %dx%d heightfield at 1 m from %d displacement triangles" % (TERRAIN.nx, TERRAIN.nz, len(terrain_tris)))

    # brush entities: solid ones are part of the world; gates are held back for the route
    gate_cands = []
    door_shut = []   # boxes of doors closed at map start: they block the reachability filters only
    wc_models, wc_flat = [0], []    # what `world_collision` collides with, the same selection as the boxes
    for e in ents:
        m = str(e.get("model", ""))
        if not m.startswith("*"):
            continue
        cls = e.get("classname")
        # dot-map's world-treatment classes (func_wall, func_breakable, func_physbox...) are drawn by the
        # global pack, so they collide here too: drawn and not solid is a floor somebody falls through.
        gate = cls in spec.get("gate_classes", [])
        if cls == spec.get("barricade_class"):
            continue
        if not gate and (cls in spec.get("solid_classes", []) or dclasses.treatment(cls)[0] == "world"):
            mb = model_boxes(bs, int(m[1:]), y0)
            if cls in BREAKABLE and cls not in spec.get("solid_classes", []):
                # the game breaks nothing: an upright breakable (a door, a window) would close its way for good
                mb = [b for b in mb if b["size"][1] <= 0.5]
                wc_flat.append(int(m[1:]))
            else:
                wc_models.append(int(m[1:]))
            boxes.extend(mb)
        elif not gate and movers.closed_door(e):
            door_shut.extend(model_boxes(bs, int(m[1:]), y0))
        elif gate:
            only = spec.get("gate_names")
            gb = model_boxes(bs, int(m[1:]), y0)
            if gb and (only is None or e.get("targetname") in only):
                e = dict(e)
                e.update(only.get(e.get("targetname"), {}) if only else {})
                gate_cands.append((e, gb))

    # Authoring the source could not carry: a moving platform or a puzzle step is a thing the game
    # has no mover for, so a spec adds the boxes that stand in for it (`add_boxes`, game coordinates),
    # cuts the ones that must go (`cut`: regions [x0,y0,z0,x1,y1,z1] whose box centres are removed),
    # and names a gate made of added boxes (`extra_gates`) that opens like a door.
    for c in spec.get("cut", []):
        x0, y0_, z0, x1, y1, z1 = c[:6]
        keep_only(boxes, [b for b in boxes if not (x0 <= b["at"][0] <= x1 and y0_ <= b["at"][1] <= y1 and z0 <= b["at"][2] <= z1
                                                   and (len(c) < 7 or b["mat"] == c[6]))], "cut")
    # `crop` [x0, z0, x1, z1]: a map converted only in part (an escape map whose later stages need a
    # lift or a vanishing floor) keeps the boxes that touch this rectangle, game coordinates. What is
    # beyond is a wall of sky and scenery nobody reaches, and it is most of a big map's box count.
    if spec.get("crop"):
        cx0, cz0, cx1, cz1 = spec["crop"]
        n0 = len(boxes)
        keep_only(boxes, [b for b in boxes if b["at"][0] + b["size"][0] / 2 >= cx0 and b["at"][0] - b["size"][0] / 2 <= cx1
                          and b["at"][2] + b["size"][2] / 2 >= cz0 and b["at"][2] - b["size"][2] / 2 <= cz1], "crop")
        print("  cropped %d of %d boxes outside the stage" % (n0 - len(boxes), n0))
    # `clip_y` [lo, hi]: a wall or shaft that runs far past the stage (a trench wall a hundred metres
    # tall) is shortened to this band, and one wholly outside is dropped. It is the same wall to a
    # body, and a frame looking down is no longer blocked by it.
    if spec.get("clip_y"):
        lo_c, hi_c = spec["clip_y"]
        kept = []
        for b in boxes:
            b0, b1 = b["at"][1] - b["size"][1] / 2, b["at"][1] + b["size"][1] / 2
            if b1 <= lo_c or b0 >= hi_c:
                continue
            if b0 < lo_c or b1 > hi_c:
                n0, n1 = max(b0, lo_c), min(b1, hi_c)
                b["at"][1], b["size"][1] = r3((n0 + n1) / 2), r3(n1 - n0)
            kept.append(b)
        print("  clip_y: %d boxes kept of %d" % (len(kept), len(boxes)))
        keep_only(boxes, kept, "clip_y")
    # `widen_doorways` metres: a doorway narrower than two of the graph's points (a metre apart, 0.35 m
    # kept clear of a wall) has no point in it, so the rooms either side were joined by a link running
    # through the wall. The two wall pieces flanking such a gap are trimmed back to this width, so the
    # rooms join by geometry. Opt-in: it moves collision.
    if spec.get("widen_doorways"):
        n_wd = widen_doorways(boxes, float(spec["widen_doorways"]))
        print("  widen_doorways: %d doorways opened to %.2f m" % (n_wd, float(spec["widen_doorways"])))
    # `min_thick` metres: a wall thinner than the body's radius (a diagonal wall the box cutter steps
    # as a chain of 0.38 m slabs, a panel 8 cm deep) leaves slivers the navigation join cannot
    # sew across and a cell flood samples past. Standing walls (taller than half a metre) are
    # thickened about their centre to this; a floor or a ledge is left, its thickness is height.
    if spec.get("min_thick"):
        mt, n_fat = float(spec["min_thick"]), 0
        for b in boxes:
            if b["size"][1] <= 0.5 or b.get("yaw"):
                continue
            for ax in (0, 2):
                if b["size"][ax] < mt:
                    b["size"][ax] = r3(mt)
                    n_fat += 1
        print("  min_thick: %d wall sides thickened to %.2f m" % (n_fat, mt))
    # `unyaw`: the game's graph cuts a turned box out as its axis-aligned bounds, so a 7 m wall
    # at 45 degrees closes a 5 m square of corridor to the horde (the battle station's diagonal
    # walls shut the route off). A standing turned box is replaced by a row of upright pieces as
    # long as the wall is thick, each following the line, so the bounds hug it. Floors stay.
    if spec.get("unyaw"):
        mt_ = float(spec.get("min_thick", 0.6))
        out, n_pc, n_src = [], 0, 0
        for b in boxes:
            if not b.get("yaw") or b["size"][1] <= 0.5:
                out.append(b)
                continue
            n_src += 1
            DROPS.append(("unyaw_replaced", b))
            th = max(min(b["size"][0], b["size"][2]), mt_)
            along = 0 if b["size"][0] >= b["size"][2] else 2
            L = b["size"][along]
            n = max(1, int(math.ceil(L / th)))
            a = math.radians(b["yaw"])
            # Godot's rotation about Y: local x is (cos, -sin), local z is (sin, cos).
            ux, uz = (math.cos(a), -math.sin(a)) if along == 0 else (math.sin(a), math.cos(a))
            pl = L / n
            for k in range(n):
                off = -L / 2 + (k + 0.5) * pl
                t = {kk: vv for kk, vv in b.items() if kk != "yaw"}
                t["at"] = [r3(b["at"][0] + ux * off), b["at"][1], r3(b["at"][2] + uz * off)]
                t["size"] = [r3(abs(ux) * pl + abs(uz) * th), b["size"][1], r3(abs(uz) * pl + abs(ux) * th)]
                out.append(t)
                n_pc += 1
        print("  unyaw: %d turned walls became %d upright pieces" % (n_src, n_pc))
        boxes[:] = out
    # `min_floor`: the same for a floor. A diagonal floor is stepped as a row of strips 0.39 m deep,
    # each narrower than the graph's metre spacing, so a strip holds no point of its own and the
    # row is a chain of islands. Widening a strip to this (it overlaps its neighbours, so the
    # ground only gains a ragged edge under the diagonal wall) gives the graph points to join.
    if spec.get("min_floor"):
        mf, n_fl = float(spec["min_floor"]), 0
        for b in boxes:
            if b["size"][1] > 0.5 or b.get("yaw") or not b.get("visible", True):
                continue
            ax = 0 if b["size"][0] < b["size"][2] else 2
            if b["size"][ax] < mf and b["size"][2 - ax] >= 2 * mf:
                b["size"][ax] = r3(mf)
                n_fl += 1
        print("  min_floor: %d floor strips widened to %.2f m" % (n_fl, mf))
    # `drop_small` [volume, longest side]: detail too small to matter to a body or the graph (shelf
    # slats, trim, rail posts) is dropped so a big map fits the document's box limit. A box that
    # long is a floor strip or a stair slab, never dropped whatever its volume.
    if spec.get("drop_small"):
        vmax, smax = spec["drop_small"]
        small = [b for b in boxes if b["size"][0] * b["size"][1] * b["size"][2] < vmax and max(b["size"]) < smax]
        if spec.get("keep_treads"):
            # A stair of 0.25 m risers is boxes 1.3 x 0.2 x 0.4: each under `vmax` and shorter than `smax`,
            # so the whole flight went with the shelf slats and the lab's upper and lower floors were
            # never joined (the flood walked round by drops, which a body cannot climb back). A small box
            # is a tread when it is a hand wide and a box of another top 0.1 to 0.45 m
            # away stands against it: that is a riser, and no slat or rail post has one.
            by_cell = {}
            for c in boxes:
                for ix in range(int((c["at"][0] - c["size"][0] / 2 - 0.1) // 2), int((c["at"][0] + c["size"][0] / 2 + 0.1) // 2) + 1):
                    for iz in range(int((c["at"][2] - c["size"][2] / 2 - 0.1) // 2), int((c["at"][2] + c["size"][2] / 2 + 0.1) // 2) + 1):
                        by_cell.setdefault((ix, iz), []).append(c)

            def stair_runs(cands):
                # A flight of low risers (a porch's seven steps of 8 cm, 15 cm deep) has no neighbour 0.1 m
                # away to qualify, but its boxes touch each other with tops climbing: three or more tops
                # in one chain of touching small boxes is a stair, where slats and trim share one top.
                near = {}
                for b in cands:
                    if b.get("yaw") or b["size"][1] < 0.03 or b["size"][0] * b["size"][2] < 0.25:
                        continue
                    for ix in range(int((b["at"][0] - b["size"][0] / 2 - 0.1) // 2), int((b["at"][0] + b["size"][0] / 2 + 0.1) // 2) + 1):
                        for iz in range(int((b["at"][2] - b["size"][2] / 2 - 0.1) // 2), int((b["at"][2] + b["size"][2] / 2 + 0.1) // 2) + 1):
                            near.setdefault((ix, iz), []).append(b)
                pool = {id(b): b for v in near.values() for b in v}
                links = {k: [] for k in pool}
                for v in near.values():
                    for i, a in enumerate(v):
                        for c in v[i + 1:]:
                            if abs(c["at"][0] - a["at"][0]) > (c["size"][0] + a["size"][0]) / 2 + 0.06 or abs(c["at"][2] - a["at"][2]) > (c["size"][2] + a["size"][2]) / 2 + 0.06:
                                continue
                            if 0.03 <= abs(c["at"][1] + c["size"][1] / 2 - a["at"][1] - a["size"][1] / 2) <= 0.45:
                                links[id(a)].append(id(c))
                                links[id(c)].append(id(a))
                found, seen = [], set()
                for k in pool:
                    if k in seen or not links[k]:
                        continue
                    comp, todo = [], [k]
                    seen.add(k)
                    while todo:
                        n = todo.pop()
                        comp.append(pool[n])
                        for m in links[n]:
                            if m not in seen:
                                seen.add(m)
                                todo.append(m)
                    tops = {round(c["at"][1] + c["size"][1] / 2, 2) for c in comp}
                    if 3 <= len(tops) and len(comp) <= 3 * len(tops) and max(tops) - min(tops) <= 1.5:
                        found += comp
                return found

            def riser_beside(b):
                if b.get("yaw") or b["size"][1] < 0.03 or min(b["size"][0], b["size"][2]) < 0.2 or b["size"][0] * b["size"][2] < 0.25:
                    return False
                top = b["at"][1] + b["size"][1] / 2
                for c in by_cell.get((int(b["at"][0] // 2), int(b["at"][2] // 2)), []):
                    if c is b or c.get("yaw"):
                        continue
                    if abs(c["at"][0] - b["at"][0]) > (c["size"][0] + b["size"][0]) / 2 + 0.06 or abs(c["at"][2] - b["at"][2]) > (c["size"][2] + b["size"][2]) / 2 + 0.06:
                        continue
                    if 0.1 <= abs(c["at"][1] + c["size"][1] / 2 - top) <= 0.45:
                        return True
                return False

            treads = [b for b in small if riser_beside(b)]
            treads += [b for b in stair_runs(small) if b not in treads]
            small = [b for b in small if b not in treads]
            # A tread is ground, not an obstacle: the graph grows every box by the clearance, and a
            # flight of 0.25 m risers is within that of every point on it, so no point stood on a stair.
            tread_ids.update(id(b) for b in treads)
            print("  keep_treads: %d small boxes kept as stair treads" % len(treads))
        if keep_small:
            small.sort(key=lambda b: b["size"][0] * b["size"][1] * b["size"][2])
            small = small[:max(0, len(small) - keep_small)]
        keep_only(boxes, [b for b in boxes if b not in small], "drop_small")
        print("  dropped %d small boxes" % len(small))
        dropped_any = dropped_any or bool(small)
    if spec.get("max_boxes") and len(boxes) > spec["max_boxes"] and not spec.get("nav_before_cap"):
        # The wire limit (ZzMapDoc.WIRE_LIMIT, MAX_BOXES) caps what a document can collide with; the
        # drawn world pack carries the detail, so the smallest solids go first.
        # Kept treads are not counted here: the flood prunes the ones it never stands on and the cap is
        # applied again after it, so a map's only stair is not the first thing the cap takes.
        order = sorted((i for i in range(len(boxes)) if id(boxes[i]) not in tread_ids), key=lambda i: boxes[i]["size"][0] * boxes[i]["size"][1] * boxes[i]["size"][2])
        gone = set(order[:len(order) - int(spec["max_boxes"])])
        print("  max_boxes: dropped the %d smallest of %d boxes" % (len(gone), len(boxes)))
        dropped_any = dropped_any or bool(gone)
        keep_only(boxes, [b for i, b in enumerate(boxes) if i not in gone], "max_boxes")
    for ab in spec.get("add_boxes", []):
        boxes.append(dict(ab))
        added_ids.add(id(boxes[-1]))
    # `stairs`: a flight that stands in for a slope too steep for the graph (a slide, a ladder shaft).
    # [x0, y0, z0, x1, y1, z1, width]: steps from the top (x0, y0, z0) to the foot (x1, y1, z1) along
    # the longer horizontal axis, each rising at most 0.4 m over a run of 1 m or more (under the flood's 0.42 step) (the graph's points are a metre apart), as wide as
    # `width` across, standing on `base` (the lowest y) so there is no gap under a step.
    for st in spec.get("stairs", []):
        x0, y0_, z0, x1, y1_, z1, w = st[:7]
        base = st[7] if len(st) > 7 else min(y0_, y1_) - 1.0
        along_x = abs(x1 - x0) >= abs(z1 - z0)
        length = abs(x1 - x0) if along_x else abs(z1 - z0)
        n = max(1, int(math.ceil(abs(y1_ - y0_) / 0.4)))
        run = length / (n + 1)
        for k in range(n + 1):
            top = y0_ + (y1_ - y0_) * k / n
            t = (k + 0.5) / (n + 1)
            cx, cz = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
            sz = [r3(run), r3(top - base), r3(w)] if along_x else [r3(w), r3(top - base), r3(run)]
            boxes.append({"at": [r3(cx), r3((top + base) / 2), r3(cz)], "size": sz, "mat": st[8] if len(st) > 8 else "metal"})
    if spec.get("drop_buried"):
        # A box wholly inside another solid one adds nothing to collision, but the graph reads its
        # top as an obstacle at a height no floor has: two overlapping terraces left a whole step
        # with no points on it.
        def extent(b):
            return [b["at"][k] - b["size"][k] / 2 for k in range(3)] + [b["at"][k] + b["size"][k] / 2 for k in range(3)]
        ext = [(b, extent(b)) for b in boxes if not b.get("yaw") and b.get("visible", True)]
        # A container covers its contents' centre, so look it up in an x/z grid (every pair was 540M tests on a whole station).
        cell, grid, big = 8.0, collections.defaultdict(list), []
        for b, f in ext:
            nx, nz = int(f[3] // cell) - int(f[0] // cell) + 1, int(f[5] // cell) - int(f[2] // cell) + 1
            if nx * nz > 64:
                big.append((b, f))
                continue
            for gx in range(int(f[0] // cell), int(f[3] // cell) + 1):
                for gz in range(int(f[2] // cell), int(f[5] // cell) + 1):
                    grid[(gx, gz)].append((b, f))
        buried = set()
        for b, e in ext:
            near = grid.get((int(((e[0] + e[3]) / 2) // cell), int(((e[2] + e[5]) / 2) // cell)), ())
            for c, f in (*near, *big):
                if c is not b and id(c) not in buried and all(f[k] <= e[k] + 0.02 for k in range(3)) and all(f[k + 3] >= e[k + 3] - 0.02 for k in range(3)):
                    buried.add(id(b))
                    break
        keep_only(boxes, [b for b in boxes if id(b) not in buried], "drop_buried")
        print("  dropped %d buried box(es)" % len(buried))
    if spec.get("drop_ramps") and spec.get("drop_every_ramp"):
        # Only for a document too big for the wire (the mall): slab-cut brushes rising `drop_ramps`
        # metres that no body could walk up (tunnel walls, arches) go. A walkable ramp or stair always
        # stays: the drawn world shows it, and a ramp with no collision is a floor players fall through.
        gone_ids = {b["_brush"] for b in boxes if b.get("_rise", 0) >= spec["drop_ramps"] and not b["_walkable"]}
        n0 = len(boxes)
        keep_only(boxes, [b for b in boxes if b.get("_brush") not in gone_ids], "drop_ramps")
        print("  dropped %d slab(s) of %d unwalkable slab brush(es) rising %.1f m or more" % (n0 - len(boxes), len(gone_ids), spec["drop_ramps"]))
    for g in spec.get("extra_gates", []):
        gate_cands.append((dict(g), [dict(b) for b in g["boxes"]]))

    # A sky lid (a slab over the whole map, there to keep a player from climbing out) is a floor to the
    # bake: every random route the choke finder walks starts and ends up on it, so the street's
    # traffic is a handful of routes and no place is a choke. Nobody reaches it from the ground.
    if spec.get("drop_lids"):
        # An invisible thin slab is the author's clip over the map, whatever its area (the manor's is six, down to 500 m2).
        lids = [b for b in boxes if b["at"][1] - b["size"][1] / 2 > 3.0 and (b["size"][0] * b["size"][2] > 1500.0
                or (b.get("visible", True) is False and b["size"][1] < 0.3 and b["size"][0] * b["size"][2] > 300.0))]
        keep_only(boxes, [b for b in boxes if b not in lids], "drop_lids")
        print("  dropped %d sky lid(s)" % len(lids))

    # Roadblocks across an open street. The choke finder wants narrow places many routes share,
    # and a street nine metres wide has none: the doors are barricaded (off the bake), so the
    # horde's whole way to a house would be open ground. A wrecked-vehicle line with a gap a
    # little over two bodies wide gives it somewhere to be funnelled, and the gap is the choke.
    for x, gap0, gap1 in spec.get("roadblocks", []):
        z0, z1 = spec["street_z"]
        for a, b_ in ((z0, gap0), (gap1, z1)):
            if b_ - a > 0.1:
                boxes.append({"at": [r3(x), 1.1, r3((a + b_) / 2)], "size": [0.8, 2.2, r3(b_ - a)],
                              "mat": "metal", "tint": [0.42, 0.4, 0.38]})

    barricades, bar_boxes, bar_geo = [], [], []
    bc = spec.get("barricade_class")
    for e in ents:
        if bc and e.get("classname") == bc and str(e.get("model", "")).startswith("*"):
            lo, hi = bs.model_bounds(int(e["model"][1:]))
            og = parse_vec(e.get("origin", "0 0 0"))      # a brush entity's model is origin-relative
            lo = [lo[k] + og[k] for k in range(3)]
            hi = [hi[k] + og[k] for k in range(3)]
            a, b_ = gpt(lo, y0), gpt(hi, y0)
            mn = [min(a[k], b_[k]) for k in range(3)]
            mx = [max(a[k], b_[k]) for k in range(3)]
            size = [mx[k] - mn[k] for k in range(3)]
            bid = "bar_%d" % (len(barricades) + 1)
            thin = 0 if size[0] < size[2] else 2
            n = max(2, int(round(size[1] / 0.36)))
            for k in range(n):
                sz = list(size)
                sz[1] = size[1] / n * 0.82
                sz[thin] = max(sz[thin], 0.14)
                bar_boxes.append({
                    "at": [r3((mn[0] + mx[0]) / 2), r3(mn[1] + (k + 0.5) * size[1] / n), r3((mn[2] + mx[2]) / 2)],
                    "size": [r3(v) for v in sz], "mat": "wood", "tint": [0.62 - 0.05 * (k % 3), 0.46 - 0.04 * (k % 3), 0.3],
                    "nav": False, "barricade": bid})
            bar_geo.append((bid, (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2, thin))
            barricades.append({"id": bid, "label": "the boards at x %d z %d" % (round((mn[0] + mx[0]) / 2), round((mn[2] + mx[2]) / 2)),
                               "health": spec.get("barricade_health", 1800)})

    def src_to_game(e):
        return gpt(parse_vec(e["origin"]), y0)

    # A map whose first stage cannot be built from brushes (a lift, a vanishing floor) starts its
    # survivors at a later stage instead: `survivor_start` is a block of spawns at a game position.
    ss = spec.get("survivor_start")
    start_spawns = []
    if ss:
        for r in range(ss.get("rows", 4)):
            for c in range(ss.get("cols", 6)):
                start_spawns.append({"at": [r3(ss["at"][0] + c * ss.get("gap", 1.4)), r3(ss["at"][1] + 0.1), r3(ss["at"][2] + r * ss.get("gap", 1.4))],
                                     "yaw": ss.get("yaw", 0.0)})
    starts = [s_["at"] for s_ in start_spawns] if ss else [src_to_game(e) for e in surv]
    if TERRAIN:
        # Ship the finest field that fits the budget over the ground the survivors reach (plus a
        # margin), then walk exactly the shipped field so the walk mask matches what the game reads.
        walked = {(a, b) for a, b, h in build_nav(boxes, starts)[2] if (a, b, h) in build_nav.tsurf}
        if not walked:
            sys.exit("import_bsp: the survivors reach no terrain; check the spawns and y0 (or set the spec's \"terrain\": false if the displacements are scenery)")
        xs = [a * CELL for a, _ in walked]
        zs = [b * CELL for _, b in walked]
        near = {(a // 4, b // 4) for a, b in walked}
        hf, size = dterrain.fit(terrain_tris, (min(xs), min(zs), max(xs) + CELL, max(zs) + CELL), int(topts.get("budget", TERRAIN_BUDGET)),
                                cells=tuple(topts.get("cells", TERRAIN_CELLS)),
                                keep=lambda x, z: (math.floor(x / CELL) // 4, math.floor(z / CELL) // 4) in near)
        TERRAIN = dterrain.Heightfield.decode(hf.encode(0.05))[0]
        print("terrain: shipped %dx%d at %.1f m, %d bytes" % (TERRAIN.nx, TERRAIN.nz, TERRAIN.cell, size))
        # Cliffs and undercuts a heightfield smooths away stay solid where they are drawn. They join
        # the document last: the walk flood reads them as walls on ground it can climb.
        FACES[:] = dterrain.face_boxes(terrain_tris, TERRAIN, size=float(topts.get("face_cell", 0.5)))
        print("terrain: %d boxes hold the steep faces the field cannot" % len(FACES))
    floors, surf, seen, parent, dist = build_nav(boxes, starts)

    # Distant scenery (the original's backdrop pieces, its boundary walls twenty metres tall) is a
    # tall box nobody on the ground can stand beside: with no ground within 0.6 m of its footprint
    # it only gives the navigation bake tops to wander on, and the choke finder's random routes
    # start and end up there (twelve of a hundred and ninety-two found a way) instead of in the street.
    if spec.get("drop_decor"):
        def beside_ground(b, g=0.6):
            x0, x1 = b["at"][0] - b["size"][0] / 2 - g, b["at"][0] + b["size"][0] / 2 + g
            z0, z1 = b["at"][2] - b["size"][2] / 2 - g, b["at"][2] + b["size"][2] / 2 + g
            return any(x0 < f[2] and x1 > f[0] and z0 < f[3] and z1 > f[1] for f in floors)
        far = [b for b in boxes if b["at"][1] + b["size"][1] / 2 > 3.0 and not beside_ground(b)]
        keep_only(boxes, [b for b in boxes if b not in far], "drop_decor")
        print("  dropped %d boxes of distant scenery" % len(far))

    # `drop_ceilings` [min area, y]: a roof or ceiling slab (thin, wide, no walkable top: a body
    # can never stand on it) at least `y` metres above the ground under it is a lid over the stage.
    # It hides the route from the overview and from every frame that looks down, and the horde
    # never needed it: the walls are tall. Dropped after the flood, so a slab that is a floor to
    # somebody (a walkway, a gantry) is kept because its top is ground.
    if spec.get("drop_ceilings"):
        amin, ymin = spec["drop_ceilings"]

        def walkable_top(b):
            top = b["at"][1] + b["size"][1] / 2
            for fx in (-0.4, 0.0, 0.4):
                for fz in (-0.4, 0.0, 0.4):
                    ix = int(math.floor((b["at"][0] + fx * b["size"][0]) / CELL))
                    iz = int(math.floor((b["at"][2] + fz * b["size"][2]) / CELL))
                    if any(abs(h - top) <= 0.3 and (ix, iz, h) in seen for h in surf.get((ix, iz), ())):
                        return True
            return False
        lids = [b for b in boxes if b["size"][1] <= 1.2 and b["size"][0] * b["size"][2] >= amin and b["at"][1] - b["size"][1] / 2 >= ymin
                and not b.get("yaw") and not walkable_top(b)]
        keep_only(boxes, [b for b in boxes if b not in lids], "drop_ceilings")
        print("  dropped %d ceiling slab(s)" % len(lids))

    # Props are cut out of the game's ground, and a metre-spaced graph has no point in a way
    # narrower than two cells: both left whole rooms (posts, caches, a window's far side) off the
    # horde's ground though the cell flood reached them. So the ground is flooded again with the
    # props as obstacles and 2x2 openings only; a prop that shuts a way the first flood had is
    # dropped (a sofa in a doorway), and what is still cut off is not ground.
    def settle(p, lift=0.0):
        h = floor_at(surf, seen, p[0], p[2], p[1])
        return None if h is None else [r3(p[0]), r3(h + lift), r3(p[2])]

    sizes = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "prop_sizes.json")))["props"]
    cand = []
    for e in ents:
        if e.get("classname") in ("prop_physics", "prop_dynamic", "func_physbox", "prop_physics_override", "prop_dynamic_override", "prop_physics_multiplayer"):
            pm = spec.get("prop_models", {})
            cid = pm.get(e.get("model")) or {k.lower(): v for k, v in pm.items()}.get(str(e.get("model", "")).lower())
            p = settle(src_to_game(e)) if cid else None
            if p:
                cand.append({"id": cid, "at": p, "yaw": r3(parse_vec(e.get("angles", "0 0 0"))[1] % 360)})

    # Static props are compiled out of the entity lump (dot-map's intermediate keeps them apart),
    # and in most maps they are the furniture and the wrecks.
    pm_lower = {k.lower(): v for k, v in spec.get("prop_models", {}).items()}
    for sp in getattr(bs, "doc", {}).get("static_props", []) if isinstance(getattr(bs, "doc", None), dict) else []:
        cid = pm_lower.get(str(sp.get("model", "")).lower().replace("//", "/"))
        if not cid:
            continue
        o, a = sp["origin"], sp.get("angles", [0, 0, 0])
        p = settle(src_to_game({"origin": "%f %f %f" % (o[0], o[1], o[2])}))
        if p:
            cand.append({"id": cid, "at": p, "yaw": r3(a[1] % 360)})

    if spec.get("prop_min_y") is not None:
        # Props that settled into a pit the players never reach (a lower level the flood leaves out).
        cand = [c for c in cand if c["at"][1] >= spec["prop_min_y"]]

    if spec.get("drop_props"):
        # [x, z] of single props to leave out: one that settled inside a wall or on nothing (headless_maps names them).
        cand = [c for c in cand if not any(abs(c["at"][0] - x) < 0.3 and abs(c["at"][2] - z) < 0.3 for x, z in spec["drop_props"])]

    def blocks_of(plist):
        out = {}
        for pr in plist:
            sx, sy, sz = sizes[pr["id"]]
            if sy <= 0.5:
                continue
            rad = max(sx, sz) / 2 + 0.3
            for ix in range(int(math.floor((pr["at"][0] - rad) / CELL)), int(math.floor((pr["at"][0] + rad) / CELL)) + 1):
                for iz in range(int(math.floor((pr["at"][2] - rad) / CELL)), int(math.floor((pr["at"][2] + rad) / CELL)) + 1):
                    out.setdefault((ix, iz), []).append(pr["at"][1])
        return out

    def ground_cells(plist):
        r = build_nav(boxes, starts, blocks_of(plist), True)
        return r, {(a, b, round(h, 2)) for a, b, h in r[2]}

    keep = list(cand)
    res, have = ground_cells(keep)
    base = {(a, b, round(h, 2)) for a, b, h in build_nav(boxes, starts, None, True)[2]}
    for pr in list(cand):
        if sizes[pr["id"]][1] <= 0.5 or have >= base:
            continue
        trial = [q for q in keep if q is not pr]
        r2, h2 = ground_cells(trial)
        # Cells are (x, z, height): a car park's roof a prop seals off is a level, not new ground columns.
        # A prop's own footprint is cells the flood loses by definition; only what it cut off
        # beyond that (a room behind it) is a reason to drop it, or every prop on open ground goes.
        if len(h2) - len(have) > len(blocks_of([pr])) + 6:
            keep, res, have = trial, r2, h2
    floors, surf, seen2, parent, dist = build_nav(boxes, starts, blocks_of(keep), True)
    # `nav_min_depth` metres: the flood's rectangles on a ragged diagonal (a stepped walkway) come out
    # one cell deep, 0.4 m, and the game's graph puts its first point half a spacing into a floor,
    # so a strip that thin holds no point and the walkway has no ground at all. A thin strip is
    # grown about its middle to this depth; it overlaps its neighbour rows (they are the same
    # walkway) and anything it spills onto a wall is dropped by the graph's clearance.
    if spec.get("nav_min_depth"):
        nd, n_grown = float(spec["nav_min_depth"]), 0
        for f in floors:
            for lo, hi in ((0, 2), (1, 3)):
                if f[hi] - f[lo] < nd:
                    mid = (f[lo] + f[hi]) / 2
                    f[lo], f[hi] = r3(mid - nd / 2), r3(mid + nd / 2)
                    n_grown += 1
        print("  nav_min_depth: %d floor sides grown to %.2f m" % (n_grown, nd))
    lost = {(a, b) for a, b, _ in seen} - {(a, b) for a, b, _ in have}
    seen = seen2
    if TERRAIN:
        tseen = {(a, b) for a, b, h in seen if (a, b, h) in build_nav.tsurf}
        TERRAIN_PTS = dterrain.walk_points(TERRAIN, dterrain.walk_samples(TERRAIN, tseen, CELL), 1.0)
    if tread_ids:
        # Only the stairs the flood stands on are ground; thousands of trim ridges that look like a
        # flight cost the wire for nothing. A tread is kept when a walked cell lies on its footprint.
        def walked(b):
            top = b["at"][1] + b["size"][1] / 2
            for ix in range(int(math.floor((b["at"][0] - b["size"][0] / 2 - 0.2) / CELL)), int(math.floor((b["at"][0] + b["size"][0] / 2 + 0.2) / CELL)) + 1):
                for iz in range(int(math.floor((b["at"][2] - b["size"][2] / 2 - 0.2) / CELL)), int(math.floor((b["at"][2] + b["size"][2] / 2 + 0.2) / CELL)) + 1):
                    if any((ix, iz, h) in seen and abs(h - top) <= 0.3 for h in surf.get((ix, iz), ())):
                        return True
            return False
        idle = [b for b in boxes if id(b) in tread_ids and not walked(b)]
        keep_only(boxes, [b for b in boxes if not any(b is c for c in idle)], "idle_treads")
        tread_ids.difference_update(id(b) for b in idle)
        print("  keep_treads: %d stair boxes the flood stands on kept, %d idle ones dropped" % (len(tread_ids), len(idle)))
        if spec.get("max_boxes") and len(boxes) > spec["max_boxes"] and not spec.get("nav_before_cap"):
            order = sorted((i for i in range(len(boxes)) if id(boxes[i]) not in tread_ids), key=lambda i: boxes[i]["size"][0] * boxes[i]["size"][1] * boxes[i]["size"][2])
            gone = set(order[:len(boxes) - int(spec["max_boxes"])])
            keep_only(boxes, [b for i, b in enumerate(boxes) if i not in gone], "max_boxes")
            print("  max_boxes: %d more smallest dropped after the stairs were pruned" % len(gone))
            dropped_any = dropped_any or bool(gone)
    print("  ground: %d cells walked without props, %d with; %d of %d props kept" % (len({(a, b) for a, b, _ in seen}) + len(lost), len({(a, b) for a, b, _ in seen}), len(keep), len(cand)))

    # The game's own graph, worked out here (nav_emulate): a doorway a metre wide has no point in
    # it, so the cell flood above reaches rooms the horde cannot. A window's two sides are joined
    # by a link from the nearest point on each; whole rooms the doors alone do not join to the
    # street are joined by a link across the doorway, where the cells say a body walks (every link
    # is across a gap the flood crossed). What is still cut off is not somewhere a post goes.
    import nav_emulate
    for b in boxes:
        if id(b) in tread_ids:
            b["nav"] = False     # after the flood, which walks the treads: see keep_treads
    if spec.get("clip_underlay"):
        # An invisible clip slab a little under a floor (the author's ground clip, 15 cm below the lab's
        # concrete) is no wall: the floor stands on it. But the game's graph grows every box by the
        # clearance on all sides and only forgives a box whose top is within 0.12 m of a floor, so a
        # slab 0.15 m down took every point off the lab's whole ground level (1300 m2 with no point,
        # and the horde never entered). Such a slab stays solid for bodies and is left out of the graph.
        under = 0
        for b in boxes:
            if b.get("visible", True) is not False or not b.get("solid", True) or "nav" in b or b.get("gate"):
                continue
            nb = nav_emulate._bounds(b)
            if nav_emulate._is_floor(nb, floors):
                continue
            if any(nb[0] < f[2] and nb[3] > f[0] and nb[2] < f[3] and nb[5] > f[1] and f[4] - 0.4 <= nb[4] <= f[4] - 0.02 for f in floors):
                b["nav"] = False
                under += 1
        print("  clip_underlay: %d invisible slab(s) under a floor left out of the graph" % under)
    G = nav_emulate.Graph(boxes + bar_boxes, keep, sizes, floors, terrain_pts=TERRAIN_PTS, solid_props=prior_solid_props(os.path.join(out_dir, spec["id"] + ".json")))
    links = list(build_nav.links)
    dead = set()
    for bid, cx, cz, thin in bar_geo:
        d = (1.2, 0.0) if thin == 0 else (0.0, 1.2)
        ia, ib = G.nearest(cx + d[0], 0.0, cz + d[1], 2.0), G.nearest(cx - d[0], 0.0, cz - d[1], 2.0)
        if ia < 0 or ib < 0 or G.nearest(cx + d[0], 0.0, cz + d[1], 2.5) < 0 or G.nearest(cx - d[0], 0.0, cz - d[1], 2.5) < 0:
            dead.add(bid)
            continue
        links.append([r3(G.pts[ia][0]), r3(G.pts[ia][1]), r3(G.pts[ia][2]), r3(G.pts[ib][0]), r3(G.pts[ib][1]), r3(G.pts[ib][2])])
        G.union(ia, ib)

    def walkable(a, b_):
        n = max(2, int(math.dist(a, b_) / 0.25))
        for k in range(n + 1):
            t = k / n
            x, y, z = a[0] + (b_[0] - a[0]) * t, a[1] + (b_[1] - a[1]) * t, a[2] + (b_[2] - a[2]) * t
            ix, iz = int(math.floor(x / CELL)), int(math.floor(z / CELL))
            if not any((ix, iz, h) in seen and abs(h - y) <= 0.45 for h in surf.get((ix, iz), ())):
                return False
        return True

    pairs = []
    for i, pa_ in enumerate(G.pts):
        hx, hz = int(math.floor(pa_[0] / 1.5)), int(math.floor(pa_[2] / 1.5))
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                for j in G.near.get((hx + dx, hz + dz), ()):
                    if j > i and G.find(i) != G.find(j):
                        dd = math.dist(pa_, G.pts[j])
                        if dd <= 3.2 and abs(pa_[1] - G.pts[j][1]) <= spec.get("link_dy", 0.5):
                            pairs.append((dd, i, j))
    pairs.sort()
    bridged = 0
    wall_obs = None if spec.get("keep_wall_links") else link_obstacles(boxes + bar_boxes, floors)
    for dd, i, j in pairs:
        if wall_obs is not None and link_blocked(wall_obs, G.pts[i], G.pts[j]):
            continue    # the cells only walk it because a wall thinner than a cell is invisible to them
        if G.find(i) != G.find(j) and walkable(G.pts[i], G.pts[j]):
            G.union(i, j)
            bridged += 1
            links.append([r3(G.pts[i][0]), r3(G.pts[i][1]), r3(G.pts[i][2]), r3(G.pts[j][0]), r3(G.pts[j][1]), r3(G.pts[j][2])])
    if wall_obs is not None:
        # A doorway narrower than two points leaves the room behind it an island, and the first
        # pass above no longer takes the window sill instead. Join each small island to the
        # ground by the shortest line a body of 0.25 m radius walks clear of every wall (the door).
        sizes_ = {}
        for i in range(len(G.pts)):
            r = G.find(i)
            sizes_[r] = sizes_.get(r, 0) + 1
        reach = []
        for i, pa_ in enumerate(G.pts):
            if sizes_[G.find(i)] >= 150:
                continue
            for j, pb_ in enumerate(G.pts):
                if sizes_[G.find(j)] < 150 or abs(pa_[0] - pb_[0]) > 5 or abs(pa_[2] - pb_[2]) > 5:
                    continue
                dd = math.dist(pa_, pb_)
                if dd <= 5.0 and abs(pa_[1] - pb_[1]) <= spec.get("link_dy", 0.5):
                    reach.append((dd, i, j))
        reach.sort()
        doors = 0
        for dd, i, j in reach:
            if G.find(i) != G.find(j) and not link_blocked(wall_obs, G.pts[i], G.pts[j], grow=0.25, min_h=0.4 if spec.get("strict_wall_links") else 0.55):
                G.union(i, j)
                doors += 1
                links.append([r3(G.pts[i][0]), r3(G.pts[i][1]), r3(G.pts[i][2]), r3(G.pts[j][0]), r3(G.pts[j][1]), r3(G.pts[j][2])])
        print("  doorway links: %d small islands joined through a gap" % doors)
        # What no clear line joins and is a real part of the map (40 points or more: a yard, a
        # floor of a building) keeps the old link through the wall or over the sill, because
        # leaving it an island cut the horde off half of Jurassic Park. Pockets under that are
        # left alone: a spawn behind a window is a short vault for a survivor, not a way in.
        sizes_ = {}
        for i in range(len(G.pts)):
            sizes_[G.find(i)] = sizes_.get(G.find(i), 0) + 1
        kept_walls = 0
        for dd, i, j in pairs:
            if G.find(i) != G.find(j) and sizes_[G.find(i)] >= 40 and sizes_[G.find(j)] >= 40 and walkable(G.pts[i], G.pts[j]):
                tot = sizes_[G.find(i)] + sizes_[G.find(j)]
                G.union(i, j)
                sizes_[G.find(i)] = tot
                kept_walls += 1
                links.append([r3(G.pts[i][0]), r3(G.pts[i][1]), r3(G.pts[i][2]), r3(G.pts[j][0]), r3(G.pts[j][1]), r3(G.pts[j][2])])
        print("  wall links kept: %d (the only join of a part of the map with 40 points or more)" % kept_walls)
    build_nav.links = links[:600]
    # The document carries every link and the game joins their ends, so the main ground is what they make one (a flight
    # of stairs the metre-spaced graph has no point on is joined by one link; counting without it said 368 of 2637).
    for l_ in build_nav.links + [list(x) for x in spec.get("extra_links", [])]:
        a_, b_ = G.nearest(l_[0], l_[1], l_[2], 1.0), G.nearest(l_[3], l_[4], l_[5], 1.0)
        if a_ >= 0 and b_ >= 0:
            G.union(a_, b_)
    # The walked route's path, and the links that join the graph's pieces along it, come before the main ground is
    # counted: a stair the metre-spaced points miss is joined by exactly such a link.
    exodus_path = None
    if spec["mode"] == "exodus" and dist:
        if spec.get("end_src"):
            tx, ty, tz = gpt(spec["end_src"], y0)
            end = min(dist, key=lambda st: (st[0] * CELL + CELL / 2 - tx) ** 2 + (st[1] * CELL + CELL / 2 - tz) ** 2 + 4 * (st[2] - ty) ** 2)
        else:
            end = max(dist, key=lambda st: dist[st])
        path = [end]
        while path[-1] in parent:
            path.append(parent[path[-1]])
        path.reverse()
        exodus_path = path
        if spec.get("route_bridge"):
            # A slope the flood climbs can be cut into floors that the graph builder does not join
            # (steps over 0.5 m, 1.5 m ties). Where the walked route crosses between two components,
            # link the points nearest each side; the flood proved a body gets across.
            bl = 0
            prev = None
            for st in path[::2]:
                q = (( st[0] + 0.5) * CELL, st[2], (st[1] + 0.5) * CELL)
                k = G.nearest(q[0], q[1], q[2], 2.0)
                if k < 0:
                    continue
                if prev is not None and G.find(prev) != G.find(k):
                    a_, b_ = G.pts[prev], G.pts[k]
                    G.union(prev, k)
                    build_nav.links.append([r3(a_[0]), r3(a_[1]), r3(a_[2]), r3(b_[0]), r3(b_[1]), r3(b_[2])])
                    bl += 1
                prev = k
            print("  route_bridge: %d links along the route" % bl)
    start_pt = G.nearest(starts[0][0], starts[0][1], starts[0][2], 3.0)
    if start_pt < 0:
        sys.exit(f"no ground within 3 m of the survivor start {starts[0]}: the start floats or the map's floor is not brushes (displacements, models)")
    main = G.find(start_pt)
    for bid, cx, cz, thin in bar_geo:
        d = (1.2, 0.0) if thin == 0 else (0.0, 1.2)
        for sgn in (1, -1):
            k = G.nearest(cx + sgn * d[0], 0.0, cz + sgn * d[1], 2.5)
            if k < 0 or G.find(k) != main:
                dead.add(bid)
    barricades = [b for b in barricades if b["id"] not in dead]
    for b in bar_boxes:
        if b["barricade"] in dead:
            del b["barricade"]
            del b["nav"]

    def on_main(x, y, z):
        k = G.nearest(x, y, z, 1.0)
        return k >= 0 and G.find(k) == main

    if os.environ.get("ZZ_DEBUG_POINTS"):
        # What the horde's graph reaches, for a plot: [x, y, z, 1 if on the main ground].
        with open(os.environ["ZZ_DEBUG_POINTS"], "w") as dbg:
            json.dump([[*q, int(G.find(i) == main)] for i, q in enumerate(G.pts)], dbg)
    if os.environ.get("ZZ_DEBUG_CHAIN"):
        lo_, hi_ = [float(t) for t in os.environ["ZZ_DEBUG_CHAIN"].split(",")]
        tgt = [st for st in seen if lo_ <= st[2] <= hi_]
        if tgt:
            st = tgt[len(tgt) // 2]
            chain = [st]
            while chain[-1] in parent:
                chain.append(parent[chain[-1]])
            prev = None
            for c in reversed(chain):
                if prev is None or abs(c[2] - prev[2]) > 0.05:
                    print("   chain", round((c[0] + 0.5) * CELL, 1), round(c[2], 2), round((c[1] + 0.5) * CELL, 1))
                prev = c
    main_pts = sum(1 for i in range(len(G.pts)) if G.find(i) == main)
    GRAPH_MAIN[:] = [main_pts, len(G.pts)]
    print("  game graph: %d points, %d bridged, %d of %d points on the main ground; %d barricades kept" % (
        len(G.pts), bridged, main_pts, len(G.pts), len(barricades)))

    spawns = list(start_spawns)
    for e in ([] if ss else surv):
        p = settle(src_to_game(e), 0.1)
        sr = spec.get("spawn_region")
        if p and sr and not (sr[0] <= p[0] <= sr[2] and sr[1] <= p[2] <= sr[3]):
            continue
        # A spawn a prop stands on is a survivor inside a van (headless_maps names them).
        if p and any(sizes[q["id"]][1] > 0.5 and abs(q["at"][0] - p[0]) < max(sizes[q["id"]][0], sizes[q["id"]][2]) / 2 + 0.6
                     and abs(q["at"][2] - p[2]) < max(sizes[q["id"]][0], sizes[q["id"]][2]) / 2 + 0.6 for q in keep):
            continue
        if p and p[2] <= spec.get("spawn_z_max", 1e9):
            sp = {"at": p, "yaw": r3(reader.yaw_to_godot(parse_vec(e.get("angles", "0 0 0"))[1]))}
            # The entity's name and start state, so the game's spawn_enabled can toggle it like the live entity does.
            if str(e.get("targetname", "")).strip():
                sp["name"] = str(e["targetname"]).strip()[:64]
            if str(e.get("StartDisabled", "0")).strip() == "1":
                sp["disabled"] = True
            spawns.append(sp)
    # Too few usable starts (the source's own sit in the air, in a wall or off the graph): the team
    # stands on the main ground around the flood's seed, 1.4 m apart, so a generated spec still plays.
    if G.pts and len(spawns) < spec.get("survivors", 4):
        sx, sy, sz = starts[0]
        mp = sorted((q for i, q in enumerate(G.pts) if G.find(i) == main), key=lambda q: (q[0] - sx) ** 2 + (q[2] - sz) ** 2)
        for q in mp:
            if len(spawns) >= max(4, spec.get("survivors", 4)):
                break
            if all((q[0] - o["at"][0]) ** 2 + (q[2] - o["at"][2]) ** 2 >= 1.96 for o in spawns):
                spawns.append({"at": [r3(q[0]), r3(q[1] + 0.1), r3(q[2])], "yaw": 0})
    # A survivor start on an island of the horde's graph (a room whose doorway is narrower than two
    # points) is a stand-in that has no path out and walks into the nearest wall: atix's second
    # spawn stood behind a window sill. It moves to the nearest point of the main ground within 8 m
    # (the team needs its places, so it is not dropped), 1.4 m clear of the other starts.
    if G.pts and not ss:
        mainpts = [q for i, q in enumerate(G.pts) if G.find(i) == main]
        moved = 0
        for sp in spawns:
            at = sp["at"]
            if any(abs(q[1] - at[1]) <= 0.6 and (q[0] - at[0]) ** 2 + (q[2] - at[2]) ** 2 <= 2.25 for q in mainpts):
                continue
            for q in sorted(mainpts, key=lambda q: (q[0] - at[0]) ** 2 + (q[2] - at[2]) ** 2 + (q[1] - at[1]) ** 2):
                if (q[0] - at[0]) ** 2 + (q[2] - at[2]) ** 2 > 64:
                    break
                if abs(q[1] - at[1]) <= 0.6 and all((q[0] - o["at"][0]) ** 2 + (q[2] - o["at"][2]) ** 2 >= 1.96 for o in spawns):
                    sp["at"] = [r3(q[0]), r3(q[1] + 0.1), r3(q[2])]
                    moved += 1
                    break
        if moved:
            print("  survivor spawns: %d off the horde's ground moved onto it" % moved)
    zsp = [list(p) for p in spec.get("zombie_start", [])]
    for cls in ([] if spec.get("zombie_start") else spec["zombie_classes"]):
        for e in ents:
            if e.get("classname") == cls:
                p = settle(src_to_game(e))
                if p:
                    zsp.append(p)

    # A start the horde cannot path out of is a zombie idling for the whole wave (an octagon room
    # whose stepped edge the graph cannot climb): zkeep the starts within a metre of the main ground.
    if zsp and G.pts:
        if door_shut:
            sealed = dflood.sealed_by([b for b in boxes if b.get("solid", True)], door_shut, [starts[0]], zsp, cell=CELL)
            if sealed:
                print("  zombie starts: %d behind a door closed at the start dropped" % len(sealed))
                zsp = [p for p in zsp if p not in sealed]
        # A start inside a damaging trigger_hurt (a shelter under a nuke's kill trigger) is a zombie that dies on
        # spawn or when the event fires. A volume holding over half the starts is the map-wide kill, not a place.
        burnt = []
        for e in ents:
            m = str(e.get("model", ""))
            if e.get("classname") != "trigger_hurt" or not m.startswith("*") or float(e.get("damage", 10) or 0) <= 0:
                continue
            hurt = []
            for rec in bs.model_brushes(int(m[1:])):
                if rec["hull"]:
                    pts = [gpt(q, y0) for q in rec["hull"]]
                    hurt.append([min(q[k] for q in pts) if k < 3 else max(q[k - 3] for q in pts) for k in range(6)])
            for h in hurt:
                hit = dflood.inside_volumes(zsp, [h], pad=0.25)
                if 0 < len(hit) <= len(zsp) // 2:
                    burnt.extend(q for q in hit if q not in burnt)
        if burnt:
            print("  zombie starts: %d inside a damaging trigger_hurt dropped" % len(burnt))
            zsp = [p for p in zsp if p not in burnt]
        zkeep = [p for p in zsp if any(G.find(i) == main and (q[0] - p[0]) ** 2 + (q[2] - p[2]) ** 2 <= 1.0 and abs(q[1] - p[1]) <= 0.6
                                      for i, q in enumerate(G.pts))]
        if len(zkeep) >= 4:
            if len(zkeep) != len(zsp):
                print("  zombie starts: %d of %d on the main ground" % (len(zkeep), len(zsp)))
            zsp = zkeep

    if G.pts and len(zsp) < 4:
        # The source's zombie spawns did not land on ground: the horde starts at the far end of the main ground.
        cx = sum(o["at"][0] for o in spawns) / max(1, len(spawns))
        cz = sum(o["at"][2] for o in spawns) / max(1, len(spawns))
        far = -1 if spec["mode"] == "survival" else 1  # an escape map's horde starts a run behind the team, not across the map
        for q in sorted((q for i, q in enumerate(G.pts) if G.find(i) == main and (spec["mode"] == "survival" or 100 <= (q[0] - cx) ** 2 + (q[2] - cz) ** 2 <= 1600)),
                        key=lambda q: far * ((q[0] - cx) ** 2 + (q[2] - cz) ** 2)):
            if len(zsp) >= 8:
                break
            if all((q[0] - o[0]) ** 2 + (q[2] - o[2]) ** 2 >= 4 for o in zsp):
                zsp.append([r3(q[0]), r3(q[1]), r3(q[2])])

    def settle_any(p):
        ix, iz = int(math.floor(p[0] / CELL)), int(math.floor(p[2] / CELL))
        hs = [h for h in surf.get((ix, iz), []) if abs(h - p[1]) <= 0.6]
        return [r3(p[0]), r3(min(hs, key=lambda h: abs(h - p[1]))), r3(p[2])] if hs else None

    items = []
    kinds = [("weapon", "smg"), ("ammo", None), ("weapon", "shotgun"), ("medkit", None), ("pills", None), ("weapon", "rifle")]
    item_map = spec.get("item_map", {})
    k = 0
    for e in ents:
        cls = e.get("classname")
        if cls == spec.get("item_class") or cls in item_map:
            p = settle_any(src_to_game(e))
            if p:
                if cls in item_map:
                    kind, wid = item_map[cls]
                else:
                    kind, wid = kinds[k % len(kinds)]
                    k += 1
                it = {"kind": kind, "at": p}
                if wid:
                    it["id"] = wid
                items.append(it)
    for kind, wid, x, z in spec.get("items", []):
        p = settle_any([x, spec.get("items_y", 22.3), z])
        if p:
            it = {"kind": kind, "at": p}
            if wid:
                it["id"] = wid
            items.append(it)
    if spec.get("items_auto") and spawns:
        # Starting kit beside the first survivor spawn, for a map whose spec cannot name coordinates (tools/auto_spec.py).
        sx, sy, sz = spawns[0]["at"]
        for (kind, wid), (dx, dz) in zip(kinds[:5], [(2, 2), (-2, 2), (2, -2), (-2, -2), (0, 3)]):
            p = settle_any([sx + dx, sy, sz + dz])
            if p:
                it = {"kind": kind, "at": p}
                if wid:
                    it["id"] = wid
                items.append(it)
    items = items[:60]

    props, cache_src = [], []
    for pr in keep:
        props.append(pr)
        if pr["id"] == "survival_box":
            cache_src.append(pr["at"])

    objectives, route, end_area, gate_boxes = [], [], [], []
    if spec["mode"] == "exodus" and dist:
        path = exodus_path

        def wp(st):
            return [r3((st[0] + 0.5) * CELL), r3(st[2]), r3((st[1] + 0.5) * CELL)]

        step = max(8, len(path) // 150 + 1)
        route = [wp(path[i]) for i in range(0, len(path), step)]
        if route[-1] != wp(path[-1]):
            route.append(wp(path[-1]))
        ex, ey, ez = wp(path[-1])
        end_area = [{"min": [r3(ex - 3), r3(ey - 0.6), r3(ez - 3)], "max": [r3(ex + 3), r3(ey + 3), r3(ez + 3)]}]
        found = []
        for e, gb in gate_cands:
            first = None
            for k, st in enumerate(path):
                x, h, z = wp(st)
                for b in gb:
                    lo, hi = b["at"][1] - b["size"][1] / 2, b["at"][1] + b["size"][1] / 2
                    if hi >= h - 0.3 and lo <= h + 1.8 and any(inside_box(b, x + dx, z + dz) for dx in (-0.5, 0, 0.5) for dz in (-0.5, 0, 0.5)):
                        first = k
                        break
                if first is not None:
                    break
            if first is not None:
                found.append((first, e, gb))
        found.sort(key=lambda t: t[0])
        for n, (k, e, gb) in enumerate(found):
            gid = "gate_%d" % (n + 1)
            for b in gb:
                b["gate"] = gid
                gate_boxes.append(b)
            x, h, z = wp(path[max(0, k - 3)])
            objectives.append({"id": "obj_%d" % (n + 1), "kind": "use", "at": [x, r3(h + 1.0), z], "label": e.get("label", spec.get("gate_label", "Open the way on")),
                               "seconds": 2, "holdout": e.get("holdout", spec.get("holdout", 20)), "opens": [gid], "prop": "lever",
                               "message": "It is opening. Hold on until it does!"})
        objectives = objectives[:16]

    deep = {}
    for ix, iz, h in seen:
        if all(any((ix + dx, iz + dz, h2) in seen and abs(h2 - h) <= STEP for h2 in surf.get((ix + dx, iz + dz), ()))
               for dx in range(-2, 3) for dz in range(-2, 3)):
            if on_main((ix + 0.5) * CELL, h, (iz + 0.5) * CELL):
                deep.setdefault((ix, iz), h)

    # A post on an island of the horde's graph is a post no zombie reaches: only spawns on the main ground are candidates.
    posts, pts = [], [s["at"] for s in spawns if on_main(s["at"][0], s["at"][1], s["at"][2])] or [s["at"] for s in spawns]
    off_main = [s["at"] for s in spawns if not on_main(s["at"][0], s["at"][1], s["at"][2])]
    if off_main:
        print("  survivor spawns: %d off the main ground (none of it within 8 m); not used as posts" % len(off_main))
    # Posts: the spawns, spread. A spec that names a `post_region` ([x0, z0, x1, z1]) puts them
    # inside it instead, on ground well clear of a wall: a team that holds a house is held behind
    # its doors and windows, which is what makes the narrow places the horde must come through
    # (chokes); posts all on an open street have none.
    if spec.get("post_region") and spec["mode"] == "survival":
        x0, z0, x1, z1 = spec["post_region"]
        pts = [[r3((ix + 0.5) * CELL), r3(h), r3((iz + 0.5) * CELL)] for (ix, iz), h in sorted(deep.items())
               if x0 <= (ix + 0.5) * CELL <= x1 and z0 <= (iz + 0.5) * CELL <= z1 and h <= 0.35 and on_main((ix + 0.5) * CELL, h, (iz + 0.5) * CELL)]
    if pts and spec["mode"] == "survival":
        posts.append(pts[0] if not spec.get("post_region") else min(pts, key=lambda q: (q[0] - spec["post_region"][0]) ** 2 + q[2] ** 2))
        while len(posts) < spec.get("posts", 6) and len(posts) < len(pts):
            posts.append(max(pts, key=lambda q: min((q[0] - p[0]) ** 2 + (q[2] - p[2]) ** 2 for p in posts)))
    caches = []
    # A cache goes on open ground the horde certainly has: the nearest cell to the crate whose
    # whole 5x5 neighbourhood is ground (a crate's own cell is cut out, and the edge of a room
    # holds a point the game's graph, a metre apart, may not).
    for p in cache_src:
        near = [(((ix + 0.5) * CELL - p[0]) ** 2 + ((iz + 0.5) * CELL - p[2]) ** 2, ix, iz, h) for (ix, iz), h in deep.items()
                if abs(h - p[1]) < 1.0 and abs((ix + 0.5) * CELL - p[0]) < 4 and abs((iz + 0.5) * CELL - p[2]) < 4]
        if not near:
            continue
        _, ix, iz, h = min(near)
        q = [r3((ix + 0.5) * CELL), r3(h), r3((iz + 0.5) * CELL)]
        cr = spec.get("cache_region") or spec.get("post_region")
        if cr and not (cr[0] <= q[0] <= cr[2] and cr[1] <= q[2] <= cr[3]):
            continue  # a crate outside the players' region is a long walk the horde never makes
        if on_main(q[0], q[1], q[2]) and h <= 0.35 and len(caches) < 8 and all((q[0] - c[0]) ** 2 + (q[2] - c[2]) ** 2 > 36 for c in caches):
            caches.append(q)

    if spec.get("caches_near_posts") and not caches:
        # A map with no supply crates of its own: a cache a few metres from each post, on ground
        # whose whole neighbourhood is open and the horde's, never in the start room's middle.
        for pst in posts:
            near = sorted((((ix + 0.5) * CELL - pst[0]) ** 2 + ((iz + 0.5) * CELL - pst[2]) ** 2, ix, iz, h) for (ix, iz), h in deep.items()
                          if abs(h - pst[1]) < 0.5 and 9 <= ((ix + 0.5) * CELL - pst[0]) ** 2 + ((iz + 0.5) * CELL - pst[2]) ** 2 <= 100)
            for _, ix, iz, h in near:
                q = [r3((ix + 0.5) * CELL), r3(h), r3((iz + 0.5) * CELL)]
                cr = spec.get("cache_region")
                if cr and not (cr[0] <= q[0] <= cr[2] and cr[1] <= q[2] <= cr[3]):
                    continue  # a spec that names a cache region keeps these in it too
                if on_main(q[0], q[1], q[2]) and all((q[0] - c[0]) ** 2 + (q[2] - c[2]) ** 2 > 49 for c in caches):
                    caches.append(q)
                    break
        caches = caches[:8]

    lights = []
    al = spec.get("auto_lights")
    if al and not al.get("force") and len(source_lamps(ents, y0)) >= AUTO_LIGHTS_BELOW:
        al = None    # the author's own lamps are the map's light; a grid replaces them only when there are few
    if al:
        # The map had no lamps of its own (it was lit by baked light, which is the author's): a lamp
        # every `spacing` metres over the horde's ground, `height` above the floor, taken in a
        # fixed order so the same map always gets the same lamps.
        sp_ = al.get("spacing", 6.0)
        taken = {}
        for (ix, iz), h in sorted(deep.items()):
            cx, cz = (ix + 0.5) * CELL, (iz + 0.5) * CELL
            key = (int(math.floor(cx / sp_)), int(math.floor(cz / sp_)), round(h))
            if key in taken or not on_main(cx, h, cz):
                continue
            taken[key] = [r3(cx), r3(h + al.get("height", 2.3)), r3(cz)]
        picked = list(taken.items())[:al.get("max", 100)]
        if al.get("checker"):
            # Every other cell of the lamp grid: a sparse, dim building instead of a lit shop.
            picked = [(k, v) for k, v in picked if (k[0] + k[1]) % 2 == 0]
        for _k, at in picked:
            lights.append({"at": at, "range": al.get("range", 7.0), "energy": al.get("energy", 0.9), "colour": al.get("colour", [1.0, 0.93, 0.8])})
    if not al:
        lights.extend(source_lamps(ents, y0))

    env = {"sky_top": [0.02, 0.03, 0.07], "sky_horizon": [0.08, 0.1, 0.15], "ground": [0.03, 0.03, 0.04], "sun_pitch": -45.0,
           "sun_yaw": 12.0, "sun_energy": 0.22, "sun_colour": [0.45, 0.65, 0.95], "ambient": [0.36, 0.4, 0.52], "ambient_energy": 0.3, "fog": 0.02}

    env.update(spec.get("environment", {}))
    lo, hi = gpt(bs.model_bounds(0)[0], y0), gpt(bs.model_bounds(0)[1], y0)
    # `split_over` metres: a box wider than this (a harbour's ground slab, 430 m across) is cut into
    # equal tiles. The lightmap unwrap packs a box's faces into one chart, and a chart that size
    # leaves no texel density the sheet can hold, so the bake fails; tiles each get their own chart.
    # Same solid to a body and to the graph, which only see the union.
    if not spec.get("keep_wall_links"):
        build_nav.links = filter_wall_links(build_nav.links, boxes + bar_boxes, keep, sizes, floors, bool(spec.get("strict_wall_links")), spec.get("extra_links", []))
    if spec.get("nav_before_cap") and spec.get("max_boxes") and len(boxes) > spec["max_boxes"]:
        # The cap is the wire's, not the horde's: the flood, route and graph above saw every box, as the server's does (nav.json).
        order = sorted((i for i in range(len(boxes)) if id(boxes[i]) not in tread_ids | added_ids), key=lambda i: boxes[i]["size"][0] * boxes[i]["size"][1] * boxes[i]["size"][2])
        gone = set(order[:len(boxes) - int(spec["max_boxes"])])
        keep_only(boxes, [b for i, b in enumerate(boxes) if i not in gone], "max_boxes_cap")
        dropped_any = True
        print("  max_boxes (nav_before_cap): dropped the %d smallest after the graph was built" % len(gone))
    if spec.get("split_over"):
        lim, tiled = float(spec["split_over"]), []
        for b in boxes + bar_boxes + gate_boxes:
            nx = int(math.ceil(b["size"][0] / lim)) if not b.get("yaw") else 1
            nz = int(math.ceil(b["size"][2] / lim)) if not b.get("yaw") else 1
            if nx * nz == 1:
                tiled.append(b)
                continue
            for i in range(nx):
                for k in range(nz):
                    t = dict(b)
                    t["size"] = [r3(b["size"][0] / nx), b["size"][1], r3(b["size"][2] / nz)]
                    t["at"] = [r3(b["at"][0] - b["size"][0] / 2 + (i + 0.5) * b["size"][0] / nx), b["at"][1],
                               r3(b["at"][2] - b["size"][2] / 2 + (k + 0.5) * b["size"][2] / nz)]
                    tiled.append(t)
        print("  split_over: %d boxes became %d" % (len(boxes + bar_boxes + gate_boxes), len(tiled)))
        all_boxes = tiled
    else:
        all_boxes = boxes + bar_boxes + gate_boxes
    turned = aim_spawns(spawns, all_boxes, floors=floors, goals=[list(p) for p in list(posts) + list(caches) + list(route or [])[1:]])
    if turned:
        print("  survivor spawns: %d facing a wall turned to open ground" % turned)
    nav_doc = {"spacing": 1.0, "clearance": 0.35, "floors": floors, "links": build_nav.links[:600] + [list(l) for l in spec.get("extra_links", [])]}
    import nav_emulate
    feet = nav_emulate.under_feet_for(all_boxes, props, sizes, floors, terrain_pts=TERRAIN_PTS, solid_props=prior_solid_props(os.path.join(out_dir, spec["id"] + ".json")))
    if feet:
        nav_doc["under_feet"] = feet
        print("  nav.under_feet %.2f: a slab just under a floor was swallowing its points" % feet)
    doc = {
        "format": 1, "kind": "zombiezone_map", "id": spec["id"], "name": spec["name"],
        "author": "%s (original map, %s, %s); converted. Removed on request." % (spec["author"], spec["page"], spec["licence"]),
        "attribution": "Geometry converted from %s by %s, %s (%s), used non-commercially with credit under the licence. Credit: %s. The original file is not redistributed and its textures and models are not used (the game draws its own surfaces and Kenney CC0 props). This conversion is removed on the author's request." % (
            spec["source"], spec["author"], spec["page"], spec["licence"], spec["author"]),
        "blurb": spec["blurb"], "mode": spec["mode"], "survivors": spec.get("survivors", 0), "next": "",
        "survive_seconds": spec.get("survive_seconds", 0), "kill_y": spec.get("kill_y", r3(min(lo[1], hi[1]) - 12.0)),
        "environment": env,
        "boxes": [{k: v for k, v in b.items() if not k.startswith("_")} for b in all_boxes], "props": props, "lights": lights,
        "spawns": {"survivors": spawns},
        "areas": {"start": [], "end": end_area}, "route": route or ([spawns[0]["at"]] if spawns else []),
        "nav": nav_doc,
        "items": items, "objectives": objectives, "sleepers": [list(z) for z in spec.get("sleepers", [])], "zombie_spawns": zsp, "posts": posts, "caches": caches,
        "barricades": barricades,
    }
    if len(lights) > REALTIME_LAMPS:
        doc["wire_lamps"] = WIRE_LAMPS
    if spawns:
        sp = [s["at"] for s in spawns]
        doc["areas"]["start"] = [{"min": [r3(min(p[0] for p in sp) - 2), r3(min(p[1] for p in sp) - 0.5), r3(min(p[2] for p in sp) - 2)],
                                  "max": [r3(max(p[0] for p in sp) + 2), r3(max(p[1] for p in sp) + 3), r3(max(p[2] for p in sp) + 2)]}]
    if TERRAIN:
        doc["terrain"] = TERRAIN.encode(0.05, dterrain.walk_samples(TERRAIN, tseen, CELL), spec.get("terrain_mat", "dirt"))
        for x0, y0_, z0, x1, y1, z1 in FACES:
            doc["boxes"].append({"at": [r3((x0 + x1) / 2), r3((y0_ + y1) / 2), r3((z0 + z1) / 2)], "size": [r3(x1 - x0), r3(y1 - y0_), r3(z1 - z0)],
                                 "mat": spec.get("terrain_mat", "dirt")})
    lids = [b for stage, b in DROPS if stage == "drop_lids"]
    if lids:    # walk_check skips them: a lid is above the ground on purpose, and the audit would call its top a missing floor
        doc["dropped_lids"] = []
        for b in lids:
            r = max(b["size"][0], b["size"][2]) / 2
            doc["dropped_lids"].append([r3(b["at"][0] - r), r3(b["at"][1] - b["size"][1] / 2), r3(b["at"][2] - r),
                                        r3(b["at"][0] + r), r3(b["at"][1] + b["size"][1] / 2), r3(b["at"][2] + r)])
    water = water_volumes(bs, y0, floors, spec, doc["boxes"], doc["kill_y"])
    if water:
        doc["water"] = water
        print("  water: %d volume(s)" % len(water))
    # Toys: loose dot-props, from the spec's hints ([toy, anchor, dx, dz]); build_maps settles each
    # onto clear floor, the same way the hand-built maps' are.
    prior_solid = prior_solid_props(os.path.join(out_dir, spec["id"] + ".json"))
    if spec.get("toys"):
        import build_maps
        if prior_solid:
            doc["solid_props"] = prior_solid    # settle_toys keeps a toy out of them
        hints = build_maps.spec_hints(spec)
        doc["toys"] = build_maps.settle_toys(doc, hints)
    doc.pop("solid_props", None)
    if prior_solid:    # solid_props.sh refreshes it; kept so a re-import never drops it
        doc = {k2: v2 for k, v in doc.items() for k2, v2 in (((k, v), ("solid_props", prior_solid)) if k == "props" else ((k, v),))}
    doc = name_world(doc, os.path.join(HERE, ".."))
    # The spec's `ambient`, else the keyword vote of the world's sound names (tools/ambient.py).
    field, _why = ambient.resolve(spec["id"], spec)
    if field is not None:
        doc = ambient.put(doc, field)
    prior_hulls = prior_world_collision(os.path.join(out_dir, spec["id"] + ".json"))
    hull_all = spec.get("hull_collision")    # {"cuts": [i, ...], "uncropped": bool}: the world's hulls collide where the boxes were cut or cropped
    if (dropped_any or hull_all or prior_hulls) and doc.get("world"):
        # The budget dropped boxes the world pack still draws: the game collides with the pack's own
        # hulls for these models, so the wire carries only what the graph needs.
        moved = [k for k in ("widen_doorways",) if spec.get(k)]
        if moved:
            print("  world_collision: not written, the spec moves collision (%s)" % ", ".join(moved), file=sys.stderr)
        else:
            doc["world_collision"] = {"models": sorted(set(wc_models)), "flat": sorted(set(wc_flat)), "flat_height": 0.5,
                                      "skip": [list(c[:6]) for i, c in enumerate(spec.get("cut", [])) if len(c) < 7 and i not in (hull_all or {}).get("cuts", [])]}
            if spec.get("crop") and not (hull_all or {}).get("uncropped"):
                doc["world_collision"]["within"] = list(spec["crop"])
            if spec.get("clip_y") and not (hull_all or {}).get("uncropped"):
                doc["world_collision"]["band"] = list(spec["clip_y"])
            print("  world_collision: %d models from the world pack's hulls" % len(doc["world_collision"]["models"]))
    doc = cut_blocked_links(doc, spec.get("extra_links", []))
    doc = reseat_spawns(doc)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, spec["id"] + ".json")
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    write_hulls(doc, out_dir)
    if os.environ.get("ZZ_DROP_TRACE"):
        with open(os.environ["ZZ_DROP_TRACE"], "w") as f:
            json.dump([[st, {k: v for k, v in b.items() if k in ("at", "size", "yaw", "mat", "kind", "visible", "_rise", "_walkable")}] for st, b in DROPS], f, separators=(",", ":"))
    print("%s: %d boxes (%d barricade), %d props, %d lights, %d spawns, %d zombie spawns, %d floors, %d items, %d caches, %d posts" % (
        path, len(doc["boxes"]), len(bar_boxes), len(props), len(lights), len(spawns), len(zsp), len(floors), len(items), len(caches), len(posts)))
    print("  route %d points, %d objectives, %d gate boxes, %d cells reachable, end %s" % (len(route), len(objectives), len(gate_boxes), len(seen), end_area[0]["min"] if end_area else None))
    if spec.get("terrain"):
        share = len(tseen) * CELL * CELL / max(terrain_area, 1.0)
        print("  terrain: the survivors walk %.0f m2, %.1f%% of the displacements' %d m2" % (len(tseen) * CELL * CELL, share * 100, terrain_area))
        if share < 0.05:
            print("  WARNING: the survivors' flood covers under 5% of the terrain: check the spawns, y0 and the slope limit")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
