#!/usr/bin/env python3 -I
"""A thin adapter from dot-map's dotbsp intermediate JSON to a Look At Me floor skeleton.

dotbsp (../dot-map-convert) reads the compiled map; this only decides what the game wants from
it: where the rooms are. Wall brushes (world solids that stand through a storey) are rasterised,
the space outside the building is flood-filled away, the rest is eroded so that a doorway pinches
rooms apart, and each blob becomes rectangles on the game's 4 m grid. The result is a layout
file (rooms, with a kind and a size) that tools/build_levels.py turns into a proven level: the
doors, puzzles, furniture and witches are the builder's, not the source map's.

    python3 -I tools/bsp_layout.py map.json --bbox -80 48 -25 102 --z 640 850 --scale 0.0254 --out tools/layouts/x.json [--plot x.png]

--scale is metres per map unit. The intermediate says 0.01905 (the modelling convention); a player
hull of 72 units is 1.83 m only at 0.0254, and at that scale the rooms come out 8 to 16 m, the
size this game's rooms are. Layout is a skeleton, not a copy: the source's art and props are
never read.
"""
import argparse, json, math, sys
import numpy as np
from scipy import ndimage

CELL_M = 4.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("intermediate")
    ap.add_argument("--bbox", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"), required=True, help="metres, at --scale")
    ap.add_argument("--z", type=float, nargs="+", required=True, help="map-unit heights to sample walls at (every one is unioned)")
    ap.add_argument("--scale", type=float, default=0.0254)
    ap.add_argument("--res", type=float, default=0.25, help="raster cell, metres")
    ap.add_argument("--erode", type=float, default=0.75, help="metres: what a doorway pinches")
    ap.add_argument("--min-area", type=float, default=24.0, help="m2: smaller blobs are cupboards")
    ap.add_argument("--out", required=True)
    ap.add_argument("--plot")
    ap.add_argument("--ascii", action="store_true")
    a = ap.parse_args()
    doc = json.load(open(a.intermediate))
    S = a.scale
    x0, y0, x1, y1 = a.bbox
    nx, ny = int((x1 - x0) / a.res), int((y1 - y0) / a.res)
    wall = np.zeros((ny, nx), bool)
    for b in doc["brushes"]:
        if b["model"] != 0 or not b["player_solid"]:
            continue
        mn, mx = b["mins"], b["maxs"]
        if not any(mn[2] <= z <= mx[2] and mx[2] - mn[2] >= 60 for z in a.z):
            continue
        i0 = max(0, int((mn[0] * S - x0) / a.res)); i1 = min(nx, int(math.ceil((mx[0] * S - x0) / a.res)))
        j0 = max(0, int((mn[1] * S - y0) / a.res)); j1 = min(ny, int(math.ceil((mx[1] * S - y0) / a.res)))
        if i1 > i0 and j1 > j0:
            wall[j0:j1, i0:i1] = True
    free = ~wall
    lab, n = ndimage.label(free)
    outside = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    inside = free & ~np.isin(lab, list(outside))
    r = int(round(a.erode / a.res))
    core = ndimage.binary_erosion(inside, iterations=r)
    lab, n = ndimage.label(core)
    per = int(round(CELL_M / a.res))
    rooms = []
    for k in range(1, n + 1):
        m = lab == k
        if m.sum() * a.res * a.res < a.min_area:
            continue
        m = ndimage.binary_dilation(m, iterations=r) & inside
        # 4 m cells that are at least 60% this blob
        gx0, gy0 = int(math.floor(x0 / CELL_M)), int(math.floor(y0 / CELL_M))
        cells = {}
        for j in range(0, ny, per):
            for i in range(0, nx, per):
                blk = m[j:j + per, i:i + per]
                if blk.size and blk.mean() >= 0.6:
                    cells[(i // per, j // per)] = True
        # greedy rectangles: widest run, then as tall as it stays full
        left = dict(cells)
        while left:
            (ci, cj) = min(left, key=lambda c: (c[1], c[0]))
            w = 1
            while (ci + w, cj) in left: w += 1
            d = 1
            while all((ci + t, cj + d) in left for t in range(w)): d += 1
            if w * d >= 2:
                rooms.append({"x": ci, "z": cj, "w": w, "d": d, "blob": k})
            for t in range(w):
                for u in range(d):
                    left.pop((ci + t, cj + u), None)
    # cells are relative to the bbox corner; the builder re-centres
    for rm in rooms:
        rm["kind"] = "corridor" if min(rm["w"], rm["d"]) == 1 else "room"
    if a.ascii:
        # The wall plan at the game's 4 m cell, for laying rooms over by hand: '#' is a cell that is
        # at least 12% wall, '.' is open, so a hall reads as a ring and a row of rooms as a grid.
        # This is what the layouts in tools/layouts were drawn against.
        rows = []
        for j in range(0, ny, per):
            rows.append("".join("#" if wall[j:j + per, i:i + per].mean() >= 0.12 else "." for i in range(0, nx, per)))
        print("origin %.1f %.1f m, rows go up in map Y (north is the last row)" % (x0, y0))
        print("\n".join(reversed(rows)))
    json.dump({"format": 1, "source": doc.get("source", {}).get("name"), "cell": CELL_M, "scale": S, "rooms": rooms}, open(a.out, "w"), indent=1)
    print("%d rooms (%d corridors) from %d blobs; %d m2 of plan" % (len(rooms), sum(r["kind"] == "corridor" for r in rooms), n,
          sum(r["w"] * r["d"] for r in rooms) * 16))
    if a.plot:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        fig, ax = plt.subplots(figsize=(14, 14 * ny / nx))
        ax.imshow(wall, origin="lower", extent=(0, nx * a.res, 0, ny * a.res), cmap="Greys")
        for rm in rooms:
            ax.add_patch(Rectangle((rm["x"] * CELL_M, rm["z"] * CELL_M), rm["w"] * CELL_M, rm["d"] * CELL_M, fc="none", ec="r" if rm["kind"] == "room" else "b", lw=1.5))
        fig.savefig(a.plot, dpi=60)


if __name__ == "__main__":
    main()
