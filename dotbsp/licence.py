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

from . import props as _props
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


def replacement(generic, colour, table):
    """The free replacement record of a surface of this generic id and average colour."""
    row = table.get(generic) or table["flat"]
    r = {"generic": generic if generic in table else "flat", "colour": _snap(colour)}
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
        r = replacement(s.get("generic"), s.get("colour"), table)
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
    mods = [{"model": m, "count": n, "stand_in": tbl.get(m) or "placeholder_box"} for m, n in sorted(counts.items())]
    block = {"textures": free, "models": mods,
             "note": "No source texture or model is shipped; each source name is only the name a replacement stands for."}
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
    return "\n".join(lines) + "\n"
