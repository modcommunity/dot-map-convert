"""Texture quality report of a converted map: what each replaced surface set is drawn at, per metre.

A converted map is drawn world-triplanar (`lightmapped.gdshader`, `DotMapSurfaces._lightmapped`): one repeat of a
PBR set covers `DRAW_METRES` metres whatever the source's own texture scale was, so the mesh uv is not what a
player sees and retiling it changes nothing. The pixels per metre of a set are its albedo's width over that.
`--store` reads the real width of the shipped slice (`<store>/<id>/<tier>/albedo.webp`); a set missing from it is
drawn from the small fallback albedo beside the map (`licence.SMALL_PX`, 64 until 2026-10-26), which is what reads as blur. The
original's density (texels over the metres one repeat of its uv spans) is listed to show the replacement is
not the blurrier of the two. Worst sets by drawn area come first.

    python3 -I tools/bsp/bsp.py texquality <mesh prefix> [--store DIR] [--json F] [--top N] [--target 256]
"""

import collections
import json
import os

from . import licence, mesh, pbrmap

DRAW_METRES = 2.0     # metres one repeat of a PBR set covers in dot-map's world material
TARGET = 256.0        # px per metre under which a surface reads soft at arm's length
DENSE = 1024.0        # px per metre over which a surface is shimmer and memory a player cannot see


def _slice_px(store, set_id, tier):
    """The albedo width of a slice in `store`, or 0 when it is not there."""
    from PIL import Image
    path = os.path.join(store, set_id, tier or "1k", "albedo.webp")
    if not os.path.exists(path):
        return 0
    with Image.open(path) as im:
        return im.size[0]


def _fallback_px(directory, use):
    """The width of the small albedo a pack carries for `use`, else what the converter writes now."""
    from PIL import Image
    rel = use.get("fallback_file")
    if rel and os.path.exists(os.path.join(directory, rel)):
        with Image.open(os.path.join(directory, rel)) as im:
            return im.size[0]
    return licence.SMALL_PX


def percentiles(pairs, qs=(5, 50, 95)):
    """Area-weighted percentiles of (area, value) pairs: the value under which `q` percent of the area lies."""
    pairs = sorted(pairs, key=lambda p: p[1])
    total = sum(a for a, _ in pairs)
    out = {}
    for q in qs:
        run, hit = 0.0, pairs[-1][1] if pairs else 0
        for a, v in pairs:
            run += a
            if run >= total * q / 100.0:
                hit = v
                break
        out["p%d" % q] = round(hit)
    return out


def report(prefix, store=None, target=TARGET, top=15, dense=DENSE):
    man, m = mesh.read(prefix)
    uses = {t["key"]: t for t in man.get("licence", {}).get("textures", []) if t.get("key")}
    rows = collections.OrderedDict()
    here = os.path.dirname(os.path.abspath(prefix))
    total = 0.0
    drawn, orig = [], []
    for rec, s in zip(man["surfaces"], m.surfaces):
        use = uses.get(rec.get("free"))
        if use is None or use.get("kind") != "pbr" or s.sky3d or s.water:
            continue
        r = rows.get(rec["free"])
        if r is None:
            sid = use["generic"][len(pbrmap.GENERIC):]
            px = _slice_px(store, sid, use.get("tier")) if store else pbrmap.TIERS.get(use.get("tier"), 0)
            r = rows[rec["free"]] = {"set": sid, "tier": use.get("tier"), "px": px or _fallback_px(here, use), "missing": not px,
                                     "area": 0.0, "src": 0.0, "materials": collections.Counter()}
        area = rec.get("area", 0.0)
        rm = mesh.repeat_metres(s)
        r["area"] += area
        r["src"] += area * ((s.texels[0] if s.texels else 0) / rm if rm else 0)
        r["materials"][rec.get("material")] += area
        drawn.append((area, r["px"] / DRAW_METRES))
        orig.append((area, (s.texels[0] if s.texels else 0) / rm if rm else 0))
        total += area
    out = []
    for r in rows.values():
        out.append({"set": r["set"], "tier": r["tier"], "px": r["px"], "slice_missing": r["missing"], "area_m2": round(r["area"], 1),
                    "px_per_m": round(r["px"] / DRAW_METRES), "source_px_per_m": round(r["src"] / (r["area"] or 1.0)),
                    "materials": [k for k, _ in r["materials"].most_common(3)]})
    bad = sorted((r for r in out if r["px_per_m"] < target), key=lambda r: -r["area_m2"])
    low = sum(r["area_m2"] for r in bad)
    over = sorted((r for r in out if r["px_per_m"] > dense), key=lambda r: -r["area_m2"])
    soft = sorted((r for r in out if r["source_px_per_m"] > r["px_per_m"] * 2 and r["px_per_m"] >= target), key=lambda r: -r["area_m2"])
    return {"map": man.get("name"), "drawn_m2": round(total, 1), "below_target_m2": round(low, 1), "target_px_per_m": target,
            "sets": len(out), "sets_below_target": len(bad), "worst": bad[:top],
            "drawn_percentiles": percentiles(drawn), "original_percentiles": percentiles(orig),
            "dense_px_per_m": dense, "dense_m2": round(sum(r["area_m2"] for r in over), 1), "dense": over[:top],
            "blurrier_than_original": soft[:top]}


def cmd(args):
    r = report(args.mesh, store=args.store, target=args.target, top=args.top, dense=args.dense)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(r, f, indent=1, sort_keys=True)
    print("%s: %.0f m2 of PBR surface, %.0f m2 (%.0f%%) under %d px/m; %d of %d sets" % (
        r["map"], r["drawn_m2"], r["below_target_m2"], 100 * r["below_target_m2"] / (r["drawn_m2"] or 1), r["target_px_per_m"], r["sets_below_target"], r["sets"]))
    for w in r["worst"]:
        print("  %-28s %-4s %5.0f m2  %4d px/m (original %d)%s  %s" % (w["set"], w["tier"] or "-", w["area_m2"], w["px_per_m"], w["source_px_per_m"],
                                                                      "  SLICE MISSING: %d px fallback" % w["px"] if w["slice_missing"] else "", ", ".join(w["materials"])))
    print("  drawn px/m by area p5/p50/p95: %(p5)d / %(p50)d / %(p95)d; original %%s" % r["drawn_percentiles"] % "/".join(str(r["original_percentiles"][k]) for k in ("p5", "p50", "p95")))
    print("  over %d px/m (too dense): %.0f m2 in %d sets; drawn under half the original's density: %d sets" % (
        r["dense_px_per_m"], r["dense_m2"], len(r["dense"]), len(r["blurrier_than_original"])))
    return 1 if args.fail_below and r["sets_below_target"] else 0
