"""A model's brushes as the boxes `flood.Flood` reads, in metres and Godot axes.

zombie-zone-maps' `model_boxes`, with the game's material table taken out: this returns the
source material name and the brush kind, and the game maps those to its own surface.
"""

from . import boxes as _boxes
from . import entities as _ent
from . import reader
from . import units as _units

DEFAULT_CONTENTS = reader.CONTENTS_SOLID | reader.CONTENTS_WINDOW | 0x10000   # solid, glass, playerclip


def model_boxes(doc, model=0, scale=_units.VISUAL, y0=0.0, slab_m=0.4, min_m=0.04, max_slabs=40,
                contents=DEFAULT_CONTENTS, tilt=False):
    """Boxes for every brush of `model` whose contents match: a list of
    {"at", "size", "yaw", "shape", "kind", "material", "rise", "brush"}.

    `kind` is `entities.classify_brush`'s ('solid', 'invisible', 'sky', 'glass'); `material` the
    lowercase source name it picked (None for an invisible or sky brush); `rise` is how far a
    brush cut into slabs along its slope climbs (0 otherwise), which is how a game decides
    whether a walking graph with a small step can use it. `slab_m` and `min_m` are in metres
    and converted at `scale`, so a 0.0254 game gets the same physical slab as a 0.01905 one.
    """
    by_id = {b["id"]: b for b in doc["brushes"]}
    m = next((x for x in doc["models"] if x["index"] == model), None)
    out = []
    for bid in (m["brushes"] if m else []):
        rec = by_id[bid]
        if not rec["hull"] or not (rec["contents"] & contents):
            continue
        kind, mat = _ent.classify_brush_record(doc, rec)
        made = _boxes.decompose([tuple(s["plane"]) for s in rec["sides"]], [tuple(p) for p in rec["hull"]],
                                slab=_units.from_metres(slab_m, scale), min_size=_units.from_metres(min_m, scale),
                                tilt=tilt, max_slabs=max_slabs)
        conv = []
        for b in made:
            sx, sy, sz = _boxes.size(b)
            conv.append({"at": list(_units.to_game(_boxes.centre(b), scale, y0)), "size": [sx * scale, sz * scale, sy * scale],
                         "yaw": b["phi"] % 90.0, "shape": b["kind"], "kind": kind, "material": mat, "brush": bid})
        rise = 0.0
        if conv and all(c["shape"] == "slab" for c in conv):
            rise = max(c["at"][1] + c["size"][1] / 2 for c in conv) - min(c["at"][1] - c["size"][1] / 2 for c in conv)
        for c in conv:
            c["rise"] = rise
        out.extend(conv)
    return out
