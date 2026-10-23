"""Writes addons/dot_map/io/catalogue.json, the slice of the class catalogue DotMapIO needs.

    python3 -I tools/bsp/defs/runtime.py [--out FILE] [--all]

Per class (bases folded in): input and output names (lower case to the written name) and each
key's type and default. By default only the classes the scanned maps use and the classes a
runtime component implements; `--all` writes every class. Names, types and defaults only, like
the file it is cut from.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import classes, defs  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "..", "addons", "dot_map", "io", "catalogue.json")


def build(doc, everything=False):
    names = set(doc["classes"]) if everything else set(doc.get("map_classes", {})) | set(classes.COMPONENTS)
    base = defs.resolve(doc, defs.IMPLICIT)
    common = {"inputs": {k: v[0] for k, v in sorted(base["inputs"].items())},
              "outputs": {k: v[0] for k, v in sorted(base["outputs"].items())},
              "keys": {k: [v[0], v[1]] for k, v in sorted(base["keys"].items())}}
    out = {}
    for n in sorted(names):
        r = defs.resolve(doc, n)
        if r is None:
            continue
        rec = {"inputs": {k: v[0] for k, v in sorted(r["inputs"].items())},
               "outputs": {k: v[0] for k, v in sorted(r["outputs"].items())},
               "keys": {k: [v[0], v[1]] for k, v in sorted(r["keys"].items())}}
        # What every class has is stored once, under "common".
        out[n] = {f: {k: v for k, v in rec[f].items() if common[f].get(k) != v} for f in rec}
    return {"format": "dot-map-io-catalogue", "version": 1, "notice": doc["_notice"], "common": common, "classes": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    cat = build(defs.load(), a.all)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(cat, f, sort_keys=True, separators=(",", ":"))
        f.write("\n")
    print("%d classes -> %s (%d bytes)" % (len(cat["classes"]), a.out, os.path.getsize(a.out)))


if __name__ == "__main__":
    main()
