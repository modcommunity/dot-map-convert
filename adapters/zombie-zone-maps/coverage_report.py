#!/usr/bin/env python3
"""Where a converted map's missing share of drawn world went, by stage and by place.

    ZZ_DROP_TRACE=/tmp/drops.json python3 -I tools/import_bsp.py tools/bsp/<id>.json <bsp>
    python3 -I tools/coverage_report.py tools/bsp/<id>.json <bsp> /tmp/drops.json [--extra maps/hulls/<id>.nav.json]

completeness.py says how much of the source's drawn face area lies on a box of the document. This
says, for the area that does not, which stage of the importer removed the box that would have covered
it (`cut`, `drop_small`, `drop_buried`, `max_boxes_cap`, ...; the importer writes the trace), whether
the server's nav extra (the budgeted-away boxes, hulls/<id>.nav.json) still holds it, and which parts
of the map it is in (16 m cells, biggest first). Faces with no covering box anywhere are "never boxed"
(displacements, surfaces stepped past the tolerance, anything a stage replaced). It also totals the
volume of every dropped box by stage and kind (solid, clip, nodraw, sky).
"""
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import completeness  # noqa: E402
import import_bsp  # noqa: E402
from dotbsp import reader  # noqa: E402


def kind_of(b):
    return b.get("kind") if b.get("visible", True) is False else "solid"


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    extra_path = argv[argv.index("--extra") + 1] if "--extra" in argv else None
    if extra_path:
        args.remove(extra_path)
    spec_path, bsp_path, trace_path = args[:3]
    spec = json.load(open(spec_path))
    doc = json.load(open(os.path.join(HERE, "..", "maps", spec["id"] + ".json")))
    y0 = float(spec.get("y0", 0.0))
    trace = json.load(open(trace_path))
    extra = json.load(open(extra_path))["boxes"] if extra_path else []
    stages = collections.defaultdict(list)
    for st, b in trace:
        stages[st].append(b)

    print("== dropped boxes by stage and kind (count, volume m3)")
    for st, bs_ in sorted(stages.items()):
        by = collections.defaultdict(lambda: [0, 0.0])
        for b in bs_:
            k = by[kind_of(b)]
            k[0] += 1
            k[1] += b["size"][0] * b["size"][1] * b["size"][2]
        print("  %-16s %6d  %s" % (st, len(bs_), "  ".join("%s %d (%.0f m3)" % (k, c, v) for k, (c, v) in sorted(by.items()))))

    layers = [("wire", doc["boxes"]), ("nav extra", extra)] + [(st, bs_) for st, bs_ in sorted(stages.items())]
    idx = [(name, bx, completeness._grid(bx)) for name, bx in layers if bx]

    bsp = reader.Bsp(bsp_path).load()
    m = bsp.models[0]
    tot = 0.0
    by_stage = collections.Counter()
    by_mat = collections.defaultdict(collections.Counter)
    by_cell = collections.defaultdict(collections.Counter)
    for f in bsp.faces[m[10]:m[10] + m[11]]:
        name, flags = bsp.face_material(f)
        if flags & reader.SKIP_MASK or name.lower().startswith("tools/"):
            continue
        pts = bsp.face_points(f)
        if len(pts) < 3:
            continue
        a = 0.0
        for k in range(1, len(pts) - 1):
            u = [pts[k][j] - pts[0][j] for j in range(3)]
            v = [pts[k + 1][j] - pts[0][j] for j in range(3)]
            cr = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            a += 0.5 * math.sqrt(sum(c * c for c in cr))
        a *= import_bsp.S ** 2
        tot += a
        c = [sum(p[j] for p in pts) / len(pts) for j in range(3)]
        samples = [import_bsp.gpt(q, y0) for q in [c] + [[c[j] + 0.7 * (p[j] - c[j]) for j in range(3)] for p in pts]]
        disp = f[6] >= 0
        for q in samples:
            w = a / len(samples)
            for name_, bx, g in idx:
                if completeness._on_box(q, bx, g):
                    key = "covered (wire)" if name_ == "wire" else name_
                    break
            else:
                key = "never boxed (displacement)" if disp else "never boxed"
            by_stage[key] += w
            if key != "covered (wire)":
                by_mat[key][name.lower()] += w
                by_cell[key][(int(q[0] // 16), int(q[1] // 8), int(q[2] // 16))] += w

    print("\n== drawn face area %.0f m2: share by where its covering box is" % tot)
    for k, v in by_stage.most_common():
        print("  %-28s %9.0f m2  %5.1f%%" % (k, v, 100 * v / tot))
    for k in by_stage:
        if k.startswith("covered"):
            continue
        print("\n== %s: top materials, top places ([x, y, z] ranges of 16/8/16 m cells)" % k)
        print("  materials:", ", ".join("%s %.0f" % kv for kv in by_mat[k].most_common(6)))
        for (cx, cy, cz), v in by_cell[k].most_common(8):
            print("  [%d..%d, %d..%d, %d..%d]  %.0f m2" % (cx * 16, cx * 16 + 16, cy * 8, cy * 8 + 8, cz * 16, cz * 16 + 16, v))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
