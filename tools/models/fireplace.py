"""A brick fireplace with a stone mantel and a dark firebox, CC0, for `rules/models/categories.tsv`.

blender -b --factory-startup --python fireplace.py -- out.glb
1.36 x 1.65 x 0.56 m, origin on the floor, centred, opening towards +Z.
"""
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, rgb, rough, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*rgb, 1.0)
        b.inputs["Emission Strength"].default_value = emit
    return m


parts = []


def box(size, loc, m, bevel=0.0, rot=(0, 0, 0)):
    """Arguments are glTF axes (x, y up, z); Blender is Z up."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0], -loc[2], loc[1]))
    o = bpy.context.object
    o.scale = (size[0], size[2], size[1])
    bpy.ops.object.transform_apply(scale=True)
    o.rotation_euler = (rot[0], rot[2], rot[1])
    if bevel:
        mod = o.modifiers.new("b", "BEVEL")
        mod.width, mod.segments = bevel, 2
    o.data.materials.append(m)
    parts.append(o)
    return o


def cyl(radius, height, loc, m, verts=16):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height, vertices=verts, location=(loc[0], -loc[2], loc[1]))
    o = bpy.context.object
    o.data.materials.append(m)
    parts.append(o)
    return o


def finish(name):
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    bpy.context.object.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True, export_yup=True)


brick, stone, soot, iron = mat("fp_brick", (0.50, 0.22, 0.15), 0.9), mat("fp_stone", (0.62, 0.60, 0.56), 0.8), mat("fp_soot", (0.03, 0.025, 0.02), 1.0), mat("fp_iron", (0.08, 0.08, 0.08), 0.5, 0.7)
box((0.28, 0.75, 0.5), (-0.51, 0.375, 0), brick, 0.01)               # left jamb
box((0.28, 0.75, 0.5), (0.51, 0.375, 0), brick, 0.01)                # right jamb
box((1.3, 0.3, 0.5), (0, 0.9, 0), brick)                       # lintel course
box((0.74, 0.72, 0.3), (0, 0.36, -0.1), soot)                          # firebox
box((0.76, 0.04, 0.48), (0, 0.02, 0.01), stone, 0.005)               # hearth floor
box((1.36, 0.08, 0.56), (0, 1.16, 0.03), stone, 0.01)                # mantel
box((0.9, 0.5, 0.3), (0, 1.4, -0.1), brick, 0.01)                    # flue breast
box((0.7, 0.025, 0.02), (0, 0.18, 0.2), iron)                        # grate bar
for sx in (-1, 1):
    box((0.025, 0.18, 0.2), (sx * 0.34, 0.1, 0.1), iron)             # andirons
finish("Fireplace")
