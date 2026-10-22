"""A map's drawn world as triangles, and its solid world as convex hulls: the full geometry.

The box path (`boxes`, `gamebox`) cuts every brush into axis boxes, which is lossy by design:
a ramp is slabs, an arch is steps, a displacement (terrain) and a curved tunnel wall are
missing or blocky, and 4-Way Tunnel kept 86% of its drawn area that way. This module keeps
what the mapper drew instead, game-neutral, in game metres and Godot axes:

- `build(bsp, ...)` reads every drawn face of the world and of the drawn brush entities
  (`DRAWN_BRUSH_ENTITIES`, offset by their `origin`), triangulates brush faces in the order
  vbsp stored them (already Godot's front face) and subdivides displacements, and groups the
  triangles into surfaces by (model, material). Each surface carries the source material name,
  the generic material id and tint from `source_textures.tsv` (what a game draws it with: no
  source texture is ever used), the average colour of the original texture as the compiler
  measured it (`colour`, so a replacement can be tinted to the original's palette), and the
  texel size of the original so a game can keep the mapper's texture scale.
- Every player-solid brush of the world and of the solid brush entities becomes a convex hull
  (points and planes), which is the exact solid the mapper drew. Convex per brush, never one
  trimesh: a body sliding along a concave triangle soup catches on every interior edge.
  Displacements collide as their triangles (terrain is not convex), flagged `collide`.
- `write(mesh, prefix)` writes `<prefix>.json` (the manifest) and `<prefix>.bin` (the data);
  `coverage(bsp, mesh)` point-samples the source's drawn faces and solids against what was
  written, and `silhouette` compares the two from above.

Kept from game-g2gfast's `tools/bsp_import.py` (where the mesh path was first built and
measured): the face normal is the face's own plane, never negated by `dface_t.side`; the
winding is not reversed; displacement normals are averaged over the grid while a brush face
keeps its exact plane normal; `rendermode 10`, an alpha render mode at `renderamt 0` and a
`func_brush` that starts disabled are not drawn. The 3D skybox
(`skybox_of`, `sky_scale`) is g2g's too: its room's faces are moved out and scaled up around the
world origin as the engine draws them, flagged `sky3d`, and never collide. Left in g2g for now:
the baked lightmap atlas (a game that bakes its own light does not want the map's), packed
textures (never shipped) and coplanar brush merging.

The binary (`dot-bsp-mesh`, version 1), little-endian:

- a surface's vertices are `vertex_count` records of eight float32: position (3, metres),
  normal (3), uv (2: the source texture's own coordinate divided by its size, so one repeat
  of a replacement is one repeat of the original, laid where the mapper laid it);
- then `index_count` uint32 triangle indices into that surface's vertices;
- a hull is `point_count` float32 triples and `plane_count` float32 quads (nx, ny, nz, d with
  n.p <= d inside), in metres and Godot axes.
"""

import collections
import gzip
import hashlib
import json
import math
import os
import random
import struct

from . import docboxes, reader, texturemap
from . import units as _units

FORMAT = "dot-bsp-mesh"
VERSION = 1

# Brush entities a player SEES. The solid list decides collision and is the wrong list for
# drawing: func_clip_vphysics is solid and invisible, func_illusionary visible and not solid.
DRAWN_BRUSH_ENTITIES = (reader.SOLID_BRUSH_ENTITIES - {"func_clip_vphysics"}) | {
    "func_illusionary", "func_wall_illusionary",
}
# Brush entities a body stands on or is stopped by. A door, a button and a lift are solid
# where they rest; making them move is the entity layer's (map-import-entities), which finds
# the surfaces and hulls by model index.
SOLID_BRUSH_ENTITIES = reader.SOLID_BRUSH_ENTITIES - {"func_illusionary"}

# Render modes whose alpha is `renderamt` (Color, Texture, Glow, Solid, Additive and the
# additive variants). Normal (0) ignores renderamt.
ALPHA_RENDER_MODES = {"1", "2", "3", "4", "5", "7", "8", "9"}

# The .bin is planar per surface (positions, normals, uvs, indices), so a reader slices each
# block straight into a typed array (Godot's PackedByteArray.to_vector3_array) instead of
# de-interleaving in a script loop, and it is gzip'd: float planes compress well apart.
LAYOUT = "per surface: vertex_count float32 xyz positions, then normals, then float32 uv pairs, then index_count uint32"


def hidden(e):
    """Whether a brush entity starts invisible: `rendermode 10`, an alpha render mode at
    `renderamt 0` (a brush an output fades in), or a func_brush that starts disabled."""
    mode = str(e.get("rendermode", "0")).strip()
    if mode == "10":
        return True
    try:
        if mode in ALPHA_RENDER_MODES and float(str(e.get("renderamt", "255")).strip()) <= 0.0:
            return True
    except ValueError:
        pass
    return e.get("classname") == "func_brush" and str(e.get("StartDisabled", "0")).strip() == "1"


def model_entities(bsp):
    """{model index: entity index} for every brush entity (`model` "*N")."""
    out = {}
    for i, e in enumerate(bsp.entities):
        m = str(e.get("model", ""))
        if m.startswith("*") and m[1:].isdigit():
            out[int(m[1:])] = i
    return out


def srgb(refl):
    """The compiler's measured average albedo of a texture (linear) as sRGB, or None when it
    is black and the name does not say black: a `$selfillum` panel measures black and is not."""
    if refl is None or len(refl) < 3 or max(float(c) for c in refl[:3]) < 0.004:
        return None

    def one(c):
        c = max(0.0, min(1.0, float(c)))
        return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055
    return [round(one(c), 4) for c in refl[:3]]


def leaf_of(bsp, point):
    """The world leaf a map-unit point is in, by walking model 0's BSP tree."""
    node = bsp.models[0][9]
    while node >= 0:
        n = bsp.nodes[node]
        pl = bsp.planes[n[0]]
        node = n[1] if pl[0] * point[0] + pl[1] * point[1] + pl[2] * point[2] - pl[3] >= 0 else n[2]
    return -1 - node


def skybox_of(bsp):
    """The 3D skybox: (sky camera origin, its scale, (lo, hi) of its room in map units), or None.

    [b]A 3D skybox is a small room outside the play space, built at a sixteenth of the size
    (the `sky_camera`'s `scale`) and drawn by the engine behind everything, that many times
    larger, as if it surrounded the map.[/b] Imported as ordinary faces it is two faults at
    once: the backdrop is missing and a miniature of it hangs where it was compiled. The room
    is the area the sky camera stands in (every non-solid leaf with that area number, boxed);
    a face all of whose corners are inside that box belongs to it. From game-g2gfast, where
    ten of 26 maps had one; 66 of the 200 maps surveyed here do.
    """
    cams = [e for e in bsp.entities if e.get("classname") == "sky_camera"]
    if not cams or not bsp.nodes:
        return None
    o = tuple(reader.entity_vec(cams[0]))
    try:
        k = float(cams[0].get("scale", "16")) or 16.0
    except ValueError:
        k = 16.0
    leaf = leaf_of(bsp, o)
    if not 0 <= leaf < len(bsp.leafs):
        return None
    area = bsp.leafs[leaf][2] & 0x1FF
    boxes = [(lf[3:6], lf[6:9]) for lf in bsp.leafs if (lf[2] & 0x1FF) == area and not lf[0] & 1]
    if not boxes or area == 0:
        return None
    lo = tuple(min(b[0][a] for b in boxes) - 1 for a in range(3))
    hi = tuple(max(b[1][a] for b in boxes) + 1 for a in range(3))
    return o, k, (lo, hi)


def in_box(p, box):
    return all(box[0][a] <= p[a] <= box[1][a] for a in range(3))


# How far from the world origin the 3D skybox may reach, in map units: inside a camera's
# default 4000 m far plane with room for a player at the edge of a ~300 m map.
SKY_REACH = 3500.0 / _units.VISUAL


def sky_scale(bsp, sky, drawn):
    """The scale the 3D skybox is drawn at: the camera's own, unless that puts its farthest
    face past SKY_REACH; then the largest that brings it inside, but never so small that its
    nearest face comes inside the map's own bounds (the engine draws the sky behind
    everything; drawn into the world here it could stand in the play space). `drawn` is
    [(face, offset)]. g2g measured this on a sky camera saying 512: its islands were 20 km
    out, behind the far plane, imported and invisible."""
    if sky is None:
        return None
    o, k, box = sky
    near, far = math.inf, 0.0
    for f, off in drawn:
        pts = [(p[0] + off[0], p[1] + off[1], p[2] + off[2]) for p in bsp.face_points(f)]
        if pts and all(in_box(p, box) for p in pts):
            for p in pts:
                d = math.dist(o, p)
                near, far = min(near, d), max(far, d)
    if far <= 0.0:
        return k
    lo, hi = bsp.model_bounds(0)
    radius = max(math.dist((0.0, 0.0, 0.0), (x, y, z))
                 for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2]))
    if far * k > SKY_REACH:
        return min(k, max(float(int(SKY_REACH / far)), float(math.ceil(radius / max(near, 1.0)))))
    return k


def _drawn_models(bsp, drawn_classes):
    """[(model, entity index or None, entity, offset)] of the world and every drawn brush entity."""
    owners = model_entities(bsp)
    out = [(0, None, {}, (0.0, 0.0, 0.0))]
    for mi in sorted(owners):
        if 0 < mi < len(bsp.models):
            e = bsp.entities[owners[mi]]
            if e.get("classname") in drawn_classes and not hidden(e):
                out.append((mi, owners[mi], e, tuple(reader.entity_vec(e))))
    return out


def _sky_setup(bsp, drawn_classes):
    """(sky, scale) for `build` and `source_drawn` alike, so both move the same faces."""
    sky = skybox_of(bsp)
    if sky is None:
        return None, None
    drawn = [(f, off) for mi, _ei, _e, off in _drawn_models(bsp, drawn_classes) for f in bsp.model_faces(mi)
             if not bsp.face_material(f)[1] & reader.SKIP_MASK]
    return sky, sky_scale(bsp, sky, drawn)


def _sky_face(bsp, f, off, sky):
    if sky is None:
        return False
    pts = bsp.face_points(f) if f[6] < 0 else [p for t in bsp.displacement_tris(f) for p in t]
    return bool(pts) and all(in_box((p[0] + off[0], p[1] + off[1], p[2] + off[2]), sky[2]) for p in pts)


class Surface:
    __slots__ = ("model", "entity", "classname", "targetname", "material", "generic", "tint",
                 "colour", "texels", "water", "displacement", "collide", "sky3d", "chunk", "verts", "index",
                 "_dedupe")

    def __init__(self, model, entity, classname, targetname, material):
        self.model, self.entity, self.classname, self.targetname = model, entity, classname, targetname
        self.material = material
        self.generic, self.tint, self.colour, self.texels = None, None, None, None
        self.water = self.displacement = self.collide = self.sky3d = False
        self.chunk = None
        self.verts, self.index, self._dedupe = [], [], {}

    def vertex(self, p, n, uv):
        k = (round(p[0], 4), round(p[1], 4), round(p[2], 4), round(n[0], 3), round(n[1], 3),
             round(n[2], 3), round(uv[0], 4), round(uv[1], 4))
        i = self._dedupe.get(k)
        if i is None:
            i = len(self.verts)
            self._dedupe[k] = i
            self.verts.append((p, n, uv))
        return i

    def area(self):
        a = 0.0
        for t in range(0, len(self.index), 3):
            a += _tri_area(*(self.verts[self.index[t + k]][0] for k in range(3)))
        return a


class Mesh:
    """What `build` returns: `surfaces`, `hulls`, the source's identity and what was left out."""

    def __init__(self):
        self.surfaces = []
        self.hulls = []
        self.source = {}
        self.scale = _units.VISUAL
        self.y0 = 0.0
        self.notes = []
        self.sky = None
        self.skipped = collections.Counter()

    def triangles(self, displacements=True):
        """Every drawn triangle as three game-metre points, for a coverage test."""
        for s in self.surfaces:
            if s.displacement and not displacements:
                continue
            for t in range(0, len(s.index), 3):
                yield tuple(s.verts[s.index[t + k]][0] for k in range(3))

    def counts(self):
        return {"surfaces": len(self.surfaces), "vertices": sum(len(s.verts) for s in self.surfaces),
                "triangles": sum(len(s.index) // 3 for s in self.surfaces), "hulls": len(self.hulls),
                "models": len({s.model for s in self.surfaces} | {h["model"] for h in self.hulls})}


def _tri_area(a, b, c):
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    x, y, z = u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]
    return 0.5 * math.sqrt(x * x + y * y + z * z)


def _is_water(name, generic):
    return generic == "water" or "WATER" in name.upper()


CHUNK = 32.0


def build(bsp, tmap=None, scale=_units.VISUAL, y0=0.0, classify=docboxes.classify_material,
          drawn_classes=DRAWN_BRUSH_ENTITIES, solid_classes=SOLID_BRUSH_ENTITIES, chunk=CHUNK):
    """The drawn and solid world of a loaded `reader.Bsp` as a `Mesh`, in metres and Godot axes.

    `tmap` is a `texturemap.TextureMap` (the shared list by default). `y0` is subtracted from
    every height, for a game whose floor is at 0. `drawn_classes` and `solid_classes` say which
    brush entities are drawn and which collide. The world's faces are split into `chunk`-metre
    columns (x, z), one surface per material per column, so a renderer culls what is out of
    view instead of drawing one map-sized surface per material (0 turns it off).
    """
    tmap = tmap or texturemap.load()
    out = Mesh()
    out.scale, out.y0 = scale, y0
    out.source = {"file": os.path.basename(bsp.path), "bytes": len(bsp.d),
                  "sha256": hashlib.sha256(bsp.d).hexdigest(), "bsp_version": bsp.version}
    owners = model_entities(bsp)

    sky, k = _sky_setup(bsp, drawn_classes)
    if sky is not None:
        out.sky = {"camera": list(sky[0]), "scale": k, "camera_scale": sky[1],
                   "room": [list(sky[2][0]), list(sky[2][1])]}

    def g(p, off):
        q = (p[0] + off[0], p[1] + off[1], p[2] + off[2])
        return (q[0] * scale, q[2] * scale - y0, -q[1] * scale)

    def g_sky(p, off):
        # the engine draws sky point q where the world has (q - camera) * scale
        q = [(p[i] + off[i] - sky[0][i]) * k for i in range(3)]
        return (q[0] * scale, q[2] * scale - y0, -q[1] * scale)

    def gn(n):
        return (n[0], n[2], -n[1])

    models = [(0, None)]
    for mi in sorted(owners):
        if 0 < mi < len(bsp.models):
            models.append((mi, owners[mi]))

    surfaces = {}
    for mi, ei in models:
        e = bsp.entities[ei] if ei is not None else {}
        cls = e.get("classname", "worldspawn")
        off = tuple(reader.entity_vec(e)) if ei is not None else (0.0, 0.0, 0.0)
        drawn = mi == 0 or (cls in drawn_classes and not hidden(e))
        if not drawn and mi > 0:
            out.skipped["model:" + cls] += 1
        if drawn:
            for f in bsp.model_faces(mi):
                name, flags = bsp.face_material(f)
                if flags & reader.SKIP_MASK:
                    out.skipped["face:" + reader.clean_material(name)] += 1
                    continue
                in_sky = _sky_face(bsp, f, off, sky)
                if in_sky:
                    out.skipped["face:sky3d_moved"] += 1
                cell = None
                if mi == 0 and chunk > 0 and not in_sky:
                    fp = bsp.face_points(f)
                    if fp:
                        c = g([sum(p[i] for p in fp) / len(fp) for i in range(3)], off)
                        cell = [int(math.floor(c[0] / chunk)), int(math.floor(c[2] / chunk))]
                _add_face(bsp, f, name, mi, ei, cls, e.get("targetname", ""), off, surfaces, tmap,
                          classify, g_sky if in_sky else g, gn, in_sky, cell)
        solid = mi == 0 or cls in solid_classes
        if not solid:
            continue
        for bi in sorted(bsp.model_brushes(mi)):
            if bi >= len(bsp.brushes):
                continue
            contents = bsp.brushes[bi][2]
            if not contents & reader.MASK_PLAYERSOLID:
                continue
            pts = bsp.brush_hull(bi)
            if len(pts) < 4:
                out.skipped["hull:degenerate"] += 1
                continue
            if sky is not None and all(in_box((p[0] + off[0], p[1] + off[1], p[2] + off[2]), sky[2]) for p in pts):
                out.skipped["hull:sky3d"] += 1      # the sky room is scenery, never stood in
                continue
            names = docboxes.brush_material_names(bsp, bi)
            kind = "solid"
            if all(n.startswith("TOOLS/") for n in names):
                kind = "sky" if any("SKYBOX" in n for n in names) else "clip"
            elif contents & reader.CONTENTS_PLAYERCLIP and not contents & reader.CONTENTS_SOLID:
                kind = "clip"
            elif contents & reader.CONTENTS_WINDOW:
                kind = "glass"
            planes = []
            for (nx, ny, nz, d) in bsp.brush_planes(bi, off):
                # n.p <= d in map units; in metres with y0, n' = (nx, nz, -ny), d' = d*s - nz*y0
                planes.append((nx, nz, -ny, d * scale - nz * y0))
            out.hulls.append({"brush": bi, "model": mi, "entity": ei, "classname": cls, "kind": kind,
                              "contents": contents, "points": [g(p, off) for p in pts], "planes": planes})
    out.surfaces = [s for s in surfaces.values() if s.index]
    out.surfaces.sort(key=lambda s: (s.model, s.chunk or [], s.sky3d, s.displacement, s.material))
    return out


def _add_face(bsp, f, name, mi, ei, cls, targetname, off, surfaces, tmap, classify, g, gn, sky3d=False,
              chunk=None):
    disp = f[6] >= 0
    key = (mi, name, disp, sky3d, tuple(chunk) if chunk else None)
    s = surfaces.get(key)
    if s is None:
        s = Surface(mi, ei, cls, targetname, reader.clean_material(name))
        hit = tmap.lookup(classify(name))
        if hit is not None:
            s.generic, s.tint = hit[0], (list(hit[1]) if hit[1] else None)
        s.water = _is_water(name, s.generic)
        s.displacement = disp
        s.collide = disp and not sky3d
        s.sky3d = sky3d
        s.chunk = chunk
        surfaces[key] = s
    ti = bsp.texinfo[f[5]]
    td = int(ti[17])
    tw = th = 1
    if 0 <= td < len(bsp.texdata):
        tw, th = max(1, bsp.texdata[td][4]), max(1, bsp.texdata[td][5])
        if s.colour is None:
            s.colour = srgb(bsp.texdata[td][0:3])
            s.texels = [tw, th]

    def uv(p):
        return ((p[0] * ti[0] + p[1] * ti[1] + p[2] * ti[2] + ti[3]) / tw,
                (p[0] * ti[4] + p[1] * ti[5] + p[2] * ti[6] + ti[7]) / th)

    if disp:
        tris = bsp.displacement_tris(f, with_base=True)
        acc = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
        for t in tris:
            a, b, c = t[0][0], t[1][0], t[2][0]
            u = [b[i] - a[i] for i in range(3)]
            v = [c[i] - a[i] for i in range(3)]
            # The stored order is the front face, whose right-hand cross points INTO the
            # surface; the outward normal is its negation.
            nn = [-(u[1] * v[2] - u[2] * v[1]), -(u[2] * v[0] - u[0] * v[2]), -(u[0] * v[1] - u[1] * v[0])]
            for p, _base in t:
                k = (round(p[0], 2), round(p[1], 2), round(p[2], 2))
                for i in range(3):
                    acc[k][i] += nn[i]
        for t in tris:
            ids = []
            for p, base in t:
                nn = acc[(round(p[0], 2), round(p[1], 2), round(p[2], 2))]
                ln = math.sqrt(sum(c * c for c in nn)) or 1.0
                # A displacement's texture lies on the flat quad it was drawn from.
                ids.append(s.vertex(g(p, off), gn([c / ln for c in nn]), uv(base)))
            if len(set(ids)) == 3:
                s.index.extend(ids)
        return
    pts = bsp.face_points(f)
    if len(pts) < 3:
        return
    n = gn(bsp.planes[f[0]][:3])
    ring = [s.vertex(g(p, off), n, uv(p)) for p in pts]
    for k in range(1, len(ring) - 1):
        tri = (ring[0], ring[k], ring[k + 1])
        if len(set(tri)) == 3:
            s.index.extend(tri)


# --- writing ------------------------------------------------------------------------------

def manifest(mesh, credit=None, name=None):
    return {"format": FORMAT, "version": VERSION, "name": name,
            "units": {"length": "metres", "metres_per_unit": mesh.scale, "y0": mesh.y0,
                      "axes": "Godot (x, z, -y) of the map's", "vertex": LAYOUT,
                      "uv": "source texture coordinate / source texture size"},
            "source": mesh.source, "credit": credit or {}, "counts": mesh.counts(), "sky3d": mesh.sky,
            "skipped": dict(sorted(mesh.skipped.items())), "notes": mesh.notes}


def write(mesh, prefix, credit=None, name=None, extra=None):
    """Write `<prefix>.json` and `<prefix>.bin`; returns the manifest. `extra` is merged into
    the manifest (the CLI puts `movers`, `volumes`, `destinations` and `entity_report` there)."""
    doc = manifest(mesh, credit, name)
    doc.update(extra or {})
    blob = bytearray()
    surfaces = []
    for s in mesh.surfaces:
        n = len(s.verts)
        poff = len(blob)
        blob += struct.pack("<%df" % (3 * n), *[c for v in s.verts for c in v[0]])
        noff = len(blob)
        blob += struct.pack("<%df" % (3 * n), *[c for v in s.verts for c in v[1]])
        uoff = len(blob)
        blob += struct.pack("<%df" % (2 * n), *[c for v in s.verts for c in v[2]])
        ioff = len(blob)
        blob += struct.pack("<%dI" % len(s.index), *s.index)
        rec = {"model": s.model, "entity": s.entity, "classname": s.classname, "material": s.material,
               "generic": s.generic, "vertex_count": n, "position_offset": poff,
               "normal_offset": noff, "uv_offset": uoff,
               "index_offset": ioff, "index_count": len(s.index)}
        for k in ("targetname", "tint", "colour", "texels", "chunk"):
            v = getattr(s, k)
            if v:
                rec[k] = v
        for k in ("water", "displacement", "collide", "sky3d"):
            if getattr(s, k):
                rec[k] = True
        surfaces.append(rec)
    hulls = []
    for h in mesh.hulls:
        poff = len(blob)
        for p in h["points"]:
            blob += struct.pack("<3f", *p)
        qoff = len(blob)
        for q in h["planes"]:
            blob += struct.pack("<4f", *q)
        hulls.append({"brush": h["brush"], "model": h["model"], "entity": h["entity"], "kind": h["kind"],
                      "point_offset": poff, "point_count": len(h["points"]),
                      "plane_offset": qoff, "plane_count": len(h["planes"])})
    doc["surfaces"] = surfaces
    doc["hulls"] = hulls
    packed = gzip.compress(bytes(blob), compresslevel=9, mtime=0)
    doc["bin"] = {"file": os.path.basename(prefix) + ".bin", "compression": "gzip", "bytes": len(blob),
                  "stored_bytes": len(packed), "sha256": hashlib.sha256(packed).hexdigest()}
    os.makedirs(os.path.dirname(os.path.abspath(prefix)) or ".", exist_ok=True)
    with open(prefix + ".bin", "wb") as f:
        f.write(packed)
    with open(prefix + ".json", "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    return doc


def read(prefix):
    """(manifest, Mesh) back from `write`'s files: the round trip the tests and a checker use."""
    with open(prefix + ".json") as f:
        doc = json.load(f)
    with open(prefix + ".bin", "rb") as f:
        blob = f.read()
    if doc.get("bin", {}).get("compression") == "gzip":
        blob = gzip.decompress(blob)
    if doc.get("format") != FORMAT or int(doc.get("version", 0)) > VERSION:
        raise ValueError("%s is not a %s v%d manifest" % (prefix, FORMAT, VERSION))
    m = Mesh()
    m.scale = doc["units"]["metres_per_unit"]
    for rec in doc["surfaces"]:
        s = Surface(rec["model"], rec["entity"], rec["classname"], rec.get("targetname", ""), rec["material"])
        s.generic, s.water, s.displacement = rec.get("generic"), rec.get("water", False), rec.get("displacement", False)
        s.collide, s.sky3d, s.tint, s.colour = rec.get("collide", False), rec.get("sky3d", False), rec.get("tint"), rec.get("colour")
        s.texels, s.chunk = rec.get("texels"), rec.get("chunk")
        n = rec["vertex_count"]
        pos = struct.unpack_from("<%df" % (3 * n), blob, rec["position_offset"])
        nor = struct.unpack_from("<%df" % (3 * n), blob, rec["normal_offset"])
        uvs = struct.unpack_from("<%df" % (2 * n), blob, rec["uv_offset"])
        for i in range(n):
            s.verts.append((pos[3 * i:3 * i + 3], nor[3 * i:3 * i + 3], uvs[2 * i:2 * i + 2]))
        s.index = list(struct.unpack_from("<%dI" % rec["index_count"], blob, rec["index_offset"]))
        m.surfaces.append(s)
    for rec in doc["hulls"]:
        pts = [struct.unpack_from("<3f", blob, rec["point_offset"] + 12 * i) for i in range(rec["point_count"])]
        pls = [struct.unpack_from("<4f", blob, rec["plane_offset"] + 16 * i) for i in range(rec["plane_count"])]
        m.hulls.append({"brush": rec["brush"], "model": rec["model"], "entity": rec["entity"], "kind": rec["kind"],
                        "points": pts, "planes": pls})
    return doc, m


# --- checking what was kept ---------------------------------------------------------------

class _TriGrid:
    """Triangles bucketed on a coarse 3D grid, for "is this point on some triangle?"."""

    def __init__(self, tris, cell=1.0):
        self.cell, self.cells = cell, collections.defaultdict(list)
        for t in tris:
            if _tri_area(*t) < 1e-12:
                continue        # a sliver has no surface to be near, and its edges divide by zero
            lo = [min(p[k] for p in t) for k in range(3)]
            hi = [max(p[k] for p in t) for k in range(3)]
            for x in range(int(math.floor(lo[0] / cell)), int(math.floor(hi[0] / cell)) + 1):
                for y in range(int(math.floor(lo[1] / cell)), int(math.floor(hi[1] / cell)) + 1):
                    for z in range(int(math.floor(lo[2] / cell)), int(math.floor(hi[2] / cell)) + 1):
                        self.cells[(x, y, z)].append(t)

    def near(self, p, eps):
        c = tuple(int(math.floor(p[k] / self.cell)) for k in range(3))
        for t in self.cells.get(c, ()):
            if _point_tri_distance(p, t) <= eps:
                return True
        return False


def _point_tri_distance(p, t):
    """Distance from a point to a triangle (Ericson's closest-point test)."""
    a, b, c = t

    def sub(u, v):
        return (u[0] - v[0], u[1] - v[1], u[2] - v[2])

    def dot(u, v):
        return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    ab, ac, ap = sub(b, a), sub(c, a), sub(p, a)
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        q = a
    else:
        bp = sub(p, b)
        d3, d4 = dot(ab, bp), dot(ac, bp)
        cp = sub(p, c)
        d5, d6 = dot(ab, cp), dot(ac, cp)
        vc, vb, va = d1 * d4 - d3 * d2, d5 * d2 - d1 * d6, d3 * d6 - d5 * d4
        if d3 >= 0 and d4 <= d3:
            q = b
        elif d6 >= 0 and d5 <= d6:
            q = c
        elif vc <= 0 and d1 >= 0 and d3 <= 0:
            v = d1 / (d1 - d3)
            q = (a[0] + v * ab[0], a[1] + v * ab[1], a[2] + v * ab[2])
        elif vb <= 0 and d2 >= 0 and d6 <= 0:
            w = d2 / (d2 - d6)
            q = (a[0] + w * ac[0], a[1] + w * ac[1], a[2] + w * ac[2])
        elif va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
            w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
            q = (b[0] + w * (c[0] - b[0]), b[1] + w * (c[1] - b[1]), b[2] + w * (c[2] - b[2]))
        else:
            den = 1.0 / (va + vb + vc)
            v, w = vb * den, vc * den
            q = (a[0] + ab[0] * v + ac[0] * w, a[1] + ab[1] * v + ac[1] * w, a[2] + ab[2] * v + ac[2] * w)
    d = sub(p, q)
    return math.sqrt(dot(d, d))


def _sample_tri(t, rng):
    r1, r2 = rng.random(), rng.random()
    if r1 + r2 > 1.0:
        r1, r2 = 1.0 - r1, 1.0 - r2
    a, b, c = t
    return tuple(a[k] + r1 * (b[k] - a[k]) + r2 * (c[k] - a[k]) for k in range(3))


def source_drawn(bsp, scale=_units.VISUAL, y0=0.0, drawn_classes=DRAWN_BRUSH_ENTITIES):
    """Every triangle the SOURCE draws, independently of `build`'s grouping: the reference.
    3D skybox faces are placed where the engine draws them, as `build` places them."""
    sky, k = _sky_setup(bsp, drawn_classes)
    out = []
    for mi, _ei, _e, off in _drawn_models(bsp, drawn_classes):
        for f in bsp.model_faces(mi):
            name, flags = bsp.face_material(f)
            if flags & reader.SKIP_MASK:
                continue
            if _sky_face(bsp, f, off, sky):
                def g(p, off=off):
                    q = [(p[i] + off[i] - sky[0][i]) * k for i in range(3)]
                    return (q[0] * scale, q[2] * scale - y0, -q[1] * scale)
            else:
                def g(p, off=off):
                    return ((p[0] + off[0]) * scale, (p[2] + off[2]) * scale - y0, -(p[1] + off[1]) * scale)
            if f[6] >= 0:
                out.extend((g(t[0]), g(t[1]), g(t[2])) for t in bsp.displacement_tris(f))
            else:
                p = [g(q) for q in bsp.face_points(f)]
                out.extend((p[0], p[k2], p[k2 + 1]) for k2 in range(1, len(p) - 1))
    return out


def coverage(bsp, mesh, per_m2=4.0, eps=0.02, solid_samples=20000, seed=1):
    """How much of the source survived, by sampling the source and asking the output.

    `drawn`: area-weighted points on every face the source draws (world and drawn brush
    entities, displacements included), each counted when it lies within `eps` metres of an
    output triangle. `solid`: points inside the source's player-solid brushes, counted when
    inside an output hull (by the hull's own planes). Both are shares 0..1, with the source
    totals; `missing` lists the materials whose drawn area went missing most.
    """
    rng = random.Random(seed)
    grid = _TriGrid(list(mesh.triangles()), cell=1.0)
    src = source_drawn(bsp, mesh.scale, mesh.y0)
    total = hit = 0
    area = 0.0
    for t in src:
        a = _tri_area(*t)
        area += a
        n = int(a * per_m2) + (1 if rng.random() < (a * per_m2) % 1.0 else 0)
        for _ in range(n):
            total += 1
            if grid.near(_sample_tri(t, rng), eps):
                hit += 1
    # Solids: brushes of the world and the solid brush entities that a player is stopped by.
    # The 3D skybox room is skipped as `build` skips it: scenery, never stood in.
    owners = model_entities(bsp)
    sky = skybox_of(bsp)
    brushes = []
    for mi in [0] + sorted(owners):
        if not 0 <= mi < len(bsp.models):
            continue
        e = bsp.entities[owners[mi]] if mi in owners else {}
        if mi > 0 and e.get("classname") not in SOLID_BRUSH_ENTITIES:
            continue
        off = reader.entity_vec(e) if mi > 0 else (0.0, 0.0, 0.0)
        for bi in bsp.model_brushes(mi):
            if bi < len(bsp.brushes) and bsp.brushes[bi][2] & reader.MASK_PLAYERSOLID:
                pts = bsp.brush_hull(bi)
                if len(pts) < 4 or (sky is not None and all(
                        in_box((p[0] + off[0], p[1] + off[1], p[2] + off[2]), sky[2]) for p in pts)):
                    continue
                brushes.append((bi, off, pts))
    vols = []
    for bi, off, pts in brushes:
        lo = [min(p[k] for p in pts) for k in range(3)]
        hi = [max(p[k] for p in pts) for k in range(3)]
        vols.append(max(1e-6, (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])))
    hulls = collections.defaultdict(list)
    for h in mesh.hulls:
        lo = [min(p[k] for p in h["points"]) for k in range(3)]
        hi = [max(p[k] for p in h["points"]) for k in range(3)]
        for x in range(int(math.floor(lo[0] / 2.0)), int(math.floor(hi[0] / 2.0)) + 1):
            for z in range(int(math.floor(lo[2] / 2.0)), int(math.floor(hi[2] / 2.0)) + 1):
                hulls[(x, z)].append(h)
    s_total = s_hit = 0
    if brushes:
        for _ in range(solid_samples):
            bi, off, pts = rng.choices(brushes, weights=vols)[0]
            lo = [min(p[k] for p in pts) for k in range(3)]
            hi = [max(p[k] for p in pts) for k in range(3)]
            for _try in range(20):
                q = tuple(lo[k] + rng.random() * (hi[k] - lo[k]) for k in range(3))
                if bsp.point_in_brush(bi, q, epsilon=-0.01):
                    break
            else:
                continue
            gp = ((q[0] + off[0]) * mesh.scale, (q[2] + off[2]) * mesh.scale - mesh.y0, -(q[1] + off[1]) * mesh.scale)
            s_total += 1
            for h in hulls.get((int(math.floor(gp[0] / 2.0)), int(math.floor(gp[2] / 2.0))), ()):
                if all(pl[0] * gp[0] + pl[1] * gp[1] + pl[2] * gp[2] <= pl[3] + 1e-3 for pl in h["planes"]):
                    s_hit += 1
                    break
    return {"drawn": hit / total if total else 1.0, "drawn_samples": total, "drawn_area_m2": round(area, 1),
            "solid": s_hit / s_total if s_total else 1.0, "solid_samples": s_total,
            "source_triangles": len(src), "output_triangles": mesh.counts()["triangles"]}


def silhouette(tris, cell=0.5, axis=1):
    """The set of grid cells a list of triangles covers seen along `axis` (1: from above)."""
    keep = [k for k in range(3) if k != axis]
    out = set()
    for t in tris:
        a, b, c = ([p[k] for k in keep] for p in t)
        lo = [min(a[i], b[i], c[i]) for i in range(2)]
        hi = [max(a[i], b[i], c[i]) for i in range(2)]
        for x in range(int(math.floor(lo[0] / cell)), int(math.floor(hi[0] / cell)) + 1):
            for y in range(int(math.floor(lo[1] / cell)), int(math.floor(hi[1] / cell)) + 1):
                px, py = (x + 0.5) * cell, (y + 0.5) * cell
                if _in_tri2(px, py, a, b, c, cell * 0.5):
                    out.add((x, y))
    return out


def _in_tri2(px, py, a, b, c, pad):
    def side(p, q):
        return (q[0] - p[0]) * (py - p[1]) - (q[1] - p[1]) * (px - p[0])
    d1, d2, d3 = side(a, b), side(b, c), side(c, a)
    if (d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0):
        return True
    # A sliver seen edge-on (a wall from above) covers the cells it passes through.
    for p, q in ((a, b), (b, c), (c, a)):
        dx, dy = q[0] - p[0], q[1] - p[1]
        ln2 = dx * dx + dy * dy
        tt = 0.0 if ln2 == 0 else max(0.0, min(1.0, ((px - p[0]) * dx + (py - p[1]) * dy) / ln2))
        if math.hypot(px - (p[0] + tt * dx), py - (p[1] + tt * dy)) <= pad:
            return True
    return False


def silhouette_diff(bsp, mesh, cell=0.5):
    """Top-down and side silhouettes of the source and the output: the share of source cells
    the output also covers, per view."""
    src = source_drawn(bsp, mesh.scale, mesh.y0)
    got = list(mesh.triangles())
    out = {}
    for label, axis in (("top", 1), ("side_x", 0), ("side_z", 2)):
        a, b = silhouette(src, cell, axis), silhouette(got, cell, axis)
        out[label] = {"source_cells": len(a), "kept": len(a & b) / len(a) if a else 1.0, "extra": len(b - a)}
    return out
