"""A brush as boxes, for the games whose map documents are boxes rather than meshes.

Five converters each had their own copy of this, and each had fixed something the others
had not. This is the union, in the order a brush is tried:

1. **An axis-aligned box** when the hull has all eight corners of its bounding box and no
   others. Three copies tested only "every corner is a box corner", which a wedge passes
   (its six corners are all box corners), so a ramp became a block; zombie-zone tested the
   planes and did not have that bug. Found by this package's tests.
2. **A box turned about the vertical axis** (prop-hunt's `turned_box`; zombie-zone's
   `box_from_prism` was the same idea with one angle and a 0.5-unit tolerance). The angle is
   each upright side's direction modulo 90, tried in turn, corners within 1.5 units:
   four-decimal planes at a thousand units leave a unit of slack. A room built at thirty
   degrees to the grid cut into axis-aligned slabs is a saw-tooth players catch on.
3. **A vertical prism of any plan** (prop-hunt's `prism_box`): the smallest turned rectangle
   round its plan. A curved wall is a run of such wedges and a round room's column is one;
   slicing them as slopes bit chunks out of the room. zombie-zone sliced them. Only when
   the plan fills at least `PRISM_FILL` of that rectangle (an octagon fills 83%): prop-hunt
   took any plan, and the rectangle round a triangular column is twice the column, a wall
   where the map has a corridor. A thinner plan goes on to slabs.
4. **One tilted box for a single-slope ramp**, only when the caller's document can draw a
   tilted box (`tilt=True`; game-playground's `ramp_box`). A staircase of slabs left gaps a
   survey reads as slots, and feet catch on its saw-tooth.
5. **Slabs** for everything else (roofs, wedges, ramps a document cannot tilt). Cut **along
   the slope** (zombie-zone's fix): the other copies cut along the longer horizontal axis,
   which turns a ramp wider than it is long into one flat block at its mid-height. Each
   slab spans the brush's own cross-section at its middle (zombie-zone's fix too): the other
   copies used the bounding box across the cut, which overhangs a wedge whose plan narrows.

Everything is in map units and map axes (Z-up). A box is a dict:

    {"x": (x0, x1), "y": (y0, y1), "z": (z0, z1), "phi": degrees, "kind": "box" | "turned" | "prism" | "ramp" | "slab"}

where the ranges are in a frame turned `phi` degrees about +Z (0 for most), so the box's
centre in map coordinates is `centre(box)`. A ramp box also carries `ramp`: (axis, zlow,
zhigh, base, angle, sign), playground's tuple.
"""

import math

SLAB = 28.0          # map units: about 0.53 m, a slope's riser
PRISM_FILL = 0.8     # least share of its rectangle a prism's plan fills to be that rectangle


def _plan_area(pts2):
    """Area of the convex plan through these (x, y) points (they are a convex brush's)."""
    cx = sum(p[0] for p in pts2) / len(pts2)
    cy = sum(p[1] for p in pts2) / len(pts2)
    ring = sorted(pts2, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    return abs(sum(ring[i][0] * ring[i - 1][1] - ring[i - 1][0] * ring[i][1] for i in range(len(ring)))) / 2


def _bounds(pts):
    return ((min(p[0] for p in pts), max(p[0] for p in pts)),
            (min(p[1] for p in pts), max(p[1] for p in pts)),
            (min(p[2] for p in pts), max(p[2] for p in pts)))


def box_in_frame(pts, phi, tol, solid=True):
    """The hull's extents in a frame turned phi degrees about z, or None when some corner is
    not a corner of that bounding box. ((x0, x1), (y0, y1), (z0, z1)) in the turned frame.

    [b]`solid` also wants all eight corners present.[/b] Every corner of a wedge (a ramp
    with level ends, six corners) is a corner of its bounding box too, so the corner test
    alone wrote ramps as full blocks: a step the height of the ramp at its foot. Three
    copies of the old converter had that; the one that tested the planes instead did not.
    """
    c, sn = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    q = [(p[0] * c + p[1] * sn, -p[0] * sn + p[1] * c, p[2]) for p in pts]
    (x0, x1), (y0, y1), (z0, z1) = _bounds(q)
    seen = set()
    for p in q:
        k = []
        for v, lo, hi in ((p[0], x0, x1), (p[1], y0, y1), (p[2], z0, z1)):
            # The nearer face, not the first in tolerance: a pane thinner than `tol` has
            # both faces in tolerance of every corner and would look like four corners.
            dl, dh = abs(v - lo), abs(v - hi)
            if min(dl, dh) >= tol:
                return None
            k.append(0 if dl <= dh else 1)
        seen.add(tuple(k))
    if solid and len(seen) < 8:
        return None
    return (x0, x1), (y0, y1), (z0, z1)


def turned_box(planes, pts):
    """(ranges, phi) when the brush is a box turned about the vertical axis, else None."""
    tried = set()
    for nx, ny, nz, _d in planes:
        if abs(nz) > 1e-3:
            continue
        phi = round(math.degrees(math.atan2(ny, nx)) % 90.0, 2)
        if phi in tried or phi < 0.05 or phi > 89.95:
            continue
        tried.add(phi)
        box = box_in_frame(pts, phi, 1.5)
        if box is not None:
            return box, phi
    return None


def prism_box(pts):
    """(ranges, phi) for a vertical prism of any plan shape: the smallest turned rectangle
    round its plan. None for a brush whose top or bottom is not flat and level."""
    zs = sorted({round(p[2], 1) for p in pts})
    if len(zs) != 2:
        return None
    low = {(round(p[0], 1), round(p[1], 1)) for p in pts if abs(p[2] - zs[0]) < 0.15}
    high = {(round(p[0], 1), round(p[1], 1)) for p in pts if abs(p[2] - zs[1]) < 0.15}
    if low != high or len(low) < 3:
        return None
    plan = [(x, y, zs[0]) for x, y in low]
    best = None
    for (ax, ay), (bx_, by) in ((p, q) for p in sorted(low) for q in sorted(low) if p != q):
        phi = math.degrees(math.atan2(by - ay, bx_ - ax)) % 90.0
        box = box_in_frame(plan, phi, 1e9, solid=False)
        area = (box[0][1] - box[0][0]) * (box[1][1] - box[1][0])
        if best is None or area < best[0] - 1e-6:
            best = (area, phi, box)
    _a, phi, box = best
    if best[0] <= 0 or _plan_area(sorted(low)) < PRISM_FILL * best[0]:
        return None
    return (box[0], box[1], (zs[0], zs[1])), phi


def ramp_box(planes, pts):
    """A tilted box for a wedge whose only sloping face rises along one world axis, else None.

    (axis 'x' or 'y', z at the low end of the axis, z at the high end, base z, angle in
    degrees, sign). The box hangs under the surface, so the sliver it overhangs past the
    high end is inside the wall the ramp meets.
    """
    sloped = [p for p in planes if 0.05 < p[2] < 0.98]
    if len(sloped) != 1:
        return None
    nx, ny, nz, d = sloped[0]
    if (abs(nx) > 1e-3) == (abs(ny) > 1e-3):
        return None
    (x0, x1), (y0, y1), (base, _top) = _bounds(pts)
    along_x = abs(nx) > 1e-3
    g = -(nx if along_x else ny) / nz
    if along_x:
        za, zb = (d - nx * x0) / nz, (d - nx * x1) / nz
    else:
        za, zb = (d - ny * y0) / nz, (d - ny * y1) / nz
    return ("x" if along_x else "y", za, zb, base, math.degrees(math.atan(abs(g))), 1 if g > 0 else -1)


def slabs(planes, pts, slab=SLAB, min_size=0.5, max_slabs=400):
    """The brush cut into slabs along its slope, each spanning the cross-section at its middle."""
    (x0, x1), (y0, y1), _z = _bounds(pts)
    gx = gy = 0.0
    for a, b, c, _d in planes:
        if 1e-3 < abs(c) < 0.9995:
            gx += abs(a)
            gy += abs(b)
    if gx == 0 and gy == 0:
        gx, gy = x1 - x0, y1 - y0
    axis = 0 if gx >= gy else 1
    lo, hi = (x0, x1) if axis == 0 else (y0, y1)
    n = max(1, min(max_slabs, int(math.ceil((hi - lo) / slab))))
    w = (hi - lo) / n
    out = []
    for k in range(n):
        mid = lo + (k + 0.5) * w
        # The planes restricted to the cut at `mid`: a 2D polygon in (other axis, z).
        cons = [((b, c, d - a * mid) if axis == 0 else (a, c, d - b * mid)) for a, b, c, d in planes]
        verts = []
        for i in range(len(cons)):
            p1, q1, r1 = cons[i]
            for j in range(i + 1, len(cons)):
                p2, q2, r2 = cons[j]
                det = p1 * q2 - p2 * q1
                if abs(det) < 1e-9:
                    continue
                u = (r1 * q2 - r2 * q1) / det
                zz = (p1 * r2 - p2 * r1) / det
                if all(p * u + q * zz <= r + 0.1 for p, q, r in cons):
                    verts.append((u, zz))
        if len(verts) < 3:
            continue
        u0, u1 = min(v[0] for v in verts), max(v[0] for v in verts)
        z0, z1 = min(v[1] for v in verts), max(v[1] for v in verts)
        if z1 - z0 < min_size or u1 - u0 < min_size:
            continue
        a0, a1 = lo + k * w, lo + (k + 1) * w
        if axis == 0:
            out.append({"x": (a0, a1), "y": (u0, u1), "z": (z0, z1), "phi": 0.0, "kind": "slab"})
        else:
            out.append({"x": (u0, u1), "y": (a0, a1), "z": (z0, z1), "phi": 0.0, "kind": "slab"})
    return out


def decompose(planes, pts, slab=SLAB, min_size=0.5, tilt=False, max_slabs=400):
    """The brush as boxes (see the module docstring), [] for a degenerate one.

    `planes` are the brush's real sides (nx, ny, nz, d) and `pts` its hull corners, both in
    the same frame (a brush entity's already moved by its origin).
    """
    if len(pts) < 4:
        return []
    ranges = box_in_frame(pts, 0.0, 0.5)
    if ranges is not None:
        (x0, x1), (y0, y1), (z0, z1) = ranges
        return [{"x": (x0, x1), "y": (y0, y1), "z": (z0, z1), "phi": 0.0, "kind": "box"}]
    tb = turned_box(planes, pts)
    if tb is not None:
        (bx, by, bz), phi = tb
        return [{"x": bx, "y": by, "z": bz, "phi": phi, "kind": "turned"}]
    pb = prism_box(pts)
    if pb is not None:
        (bx, by, bz), phi = pb
        return [{"x": bx, "y": by, "z": bz, "phi": phi, "kind": "prism"}]
    if tilt:
        rb = ramp_box(planes, pts)
        if rb is not None:
            (x0, x1), (y0, y1), (z0, z1) = _bounds(pts)
            return [{"x": (x0, x1), "y": (y0, y1), "z": (z0, z1), "phi": 0.0, "kind": "ramp", "ramp": rb}]
    return slabs(planes, pts, slab, min_size, max_slabs)


def centre(box):
    """The box's centre in map coordinates (undoing its turn)."""
    uc, vc = (box["x"][0] + box["x"][1]) / 2, (box["y"][0] + box["y"][1]) / 2
    c, s = math.cos(math.radians(box["phi"])), math.sin(math.radians(box["phi"]))
    return (uc * c - vc * s, uc * s + vc * c, (box["z"][0] + box["z"][1]) / 2)


def size(box):
    """(along x', along y', along z) of the box, in map units, in its own turned frame."""
    return (box["x"][1] - box["x"][0], box["y"][1] - box["y"][0], box["z"][1] - box["z"][0])


def terrain_cells(tris, cell=80.0, quant=5.0, depth=52.0):
    """Displacement ground as a stepped field of boxes (prop-hunt's and hide-n-seek's --terrain).

    A displacement is a heightmap sculpted over a quad, not a brush, so the box pass finds no
    ground at all in a map whose yard is terrain. The triangles are sampled at the middle of
    `cell`-unit cells (nine sub-samples averaged, so a cell half under a wall still has a
    height), the height rounded to `quant` units and equal neighbours merged: a flat yard is a
    few boxes, not a thousand. Returns boxes as above (`kind` "terrain"), map units.
    """
    if not tris:
        return []
    x0 = min(p[0] for t in tris for p in t)
    y0 = min(p[1] for t in tris for p in t)
    nx = int((max(p[0] for t in tris for p in t) - x0) // cell) + 1
    ny = int((max(p[1] for t in tris for p in t) - y0) // cell) + 1
    acc = {}
    sub = (0.17, 0.5, 0.83)
    for a, b, c in tris:
        mnx, mxx = min(q[0] for q in (a, b, c)), max(q[0] for q in (a, b, c))
        mny, mxy = min(q[1] for q in (a, b, c)), max(q[1] for q in (a, b, c))
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-9:
            continue
        for i in range(int((mnx - x0) // cell), int((mxx - x0) // cell) + 1):
            for j in range(int((mny - y0) // cell), int((mxy - y0) // cell) + 1):
                for fx in sub:
                    for fy in sub:
                        px, py = x0 + (i + fx) * cell, y0 + (j + fy) * cell
                        l1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / d
                        l2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / d
                        l3 = 1 - l1 - l2
                        if min(l1, l2, l3) >= -1e-6:
                            acc.setdefault((i, j), []).append(l1 * a[2] + l2 * b[2] + l3 * c[2])
    h = {k: round(sum(v) / len(v) / quant) * quant for k, v in acc.items()}
    runs = set()
    for j in range(ny):
        i = 0
        while i < nx:
            if (i, j) not in h:
                i += 1
                continue
            e = i
            while (e + 1, j) in h and h[(e + 1, j)] == h[(i, j)]:
                e += 1
            runs.add((i, e, h[(i, j)], j))
            i = e + 1
    out, done = [], set()
    for (i, e, ht, j) in sorted(runs, key=lambda k: (k[3], k[0])):
        if (i, e, ht, j) in done:
            continue
        j2 = j
        while (i, e, ht, j2 + 1) in runs:
            j2 += 1
            done.add((i, e, ht, j2))
        out.append({"x": (x0 + i * cell, x0 + (e + 1) * cell), "y": (y0 + j * cell, y0 + (j2 + 1) * cell),
                    "z": (ht - depth, ht), "phi": 0.0, "kind": "terrain"})
    return out
