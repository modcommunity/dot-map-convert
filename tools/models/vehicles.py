"""Four low-poly work vehicles, CC0, for `rules/models/categories.tsv`: a box truck, a flatbed truck, a box trailer and a forklift.

blender -b --factory-startup --python vehicles.py -- outdir
Writes dm_boxtruck.glb, dm_flatbedtruck.glb, dm_boxtrailer.glb and dm_forkliftmachine.glb into outdir. Length along X, front at +X, origin on the floor, centred.
Plain colour materials only, under 700 triangles each, real-world scale (the picker rescales).
"""
import math
import sys

import bpy

outdir = sys.argv[sys.argv.index("--") + 1]
M = {}


def mat(name, rgb, rough=0.7, metal=0.0):
    if name not in M:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Base Color"].default_value = (*rgb, 1.0)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        M[name] = m
    return M[name]


def paint(): return mat("paint", (0.72, 0.18, 0.14))
def cargo(): return mat("cargo", (0.82, 0.82, 0.8))
def dark(): return mat("dark", (0.1, 0.1, 0.11), 0.9)
def glass(): return mat("glass", (0.35, 0.5, 0.6), 0.2)
def steel(): return mat("steel", (0.4, 0.42, 0.45), 0.5, 0.6)
def wood(): return mat("deck", (0.5, 0.36, 0.2), 0.9)


def box(parts, x0, x1, y0, y1, z0, z1, m):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    o = bpy.context.object
    o.scale = (x1 - x0, y1 - y0, z1 - z0)
    o.data.materials.append(m)
    parts.append(o)


def wheel(parts, x, y, r, w, m=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=r, depth=w, location=(x, y, r), rotation=(math.pi / 2, 0, 0))
    o = bpy.context.object
    o.data.materials.append(m or dark())
    parts.append(o)
    # hub
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=r * 0.5, depth=w * 1.05, location=(x, y, r), rotation=(math.pi / 2, 0, 0))
    h = bpy.context.object
    h.data.materials.append(steel())
    parts.append(h)


def cab(parts, x0, x1, hw, z0=0.9, top=2.6):
    """Truck cab: lower body plus a glazed upper part, a bonnet is not needed (cab-over)."""
    box(parts, x0, x1, -hw, hw, z0, z0 + 0.7, paint())
    box(parts, x0 + 0.05, x1, -hw + 0.02, hw - 0.02, z0 + 0.7, top, paint())
    box(parts, x1 - 0.01, x1 + 0.02, -hw + 0.12, hw - 0.12, z0 + 0.95, top - 0.35, glass())
    for s in (-1, 1):
        box(parts, x0 + 0.4, x1 - 0.5, s * (hw - 0.01), s * (hw + 0.015), z0 + 0.95, top - 0.35, glass())
    box(parts, x1 - 0.02, x1 + 0.06, -hw, hw, z0, z0 + 0.25, steel())


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
    M.clear()
    return []


def axle_wheels(parts, xs, hw, r=0.5, w=0.3):
    for x in xs:
        for s in (-1, 1):
            wheel(parts, x, s * (hw - 0.05), r, w)


# Box truck, 6.2 x 2.4 x 3.0 m.
p = fresh()
box(p, -3.1, 1.3, -1.15, 1.15, 0.45, 0.85, steel())      # chassis
box(p, -3.1, 1.2, -1.2, 1.2, 0.85, 3.0, cargo())          # cargo box
box(p, -3.12, -3.08, -1.0, 1.0, 1.0, 2.8, steel())        # rear door frame
cab(p, 1.25, 3.1, 1.1, 0.7, 2.6)
axle_wheels(p, (2.2, -1.9, -0.6), 1.2)
finish(p, "TruckBox", f"{outdir}/dm_boxtruck.glb")

# Flatbed truck, 5.6 x 2.3 x 2.6 m.
p = fresh()
box(p, -2.8, 1.0, -1.1, 1.1, 0.5, 0.8, steel())
box(p, -2.8, 1.0, -1.15, 1.15, 0.8, 0.95, wood())         # deck
for s in (-1, 1):
    box(p, -2.8, 1.0, s * 1.1, s * 1.15, 0.95, 1.3, wood())   # side boards
box(p, 0.95, 1.0, -1.15, 1.15, 0.95, 1.9, wood())            # headboard behind the cab
cab(p, 1.05, 2.8, 1.05, 0.7, 2.5)
axle_wheels(p, (1.95, -1.6, -0.5), 1.15, 0.42, 0.3)
finish(p, "TruckFlatbed", f"{outdir}/dm_flatbedtruck.glb")

# Box trailer on a tandem axle with a landing gear and a front kingpin plate, 8 x 2.5 x 3.6 m (deck at 1.1 m).
p = fresh()
box(p, -4.0, 4.0, -1.2, 1.2, 1.0, 1.15, steel())
box(p, -4.0, 4.0, -1.25, 1.25, 1.15, 3.6, cargo())
box(p, -4.02, -3.98, -1.0, 1.0, 1.3, 3.4, steel())
for z in (1.8, 2.6):
    box(p, -4.0, 4.0, -1.255, 1.255, z, z + 0.05, steel())   # ribs
for s in (-1, 1):
    box(p, 3.0, 3.1, s * 1.0, s * 1.1, 0.35, 1.0, steel())    # landing legs
axle_wheels(p, (-2.5, -1.2), 1.25, 0.5, 0.3)
finish(p, "Trailer", f"{outdir}/dm_boxtrailer.glb")

# Forklift, 1.2 x 2.1 x 3.0 m (mast to +X): counterweight rear, seat and overhead guard, mast with two tines.
p = fresh()
box(p, -1.3, 0.5, -0.55, 0.55, 0.3, 0.85, paint())          # body
box(p, -1.45, -0.9, -0.55, 0.55, 0.3, 1.1, steel())         # counterweight
box(p, -0.7, -0.2, -0.3, 0.3, 0.85, 1.15, dark())           # seat
for sx in (-0.85, 0.2):
    for sy in (-0.45, 0.45):
        box(p, sx, sx + 0.05, sy, sy + 0.05, 1.1, 2.05, steel())    # guard posts
box(p, -0.9, 0.3, -0.5, 0.5, 2.05, 2.1, steel())             # guard roof
for s in (-1, 1):
    box(p, 0.55, 0.65, s * 0.4, s * 0.3, 0.2, 2.1, steel())   # mast uprights (two)
box(p, 0.55, 0.65, -0.4, 0.4, 1.5, 1.6, steel())
box(p, 0.65, 0.72, -0.45, 0.45, 0.15, 1.0, steel())          # carriage
for s in (-1, 1):
    box(p, 0.72, 1.7, s * 0.35 - 0.06, s * 0.35 + 0.06, 0.1, 0.18, steel())  # tines
for x, y in ((0.15, -0.55), (0.15, 0.55)):
    wheel(p, x, y, 0.32, 0.22)
for y in (-0.5, 0.5):
    wheel(p, -1.0, y, 0.27, 0.2)
finish(p, "Forklift", f"{outdir}/dm_forkliftmachine.glb")
