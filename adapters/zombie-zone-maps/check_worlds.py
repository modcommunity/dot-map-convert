"""Fails when a drawn world's manifest is unreadable or disagrees with its .bin, its map document or itself.

    python3 -I tools/check_worlds.py [world_root]

Every `world/zz_world_<id>/<id>.json` must parse, be a `dot-bsp-mesh` v1 with the entity sections
tools/build_worlds.py writes, name a .bin whose stored sha256 matches, belong to a document that
names it, and every mover must have the model its game animates (surfaces, and hulls when it is
carried solid). It also fails a bin whose hull bounds disagree with its mover records, or with the document's boxes and spawns, in height: a bin built without the spec's y0 sits y0 metres off its movers. Runs on the committed files alone, so CI needs no source map.
"""

import gzip
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SECTIONS = ("movers", "volumes", "links", "entities")
CARRIED = {"slide", "rotate", "plat", "path"}
# A mover record's box and its model's hull points are the same numbers; they differ by y0 when the bin was built without it.
MOVER_TOL = 0.05
# The document's drawn boxes are a subset of the world, so they may sit inside its hull bounds, never outside.
DOC_TOL = 1.0


def hull_bounds(m, data):
    """{model: [x0, y0, z0, x1, y1, z1]} over every hull point of the bin (sky brushes included: the document's boxes reach them)."""
    out = {}
    for h in m["hulls"]:
        n, off = h["point_count"], h["point_offset"]
        pts = struct.unpack_from("<%df" % (3 * n), data, off)
        b = out.setdefault(h["model"], [1e9, 1e9, 1e9, -1e9, -1e9, -1e9])
        for i in range(n):
            for a in range(3):
                b[a] = min(b[a], pts[3 * i + a])
                b[3 + a] = max(b[3 + a], pts[3 * i + a])
    return out


def check_alignment(pack, m, data, doc):
    """Problems where the bin's geometry and the movers or the document disagree on height (a lost y0)."""
    bad = []
    bounds = hull_bounds(m, data)
    for r in m["movers"]:
        h = bounds.get(r.get("model"))
        if h is None or len(r.get("mins", [])) != 3:
            continue
        err = max(max(abs(h[a] - r["mins"][a]), abs(h[3 + a] - r["maxs"][a])) for a in range(3))
        if err > MOVER_TOL:
            bad.append("%s mover %s: its hull is %.2f m from its record (y0 %s not applied to the bin?)" % (
                pack, r.get("targetname") or r["entity"], err, m["units"].get("y0")))
    h0 = bounds.get(0)
    if doc is not None and h0 is not None:
        boxes = [b for b in doc.get("boxes", []) if b.get("visible", True)]
        if boxes:
            lo = min(b["at"][1] - b["size"][1] / 2 for b in boxes)
            hi = max(b["at"][1] + b["size"][1] / 2 for b in boxes)
            if lo < h0[1] - DOC_TOL or hi > h0[4] + DOC_TOL:
                bad.append("%s: the document's boxes span y %.1f..%.1f outside the world's %.1f..%.1f" % (pack, lo, hi, h0[1], h0[4]))
        for s in (doc.get("spawns") or {}).get("survivors", []):
            if not h0[1] - DOC_TOL <= s["at"][1] <= h0[4] + DOC_TOL:
                bad.append("%s: a survivor spawn at y %.1f is outside the world's %.1f..%.1f" % (pack, s["at"][1], h0[1], h0[4]))
                break
    return bad


def check(pack_dir):
    """The problems found in one world directory, as strings."""
    pack = os.path.basename(pack_dir)
    map_id = pack[len("zz_world_"):]
    bad = []
    path = os.path.join(pack_dir, map_id + ".json")
    try:
        with open(path) as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        return ["%s: does not parse: %s" % (path, e)]
    if m.get("format") != "dot-bsp-mesh" or m.get("version") not in (1, 2):
        bad.append("%s: not a dot-bsp-mesh v1 or v2" % pack)
    for k in SECTIONS:
        if not isinstance(m.get(k), list):
            bad.append("%s: no '%s' list (rebuild with tools/build_worlds.py)" % (pack, k))
    if not isinstance(m.get("destinations"), dict):
        bad.append("%s: no 'destinations' table" % pack)
    if bad:
        return bad
    data = None
    try:
        with open(os.path.join(pack_dir, m["bin"]["file"]), "rb") as f:
            stored = f.read()
        data = gzip.decompress(stored) if m["bin"].get("compression") == "gzip" else stored
        if hashlib.sha256(stored).hexdigest() != m["bin"]["sha256"] or len(stored) != m["bin"]["stored_bytes"]:
            bad.append("%s: the .bin is not the one the manifest describes" % pack)
    except (OSError, KeyError) as e:
        bad.append("%s: no .bin: %s" % (pack, e))
    # A pack from dot-map's global importer carries no "zz" block (the game reads it as a global pack).
    if "zz" in m and not isinstance(m["zz"].get("materials"), dict):
        bad.append("%s: no zz.materials" % pack)
    drawn = {s["model"] for s in m["surfaces"]}
    hulled = {h["model"] for h in m["hulls"]}
    for r in m["movers"]:
        who = "%s mover %s (%s)" % (pack, r.get("targetname") or r["entity"], r["kind"])
        if r.get("model") is None:
            # A prop mover (a door model, not a brush) is placed from its model path.
            if not r.get("model_path"):
                bad.append("%s: neither a brush model nor a model_path" % who)
            keys = ("origin",)
        else:
            if r["model"] not in drawn and r["model"] not in hulled:
                bad.append("%s: its model has neither surfaces nor hulls" % who)
            elif r["kind"] in CARRIED and r.get("solid", True) and r["model"] not in hulled:
                bad.append("%s: solid but has no hull" % who)
            keys = ("origin", "mins", "maxs")
        for k in keys:
            if len(r.get(k, [])) != 3:
                bad.append("%s: no %s" % (who, k))
    for rec in m["links"]:
        for k in ("from", "output", "input", "target", "delay"):
            if k not in rec:
                bad.append("%s: a link has no '%s'" % (pack, k))
                break
    docp = os.path.join(HERE, "..", "maps", map_id + ".json")
    doc = None
    if os.path.isfile(docp):
        with open(docp) as f:
            doc = json.load(f)
        if doc.get("world") != pack:
            bad.append("%s: maps/%s.json does not name it" % (pack, map_id))
        # dot-map's SOLID_BOX: a deployed server has no world/, so its document must carry the boxes (tools/solid_props.sh).
        solid = sum(1 for p in m.get("props", []) if "box" not in p and int(p.get("solid", 0)) in (2, 3, 4, 6))
        if solid and not doc.get("solid_props"):
            bad.append("%s: %d solid props and no 'solid_props' in maps/%s.json (run tools/solid_props.sh)" % (pack, solid, map_id))
    if data is not None:
        bad += check_alignment(pack, m, data, doc)
    return bad


def main(argv):
    root = argv[1] if len(argv) > 1 else os.path.join(HERE, "..", "world")
    dirs = sorted(d for d in os.listdir(root) if d.startswith("zz_world_"))
    bad = []
    for d in dirs:
        bad += check(os.path.join(root, d))
    for line in bad:
        print("FAIL " + line)
    print("%d worlds, %d problems" % (len(dirs), len(bad)))
    return 1 if bad or not dirs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
