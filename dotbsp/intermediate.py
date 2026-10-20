"""The shared intermediate: one BSP map as a JSON document every game's adapter reads.

The format is documented in ../README.md ("The intermediate"). In short: map units, map axes
(Z-up), nothing decided that a game decides differently. A brush carries its real planes, its
hull corners and the default box decomposition; an entity carries every key it had; spawns
and lights are the entities the family's games all read, normalised once. The credit block is
carried through untouched so an adapter writes the same author, page and licence the map was
converted under.
"""

import hashlib
import os

from . import boxes as _boxes
from . import reader
from . import units as _units

FORMAT = "dot-bsp-intermediate"
VERSION = 1

CONTENTS_NAMES = (
    (reader.CONTENTS_SOLID, "solid"), (reader.CONTENTS_WINDOW, "window"),
    (reader.CONTENTS_GRATE, "grate"), (reader.CONTENTS_SLIME, "slime"),
    (reader.CONTENTS_WATER, "water"), (reader.CONTENTS_MOVEABLE, "moveable"),
    (reader.CONTENTS_PLAYERCLIP, "playerclip"), (reader.CONTENTS_MONSTERCLIP, "monsterclip"),
    (reader.CONTENTS_MONSTER, "monster"), (reader.CONTENTS_DETAIL, "detail"),
    (reader.CONTENTS_LADDER, "ladder"),
)

CREDIT_KEYS = ("author", "page", "licence", "no_share_check", "notes")


def _r(v, n=3):
    return round(float(v), n)


def _rv(p, n=3):
    return [_r(c, n) for c in p]


def contents_names(c):
    return [n for bit, n in CONTENTS_NAMES if c & bit]


def summary(bsp, name=None, nbytes=None):
    """The cheap facts about a map, without loading its geometry (what `list` prints)."""
    ents = reader.parse_entities(bsp._lump(reader.LUMP_ENTITIES).decode("ascii", "replace"))
    classes = {}
    for e in ents:
        c = e.get("classname", "?")
        classes[c] = classes.get(c, 0) + 1
    spawns = {}
    for c, n in classes.items():
        team = reader.SPAWN_CLASSES.get(c)
        if team:
            spawns[team] = spawns.get(team, 0) + n
    brush_ents = sum(1 for e in ents if str(e.get("model", "")).startswith("*"))
    try:
        sprp = len(bsp.static_props())
    except Exception:          # a malformed game lump costs the count, not the listing
        sprp = -1
    compressed = any(bsp.d[o:o + 4] == b"LZMA" for o, ln, _ in bsp.dir if ln >= 17)
    world = ents[0] if ents and ents[0].get("classname") == "worldspawn" else {}
    try:
        models = bsp._array(reader.LUMP_MODELS, reader.FMT_MODEL)
        (mn, mx) = (models[0][0:3], models[0][3:6]) if models else ((0, 0, 0), (0, 0, 0))
    except Exception:
        mn, mx = (0, 0, 0), (0, 0, 0)
    return {
        "name": name or os.path.splitext(os.path.basename(bsp.path))[0],
        "version": bsp.version, "revision": bsp.revision,
        "bytes": nbytes if nbytes is not None else len(bsp.d),
        "compressed": compressed,
        "entities": len(ents), "brush_entities": brush_ents,
        "brushes": len(bsp._lump(reader.LUMP_BRUSHES)) // 12,
        "displacements": len(bsp._lump(reader.LUMP_DISPINFO)) // 176,
        "static_props": sprp,
        "lights": sum(n for c, n in classes.items() if c in reader.LIGHT_CLASSES),
        "spawns": spawns,
        "pak_files": len(bsp.pak_names()),
        "size_m": [_r((mx[i] - mn[i]) * reader.METRES_PER_UNIT, 1) for i in range(3)],
        "sky": world.get("skyname", ""),
        "classes": classes,
    }


def _light(i, e):
    # `_light` is "r g b brightness"; a mapper's typo costs the colour, not the light.
    toks = e.get("_light", "").split()
    col = [float(t) for t in toks] if toks and all(_isnum(t) for t in toks) else []
    if len(col) < 3:
        col = [255.0, 255.0, 255.0]
    if len(col) < 4:
        col.append(200.0)
    out = {"entity": i, "class": e.get("classname"), "origin": _rv(reader.entity_vec(e)),
           "colour": _rv(col[:3], 1), "brightness": _r(col[3], 1),
           "angles": _rv(reader.entity_vec(e, "angles"))}
    if "pitch" in e and _isnum(e["pitch"]):
        out["pitch"] = _r(float(e["pitch"]))
    for k in ("_cone", "_inner_cone", "_distance", "_fifty_percent_distance", "_zero_percent_distance"):
        if k in e and _isnum(e[k]):
            out[k.lstrip("_")] = _r(float(e[k]))
    if e.get("classname") == "light_environment":
        out["sun"] = True
        amb = e.get("_ambient", "").split()
        if len(amb) >= 3 and all(_isnum(t) for t in amb):
            out["ambient"] = [_r(float(t), 1) for t in amb[:4]]
    return out


def _isnum(t):
    try:
        float(t)
        return True
    except ValueError:
        return False


def build(bsp, credit=None, faces=False, displacements=False, slab=_boxes.SLAB, name=None, scale=None):
    """The intermediate document for a loaded `reader.Bsp`.

    `faces` adds the world's drawn faces (polygons by material) and `displacements` the
    terrain triangles; both are off by default because a box game reads neither and a surf
    map's faces are tens of megabytes of JSON. `scale` is metres per unit (`units.VISUAL` by
    default, `units.HULL` for a game that wants a 72 unit player to be 1.83 m); the geometry
    stays in map units either way, and the choice is written to `units.metres_per_unit`.
    """
    scale = _units.parse_scale(scale if scale is not None else _units.VISUAL)
    mats, mat_index = [], {}

    def mat(name_):
        if name_ not in mat_index:
            mat_index[name_] = len(mats)
            mats.append({"name": name_, "clean": reader.clean_material(name_)})
        return mat_index[name_]

    ents = bsp.entities
    model_entity = {}
    for i, e in enumerate(ents):
        m = str(e.get("model", ""))
        if m.startswith("*") and m[1:].isdigit():
            model_entity[int(m[1:])] = i
    models, brushes, seen = [], [], set()
    for mi in range(len(bsp.models)):
        ei = model_entity.get(mi)
        if mi > 0 and ei is None:
            continue
        origin = reader.entity_vec(ents[ei]) if ei is not None else [0.0, 0.0, 0.0]
        mn, mx = bsp.model_bounds(mi)
        ids = []
        for bi in sorted(bsp.model_brushes(mi)):
            if bi in seen or bi >= len(bsp.brushes):
                continue
            seen.add(bi)
            first, count, contents = bsp.brushes[bi]
            sides = []
            for s in bsp.brushsides[first:first + count]:
                if s[3]:
                    continue
                pl = bsp.planes[s[0]]
                mname, flags = bsp.side_material(s)
                d = pl[3] + pl[0] * origin[0] + pl[1] * origin[1] + pl[2] * origin[2]
                sides.append({"plane": [_r(pl[0], 6), _r(pl[1], 6), _r(pl[2], 6), _r(d, 3)],
                              "material": mat(mname), "flags": flags})
            hull = [(p[0] + origin[0], p[1] + origin[1], p[2] + origin[2]) for p in bsp.brush_hull(bi)]
            planes = [tuple(s["plane"]) for s in sides]
            rec = {"id": bi, "model": mi, "contents": contents, "contents_names": contents_names(contents),
                   "player_solid": bool(contents & reader.MASK_PLAYERSOLID),
                   "sides": sides, "hull": [_rv(p) for p in hull]}
            if hull:
                rec["mins"] = _rv([min(p[k] for p in hull) for k in range(3)])
                rec["maxs"] = _rv([max(p[k] for p in hull) for k in range(3)])
                rec["boxes"] = [_box_json(b) for b in _boxes.decompose(planes, hull, slab=slab)]
            brushes.append(rec)
            ids.append(bi)
        models.append({"index": mi, "entity": ei, "origin": _rv(origin),
                       "mins": _rv([mn[k] + origin[k] for k in range(3)]),
                       "maxs": _rv([mx[k] + origin[k] for k in range(3)]), "brushes": ids})

    entities = []
    for i, e in enumerate(ents):
        rec = {"index": i, "classname": e.get("classname", ""), "keys": e}
        if "origin" in e:
            rec["origin"] = _rv(reader.entity_vec(e))
        m = str(e.get("model", ""))
        if m.startswith("*") and m[1:].isdigit():
            rec["model_index"] = int(m[1:])
        entities.append(rec)
    spawns = [{"entity": i, "class": e.get("classname"), "team": reader.SPAWN_CLASSES[e.get("classname")],
               "origin": _rv(reader.entity_vec(e)), "yaw": _r(reader.entity_yaw(e))}
              for i, e in enumerate(ents) if e.get("classname") in reader.SPAWN_CLASSES]
    lights = [_light(i, e) for i, e in enumerate(ents) if e.get("classname") in reader.LIGHT_CLASSES]
    props = [{"model": p["model"], "origin": _rv(p["origin"]), "angles": _rv(p["angles"]),
              "solid": p["solid"], "skin": p["skin"], "scale": _r(p["scale"])} for p in bsp.static_props()]

    doc = {
        "format": FORMAT, "version": VERSION,
        "units": {"length": "map units; metres = units * %g" % scale, "metres_per_unit": scale,
                  "axes": "map axes, Z up; Godot = (x, z, -y)", "angles": "degrees (pitch, yaw, roll); yaw about +Z from +X"},
        "source": {"name": name or os.path.splitext(os.path.basename(bsp.path))[0],
                   "file": os.path.basename(bsp.path), "bytes": len(bsp.d),
                   "sha256": hashlib.sha256(bsp.d).hexdigest(), "bsp_version": bsp.version,
                   "revision": bsp.revision},
        "credit": {k: (credit or {}).get(k) for k in CREDIT_KEYS},
        "world": {"mins": models[0]["mins"] if models else [0, 0, 0], "maxs": models[0]["maxs"] if models else [0, 0, 0],
                  "keys": ents[0] if ents and ents[0].get("classname") == "worldspawn" else {}},
        "materials": mats, "models": models, "brushes": brushes,
        "entities": entities, "spawns": spawns, "lights": lights, "static_props": props,
        "counts": {"brushes": len(brushes), "entities": len(entities), "spawns": len(spawns),
                   "lights": len(lights), "static_props": len(props),
                   "displacements": len(bsp.dispinfo) // 176},
    }
    for k, v in (credit or {}).items():
        if k not in CREDIT_KEYS:
            doc["credit"][k] = v
    if faces:
        out = []
        for f in bsp.model_faces(0):
            if f[6] >= 0:
                continue
            mname, flags = bsp.face_material(f)
            pl = bsp.planes[f[0]]
            n = list(pl[:3]) if not f[1] else [-pl[0], -pl[1], -pl[2]]
            out.append({"material": mat(mname), "flags": flags, "normal": _rv(n, 5),
                        "points": [_rv(p) for p in bsp.face_points(f)]})
        doc["faces"] = out
    if displacements:
        doc["displacements"] = [{"material": mat(bsp.face_material(f)[0]),
                                 "tris": [[_rv(p) for p in t] for t in bsp.displacement_tris(f)]}
                                for f in bsp.model_faces(0) if f[6] >= 0]
    return doc


def _box_json(b):
    out = {"x": [_r(b["x"][0]), _r(b["x"][1])], "y": [_r(b["y"][0]), _r(b["y"][1])],
           "z": [_r(b["z"][0]), _r(b["z"][1])], "phi": _r(b["phi"]), "kind": b["kind"]}
    if "ramp" in b:
        out["ramp"] = [b["ramp"][0]] + [_r(v) for v in b["ramp"][1:]]
    return out


def brush_planes(rec):
    """A brush record's planes as tuples, for `boxes.decompose`."""
    return [tuple(s["plane"]) for s in rec["sides"]]


def brush_hull(rec):
    return [tuple(p) for p in rec["hull"]]


def check(doc):
    """Problems with a document a reader is about to trust: [] when it is usable."""
    probs = []
    if doc.get("format") != FORMAT:
        probs.append("format is %r, not %r" % (doc.get("format"), FORMAT))
    if doc.get("version", 0) > VERSION:
        probs.append("version %s is newer than this reader's %d" % (doc.get("version"), VERSION))
    for k in ("materials", "models", "brushes", "entities", "spawns", "lights"):
        if not isinstance(doc.get(k), list):
            probs.append("%s is missing" % k)
    n = len(doc.get("materials", []))
    for b in doc.get("brushes", [])[:100000]:
        for s in b.get("sides", []):
            if not 0 <= s.get("material", -1) < n:
                probs.append("brush %s names material %s of %d" % (b.get("id"), s.get("material"), n))
                return probs
    return probs
