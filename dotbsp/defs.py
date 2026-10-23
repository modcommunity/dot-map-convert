"""Reads rules/entity_defs.json, the generated class catalogue (see defs/build.py).

`resolve(name)` returns a class with its bases folded in: keys as name -> (type, default,
choices), inputs and outputs as lowercase name -> (name, type).
"""

import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rules", "entity_defs.json")
IMPLICIT = "_cbaseentity_"


def load(path=PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def known(doc, name):
    return name.lower() in doc["classes"]


def resolve(doc, name, _seen=None):
    """Folded record of a class or base, or None when the catalogue lacks it."""
    name = name.lower()
    rec = doc["classes"].get(name) or doc["bases"].get(name)
    if rec is None:
        return None
    seen = _seen if _seen is not None else set()
    out = {"keys": {}, "inputs": {}, "outputs": {}, "solid": bool(rec.get("solid")), "in": rec["in"]}
    if name in seen:
        return out
    seen.add(name)
    for b in ([IMPLICIT] if name != IMPLICIT else []) + rec.get("bases", []):
        r = resolve(doc, b, seen)
        if r:
            for f in ("keys", "inputs", "outputs"):
                out[f].update(r[f])
    for k in rec.get("extra", ()):
        out["keys"][k] = ("", "", [])
    for k, v in rec.get("keys", {}).items():
        out["keys"][k] = (v[0], v[1], v[2] if len(v) > 2 else [])
    for f in ("inputs", "outputs"):
        for n, t in rec.get(f, {}).items():
            out[f][n.lower()] = (n, t)
    return out
