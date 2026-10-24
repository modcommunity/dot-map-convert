"""Matching a map's placed models to a game's own props.

A converter never uses the source's models (they are the author's art). It keeps the position
and yaw of the ones the game has a stand-in for. The mapping is a dict the adapter's spec
holds, {"models/props/couch.mdl": "sofa"}, and the matching rules lived in each adapter:

* case-insensitive (a mapper writes `Models/Props_c17/Chair.mdl`; the lump lowercases);
* `\\` and `//` are `/` (static props come out of the game lump with forward slashes, entities
  as typed);
* a static prop (the `sprp` lump, compiled out of the entity lump) matches the same table as
  a `prop_dynamic` or `prop_physics`, because to the game they are the same furniture;
* `scale` rides along, because a v11 static prop can be scaled and the stand-in should follow.
"""

from . import entities as _ent
from . import reader


def norm_model(name):
    """A model path as matched: lowercase, forward slashes, no doubled slash, no leading slash."""
    n = str(name or "").strip().lower().replace("\\", "/")
    while "//" in n:
        n = n.replace("//", "/")
    return n.lstrip("/")


class PropTable:
    """{model path: id} compared by `norm_model`. `id` may be anything (a string, a dict)."""

    def __init__(self, mapping):
        self.map = {norm_model(k): v for k, v in (mapping or {}).items()}
        # prop-hunt-maps' PROP_MAP and its siblings key by file stem ("chair_office"), because
        # authors spell one model under several folders; a key with no "/" matches that way.
        self.stems = {k.rsplit(".", 1)[0] if k.endswith(".mdl") else k: v for k, v in self.map.items() if "/" not in k}

    def __len__(self):
        return len(self.map)

    def get(self, model, default=None):
        n = norm_model(model)
        if n in self.map:
            return self.map[n]
        stem = n.rsplit("/", 1)[-1]
        return self.stems.get(stem.rsplit(".", 1)[0], default)

    def unmatched(self, models):
        """Sorted, counted model paths not in the table: what an author still has to map."""
        out = {}
        for m in models:
            n = norm_model(m)
            if n and self.get(n) is None:
                out[n] = out.get(n, 0) + 1
        return sorted(out.items(), key=lambda kv: (-kv[1], kv[0]))


def placed_props(doc, table, include_static=True, classes=None):
    """Every placed prop the table has a stand-in for: [{id, model, origin, yaw, angles, scale,
    source, solid}], `solid` being a prop_dynamic's own key (0 for the rest), `source` being "entity" or "static". `origin` and `angles` are map units and degrees.

    `classes` replaces the default entity classes (the prop and physics-box classes).
    """
    if not isinstance(table, PropTable):
        table = PropTable(table)
    classes = frozenset(classes) if classes else (_ent.PROP_CLASSES | _ent.PHYSICS_PROP_CLASSES)
    out = []
    for rec in doc["entities"]:
        k = rec["keys"]
        if rec["classname"] not in classes or str(k.get("model", "")).startswith("*"):
            continue
        cid = table.get(k.get("model"))
        if cid is None:
            continue
        ang = reader.entity_vec(k, "angles")
        out.append({"id": cid, "model": norm_model(k.get("model")), "origin": reader.entity_vec(k),
                    "yaw": ang[1], "angles": ang, "scale": _num(k.get("modelscale"), 1.0), "source": "entity",
                    "solid": int(_num(k.get("solid"), 0)) if rec["classname"].startswith("prop_dynamic") else 0})
    if include_static:
        for sp in doc.get("static_props", []):
            cid = table.get(sp.get("model"))
            if cid is None:
                continue
            ang = list(sp.get("angles", [0, 0, 0]))
            out.append({"id": cid, "model": norm_model(sp["model"]), "origin": list(sp["origin"]),
                        "yaw": ang[1], "angles": ang, "scale": sp.get("scale", 1.0), "source": "static"})
    return out


def model_census(doc):
    """[(model path, count)] over every placed model in the map, most used first: the list an
    author maps from. Entities and static props together."""
    counts = {}
    for rec in doc["entities"]:
        m = rec["keys"].get("model", "")
        if m and not m.startswith("*") and (rec["classname"] in _ent.PROP_CLASSES or rec["classname"] in _ent.PHYSICS_PROP_CLASSES):
            counts[norm_model(m)] = counts.get(norm_model(m), 0) + 1
    for sp in doc.get("static_props", []):
        counts[norm_model(sp["model"])] = counts.get(norm_model(sp["model"]), 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _num(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
