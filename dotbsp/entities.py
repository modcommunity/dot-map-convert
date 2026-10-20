"""What an entity or a brush is, once, and the teleport links between entities.

[b]The split with a game's adapter[/b]: this says what a classname *is* (a spawn, a light, a
door, a button, a prop the mapper placed, a trigger); the game decides what that means for it
(a door is a gate in zombie-zone, a hiding place's door in prop-hunt, scenery in deathrun).
The lists were written out five times in the maps repositories' adapters, each missing
classes the others had (`prop_physics_multiplayer`, `func_door_rotating`, `momentary_rot_button`).
A game that needs another class passes it in `extra`; nothing here is a fork point.

Everything takes the intermediate (`doc`) or one entity's dict of keys, so it runs the same on a
saved JSON as on a map just read.
"""

import math

from . import reader

SPAWN = "spawn"
LIGHT = "light"
PROP = "prop"             # a placed model: dynamic, physics (movable) or a func_physbox
DOOR = "door"
BUTTON = "button"
TELEPORT = "teleport"     # trigger_teleport (the pad) or its destination
TRIGGER = "trigger"
SOLID_BRUSH = "solid_brush"
NONSOLID_BRUSH = "nonsolid_brush"
OTHER = "other"

PROP_CLASSES = frozenset("""
    prop_dynamic prop_dynamic_override prop_physics prop_physics_override
    prop_physics_multiplayer prop_ragdoll prop_static
""".split())
PHYSICS_PROP_CLASSES = frozenset("prop_physics prop_physics_override prop_physics_multiplayer func_physbox func_physbox_multiplayer".split())
DOOR_CLASSES = frozenset("func_door func_door_rotating prop_door_rotating func_movelinear".split())
BUTTON_CLASSES = frozenset("func_button func_rot_button momentary_rot_button".split())
TELEPORT_PADS = frozenset(("trigger_teleport",))
TELEPORT_DESTINATIONS = frozenset(("info_teleport_destination", "point_teleport", "info_target", "info_landmark"))


def classify_entity(e, extra=None):
    """The kind of one entity (its `keys` dict): SPAWN, LIGHT, PROP, DOOR, BUTTON, TELEPORT,
    TRIGGER, SOLID_BRUSH, NONSOLID_BRUSH or OTHER. `extra` maps a classname to a kind and wins."""
    c = e.get("classname", "")
    if extra and c in extra:
        return extra[c]
    if c in reader.SPAWN_CLASSES:
        return SPAWN
    if c in reader.LIGHT_CLASSES:
        return LIGHT
    if c in TELEPORT_PADS or c == "info_teleport_destination":
        return TELEPORT
    if c in DOOR_CLASSES:
        return DOOR
    if c in BUTTON_CLASSES:
        return BUTTON
    if c in PROP_CLASSES or c in PHYSICS_PROP_CLASSES:
        return PROP
    if c.startswith("trigger_"):
        return TRIGGER
    if c in reader.NONSOLID_BRUSH_ENTITIES:
        return NONSOLID_BRUSH
    if c in reader.SOLID_BRUSH_ENTITIES:
        return SOLID_BRUSH
    return OTHER


def classify_all(doc, extra=None):
    """{kind: [entity record, ...]} over a document's entities, in file order."""
    out = {}
    for rec in doc["entities"]:
        out.setdefault(classify_entity(rec["keys"], extra), []).append(rec)
    return out


def unclassified_brush_entities(doc):
    """Sorted classnames of brush entities that are in neither of the reader's lists. The
    reader's rule is that these are reported, not guessed: an invisible wall nobody can explain."""
    seen = set()
    for rec in doc["entities"]:
        if rec.get("model_index") and classify_entity(rec["keys"]) in (OTHER, TRIGGER):
            c = rec["classname"]
            if c not in reader.SOLID_BRUSH_ENTITIES and c not in reader.NONSOLID_BRUSH_ENTITIES and not c.startswith("trigger_"):
                seen.add(c)
    return sorted(seen)


def classify_brush(names, contents):
    """(kind, material) of one world brush from its lowercase material names and contents:
    kind is 'solid', 'invisible' (clips and tools), 'sky' (the world's own box) or 'glass'.

    [b]A brush with only tool textures is not a wall the player sees[/b]: clips and triggers
    are tools/ materials; sky is the six-sided box round the map. `material` is the name of
    the first upward-facing side's material when `names` is a list of (normal_z, name) pairs,
    else of the first real side; the game maps it to its own surface.
    """
    pairs = [(n if isinstance(n, tuple) else (0.0, n)) for n in names]
    real = [(nz, n.lower()) for nz, n in pairs if not n.lower().startswith("tools/")]
    if not real:
        return ("sky" if any("skybox" in n.lower() for _, n in pairs) else "invisible"), None
    if contents & (reader.CONTENTS_PLAYERCLIP | reader.CONTENTS_MONSTERCLIP):
        return "invisible", None
    top = [n for nz, n in real if nz > 0.5]
    name = (top or [n for _, n in real])[0]
    if contents & reader.CONTENTS_WINDOW:
        return "glass", name
    return "solid", name


def classify_brush_record(doc, rec):
    """`classify_brush` for a brush record of the intermediate."""
    mats = doc["materials"]
    return classify_brush([(s["plane"][2], mats[s["material"]]["name"]) for s in rec["sides"]], rec["contents"])


# --- teleports -----------------------------------------------------------------------------

def teleports(doc):
    """Every trigger_teleport resolved to where it sends: a list of
    {entity, model, mins, maxs, origin, target, destination, dest_origin, dest_yaw, landmark}.

    `mins`/`maxs` are the trigger's brush bounds in world units (the document already moved a
    brush entity to its origin). `destination` is the entity record `target` names
    (`info_teleport_destination` first, then any entity with that targetname); None, with
    `dest_origin` None, when the map names one that does not exist, so a game can report it
    rather than crash on a `next()`. A destination may name a `target` of its own (a landmark
    that offsets the player); it is returned as `landmark` and the game decides.
    """
    by_name = {}
    for rec in doc["entities"]:
        n = rec["keys"].get("targetname")
        if n:
            by_name.setdefault(n, []).append(rec)
    models = {m["index"]: m for m in doc["models"]}
    out = []
    for rec in doc["entities"]:
        k = rec["keys"]
        if rec["classname"] not in TELEPORT_PADS:
            continue
        m = models.get(rec.get("model_index"))
        dests = by_name.get(k.get("target", ""), [])
        dests.sort(key=lambda r: r["classname"] != "info_teleport_destination")     # the real class first
        d = dests[0] if dests else None
        item = {"entity": rec["index"], "model": rec.get("model_index"),
                "mins": m["mins"] if m else None, "maxs": m["maxs"] if m else None,
                "origin": rec.get("origin"), "target": k.get("target", ""),
                "destination": d, "dest_origin": None, "dest_yaw": 0.0, "landmark": k.get("landmark") or None}
        if d is not None:
            item["dest_origin"] = reader.entity_vec(d["keys"])
            item["dest_yaw"] = reader.entity_yaw(d["keys"])
            if d["keys"].get("target"):
                item["landmark"] = d["keys"]["target"]
        out.append(item)
    return out


def teleport_destination(doc, model):
    """The (origin, yaw) a trigger_teleport with brush model `model` (an int or "*7") sends to,
    or None when it has no resolvable destination."""
    idx = int(str(model).lstrip("*"))
    for t in teleports(doc):
        if t["model"] == idx and t["dest_origin"] is not None:
            return t["dest_origin"], t["dest_yaw"]
    return None


def pad_rect(t, min_size=48.0):
    """A teleport trigger's footprint (x0, x1, y0, y1) in map units, widened about its centre to
    `min_size`: a trigger the map walks through is a thin wall and a pad wants a stride's width."""
    x0, y0 = t["mins"][0], t["mins"][1]
    x1, y1 = t["maxs"][0], t["maxs"][1]
    if x1 - x0 < min_size:
        x0, x1 = (x0 + x1) / 2 - min_size / 2, (x0 + x1) / 2 + min_size / 2
    if y1 - y0 < min_size:
        y0, y1 = (y0 + y1) / 2 - min_size / 2, (y0 + y1) / 2 + min_size / 2
    return (x0, x1, y0, y1)
