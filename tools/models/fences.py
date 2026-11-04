"""Fences, CC0, for `rules/models/categories.tsv`: a chain-link panel, a wooden picket panel and a concrete road barrier, then the long low variants (a rail fence, a split-rail fence, a stacked-log barrier) and a picket corner and end post.

blender -b --factory-startup --python fences.py -- outdir
Writes dm_chainlinkfence, dm_woodfence, dm_jerseybarrier, dm_fencelongrail, dm_fencesplitrail, dm_fencelogstack, dm_fencecorner and dm_fenceendpost (.glb) into outdir. Origin on the floor, centred, the length along X.
Plain colour materials only, under 400 triangles each.
"""
import math
import sys

import bpy

outdir = sys.argv[sys.argv.index("--") + 1]


def mat(name, rgb, rough=0.8, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def box(parts, cx, cy, cz, sx, sy, sz, m, rx=0.0, ry=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    o = bpy.context.object
    o.scale = (sx, sy, sz)
    o.rotation_euler = (rx, ry, 0)
    o.data.materials.append(m)
    parts.append(o)


def cyl(parts, cx, cy, cz, r, h, m, verts=8):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=(cx, cy, cz))
    o = bpy.context.object
    o.data.materials.append(m)
    parts.append(o)


def finish(parts, name, path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    o = bpy.context.object
    o.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.quads_convert_to_tris()
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True, export_yup=True)


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return []


# Chain-link: two posts, top rail, and a diamond lattice of thin bars (a flat wire mesh would be see-through noise at this size).
parts = fresh()
steel, wire = mat("fence_post", (0.45, 0.47, 0.5), 0.5, 0.8), mat("fence_wire", (0.62, 0.64, 0.66), 0.5, 0.7)
L, H = 3.0, 1.9
for x in (-L / 2 + 0.04, L / 2 - 0.04):
    cyl(parts, x, 0, H / 2, 0.04, H, steel)
box(parts, 0, 0, H - 0.03, L, 0.04, 0.04, steel)
box(parts, 0, 0, 0.1, L, 0.03, 0.03, steel)
# Diagonals are clipped to the frame so no wire pokes out; the pitch of the diamonds is about 0.3 m.
x0, x1, z0, z1 = -L / 2 + 0.08, L / 2 - 0.08, 0.13, H - 0.05
pitch = 0.3
for s in (1, -1):
    c = x0 - (z1 - z0) - pitch
    while c < x1 + (z1 - z0):
        # line x = c + s*(z - z0); clip against the four sides
        za, zb = z0, z1
        za = max(za, z0 + (x0 - c) * s) if s > 0 else max(za, z0 - (x1 - c))
        zb = min(zb, z0 + (x1 - c) * s) if s > 0 else min(zb, z0 - (x0 - c))
        if zb - za > 0.05:
            xa, xb = c + s * (za - z0), c + s * (zb - z0)
            ln = math.hypot(xb - xa, zb - za)
            ang = math.atan2(xb - xa, zb - za)
            box(parts, (xa + xb) / 2, 0, (za + zb) / 2, 0.012, 0.012, ln, wire, ry=ang)
        c += pitch
finish(parts, "FenceChainlink", f"{outdir}/dm_chainlinkfence.glb")

# Wooden picket panel with two rails.
parts = fresh()
wood, rail = mat("fence_picket", (0.62, 0.5, 0.33), 0.9), mat("fence_rail", (0.45, 0.34, 0.21), 0.9)
L, H = 2.4, 1.1
for x in (-L / 2 + 0.05, L / 2 - 0.05):
    box(parts, x, 0, H / 2 + 0.05, 0.1, 0.1, H + 0.1, rail)
for z in (0.3, 0.8):
    box(parts, 0, -0.035, z, L, 0.04, 0.08, rail)
pk = 14
w = 0.1
for i in range(pk):
    x = -L / 2 + 0.2 + i * (L - 0.4) / (pk - 1)
    box(parts, x, 0.01, 0.52, w, 0.02, 0.98 - 0.0, wood)
finish(parts, "FenceWood", f"{outdir}/dm_woodfence.glb")

# Concrete road barrier (tapered profile, flat ends).
parts = fresh()
conc = mat("barrier_concrete", (0.66, 0.65, 0.62), 0.95)
L = 3.0
bpy.ops.mesh.primitive_cube_add(size=1)
o = bpy.context.object
o.data.materials.append(conc)
# profile in Y/Z: wide foot, steep taper, narrow top
prof = [(-0.30, 0.0), (0.30, 0.0), (0.30, 0.1), (0.14, 0.45), (0.10, 0.82), (-0.10, 0.82), (-0.14, 0.45), (-0.30, 0.1)]
import bmesh
bm = bmesh.new()
vs0 = [bm.verts.new((-L / 2, y, z)) for y, z in prof]
f = bm.faces.new(vs0)
res = bmesh.ops.extrude_face_region(bm, geom=[f])
vs1 = [v for v in res["geom"] if isinstance(v, bmesh.types.BMVert)]
bmesh.ops.translate(bm, vec=(L, 0, 0), verts=vs1)
bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
bm.to_mesh(o.data)
bm.free()
parts = [o]
finish(parts, "BarrierJersey", f"{outdir}/dm_jerseybarrier.glb")


# Long low rail fence (a whole run in one piece, about 11 m): posts every 1.83 m with struts, three rails.
parts = fresh()
post, rl = mat("rail_post", (0.4, 0.33, 0.24), 0.9), mat("rail_bar", (0.5, 0.42, 0.3), 0.9)
L, H = 11.0, 0.85
for i in range(7):
    x = -L / 2 + 0.05 + i * (L - 0.1) / 6
    box(parts, x, 0, H / 2, 0.1, 0.1, H, post)
    # Leaning struts on both sides give the 0.35 m footprint of the stake fence this replaces.
    for sg in (1, -1):
        box(parts, x, sg * 0.07, 0.38, 0.07, 0.05, 0.8, post, rx=-sg * 0.25)
for z in (0.25, 0.5, H - 0.04):
    box(parts, 0, 0, z, L, 0.04, 0.07, rl)
finish(parts, "FenceLongRail", f"{outdir}/dm_fencelongrail.glb")

# Split-rail fence: crossed posts every 1.6 m with two rails resting in the crosses (about 9.6 m, 0.8 m deep as the zigzag it replaces).
parts = fresh()
post, rl = mat("rail_post", (0.4, 0.33, 0.24), 0.9), mat("rail_bar", (0.5, 0.42, 0.3), 0.9)
L, H = 9.6, 0.88
n = 7
for i in range(n):
    x = -L / 2 + 0.1 + i * (L - 0.2) / (n - 1)
    for s in (1, -1):
        box(parts, x, 0, 0.45, 0.09, 0.09, 1.0, post, rx=s * 0.6)
for z in (0.4, 0.75):
    box(parts, 0, 0, z, L, 0.08, 0.08, rl)
finish(parts, "FenceSplitRail", f"{outdir}/dm_fencesplitrail.glb")

# Stacked-log barrier: three logs in a pyramid held by two crossed-post ends (4 m long, about 1.1 m high).
parts = fresh()
log, post = mat("barrier_log", (0.42, 0.3, 0.2), 0.95), mat("rail_post", (0.4, 0.33, 0.24), 0.9)
L = 4.0
for y, z, r in ((-0.26, 0.26, 0.26), (0.26, 0.26, 0.26), (0.0, 0.7, 0.26)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=r, depth=L, location=(0, y, z), rotation=(0, math.pi / 2, 0))
    o = bpy.context.object
    o.data.materials.append(log)
    parts.append(o)
for x in (-L / 2 + 0.3, L / 2 - 0.3):
    for s in (1, -1):
        box(parts, x, 0, 0.55, 0.1, 0.1, 1.15, post)
        parts[-1].rotation_euler = (s * 0.45, 0, 0)
finish(parts, "FenceLogStack", f"{outdir}/dm_fencelogstack.glb")


def picket_panel(parts, along_y, length, h, m_picket, m_rail):
    # One picket panel from the origin outwards (+X, or glTF -Z when along_y) with two rails.
    def put(a, b, z, la, lb, lz, m):
        # a runs along the panel, b is the depth
        if along_y:
            box(parts, b, a, z, lb, la, lz, m)
        else:
            box(parts, a, b, z, la, lb, lz, m)

    for z in (0.25, 0.65):
        put(length / 2, -0.035, z, length, 0.04, 0.08, m_rail)
    n = int(length / 0.12)
    for i in range(n):
        put(0.06 + i * (length - 0.12) / (n - 1), 0.0, h / 2, 0.1, 0.02, h, m_picket)


# Picket corner: two panels meeting at a post, one along +X and one along -Y, 0.83 m high.
parts = fresh()
wood, rail = mat("fence_picket", (0.62, 0.5, 0.33), 0.9), mat("fence_rail", (0.45, 0.34, 0.21), 0.9)
picket_panel(parts, False, 1.15, 0.83, wood, rail)
picket_panel(parts, True, 1.15, 0.83, wood, rail)
box(parts, 0, 0, 0.45, 0.08, 0.08, 0.9, rail)
finish(parts, "FenceCorner", f"{outdir}/dm_fencecorner.glb")

# Picket end post.
parts = fresh()
wood, rail = mat("fence_picket", (0.62, 0.5, 0.33), 0.9), mat("fence_rail", (0.45, 0.34, 0.21), 0.9)
box(parts, 0, 0, 0.4, 0.08, 0.08, 0.8, rail)
box(parts, 0, 0, 0.82, 0.11, 0.11, 0.04, wood)
finish(parts, "FenceEndPost", f"{outdir}/dm_fenceendpost.glb")
