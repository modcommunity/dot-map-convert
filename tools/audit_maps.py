#!/usr/bin/env python3
"""The shared audit runner: `bsp.py audit` over a map repository's converted maps, one line per map.

    python3 -P tools/audit_maps.py REPO [id ...] [--max-loss 0.002] [--json OUT] [--src DIR ...] [--passable-kind K] [--passable-class C] [--exempt FILE]

REPO is a map repository (a path, or a name under --godot, default ~/godot). Each map is found its source
.bsp (the repository's `tools/ports.txt`, or a document's `attribution`, or the world's name), audited, and
summarised: lost brush share, lost floor share, the worst class/kind and the worst floor materials.
Read-only: nothing is written but the optional --json.

A map whose importer drops brushes on purpose (scenery out of reach, ground buried under the sea bed, door leaves the bots cannot pass) is
recorded in `REPO/tools/audit_exempt.json` (or --exempt FILE), never by raising --max-loss: `{"id": {"brush_loss": 0.004, "floor_loss": 0.003,
"passes": ["prune_far_scenery"], "why": "..."}}`. The two numbers are ceilings measured with `tools/audit_passes.py`, which names the importer
pass behind each lost brush; the map passes at or under them, so a new loss still fails. `passes` and `why` are required.

Box documents (hide-n-seek, prop-hunt, murder-mystery, game-playground) were shifted by the importer so the
map's origin stands on open ground. A document imported since 2026-11-07 records the shift, the --bounds crop and the
source map's name and hash in `source_frame` (dotbsp/sourceframe.py): the audit then uses that exact frame
(`frame=recorded`), audits only inside the crop, and does no registration. An older document, or one whose recorded
hash is not the .bsp found, falls back to `register()`, which recovers the shift:
an FFT correlation of the source's solid footprints with the boxes' (x, z), a histogram of top heights (y),
then a hill-climb on the brushes collided. The offset found is printed (`at=`): the game-metre vector to ADD
to the document's coordinates to land on the source's. World packs (`worlds/<id>/<id>`, the global
importer's mesh) carry their own y0 and are audited with --mesh.
"""
import argparse
import collections
import glob
import itertools
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np  # noqa: E402
from dotbsp import audit, classes, docboxes, mesh, reader, sourceframe, terrain, units  # noqa: E402

CELL = 0.5       # metres per raster cell for the footprint correlation
SRC_ROOTS = ["~/projects/mapsrc", "~/godot/inspirations"]
# Contents kinds a box document cannot express and a body does not stop at: a ladder is a climbable volume (the document has
# no ladder; the games' bots reach a level by its stairs), not a solid, so its brush and the "floor" on its top are not owed.
DOC_PASSABLE_KINDS = ("ladder",)


def bsp_index(roots):
    idx = collections.defaultdict(list)
    for r in roots:
        for p in glob.glob(os.path.join(os.path.expanduser(r), "**", "*.bsp"), recursive=True):
            idx[os.path.basename(p).lower()].append(p)
    return idx


def load_bsp(path):
    with open(path, "rb") as f:
        return reader.Bsp(path, data=f.read()).load()


def read_ports(repo):
    """{id: (store key or dir, bsp file name)} from tools/ports.txt."""
    out = {}
    p = os.path.join(repo, "tools", "ports.txt")
    if os.path.exists(p):
        for line in open(p):
            f = line.rstrip("\n").split("\t")
            if line.startswith("#") or len(f) < 3:
                continue
            out[f[0]] = (f[1], f[2])
    return out


def solid_brushes(bsp):
    return [bi for bi, (_m, _e, c) in sorted(audit.brush_owners(bsp).items())
            if c == "worldspawn" and bsp.brushes[bi][2] & reader.MASK_PLAYERSOLID
            and audit.contents_kind(bsp.brushes[bi][2], audit._names(bsp, bi)) in audit.COLLIDES]


def solid_boxes(bsp, scale):
    """[(x0, x1, y0, y1, z0, z1)] game metres, one per player-solid worldspawn brush."""
    out = []
    for bi in solid_brushes(bsp):
        pts = bsp.brush_hull(bi)
        if len(pts) < 4:
            continue
        g = [audit.to_game(p, scale) for p in pts]
        out.append(tuple(v for k in range(3) for v in (min(p[k] for p in g), max(p[k] for p in g))))
    return out


def raster(rects, lo, shape):
    img = np.zeros(shape, dtype=np.float32)
    for x0, x1, z0, z1 in rects:
        i0, i1 = int((x0 - lo[0]) // CELL), int((x1 - lo[0]) // CELL)
        j0, j1 = int((z0 - lo[1]) // CELL), int((z1 - lo[1]) // CELL)
        img[max(i0, 0):max(i1 + 1, 0), max(j0, 0):max(j1 + 1, 0)] = 1.0
    return img


def doc_rects(boxes):
    out = []
    for b in boxes:
        if b.get("solid") is False:
            continue
        x, _y, z = b["at"]
        sx, _sy, sz = b["size"]
        yaw = math.radians(b.get("yaw", 0) or 0)
        hx = (abs(math.cos(yaw)) * sx + abs(math.sin(yaw)) * sz) / 2
        hz = (abs(math.sin(yaw)) * sx + abs(math.cos(yaw)) * sz) / 2
        out.append((x - hx, x + hx, z - hz, z + hz))
    return out


class Shifted:
    """A terrain field moved by the registration offset."""
    def __init__(self, field, off):
        self.field, self.off = field, off

    def height(self, x, z):
        h = self.field.height(x - self.off[0], z - self.off[2])
        return None if h is None else h + self.off[1]


def shift_boxes(boxes, off):
    out = []
    for b in boxes:
        c = dict(b)
        c["at"] = [b["at"][0] + off[0], b["at"][1] + off[1], b["at"][2] + off[2]]
        out.append(c)
    return out


def register(bsp, doc, scale):
    """Up to ten candidate vectors (game metres) to add to the document's coordinates to land on the source's."""
    sb = solid_boxes(bsp, scale)
    boxes = [b for b in doc.get("boxes", []) if b.get("solid") is not False]
    if not sb or not boxes:
        return []
    srects = [(a[0], a[1], a[4], a[5]) for a in sb]
    drects = doc_rects(boxes)
    allr = srects + drects
    lo = (min(r[0] for r in allr) - 5, min(r[2] for r in allr) - 5)
    hi = (max(r[1] for r in allr) + 5, max(r[3] for r in allr) + 5)
    shape = (int((hi[0] - lo[0]) / CELL) + 2, int((hi[1] - lo[1]) / CELL) + 2)
    a, b = raster(srects, lo, shape), raster(drects, lo, shape)
    n = (2 * shape[0], 2 * shape[1])
    fa, fb = np.fft.rfft2(a - a.mean(), n), np.fft.rfft2(b - b.mean(), n)
    cc = np.fft.irfft2(fa * np.conj(fb), n)    # cc[s] = sum a[p + s] * b[p]: shift s takes the document to the source
    peaks = []
    flat = np.argsort(cc, axis=None)[::-1]
    for k in flat[:20000]:
        i, j = np.unravel_index(k, cc.shape)
        di = i if i < shape[0] else i - n[0]
        dj = j if j < shape[1] else j - n[1]
        if all(abs(di - p[0]) > 6 or abs(dj - p[1]) > 6 for p in peaks):
            peaks.append((di, dj))
        if len(peaks) == 10:
            break
    return [_with_height(sb, boxes, [float(di * CELL), 0.0, float(dj * CELL)]) for di, dj in peaks]


def _with_height(sb, boxes, off):
    # height: the mode of (source top - document top) over boxes whose columns meet
    tops = collections.Counter()
    cell = 2.0
    stop = collections.defaultdict(set)
    for x0, x1, y0, y1, z0, z1 in sb:
        stop[(int((x0 + x1) / 2 // cell), int((z0 + z1) / 2 // cell))].add(round(y1, 2))
    for bx in boxes:
        k = (int((bx["at"][0] + off[0]) // cell), int((bx["at"][2] + off[2]) // cell))
        t = bx["at"][1] + bx["size"][1] / 2
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for s in stop.get((k[0] + dx, k[1] + dz), ()):
                    tops[round((s - t) / 0.05)] += 1
    if tops:
        off[1] = tops.most_common(1)[0][0] * 0.05
    return off


def brush_hits(bsp, boxes, off, scale, sample, terrain_field=None):
    out = audit.Boxes(shift_boxes(boxes, off), terrain=Shifted(terrain_field, off) if terrain_field else None)
    hit = n = 0
    for bi in sample:
        qs = audit.brush_points(bsp, bi, (0.0, 0.0, 0.0))
        if not qs:
            continue
        n += 1
        hit += any(out.contains(*audit.to_game(q, scale)) for q in qs)
    return hit / n if n else 0.0


def _scorer(bsp, doc, scale, field):
    cand = solid_brushes(bsp)
    sample = cand[::max(1, len(cand) // 250)]
    return lambda t: brush_hits(bsp, doc["boxes"], t, scale, sample, field)


def grid(score, off):
    """The candidate's best neighbour on a grid over x and z (the FFT cell is half a metre and a wall is 0.3 m thick)."""
    best, pick = -1.0, list(off)
    for dx, dz in sorted(itertools.product(range(-6, 7), repeat=2), key=lambda d: d[0] ** 2 + d[1] ** 2):   # a tie keeps the nearest
        t = [off[0] + dx * 0.1, off[1], off[2] + dz * 0.1]
        v = score(t)
        if v > best + 1e-9:
            best, pick = v, t
    return pick, best


def climb(score, off, best):
    """A hill-climb that also moves diagonally, so it does not stop on a ridge where one axis alone loses hits."""
    moves = [m for m in itertools.product((-1, 0, 1), repeat=3) if any(m)]
    for step in (0.1, 0.03, 0.01):
        moved = True
        while moved:
            moved = False
            for m in moves:
                t = [off[k] + m[k] * step for k in range(3)]
                v = score(t)
                if v > best + 1e-9:
                    off, best, moved = t, v, True
    return [round(float(v), 3) for v in off], float(best)


def refine(bsp, doc, cands, scale, field, keep=3):
    """(offset, hit share) of the best of the FFT candidates: all gridded, the best `keep` climbed."""
    score = _scorer(bsp, doc, scale, field)
    ranked = sorted((grid(score, c) for c in cands), key=lambda t: -t[1])[:keep]
    return max((climb(score, o, h) for o, h in ranked), key=lambda t: t[1])


def load_exempt(path):
    """{map id: {brush_loss, floor_loss, passes, why}} from an `audit_exempt.json`; {} when there is none. A row without `why` or `passes` is refused."""
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        rows = json.load(f)
    for mid, ex in rows.items():
        if not str(ex.get("why", "")).strip() or not ex.get("passes"):
            raise SystemExit("%s: %s is an exemption without a reason: it needs `why` and the importer `passes` behind the loss" % (path, mid))
        for k in ("brush_loss", "floor_loss"):
            if not isinstance(ex.get(k, 0.0), (int, float)):
                raise SystemExit("%s: %s.%s is not a number" % (path, mid, k))
    return rows


def apply_exempt(r, ex, max_loss):
    """Marks summary `r` as passing when it is within the map's recorded ceilings; returns "ok", "exempt" or "LOSS"."""
    if "ok" not in r:
        return "LOSS"
    if r["ok"]:
        return "ok"
    if ex and r["brush_loss"] <= max(max_loss, ex.get("brush_loss", 0.0)) and r["floor_loss"] <= max(max_loss, ex.get("floor_loss", 0.0)):
        r["ok"], r["exempt"] = True, ex
        return "exempt"
    return "LOSS"


def summary(r, max_loss):
    bl = 1.0 - r["brushes_collided"] / r["brushes_expected"] if r["brushes_expected"] else 0.0
    fl = r["floor_missed"] / r["floor_samples"] if r["floor_samples"] else 0.0
    worst = sorted(((v[1] - v[2], k) for k, v in r["brushes"].items() if v[1] and v[2] < v[1]), reverse=True)[:6]
    wf = sorted(((v[0], k, v[1]) for k, v in r["floors"].items()), reverse=True)[:3]
    return {"brush_loss": bl, "floor_loss": fl, "brushes": (r["brushes_collided"], r["brushes_expected"]),
            "floors": (r["floor_samples"] - r["floor_missed"], r["floor_samples"]),
            "worst_brushes": [(k, n) for n, k in worst], "worst_floors": [(k.replace("|", " "), m, n) for m, k, n in wf],
            "ok": bl <= max_loss and fl <= max_loss}


def recorded_frame(doc, bsp_path):
    """The document's `source_frame` when it describes this .bsp (same hash, when it records one), else None."""
    sf = sourceframe.read(doc)
    if sf is None:
        return None
    if sf.get("sha256") and sf["sha256"] != sourceframe.file_sha256(bsp_path):
        return None
    return sf


def keep_of(sf):
    """The audit's region for a recorded crop (--within/--band), or None for the whole map."""
    if not sf or not (sf.get("crop") or sf.get("crop_band")):
        return None
    return audit.region(",".join(map(str, sf["crop"])) if sf.get("crop") else None,
                        ",".join(map(str, sf["crop_band"])) if sf.get("crop_band") else None)


def run_doc(bsp_path, doc_path, scale, max_loss, passable=(), skip_kinds=DOC_PASSABLE_KINDS, detail=False):
    bsp = load_bsp(bsp_path)
    with open(doc_path) as f:
        doc = json.load(f)
    field = terrain.Heightfield.decode(doc["terrain"])[0] if doc.get("terrain") else None
    sf = recorded_frame(doc, bsp_path)
    keep = None
    if sf:
        # the importer's own shift: exact, so nothing is searched and the fit is only reported
        scale = sf.get("scale") or scale
        off = [float(v) for v in sf["offset"]]
        cand = solid_brushes(bsp)
        hit = brush_hits(bsp, doc.get("boxes", []), off, scale, cand[::max(1, len(cand) // 250)], field)
        keep = keep_of(sf)
    else:
        cands = register(bsp, doc, scale)
        if not cands:
            return {"error": "no boxes or no source brushes"}
        off, hit = refine(bsp, doc, cands, scale, field)
    out = audit.Boxes(shift_boxes(doc.get("boxes", []), off), terrain=Shifted(field, off) if field else None)
    cl = lambda c: c == "worldspawn" or (classes.treatment(c)[0] == "world" and c not in passable)  # noqa: E731
    # A brush entity that starts not solid (Solidity 1, StartDisabled, rendermode 10, a toggle that starts off) is left out by every box importer
    # (docboxes.entity_starts_hidden): a box document has no switch, so it is not owed.
    res = audit.audit(bsp, out, scale, 0.0, cl, keep=keep, skip_kinds=skip_kinds, skip_entity=docboxes.entity_starts_hidden)
    s = summary(res, max_loss)
    if detail:
        s["lost"] = res["brushes_lost"]
        s["floor_lost"] = res["floor_missed_points"]
    s.update(offset=off, fit=hit, frame="recorded" if sf else "registered", cropped=keep is not None)
    return s


def run_mesh(bsp_path, prefix, max_loss):
    bsp = load_bsp(bsp_path)
    man, m = mesh.read(prefix)
    return summary(audit.audit(bsp, audit.Hulls(m.hulls), man["units"]["metres_per_unit"], man["units"]["y0"], None), max_loss)


def targets(repo, idx, only):
    """[(id, bsp path or None, kind, doc or mesh prefix, note)]"""
    name = os.path.basename(repo.rstrip("/"))
    ports = read_ports(repo)
    out = []

    def find(fname):
        c = [p for p in idx.get(fname.lower(), []) if os.path.exists(p)]
        return c[0] if c else None

    def by_source(doc, mid):
        """The .bsp in the mapsrc directory named for the document's source id (a Workshop or GameBanana number)."""
        m = re.search(r"id=(\d+)|/(\d+)\s*$", str(doc.get("source") or ""))
        if not m:
            return None
        n = m.group(1) or m.group(2)
        cands = [p for ps in idx.values() for p in ps if os.path.exists(p) and re.search(r"/(?:gb)?%s/" % n, p)]
        if not cands:
            return None
        pref = [p for p in cands if os.path.basename(p)[:-4].lower() in mid.lower() or mid.lower().split("_", 1)[-1] in os.path.basename(p).lower()]
        return (pref or sorted(cands, key=os.path.getsize, reverse=True))[0]

    if name in ("arena-surf-dm-maps", "g2gfast-maps"):
        for d in sorted(glob.glob(os.path.join(repo, "worlds", "*", "*.json")) + glob.glob(os.path.join(repo, "worlds", "*.json"))):
            if d.endswith((".coverage.json", ".doc.json", "credits.json")):
                continue
            mid = os.path.basename(d)[:-5]
            out.append((mid, find(mid + ".bsp"), "mesh", d[:-5], ""))
        return [t for t in out if not only or t[0] in only]
    for d in sorted(glob.glob(os.path.join(repo, "maps", "*.json"))):
        mid = os.path.basename(d)[:-5]
        if only and mid not in only:
            continue
        doc = json.load(open(d))
        fname = None
        path_bsp = None
        if mid in ports:
            fname = ports[mid][1]
            path_bsp = find(fname)
        else:
            m = re.search(r"converted from (\w+)", str(doc.get("attribution") or ""), re.I)
            if m:
                fname = m.group(1) + ".bsp"
                path_bsp = find(fname)
        sf = sourceframe.read(doc)
        if sf and sf.get("map"):
            cands = [p for p in idx.get(sf["map"].lower(), []) if os.path.exists(p)]
            hashed = [p for p in cands if sf.get("sha256") and sourceframe.file_sha256(p) == sf["sha256"]]
            path_bsp = (hashed or ([path_bsp] if path_bsp else []) or cands or [None])[0]
            fname = fname or sf["map"]
        path_bsp = path_bsp or by_source(doc, mid)
        # last: a .bsp named for the map itself (ph_abandoned_church) or for it without its game prefix (mm_mu_hotel: mu_hotel)
        path_bsp = path_bsp or find(mid + ".bsp") or (find(mid.split("_", 1)[1] + ".bsp") if "_" in mid else None)
        out.append((mid, path_bsp, "doc", d, "" if (fname or doc.get("source")) else "hand-built (no source map)"))
    return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repo")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--godot", default=os.path.expanduser("~/godot"))
    ap.add_argument("--max-loss", type=float, default=0.002)
    ap.add_argument("--src", action="append", default=[])
    ap.add_argument("--passable-kind", action="append", default=None, metavar="KIND",
                    help="contents kind not owed to a box document (repeatable; default %s)" % ", ".join(DOC_PASSABLE_KINDS))
    ap.add_argument("--passable-class", action="append", default=[], metavar="CLASS",
                    help="brush entity class not owed to a box document (repeatable)")
    ap.add_argument("--exempt", help="recorded exemptions (default REPO/tools/audit_exempt.json)")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    repo = a.repo if os.path.isdir(a.repo) else os.path.join(a.godot, a.repo)
    exempt = load_exempt(a.exempt or os.path.join(repo, "tools", "audit_exempt.json"))
    idx = bsp_index(a.src or SRC_ROOTS)
    rows = {}
    for mid, bsp, kind, path, note in targets(repo, idx, set(a.ids)):
        if not bsp:
            rows[mid] = {"skip": note or "source .bsp not found"}
            print("%-28s SKIP  %s" % (mid, rows[mid]["skip"]), flush=True)
            continue
        try:
            r = run_doc(bsp, path, units.VISUAL, a.max_loss, a.passable_class, tuple(a.passable_kind or DOC_PASSABLE_KINDS)) if kind == "doc" else run_mesh(bsp, path, a.max_loss)
        except Exception as e:    # one bad map never stops the run
            r = {"error": "%s: %s" % (type(e).__name__, e)}
        rows[mid] = r
        if "error" in r:
            print("%-28s ERROR %s" % (mid, r["error"]), flush=True)
            continue
        if r.get("fit") is None:
            fit = ""
        elif r.get("frame") == "recorded":
            fit = " fit=%.2f at=%s frame=recorded%s" % (r["fit"], r["offset"], " cropped" if r.get("cropped") else "")
        else:
            fit = " fit=%.2f at=%s%s" % (
                r["fit"], r["offset"], "  FRAME? (a crop, or a registration miss: not trusted)" if r["fit"] < 0.8 else "")
        verdict = apply_exempt(r, exempt.get(mid), a.max_loss)
        print("%-28s %s brushes %.4f (%d/%d) floor %.4f (%d/%d)%s" % (
            mid, {"ok": "ok  ", "exempt": "EXMP", "LOSS": "LOSS"}[verdict], r["brush_loss"], *r["brushes"], r["floor_loss"], *r["floors"], fit), flush=True)
        if verdict == "exempt":
            ex = exempt[mid]
            print("      exempt up to brushes %.4f floor %.4f (%s): %s" % (ex.get("brush_loss", 0.0), ex.get("floor_loss", 0.0), ", ".join(ex["passes"]), ex["why"]))
        elif mid in exempt:
            print("      exemption no longer needed: under %.4f" % a.max_loss)
        if not r["ok"]:
            for k, n in r["worst_brushes"]:
                print("      lost brushes %4d  %s" % (n, k.replace("|", " ")))
            for k, m, n in r["worst_floors"]:
                print("      floor misses %4d of %d  %s" % (m, n, k))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rows, f, indent=1, sort_keys=True)
    bad = [m for m, r in rows.items() if "ok" in r and not r["ok"]]
    print("%d maps: %d audited, %d over %.4f, %d skipped, %d errors" % (
        len(rows), sum("ok" in r for r in rows.values()), len(bad), a.max_loss,
        sum("skip" in r for r in rows.values()), sum("error" in r for r in rows.values())))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
