"""Closes the cracks a document's survey calls slots: two boxes whose plan footprints stand less than a player's width apart over more than a step of shared height.

A brush cut into slabs, or two walls the author left a sliver apart, leave such a crack; no player fits it and it is not a passage. `close_gaps(boxes)` grows the thinner upright box across it (document boxes: {"at", "size", "turn"}, godot axes, metres). A tilted box counts as its world AABB, as the survey reads it, and is never grown.
"""
import math

PLAYER_WIDTH = 0.8   # the survey's slot width (game-playlot playground_map_survey.gd)
STEP = 0.4           # floors that differ by less than this are stepped over, so the crack between them is no slot


def _frame(b):
    """(plan x axis, plan z axis, upright) of a box; for a tilted one the axes are the world's."""
    t = b.get("turn")
    if not t or not t[3]:
        return (1.0, 0.0), (0.0, 1.0), True
    if t[0] == 0 and t[2] == 0 and t[1] != 0:
        a = math.radians(t[3]) * (1 if t[1] > 0 else -1)
        c, s = math.cos(a), math.sin(a)
        return (c, -s), (s, c), True
    return (1.0, 0.0), (0.0, 1.0), False


def _rot(t):
    n = math.sqrt(t[0] ** 2 + t[1] ** 2 + t[2] ** 2) or 1.0
    ux, uy, uz = t[0] / n, t[1] / n, t[2] / n
    a = math.radians(t[3])
    c, s, k = math.cos(a), math.sin(a), 1 - math.cos(a)
    return [[c + ux * ux * k, ux * uy * k - uz * s, ux * uz * k + uy * s],
            [uy * ux * k + uz * s, c + uy * uy * k, uy * uz * k - ux * s],
            [uz * ux * k - uy * s, uz * uy * k + ux * s, c + uz * uz * k]]


def _extent(b, fr):
    """(plan polygon, (y low, y high)); a tilted box is its world AABB."""
    (xx, xz), (zx, zz), up = fr
    hx, hy, hz = b["size"][0] / 2, b["size"][1] / 2, b["size"][2] / 2
    cx, cy, cz = b["at"]
    if up:
        return [(cx + sx * hx * xx + sz * hz * zx, cz + sx * hx * xz + sz * hz * zz)
                for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))], (cy - hy, cy + hy)
    R = _rot(b["turn"])
    xs, ys, zs = [], [], []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                v = (sx * hx, sy * hy, sz * hz)
                xs.append(cx + sum(R[0][j] * v[j] for j in range(3)))
                ys.append(cy + sum(R[1][j] * v[j] for j in range(3)))
                zs.append(cz + sum(R[2][j] * v[j] for j in range(3)))
    return [(min(xs), min(zs)), (max(xs), min(zs)), (max(xs), max(zs)), (min(xs), max(zs))], (min(ys), max(ys))


def _seg(p, a, b):
    abx, aby = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / max(abx * abx + aby * aby, 1e-12)))
    vx, vy = a[0] + abx * t - p[0], a[1] + aby * t - p[1]
    return math.hypot(vx, vy), (vx, vy)


def _overlap(pa, pb):
    for poly in (pa, pb):
        for k in range(4):
            ax, ay = -(poly[(k + 1) % 4][1] - poly[k][1]), poly[(k + 1) % 4][0] - poly[k][0]
            a = [v[0] * ax + v[1] * ay for v in pa]
            b = [v[0] * ax + v[1] * ay for v in pb]
            if max(a) < min(b) - 1e-6 or max(b) < min(a) - 1e-6:
                return False
    return True


def close_gaps(boxes, limit=PLAYER_WIDTH, passes=60):
    """Grows upright boxes across the cracks; returns how many cracks it could not close (both boxes tilted)."""
    left = 0
    for _ in range(passes):
        frames = [_frame(b) for b in boxes]
        ext = [_extent(b, f) for b, f in zip(boxes, frames)]
        order = sorted(range(len(boxes)), key=lambda i: min(p[0] for p in ext[i][0]))
        lo = [min(p[0] for p in ext[i][0]) for i in order]
        hi = [max(p[0] for p in ext[i][0]) for i in range(len(boxes))]
        changed, left = 0, 0
        for ia, i in enumerate(order):
            for ib in range(ia + 1, len(order)):
                j = order[ib]
                if lo[ib] > hi[i] + limit:
                    break
                pi, yi = ext[i]
                pj, yj = ext[j]
                if min(p[1] for p in pi) > max(p[1] for p in pj) + limit or min(p[1] for p in pj) > max(p[1] for p in pi) + limit:
                    continue
                if min(yi[1], yj[1]) - max(yi[0], yj[0]) <= STEP or _overlap(pi, pj):
                    continue
                best, vec = 1e9, None
                for k in range(4):
                    for p in pj:
                        d, v = _seg(p, pi[k], pi[(k + 1) % 4])
                        if d < best:
                            best, vec = d, (-v[0], -v[1])      # from the point on i back to p on j: i -> j
                    for p in pi:
                        d, v = _seg(p, pj[k], pj[(k + 1) % 4])
                        if d < best:
                            best, vec = d, v                    # from p on i to the point on j: i -> j
                if not (0.001 < best < limit):
                    continue
                cand = [(min(boxes[w]["size"][0], boxes[w]["size"][2]), w, v)
                        for w, v in ((i, vec), (j, (-vec[0], -vec[1]))) if frames[w][2]]
                if not cand:
                    # both tilted: grow one along the local axis (x or z) most in line with the crack
                    for w, v in ((i, vec), (j, (-vec[0], -vec[1]))):
                        R = _rot(boxes[w]["turn"])
                        for k in (0, 2):
                            u = (R[0][k], R[1][k], R[2][k])
                            pl = u[0] * u[0] + u[2] * u[2]
                            if pl < 0.25:
                                continue
                            t = v[0] * u[0] + v[1] * u[2]
                            cand.append((-abs(t) / pl, w, k, t / pl, u))
                    if not cand:
                        left += 1
                        continue
                    _, w, k, g, u = min(cand)
                    if abs(g) < 0.0005 or abs(g) > 2 * limit:
                        left += 1
                        continue
                    b = boxes[w]
                    b["size"][k] = round(b["size"][k] + abs(g), 3)
                    sg = 1.0 if g > 0 else -1.0
                    for a_ in range(3):
                        b["at"][a_] = round(b["at"][a_] + u[a_] * sg * abs(g) / 2, 3)
                    ext[w] = _extent(b, frames[w])
                    changed += 1
                    continue
                _, w, v = min(cand)
                (xx, xz), (zx, zz), _u = frames[w]
                du, dv = v[0] * xx + v[1] * xz, v[0] * zx + v[1] * zz
                k, e = (0, du) if abs(du) >= abs(dv) else (2, dv)
                if abs(e) < 0.0005:
                    left += 1
                    continue
                b, ax = boxes[w], ((xx, xz) if k == 0 else (zx, zz))
                grow, sgn = abs(e) + 0.003, (1.0 if e > 0 else -1.0)
                b["size"][k] = round(b["size"][k] + grow, 3)
                b["at"][0] = round(b["at"][0] + ax[0] * sgn * grow / 2, 3)
                b["at"][2] = round(b["at"][2] + ax[1] * sgn * grow / 2, 3)
                ext[w] = _extent(b, frames[w])
                changed += 1
        if not changed:
            break
    return left
