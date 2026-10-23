"""What moves in a map, and what a body feels inside a volume: the brush entities as data.

`mesh.build` draws a door, a button and a lift where they were compiled and makes them solid
there; this says how each moves, so a game can move the model's surfaces and hulls (found by
`model` index in the mesh manifest) and wire a press to what it opens. The source engine runs
these through outputs (`OnPressed` -> `door1,Open`); the outputs that drive another mover are
kept as `{output, target, input, param, delay, times}` records, because "a button opens a
door" and "a button starts the lift" are what the zombie and escape maps are built around, and
a game can run that much without being a scripting engine. Everything else an output does
(relays, counters, text) stays logic, in the intermediate's entity list.

Every length is in game metres, every direction in Godot axes, every angle in degrees, every
speed per second, as in `mesh`. Modelled on game-g2gfast's `tools/bsp_mechanics.py`, which
measured the door, button and conveyor rules over 42 maps; the formulas are the original
engine's (a door travels its size along its direction, less `lip`).

- `movers(bsp)`: one record a moving brush entity (`classes` treatment `mover`).
- `volumes(bsp)`: one record a trigger volume, water and ladder brush (treatment `volume`),
  each with its brushes' planes so a game can test containment exactly.
- `links(bsp)`: the output -> input graph between entities, each end resolved to entity indices.
- `generic(bsp)`: every entity kept as data (logic, unknown classes) with all its keys.
- `paths(bsp)`: the `path_track` chains trains run on.
"""

import fnmatch
import math
import re

from . import reader
from . import units as _units

# spawnflags, as the original engine numbers them
SF_DOOR_START_OPEN = 1
SF_DOOR_PASSABLE = 8
SF_DOOR_TOGGLE = 32
SF_DOOR_USE_OPENS = 256
SF_DOOR_TOUCH_OPENS = 1024
SF_DOOR_LOCKED = 2048
SF_DOOR_SILENT = 4096
SF_ROT_REVERSE = 2
SF_ROT_X = 64
SF_ROT_Y = 128
SF_BUTTON_DONT_MOVE = 1
SF_BUTTON_TOGGLE = 32
SF_BUTTON_TOUCH = 256
SF_BUTTON_LOCKED = 2048
SF_ROTATING_START_ON = 1
SF_ROTATING_REVERSE = 2
SF_ROTATING_X = 4
SF_ROTATING_Y = 8
SF_ROTATING_NOT_SOLID = 64
SF_TRAIN_NOT_SOLID = 8
SF_TRIGGER_CLIENTS = 1

_OUTPUT_SPLIT = re.compile(r"[,\x1b]")


def _f(e, k, d=0.0):
    try:
        return float(str(e.get(k, d)).split()[0])
    except (ValueError, IndexError):
        return d


def _i(e, k, d=0):
    try:
        return int(float(str(e.get(k, d)).split()[0]))
    except (ValueError, IndexError):
        return d


def angle_vector(text):
    """The engine's AngleVectors forward of "pitch yaw roll", in map axes."""
    try:
        p, y = (math.radians(float(v)) for v in str(text).split()[:2])
    except ValueError:
        return (1.0, 0.0, 0.0)
    return (math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), -math.sin(p))


def gdir(v):
    return [round(v[0], 5), round(v[2], 5), round(-v[1], 5)]


def _output_link(key, line):
    parts = _OUTPUT_SPLIT.split(line)
    if len(parts) < 2:
        return None
    parts += [""] * (5 - len(parts))
    try:
        delay = float(parts[3] or 0)
    except ValueError:
        delay = 0.0
    try:
        times = int(float(parts[4] or -1))
    except ValueError:
        times = -1
    return {"output": key, "target": parts[0].strip(), "input": parts[1].strip(),
            "param": parts[2].strip(), "delay": round(delay, 3), "times": times}


def output_shaped(value):
    """True for a value written as `target,input,param,delay,times`: the shape decides, because
    input-capture entities name their outputs `PressedAttack` and counters `OutValue`."""
    parts = _OUTPUT_SPLIT.split(str(value))
    if len(parts) != 5 or not parts[0].strip() or not parts[1].strip():
        return False
    try:
        float(parts[3])
        int(float(parts[4]))
    except ValueError:
        return False
    return True


def outputs(e):
    """Every output of an entity: [{output, target, input, param, delay, times}].

    Keys starting with `On` first, as always; then, from the ordered pairs, any other key whose
    value has the output shape (repeats included).
    """
    out = []
    for k, v in e.items():
        if not k.startswith("On"):
            continue
        for line in str(v).split("\n"):
            rec = _output_link(k, line)
            if rec:
                out.append(rec)
    for k, v in getattr(e, "pairs", ()):
        if not k.startswith("On") and output_shaped(v):
            out.append(_output_link(k, v))
    return out


def _model_size(bsp, mi):
    lo, hi = bsp.model_bounds(mi)
    return [hi[k] - lo[k] for k in range(3)], lo, hi


def _travel(size, d, lip):
    """How far a door or button moves along unit `d` (map units): its size that way, less lip.
    The engine's formula, `|dx|(sx-2) + |dy|(sy-2) + |dz|(sz-2) - lip`."""
    return max(0.0, sum(abs(d[k]) * (size[k] - 2.0) for k in range(3)) - lip)


def _movedir(e):
    """A door's or button's direction: `movedir` when written, else its `angles`; the
    compiler's special values -1 and -2 of the yaw-only `angle` key are up and down."""
    if "movedir" in e:
        return angle_vector(e["movedir"])
    a = _f(e, "angle", 0.0) if "angle" in e else None
    if a == -1:
        return (0.0, 0.0, 1.0)
    if a == -2:
        return (0.0, 0.0, -1.0)
    if a is not None:
        return angle_vector("0 %g 0" % a)
    return angle_vector(e.get("angles", "0 0 0"))


def _rot_axis(e, flags, x_flag, y_flag):
    if flags & x_flag:
        axis = (1.0, 0.0, 0.0)            # roll: about the map's X
    elif flags & y_flag:
        axis = (0.0, 1.0, 0.0)            # pitch: about the map's Y
    else:
        axis = (0.0, 0.0, 1.0)            # yaw: about up
    return axis


def touch_opens(e):
    """Whether walking into a door opens it. The original's func_door spawnflag 1024 is
    "touch opens" (not set: only use and inputs open it), and a named door with no flag
    waits for an input."""
    return bool(_i(e, "spawnflags") & SF_DOOR_TOUCH_OPENS)


def movers(bsp, scale=_units.VISUAL, y0=0.0, owners=None):
    """One record per moving brush entity (and per prop_door_rotating, which has no model)."""
    from . import mesh
    owners = owners if owners is not None else mesh.model_entities(bsp)
    by_entity = {ei: mi for mi, ei in owners.items()}
    named = {}
    for i, e in enumerate(bsp.entities):
        if e.get("targetname"):
            named.setdefault(e["targetname"].lower(), []).append(i)

    def g(p):
        return [round(p[0] * scale, 4), round(p[2] * scale - y0, 4), round(-p[1] * scale, 4)]

    out = []
    for i, e in enumerate(bsp.entities):
        cls = e.get("classname", "")
        mi = by_entity.get(i)
        if cls not in KINDS:
            continue
        flags = _i(e, "spawnflags")
        origin = reader.entity_vec(e)
        rec = {"entity": i, "model": mi, "classname": cls, "targetname": e.get("targetname", ""),
               "kind": KINDS[cls], "origin": g(origin), "spawnflags": flags,
               "speed": round(_f(e, "speed", 100.0) * scale, 4), "outputs": outputs(e)}
        size = lo = hi = None
        if mi is not None and 0 <= mi < len(bsp.models):
            size, lo, hi = _model_size(bsp, mi)
            a, b = g([lo[k] + origin[k] for k in range(3)]), g([hi[k] + origin[k] for k in range(3)])
            rec["mins"], rec["maxs"] = [min(a[k], b[k]) for k in range(3)], [max(a[k], b[k]) for k in range(3)]
        if cls in ("func_door", "func_button"):
            d = _movedir(e)
            dist = _travel(size, d, _f(e, "lip")) if size else 0.0
            if cls == "func_button" and flags & SF_BUTTON_DONT_MOVE:
                dist = 0.0
            rec.update(direction=gdir(d), distance=round(dist * scale, 4), wait=_f(e, "wait", 4 if cls == "func_door" else 1),
                       start_open=bool(cls == "func_door" and flags & SF_DOOR_START_OPEN),
                       locked=bool(flags & (SF_DOOR_LOCKED if cls == "func_door" else SF_BUTTON_LOCKED)),
                       toggle=bool(flags & SF_DOOR_TOGGLE), use=bool(flags & SF_DOOR_USE_OPENS) if cls == "func_door" else True,
                       touch=touch_opens(e) if cls == "func_door" else bool(flags & SF_BUTTON_TOUCH),
                       solid=not (cls == "func_door" and flags & SF_DOOR_PASSABLE))
        elif cls in ("func_door_rotating", "func_rot_button", "momentary_rot_button", "prop_door_rotating"):
            axis = _rot_axis(e, flags, SF_ROT_X, SF_ROT_Y)
            dist = _f(e, "distance", 90.0)
            start_open = bool(flags & SF_DOOR_START_OPEN)
            if cls == "prop_door_rotating":
                # Flag 2 is not "reverse" on a model door; its direction is opendir (0 away from the
                # opener, 1 forward, 2 back) and spawnpos (1 open forward, 2 open back at the start).
                axis = (0.0, 0.0, 1.0)
                rec["model_path"] = e.get("model", "")
                open_dir = _i(e, "opendir")
                spawn = _i(e, "spawnpos")
                dist = abs(dist)
                if open_dir == 2:
                    dist = -dist
                ang = e.get("angles", "").split()
                rec["open_dir"] = open_dir if open_dir in (0, 1, 2) else 0
                rec["yaw"] = _f({"a": ang[1]}, "a") if len(ang) > 1 else 0.0
                if spawn in (1, 2):
                    rec["spawn_side"] = 1.0 if spawn == 1 else -1.0
                start_open = start_open or spawn in (1, 2)
            elif flags & SF_ROT_REVERSE:
                dist = -dist
            rec.update(axis=gdir(axis), degrees=round(dist, 3), wait=_f(e, "wait", 4),
                       speed=round(_f(e, "speed", 100.0), 3), start_open=start_open,
                       locked=bool(flags & SF_DOOR_LOCKED), use=True, touch=False, solid=True)
        elif cls == "func_movelinear":
            d = angle_vector(e.get("movedir", "0 0 0"))
            rec.update(direction=gdir(d), distance=round(_f(e, "movedistance", 100.0) * scale, 4),
                       start_position=round(_f(e, "startposition"), 3), solid=True)
        elif cls == "func_rotating":
            axis = _rot_axis(e, flags, SF_ROTATING_X, SF_ROTATING_Y)
            sp = _f(e, "maxspeed", 100.0)
            rec.update(axis=gdir(axis), degrees_per_second=round(-sp if flags & SF_ROTATING_REVERSE else sp, 3),
                       start_on=bool(flags & SF_ROTATING_START_ON), solid=not flags & SF_ROTATING_NOT_SOLID)
            rec.pop("speed")
            if _f(e, "fanfriction") > 0:
                rec["fan_friction"] = round(_f(e, "fanfriction"), 3)
        elif cls in ("func_tracktrain", "func_tanktrain", "func_train"):
            rec.update(path=chain(bsp, e.get("target", ""), named, g, scale), solid=not flags & SF_TRAIN_NOT_SOLID,
                       start_speed=round(_f(e, "startspeed", 0.0) * scale, 4),
                       height=round(_f(e, "height", 0.0) * scale, 4))
        elif cls in ("func_plat", "func_platrot"):
            h = _f(e, "height", 0.0) or ((size[2] - 8.0) if size else 0.0)
            rec.update(direction=[0.0, -1.0, 0.0], distance=round(h * scale, 4), solid=True)
        elif cls == "func_conveyor":
            d = angle_vector(e.get("movedir", "0 0 0"))
            rec.update(direction=gdir(d), carries=not flags & 1, solid=not flags & 2)
        _travel_time(rec)
        if cls in ("func_door", "func_button"):
            rec["lip"] = round(_f(e, "lip") * scale, 4)
        rec["opened_by"] = []
        out.append(rec)
    # Who drives whom: an output of any entity whose target is a mover's name.
    by_name = {}
    for r in out:
        if r["targetname"]:
            by_name.setdefault(r["targetname"].lower(), []).append(r)
    for i, e in enumerate(bsp.entities):
        for o in outputs(e):
            for r in by_name.get(o["target"].lower(), ()):
                r["opened_by"].append({"entity": i, "classname": e.get("classname", ""),
                                       "targetname": e.get("targetname", ""), "output": o["output"],
                                       "input": o["input"], "delay": o["delay"]})
    return out


def _travel_time(rec):
    """Seconds one full travel takes: a slide's distance over its speed, a hinge's degrees over
    its degrees a second; 0 for what does not travel."""
    t = 0.0
    if "degrees" in rec and rec.get("speed"):
        t = abs(rec["degrees"]) / rec["speed"]
    elif "distance" in rec and rec.get("speed"):
        t = rec["distance"] / rec["speed"]
    rec["travel_time"] = round(t, 4)


KINDS = {
    "func_door": "slide", "func_button": "button", "func_door_rotating": "rotate",
    "func_rot_button": "rotate_button", "momentary_rot_button": "rotate_button",
    "prop_door_rotating": "rotate", "func_movelinear": "slide", "func_rotating": "spin",
    "func_tracktrain": "path", "func_tanktrain": "path", "func_train": "path",
    "func_plat": "plat", "func_platrot": "plat", "func_conveyor": "conveyor",
}


def chain(bsp, first, named, g, scale=_units.VISUAL, limit=512):
    """The corners of a path from `path_track` named `first`, following `target`, as
    [{name, at, speed?, wait?}]; stops at a loop (marked `loop`) or a missing corner."""
    out, seen = [], set()
    name = first
    while name and len(out) < limit:
        ids = named.get(name.lower())
        if not ids:
            break
        e = bsp.entities[ids[0]]
        if name.lower() in seen:
            out.append({"loop": name})
            break
        seen.add(name.lower())
        c = {"name": name, "at": g(reader.entity_vec(e))}
        if _f(e, "speed"):
            c["speed"] = round(_f(e, "speed") * scale, 4)
        out.append(c)
        name = e.get("target", "")
    return out


VOLUME_KINDS = {"trigger_multiple": "multiple", "trigger_once": "once", "trigger_teleport": "teleport", "trigger_push": "push", "trigger_hurt": "hurt",
                "trigger_gravity": "gravity", "func_water_analog": "water", "func_water": "water",
                "func_ladder": "ladder", "trigger_soundscape": "soundscape"}


def volumes(bsp, scale=_units.VISUAL, y0=0.0, owners=None):
    """One record per trigger volume, water brush and ladder: kind, its keys that matter, and
    its brushes as plane lists (n.p <= d inside, metres, Godot axes)."""
    from . import mesh
    owners = owners if owners is not None else mesh.model_entities(bsp)

    def planes(bi, off):
        return [[round(nx, 6), round(nz, 6), round(-ny, 6), round(d * scale - nz * y0, 5)]
                for nx, ny, nz, d in bsp.brush_planes(bi, off)]

    out = []
    for mi, ei in sorted(owners.items()):
        e = bsp.entities[ei]
        kind = VOLUME_KINDS.get(e.get("classname", ""))
        if kind is None or not 0 < mi < len(bsp.models):
            continue
        off = reader.entity_vec(e)
        rec = {"entity": ei, "model": mi, "classname": e["classname"], "kind": kind,
               "targetname": e.get("targetname", ""), "spawnflags": _i(e, "spawnflags"),
               "disabled": str(e.get("StartDisabled", "0")).strip() == "1", "outputs": outputs(e),
               "brushes": [planes(bi, off) for bi in sorted(bsp.model_brushes(mi)) if bi < len(bsp.brushes)]}
        if kind in ("multiple", "once"):
            rec["wait"] = -1.0 if kind == "once" else _f(e, "wait", 1.0)
            rec["filter"] = e.get("filtername", "")
        elif kind == "teleport":
            rec["target"] = e.get("target", "")
            rec["filter"] = e.get("filtername", "")
        elif kind == "push":
            rec["direction"] = gdir(angle_vector(e.get("pushdir", "0 0 0")))
            rec["speed"] = round(_f(e, "speed", 40.0) * scale, 4)
        elif kind == "hurt":
            rec["damage"] = _f(e, "damage", 10.0)
        elif kind == "gravity":
            rec["gravity"] = _f(e, "gravity", 1.0)
        out.append(rec)
    # World brushes compiled with water or ladder contents (most water is these).
    for bi in sorted(bsp.model_brushes(0)):
        if bi >= len(bsp.brushes):
            continue
        c = bsp.brushes[bi][2]
        kind = "water" if c & (reader.CONTENTS_WATER | reader.CONTENTS_SLIME) else "ladder" if c & reader.CONTENTS_LADDER else None
        if kind:
            out.append({"entity": None, "model": 0, "classname": "worldspawn", "kind": kind, "brush": bi,
                        "slime": bool(c & reader.CONTENTS_SLIME), "brushes": [planes(bi, (0.0, 0.0, 0.0))]})
    return out


_SPECIAL = ("!activator", "!caller", "!self", "!player", "!picker")


def _resolve(target, named, classes):
    """The entities a target names: an exact name, else a `*` wildcard over names, else a class name (the engine does all three)."""
    if target in named:
        return named[target]
    if "*" in target:
        return sorted(i for n, ids in named.items() if fnmatch.fnmatchcase(n, target) for i in ids)
    return classes.get(target, [])


def links(bsp):
    """Every output as a graph edge: the output's record plus `from` (entity index), `from_name`
    and `to`, the entity indices its target names (empty for a `!activator`-style special, which
    is flagged `special`, or for a name nothing carries)."""
    named = {}
    for i, e in enumerate(bsp.entities):
        if e.get("targetname"):
            named.setdefault(e["targetname"].lower(), []).append(i)
    classes = {}
    for i, e in enumerate(bsp.entities):
        classes.setdefault(e.get("classname", "").lower(), []).append(i)
    out = []
    for i, e in enumerate(bsp.entities):
        for o in outputs(e):
            t = o["target"].lower()
            rec = dict(o)
            rec.update({"from": i, "from_name": e.get("targetname", ""), "from_class": e.get("classname", ""),
                        "to": _resolve(t, named, classes), "special": t in _SPECIAL or t.startswith("!")})
            out.append(rec)
    return out


def generic(bsp, owners=None):
    """Entities kept as data: treatment `data` or undecided. {entity, classname, targetname,
    target, origin, model, treatment, keys}; `keys` is every key but the outputs and origin."""
    from . import classes, mesh
    owners = owners if owners is not None else mesh.model_entities(bsp)
    by_entity = {ei: mi for mi, ei in owners.items()}
    k = _units.VISUAL
    out = []
    for i, e in enumerate(bsp.entities):
        cls = e.get("classname", "")
        t = classes.treatment(cls)[0]
        if t not in (None, "data"):
            continue
        p = reader.entity_vec(e)
        out.append({"entity": i, "classname": cls, "targetname": e.get("targetname", ""),
                    "target": e.get("target", ""), "model": by_entity.get(i),
                    "origin": [round(p[0] * k, 4), round(p[2] * k, 4), round(-p[1] * k, 4)],
                    "treatment": t or "unknown",
                    "keys": {a: str(v) for a, v in e.items() if not a.startswith("On") and a not in ("origin", "classname")}})
    return out


def spawns(bsp, scale=_units.VISUAL, y0=0.0):
    """Every player spawn the source places: {classname, team, targetname, at, yaw}. The game picks
    which team a class is for; `team` is the reader's default reading of the class name."""
    out = []
    for e in bsp.entities:
        c = e.get("classname", "")
        team = reader.SPAWN_CLASSES.get(c)
        if team is None and c.startswith("info_player_"):
            team = "any"
        if team is None:
            continue
        p = reader.entity_vec(e)
        out.append({"classname": c, "team": team, "targetname": e.get("targetname", ""),
                    "at": [round(p[0] * scale, 4), round(p[2] * scale - y0, 4), round(-p[1] * scale, 4)],
                    "yaw": round(reader.yaw_to_godot(reader.entity_yaw(e)), 3)})
    return out


PICKUP_PATTERNS = ("weapon_*", "item_*", "ammo_*")


def pickups(bsp, scale=_units.VISUAL, y0=0.0):
    """Weapons, items and ammunition the source lays in the map, as the entity dictionaries
    dot-weapon's `DotWeaponSpawner.add_entities` takes: {classname, origin, angle, props}. What each
    one gives is the game's `classes:` mapping in its spawner.yml, never decided here; a class
    the source marks `dropped` (a bomb defuser) is not a pickup."""
    import fnmatch
    from . import classes
    out = []
    for e in bsp.entities:
        c = e.get("classname", "")
        if not any(fnmatch.fnmatchcase(c, pat) for pat in PICKUP_PATTERNS) or classes.treatment(c)[0] != "point":
            continue
        p = reader.entity_vec(e)
        out.append({"classname": c, "origin": [round(p[0] * scale, 4), round(p[2] * scale - y0, 4), round(-p[1] * scale, 4)],
                    "angle": round(reader.yaw_to_godot(reader.entity_yaw(e)), 3),
                    "props": {"targetname": e["targetname"]} if e.get("targetname") else {}})
    return out


def destinations(bsp, scale=_units.VISUAL, y0=0.0):
    """{name: {at, yaw}} of every point a teleport may send a body to."""
    out = {}
    for e in bsp.entities:
        if e.get("classname") in ("info_teleport_destination", "info_target", "info_landmark", "point_teleport") and e.get("targetname"):
            p = reader.entity_vec(e)
            out.setdefault(e["targetname"], {"at": [round(p[0] * scale, 4), round(p[2] * scale - y0, 4), round(-p[1] * scale, 4)],
                                             "yaw": round(reader.yaw_to_godot(reader.entity_yaw(e)), 3)})
    return out
