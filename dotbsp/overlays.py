"""The decals and detail grass a map's compiler moved out of its entities, as mesh geometry.

`info_overlay` decals (`reader.Bsp.overlays`) are cut to the faces they were laid on; `dprp` detail
sprites (`reader.Bsp.detail_sprites`) become two crossed upright cards each. `mesh.build` draws
them only when asked (`regen --overlays`, `--detail`, or `--no-omit`), so a map converted without
them is byte-for-byte what it was.
"""

import math

# map units an overlay sits off its face per render order step: far enough that it never
# fights the face for depth at range, near enough that no gap shows at its edge
LIFT = 0.25


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))


def clip(poly, quad):
    """Sutherland-Hodgman: `poly` (tuples whose first two values are overlay-plane u, v) cut to the
    convex `quad`; the other values of a point are interpolated along the cut edges."""
    area = sum(quad[i - 1][0] * quad[i][1] - quad[i][0] * quad[i - 1][1] for i in range(4))
    sign = 1.0 if area >= 0 else -1.0
    for i in range(4):
        a, b = quad[i - 1], quad[i]

        def inside(p):
            return sign * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))

        out = []
        for k in range(len(poly)):
            p, q = poly[k - 1], poly[k]
            sp, sq = inside(p), inside(q)
            if sq >= 0:
                if sp < 0:
                    out.append(_lerp(p, q, sp / (sp - sq)))
                out.append(q)
            elif sp >= 0:
                out.append(_lerp(p, q, sp / (sp - sq)))
        poly = out
        if len(poly) < 3:
            return []
    return poly


def quad_params(quad, x, y):
    """(a, b) where the bilinear `quad` at a along corner 0->3 and b along 0->1 is the point x, y."""
    q0, q1, q2, q3 = quad
    e = (q3[0] - q0[0], q3[1] - q0[1])
    f = (q1[0] - q0[0], q1[1] - q0[1])
    h = (q0[0] - q1[0] + q2[0] - q3[0], q0[1] - q1[1] + q2[1] - q3[1])
    a = b = 0.5
    for _ in range(12):
        rx = q0[0] + a * e[0] + b * f[0] + a * b * h[0] - x
        ry = q0[1] + a * e[1] + b * f[1] + a * b * h[1] - y
        j00, j01, j10, j11 = e[0] + b * h[0], f[0] + a * h[0], e[1] + b * h[1], f[1] + a * h[1]
        det = j00 * j11 - j01 * j10
        if abs(det) < 1e-12:
            break
        a -= (rx * j11 - ry * j01) / det
        b -= (ry * j00 - rx * j10) / det
    return a, b


def _normal(bsp, f, tri):
    if f[6] < 0:
        return tuple(bsp.planes[f[0]][:3])
    a, b, c = tri[0][0], tri[1][0], tri[2][0]
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    # the stored displacement order's right-hand cross points into the surface (mesh._add_face)
    n = (-(u[1] * v[2] - u[2] * v[1]), -(u[2] * v[0] - u[0] * v[2]), -(u[0] * v[1] - u[1] * v[0]))
    ln = math.sqrt(_dot(n, n)) or 1.0
    return (n[0] / ln, n[1] / ln, n[2] / ln)


def overlay_polys(bsp, o, faces):
    """[(face index, normal, [(point, base point, (u, v)), ...])]: overlay `o` cut to each listed face
    that is in `faces`. A displacement is cut on its flat base, where its texture lies, and the polygon
    follows the displaced surface; corner 0 takes texture (u0, v0), 1 (u0, v1), 2 (u1, v1), 3 (u1, v0)."""
    org, bu, bv, quad = o["origin"], o["basis_u"], o["basis_v"], o["corners"]
    (u0, u1), (v0, v1) = o["u"], o["v"]
    out = []
    for fi in o["faces"]:
        if fi not in faces:
            continue
        f = bsp.faces[fi]
        if f[6] >= 0:
            tris = [[(p, base) for p, base in t] for t in bsp.displacement_tris(f, with_base=True)]
        else:
            pts = bsp.face_points(f)
            tris = [[(p, p) for p in pts]] if len(pts) >= 3 else []
        for t in tris:
            poly = []
            for p, base in t:
                d = (base[0] - org[0], base[1] - org[1], base[2] - org[2])
                poly.append((_dot(d, bu), _dot(d, bv)) + tuple(p) + tuple(base))
            cut = clip(poly, quad)
            if len(cut) < 3:
                continue
            ring = []
            for v in cut:
                a, b = quad_params(quad, v[0], v[1])
                ring.append((v[2:5], v[5:8], (u0 + (u1 - u0) * a, v0 + (v1 - v0) * b)))
            out.append((fi, _normal(bsp, f, t), ring))
    return out


def sprite_cards(sprite, prop):
    """The two crossed upright quads of one detail sprite, each four (point, (u, v)) in map units."""
    (x0, top), (x1, bottom) = sprite["ul"], sprite["lr"]
    (s0, t0), (s1, t1) = sprite["tex_ul"], sprite["tex_lr"]
    k = prop["scale"]
    ox, oy, oz = prop["origin"]
    cards = []
    for yaw in (prop["angles"][1], prop["angles"][1] + 90.0):
        r = math.radians(yaw)
        rx, ry = -math.sin(r), math.cos(r)
        cards.append([((ox + rx * x * k, oy + ry * x * k, oz + z * k), uv) for x, z, uv in
                      ((x0, bottom, (s0, t1)), (x1, bottom, (s1, t1)), (x1, top, (s1, t0)), (x0, top, (s0, t0)))])
    return cards


def world_faces(bsp):
    """The world model's face indices: an overlay laid on a moving brush is not drawn."""
    if not bsp.models:
        return set()
    m = bsp.models[0]
    return set(range(m[10], m[10] + m[11]))


def sky_move(sky):
    """A function moving a map point inside the 3D skybox room out to where the world pack draws it
    (`mesh.build`'s g_sky: (p - camera) * scale, the engine drawing the sky camera at the world origin), and leaving every other point; `sky` is
    (camera, drawn scale, (lo, hi) room box) or None. With it, `inside(points)` says whether all are
    in the room."""
    if sky is None:
        return (lambda p: p), (lambda pts: False)
    cam, k, (lo, hi) = sky

    def inside(pts):
        return bool(pts) and all(all(lo[a] <= p[a] <= hi[a] for a in range(3)) for p in pts)

    return (lambda p: tuple((p[i] - cam[i]) * k for i in range(3))), inside


def ground(bsp, faces, to, cell=2.0, sky=None):
    """height(x, z): the highest displacement point `to` (map units -> (x, y, z) with y up) puts in the
    `cell`-wide square holding x, z, or None where no displacement lies. Brushes are left out: a
    camera is only ever lost under terrain, whose surface stands off its base plane. A displacement in
    the 3D skybox room (`sky`, see `sky_move`) counts where the world pack draws it, moved out."""
    move, inside = sky_move(sky)
    top = {}
    for fi in faces:
        f = bsp.faces[fi]
        if f[6] < 0:
            continue
        tris = bsp.displacement_tris(f)
        moved = inside([p for t in tris for p in t])
        for t in tris:
            pts = [to(move(p) if moved else p) for p in t]
            y = max(p[1] for p in pts)
            for i in range(math.floor(min(p[0] for p in pts) / cell), math.floor(max(p[0] for p in pts) / cell) + 1):
                for k in range(math.floor(min(p[2] for p in pts) / cell), math.floor(max(p[2] for p in pts) / cell) + 1):
                    if top.get((i, k), -math.inf) < y:
                        top[(i, k)] = y
    return lambda x, z: top.get((math.floor(x / cell), math.floor(z / cell)))


def view_of(at, height, reach=(8.0, 12.0), clear=2.5, above=4.0, rise=30.0, step=2.0):
    """A camera point looking at `at` (y up) from `reach` away, `clear` over the ground `height` gives
    under it and `above` over `at`, whose sight line keeps over the ground; the lowest such, or None.

    An info_overlay's origin lies on its face's base plane, which under a displacement can be tens of
    metres below the drawn ground: a view picked round the origin shoots from inside the hill."""
    def over(x, y, z, margin):
        g = height(x, z)
        return g is None or y > g + margin

    best = None
    for dist in reach:
        for deg in range(0, 360, 30):
            x, z = at[0] + dist * math.cos(math.radians(deg)), at[2] + dist * math.sin(math.radians(deg))
            g = height(x, z)
            y = max(at[1] + above, (g if g is not None else -math.inf) + clear)
            top = y + rise
            while y <= top:
                # the first quarter of the line is the decal's own slope, and its end the decal itself
                if all(over(at[0] + (x - at[0]) * t, at[1] + (y - at[1]) * t, at[2] + (z - at[2]) * t, -0.3)
                       for t in [i / 20.0 for i in range(5, 20)]):
                    if best is None or y - at[1] < best[1] - at[1]:
                        best = (x, y, z)
                    break
                y += step
    return best


def overlay_views(bsp, match, to, name="overlay", sky=None):
    """[(view name, camera, target)] for every world overlay whose texture contains `match`
    (case-insensitive): the target is the middle of the drawn decal, on the displaced surface. One in
    the 3D skybox room (`sky`: camera, drawn scale, room box, as `mesh.build` moves it) is aimed at
    where the pack draws it, moved out and that many times larger, from that much farther off."""
    faces = world_faces(bsp)
    height = ground(bsp, faces, to, sky=sky)
    move, inside = sky_move(sky)
    out = []
    for o in bsp.overlays():
        texdata = int(bsp.texinfo[o["texinfo"]][17])
        if match.lower() not in bsp.texnames[bsp.texdata[texdata][3]].lower():
            continue
        polys = overlay_polys(bsp, o, faces)
        if not polys:
            continue
        f = bsp.faces[polys[0][0]]
        in_sky = inside(bsp.face_points(f) if f[6] < 0 else [p for t in bsp.displacement_tris(f) for p in t])
        k = sky[1] if in_sky else 1.0
        pts = [to(move(p) if in_sky else p) for _, _, ring in polys for p, _base, _uv in ring]
        at = tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))
        view = view_of(at, height, reach=(8.0 * k, 12.0 * k), clear=2.5, above=4.0 * k, rise=30.0 * k,
                       step=2.0 * k) if in_sky else view_of(at, height)
        out.append(("%s_%d" % (name, o["id"]), view, at))
    return out
