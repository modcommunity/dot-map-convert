"""The licence pass: no source-game texture or model leaves the importer.

Every texture a map draws is replaced by a free one: a photographic set from the addon's
`surfaces/` (ambientCG, CC0) through the generic id of `source_textures.tsv`, or an image
`textures.py` generates in the original's average colour. `annotate` records that for every
surface (`free` key) and in the manifest's `licence` block with URL, author and licence;
`check` fails on anything left without a free replacement. Models are never read: each is
listed with the stand-in a game's `PropTable` gives it, or `placeholder_box`. Sounds are
listed by `environment.sounds` and carry an empty `stand_in` until a free file is mapped.
"""

import collections
import os

from . import modelmap
from . import nearest as _nearest
from . import pbrmap
from . import props as _props
from . import standins
from . import textures

HERE = os.path.dirname(os.path.abspath(__file__))
FREE_PATH = os.path.join(HERE, "free_textures.tsv")
ALLOWED = frozenset(("CC0-1.0", "MIT", "Public Domain", "CC-BY-4.0"))


def load(path=FREE_PATH):
    """{generic id: {kind, source, url, author, licence}} from the table; raises on a bad row."""
    table = {}
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for n, line in enumerate(lines, 1):
        if not line.strip() or line.startswith("#"):
            continue
        c = line.split("\t")
        if len(c) != 6:
            raise ValueError("%s:%d: want 6 columns, got %d" % (path, n, len(c)))
        table[c[0]] = dict(zip(("kind", "source", "url", "author", "licence"), c[1:]))
    return table


def _key(r):
    return "%s:%s" % (r["kind"], r["generic"]) if r["kind"] != "generated" else "generated:%s:%s" % (
        r["generic"], "".join("%02x" % round(c * 255) for c in r["colour"]))


def _snap(colour):
    """Colour on a coarse grid, so a map's many near-equal averages share one generated image."""
    return [round(min(1.0, max(0.0, c)) * 8) / 8 for c in (colour or (0.5, 0.5, 0.5))[:3]]


def name_colour(material):
    """A colour for a texture the compiler measured as black that its name still tells: `black` is
    black (a dark veil), a `white` light panel is a pale surface. None for any other name."""
    base = str(material or "").lower().replace("\\", "/").rsplit("/", 1)[-1]
    if base.startswith("black") or base.endswith("_black"):
        return (0.04, 0.04, 0.04)
    if base.startswith("white"):
        return (0.9, 0.9, 0.9)
    return None


def _photo_row(kind, table):
    """A table row of a photo set of this kind (for its URL, author and licence), or None."""
    for row in table.values():
        if row["kind"] == kind:
            return row
    return None


def replacement(generic, colour, table, material=None):
    """The free replacement record of a surface of this generic id and average colour. A texture
    no row names gets the nearest photo set by name or colour (`how`), else a flat generated image."""
    colour = colour or name_colour(material)
    row = table.get(generic)
    how = "table" if row else None
    gid = generic
    if row is None:
        kind, how = _nearest.nearest(material, colour)
        row = _photo_row(kind, table) if kind else None
        if row:
            gid = "nearest_" + kind
        else:
            row, gid, how = table["flat"], "flat", "flat"
    if not gid.startswith(pbrmap.GENERIC) and (row["kind"] != "generated" or gid == "flat"):
        e = pbrmap.choose(material, colour, row["kind"] if row["kind"] != "generated" else None)
        if e:
            gid, how = pbrmap.GENERIC + e["id"], "library"
            row = {"kind": "pbr", "source": e["source"], "url": e["url"], "author": e["author"], "licence": e["licence"]}
    r = {"generic": gid, "colour": _snap(colour), "how": how}
    r.update(row)
    if r["kind"] == "generated":
        r["file"] = "textures/gen_%s_%s.png" % (r["generic"], "".join("%02x" % round(c * 255) for c in r["colour"]))
    elif r["kind"] == "pbr":
        r["file"] = "pbr/%s" % r["generic"][len(pbrmap.GENERIC):]
    else:
        r["file"] = "surfaces/%s" % r["kind"]
    return r


def _blend_records(s):
    """The library sets a blend displacement mixes, as replacement records, or [] without a library."""
    out = []
    for e in pbrmap.choose_layers(s.get("material")) if pbrmap.ENABLED else []:
        r = {"generic": pbrmap.GENERIC + e["id"], "colour": _snap(s.get("colour") or [0.5, 0.5, 0.5]), "how": "blend", "kind": "pbr",
             "source": e["source"], "url": e["url"], "author": e["author"], "licence": e["licence"], "file": "pbr/" + e["id"]}
        out.append(r)
    return out


def annotate(doc, outdir=None, table=None, prop_table=None, models=(), free_models=None, free_sounds=None, shaped=None, pbr_store=None, model_store=None):
    """Add `free` to every surface of the manifest `doc` and a `licence` block; write the generated
    images under `outdir` when given. `models` is the placed model paths (static props and
    prop entities); `prop_table` a `PropTable` of the game's stand-ins. Returns the block."""
    table = table or load()
    used = collections.OrderedDict()
    for s in doc["surfaces"]:
        recs = _blend_records(s) if s.get("alpha_offset") else []
        if not recs:
            recs = [replacement(s.get("generic"), s.get("colour"), table, s.get("material"))]
        s["free"] = _key(recs[0])
        if len(recs) > 1:
            s["free2"] = _key(recs[1])
        for r in recs:
            key = _key(r)
            u = used.setdefault(key, dict(r, sources=collections.Counter(), surfaces=0, area=0.0))
            u["sources"][s["material"]] += 1
            u["surfaces"] += 1
            u["area"] += s.get("area", 0.0)
        if r["kind"] == "generated" and outdir:
            p = os.path.join(outdir, r["file"])
            if not os.path.exists(p):
                textures.write(p, r["generic"], r["colour"])
    total = sum(u["area"] for u in used.values() if u["kind"] == "pbr") or 1.0
    store = pbr_store or (os.path.join(outdir, "pbr") if outdir else None)
    free = []
    for key, u in used.items():
        u["sources"] = sorted(u["sources"])
        u["area"] = round(u["area"], 1)
        if u["kind"] == "pbr":
            u["tier"] = pbrmap.tier_for(u["area"] / total)
            if store:
                pbrmap.ship_shared(u["generic"], store, u["tier"])
        free.append(dict(u, key=key))
    counts = collections.Counter(_props.norm_model(m) for m in models if m)
    tbl = prop_table or _props.PropTable({})
    free_models = free_models or standins.models()
    mods, used_models = [], {}
    for m, n in sorted(counts.items()):
        mine = tbl.get(m)
        row = None if mine or standins.is_detail(m) else free_models.get(m.replace("models/", "", 1))
        hit = (shaped or {}).get(m)
        if hit and hit["stand_in"].startswith("lib/"):
            mine = None
        elif mine or row:
            hit = None
        if hit and hit["row"]:
            row = dict(hit["row"], stand_in=hit["stand_in"])
        mods.append({"model": m, "count": n, "stand_in": mine or (row["stand_in"] if row else "skybox" if standins.is_skybox(m) else "detail" if standins.is_detail(m) and not (hit and hit.get("box")) else "measured_box" if hit and hit.get("box") else "placeholder_box")})
        if row:
            used_models.setdefault(row["stand_in"], dict(row, files=[], count=0))
            used_models[row["stand_in"]]["count"] += n
    free_sounds = free_sounds or standins.sounds()
    used_sounds = {}
    for s in doc.get("sounds", {}).get("ambient", []):
        row = free_sounds.get(s.get("message"))
        s["stand_in"] = row["stand_in"] if row else ""
        if row and row["stand_in"]:
            used_sounds.setdefault(row["stand_in"], dict(row, count=0))["count"] += 1
    skipped = sum(m["count"] for m in mods if m["stand_in"] == "skybox")
    block = {"textures": free, "models": mods, "skipped_skybox_models": skipped, "model_stand_ins": sorted(used_models.values(), key=lambda r: r["stand_in"]),
             "sounds": sorted(used_sounds.values(), key=lambda r: r["stand_in"]),
             "note": "No source texture, model or sound is shipped; each source name is only the name a replacement stands for."}
    libs = [r for r in block["model_stand_ins"] if r["stand_in"].startswith("lib/")]
    if libs and model_store:
        for r in libs:
            r["store_file"] = modelmap.ship(r, model_store)
        block["model_store"] = os.path.relpath(model_store, outdir).replace(os.sep, "/") if outdir else model_store
    if store and any(t["kind"] == "pbr" for t in free):
        block["pbr_store"] = os.path.relpath(store, outdir).replace(os.sep, "/") if outdir else store
        if outdir:
            small_albedos(block, outdir, store)
    doc["licence"] = block
    return block


SMALL_PX = 64


def small_albedos(block, outdir, store, px=SMALL_PX):
    """Write a `px`-square albedo of each PBR set into the pack (`textures/fb_<id>.webp`, a few KB each) and name it
    `fallback_file`, so a client without the store slices draws the set's own colours and pattern, not a guess.
    Returns the bytes written."""
    from PIL import Image
    total = 0
    for t in block.get("textures", []):
        if t.get("kind") != "pbr":
            continue
        sid = t["file"].split("/")[-1]
        rel = "textures/fb_%s.webp" % sid
        out = os.path.join(outdir, rel)
        if not os.path.exists(out):
            src = None
            for tier in (t.get("tier", "1k"), "1k", "2k"):
                for ext in ("webp", "jpg", "png"):
                    cand = os.path.join(store, sid, tier, "albedo." + ext)
                    if os.path.exists(cand):
                        src = src or cand
            if src is None:
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with Image.open(src) as im:
                im.convert("RGB").resize((px, px), Image.LANCZOS).save(out, "WEBP", quality=80, method=6)
        t["fallback_file"] = rel
        total += os.path.getsize(out)
    return total


def cmd_small(args):
    """`bsp.py smallalbedo <manifest.json>...`: add the small albedos to packs already converted, without a regen."""
    import json
    for m in args.manifests:
        with open(m) as f:
            doc = json.load(f)
        block = doc.get("licence", {})
        outdir = os.path.dirname(os.path.abspath(m))
        store = args.pbr_store or os.path.normpath(os.path.join(outdir, block.get("pbr_store", "pbr")))
        n = small_albedos(block, outdir, store, args.px)
        with open(m, "w") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
            f.write("\n")
        print("%s: %d small albedos, %d bytes" % (m, sum(1 for t in block.get("textures", []) if t.get("fallback_file")), n))
    return 0


def check(doc):
    """Problems that keep a map from shipping: a surface with no free replacement, or one whose
    licence is not in ALLOWED. [] when clean."""
    block = doc.get("licence")
    if not block:
        return ["no licence block: run the licence pass"]
    keys = {t["key"]: t for t in block["textures"]}
    bad = []
    for t in block["textures"]:
        if t.get("licence") not in ALLOWED:
            bad.append("%s: licence %r is not free" % (t["key"], t.get("licence")))
        if not t.get("url") or not t.get("author"):
            bad.append("%s: no URL or author recorded" % t["key"])
    for kind in ("model_stand_ins", "sounds"):
        for t in block.get(kind, []):
            if t.get("licence") not in ALLOWED or not t.get("url") or not t.get("author"):
                bad.append("%s %s: licence, URL or author is missing or not free" % (kind, t.get("stand_in")))
    for i, s in enumerate(doc["surfaces"]):
        if s.get("free") not in keys:
            bad.append("surface %d (%s) has no free replacement" % (i, s.get("material")))
    return bad


def credits_markdown(doc):
    """CREDITS.md text for the replacements a map uses, one line per distinct source."""
    seen, lines = set(), ["# Texture credits", "",
                          "Every texture of this map is a free replacement; the original map's textures and models are not used.", ""]
    for t in doc["licence"]["textures"]:
        k = (t["kind"], t["url"]) if t["kind"] != "generated" else ("generated", t["generic"])
        if k in seen:
            continue
        seen.add(k)
        lines.append("- %s (%s): %s, %s, %s, %s" % (t["kind"], t["generic"], t["source"], t["author"], t["licence"], t["url"]))
    for title, kind in (("Model stand-ins", "model_stand_ins"), ("Sound stand-ins", "sounds")):
        rows = doc["licence"].get(kind) or []
        if rows:
            lines += ["", "# " + title, ""]
            lines += ["- %s: %s, %s, %s, %s" % (t["stand_in"], t["source"], t["author"], t["licence"], t["url"]) for t in rows]
    return "\n".join(lines) + "\n"


# Licences that require the author to be named where the work is shown.
ATTRIBUTION = frozenset(("CC-BY-4.0",))


def credits_list(doc):
    """The machine-readable credits of a map: one dict per distinct work it shows (kind, name, author, licence, url,
    source, `attribution` true when the licence requires naming the author, `uses` how many times it is drawn).
    The same rows `credits_markdown` prints; `DotMapCredits` reads them from the manifest's licence block."""
    out, seen = [], {}
    block = doc.get("licence", {})

    def add(kind, name, row, uses):
        k = (kind, row.get("url") or name)
        if k in seen:
            seen[k]["uses"] += uses
            return
        seen[k] = {"kind": kind, "name": name, "author": row.get("author", ""), "licence": row.get("licence", ""),
                   "url": row.get("url", ""), "source": row.get("source", ""),
                   "attribution": row.get("licence") in ATTRIBUTION, "uses": uses}
        out.append(seen[k])

    for t in block.get("textures", []):
        if t["kind"] != "generated":
            add("texture", t["generic"], t, int(t.get("surfaces", 1)))
    for t in block.get("model_stand_ins", []):
        add("model", t["stand_in"], t, int(t.get("count", 1)))
    for t in block.get("sounds", []):
        add("sound", t["stand_in"], t, int(t.get("count", 1)))
    return out
