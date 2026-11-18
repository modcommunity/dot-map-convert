"""Gameplay fidelity: does the converted map do everything the original did?

Textures and models may be stood in for; what a map *does* may not change. This compares the
original's entity graph, read the way the original engine reads it, with what the converter
records and the DotMapIO runtime runs, and names every difference as a finding class:

    findings(bsp) -> {"findings": {class: [detail, ...]}, "classes": {classname: status}, ...}

The reference reading (`reference_entities`) is the engine's, not the converter's: quote-aware
(a value may hold braces), a repeated key's LAST value wins (the converter's dict keeps the
first; `pairs` keeps all), key names and entity names compare case-insensitively, an output
value splits on ESC when it holds one and on commas otherwise, and a key is an output when the
class's definition says so (any case), as well as by the converter's own rules.

Each finding class is in `FINDINGS` with its severity: `lost` (gameplay the original had does
not happen), `changed` (it happens differently), `unsupported` (the class or input is not
implemented and the map uses it), `source` (the original itself is broken there; nothing to
convert, listed so nobody chases it), `handled` (a construct the runtime runs as the engine does,
counted so the audit shows how often it matters). A class of entity is `implemented`, `approximated`,
`ignored` or `unknown` (`class_status`). `gameplay_lost` (coverage list, ratcheted) is the
sorted `class:detail` strings of every `lost`/`changed`/`unsupported` finding.
"""

import collections
import fnmatch
import json
import os
import re

from . import classes as _classes
from . import inputs as _inputs
from . import movers, reader

DEFS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules", "entity_defs.json")

# class -> (severity, what it means)
FINDINGS = {
    "entity_misparsed": ("lost", "the converter's entity count or key pairs differ from the engine's reading (a value holding a brace)"),
    "output_lost": ("lost", "an output the engine fires that the converter does not record"),
    "output_mangled": ("changed", "an output recorded with a different target, input, parameter, delay or count (ESC-separated value holding commas)"),
    "repeat_key_first": ("changed", "a repeated gameplay key: the converter's records use the first value, the engine the last"),
    "key_case": ("lost", "a gameplay key written in another case (`Target`) that the converter's records do not see"),
    "teleport_dest_lost": ("lost", "a trigger_teleport whose destination the engine finds and the runtime does not (class, case or name)"),
    "teleport_dest_moved": ("changed", "a trigger_teleport sent to another place than the engine sends it (duplicate names, first vs last)"),
    "teleport_retargeted": ("changed", "the converter's release_pits heuristic re-aimed a teleport the author wired elsewhere"),
    "teleport_target_dynamic": ("handled", "a trigger_teleport whose target logic changes at run time (AddOutput target / SetRemoteDestination); DotMapTeleport re-aims it as the engine does"),
    "teleport_landmark_lost": ("lost", "a landmark the engine resolves that the runtime's destinations lack"),
    "teleport_landmark_angles": ("handled", "UseLandmarkAngles: DotMapVolumeNode snaps the body to the destination's yaw as the engine does"),
    "filter_dropped": ("lost", "a filtername on a volume kind whose record drops it (everyone passes)"),
    "filter_class_unsupported": ("unsupported", "a filter class the runtime does not evaluate (admits everyone)"),
    "volume_unrecorded": ("lost", "a trigger/volume brush entity with no volume record (nothing touches it)"),
    "volume_empty": ("lost", "a volume record with no brushes (its model has none the tree reaches)"),
    "volume_parented": ("unsupported", "a volume parented to a moving entity; the volume stays where it was compiled"),
    "volume_key_unread": ("unsupported", "a gameplay key on a volume the runtime does not apply"),
    "mover_unrecorded": ("lost", "a moving brush entity with no mover record"),
    "class_unsupported": ("unsupported", "a gameplay class (wired by outputs, or a trigger/logic/filter/game class) with no runtime component"),
    "class_unknown": ("unsupported", "a class nobody decided about (no classes.tsv row)"),
    "input_unimplemented": ("unsupported", "an input sent to an entity whose component does not implement it"),
    "player_input": ("unsupported", "an input sent to the player (!activator/!player): the game's actor must implement it"),
    "spawn_lost": ("lost", "a player spawn the converter does not record"),
    "model_missing": ("lost", "a brush entity naming a model the map does not have"),
    "target_dangling": ("source", "an output target no entity carries (the original does nothing there either)"),
    "parent_dangling": ("source", "a parentname no entity carries"),
    "filter_dangling": ("source", "a filtername no entity carries (the engine admits everyone)"),
    "teleport_dangling": ("source", "a trigger_teleport target no entity carries (the engine does nothing)"),
}
SEVERE = ("lost", "changed", "unsupported")

# Keys the converter's records read by exact name.
RECORD_KEYS = ("classname", "targetname", "target", "parentname", "filtername", "origin", "angles", "model",
               "spawnflags", "StartDisabled", "wait", "speed", "pushdir", "damage", "gravity", "landmark")
# Gameplay keys per volume class the runtime applies (DotMapVolumeNode/DotMapTrigger/DotMapHurt/DotMapPush).
# Anything else a definition lists for the class and the map sets off its default is `volume_key_unread`.
VOLUME_KEYS_READ = {
    "*": {"classname", "targetname", "target", "parentname", "filtername", "origin", "angles", "model", "spawnflags",
          "startdisabled", "wait", "hammerid", "globalname", "rendermode", "renderamt", "rendercolor", "renderfx",
          "disablereceiveshadows", "disableshadows", "vrad_brush_cast_shadows", "_minlight", "solid",
          "origin_x", "texturescroll", "fadescale", "mindxlevel", "maxdxlevel", "inputfilter", "invert_exclusion",
          "spawnflags_", "damagefilter", "speed", "pushdir", "damage", "gravity", "landmark", "damagetype"},
    # DotMapHurt._configure: rate, cap, doubling model, one-shot damage and knockback.
    "trigger_hurt": {"hurtrate", "damagecap", "damagemodel", "damageonce", "damageforce", "nodmgforce"},
}


def volume_keys_read(cls):
    """Keys the runtime reads for one volume class: the shared set plus the class's own."""
    return VOLUME_KEYS_READ["*"] | VOLUME_KEYS_READ.get(cls.lower(), set())
FILTERS_IMPLEMENTED = ("filter_activator_name", "filter_activator_class", "filter_activator_team", "filter_damage_type",
                       "filter_multi")
SPECIAL = ("!activator", "!player", "!caller", "!self", "!picker", "!pvsplayer", "!speechtarget")
GAMEPLAY_PREFIXES = ("trigger_", "func_door", "func_button", "func_rot_button", "momentary_", "func_movelinear",
                     "func_tracktrain", "func_train", "func_tanktrain", "func_rotating", "func_conveyor", "func_brush",
                     "func_wall_toggle", "func_breakable", "func_physbox", "func_pushable", "func_plat", "func_water",
                     "func_ladder", "logic_", "math_", "filter_", "game_", "point_teleport", "point_servercommand",
                     "point_clientcommand", "point_template", "env_entity_maker", "player_", "info_teleport_destination",
                     "info_player_", "path_track", "path_corner", "prop_door_rotating", "func_tank", "env_explosion",
                     "point_hurt", "env_laser", "env_fire", "point_push", "env_global", "info_landmark", "func_buyzone",
                     "func_bomb_target", "func_hostage_rescue", "func_clip_vphysics", "func_movelinear", "func_monitor",
                     "point_viewcontrol", "env_shake", "env_fade", "func_nogrenades", "func_respawnroom", "func_regenerate")
TELEPORT_DESTINATION_CLASSES = ("info_teleport_destination", "info_target", "info_landmark", "point_teleport")



# -- the engine's reading ---------------------------------------------------------------------

def reference_entities(text):
    """[[ (key, value), ... ], ...]: every entity's pairs in file order, quote-aware (the reader's own, which follows the engine)."""
    return reader.entity_pairs(text)


class Ref:
    """One entity as the engine holds it: keys lowercased, last value wins; outputs by definition."""

    __slots__ = ("pairs", "k", "cls")

    def __init__(self, pairs):
        self.pairs = pairs
        self.k = {}
        for a, v in pairs:
            self.k[a.lower()] = v
        self.cls = self.k.get("classname", "").lower()

    def get(self, key, default=""):
        return self.k.get(key.lower(), default)


_DEFS = None


def _defs():
    global _DEFS
    if _DEFS is None:
        try:
            with open(DEFS, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {"classes": {}, "bases": {}}
        _DEFS = (d.get("classes", {}), d.get("bases", {}), {})
    return _DEFS


def class_outputs(cls):
    """Lowercase output names a class's definition (with its bases) declares."""
    cl, bases, memo = _defs()
    if cls in memo:
        return memo[cls]
    out, seen, stack = set(), set(), [cl.get(cls)]
    while stack:
        d = stack.pop()
        if not d:
            continue
        out |= {o.lower() for o in d.get("outputs", {})}
        for b in d.get("bases", []):
            if b not in seen:
                seen.add(b)
                stack.append(bases.get(b))
    memo[cls] = out
    return out


def split_output(value):
    """The engine's split: ESC when the value holds one, else commas. None when not two fields."""
    parts = value.split("\x1b") if "\x1b" in value else value.split(",")
    if len(parts) < 2:
        return None
    parts += [""] * (5 - len(parts))
    try:
        delay = round(float(parts[3] or 0), 3)
    except ValueError:
        delay = 0.0
    try:
        times = int(float(parts[4] or -1))
    except ValueError:
        times = -1
    return (parts[0].strip(), parts[1].strip(), parts[2].strip(), delay, times)


def reference_outputs(r):
    """[(output lowercase, target, input, param, delay, times)] the engine would build for one entity."""
    declared = class_outputs(r.cls)
    out = []
    for k, v in r.pairs:
        kl = k.lower()
        if kl.startswith("on") or kl in declared or movers.output_shaped(v):
            o = split_output(v)
            if o and o[0] and o[1]:
                out.append((kl,) + o)
    return out


# -- classification --------------------------------------------------------------------------

def gameplay_class(cls):
    return cls.startswith(GAMEPLAY_PREFIXES)


def class_status(cls, wired=False, recorded=False):
    """implemented | approximated | ignored | unknown, for one class (wired: it sends or receives outputs)."""
    t = _classes.treatment(cls)[0]
    comp = _classes.component(cls)
    if t is None:
        return "unknown"
    if comp != "DotMapEntity" or t in ("world", "drawn") or recorded:
        return "implemented"
    if t == "dropped":
        return "ignored" if not wired else "approximated"
    if t in ("volume", "mover"):
        return "approximated"
    if t == "point":
        return "implemented" if not wired else "approximated"
    return "approximated" if wired else "ignored"


# -- the audit -------------------------------------------------------------------------------

def findings(bsp):
    """Every finding of one loaded map. See the module docstring."""
    text = bsp._lump(reader.LUMP_ENTITIES).decode("ascii", "replace")
    refs = [Ref(p) for p in reference_entities(text)]
    conv = bsp.entities
    f = collections.defaultdict(list)

    def add(kind, detail):
        f[kind].append(detail)

    # 1. the converter's entity list against the engine's
    if len(refs) != len(conv) or any(list(r.pairs) != list(c.pairs) for r, c in zip(refs, conv)):
        add("entity_misparsed", "engine %d entities, converter %d" % (len(refs), len(conv)))
        aligned = False
    else:
        aligned = True
    if not aligned:
        # Later per-entity comparisons need one index space; the converter's is what the runtime runs.
        refs = [Ref(list(c.pairs)) for c in conv]

    named = collections.defaultdict(list)
    for i, r in enumerate(refs):
        n = r.get("targetname")
        if n:
            named[n.lower()].append(i)
    by_class = collections.defaultdict(list)
    for i, r in enumerate(refs):
        by_class[r.cls].append(i)

    def resolve(t):
        t = t.lower()
        if t in named:
            return named[t]
        if "*" in t:
            return sorted(i for n, ids in named.items() if fnmatch.fnmatchcase(n, t) for i in ids)
        return by_class.get(t, [])

    # 2. outputs: engine's vs converter's
    conv_links = movers.links(bsp)
    conv_out = collections.defaultdict(collections.Counter)
    for k in conv_links:
        conv_out[k["from"]][(k["output"].lower(), k["target"], k["input"], k["param"], k["delay"], k["times"])] += 1
    wired = set()
    ref_links = []
    for i, r in enumerate(refs):
        ro = collections.Counter(reference_outputs(r))
        co = conv_out.get(i, collections.Counter())
        for o, n in (ro - co).items():
            loose = [c for c in co if c[0] == o[0] and c[1].lower() == o[1].lower() and c[2].lower() == o[2].lower()]
            kind = "output_mangled" if loose else "output_lost"
            add(kind, "%s#%d %s -> %s.%s(%s)" % (r.cls, i, o[0], o[1], o[2], o[3][:40]))
        for o in ro.elements():
            ref_links.append((i, o))
            if o[1]:
                wired.add(i)
    special_inputs = collections.Counter()
    for i, o in ref_links:
        t = o[1].lower()
        if t.startswith("!"):
            if t in ("!activator", "!player", "!pvsplayer", "!picker"):
                inp = o[2].lower()
                if inp == "addoutput":
                    inp += " " + (o[3].split(" ", 1)[0].split(":", 1)[0].lower() if o[3] else "")
                special_inputs[inp] += 1
            continue
        ids = resolve(t)
        if not ids:
            if t not in ("player", "worldspawn"):
                add("target_dangling", "%s -> %s" % (refs[i].cls, o[1]))
            continue
        wired.update(ids)
    for inp, n in sorted(special_inputs.items()):
        add("player_input", "%s x%d" % (inp, n))
    for u in _inputs.unimplemented(bsp, conv_links):
        add("input_unimplemented", u)

    # 3. keys: case and repeats on the keys the converter's records read
    for i, (r, c) in enumerate(zip(refs, conv)):
        if not (gameplay_class(r.cls) or _classes.treatment(r.cls)[0] in ("volume", "mover")):
            continue
        for k in RECORD_KEYS:
            if k not in c and k.lower() in r.k and any(a.lower() == k.lower() for a, _v in r.pairs):
                add("key_case", "%s#%d %s" % (r.cls, i, next(a for a, _v in r.pairs if a.lower() == k.lower())))
            elif k in c and str(c[k]) != r.get(k):
                if any(a.lower() == k.lower() for a, _v in r.pairs[1:]) and not k.startswith("On"):
                    add("repeat_key_first", "%s#%d %s: %r vs %r" % (r.cls, i, k, str(c[k])[:30], r.get(k)[:30]))

    # 4. volumes, movers, spawns
    from . import mesh
    owners = mesh.model_entities(bsp)
    vols = movers.volumes(bsp, owners=owners)
    vol_by = {v["entity"]: v for v in vols if v.get("entity") is not None}
    try:
        mov_by = {m["entity"]: m for m in movers.movers(bsp, owners=owners)}
    except (KeyError, IndexError, ValueError, ZeroDivisionError) as ex:
        mov_by = {}
        add("mover_unrecorded", "movers() failed: %s" % ex)
    nmodels = len(bsp.models)
    for i, r in enumerate(refs):
        m = r.get("model")
        if m.startswith("*") and m[1:].isdigit() and int(m[1:]) >= nmodels:
            add("model_missing", "%s#%d %s" % (r.cls, i, m))
        t = _classes.treatment(r.cls)[0]
        if t == "volume" and i not in vol_by and m.startswith("*"):
            add("volume_unrecorded", "%s#%d %s" % (r.cls, i, r.get("targetname")))
        if t == "mover" and i not in mov_by and (m.startswith("*") or r.cls.startswith("prop_door")):
            add("mover_unrecorded", "%s#%d %s" % (r.cls, i, r.get("targetname")))
    for v in vols:
        if v.get("entity") is None:
            continue
        r = refs[v["entity"]]
        if not v.get("brushes"):
            add("volume_empty", "%s#%d %s" % (r.cls, v["entity"], r.get("targetname")))
        if r.get("parentname"):
            p = resolve(r.get("parentname").split(",")[0])
            if p and any(refs[j].cls != "info_target" for j in p):
                add("volume_parented", "%s#%d -> %s" % (r.cls, v["entity"], r.get("parentname")))
        fn = r.get("filtername")
        if fn and str(v.get("filter", "")).lower() != fn.lower():
            add("filter_dropped", "%s#%d (%s) filter %s" % (r.cls, v["entity"], v["kind"], fn))
        read = volume_keys_read(r.cls)
        for a, val in r.k.items():
            if a not in read and not a.startswith("on") and a not in class_outputs(r.cls):
                gk = _volume_gameplay_keys(r.cls)
                if a in gk and _num(val) != _num(gk[a]):
                    add("volume_key_unread", "%s.%s=%s" % (r.cls, a, val[:20]))
    # filters
    for i, r in enumerate(refs):
        fn = r.get("filtername") or r.get("damagefilter")
        if not fn:
            continue
        ids = resolve(fn)
        if not ids:
            add("filter_dangling", "%s#%d %s" % (r.cls, i, fn))
            continue
        for j in ids:
            fc = refs[j].cls
            if fc.startswith("filter_") and fc not in FILTERS_IMPLEMENTED:
                add("filter_class_unsupported", fc)
    # spawns
    nsp = sum(1 for r in refs if r.cls in reader.SPAWN_CLASSES or r.cls.startswith("info_player_"))
    got = len(movers.spawns(bsp))
    if got < nsp:
        add("spawn_lost", "engine %d spawns, converter %d" % (nsp, got))

    # 5. teleports
    dests = movers.destinations(bsp)
    dynamic = set()
    for i, o in ref_links:
        inp = o[2].lower()
        if inp == "setremotedestination" or (inp == "addoutput" and o[3].lower().startswith(("target ", "target:", "landmark "))):
            for j in resolve(o[1]) if not o[1].startswith("!") else []:
                if refs[j].cls == "trigger_teleport":
                    dynamic.add(j)
    for j in sorted(dynamic):
        add("teleport_target_dynamic", "trigger_teleport#%d %s" % (j, refs[j].get("targetname")))
    for v in vols:
        if v.get("kind") != "teleport":
            continue
        i = v["entity"]
        r = refs[i]
        t = r.get("target")
        if v.get("retargeted_from"):
            add("teleport_retargeted", "#%d %s -> %s" % (i, v["retargeted_from"], v["target"]))
        if not t:
            continue
        ids = resolve(t)
        if not ids:
            add("teleport_dangling", "#%d %s" % (i, t))
            continue
        want = reader.entity_vec(_as_entity(refs[ids[0]]))
        rec_t = v.get("retargeted_from") or v.get("target", "")
        d = dests.get(rec_t)
        if d is None:
            add("teleport_dest_lost", "#%d %s (%s)" % (i, t, refs[ids[0]].cls))
        else:
            src = list(want)
            got_at = _from_godot(d["at"])
            if max(abs(a - b) for a, b in zip(src, got_at)) > 1.0:
                add("teleport_dest_moved", "#%d %s engine %s runtime %s" % (i, t, [round(x) for x in src], [round(x) for x in got_at]))
        lm = r.get("landmark")
        if lm:
            if not resolve(lm):
                add("teleport_dangling", "#%d landmark %s" % (i, lm))
            elif lm not in dests:
                add("teleport_landmark_lost", "#%d %s" % (i, lm))
            if r.get("uselandmarkangles") not in ("", "0"):
                add("teleport_landmark_angles", "#%d" % i)

    # 6. classes
    recorded = set(vol_by) | set(mov_by)
    per_class = collections.defaultdict(lambda: [0, False, False])
    for i, r in enumerate(refs):
        pc = per_class[r.cls]
        pc[0] += 1
        pc[1] = pc[1] or i in wired
        pc[2] = pc[2] or i in recorded
    status = {}
    for cls, (n, w, rec) in per_class.items():
        s = class_status(cls, w, rec)
        status[cls] = s
        if s == "unknown" and (w or gameplay_class(cls)):
            add("class_unknown", cls)
        elif s in ("approximated", "ignored") and (w or gameplay_class(cls)) and not _ignorable(cls):
            add("class_unsupported", "%s (%s)" % (cls, s))
    parents = 0
    for i, r in enumerate(refs):
        p = r.get("parentname")
        if p and not resolve(p.split(",")[0]):
            parents += 1
            add("parent_dangling", "%s#%d %s" % (r.cls, i, p))
    out = {k: sorted(set(v)) if k in _DEDUP else v for k, v in f.items()}
    return {"findings": out, "classes": status, "entities": len(refs), "aligned": aligned,
            "counts": {k: len(v) for k, v in f.items()}}


_DEDUP = ("filter_class_unsupported", "class_unknown", "class_unsupported", "input_unimplemented", "volume_key_unread")


def _ignorable(cls):
    """Classes that are not gameplay even when wired: the original's sound, light and effect toys."""
    return cls.startswith(("ambient_", "env_sprite", "env_spark", "env_smoke", "env_steam", "light", "env_sound",
                           "env_soundscape", "info_particle_system", "env_lightglow", "env_beam", "env_dustpuff",
                           "env_splash", "env_bubbles", "point_spotlight", "env_texturetoggle", "func_dustmotes",
                           "func_smokevolume", "env_tonemap_controller", "color_correction", "env_fog_controller",
                           "env_sun", "sky_camera", "env_cubemap", "info_overlay", "infodecal", "shadow_control",
                           "env_wind", "func_precipitation", "env_projectedtexture", "postprocess_controller",
                           "point_clientcommand", "game_text", "env_hudhint", "env_message", "env_instructor_hint",
                           "prop_physics", "prop_dynamic", "prop_static", "func_illusionary", "func_detail", "func_lod",
                           "info_node", "info_hint", "env_screenoverlay", "point_camera", "func_monitor",
                           "env_shooter", "env_physexplosion", "env_rotorwash", "env_citadel"))


_VOL_KEYS = {}


def _volume_gameplay_keys(cls):
    """Keys a class's definition gives that change how the volume plays (bools/numbers, not names)."""
    if cls in _VOL_KEYS:
        return _VOL_KEYS[cls]
    cl, bases, _m = _defs()
    keys, seen, stack = {}, set(), [cl.get(cls)]
    while stack:
        d = stack.pop()
        if not d:
            continue
        for k, v in d.get("keys", {}).items():
            keys.setdefault(k.lower(), v)
        for b in d.get("bases", []):
            if b not in seen:
                seen.add(b)
                stack.append(bases.get(b))
    out = {k: (v[1] if len(v) > 1 else "") for k, v in keys.items()
           if v and v[0] in ("integer", "float", "choices", "boolean", "flags")}
    _VOL_KEYS[cls] = out
    return out


def _num(v):
    try:
        return float(str(v).split()[0])
    except (ValueError, IndexError):
        return 0.0 if not str(v).strip() else str(v).strip().lower()


def _as_entity(r):
    e = reader.Entity()
    e.update({k: v for k, v in r.k.items()})
    return e


def _from_godot(at, scale=None):
    from . import units
    s = scale or units.VISUAL
    return (at[0] / s, -at[2] / s, at[1] / s)


def gameplay_lost(rep):
    """Sorted `class:detail` of every severe finding: the coverage list the ratchet guards."""
    out = []
    for k, v in rep["findings"].items():
        if FINDINGS.get(k, ("lost",))[0] in SEVERE:
            out += ["%s:%s" % (k, d) for d in v]
    return sorted(set(out))
