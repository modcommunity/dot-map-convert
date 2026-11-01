#!/usr/bin/env python3
"""How much of a converted map's drawn world the document still has.

    tools/completeness.py --src DIR                       # every spec in tools/bsp/
    tools/completeness.py --src DIR tools/bsp/zm_x.json   # these
    tools/completeness.py --src DIR spec.json:doc.json    # a document somewhere else

For every drawn face of the source's world (tool textures and sky skipped), the share of its area
whose sample points (the centre and each corner pulled 70% towards it) lie within 0.12 m of a box
of `maps/<id>.json`, area-weighted over the map. A map below its spec's `min_coverage` (default
0.80) fails: the count of boxes against brushes says nothing, because one brush is cut into many
boxes and a dropped arch is still "a lot of boxes".

A map over the wire budget keeps the boxes the budget dropped in maps/hulls/<id>.nav.json (server-only);
the second line counts those too. tools/coverage_report.py says which stage dropped what is left.

Why it exists: 4-Way Tunnel shipped with 11.7% of its world (a `cut` that took the east half for a
skybox it is not, and `drop_ramps` taking every slab-cut brush, which is every tunnel wall and arch
in the map), and every suite passed, because the graph, the route and the gates were all on the
piece that was left. Displacements and water are not boxes, so a map that is mostly terrain or
sea, or one cropped on purpose, sets a lower `min_coverage` in its spec and says why.

The BSPs are not in this repository (they are the authors'); a spec whose source is not found
under `--src` (or $ZZ_BSP_SRC) is listed as skipped, not failed.
"""
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import import_bsp  # noqa: E402  (finds dot-map-convert and puts it on the path)
from dotbsp import reader  # noqa: E402

TOL = 0.12
DEFAULT_MIN = 0.80


def _grid(boxes):
    g = {}
    for i, b in enumerate(boxes):
        (x, _y, z), (sx, _sy, sz) = b["at"], b["size"]
        r = 0.5 * max(math.hypot(sx, sz), 0.01) + TOL
        for cx in range(int(math.floor((x - r) / 4)), int(math.floor((x + r) / 4)) + 1):
            for cz in range(int(math.floor((z - r) / 4)), int(math.floor((z + r) / 4)) + 1):
                g.setdefault((cx, cz), []).append(i)
    return g


def _on_box(p, boxes, g):
    for i in g.get((int(math.floor(p[0] / 4)), int(math.floor(p[2] / 4))), ()):
        b = boxes[i]
        (x, y, z), (sx, sy, sz) = b["at"], b["size"]
        dx, dy, dz = p[0] - x, p[1] - y, p[2] - z
        if abs(dy) > sy / 2 + TOL:
            continue
        yaw = math.radians(b.get("yaw", 0.0))
        # Either sense of yaw: a small error in the document's convention must not read as a hole.
        for s in ((1, -1) if yaw else (1,)):
            c, sn = math.cos(s * yaw), math.sin(s * yaw)
            lx, lz = c * dx - sn * dz, sn * dx + c * dz
            if abs(lx) <= sx / 2 + TOL and abs(lz) <= sz / 2 + TOL:
                return True
    return False


def _find(src_dirs, name):
    for root in src_dirs:
        for p in glob.glob(os.path.join(root, "**", name), recursive=True):
            return p
    return None


def measure(bsp_path, doc, y0, extra=()):
    """(covered share, displacement share, drawn m2, share with `extra` boxes too) of the BSP's world faces."""
    bsp = reader.Bsp(bsp_path).load()
    boxes = doc["boxes"]
    g = _grid(boxes)
    both = list(boxes) + list(extra)
    g2 = _grid(both) if extra else g
    tot = cov = cov2 = disp = 0.0
    m = bsp.models[0]
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
        if f[6] >= 0:
            disp += a
        c = [sum(p[j] for p in pts) / len(pts) for j in range(3)]
        samples = [c] + [[c[j] + 0.7 * (p[j] - c[j]) for j in range(3)] for p in pts]
        hit = sum(_on_box(import_bsp.gpt(q, y0), boxes, g) for q in samples) / len(samples)
        tot += a
        cov += a * hit
        cov2 += a * (sum(_on_box(import_bsp.gpt(q, y0), both, g2) for q in samples) / len(samples) if extra else hit)
    if not tot:
        return 0.0, 0.0, 0.0, 0.0
    return cov / tot, disp / tot, tot, cov2 / tot


def main(argv):
    src_dirs, specs = [], []
    it = iter(argv[1:])
    for a in it:
        if a == "--src":
            src_dirs.append(next(it))
        else:
            specs.append(a)
    src_dirs += [d for d in os.environ.get("ZZ_BSP_SRC", "").split(":") if d]
    if not src_dirs:
        sys.exit("completeness: name the directory holding the source BSPs with --src (or $ZZ_BSP_SRC)")
    specs = specs or sorted(glob.glob(os.path.join(HERE, "bsp", "*.json")))
    failed = skipped = 0
    for sp in specs:
        doc_path = None
        if ":" in sp:
            sp, doc_path = sp.split(":", 1)
        spec = json.load(open(sp))
        doc_path = doc_path or os.path.join(HERE, "..", "maps", spec["id"] + ".json")
        src = _find(src_dirs, spec["source"])
        if not src or not os.path.exists(doc_path):
            print("%-26s skipped (%s not found)" % (spec["id"], spec["source"] if not src else doc_path))
            skipped += 1
            continue
        nav_extra = os.path.join(os.path.dirname(doc_path), "hulls", spec["id"] + ".nav.json")
        extra = json.load(open(nav_extra)).get("boxes", []) if os.path.exists(nav_extra) else []
        share, disp, area, with_extra = measure(src, json.load(open(doc_path)), float(spec.get("y0", 0.0)), extra)
        need = float(spec.get("min_coverage", DEFAULT_MIN))
        ok = share >= need
        failed += not ok
        print("%-26s %5.1f%% of %6.0f m2 drawn (displacements %4.1f%%), needs %4.1f%%  %s"
              % (spec["id"], 100 * share, area, 100 * disp, 100 * need, "ok" if ok else "FAILED"))
        if extra:
            print("%-26s %5.1f%% with the server's nav extra (maps/hulls/%s.nav.json); the rest collides through the world hulls"
                  % ("", 100 * with_extra, spec["id"]))
    print("completeness: %d map(s) below their threshold, %d skipped" % (failed, skipped))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
