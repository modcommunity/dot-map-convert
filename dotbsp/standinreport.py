"""Which props of the shipped worlds are still drawn by a stand-in that is not an equal-quality free model.

`bsp.py standins <manifest | dir>...` reads each converted world's `licence.models` (what shipped),
ranks every model by how many instances the worlds use, and sorts each into a tier by the stand-in's id:
free (Poly Haven, Sketchfab CC0/CC-BY, Quaternius), kenney (a Kenney block, acceptable but an upgrade
candidate), generated (a plain model of the original's size), placeholder (a box or a `detail` skip).
It also lists the sound rows that stay silent by rule, and where the shipped stand-in differs from
`rules/models/picks.tsv` (a world that wants regenerating). `--strict` exits 1 while a model of the
chosen tiers remains.
"""

import glob
import json
import os
import sys

from . import modeldims

TIERS = ("free", "kenney", "generated", "placeholder")


def tier(stand_in):
    """The tier of a `licence.models` stand_in string."""
    if not stand_in.startswith("lib/"):
        return "placeholder" if stand_in in ("placeholder_box", "detail", "") else "kenney"
    ident = stand_in[4:]
    if ident.startswith("own_"):
        return "generated"
    if ident.startswith("kenney_"):
        return "kenney"
    return "free"


def picks(path=None):
    """model -> library id from picks.tsv."""
    out = {}
    with open(path or os.path.join(modeldims.RULES, "picks.tsv"), encoding="utf-8") as f:
        for line in f.read().splitlines():
            if line and not line.startswith("#"):
                c = line.split("\t")
                out[c[0]] = c[1]
    return out


def silent_sound_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f.read().splitlines():
            if line and not line.startswith("#"):
                c = line.split("\t")
                if len(c) > 1 and not c[1]:
                    rows.append(c[0])
    return rows


def manifests(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += sorted(glob.glob(os.path.join(p, "**", "*.json"), recursive=True))
        else:
            out.append(p)
    return out


def build(files, pick_table):
    """Rank models over the manifests; returns the report dict."""
    models, worlds = {}, 0
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        lic = doc.get("licence") if isinstance(doc, dict) else None
        if not isinstance(lic, dict) or "models" not in lic:
            continue
        worlds += 1
        for m in lic["models"]:
            e = models.setdefault(m["model"], {"model": m["model"], "maps": 0, "instances": 0, "stand_in": m["stand_in"]})
            e["maps"] += 1
            e["instances"] += m.get("count", 1)
    rows = []
    for e in models.values():
        e["tier"] = tier(e["stand_in"])
        want = pick_table.get(e["model"])
        e["stale"] = bool(want) and "lib/" + want != e["stand_in"] and e["tier"] != "free"
        rows.append(e)
    rows.sort(key=lambda e: (-e["maps"], -e["instances"], e["model"]))
    totals = {t: sum(e["instances"] for e in rows if e["tier"] == t) for t in TIERS}
    return {"worlds": worlds, "models": rows, "instances": totals}


def text(rep, top, tiers):
    lines = []
    total = sum(rep["instances"].values()) or 1
    lines.append("%d worlds, %d models: " % (rep["worlds"], len(rep["models"])) + ", ".join(
        "%s %d (%.1f%%)" % (t, rep["instances"][t], 100.0 * rep["instances"][t] / total) for t in TIERS))
    rest = [e for e in rep["models"] if e["tier"] in tiers]
    for e in rest[:top]:
        lines.append("%3d maps %5d inst  %-11s %-60s %s%s" % (e["maps"], e["instances"], e["tier"], e["model"], e["stand_in"],
                                                              "  (picks.tsv has a newer pick: regen)" if e["stale"] else ""))
    if len(rest) > top:
        lines.append("... %d more" % (len(rest) - top))
    return lines


def cmd(args):
    here = os.path.dirname(os.path.abspath(__file__))
    rep = build(manifests(args.paths), picks())
    tiers = tuple(args.tiers.split(","))
    bad = [t for t in tiers if t not in TIERS]
    if bad:
        print("standins: unknown tier %s (tiers: %s)" % (",".join(bad), ",".join(TIERS)), file=sys.stderr)
        return 2
    silent = silent_sound_rows(os.path.join(here, "free_sounds.tsv"))
    rep["silent_sound_rows"] = silent
    if args.json:
        json.dump(rep, sys.stdout, indent=1)
        print()
    else:
        print("\n".join(text(rep, args.top, tiers)))
        print("sounds silent by rule (free_sounds.tsv rows with no stand-in): %d: %s" % (len(silent), " ; ".join(silent)))
    left = [e for e in rep["models"] if e["tier"] in tiers]
    return 1 if args.strict and left else 0
