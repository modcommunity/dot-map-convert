"""Three fences, CC0, for `rules/models/categories.tsv`: a chain-link panel, a wooden picket panel and a concrete road barrier.

blender -b --factory-startup --python fences.py -- outdir
Writes dm_chainlinkfence.glb, dm_woodfence.glb and dm_jerseybarrier.glb into outdir. Origin on the floor, centred, the length along X.
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
