"""Free stand-ins for the models and sounds of a map: Kenney's CC0 packs, matched by name.

A map's own models and sounds are the author's and are never shipped. `free_models.tsv` maps a
model path to a glb in `addons/dot_map/props/`, `free_sounds.tsv` a sound name to an ogg in
`addons/dot_map/sounds/` or to a dot-audio stock bed. Both are regex tables, first match wins,
with source, URL, author and licence per row so `licence.check` can refuse anything not free.
What matches nothing stays a `placeholder_box` / silent: a wrong chair is better than a box,
a wrong voice is not better than silence.
"""

import os
import re

from . import props as _props
from . import reader

HERE = os.path.dirname(os.path.abspath(__file__))
COLUMNS = ("stand_in", "source", "url", "author", "licence")

# A model of the 3D skybox (a distant city, forest or refinery) is drawn by the sky, never placed.
SKYBOX = re.compile(r"(^|[/_])skybox(?![a-z])|(^|[/_])sky[/_]")


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


def placements(bsp, game_table=None, table=None, scale=0.01905, y0=0.0, sizes=None):
    """[{stand_in, model, at, yaw, scale, size?}] (`size`: the metres its longest side is drawn at, for a
    small thing a furniture-sized stand-in would swamp) for every placed model the game's table does not
    know and the free table does; positions in metres and Godot axes like the rest of the manifest."""
    free = FreeProps(table)
    sizes = sizes or Sizes()
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
        size = sizes.get(p["model"])
        if size:
            rec["size"] = size
        out.append(rec)
    return out
