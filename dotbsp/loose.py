"""Which placed physics props are loose, and which breakable holds each one up.

A `prop_physics*` the map did not freeze (spawnflag 8, "motion disabled") is a free body in the original: a barrel
on a ledge rolls when pushed, shot or let go. The importer drew it as a static prop. This marks it (`loose`: the toy
kind) so a game can simulate it, and records on every breakable the props resting on its top (`holds`, indexes into
`props`): shooting a support then lets what stood on it fall and roll. Rules: `loose_kinds.tsv`.
"""

import os
import re

from . import props as _props
from . import reader

KINDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loose_kinds.tsv")
FROZEN = 8          # prop_physics spawnflag: motion disabled
MATCH_M = 1.0       # the drawn prop stands this near the entity's origin (a shape-matched model is centred)
EDGE_M = 0.5        # a prop's origin may stand this far past the support's edge and still rest on it
SEAT_BELOW = 0.35   # ...and this far under its top (a hull that sinks a little)
SEAT_ABOVE = 0.6    # ...or this far over it (an origin at the middle of a barrel)

_RULES = None


def rules():
    global _RULES
    if _RULES is None:
        _RULES = []
        with open(KINDS) as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    pat, kind = line.rstrip("\n").split("\t")[:2]
                    _RULES.append((re.compile(pat), kind))
    return _RULES


def kind_of(model):
    n = _props.norm_model(model)
    for pat, kind in rules():
        if pat.search(n.rsplit("/", 1)[-1]):
            return kind
    return None


def _at(origin, scale, y0):
    return [origin[0] * scale, origin[2] * scale - y0, -origin[1] * scale]


def mark(prop_records, entities, scale, y0):
    """Sets `loose` (a toy kind) on each placed prop (`prop_records`, the manifest's `props`) that is a free
    `prop_physics*` entity of a kind the rules know. Returns how many."""
    spots = []
    for e in entities:
        k = e.get("keys", e)
        c = e.get("classname", k.get("classname", ""))
        if not c.startswith("prop_physics") or str(k.get("model", "")).startswith("*"):
            continue
        if int(_props._num(k.get("spawnflags"), 0)) & FROZEN:
            continue
        kind = kind_of(k.get("model"))
        if kind:
            spots.append((_props.norm_model(k.get("model")), _at(reader.entity_vec(k), scale, y0), kind))
    n = 0
    for model, at, kind in spots:
        best, dist = None, MATCH_M
        for i, p in enumerate(prop_records):
            if "loose" in p or _props.norm_model(p.get("model")) != model:
                continue
            d = max(abs(p["at"][0] - at[0]), abs(p["at"][2] - at[2]))
            if d < dist and abs(p["at"][1] - at[1]) < MATCH_M:
                best, dist = i, d
        if best is not None:
            prop_records[best]["loose"] = kind
            n += 1
    return n


def hold(breakables, prop_records, bounds_of, scale, y0):
    """Adds `bounds` ([x0, y0, z0, x1, y1, z1], metres, Godot axes) and `holds` (the indexes of the loose props that
    rest on its top) to each breakable. `bounds_of(model)` is the model's source-unit (mins, maxs) with its origin applied."""
    loose = [(i, p["at"]) for i, p in enumerate(prop_records) if p.get("loose")]
    for b in breakables:
        got = bounds_of(b["model"])
        if got is None:
            continue
        lo, hi = got
        a, c = _at(lo, scale, y0), _at(hi, scale, y0)
        box = [min(a[0], c[0]), min(a[1], c[1]), min(a[2], c[2]), max(a[0], c[0]), max(a[1], c[1]), max(a[2], c[2])]
        b["bounds"] = [round(v, 3) for v in box]
        b["holds"] = [i for i, at in loose
                      if box[0] - EDGE_M <= at[0] <= box[3] + EDGE_M and box[2] - EDGE_M <= at[2] <= box[5] + EDGE_M
                      and box[4] - SEAT_BELOW <= at[1] <= box[4] + SEAT_ABOVE]
