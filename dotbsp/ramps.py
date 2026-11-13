"""Walkable ramps under the library staircases a solid prop is drawn as.

A stock staircase model has no .phy in the pak, and the drawn stand-in cut into boxes is a column of treads each
taller than a body steps up (11 treads over 4.7 m on cp_orange_x3): the stairs block or snag. So a solid prop drawn
as a `WALK_RAMPS` staircase collides as one ramp along its treads' front edges instead, which is the climb the
drawing shows.

[b]The ramp is measured in the frame the game draws the model in.[/b] dot-map's mesh_props re-roots a library
stand-in on the bottom centre of its bounds, turns it by yaw + 90 and scales its longest side to `size`. Measured
from the glb's own origin instead, the ramp sat half a staircase (170 u) off the drawn steps on cp_orange_x3: an
invisible climb beside the stairs and none under them, the drawn top short of the wall (owner 2026-11-12).

[b]A staircase leads somewhere.[/b] `landing_gap` measures how far past the ramp's top the nearest solid that a
body steps onto is, so a converted map whose stairs stop short of their wall or ledge is reported, not shipped.
"""

import math

# Library staircases, in the glb's own metres: its bounds, and where the line along the treads' front edges meets the
# floor (`foot`) and the top (`crest`) along +x, the way it rises.
WALK_RAMPS = {
    "lib/kenney_furniture-kit_stairs": {"lo": (0.0, 0.0, -0.79), "hi": (1.82343, 1.33953, 0.0),
                                        "foot": -0.164, "crest": 1.639},
}
PROP_FACING_DEGREES = 90.0   # dot-map mesh_props: a library model faces +z, a Source model +x
SOLID = (2, 3, 4, 6)         # dot-map mesh_solids SOLID_BOX: the `solid` values a prop collides with
LANDING_REACH = 0.1          # metres past the top a landing is looked for: the top is flush with what it leads to


def local_points(ramp):
    """The ramp's 8 corners, model metres, bottom centre of the bounds at the origin, rising along +x."""
    (x0, y0, z0), (x1, y1, z1) = ramp["lo"], ramp["hi"]
    mx, mz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
    return [(x - mx, y - y0, z - mz)
            for x, y in ((ramp["foot"], y0), (x1, y0), (ramp["crest"], y1), (x1, y1)) for z in (z0, z1)]


def scale_of(ramp, size, scale=1.0):
    """What the game multiplies the model by: `scale`, then its longest side fitted to `size`."""
    longest = max(h - l for l, h in zip(ramp["lo"], ramp["hi"]))
    return scale * (size / longest if size and size > 0 else 1.0)


def godot_points(rec, ramp):
    """A placed prop record's ramp corners in Godot metres, exactly where mesh_props draws the model."""
    t = math.radians(float(rec.get("yaw", 0.0)) + PROP_FACING_DEGREES)
    k = scale_of(ramp, float(rec.get("size", 0.0)), float(rec.get("scale", 1.0)))
    at = rec["at"]
    return [(at[0] + k * (x * math.cos(t) + z * math.sin(t)), at[1] + k * y, at[2] + k * (-x * math.sin(t) + z * math.cos(t)))
            for x, y, z in local_points(ramp)]


def planes(points):
    """Outward planes (nx, ny, nz, d), n.p <= d inside, of the convex hull of a ramp's 8 corners (`local_points` order):
    floor, top, back, slope and the two sides."""
    c = [sum(p[i] for p in points) / len(points) for i in range(3)]
    out = []
    for a, b, e in ((0, 2, 1), (4, 6, 5), (2, 6, 3), (0, 4, 1), (0, 2, 4), (1, 3, 5)):
        p, q, r = points[a], points[b], points[e]
        u = [q[i] - p[i] for i in range(3)]
        v = [r[i] - p[i] for i in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        ln = math.sqrt(sum(x * x for x in n))
        n = [x / ln for x in n]
        d = sum(n[i] * p[i] for i in range(3))
        if sum(n[i] * c[i] for i in range(3)) > d:
            n, d = [-x for x in n], -d
        out.append((n[0], n[1], n[2], d))
    return out


def landing_probe(points, up=1):
    """A point just past the middle of the ramp's top edge and a little under it, inside whatever the stairs lead
    to: `up` is the axis that points up (1 in Godot axes, 2 in Hammer's)."""
    top = points[6:8]       # (x1, y1) at z0 and z1: the back of the top
    foot = points[0:2]
    m = [(top[0][i] + top[1][i]) / 2.0 for i in range(3)]
    f = [(foot[0][i] + foot[1][i]) / 2.0 for i in range(3)]
    run = [m[i] - f[i] if i != up else 0.0 for i in range(3)]
    ln = math.sqrt(sum(x * x for x in run)) or 1.0
    return m, [x / ln for x in run]


def landing_gap(points, boxes, up=1, reach=LANDING_REACH, limit=4.0, step=0.05):
    """How far past the ramp's top (in the points' units) the nearest box in `boxes` [(lo, hi)] stands at the top's
    height, 0.0 when one is flush; None when there is nothing within `limit`."""
    m, d = landing_probe(points, up)
    h = m[up] - reach
    s = 0.0
    while s <= limit:
        p = [m[i] + d[i] * (s + reach) for i in range(3)]
        p[up] = h
        if any(all(lo[i] - 1e-3 <= p[i] <= hi[i] + 1e-3 for i in range(3)) for lo, hi in boxes):
            return s
        s += step
    return None


def add_ramp_hulls(props, hulls):
    """Gives each solid prop drawn as a `WALK_RAMPS` staircase a ramp hull in `hulls` (dotbsp.mesh's hull records,
    Godot metres) and takes its `solid` off, so the game collides with the ramp and not with boxes cut from the
    treads. Returns [(prop, points)] for the ones it did."""
    done = []
    for rec in props:
        ramp = WALK_RAMPS.get(rec.get("stand_in", ""))
        if ramp is None or int(rec.get("solid", 0) or 0) not in SOLID:
            continue
        pts = godot_points(rec, ramp)
        hulls.append({"brush": -1, "model": 0, "entity": None, "classname": "prop_dynamic", "kind": "solid",
                      "contents": 1, "points": pts, "planes": planes(pts)})
        rec.pop("solid", None)
        rec["ramp"] = True
        done.append((rec, pts))
    return done
