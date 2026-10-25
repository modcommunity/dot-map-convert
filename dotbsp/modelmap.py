"""Pick a free library model for every ranked prop model, at the original's real size.

`bsp.py modelmap` reads `rules/models/ranking.tsv`, `model_dims.tsv` and `categories.tsv`, and the library
manifest (`$DOT_MODEL_LIBRARY`, default `~/art-library/models`), and writes `rules/models/picks.tsv`:
one row per model, the library id, the metres its longest side is drawn at, the quarter turns, the
original's centre and base, and the credit. Where no library model has a shape within reach, a plain
model of the original's exact dimensions is generated into the library's `own/` folder (a box or a
cylinder in the category's colour, CC0 by the importer's author) and picked instead.
"""

import hashlib
import json
import math
import os
import re
import sys

from . import modeldims, standins

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = modeldims.RULES
CATEGORIES = "categories.tsv"
PICKS = "picks.tsv"
ALT_STEP = 0.08         # a later alternative in a category's library regex costs this much distance
REACH = 0.85            # largest shape distance (log units) a library model may have from the original
BIAS = {"Poly Haven": -0.12, "Quaternius": -0.06, "Sketchfab": -0.1}
OWN_AUTHOR = "TMC (generated for dot-map)"
OWN_URL = "https://github.com/modcommunity/dot-map"


def library_root():
    return os.environ.get("DOT_MODEL_LIBRARY") or os.path.expanduser("~/art-library/models")


def manifest(root=None):
    root = root or library_root()
    out = []
    with open(os.path.join(root, "manifest.tsv"), encoding="utf-8") as f:
        for line in f.read().splitlines():
            if not line or line.startswith("#"):
                continue
            c = line.split("\t")
            if len(c) < 10 or "/" in c[0]:
                continue
            files = c[9].split(",")
            out.append({"id": c[0], "source": c[1], "url": c[2], "author": c[3], "licence": c[4], "tags": c[5],
                        "dims": (float(c[6]), float(c[7]), float(c[8])), "file": files[0],
                        "own": c[1].startswith("TMC")})
    return out


def categories(path=None):
    rows = []
    with open(path or os.path.join(RULES, CATEGORIES), encoding="utf-8") as f:
        for line in f.read().splitlines():
            if not line or line.startswith("#"):
                continue
            c = line.split("\t")
            rows.append({"name": re.compile(c[0]), "lib": None if c[1] == "NONE" else [re.compile(r"(?<![a-z0-9])(?:%s)(?![a-z0-9])" % a) for a in c[1].replace("-", "_").split("|")],
                         "dims": tuple(float(v) for v in c[2:5]), "shape": c[5], "colour": c[6]})
    return rows


GENERIC = {"name": None, "lib": None, "dims": (0.5, 0.5, 0.5), "shape": "box", "colour": "909088"}


SKIP_KITS = re.compile(r"kenney_(hexagon|tower-defense|marble|platformer|brick|coaster|minigolf|mini-skate|toy-car|cube-pets|blocky|mini-characters|mini-dungeon|mini-forest|mini-arena|prototype|blaster|holiday|road-pack|city-kit-roads|modular|space-kit|space-station|retro-fantasy|castle|fantasy)")


def _snake(ident):
    """An id as lower snake case, so a camelCase name matches by whole words."""
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", ident).lower().replace("-", "_")


def distance(target, lib, turn_margin=0.15):
    """(distance, scale, turns): how far library dims (w, h, d) are from the target size (x, y, z), after the best
    uniform scale. Source x is the glb's z, so the unturned pairing is x with d."""
    best = None
    for turns, (a, b) in ((0, (lib[2], lib[0])), (1, (lib[0], lib[2]))):
        t = [max(v, 0.005) for v in (target[0], target[1], target[2])]
        l = [max(v, 0.005) for v in (a, lib[1], b)]
        r = [math.log(t[i] / l[i]) for i in range(3)]
        s = math.exp(sum(r) / 3.0)
        d = max(abs(v - sum(r) / 3.0) for v in r) + 0.3 * abs(math.log(s))
        cand = (d + (0.0 if turns == 0 else turn_margin), s, turns)
        if best is None or cand < best:
            best = cand
    return best


def own_model(root, kind, size, colour):
    """Writes the generated model and returns its manifest record."""
    import trimesh
    w, h, d = (max(round(v, 2), 0.02) for v in size)
    ident = "own_%s_%dx%dx%d_%s" % (kind, w * 100, h * 100, d * 100, colour)
    folder = os.path.join(root, "own", ident)
    path = os.path.join(folder, ident + ".glb")
    if not os.path.isfile(path):
        os.makedirs(folder, exist_ok=True)
        if kind == "cyl":
            m = trimesh.creation.cylinder(radius=0.5, height=1.0, sections=24)
            m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
        else:
            m = trimesh.creation.box((1, 1, 1))
        m.apply_scale((w, h, d))
        m.apply_translation((0, h / 2, 0))
        rgb = [int(colour[i:i + 2], 16) for i in (0, 2, 4)]
        m.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=rgb + [255], metallicFactor=0.0, roughnessFactor=0.8))
        m.export(path)
        with open(os.path.join(folder, "model.json"), "w") as f:
            json.dump({"id": ident, "source": "TMC generated model", "url": OWN_URL, "author": OWN_AUTHOR, "licence": "CC0-1.0",
                       "tags": "own,%s" % kind, "dims": [w, h, d], "files": ["own/%s/%s.glb" % (ident, ident)]}, f)
    return {"id": ident, "source": "TMC generated model", "url": OWN_URL, "author": OWN_AUTHOR, "licence": "CC0-1.0",
            "dims": (w, h, d), "file": "own/%s/%s.glb" % (ident, ident), "own": True}


def _jitter(model):
    return int(hashlib.md5(model.encode()).hexdigest()[:6], 16) / 0xFFFFFF


def pick(model, size, cat, lib):
    """(record, scale, turns, distance) of the best library model for `model`, or None."""
    best = None
    scored = []
    for m in lib:
        if m["own"]:
            continue
        name = _snake(m["id"])
        if SKIP_KITS.search(name):
            continue
        rank = next((i for i, rx in enumerate(cat["lib"]) if rx.search(name)), None)
        if rank is not None:
            d, s, t = distance(size, m["dims"])
            scored.append((d + BIAS.get(m["source"], 0.0) + ALT_STEP * rank, s, t, m))
    scored.sort(key=lambda r: r[0])
    if scored and scored[0][0] <= REACH:
        near = [r for r in scored if r[0] <= scored[0][0] + 0.06][:6]
        d, s, t, m = near[int(_jitter(model) * len(near)) % len(near)]
        return m, s, t, d
    return best


def cmd(args):
    root = library_root()
    lib = manifest(root)
    cats = categories()
    dims = modeldims.load()
    rank = []
    with open(os.path.join(RULES, modeldims.RANKING), encoding="utf-8") as f:
        for line in f.read().splitlines():
            if line and not line.startswith("#"):
                c = line.split("\t")
                rank.append((c[1], int(c[2])))
    rows, stat = [], {"library": 0, "own": 0, "skipped": 0, "none": 0}
    instances = {k: 0 for k in stat}
    for model, n in rank:
        key = model[len("models/"):] if model.startswith("models/") else model
        if standins.is_skybox(model) or standins.is_detail(model):
            stat["skipped"] += 1
            instances["skipped"] += n
            continue
        cat = next((c for c in cats if c["name"].search(key.lower().rsplit("/", 1)[-1])), None)
        d = dims.get(model)
        if cat is None and d:
            cat = GENERIC
        if cat is None:
            stat["none"] += 1
            instances["none"] += n
            continue
        if d:
            lo, hi = d[0], d[1]
            size = [hi[i] - lo[i] for i in range(3)]
            centre, base = [(lo[i] + hi[i]) / 2 for i in range(3)], lo[1]
            # a measured size can be a thin sliver (a decal, a card): the category's size is the safer target
            if min(size) <= 0.0 and max(size) <= 0.0:
                d = None
        if not d:
            size, centre, base = list(cat["dims"]), [0.0, 0.0, 0.0], 0.0
        hit = pick(model, size, cat, lib) if cat["lib"] is not None else None
        if hit:
            m, s, turns, _dist = hit
            kind = "library"
        else:
            kind = "own"
            sub = "generic" if cat is GENERIC else "plain" if cat["lib"] is None else "nofit"
            instances[sub] = instances.get(sub, 0) + n
            m = own_model(root, "cyl" if cat["shape"] == "cyl" else "box", size, cat["colour"])
            s, turns = 1.0, 0
            if cat["shape"] == "none":
                stat["none"] += 1
                instances["none"] += n
                continue
        stat[kind] += 1
        instances[kind] += n
        w, h, dd = m["dims"]
        rows.append([model, m["id"], "%.4f" % (s * max(w, h, dd)), str(turns), "%.4f" % centre[0], "%.4f" % centre[2], "%.4f" % base,
                     m["source"], m["url"], m["author"], m["licence"], m["file"]])
    out = os.path.join(args.out or RULES, PICKS)
    with open(out, "w", encoding="utf-8") as f:
        f.write("# model<TAB>library id<TAB>size (m, longest side)<TAB>quarter turns<TAB>centre x<TAB>centre z<TAB>base y (original, m)<TAB>source<TAB>url<TAB>author<TAB>licence<TAB>file. bsp.py modelmap\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    total = sum(n for _m, n in rank)
    print("picked %d models: %d library, %d generated; %d skipped (skybox, left out on purpose), %d with no category" % (
        len(rows), stat["library"], stat["own"], stat["skipped"], stat["none"]))
    print("by instance of %d: library %.1f%%, generated %.1f%% (plain fixtures %.1f%%, no library fit %.1f%%, no category %.1f%%), skipped %.1f%%, unmapped %.1f%%" % (
        total, *(100.0 * instances.get(k, 0) / total for k in ("library", "own", "plain", "nofit", "generic", "skipped", "none"))))
    return 0


def ship(row, store, root=None):
    """Copies a picked library model into the shared model store, keeping its library-relative path (a pack's
    models share its texture folder), and returns that path. A glTF goes with everything beside it."""
    import shutil
    root = root or library_root()
    rel = row["file"]
    src = os.path.join(root, rel)
    dst = os.path.join(store, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if rel.endswith(".gltf"):
        if not os.path.isfile(dst):
            shutil.copytree(os.path.dirname(src), os.path.dirname(dst), dirs_exist_ok=True)
        return rel
    if not os.path.isfile(dst):
        shutil.copyfile(src, dst)
    tex = os.path.join(os.path.dirname(src), "Textures")
    if os.path.isdir(tex):
        shutil.copytree(tex, os.path.join(os.path.dirname(dst), "Textures"), dirs_exist_ok=True)
    return rel
