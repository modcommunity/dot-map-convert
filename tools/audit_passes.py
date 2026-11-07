#!/usr/bin/env python3
"""Attributes a box document's audit loss to the importer pass that removed the boxes: `python3 -I tools/audit_passes.py BSP DOC [--json OUT]`.

DOC is a document an importer wrote with DOTBSP_PASS_LEDGER=1, so `DOC.passes.json` (dotbsp/passledger.py) sits beside it. The
document is audited as it is, then once per pass with that pass's removed boxes put back, then with every pass's boxes put back;
the drop in lost brushes and in missed floor is what that pass explains. A pass that restores nothing explains none of the loss.
Passes overlap (a brush lost to two passes comes back with either), so the shares can add to more than the total.
"""
import argparse
import collections
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import audit_maps  # noqa: E402
import numpy as np  # noqa: E402
from dotbsp import audit, docboxes, units  # noqa: E402


def audit_with(bsp, doc, extra, max_loss=0.002):
    d = dict(doc)
    d["boxes"] = list(doc["boxes"]) + extra
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(d, f)
    try:
        r = audit_maps.run_doc(bsp, f.name, units.VISUAL, max_loss, detail=True)
    finally:
        os.unlink(f.name)
    return r


def what(boxes):
    """A short description of removed boxes: the commonest materials, how many are unseen, the largest."""
    mats = collections.Counter(b.get("mat", "?") for b in boxes)
    unseen = sum(1 for b in boxes if b.get("visible", True) is False)
    big = max(boxes, key=lambda b: b["size"][0] * b["size"][1] * b["size"][2]) if boxes else None
    s = ""
    if big:
        s = " largest %.1fx%.1fx%.1f at y=%.1f" % (*big["size"], big["at"][1])
    return "%s unseen=%d%s" % (",".join("%s:%d" % kv for kv in mats.most_common(3)), unseen, s)


def unexplained(bsp_path, lost, log=print, top=8):
    """Groups the brushes no pass explains by class, contents kind and a side material (+ extent), so the cause can be read."""
    bsp = audit_maps.load_bsp(bsp_path)
    groups = collections.defaultdict(list)
    for bi, cls, kind, _pt in lost:
        names = audit._names(bsp, bi)
        mat = collections.Counter(n.lower() for n in names).most_common(1)
        pts = bsp.brush_hull(bi)
        ext = max((max(p[i] for p in pts) - min(p[i] for p in pts)) for i in range(3)) if pts else 0.0
        groups[(cls, kind, mat[0][0] if mat else "?")].append(ext)
    rows = sorted(groups.items(), key=lambda kv: -len(kv[1]))[:top]
    for (cls, kind, mat), ext in rows:
        log("      %4d  %s %s  %s  (longest side %d..%d units)" % (len(ext), cls, kind, mat, min(ext), max(ext)))
    return [{"class": c, "kind": k, "material": m, "n": len(e), "ext_min": min(e), "ext_max": max(e)} for (c, k, m), e in rows]


def gaps(removed, kept):
    """How far the pruned clusters stand from what the document kept: [(gap m, boxes, m3, lowest y, highest y)] nearest first.

    Removed boxes that touch (a quarter metre) form a cluster; its gap is the nearest distance from any of its boxes to a kept
    solid box. A cluster a body cannot cross to (a void wider than a few metres) is scenery; one within 3 m is a room or a
    stair the play space may reach, which is a bug if it was pruned."""
    def arr(bs):
        return np.array([[b["at"][i] - b["size"][i] / 2 for i in range(3)] + [b["at"][i] + b["size"][i] / 2 for i in range(3)] for b in bs])
    kept = [b for b in kept if b.get("solid", True) and not b.get("yaw")]
    if not removed or not kept:
        return []
    r, k = arr(removed), arr(kept)
    n = len(r)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        g = np.maximum(0, np.maximum(r[:, :3] - r[i, 3:], r[i, :3] - r[:, 3:])).max(axis=1)
        for j in np.nonzero(g <= 0.25)[0]:
            parent[find(i)] = find(int(j))
    comps = collections.defaultdict(list)
    for i in range(n):
        comps[find(i)].append(i)
    rows = []
    for ids in comps.values():
        sub = r[ids]
        best = 1e9
        for q in sub[::max(1, len(sub) // 60)]:
            best = min(best, float(np.sqrt((np.maximum(0, np.maximum(k[:, :3] - q[3:], q[:3] - k[:, 3:])) ** 2).sum(axis=1)).min()))
        rows.append((round(best, 2), len(ids), round(float((sub[:, 3:] - sub[:, :3]).prod(axis=1).sum()), 1), round(float(sub[:, 1].min()), 1), round(float(sub[:, 4].max()), 1)))
    return sorted(rows)


GAP_PASSES = ("prune_far_scenery",)


def walkable_from_spawn(doc, removed, cell=0.5):
    """(floor cells of the removed boxes that a body can walk to from the first spawn, floor cells the removed boxes have): the
    document's boxes with the removed ones put back, walked as docboxes.floor_islands does (a 0.4 m step, no body radius)."""
    solid = [b for b in removed if b.get("solid", True)]
    spawns = [sp["at"] for side in doc.get("spawns", {}).values() for sp in side]
    if not solid or not spawns:
        return None
    islands, state_of, (x0, z0, c) = docboxes.floor_islands(list(doc["boxes"]) + solid, cell=cell)
    state = None
    for sp in spawns[:6]:
        for dy in (0.0, -0.05, -0.1, -0.2):
            state = state_of(sp[0], sp[2], sp[1] + dy)
            if state:
                break
        if state:
            break
    if state is None:
        return None
    reached = {(zi, xi, round(t, 3)) for (zi, xi), t in islands[state[0]][1]}
    total = hit = 0
    for b in solid:
        top = round(b["at"][1] + b["size"][1] / 2, 3)
        hx, hz = b["size"][0] / 2, b["size"][2] / 2
        for zi in range(int((b["at"][2] - hz - z0) / c), int((b["at"][2] + hz - z0) / c) + 2):
            for xi in range(int((b["at"][0] - hx - x0) / c), int((b["at"][0] + hx - x0) / c) + 2):
                if docboxes.within(b, x0 + (xi + 0.5) * c, z0 + (zi + 0.5) * c):
                    total += 1
                    hit += (zi, xi, top) in reached
    return hit, total


def attribute(bsp, doc_path, log=print):
    with open(doc_path) as f:
        doc = json.load(f)
    with open(doc_path + ".passes.json") as f:
        led = json.load(f)
    base = audit_with(bsp, doc, [])
    out = {"base": {"brush_loss": base["brush_loss"], "floor_loss": base["floor_loss"], "brushes": list(base["brushes"])}, "passes": {}}
    log("%-26s brushes %.4f floor %.4f  (%d/%d)" % ("as written", base["brush_loss"], base["floor_loss"], *base["brushes"]))
    out["base"]["worst_brushes"] = base["worst_brushes"]
    log("   lost by class/kind: %s" % ", ".join("%s %d" % (k.replace("|", " "), n) for k, n in base["worst_brushes"]))
    every = []
    pkey = lambda m: tuple(round(v, 3) for v in m[0])  # noqa: E731
    floor0 = {pkey(m): m for m in base["floor_lost"]}
    floor_left = set(floor0)
    lost0 = {l[0] for l in base["lost"]}
    left = set(lost0)
    by_pass = {}
    for name in led["order"]:
        row = led["passes"][name]
        boxes = row["boxes"]
        every += boxes
        if not boxes:
            continue
        r = audit_with(bsp, doc, boxes)
        back = lost0 - {l[0] for l in r["lost"]}
        by_pass[name] = len(back)
        fback = set(floor0) - {pkey(m) for m in r["floor_lost"]}
        floor_left -= fback
        left -= back
        gp = gaps(boxes, doc["boxes"]) if name in GAP_PASSES else None
        out["passes"][name] = {"removed": row["removed"], "removed_m3": row["removed_m3"], "added_m3": row["added_m3"],
                               "lost_brushes_back": len(back), "floor_samples_back": len(fback),
                               "brush_gain": base["brush_loss"] - r["brush_loss"], "floor_gain": base["floor_loss"] - r["floor_loss"],
                               "what": what(boxes), "clusters": gp}
        log("%-26s removed %5d (%.1f m3) brings back %3d lost brushes (%+.4f), %3d floor samples (%+.4f)  %s" % (
            name, row["removed"], row["removed_m3"], len(back), out["passes"][name]["brush_gain"], len(fback), out["passes"][name]["floor_gain"], out["passes"][name]["what"]))
        if name in GAP_PASSES:
            wk = walkable_from_spawn(doc, boxes)
            out["passes"][name]["walkable_from_spawn"] = wk
            log("      floor of the removed boxes a body can walk to from a spawn: %s" % ("not measured" if wk is None else "%d of %d cells" % wk))
        if gp:
            log("      %d clusters, nearest %.1f m from what is kept (%d boxes), %d within 3 m: %s" % (
                len(gp), gp[0][0], gp[0][1], sum(1 for g in gp if g[0] < 3.0), "; ".join("%.1f m/%d boxes/%.0f m3" % g[:3] for g in gp[:4])))
    if every:
        r = audit_with(bsp, doc, every)
        out["all"] = {"brush_loss": r["brush_loss"], "floor_loss": r["floor_loss"]}
        out["all"]["worst_brushes"] = r["worst_brushes"]
        log("%-26s brushes %.4f floor %.4f" % ("every pass restored", r["brush_loss"], r["floor_loss"]))
        log("   still lost by class/kind: %s" % ", ".join("%s %d" % (k.replace("|", " "), n) for k, n in r["worst_brushes"]))
    lostrows = [l for l in base["lost"] if l[0] in left]
    log("   %d of %d lost brushes are explained by no pass:" % (len(lostrows), len(lost0)))
    out["unexplained"] = unexplained(bsp, lostrows, log) if lostrows else []
    fl = collections.Counter((floor0[k][1], floor0[k][2], floor0[k][3]) for k in floor_left)
    log("   %d of %d missed floor samples are explained by no pass:" % (len(floor_left), len(floor0)))
    for (c, k, m), n in fl.most_common(6):
        ys = sorted(floor0[q][0][1] for q in floor_left if floor0[q][1:] == (c, k, m))
        log("      %4d  %s %s  %s  (y %.1f..%.1f)" % (n, c, k, m, ys[0], ys[-1]))
    out["unexplained_floor"] = [{"class": c, "kind": k, "material": m, "n": n} for (c, k, m), n in fl.most_common(6)]
    out["notes"] = led.get("notes", {})
    return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bsp")
    ap.add_argument("doc")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    res = attribute(a.bsp, a.doc)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
