"""The solid parts of a combined model: one own block per connected piece instead of one block over all of it.

A map maker's combined model (an autocombine of a street, a propper building, a wallworm wall) is a whole block or
room in one file. One block at its bounds would fill the street or the room, and no library model is that shape, so
`bsp.py modelparts` splits the model's triangles into connected pieces (vertices welded within `--weld` source units)
and writes the box of each piece to `rules/models/model_parts.tsv` (model, centre and size in metres, Godot axes, from
the model's origin). `standins.shape_matches` places one plain block per row. Only numbers are kept: no model data
leaves the importer.

Pieces that are lines (two sides under `--min-side`, a cable or a trim edge) and pieces wholly inside a bigger piece are
left out; a flat piece (a wall drawn one-sided) is given `--min-side` of depth so it is a body.
"""

import json
import os
import sys

from . import mdl, modeldims, reader, store, units

PARTS = "model_parts.tsv"
RULES = modeldims.RULES
HEADER = ("# model<TAB>centre x y z<TAB>size x y z (metres, Godot axes, from the model's origin): one own block per connected "
          "piece of a combined model. bsp.py modelparts\n")


def load(path=None):
    """{model: [(centre xyz, size xyz)]}."""
    path = path or os.path.join(RULES, PARTS)
    out = {}
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f.read().splitlines():
            if line and not line.startswith("#"):
                c = line.split("\t")
                out.setdefault(c[0], []).append(([float(v) for v in c[1:4]], [float(v) for v in c[4:7]]))
    return out


def pieces(meshes, weld=0.1, scale=units.VISUAL):
    """[(min, max)] in metres, Godot axes, of each connected piece of `meshes` (mdl.Model.meshes: source units)."""
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    step = weld if weld > 0 else 1e-3
    for _mat, vs, ix in meshes:
        keys = [(round(v[0] / step), round(v[1] / step), round(v[2] / step)) for v in vs]
        for k in keys:
            parent.setdefault(k, k)
        for t in range(0, len(ix) - 2, 3):
            a = find(keys[ix[t]])
            b = find(keys[ix[t + 1]])
            parent[b] = a
            c = find(keys[ix[t + 2]])
            parent[c] = a
    boxes = {}
    for k in parent:
        b = boxes.setdefault(find(k), [list(k), list(k)])
        for i in range(3):
            b[0][i] = min(b[0][i], k[i])
            b[1][i] = max(b[1][i], k[i])
    out = []
    for lo, hi in boxes.values():
        lo = [v * step * scale for v in lo]
        hi = [v * step * scale for v in hi]
        out.append(([lo[0], lo[2], -hi[1]], [hi[0], hi[2], -lo[1]]))
    return out


def keep(boxes, min_side=0.05):
    """[(centre, size)] of the pieces worth a block: lines (two sides under `min_side`) and pieces inside a bigger piece
    are dropped, a flat piece gets `min_side` of depth. `min_side` 0 keeps every piece as measured."""
    sized = []
    for lo, hi in boxes:
        size = [b - a for a, b in zip(lo, hi)]
        if min_side > 0 and sorted(size)[1] < min_side:
            continue
        sized.append((lo, hi, size))
    sized.sort(key=lambda b: -(b[2][0] * b[2][1] * b[2][2] + max(b[2])))
    out, kept = [], []
    for lo, hi, size in sized:
        if any(all(klo[i] - 1e-4 <= lo[i] and hi[i] <= khi[i] + 1e-4 for i in range(3)) for klo, khi in kept):
            continue
        kept.append((lo, hi))
        out.append(([round((a + b) / 2.0, 3) for a, b in zip(lo, hi)], [round(max(s, min_side), 3) for s in size]))
    return out


def measure(pak, key, weld=0.1, min_side=0.05):
    """[(centre, size)] of the packed or loose model `key`, or raises `mdl.ModelError`."""
    stem = key[:-4]
    vtx = pak.get(stem + ".dx90.vtx") or pak.get(stem + ".dx80.vtx") or pak.get(stem + ".sw.vtx")
    if vtx is None or stem + ".vvd" not in pak:
        raise mdl.ModelError("no vvd or vtx beside the mdl")
    m = mdl.parse(pak[key], pak[stem + ".vvd"], vtx)
    return keep(pieces(m.meshes, weld), min_side)


def write(rows, path):
    """Writes {model: [(centre, size)]} over the table at `path`: the models in `rows` are replaced, the rest kept."""
    table = load(path)
    table.update(rows)
    with open(path, "w", encoding="utf-8") as f:
        f.write(HEADER)
        for m in sorted(table):
            for c, s in table[m]:
                f.write("%s\t%s\t%s\n" % (m, "\t".join("%.3f" % v for v in c), "\t".join("%.3f" % v for v in s)))


def cmd(args):
    from . import models as _models
    wanted = modeldims._listed(args.models)
    root = args.root or store.default_root()
    with open(os.path.join(root, "index.json")) as f:
        index = json.load(f)
    loose = [modeldims.Loose(d) for d in (args.content or [])]
    only = args.maps or []
    rows, missing = {}, set(wanted)
    for key, h in sorted(index.items()):
        path = os.path.join(root, h, "source.bsp")
        if key.startswith("defs") or not os.path.isfile(path):
            continue
        if only and not any(key == k or key.startswith(k.rstrip("/") + "/") for k in only):
            continue
        with open(path, "rb") as f:
            bsp = reader.Bsp(path, data=f.read()).load()
        here = [m for m in _models.placed(bsp) if m in missing]
        if not here:
            continue
        pak = bsp.read_pak([], only=(".mdl", ".vvd", ".vtx"))
        for m in here:
            for src in [pak] + loose:
                if m not in src:
                    continue
                try:
                    rows[m] = measure(src, m, args.weld, args.min_side)
                except (mdl.ModelError, IndexError, KeyError) as e:
                    print("modelparts: %s: %s" % (m, e), file=sys.stderr)
                    continue
                missing.discard(m)
                break
    if args.max_parts:
        big = {m: len(p) for m, p in rows.items() if len(p) > args.max_parts}
        if big:
            raise SystemExit("modelparts: more than --max-parts %d pieces: %s" % (args.max_parts, ", ".join(
                "%s %d" % (m, n) for m, n in sorted(big.items()))))
    write(rows, os.path.join(args.out, PARTS))
    for m in sorted(missing):
        print("modelparts: %s not found in any map's pakfile or --content" % m, file=sys.stderr)
    print("modelparts: %d models, %d blocks; %d not found" % (len(rows), sum(len(p) for p in rows.values()), len(missing)))
    return 1 if missing else 0
