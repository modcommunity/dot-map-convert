"""The models a map packs in its pakfile, converted and kept in the raw store.

`extract(bsp, out_dir)` turns every packed mdl (with its vvd and vtx) into `<out>/<path>.glb`,
its materials' base textures embedded as PNG from the packed vmt/vtf, and writes
`<out>/models.json`: per model the triangle count, bounds and size in metres (Godot axes), the
materials and each texture's average colour. A model the map places but does not pack (a game
model) is listed with `packed: false`. The glb is the author's art: raw store only, never shipped.
`load_index` / `Index.get` is what an importer reads to size and tell apart a prop whose name it
cannot place.
"""

import json
import math
import os
from struct import error as struct_error

from . import mdl, props, units, vtf

TEXTURE_SIDE = 512


def _pak_name(key):
    return props.norm_model(key)


def _material_texture(pak, path, cache):
    """(png bytes, average colour) of a material's base texture, or (None, None). `path` is the vmt
    path without `materials/` and `.vmt`; a patch vmt follows its `include`."""
    if path in cache:
        return cache[path]
    cache[path] = (None, None)
    for _ in range(4):
        raw = pak.get("materials/%s.vmt" % path)
        if raw is None:
            return cache[path]
        text = raw.decode("latin-1")
        base = vtf.base_texture(text)
        if base is None:
            inc = vtf.vmt_keys(text).get("include")
            if not inc:
                return cache[path]
            inc = inc.replace("\\", "/").lower()
            path = inc[len("materials/"):-4] if inc.startswith("materials/") and inc.endswith(".vmt") else inc
            continue
        data = pak.get("materials/%s.vtf" % base)
        if data is None:
            return cache[path]
        try:
            w, h, px = vtf.read(data, TEXTURE_SIDE)
        except (vtf.TextureError, struct_error):
            return cache[path]
        cache[path] = (vtf.png(w, h, px), list(vtf.average(px)))
        return cache[path]
    return cache[path]


def convert(pak, key, cache=None, glb=True):
    """(glb bytes or None, record) for the packed model `key` ("models/x/y.mdl"), or raises
    `mdl.ModelError`. `glb=False` skips the textures and the file: the measure an importer needs."""
    cache = {} if cache is None else cache
    stem = key[:-4]
    vtx = pak.get(stem + ".dx90.vtx") or pak.get(stem + ".dx80.vtx") or pak.get(stem + ".sw.vtx")
    if vtx is None or stem + ".vvd" not in pak:
        raise mdl.ModelError("no vvd or vtx beside the mdl")
    m = mdl.parse(pak[key], pak[stem + ".vvd"], vtx)
    paths = m.material_paths(pak)
    textures, mats = {}, []
    for i, p in enumerate(paths):
        png, avg = _material_texture(pak, p, cache) if glb else (None, None)
        if png:
            textures[i] = png
        mats.append({"name": m.materials[i], "vmt": p, "average": avg})
    if m.bounds() is None:
        raise mdl.ModelError("no drawn triangles")
    lo, hi = m.bounds()
    rec = {"packed": True, "triangles": m.triangles(), "min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi],
           "size": [round(b - a, 4) for a, b in zip(lo, hi)], "centre": [round((a + b) / 2, 4) for a, b in zip(lo, hi)],
           "materials": mats}
    return (mdl.to_glb(m, textures) if glb else None), rec


def placed(bsp):
    """{normalised model path: count} over entities and static props."""
    out = {}
    for e in bsp.entities:
        m = str(e.get("model", ""))
        if m.lower().endswith(".mdl"):
            out[props.norm_model(m)] = out.get(props.norm_model(m), 0) + 1
    for p in bsp.static_props():
        out[props.norm_model(p["model"])] = out.get(props.norm_model(p["model"]), 0) + 1
    return out


def extract(bsp, out_dir=None, notes=None):
    """Convert every packed model into `out_dir` and write `models.json`; returns the index.
    With no `out_dir` nothing is written or textured: the sizes alone, for an importer."""
    notes = [] if notes is None else notes
    pak = bsp.read_pak(notes, only=(".mdl", ".vvd", ".vtx", ".vmt", ".vtf"))
    counts = placed(bsp)
    index, cache = {}, {}
    for key in sorted(k for k in pak if k.endswith(".mdl") and k.startswith("models/")):
        try:
            glb, rec = convert(pak, key, cache, glb=out_dir is not None)
        except (mdl.ModelError, IndexError, KeyError, struct_error) as e:
            notes.append("%s not converted: %s" % (key, e))
            index[key] = {"packed": False, "error": str(e)}
            continue
        if out_dir is not None:
            dest = os.path.join(out_dir, key[:-4] + ".glb")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(glb)
            rec["glb"] = key[:-4] + ".glb"
        rec["count"] = counts.get(key, 0)
        index[key] = rec
    for key, n in counts.items():
        if key not in index:
            index[key] = {"packed": False, "count": n}
    if out_dir is not None:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "models.json"), "w") as f:
            json.dump({"format": "dot-bsp-models", "version": 1, "scale": units.VISUAL, "models": index}, f, indent=1, sort_keys=True)
            f.write("\n")
    return index


class Index:
    """`models.json` read back: `get(model path)` is the record of a packed model or None."""

    def __init__(self, models):
        self.models = models

    def get(self, model):
        r = self.models.get(props.norm_model(model))
        return r if r and r.get("packed") else None

    def __len__(self):
        return sum(1 for r in self.models.values() if r.get("packed"))


def load_index(path):
    """An `Index` from a `models.json` file or the raw directory holding `models/models.json`; empty if absent."""
    if os.path.isdir(path):
        path = os.path.join(path, "models", "models.json")
    if not os.path.isfile(path):
        return Index({})
    with open(path) as f:
        return Index(json.load(f)["models"])


def measure(bsp, notes=None):
    """An `Index` of the packed models' sizes, built in memory from the bsp's pakfile."""
    return Index(extract(bsp, None, notes))


def shape_distance(size, other):
    """How unlike two (x, y, z) sizes in metres are, Godot axes: height and the two horizontal
    sides compared as log ratios, so a flat disc is far from a can and a crate is near a box.
    Yaw is free, so the horizontal sides are compared longest to shortest."""
    def lg(a, b):
        return abs(math.log(max(a, 0.02) / max(b, 0.02)))
    wa, wb = sorted((size[0], size[2]), reverse=True), sorted((other[0], other[2]), reverse=True)
    return lg(size[1], other[1]) + lg(wa[0], wb[0]) + lg(wa[1], wb[1])


def shape_distance_exact(a, b):
    """`shape_distance` with the horizontal sides compared as given (x with x, z with z), for a caller that
    knows the stand-in's orientation."""
    def lg(p, q):
        return abs(math.log(max(p, 0.02) / max(q, 0.02)))
    return lg(a[0], b[0]) + lg(a[1], b[1]) + lg(a[2], b[2])


def match_size(size, candidates, limit=1.0, scale=1.0):
    """The id in `candidates` {id: (x, y, z)} whose size is nearest `size` (times `scale`), if its
    `shape_distance` is within `limit` (1.0 is about 1.35 times off on each of the three), else None;
    ties go to the lower id so a re-import is stable."""
    s = [v * scale for v in size]
    best = None
    for cid in sorted(candidates):
        d = shape_distance(s, candidates[cid])
        if best is None or d < best[0] - 1e-9:
            best = (d, cid)
    return best[1] if best and best[0] <= limit else None


def compatible(size, other, limit=1.0, scale=1.0):
    """True when a stand-in of size `other` is within `limit` of the model's `size`."""
    return shape_distance([v * scale for v in size], other) <= limit
