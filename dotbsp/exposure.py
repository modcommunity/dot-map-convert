"""Where a prop-hunt map's props are seen from, and where more of them can hide: numpy over a document's boxes and props.

`exposure` is the bots suite's `seen` metric in rough form (good for ranking places, not for predicting the suite's number).
`add_wall_clusters` stands same-kind groups flush against tall walls in spots few standing points see, with open floor in front
(so a cluster never closes a lane) and no opening in the wall behind or beside it (so never a doorway). Moved here from
mg-prop-hunt-maps' tools/retune.py, which calls it.

Documents are the game's: `boxes` ({at, size, yaw, solid}), `props` ({id, at: [x, base y, z], yaw}) and `spawns`; `sizes` is
`prop_sizes.json`'s `props` ({id: {size: [x, y, z]}}). Boxes are treated as axis-aligned.
"""
import math


def _prop_boxes(doc, sizes):
    """The props as axis-aligned boxes [(lo, hi)], the yaw rounded to the nearest quarter turn."""
    out = []
    for q in doc["props"]:
        sx, sy, sz = sizes.get(q["id"], {}).get("size", [0.3, 0.3, 0.3])
        if round(q.get("yaw", 0.0) / 90.0) % 2:
            sx, sz = sz, sx
        x, y, z = q["at"]
        out.append(((x - sx / 2, y, z - sz / 2), (x + sx / 2, y + sy, z + sz / 2)))
    return out


def _standing(lo, hi, xs, zs, kill_y):
    """Standing places on a grid: (ix, iz, floor_y) where the top of a solid box has headroom over it."""
    import numpy as np
    out = []
    for ix, x in enumerate(xs):
        for iz, z in enumerate(zs):
            cover = np.nonzero((lo[:, 0] <= x) & (hi[:, 0] >= x) & (lo[:, 2] <= z) & (hi[:, 2] >= z))[0]
            for top in sorted(set(np.round(hi[cover, 1], 2))):
                if top >= kill_y and not ((lo[cover, 1] < top + 1.8) & (hi[cover, 1] > top + 0.1)).any():
                    out.append((ix, iz, float(top)))
    return out


def _reachable(lo, hi, places, xs, zs, starts):
    """The places a walker from `starts` (x, z, y) can get to: steps of at most 0.5 m up or down between neighbours with a clear waist-high line."""
    import numpy as np
    index = {}
    for n, (ix, iz, y) in enumerate(places):
        index.setdefault((ix, iz), []).append(n)
    xy = np.array([(xs[ix], y, zs[iz]) for ix, iz, y in places])
    todo = []
    for sx, sy, sz in starts:
        d = np.linalg.norm(xy - np.array([sx, sy, sz]), axis=1)
        todo.append(int(d.argmin()))
    seen = set(todo)
    while todo:
        n = todo.pop()
        ix, iz, y = places[n]
        cand = [m for dx in (-1, 0, 1) for dz in (-1, 0, 1) if dx or dz for m in index.get((ix + dx, iz + dz), []) if m not in seen and abs(places[m][2] - y) <= 0.5]
        if not cand:
            continue
        a = xy[n] + [0, 0.7, 0]
        end = xy[cand] + [0, 0.7, 0]
        ok = ~_blocked(lo, hi, a[None], end)
        for m, good in zip(cand, ok[0]):
            if good:
                seen.add(m)
                todo.append(m)
    return sorted(seen)


def _blocked(lo, hi, eyes, target):
    """eyes (n,3) to targets (m,3): an (n, m) array, true where a box in lo/hi lies on the segment."""
    import numpy as np
    out = np.zeros((len(eyes), len(target)), dtype=bool)
    for j, t in enumerate(target):
        d = t - eyes
        with np.errstate(divide="ignore", invalid="ignore"):
            inv = 1.0 / d
            t1 = (lo[None] - eyes[:, None]) * inv[:, None]
            t2 = (hi[None] - eyes[:, None]) * inv[:, None]
        tmin = np.nan_to_num(np.minimum(t1, t2), nan=-np.inf).max(axis=2)
        tmax = np.nan_to_num(np.maximum(t1, t2), nan=np.inf).min(axis=2)
        out[:, j] = ((tmax >= np.maximum(tmin, 0.0)) & (tmin <= 1.0)).any(axis=1)
    return out


def _scene(doc, sizes):
    """The arrays every query needs: solid boxes (lo, hi), prop boxes (plo, phi), the grid, the reachable standing places."""
    import numpy as np
    solid = [b for b in doc["boxes"] if b.get("solid", True)]
    lo = np.array([[b["at"][i] - b["size"][i] / 2 for i in range(3)] for b in solid])
    hi = np.array([[b["at"][i] + b["size"][i] / 2 for i in range(3)] for b in solid])
    plo, phi = (np.array(a) for a in zip(*_prop_boxes(doc, sizes))) if doc["props"] else (np.zeros((0, 3)),) * 2
    xs = np.arange(lo[:, 0].min(), hi[:, 0].max(), 1.0)
    zs = np.arange(lo[:, 2].min(), hi[:, 2].max(), 1.0)
    places = _standing(lo, hi, xs, zs, doc.get("kill_y", -30.0))
    sp = doc.get("spawns", {})
    starts = [tuple(s["at"]) for side in ("props", "hunters") for s in (sp.get(side, []) if isinstance(sp, dict) else [])]
    if starts:
        places = [places[n] for n in _reachable(lo, hi, places, xs, zs, starts)]
    return lo, hi, plo, phi, xs, zs, places


def _eyes(places, xs, zs, spacing, eye):
    import numpy as np
    step = max(int(round(spacing)), 1)
    return np.array([(xs[ix], y + eye, zs[iz]) for ix, iz, y in places if ix % step == 0 and iz % step == 0])


def _seen_share(blo, bhi, eyes, target, reach, skip=None):
    """The share of `eyes` within `reach` m of `target` (3,) with no box between; `skip` is a box index to ignore."""
    import numpy as np
    near = eyes[np.linalg.norm(eyes - target, axis=1) <= reach] if len(eyes) else eyes
    if not len(near):
        return 0.5
    keep = ~((blo <= target).all(axis=1) & (bhi >= target).all(axis=1))
    if skip is not None:
        keep[skip] = False
    blocked = _blocked(blo[keep], bhi[keep], near, target[None])[:, 0]
    return float((~blocked).sum()) / len(near)


def exposure(doc, sizes, spacing=3.0, eye=1.6, reach=30.0):
    """Per prop, the share of standing points within `reach` m that see it, the way the bots suite's `seen` is measured.

    Standing points are the places a walker can reach from the spawns (a 1 m grid walked in steps of
    at most half a metre, so roofs and shelves nobody can climb to do not count), thinned to every
    `spacing` m. A point sees a prop when no solid box or other prop lies on the line from its eye
    to the prop's middle (half a metre up); the prop's own box and any box holding the target do
    not count. A rough copy of the suite's metric (which asks the physics space): good for ranking
    places, not for predicting the suite's number to the point.
    """
    import numpy as np
    lo, hi, plo, phi, xs, zs, places = _scene(doc, sizes)
    eyes = _eyes(places, xs, zs, spacing, eye)
    blo = np.vstack([lo, plo])
    bhi = np.vstack([hi, phi])
    return [_seen_share(blo, bhi, eyes, np.array([q["at"][0], q["at"][1] + 0.5, q["at"][2]]), reach, len(lo) + n)
            for n, q in enumerate(doc["props"])]


def _hits(lo, hi, fp, y0, y1, pad=0.0):
    """True where a box overlaps the footprint fp = (x0, z0, x1, z1) between heights y0 and y1."""
    x0, z0, x1, z1 = fp
    return bool(((lo[:, 0] < x1 + pad) & (hi[:, 0] > x0 - pad) & (lo[:, 2] < z1 + pad) & (hi[:, 2] > z0 - pad)
                 & (lo[:, 1] < y1) & (hi[:, 1] > y0)).any())


def _inside(lo, hi, pt):
    return bool(((lo <= pt).all(axis=1) & (hi >= pt).all(axis=1)).any())


def _wall_face(lo, hi, x, z, y, nx, nz, far=1.2):
    """Distance from (x, z) to the wall face behind it, looking along (-nx, -nz) at chest height; None when open."""
    import numpy as np
    for k in range(1, int(far / 0.05) + 1):
        d = k * 0.05
        if _inside(lo, hi, np.array([x - nx * d, y + 1.0, z - nz * d])):
            return d - 0.05
    return None


def _floored(lo, hi, fp, y):
    """True where the floor under all four corners of fp is at height y (a box top within 5 cm)."""
    for cx, cz in ((fp[0], fp[1]), (fp[0], fp[3]), (fp[2], fp[1]), (fp[2], fp[3])):
        if not ((lo[:, 0] <= cx) & (hi[:, 0] >= cx) & (lo[:, 2] <= cz) & (hi[:, 2] >= cz) & (abs(hi[:, 1] - y) <= 0.05)).any():
            return False
    return True


def add_wall_clusters(doc, sizes, count=30, per=3, max_exposure=0.25, lane=1.6, separation=4.0, kinds=None,
                      spacing=3.0, eye=1.6, reach=30.0, max_height=1.4, log=print):
    """Stands up to `count` clusters of `per` same-kind props flush against tall walls; returns how many.

    A seed is a reachable standing place with a wall (solid, 1.8 m above the floor) a metre or less behind it. The cluster
    runs along the wall, props 8 cm apart, and is kept when: nothing solid or standing is in its footprint; the floor under
    its corners is the floor it stands on; the wall holds for 1.2 m past both ends at chest height (no doorway, no window
    gap); at least `lane` m of open space lie in front of each prop (no lane is closed); and its middle is seen from at
    most `max_exposure` of the standing points. Candidates go least exposed first, `separation` m apart. `kinds` defaults to
    the kinds the map already has that stand under `max_height` and are not wider than 1.2 m; they are used in turn.
    """
    import numpy as np
    lo, hi, plo, phi, xs, zs, places = _scene(doc, sizes)
    eyes = _eyes(places, xs, zs, spacing, eye)
    if kinds is None:
        kinds = []
        for q in doc["props"]:
            s = sizes.get(q["id"], {}).get("size")
            if s and q["id"] not in kinds and s[1] <= max_height and max(s[0], s[2]) <= 1.2 and min(s[0], s[2]) >= 0.25:
                kinds.append(q["id"])
        kinds.sort()
    if not kinds or not len(eyes):
        return 0
    blo = np.vstack([lo, plo])
    bhi = np.vstack([hi, phi])
    seeds, once = [], set()
    for ix, iz, y in places:
        x, z = float(xs[ix]), float(zs[iz])
        for nx, nz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            d = _wall_face(lo, hi, x, z, y, nx, nz)
            if d is None or not _inside(lo, hi, np.array([x - nx * (d + 0.1), y + 1.8, z - nz * (d + 0.1)])):
                continue
            fx, fz = x - nx * d, z - nz * d
            key = (round(fx), round(fz), nx, nz)
            if key not in once:
                once.add(key)
                seeds.append((fx, fz, y, nx, nz))
    scored = []
    for fx, fz, y, nx, nz in seeds:
        ex = _seen_share(blo, bhi, eyes, np.array([fx + nx * 0.4, y + 0.5, fz + nz * 0.4]), reach)
        if ex <= max_exposure:
            scored.append((ex, fx, fz, y, nx, nz))
    scored.sort()
    made, chosen = 0, []
    for ex, fx, fz, y, nx, nz in scored:
        if made >= count:
            break
        if any((fx - cx) ** 2 + (fz - cz) ** 2 < separation ** 2 for cx, cz in chosen):
            continue
        kind = kinds[made % len(kinds)]
        w, h, dep = sizes[kind]["size"]
        tx, tz = -nz, nx
        # yaw 0 faces +z and a quarter turn faces +x; the prop's width then runs along the wall
        yaw = math.degrees(math.atan2(nx, nz))
        hx, hz = (w / 2, dep / 2) if nz else (dep / 2, w / 2)
        span = per * (w + 0.08) - 0.08
        spots = [(fx + nx * (0.03 + dep / 2) + tx * (-span / 2 + w / 2 + k * (w + 0.08)),
                  fz + nz * (0.03 + dep / 2) + tz * (-span / 2 + w / 2 + k * (w + 0.08))) for k in range(per)]
        ok = True
        for px, pz in spots:
            fp = (px - hx, pz - hz, px + hx, pz + hz)
            if _hits(lo, hi, fp, y + 0.1, y + h, 0.02) or _hits(blo[len(lo):], bhi[len(lo):], fp, y + 0.02, y + h, 0.1) or not _floored(lo, hi, fp, y):
                ok = False
                break
            for hgt in (0.4, 1.2):
                a = np.array([px + nx * (dep / 2 + 0.05), y + hgt, pz + nz * (dep / 2 + 0.05)])
                if _blocked(blo, bhi, a[None], (a + np.array([nx, 0, nz]) * lane)[None])[0, 0]:
                    ok = False
                    break
            if not ok:
                break
        if not ok:
            continue
        run = span / 2 + 1.2
        if not all(_inside(lo, hi, np.array([fx - nx * 0.1 + tx * o, y + 1.0, fz - nz * 0.1 + tz * o]))
                   for o in np.arange(-run, run + 0.01, 0.3)):
            continue
        for px, pz in spots:
            doc["props"].append({"id": kind, "at": [round(px, 3), round(y, 3), round(pz, 3)], "yaw": round(yaw, 1)})
            blo = np.vstack([blo, [[px - hx, y, pz - hz]]])
            bhi = np.vstack([bhi, [[px + hx, y + h, pz + hz]]])
        chosen.append((fx, fz))
        made += 1
        if log:
            log("cluster %d: %d x %s at (%.1f, %.1f), exposure %.2f" % (made, per, kind, fx, fz, ex))
    return made
