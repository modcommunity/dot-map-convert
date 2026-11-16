"""The size of every model the converted maps place: what a library model is scaled to.

`bsp.py modeldims` walks the store, counts every placed model (entities and static props), and
writes `rules/models/model_dims.tsv` (model, min and max in metres, Godot axes, relative to the model's
origin, and where the size came from) plus `rules/models/ranking.tsv` (instances and maps per model).
Sizes come from the first map that packs the model (exact),
else from a folder of loose addon content given by `--content` (a workshop map that ships its models beside the
bsp instead of in its pakfile; measured exactly, source "addon"), else from the header of a stock model in
`--game-vpk` (the bounding box of its idle pose, a few percent large), else the model has no row and the picker falls
back to its category's usual size. Only numbers are kept: no model data leaves the importer.
"""

import json
import os
import struct
import sys

from . import models as _models, reader, store, units, vpk as _vpk

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
        self.vpk = _vpk.Vpk(dir_vpk)

    def bounds(self, model):
        b = self.vpk.get(model)
        if b is None:
            return None
        if len(b) < 152 or b[:4] != b"IDST":
            return None
        lo = struct.unpack_from("<3f", b, 104)
        hi = struct.unpack_from("<3f", b, 116)
        k = units.VISUAL
        return [lo[0] * k, lo[2] * k, -hi[1] * k], [hi[0] * k, hi[2] * k, -lo[1] * k]


class Loose:
    """The loose files of an addon folder (`models/...`, `materials/...`) read like a pakfile: lower-case relative paths."""

    def __init__(self, root):
        if not os.path.isdir(os.path.join(root, "models")):
            raise SystemExit("modeldims: --content %s has no models/ folder" % root)
        self.root = root
        self.files = {}
        for d, _dirs, names in os.walk(root):
            for n in names:
                full = os.path.join(d, n)
                self.files[os.path.relpath(full, root).replace(os.sep, "/").lower()] = full

    def __contains__(self, key):
        return key in self.files

    def __getitem__(self, key):
        with open(self.files[key], "rb") as f:
            return f.read()

    def get(self, key, default=None):
        return self[key] if key in self.files else default

    def bounds(self, model):
        """(min, max) in metres, Godot axes, for `model` ("models/x.mdl") when this folder holds it, else None."""
        if model not in self.files:
            return None
        try:
            rec = _models.convert(self, model, glb=False)[1]
        except Exception:       # a broken loose model is left to the next source
            return None
        return rec["min"], rec["max"]


def _ranking(path):
    """{model: (instances, maps, rank)} from a ranking.tsv."""
    out = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f.read().splitlines():
                if line and not line.startswith("#"):
                    c = line.split("\t")
                    out[c[1]] = (int(c[2]), int(c[3]), int(c[0]))
    return out


def _listed(path):
    """The model paths (`models/...mdl`, one per line, a leading map column allowed) a file names."""
    out = set()
    with open(path, encoding="utf-8") as f:
        for line in f.read().splitlines():
            if line.strip() and not line.startswith("#"):
                m = line.split()[-1].lower()
                out.add(m if m.startswith("models/") else "models/" + m)
    return out


def cmd(args):
    root = args.root or store.default_root()
    with open(os.path.join(root, "index.json")) as f:
        index = json.load(f)
    vpk = Vpk(args.game_vpk) if args.game_vpk else None
    loose = [Loose(d) for d in (getattr(args, "content", None) or [])]
    only = getattr(args, "maps", None) or []
    inst, maps, packed = {}, {}, {}
    for key, h in sorted(index.items()):
        path = os.path.join(root, h, "source.bsp")
        if key.startswith("defs") or not os.path.isfile(path):
            continue
        if only and not any(key == k or key.startswith(k.rstrip("/") + "/") for k in only):
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
            continue
        for content in loose:     # the map's own copy, exact, before a stock header
            b = content.bounds(m)
            if b:
                dims[m] = (b[0], b[1], "addon")
                break
        else:
            b = vpk.bounds(m) if vpk is not None else None
            if b:
                dims[m] = (b[0], b[1], "header")
    os.makedirs(args.out, exist_ok=True)
    order = sorted(inst, key=lambda m: (-inst[m], m))
    if getattr(args, "add", False):
        # the tables are kept line for line; the models they lack are measured and appended, ranked after them
        old_dims = load(os.path.join(args.out, DIMS))
        old_rank = _ranking(os.path.join(args.out, RANKING))
        wanted = _listed(args.models) if getattr(args, "models", None) else None
        new = [m for m in order if m not in old_rank and (wanted is None or m in wanted)]
        last = max((r[2] for r in old_rank.values()), default=0)
        with open(os.path.join(args.out, DIMS), "a", encoding="utf-8") as f:
            # a listed model the ranking already has but no size for (no header was read when it was ranked) is measured too
            fill = [m for m in order if m in old_rank and wanted is not None and m in wanted]
            for m in sorted(m for m in new + fill if m in dims and m not in old_dims):
                lo, hi, src = dims[m]
                f.write("%s\t%s\t%s\t%s\n" % (m, "\t".join("%.4f" % v for v in lo), "\t".join("%.4f" % v for v in hi), src))
        with open(os.path.join(args.out, RANKING), "a", encoding="utf-8") as f:
            for i, m in enumerate(new, last + 1):
                f.write("%d\t%s\t%d\t%d\t%s\n" % (i, m, inst[m], len(maps[m]), (dims.get(m) or old_dims.get(m) or (0, 0, "none"))[2]))
        print("modeldims: %d models added, %d with a size; %d ranked models given a size" % (
            len(new), sum(1 for m in new if m in dims or m in old_dims), sum(1 for m in fill if m in dims and m not in old_dims)))
        return 0
    with open(os.path.join(args.out, DIMS), "w", encoding="utf-8") as f:
        f.write("# model<TAB>min x y z<TAB>max x y z (metres, Godot axes, from the model's origin)<TAB>source: packed (exact), header (idle-pose box) or addon (exact, loose addon content). bsp.py modeldims\n")
        for m in sorted(dims):
            lo, hi, src = dims[m]
            f.write("%s\t%s\t%s\t%s\n" % (m, "\t".join("%.4f" % v for v in lo), "\t".join("%.4f" % v for v in hi), src))
    total = sum(inst.values())
    with open(os.path.join(args.out, RANKING), "w", encoding="utf-8") as f:
        f.write("# rank<TAB>model<TAB>instances<TAB>maps<TAB>size source. %d instances of %d models over the store. bsp.py modeldims\n" % (total, len(inst)))
        for i, m in enumerate(order, 1):
            f.write("%d\t%s\t%d\t%d\t%s\n" % (i, m, inst[m], len(maps[m]), dims[m][2] if m in dims else "none"))
    top = sorted(inst.values(), reverse=True)
    print("%d instances, %d models, %d with a size (%d packed); top 100 cover %.1f%%" % (
        total, len(inst), len(dims), len(packed), 100.0 * sum(top[:100]) / max(total, 1)))
    return 0
