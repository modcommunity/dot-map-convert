"""A single bed (wooden frame, headboard, footboard, mattress, pillow, blanket), CC0, for `rules/models/categories.tsv`.

blender -b --factory-startup --python bed.py -- out.glb
1.0 x 0.95 x 2.0 m (width X, depth Z), origin on the floor, centred, head at -Z.
"""
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, rgb, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    return m


wood, sheet, blanket = mat("bed_wood", (0.30, 0.17, 0.09), 0.6), mat("bed_sheet", (0.85, 0.85, 0.80), 0.9), mat("bed_blanket", (0.25, 0.32, 0.45), 0.95)
parts = []


def box(size, loc, m, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0], -loc[2], loc[1]))
    o = bpy.context.object
    o.scale = (size[0], size[2], size[1])   # arguments are glTF axes (x, y up, z); Blender is Z up
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        mod = o.modifiers.new("b", "BEVEL")
        mod.width, mod.segments = bevel, 2
    o.data.materials.append(m)
    parts.append(o)
    return o


box((1.0, 0.1, 1.95), (0, 0.28, 0), wood)                           # rail frame
for sx in (-1, 1):
    for sz in (-1, 1):
        box((0.07, 0.3, 0.07), (sx * 0.465, 0.15, sz * 0.91), wood)    # legs
box((1.0, 0.95, 0.06), (0, 0.475, -0.97), wood, 0.01)                # headboard
box((1.0, 0.6, 0.05), (0, 0.3, 0.97), wood, 0.01)                    # footboard
box((0.92, 0.2, 1.85), (0, 0.43, 0.0), sheet, 0.04)                  # mattress
box((0.92, 0.06, 1.2), (0, 0.55, 0.3), blanket, 0.03)                # blanket
box((0.6, 0.12, 0.35), (0, 0.58, -0.7), sheet, 0.05)                 # pillow
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
bpy.context.object.name = "Bed"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True, export_yup=True)
