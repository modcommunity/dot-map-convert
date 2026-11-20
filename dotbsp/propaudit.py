"""How every prop of a converted world is drawn, against the size of the model it stands for.

`bsp.py propaudit <world manifest | dir>...` reads each converted world's `props` and works out, per record,
what the runtime (dot-map `mesh_props.gd`) draws:

- `box` records are neutral blocks (a measured model with no stand-in);
- a `lib/<id>` stand-in is the library model at its manifest dims (`$GS_MODEL_LIBRARY/manifest.tsv`); a missing
  library model is drawn as a grey block of the record's `collide`/`bounds`, else `size` x size/2 x size/2;
- any other stand-in is a dot-map prop (`addons/dot_map/props/<id>.glb`, `$DOT_MAP_PROPS`) at its glb bounds;

times `scale`, then times `size / longest side` when the record has a `size`. That drawn box is compared with the
source model's measured box: the record's `bounds` when it has one, else `rules/models/model_dims.tsv` times `scale`.

A prop is off-scale when the ratio of drawn to source longest side is outside [--low, --high] (default 0.8 to 1.25)
and an outlier when it is over --outlier times (default 10) either way; it is distorted when, side for side (both
boxes sorted, the longest sides made equal), one of the shorter sides is more than --distort times (default 2.5) its
partner. Each off-scale record gets a cause:

- `native`: no `size`, so the stand-in is drawn at its own size (a dot-map prop or library model of another scale);
- `picks`: the `size` (from rules/models/picks.tsv or the shape match) disagrees with the measured source;
- `modelscale`: the record's `scale` is not 1 and the source size is only known unscaled;
- `standin`: the stand-in's own proportions (the longest side fits, the rest does not).

`--json PATH` writes every map's numbers and the flagged records; `--max-outliers N`, `--max-blobs N` and
`--max-offscale-share F` make the command exit 1 when a map is over (0 turns each check off; none is on by default).
"""

import glob
import json
import math
import os
import struct
import sys

from . import modeldims, modelmap

LOW, HIGH, OUTLIER, DISTORT = 0.8, 1.25, 10.0, 2.5
MIN_SIDE = 0.05  # a source side under this is a decal or a sprite; its ratio says nothing
UNMAPPED = ("placeholder_box", "measured_box")
LABELS = UNMAPPED + ("detail", "dropped", "skybox")


def props_dir():
    env = os.environ.get("DOT_MAP_PROPS")
    if env:
        return env
    cand = os.path.expanduser("~/godot/dot-map/addons/dot_map/props")
    return cand if os.path.isdir(cand) else ""


def _mat(node):
    if "matrix" in node:
        m = node["matrix"]
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    t = node.get("translation", [0, 0, 0])
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    s = node.get("scale", [1, 1, 1])
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def gltf_json(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] == b"glTF":
        n = struct.unpack_from("<I", data, 12)[0]
        return json.loads(data[20:20 + n])
    return json.loads(data)


def gltf_dims(path):
    """The (x, y, z) size of a glTF's meshes in scene space (accessor min/max through each node's transform), or None."""
    try:
        g = gltf_json(path)
    except (OSError, ValueError):
        return None
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    nodes = g.get("nodes", [])
    scenes = g.get("scenes") or [{"nodes": list(range(len(nodes)))}]
    scene = scenes[g.get("scene", 0)]

    def walk(i, parent):
        node = nodes[i]
        m = _mul(parent, _mat(node))
        if "mesh" in node:
            for prim in g["meshes"][node["mesh"]].get("primitives", []):
                acc = g["accessors"][prim["attributes"]["POSITION"]]
                if "min" not in acc:
                    continue
                for cx in (acc["min"][0], acc["max"][0]):
                    for cy in (acc["min"][1], acc["max"][1]):
                        for cz in (acc["min"][2], acc["max"][2]):
                            p = [m[r][0] * cx + m[r][1] * cy + m[r][2] * cz + m[r][3] for r in range(3)]
                            for k in range(3):
                                lo[k], hi[k] = min(lo[k], p[k]), max(hi[k], p[k])
        for c in node.get("children", []):
            walk(c, m)

    ident = [[1 if i == j else 0 for j in range(4)] for i in range(4)]
    for i in scene.get("nodes", []):
        walk(i, ident)
    if lo[0] == math.inf:
        return None
    return tuple(hi[k] - lo[k] for k in range(3))


class StandIns:
    """Native (x, y, z) dims of every stand-in id, read once."""

    def __init__(self, lib_root=None, props=None):
        self.props = props if props is not None else props_dir()
        self.lib = {}
        try:
            for row in modelmap.manifest(lib_root):
                self.lib[row["id"]] = row["dims"]
        except OSError:
            pass
        self.cache = {}
        self.table = load_standin_dims()

    def dims(self, ident):
        if ident in self.cache:
            return self.cache[ident]
        out = None
        if ident.startswith("lib/"):
            out = self.lib.get(ident[4:])
        elif self.props:
            for ext in (".glb", ".gltf"):
                p = os.path.join(self.props, ident + ext)
                if os.path.isfile(p):
                    out = gltf_dims(p)
                    break
        if out is None and not ident.startswith("lib/"):
            out = self.table.get(ident)
        self.cache[ident] = out
        return out


STANDIN_DIMS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "standin_dims.tsv")


def load_standin_dims(path=STANDIN_DIMS):
    """{stand-in id: (x, y, z)} from the checked-in `dotbsp/standin_dims.tsv` (`bsp.py propaudit --write-standin-dims`)."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                c = line.rstrip("\n").split("\t")
                out[c[0]] = tuple(float(v) for v in c[1:4])
    except OSError:
        pass
    return out


def write_standin_dims(props, path=STANDIN_DIMS):
    """Measures every dot-map prop glb under `props` and writes the table the converter's fit pass reads."""
    rows = []
    for root, _dirs, files in os.walk(props):
        for fn in files:
            if fn.endswith((".glb", ".gltf")):
                full = os.path.join(root, fn)
                d = gltf_dims(full)
                if d:
                    rows.append((os.path.splitext(os.path.relpath(full, props))[0].replace(os.sep, "/"), d))
    if not rows:
        raise SystemExit("propaudit: no prop glbs under %r" % props)
    rows.sort()
    with open(path, "w", encoding="utf-8") as f:
        f.write("# stand-in id<TAB>x<TAB>y<TAB>z: the native drawn size in metres (Godot axes) of every dot-map prop "
                "(addons/dot_map/props/<id>.glb). Written by `bsp.py propaudit --write-standin-dims --props DIR`; read by "
                "the converter's prop fit pass (standins.fit_prop) and by propaudit when the props folder is not at hand.\n")
        for ident, d in rows:
            f.write("%s\t%.3f\t%.3f\t%.3f\n" % (ident, d[0], d[1], d[2]))
    return len(rows)


def source_box(rec, dims_tbl):
    """The measured (x, y, z) box of the source model, and where it came from."""
    b = rec.get("bounds") or rec.get("collide")
    if isinstance(b, dict) and b.get("box"):
        return tuple(float(v) for v in b["box"]), "bounds"
    row = dims_tbl.get(rec.get("model", ""))
    if row:
        s = float(rec.get("scale", 1.0))
        return tuple((row[1][k] - row[0][k]) * s for k in range(3)), "model_dims"
    return None, ""


def drawn(rec, native):
    """The (x, y, z) box the runtime draws for a record whose stand-in measures `native` (mesh_props.gd _place_prop)."""
    s = float(rec.get("scale", 1.0))
    size = float(rec.get("size", 0.0))
    longest = max(native) if native else 0.0
    k = s * (size / longest if size > 0 and longest > 0.001 else 1.0)
    return tuple(v * k for v in native)


def judge(rec, src, out, low=LOW, high=HIGH, outlier=OUTLIER, distort=DISTORT):
    """(ratio, flags, cause) for one record's source and drawn boxes; ratio None when the source is too small to say."""
    ls, ld = max(src), max(out)
    if ls < MIN_SIDE or ld <= 0:
        return None, [], ""
    ratio = ld / ls
    flags = []
    if ratio < low or ratio > high:
        flags.append("offscale")
    if ratio >= outlier or ratio <= 1.0 / outlier:
        flags.append("outlier")
    ss, so = sorted(src), sorted(out)
    for a, b in zip(ss[:2], so[:2]):
        if a >= MIN_SIDE and b > 0 and max(b / (a * ratio), a * ratio / b) > distort:
            flags.append("distorted")
            break
    cause = ""
    if "offscale" in flags:
        if float(rec.get("scale", 1.0)) != 1.0 and not rec.get("bounds"):
            cause = "modelscale"
        elif not rec.get("size"):
            cause = "native"
        else:
            cause = "picks"
    elif "distorted" in flags:
        cause = "standin"
    return ratio, flags, cause


def audit_doc(doc, name, stand, dims_tbl, low=LOW, high=HIGH, outlier=OUTLIER, distort=DISTORT):
    props = doc.get("props", [])
    out = {"map": name, "props": len(props), "boxes": 0, "lib": 0, "lib_unbounded": 0, "kit": 0, "kit_missing": 0, "lib_missing": 0,
           "measured": 0, "unmeasured": 0, "offscale": 0, "outliers": 0, "distorted": 0, "causes": {}, "worst": [], "unmapped_models": {},
           "licence": {}}
    for m in doc.get("licence", {}).get("models", []):
        label = m["stand_in"] if m["stand_in"] in LABELS else "stand_in"
        out["licence"][label] = out["licence"].get(label, 0) + m["count"]
        if m["stand_in"] in UNMAPPED:
            out["unmapped_models"][m["model"]] = m["count"]
    rows = []
    for rec in props:
        sid = rec.get("stand_in")
        if not sid:
            if rec.get("box"):
                out["boxes"] += 1
            continue
        lib = sid.startswith("lib/")
        out["lib" if lib else "kit"] += 1
        if lib and not rec.get("bounds") and not rec.get("collide"):
            out["lib_unbounded"] += 1
        native = stand.dims(sid)
        if native is None:
            out["lib_missing" if lib else "kit_missing"] += 1
            continue
        src, how = source_box(rec, dims_tbl)
        if src is None:
            out["unmeasured"] += 1
            continue
        out["measured"] += 1
        d = drawn(rec, native)
        ratio, flags, cause = judge(rec, src, d, low, high, outlier, distort)
        if ratio is None:
            continue
        for fl, key in (("offscale", "offscale"), ("outlier", "outliers"), ("distorted", "distorted")):
            if fl in flags:
                out[key] += 1
        if cause:
            out["causes"][cause] = out["causes"].get(cause, 0) + 1
        if flags:
            rows.append({"model": rec.get("model", ""), "stand_in": sid, "at": rec.get("at"), "ratio": round(ratio, 3), "flags": flags,
                         "cause": cause, "source": [round(v, 3) for v in src], "source_from": how, "drawn": [round(v, 3) for v in d],
                         "size": rec.get("size"), "scale": rec.get("scale", 1.0)})
    rows.sort(key=lambda r: -abs(math.log(max(r["ratio"], 1e-6))))
    out["worst"] = rows
    out["blobs"] = out["boxes"] + out["lib_missing"] + out["kit_missing"]
    return out


def audit_world(path, stand, dims_tbl, **kw):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return audit_doc(doc, os.path.splitext(os.path.basename(path))[0], stand, dims_tbl, **kw)


def _is_world(p):
    try:
        with open(p, "rb") as f:
            head = f.read(4096)
        return b'"breakables"' in head and b'"props"' in head or b'"bin"' in head[:200]
    except OSError:
        return False


def worlds(args):
    for a in args:
        if os.path.isdir(a):
            for p in sorted(glob.glob(os.path.join(a, "**", "*.json"), recursive=True)):
                if not p.endswith((".coverage.json", ".doc.json", "credits.json")) and _is_world(p):
                    yield p
        else:
            yield a


def by_model(results):
    """Flagged records grouped by (model, stand-in) across maps, most instances first."""
    agg = {}
    for r in results:
        for w in r["worst"]:
            a = agg.setdefault((w["model"], w["stand_in"]), {"model": w["model"], "stand_in": w["stand_in"], "count": 0, "maps": set(),
                                                             "ratio": w["ratio"], "cause": w["cause"], "flags": set(),
                                                             "source": w["source"], "drawn": w["drawn"]})
            a["count"] += 1
            a["maps"].add(r["map"])
            a["flags"].update(w["flags"])
    out = sorted(agg.values(), key=lambda a: -a["count"])
    for a in out:
        a["maps"], a["flags"] = sorted(a["maps"]), sorted(a["flags"])
    return out


def unmapped_ranked(results):
    agg = {}
    for r in results:
        for m, n in r["unmapped_models"].items():
            a = agg.setdefault(m, {"model": m, "count": 0, "maps": []})
            a["count"] += n
            a["maps"].append(r["map"])
    return sorted(agg.values(), key=lambda a: -a["count"])


def failures(results, max_outliers=0, max_blobs=0, max_offscale_share=0.0):
    fail = []
    for r in results:
        if max_outliers and r["outliers"] > max_outliers:
            fail.append("%s: %d props drawn 10x off over %d" % (r["map"], r["outliers"], max_outliers))
        if max_blobs and r["blobs"] > max_blobs:
            fail.append("%s: %d neutral or missing-model blocks over %d" % (r["map"], r["blobs"], max_blobs))
        if max_offscale_share and r["measured"] and r["offscale"] / r["measured"] > max_offscale_share:
            fail.append("%s: %.0f%% of measured props off-scale over %.0f%%" % (r["map"], 100 * r["offscale"] / r["measured"], 100 * max_offscale_share))
    return fail


def cmd(args):
    if args.write_standin_dims:
        n = write_standin_dims(args.props or props_dir(), args.write_standin_dims)
        print("propaudit: %d stand-in sizes -> %s" % (n, args.write_standin_dims))
        return 0
    if not args.paths:
        raise SystemExit("propaudit: no world manifests given")
    stand = StandIns(args.library, args.props)
    dims_tbl = modeldims.load()
    kw = {"low": args.low, "high": args.high, "outlier": args.outlier, "distort": args.distort}
    results = [audit_world(p, stand, dims_tbl, **kw) for p in worlds(args.paths)]
    print("%-24s %6s %6s %6s %6s %6s %6s %7s %6s  %s" % ("map", "props", "blobs", "meas", "unmeas", "offsc", "10x", "distort", "unmap", "causes"))
    for r in results:
        print("%-24s %6d %6d %6d %6d %6d %6d %7d %6d  %s" % (r["map"][:24], r["props"], r["blobs"], r["measured"], r["unmeasured"], r["offscale"],
                                                           r["outliers"], r["distorted"], sum(r["unmapped_models"].values()),
                                                           " ".join("%s=%d" % kv for kv in sorted(r["causes"].items()))))
    models = by_model(results)
    print("\nmost frequent flagged models (instances, drawn/source, cause, source box -> drawn box):")
    for a in models[:args.top]:
        print("  %4d x%-7.2f %-10s %-44s -> %-30s %s -> %s" % (a["count"], a["ratio"], a["cause"], a["model"][:44], a["stand_in"][:30],
                                                             a["source"], a["drawn"]))
    um = unmapped_ranked(results)
    if um:
        print("\nmost used unmapped models (drawn as blocks):")
        for a in um[:args.top]:
            print("  %4d  %s  (%s)" % (a["count"], a["model"], ",".join(a["maps"])[:60]))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"maps": results, "models": models, "unmapped": um}, f, indent=1, sort_keys=True)
    fail = failures(results, args.max_outliers, args.max_blobs, args.max_offscale_share)
    for line in fail:
        print("FAIL " + line, file=sys.stderr)
    return 1 if fail else 0


def add_parser(sub):
    p = sub.add_parser("propaudit", help="every prop of converted worlds: what it is drawn as and at what size against the source (dotbsp/propaudit.py)")
    p.add_argument("paths", nargs="*")
    p.add_argument("--write-standin-dims", nargs="?", const=STANDIN_DIMS, default=None,
                   help="measure the dot-map prop glbs and write dotbsp/standin_dims.tsv (or PATH), then exit")
    p.add_argument("--library", default=None)
    p.add_argument("--props", default=None, help="dot-map props folder (default $DOT_MAP_PROPS or ~/godot/dot-map/addons/dot_map/props)")
    p.add_argument("--low", type=float, default=LOW)
    p.add_argument("--high", type=float, default=HIGH)
    p.add_argument("--outlier", type=float, default=OUTLIER)
    p.add_argument("--distort", type=float, default=DISTORT)
    p.add_argument("--max-outliers", type=int, default=0, help="exit 1 when a map has more props drawn 10x off (0: off)")
    p.add_argument("--max-blobs", type=int, default=0, help="exit 1 when a map draws more neutral or missing-model blocks (0: off)")
    p.add_argument("--max-offscale-share", type=float, default=0.0, help="exit 1 when a map's off-scale share of measured props is over this (0: off)")
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--json", default=None)
    return p
