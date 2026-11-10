#!/usr/bin/env python3
"""Fits a COMMITTED box document to a budget, in place: the importer's --max-boxes / --max-wire passes without a re-import.

    python3 -P tools/fit_doc.py MAPS_REPO_TOOLS_DIR DOC.json [--max-boxes=N] [--max-wire=BYTES] [--out=FILE]

MAPS_REPO_TOOLS_DIR is the map repository's `tools/` (its build_maps.py gives the prop sizes and footprints, which the props the cut
boxes leave hanging or buried are dropped by). A re-import throws a tuned map's props, balance and fixes away; this keeps them and
only cuts the smallest unprotected boxes (floors, stairs, door frames and the ground under an anchor stay, lost reach is restored),
rounding to centimetres first. Prints the box count, the wire size and the spawns' reach before and after.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from dotbsp import docboxes  # noqa: E402


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    tools, path = args
    out = path
    budget = {}
    for a in argv[1:]:
        if a.startswith("--out="):
            out = a[6:]
        elif a.startswith("--") and not docboxes.budget_flag(a, budget):
            sys.exit("unknown flag %s" % a)
    if not budget:
        sys.exit("give --max-boxes and/or --max-wire")
    sys.path.insert(0, tools)
    import build_maps  # noqa: E402
    doc = json.load(open(path))
    print("before: %d boxes, %d props, %d bytes on the wire" % (len(doc["boxes"]), len(doc["props"]), docboxes.wire_size(doc)))
    docboxes.apply_cap(doc, budget, size_of=build_maps.size_of, footprint=build_maps.footprint)
    print("after: %d boxes, %d props, %d bytes on the wire" % (len(doc["boxes"]), len(doc["props"]), docboxes.wire_size(doc)))
    with open(out, "w") as f:
        f.write(json.dumps(doc, indent=1) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv)
