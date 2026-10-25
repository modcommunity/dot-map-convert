"""The size of every model the converted maps place: what a library model is scaled to.

`bsp.py modeldims` walks the store, counts every placed model (entities and static props), and
writes `rules/models/model_dims.tsv` (model, min and max in metres, Godot axes, relative to the model's
origin, and where the size came from) plus `rules/models/ranking.tsv` (instances and maps per model).
Sizes come from the first map that packs the model (exact), else from the header of a stock model
in a game directory given by `--game-vpk` (the bounding box of its idle pose, a few percent large),
else the model has no row and the picker falls back to its category's usual size. Only numbers are
kept: no model data leaves the importer.
"""

import json
import os
import struct
import sys

from . import models as _models, reader, regen, store, units

DIMS = "model_dims.tsv"
RANKING = "ranking.tsv"
RULES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules", "models")


def load(path=None):
    """{model: (min xyz, max xyz, source)} in metres, Godot axes."""
    path = path or os.path.join(RULES, DIMS)
    out = {}
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f.read().splitlines():
            if line and not line.startswith("#"):
                c = line.split("\t")
                out[c[0]] = ([float(v) for v in c[1:4]], [float(v) for v in c[4:7]], c[7])
    return out


class Vpk:
    """The model headers of a game directory (`<name>_dir.vpk` and its parts), for the size of a stock model."""

    def __init__(self, dir_vpk):
        sys.path.insert(0, os.path.expanduser("~/mapsrc/dumps/tools"))
        import vpklib
        self.lib = vpklib
        self.base = dir_vpk[:-len("_dir.vpk")]
        ents, self.end, self.data = vpklib.read_dir(dir_vpk)
        self.mdl = {e["path"].lower(): e for e in ents if e["path"].lower().endswith(".mdl")}

    def bounds(self, model):
        e = self.mdl.get(model)
        if e is None:
            return None
        b = self.lib.read(e, self.base + "_dir.vpk", self.data, self.end, self.base)
        if len(b) < 152 or b[:4] != b"IDST":
            return None
        lo = struct.unpack_from("<3f", b, 104)
        hi = struct.unpack_from("<3f", b, 116)
        k = units.VISUAL
        return [lo[0] * k, lo[2] * k, -hi[1] * k], [hi[0] * k, hi[2] * k, -lo[1] * k]


def cmd(args):
    root = args.root or store.default_root()
    with open(os.path.join(root, "index.json")) as f:
        index = json.load(f)
    vpk = Vpk(args.game_vpk) if args.game_vpk else None
    inst, maps, packed = {}, {}, {}
    for key, h in sorted(index.items()):
        path = os.path.join(root, h, "source.bsp")
        if key.startswith("defs") or not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                bsp = reader.Bsp(path, data=f.read()).load()
            counts = _models.placed(bsp)
            measured = _models.measure(bsp)
        except Exception as e:      # one unreadable map must not lose the other hundred
            print("modeldims: %s skipped: %s" % (key, e), file=sys.stderr)
            continue
        for m, n in counts.items():
            inst[m] = inst.get(m, 0) + n
            maps.setdefault(m, set()).add(key)
            r = measured.get(m)
            if r and m not in packed:
                packed[m] = (r["min"], r["max"], "packed")
    dims = {}
    for m in inst:
        if m in packed:
            dims[m] = packed[m]
        elif vpk is not None:
            b = vpk.bounds(m)
            if b:
                dims[m] = (b[0], b[1], "header")
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, DIMS), "w", encoding="utf-8") as f:
        f.write("# model<TAB>min x y z<TAB>max x y z (metres, Godot axes, from the model's origin)<TAB>source: packed (exact) or header (idle-pose box). bsp.py modeldims\n")
        for m in sorted(dims):
            lo, hi, src = dims[m]
            f.write("%s\t%s\t%s\t%s\n" % (m, "\t".join("%.4f" % v for v in lo), "\t".join("%.4f" % v for v in hi), src))
    total = sum(inst.values())
    with open(os.path.join(args.out, RANKING), "w", encoding="utf-8") as f:
        f.write("# rank<TAB>model<TAB>instances<TAB>maps<TAB>size source. %d instances of %d models over the store. bsp.py modeldims\n" % (total, len(inst)))
        for i, (m, n) in enumerate(sorted(inst.items(), key=lambda kv: (-kv[1], kv[0])), 1):
            f.write("%d\t%s\t%d\t%d\t%s\n" % (i, m, n, len(maps[m]), dims[m][2] if m in dims else "none"))
    top = sorted(inst.values(), reverse=True)
    print("%d instances, %d models, %d with a size (%d packed); top 100 cover %.1f%%" % (
        total, len(inst), len(dims), len(packed), 100.0 * sum(top[:100]) / max(total, 1)))
    return 0
