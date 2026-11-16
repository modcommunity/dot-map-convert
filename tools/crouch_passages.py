#!/usr/bin/env python3
"""crouch_passages -- which parts of a converted map only a crouched player of a given hull height can reach.

Reads only what the game loads (maps/<id>/<id>.json and the collision block of <id>.bin), samples
the solid hulls on a column grid and flood-fills walkable floor (step up, jump up, fall off) from
the spawns and teleport destinations once per hull height. Per map it prints:

    crouch_only   floor a --crouch hull reaches that a --stand hull cannot: the map's required
                  crouch passages (vents, ducts, crawlways)
    lost          floor the --old hull reaches but --crouch does not: a passage that was crawlable
                  and no longer is, with the biggest cut-off regions, where each is entered, and
                  the headroom there

    tools/crouch_passages.py --root ../fc-dm-maps               every map under <root>/maps
    tools/crouch_passages.py --root ../fc-dm-maps gg-woods      these maps
    tools/crouch_passages.py --crouch 54 --old 36 --stand 72 -v

Units are the manifest's (Source units, Godot axes, y up). Hulls only: displacement ramps are not
solid here, so a surf ramp reads as open air.
"""
import argparse
import json
import sys
from collections import deque
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_playable import read_hulls, planes_of  # noqa: E402

STEP = 18.0
JUMP = 45.0
CELL = 16.0
BUCKET = 512.0
INF = 1e9
SPAWN_SLACK = 40.0
METRES = 0.01905
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


class Solids:
    def __init__(self, hulls):
        self.hulls = hulls
        self.boxes, self.planes, self.grid = [], [], {}
        for i, h in enumerate(hulls):
            lo = [min(p[a] for p in h) for a in range(3)]
            hi = [max(p[a] for p in h) for a in range(3)]
            self.boxes.append((lo, hi))
            self.planes.append(None)
            for x in range(int(lo[0] // BUCKET), int(hi[0] // BUCKET) + 1):
                for z in range(int(lo[2] // BUCKET), int(hi[2] // BUCKET) + 1):
                    self.grid.setdefault((x, z), []).append(i)

    def column(self, x, z):
        """Merged solid intervals (bottom, top) of the world along y at (x, z)."""
        out = []
        for i in self.grid.get((int(x // BUCKET), int(z // BUCKET)), ()):
            lo, hi = self.boxes[i]
            if not (lo[0] <= x <= hi[0] and lo[2] <= z <= hi[2]):
                continue
            pl = self.planes[i]
            if pl is None:
                pl = self.planes[i] = planes_of(self.hulls[i])
            y0, y1 = -INF, INF
            ok = True
            for nx, ny, nz, d in pl:
                r = d - nx * x - nz * z
                if abs(ny) < 1e-6:
                    if r < -0.01:
                        ok = False
                        break
                elif ny > 0:
                    y1 = min(y1, r / ny)
                else:
                    y0 = max(y0, r / ny)
            if ok and y1 - y0 > 0.5:
                out.append((max(y0, lo[1]), min(y1, hi[1])))
        out.sort()
        merged = []
        for a, b in out:
            if merged and a <= merged[-1][1] + 0.5:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        return merged


def ceiling_source(solids, col, x, z, y):
    """The hull whose underside is the lowest solid above a floor at y at (x, z): (index, kind, box)."""
    best = None
    for i in solids.grid.get((int(x // BUCKET), int(z // BUCKET)), ()):
        lo, hi = solids.boxes[i]
        if not (lo[0] <= x <= hi[0] and lo[2] <= z <= hi[2]) or hi[1] <= y + 1:
            continue
        pl = solids.planes[i] or planes_of(solids.hulls[i])
        y0, y1, ok = -INF, INF, True
        for nx, ny, nz, d in pl:
            r = d - nx * x - nz * z
            if abs(ny) < 1e-6:
                if r < -0.01:
                    ok = False
                    break
            elif ny > 0:
                y1 = min(y1, r / ny)
            else:
                y0 = max(y0, r / ny)
        if ok and y1 > y + 1 and y0 > y - 1 and (best is None or y0 < best[0]):
            best = (y0, i)
    if best is None:
        return None
    i = best[1]
    kind = "solid"
    for k, idx in (col.get("hull_kinds") or {}).items():
        if i in idx:
            kind = k
    if i >= col["hull_count"] - col.get("prop_hulls", 0):
        kind = "prop"
    return i, kind, [round(v) for v in solids.boxes[i][0] + solids.boxes[i][1]], round(best[0])


def analyse(job):
    root, mid, old, crouch, stand, verbose = job
    base = Path(root) / "maps" / mid / mid
    doc = json.loads(base.with_suffix(".json").read_text())
    col = doc.get("collision", {})
    if not col.get("hull_count"):
        return mid, None
    solids = Solids(read_hulls(base.with_suffix(".bin").read_bytes(), col))
    b = doc["bounds"]
    x0, x1 = sorted((b["min"][0], b["max"][0]))
    z0, z1 = sorted((b["min"][2], b["max"][2]))
    cols = {}
    for ix in range(int(x0 // CELL), int(x1 // CELL) + 1):
        for iz in range(int(z0 // CELL), int(z1 // CELL) + 1):
            iv = solids.column((ix + 0.5) * CELL, (iz + 0.5) * CELL)
            if iv:
                # floors: the top of each solid span, with the clear height up to the next span
                cols[(ix, iz)] = [(hi, iv[k + 1][0] if k + 1 < len(iv) else INF) for k, (lo, hi) in enumerate(iv)]

    seeds = [s["origin"] for s in doc.get("spawns") or []]
    if doc.get("spawn", {}).get("origin"):
        seeds.append(doc["spawn"]["origin"])
    seeds += [z["destination"] for z in doc.get("zones", []) if z.get("destination") is not None]
    seeds += [k["destination"] for k in doc.get("mechanics", {}).get("blocks", []) if k.get("destination") is not None]

    def reach(h):
        seen, q = set(), deque()
        for p in seeds:
            c = (int(p[0] // CELL), int(p[2] // CELL))
            best = None
            for k, (fy, ceil) in enumerate(cols.get(c, ())):
                if fy <= p[1] + SPAWN_SLACK and ceil - fy >= h and (best is None or fy > cols[c][best][0]):
                    best = k
            if best is not None and (c, best) not in seen:
                seen.add((c, best))
                q.append((c, best))
        while q:
            c, k = q.popleft()
            fy = cols[c][k][0]
            for dx, dz in NEIGHBOURS:
                n = (c[0] + dx, c[1] + dz)
                for nk, (ny, nceil) in enumerate(cols.get(n, ())):
                    if (n, nk) not in seen and ny - fy <= JUMP and nceil >= max(fy, ny) + h:
                        seen.add((n, nk))
                        q.append((n, nk))
        return seen

    reach_old, reach_new, reach_stand = reach(old), reach(crouch), reach(stand)
    crouch_only = reach_new - reach_stand
    lost = reach_old - reach_new
    regions, done = [], set()
    for n in lost:
        if n in done:
            continue
        comp, q = [], deque([n])
        done.add(n)
        while q:
            c, k = q.popleft()
            comp.append((c, k))
            for dx, dz in NEIGHBOURS:
                m = (c[0] + dx, c[1] + dz)
                for nk, (ny, _) in enumerate(cols.get(m, ())):
                    if (m, nk) in lost and (m, nk) not in done and abs(ny - cols[c][k][0]) <= JUMP:
                        done.add((m, nk))
                        q.append((m, nk))
        regions.append(comp)
    regions.sort(key=len, reverse=True)
    sq = (CELL * METRES) ** 2
    out = {"reach_stand": len(reach_stand) * sq, "reach_new": len(reach_new) * sq, "reach_old": len(reach_old) * sq,
           "crouch_only": len(crouch_only) * sq, "lost": len(lost) * sq, "regions": []}
    for comp in regions[: (20 if verbose else 4)]:
        cx = sum((c[0] + 0.5) * CELL for c, k in comp) / len(comp)
        cz = sum((c[1] + 0.5) * CELL for c, k in comp) / len(comp)
        cy = sum(cols[c][k][0] for c, k in comp) / len(comp)
        heads = [cols[c][k][1] - cols[c][k][0] for c, k in comp]
        gate = None
        for c, k in comp:
            for dx, dz in NEIGHBOURS:
                m = (c[0] + dx, c[1] + dz)
                if any((m, nk) in reach_new and abs(ny - cols[c][k][0]) <= JUMP for nk, (ny, _) in enumerate(cols.get(m, ()))):
                    gate = ((c[0] + 0.5) * CELL, cols[c][k][0], (c[1] + 0.5) * CELL, cols[c][k][1] - cols[c][k][0])
                    break
            if gate:
                break
        why = ceiling_source(solids, col, gate[0], gate[2], gate[1]) if gate else None
        out["regions"].append({"area": len(comp) * sq, "at": (cx, cy, cz), "headroom": (min(heads), max(heads)), "gate": gate, "why": why})
    return mid, out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("maps", nargs="*")
    ap.add_argument("--root", default=".", help="map repository (maps/<id>/<id>.json and .bin)")
    ap.add_argument("--crouch", type=float, default=54.0, help="crouched hull height in units")
    ap.add_argument("--old", type=float, default=36.0, help="the hull to compare against")
    ap.add_argument("--stand", type=float, default=72.0, help="standing hull height")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    maps_dir = Path(a.root) / "maps"
    ids = a.maps or sorted(d.name for d in maps_dir.iterdir() if (d / (d.name + ".json")).is_file())
    with Pool(a.jobs) as pool:
        results = pool.map(analyse, [(a.root, m, a.old, a.crouch, a.stand, a.verbose) for m in ids], chunksize=1)
    for mid, r in results:
        if r is None:
            print("skip %s: no collision hulls" % mid)
            continue
        print("%-34s stand %7.0f m2  crouch %7.0f  old %7.0f  crouch_only %6.1f  lost %6.1f"
              % (mid, r["reach_stand"], r["reach_new"], r["reach_old"], r["crouch_only"], r["lost"]))
        for g in r["regions"]:
            gate = "(%.0f, %.0f, %.0f) head %.0f" % g["gate"] if g["gate"] else "none"
            print("      lost %6.1f m2 at (%.0f, %.0f, %.0f) headroom %.0f-%.0f  gate %s  ceiling %s"
                  % ((g["area"],) + g["at"] + g["headroom"] + (gate, g["why"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
