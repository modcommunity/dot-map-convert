"""Free stand-ins for the models and sounds of a map: Kenney's CC0 packs, matched by name.

A map's own models and sounds are the author's and are never shipped. `free_models.tsv` maps a
model path to a glb in `addons/dot_map/props/`, `free_sounds.tsv` a sound name to an ogg in
`addons/dot_map/sounds/` or to a dot-audio stock bed. Both are regex tables, first match wins,
with source, URL, author and licence per row so `licence.check` can refuse anything not free.
What matches nothing stays a `placeholder_box` / silent: a wrong chair is better than a box,
a wrong voice is not better than silence.
"""

import math
import os
import re

from . import models as _models
from . import props as _props
from . import entities as _ent
from . import reader

HERE = os.path.dirname(os.path.abspath(__file__))
COLUMNS = ("stand_in", "source", "url", "author", "licence")

# A model of the 3D skybox (a distant city, forest or refinery) is drawn by the sky, never placed.
# Only a `skybox` or `sky` directory segment (or a skybox-named file): props/sky_scraper and de_sky_sign are props.
SKYBOX = re.compile(r"(^|[/_])skybox(?![a-z])|(^|/)sky/")


def is_skybox(model):
    """True for a model that only dresses the sky; it is skipped silently, not reported unmapped."""
    return bool(SKYBOX.search(str(model or "").lower().replace("\\", "/")))


def _load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f.read().splitlines(), 1):
            if not line.strip() or line.startswith("#"):
                continue
            c = line.split("\t")
            if len(c) != 6:
                raise ValueError("%s:%d: want 6 columns, got %d" % (path, n, len(c)))
            rows.append((re.compile(c[0]), dict(zip(COLUMNS, c[1:]))))
    return rows


class Table:
    """An ordered regex table; `get(name)` is the first matching row (a dict) or None."""

    def __init__(self, path):
        self.rows = _load(path)

    def get(self, name):
        n = str(name or "").lower().replace("\\", "/")
        for rx, row in self.rows:
            if rx.search(n):
                return row
        return None


def models(path=os.path.join(HERE, "free_models.tsv")):
    return Table(path)


class Sizes:
    """An ordered regex table to metres (`free_model_sizes.tsv`); `get(name)` is the first match or None."""

    def __init__(self, path=os.path.join(HERE, "free_model_sizes.tsv")):
        self.rows = []
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f.read().splitlines(), 1):
                if line.strip() and not line.startswith("#"):
                    c = line.split("\t")
                    if len(c) != 2:
                        raise ValueError("%s:%d: want 2 columns, got %d" % (path, n, len(c)))
                    self.rows.append((re.compile(c[0]), float(c[1])))

    def get(self, name):
        n = _props.norm_model(name).replace("models/", "", 1)
        for rx, m in self.rows:
            if rx.search(n):
                return m
        return None


SHAPE_LIMIT = 0.4   # normalised shape_distance a stand-in may be from a packed model (a stricter bar than a name)
SHAPE_MIN_SIDE, SHAPE_MAX_SIDE = 0.08, 3.5   # metres: a packed model outside is a decal or a building, not a prop


class ShapeCatalogue:
    """The generic stand-ins (`free_model_dims.tsv`) a packed model can be matched to by its measured shape."""

    def __init__(self, path=os.path.join(HERE, "free_model_dims.tsv")):
        self.dims = {}
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f.read().splitlines(), 1):
                if line.strip() and not line.startswith("#"):
                    c = line.split("\t")
                    if len(c) != 4:
                        raise ValueError("%s:%d: want 4 columns, got %d" % (path, n, len(c)))
                    self.dims[c[0]] = [float(v) for v in c[1:]]
        self.rows = {}
        for _rx, row in models().rows:
            self.rows.setdefault(row["stand_in"], row)

    def match(self, size):
        """(stand-in id, quarter_turns) nearest the measured `size` (x, y, z metres, Godot axes), or None. The
        glb's front is +z and the viewer turns it 90 degrees onto the source's +x, so glb x/z are
        compared with size z/x; quarter_turns is 1 when the other pairing (glb x with size x) fits better."""
        longest = max(size)
        if not SHAPE_MIN_SIDE <= longest <= SHAPE_MAX_SIDE:
            return None
        if size[1] < 0.3 * longest and longest > 0.8:
            return None   # a truss, a rug or a slab: a block stood in for it would be a wall
        s = [v / longest for v in size]
        best = None
        for cid in sorted(self.dims):
            d = self.dims[cid]
            k = max(d)
            n = [v / k for v in d]
            for turns, o in ((0, (n[2], n[1], n[0])), (1, tuple(n))):
                dist = _models.shape_distance_exact(s, o)
                if best is None or dist < best[0] - 1e-9:
                    best = (dist, cid, turns)
        return (best[1], best[2]) if best and best[0] <= SHAPE_LIMIT else None


def shape_matches(bsp, game_table=None, table=None, packed=None, catalogue=None):
    """{model path: {stand_in, turns, size, centre, row}} for every placed model neither the game's table nor the
    free name table knows and the map packs, matched by measured shape. The model itself is never copied."""
    from . import models as _m
    table = table or models()
    packed = packed if packed is not None else _m.measure(bsp)
    catalogue = catalogue or ShapeCatalogue()
    out = {}
    for m in _m.placed(bsp):
        rec = packed.get(m)
        if rec is None or is_skybox(m) or (game_table is not None and game_table.get(m) is not None):
            continue
        if table.get(m.replace("models/", "", 1)) is not None:
            continue
        hit = catalogue.match(rec["size"])
        if hit:
            out[m] = {"stand_in": hit[0], "turns": hit[1], "size": round(max(rec["size"]), 3),
                      "centre": rec["centre"], "base": rec["min"][1], "row": catalogue.rows.get(hit[0])}
    return out


def sounds(path=os.path.join(HERE, "free_sounds.tsv")):
    return Table(path)


class FreeProps(_props.PropTable):
    """A PropTable that answers with the free model table's stand-in id."""

    def __init__(self, table=None):
        super().__init__({})
        self.table = table or models()

    def get(self, model, default=None):
        row = self.table.get(_props.norm_model(model).replace("models/", "", 1))
        return row["stand_in"] if row else default


def placements(bsp, game_table=None, table=None, scale=0.01905, y0=0.0, sizes=None, shaped=None, packed=None):
    """[{stand_in, model, at, yaw, scale, size?}] (`size`: the metres its longest side is drawn at, for a
    small thing a furniture-sized stand-in would swamp) for every placed model the game's table does not
    know and the free table does; positions in metres and Godot axes like the rest of the manifest."""
    free = FreeProps(table)
    sizes = sizes or Sizes()
    packed = packed if packed is not None else _models_measure(bsp)
    doc = {"entities": [{"classname": e.get("classname", ""), "keys": e} for e in bsp.entities],
           "static_props": bsp.static_props()}
    out = []
    for p in _props.placed_props(doc, free):
        if game_table is not None and game_table.get(p["model"]) is not None:
            continue
        o = p["origin"]
        rec = {"stand_in": p["id"], "model": p["model"],
               "at": [round(o[0] * scale, 4), round(o[2] * scale - y0, 4), round(-o[1] * scale, 4)],
               "yaw": round(p["yaw"], 2), "scale": round(float(p.get("scale") or 1.0), 3)}
        if p["id"] == "rock" and packed.get(p["model"]) is None and UNMEASURED_DEBRIS.search(p["model"].lower()):
            continue
        size = sizes.get(p["model"])
        if size:
            rec["size"] = size
        else:
            _fit_natural(rec, packed.get(p["model"]), p.get("scale"))
        out.append(rec)
    shaped = shape_matches(bsp, game_table, table) if shaped is None else shaped
    spots = _spots(doc)
    boxes = _support_boxes(spots, packed, game_table, scale, y0)
    if boxes:
        gone = {(b["model"], tuple(b["origin"])) for b in boxes}
        out = [r for r in out if (r["model"], tuple(r["at"])) not in gone]
    if shaped:
        out += _shaped_placements(spots, shaped, scale, y0, {(b["model"], b["src"]) for b in boxes})
    out += [{k: v for k, v in b.items() if k not in ("origin", "src")} for b in boxes]
    return out


# Natural stand-ins are far smaller than what they stand in for (a 1.2 m tree for a 9 m one, a 1 m rock for a
# 15 m boulder), so a packed model's measured size is drawn: height for what grows upright (the glb's longest side
# is its height), the longest side for the rest.
NATURAL_UPRIGHT = frozenset({"tree", "plant", "pirate/palm"})
NATURAL_LOW = frozenset({"rock", "bush", "stump"})
# A stock debris model (not packed, so unmeasurable) is left out: a rock at its origin hangs in the air, small or
# sized, where the real chunk lay on or hung from something the converter does not know.
UNMEASURED_DEBRIS = re.compile(r"debris|rubble|cinderblock|concrete_chunk|concretepiece|brick|chunk|gib")
NATURAL_RANGE = (0.2, 40.0)   # metres: outside is a measuring accident (a tree-named sprite sheet), not a plant


def _fit_natural(rec, measured, modelscale):
    """Sets `size` on a natural stand-in `rec` from the packed model's measured size and puts it on the model's own
    base (some origins sit mid-trunk). Leaves it alone with no measure: a stock model cannot be measured."""
    sid = rec["stand_in"]
    if measured is None or sid not in NATURAL_UPRIGHT | NATURAL_LOW:
        return
    sx, sy, sz = measured["size"]
    size = sy if sid in NATURAL_UPRIGHT else max(sx, sy, sz)
    if not NATURAL_RANGE[0] <= size <= NATURAL_RANGE[1]:
        return
    rec["size"] = round(size, 3)
    base = measured["min"][1] * _props._num(modelscale, 1.0)
    if abs(base) > 0.05:
        rec["at"][1] = round(rec["at"][1] + base, 4)


def _models_measure(bsp):
    from . import models as _m
    return _m.measure(bsp)


def _spots(doc):
    """[(model, origin, angles, modelscale)] of every placed .mdl, in source units."""
    spots = [(e["keys"].get("model"), reader.entity_vec(e["keys"]), reader.entity_vec(e["keys"], "angles"), e["keys"].get("modelscale"))
             for e in doc["entities"] if e["classname"] in (_ent.PROP_CLASSES | _ent.PHYSICS_PROP_CLASSES)
             and not str(e["keys"].get("model", "")).startswith("*")]
    spots += [(p.get("model"), list(p["origin"]), list(p.get("angles", [0, 0, 0])), p.get("scale")) for p in doc.get("static_props", [])]
    return spots


BOX_MAX_SIDE = 4.0       # metres: a bigger packed model is a room or a roof, not furniture something stands on
BOX_MAX_HEIGHT = 1.4     # taller is a tree or a wall, which nothing rests on by its top
BOX_MIN_HEIGHT = 0.25    # a rug or a plate holds nothing up
BOX_NOT = re.compile(r"ceiling|truss|pipe|beam|moss|vine|light|lamp|rail|cable|wire|connector")   # hung or lattice things: a block would shade the room
BOX_REACH = 0.15         # how far past the edge a thing's origin may be and still rest on the model
BOX_TOP = 0.12           # how far from the top a thing's origin may be and still rest on it


def _support_boxes(spots, packed, game_table, scale, y0):
    """[{box, model, at, yaw, scale, origin, src}]: a size-correct neutral block for each placed packed model that
    something else rests on or inside (its origin lies over the model's footprint, at the model's top) and the shape table could not stand in for with the right size. Without it a stand-in table or shelf
    is smaller than the real one and the bottles on it hang in the air. The model itself is never copied."""
    out = []
    pts = [(m, o, k) for m, o, _a, k in spots]
    for model, o, ang, sc in spots:
        name = _props.norm_model(model)
        rec = packed.get(name)
        if rec is None or is_skybox(name) or BOX_NOT.search(name) or (game_table is not None and game_table.get(name) is not None):
            continue
        k = _props._num(sc, 1.0)
        sx, sy, sz = (v * k for v in rec["size"])
        if sy < BOX_MIN_HEIGHT or max(sx, sz) > BOX_MAX_SIDE or sy > BOX_MAX_HEIGHT:
            continue
        a = math.radians(ang[1])
        ca, sa = math.cos(a), math.sin(a)
        base = o[2] * scale + rec["min"][1] * k
        centre = rec["centre"]
        # the footprint in model axes (Godot): x along the model's x, z along its z; yaw turns it as the box is turned
        gx0, gz0 = o[0] * scale, -o[1] * scale
        cx, cz = centre[0] * k, centre[2] * k
        mx, mz = gx0 + cx * ca + cz * sa, gz0 - cx * sa + cz * ca
        held = False
        for m2, o2, k2 in pts:
            if o2 is o or _props.norm_model(m2) == name:
                continue
            dx, dz = o2[0] * scale - mx, -o2[1] * scale - mz
            lx, lz = dx * ca - dz * sa, dx * sa + dz * ca
            dy = o2[2] * scale - base
            if abs(lx) <= sx / 2 + BOX_REACH and abs(lz) <= sz / 2 + BOX_REACH and abs(dy - sy) <= BOX_TOP:
                held = True
                break
        if held:
            out.append({"box": [round(sx, 3), round(sy, 3), round(sz, 3)], "model": name,
                        "at": [round(mx, 4), round(base - y0 + sy / 2, 4), round(mz, 4)],
                        "yaw": round(ang[1], 2), "scale": 1.0,
                        "origin": [round(o[0] * scale, 4), round(o[2] * scale - y0, 4), round(-o[1] * scale, 4)],
                        "src": tuple(round(v, 3) for v in o)})
    return out


def _shaped_placements(spots, shaped, scale, y0, boxed=frozenset()):
    """Placements of the models `shape_matches` stood in: put on the packed model's middle, turned to its long side,
    drawn at its measured longest side (`size`, before the placement's own scale). A spot in `boxed` has a block instead."""
    out = []
    for model, o, ang, sc in spots:
        s = shaped.get(_props.norm_model(model))
        if s is None or (_props.norm_model(model), tuple(round(v, 3) for v in o)) in boxed:
            continue
        k = _props._num(sc, 1.0)
        a = math.radians(ang[1])
        cx, cz = s["centre"][0] * k, -s["centre"][2] * k
        gx = o[0] * scale + cx * math.cos(a) - cz * math.sin(a)
        gz = -o[1] * scale - (cx * math.sin(a) + cz * math.cos(a))
        out.append({"stand_in": s["stand_in"], "model": _props.norm_model(model), "shape": True,
                    "at": [round(gx, 4), round(o[2] * scale - y0 + s["base"] * k, 4), round(gz, 4)],
                    "yaw": round(ang[1] + 90.0 * s["turns"], 2), "scale": round(k, 3), "size": s["size"]})
    return out
