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

from . import nearest as _nearest
from . import props as _props
from . import standins
from . import textures

HERE = os.path.dirname(os.path.abspath(__file__))
FREE_PATH = os.path.join(HERE, "free_textures.tsv")
ALLOWED = frozenset(("CC0-1.0", "MIT", "Public Domain"))


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


def _photo_row(kind, table):
    """A table row of a photo set of this kind (for its URL, author and licence), or None."""
    for row in table.values():
        if row["kind"] == kind:
            return row
    return None


def replacement(generic, colour, table, material=None):
    """The free replacement record of a surface of this generic id and average colour. A texture
    no row names gets the nearest photo set by name or colour (`how`), else a flat generated image."""
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
    r = {"generic": gid, "colour": _snap(colour), "how": how}
    r.update(row)
    if r["kind"] == "generated":
        r["file"] = "textures/gen_%s_%s.png" % (r["generic"], "".join("%02x" % round(c * 255) for c in r["colour"]))
    else:
        r["file"] = "surfaces/%s" % r["kind"]
    return r


def annotate(doc, outdir=None, table=None, prop_table=None, models=()):
    """Add `free` to every surface of the manifest `doc` and a `licence` block; write the generated
    images under `outdir` when given. `models` is the placed model paths (static props and
    prop entities); `prop_table` a `PropTable` of the game's stand-ins. Returns the block."""
    table = table or load()
    used = collections.OrderedDict()
    for s in doc["surfaces"]:
        r = replacement(s.get("generic"), s.get("colour"), table, s.get("material"))
        key = _key(r)
        s["free"] = key
        u = used.setdefault(key, dict(r, sources=collections.Counter(), surfaces=0))
        u["sources"][s["material"]] += 1
        u["surfaces"] += 1
        if r["kind"] == "generated" and outdir:
            p = os.path.join(outdir, r["file"])
            if not os.path.exists(p):
                textures.write(p, r["generic"], r["colour"])
    free = []
    for key, u in used.items():
        u["sources"] = sorted(u["sources"])
        free.append(dict(u, key=key))
    counts = collections.Counter(_props.norm_model(m) for m in models if m)
    tbl = prop_table or _props.PropTable({})
    free_models = standins.models()
    mods, used_models = [], {}
    for m, n in sorted(counts.items()):
        mine = tbl.get(m)
        row = None if mine else free_models.get(m.replace("models/", "", 1))
        mods.append({"model": m, "count": n, "stand_in": mine or (row["stand_in"] if row else "placeholder_box")})
        if row:
            used_models.setdefault(row["stand_in"], dict(row, files=[], count=0))
            used_models[row["stand_in"]]["count"] += n
    free_sounds = standins.sounds()
    used_sounds = {}
    for s in doc.get("sounds", {}).get("ambient", []):
        row = free_sounds.get(s.get("message"))
        s["stand_in"] = row["stand_in"] if row else ""
        if row and row["stand_in"]:
            used_sounds.setdefault(row["stand_in"], dict(row, count=0))["count"] += 1
    block = {"textures": free, "models": mods, "model_stand_ins": sorted(used_models.values(), key=lambda r: r["stand_in"]),
             "sounds": sorted(used_sounds.values(), key=lambda r: r["stand_in"]),
             "note": "No source texture, model or sound is shipped; each source name is only the name a replacement stands for."}
    doc["licence"] = block
    return block


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
