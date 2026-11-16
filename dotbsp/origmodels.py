"""Original models for an `_orig` conversion: INTERNAL ONLY, never published to a public repo, never committed.

A normal conversion draws every placed model as a free stand-in (`standins.placements`). An `_orig` pack can
carry the map's own models instead, so the unedited map is seen as it was built. Each placed `.mdl` is looked
up in the map's pakfile, then in the map's loose content folders (a workshop addon's own `models/` and
`materials/`, passed as `content`), then in the installed base games (`vpk.BaseGame`). It is converted with
`models.convert` (MDL + VVD + VTX to glTF, its textures from the VMT/VTF) and written under
`<out dir>/models/orig/`:

- `<name>.bin` holds the mesh and its PNG textures once;
- `<name>.gltf` (upright) and `<name>~p<pitch>r<roll>.gltf` (one per tilt a placement uses, rounded to
  `TILT_STEP` degrees) are small JSON files that share that `.bin` and differ only in a node matrix.

The runtime (dot-map `DotMapBspMesh._place_prop`) turns a library model by yaw only, faces it along +Z, and
puts the bottom centre of its bounds (the 8 corners of the mesh box, turned by the node) on the record's
`at`. So each node matrix turns the model from Source's +X facing to +Z and applies the placement's pitch and
roll, and `settle` moves each record's `at` from the model origin to where that bottom centre lands.

`doc["original_models"]` records that the pack is internal and which models were found where; the licence's
model rows carry `internal_only`. A model that cannot be found or read keeps its free stand-in.
"""

import json
import math
import os
import re
import shutil
import struct

from . import mdl as _mdl
from . import models as _models
from . import props as _props
from . import standins, vtf

DIR = "models/orig"
PREFIX = "lib/orig/"
TILT_STEP = 10.0        # degrees: a placement's pitch and roll are rounded to this, one shared variant per pair
SOURCE_NOTE = "The map's own models (Valve and the map author's): for the internal original pack only; never publish or commit this directory."


class Sources:
    """The map's files as one read-only mapping of lower-case paths: the pakfile, then the loose content
    folders, then the installed base games. `where(path)` tells which of the three holds a path."""

    def __init__(self, pak=None, content=(), game=None):
        self.pak = pak or {}
        self.loose = {}
        for root in content or ():
            for d, _subs, files in os.walk(root):
                for f in files:
                    rel = os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/").lower()
                    if rel.startswith(("models/", "materials/")):
                        self.loose.setdefault(rel, os.path.join(d, f))
        self.game = game
        self._memo = {}

    def where(self, path):
        if path in self.pak:
            return "pak"
        if path in self.loose:
            return "content"
        if self.game and self.get(path) is not None:
            return "base"
        return None

    def get(self, path, default=None):
        if path in self.pak:
            return self.pak[path]
        if path in self.loose:
            with open(self.loose[path], "rb") as f:
                return f.read()
        if not self.game:
            return default
        if path not in self._memo:
            self._memo[path] = self.game.get(path)
        got = self._memo[path]
        return default if got is None else got

    def __contains__(self, path):
        return self.get(path) is not None

    def __getitem__(self, path):
        got = self.get(path)
        if got is None:
            raise KeyError(path)
        return got


def safe(model):
    """A file name for a model path: `models/props_foliage/tree_pine04.mdl` -> `props_foliage.tree_pine04`."""
    m = _props.norm_model(model)
    m = m[len("models/"):] if m.startswith("models/") else m
    m = m[:-4] if m.endswith(".mdl") else m
    return re.sub(r"[^a-z0-9_.-]+", "_", m.replace("/", ".").lower())[:120] or "unnamed"


def tilt(angles, step=TILT_STEP):
    """(pitch, roll) of a placement's `angles`, each rounded to `step` degrees (0: exact) into [-180, 180)."""
    def q(a):
        a = round(float(a) / step) * step if step else float(a)
        a = (a + 180.0) % 360.0 - 180.0
        return 0.0 if abs(a) < 1e-6 else round(a, 3)
    return q(angles[0]), q(angles[2])


def variant_name(base, pitch, roll):
    if not pitch and not roll:
        return base
    return "%s~p%gr%g" % (base, pitch, roll)


def _source_tilt(pitch, roll):
    """Source's AngleMatrix for (pitch, yaw 0, roll): a 3x3 in Source axes."""
    sp, cp = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))
    sr, cr = math.sin(math.radians(roll)), math.cos(math.radians(roll))
    return [[cp, sr * sp, cr * sp],
            [0.0, cr, -sr],
            [-sp, sr * cp, cr * cp]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


# Source (x, y, z) -> Godot (x, z, -y), and back.
_M = [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]]
_MI = [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]]
# Godot rotation about +Y by -90 degrees: the model's +X (Source forward) to +Z (the runtime's stand-in facing).
_FACE = [[0.0, 0.0, -1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]]


def tilt_godot(pitch, roll):
    """The placement's pitch and roll as a 3x3 in Godot axes (applied before the yaw)."""
    return _mul(_mul(_M, _source_tilt(pitch, roll)), _MI)


def node_basis(pitch, roll):
    """The node matrix (3x3, Godot axes) baked into a variant: tilt, then turn +X to +Z."""
    return _mul(_FACE, tilt_godot(pitch, roll))


def _apply(m, p):
    return [sum(m[i][k] * p[k] for k in range(3)) for i in range(3)]


def turned_box(m, lo, hi):
    """(lo, hi) of the 8 corners of box (lo, hi) turned by 3x3 `m`: how the runtime measures a turned node's mesh."""
    pts = [_apply(m, (x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    return [min(p[k] for p in pts) for k in range(3)], [max(p[k] for p in pts) for k in range(3)]


def bottom_centre(m, lo, hi):
    """Where the runtime re-roots a model whose node is turned by `m`: the bottom centre of `turned_box`."""
    a, b = turned_box(m, lo, hi)
    return [(a[0] + b[0]) / 2.0, a[1], (a[2] + b[2]) / 2.0]


def split_glb(glb):
    """(json dict, bin bytes) of a binary glTF."""
    jlen = struct.unpack_from("<I", glb, 12)[0]
    doc = json.loads(glb[20:20 + jlen].decode())
    off = 20 + jlen
    blen = struct.unpack_from("<I", glb, off)[0] if off + 8 <= len(glb) else 0
    blob = bytes(glb[off + 8:off + 8 + blen])
    # The BIN chunk is padded to 4 bytes; dot-map rejects a .bin longer than the buffer's byteLength (draws a box).
    declared = (doc.get("buffers") or [{}])[0].get("byteLength")
    return doc, blob[:declared] if declared is not None else blob


def variant_gltf(doc, bin_name, basis):
    """A copy of glTF `doc` that reads its buffer from `bin_name` and draws its mesh under a node turned by `basis`.
    The mesh node goes under a plain root, so it stays a child the runtime measures with its turn."""
    out = json.loads(json.dumps(doc))
    out["buffers"] = [dict(out["buffers"][0], uri=bin_name)]
    mesh = dict(out["nodes"][0])
    mesh["matrix"] = [round(v, 7) for v in (basis[0][0], basis[1][0], basis[2][0], 0.0,
                                            basis[0][1], basis[1][1], basis[2][1], 0.0,
                                            basis[0][2], basis[1][2], basis[2][2], 0.0,
                                            0.0, 0.0, 0.0, 1.0)]
    out["nodes"] = [{"name": "orig", "children": [1]}, mesh]
    out["scenes"] = [{"nodes": [0]}]
    return out


def _alpha_modes(doc, rec, src):
    """Sets glTF alphaMode on the materials whose vmt cuts out ($alphatest: leaves, fences) or blends ($translucent)."""
    vmt = {m["name"]: m["vmt"] for m in rec.get("materials", [])}
    for mat in doc.get("materials", []):
        raw = src.get("materials/%s.vmt" % vmt.get(mat.get("name"), mat.get("name")))
        if raw is None:
            continue
        keys = vtf.vmt_keys(raw.decode("latin-1"))
        if keys.get("$alphatest", "0").strip() not in ("0", ""):
            mat["alphaMode"] = "MASK"
            mat["alphaCutoff"] = 0.5
        elif keys.get("$translucent", "0").strip() not in ("0", ""):
            mat["alphaMode"] = "BLEND"


def spots(bsp):
    """[(model, origin, angles, modelscale, solid)] of every placed .mdl (`standins._spots`), source units."""
    doc = {"entities": [{"classname": e.get("classname", ""), "keys": e} for e in bsp.entities],
           "static_props": bsp.static_props()}
    return [s for s in standins._spots(doc) if s[0] and str(s[0]).lower().endswith(".mdl")]


def convert_all(names, src):
    """({model: (glb, record, where)} for every model in `names` that converts, {model: why} for the rest)."""
    done, failed, cache = {}, {}, {}
    for name in sorted(names):
        where = src.where(name)
        if where is None:
            failed[name] = "not found in the pakfile, the content folders or the base games"
            continue
        try:
            glb, rec = _models.convert(src, name, cache)
        except (_mdl.ModelError, struct.error, ValueError, IndexError, KeyError) as e:
            failed[name] = "%s: %s" % (type(e).__name__, e)
            continue
        done[name] = (glb, rec, where)
    return done, failed


def place(bsp, src, outdir, scale, y0, step=TILT_STEP):
    """Writes the converted models under `outdir/DIR`; returns (records, rows, info). `records` are prop records at
    the model origins (`settle` moves them once every other pass has run), `rows` the licence's model rows, `info`
    the `original_models` record. A placement whose model did not convert is not in `records`."""
    sp = spots(bsp)
    names = {_props.norm_model(s[0]) for s in sp}
    done, failed = convert_all(names, src)
    root = os.path.join(outdir, DIR)
    os.makedirs(root, exist_ok=True)
    base_doc, written, uses, records = {}, {}, {}, []
    for model, o, ang, sc, sol in sp:
        name = _props.norm_model(model)
        if name not in done:
            continue
        glb, rec, _where = done[name]
        base = safe(name)
        if name not in base_doc:
            doc, blob = split_glb(glb)
            _alpha_modes(doc, rec, src)
            with open(os.path.join(root, base + ".bin"), "wb") as f:
                f.write(blob)
            base_doc[name] = doc
        pitch, roll = tilt(ang, step)
        vname = variant_name(base, pitch, roll)
        basis = node_basis(pitch, roll)
        if vname not in written:
            with open(os.path.join(root, vname + ".gltf"), "w") as f:
                json.dump(variant_gltf(base_doc[name], base + ".bin", basis), f, separators=(",", ":"))
            written[vname] = bottom_centre(basis, rec["min"], rec["max"])
        sid = PREFIX + vname
        uses[sid] = uses.get(sid, 0) + 1
        k = float(_props._num(sc, 1.0))
        r = {"stand_in": sid, "model": name, "orig": True,
             "at": [round(o[0] * scale, 4), round(o[2] * scale - y0, 4), round(-o[1] * scale, 4)],
             "yaw": round(float(ang[1]), 2), "scale": round(k, 3), "reroot": [round(v, 5) for v in written[vname]]}
        if sol:
            lo, hi = turned_box(tilt_godot(pitch, roll), rec["min"], rec["max"])
            r["solid"] = sol
            standins._collide(r, {"size": [b - a for a, b in zip(lo, hi)], "centre": [(a + b) / 2.0 for a, b in zip(lo, hi)]},
                              o, float(ang[1]), sc, scale, y0)
        records.append(r)
    rows = [{"stand_in": sid, "store_file": "%s/%s.gltf" % (DIR, sid[len(PREFIX):]), "source": "the original map",
             "author": "Valve and the map's author", "licence": "internal-only", "url": "", "internal_only": True, "count": n}
            for sid, n in sorted(uses.items())]
    info = {"internal_only": True, "tilt_step": step, "models": len(names), "converted": len(done),
            "drawn": len({r["model"] for r in records}), "variants": len(written), "placements": len(records),
            "from_pak": sum(1 for v in done.values() if v[2] == "pak"),
            "from_content": sum(1 for v in done.values() if v[2] == "content"),
            "from_base": sum(1 for v in done.values() if v[2] == "base"),
            "missing": {k: failed[k] for k in sorted(failed)}, "note": SOURCE_NOTE}
    return records, rows, info


def merge(props, records):
    """`props` (the free placements) with every placement of a converted model replaced by `records`."""
    have = {r["model"] for r in records}
    return [p for p in props if _props.norm_model(p.get("model", "")) not in have] + records


def settle(props):
    """Moves each original-model record's `at` from the model origin to where the runtime puts the re-rooted model
    (the bottom centre of its turned box, turned by yaw + the runtime's 90-degree facing and scaled); drops the helper key."""
    for p in props:
        c = p.pop("reroot", None)
        if c is None:
            continue
        s = float(p.get("scale") or 1.0)
        phi = math.radians(float(p.get("yaw", 0.0)) + 90.0)
        cf, sf = math.cos(phi), math.sin(phi)
        p["at"] = [round(p["at"][0] + s * (c[0] * cf + c[2] * sf), 4), round(p["at"][1] + s * c[1], 4),
                   round(p["at"][2] + s * (-c[0] * sf + c[2] * cf), 4)]
    return props


def ship_licence(doc, rows, outdir, old_store):
    """Points the licence's model store at the pack folder itself, so the pack carries its models: adds the original
    rows and copies into the pack the free library models still drawn (from `old_store`, the shared library)."""
    block = doc.setdefault("licence", {})
    drawn = {p.get("stand_in") for p in doc.get("props", [])}
    keep = []
    for row in block.get("model_stand_ins", []):
        if row.get("stand_in") not in drawn:
            continue
        rel = row.get("store_file")
        if rel and str(row["stand_in"]).startswith("lib/") and old_store:
            src, dst = os.path.join(old_store, rel), os.path.join(outdir, rel)
            if os.path.isfile(src) and not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
        keep.append(row)
    block["model_stand_ins"] = keep + rows
    block["model_store"] = "."
    return block
