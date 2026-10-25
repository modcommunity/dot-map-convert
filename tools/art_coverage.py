#!/usr/bin/env python3 -I
"""How much of each converted map's art is real, and how much is a flat or stand-in surface.

    tools/art_coverage.py [--root DIR] [--max-default PCT] [--json PATH] [--worst N]

Reads every `*.coverage.json` under DIR/*/world/*/ (default: the folder holding this repo's
siblings). A texture counts as real when a free photo or PBR set was found for it
(`free_by_tier`), anything else is a generated flat colour; a model counts as unmapped when no
rule tier named it (`fallback`). A `default` tier answer only means the built-in rule table
matched, which says nothing about how good the match is. Exits 1 when any map has more than
--max-default percent flat textures or unmapped models (default 5), so it can gate a map as done.
"""

import argparse
import glob
import json
import os
import sys

KINDS = ("textures", "models")


def share(kind, entry):
    n = entry.get("looked_up", 0)
    if kind == "textures":
        generic = n - sum(entry.get("free_by_tier", {}).values())
    else:
        generic = entry.get("by_tier", {}).get("fallback", 0)
    return n, generic, (100.0 * generic / n if n else 0.0)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.abspath(os.path.join(here, "..", "..")))
    ap.add_argument("--max-default", type=float, default=5.0)
    ap.add_argument("--json")
    ap.add_argument("--worst", type=int, default=10)
    a = ap.parse_args()

    maps = []
    seen = set()
    for path in sorted(glob.glob(os.path.join(a.root, "*", "world", "*", "*.coverage.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        key = (d.get("map"), d.get("sha256"))
        if key in seen:
            continue
        seen.add(key)
        row = {"map": d.get("map") or os.path.basename(path).split(".")[0], "repo": path[len(a.root) + 1:].split(os.sep)[0]}
        for k in KINDS:
            n, g, pct = share(k, d.get(k, {}))
            row[k] = {"total": n, "generic": g, "pct": round(pct, 1)}
        maps.append(row)

    totals = {}
    for k in KINDS:
        n = sum(m[k]["total"] for m in maps)
        g = sum(m[k]["generic"] for m in maps)
        totals[k] = {"total": n, "generic": g, "pct": round(100.0 * g / n, 1) if n else 0.0}
    failing = [m for m in maps if any(m[k]["pct"] > a.max_default for k in KINDS)]

    print("art coverage: %d maps; flat textures %.1f%% (%d/%d), unmapped models %.1f%% (%d/%d); %d over %.0f%%" % (
        len(maps), totals["textures"]["pct"], totals["textures"]["generic"], totals["textures"]["total"],
        totals["models"]["pct"], totals["models"]["generic"], totals["models"]["total"], len(failing), a.max_default))
    for m in sorted(maps, key=lambda m: -(m["textures"]["generic"] + m["models"]["generic"]))[:a.worst]:
        print("  %-34s textures %5.1f%% of %-4d models %5.1f%% of %d" % (
            m["map"], m["textures"]["pct"], m["textures"]["total"], m["models"]["pct"], m["models"]["total"]))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"summary": {"total": len(maps), "failed": len(failing), "totals": totals},
                       "failures": [{"name": m["map"]} for m in failing], "maps": maps}, f, indent=1)
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
