"""A kitchen cabinet unit with a steel basin (a basin in a worktop on a painted cabinet, tap and doors), CC0, for `rules/models/categories.tsv`.

blender -b --factory-startup --python basin_unit.py -- out.glb
0.5 x 0.85 x 0.4 m, origin on the floor, centred, front towards +Z.
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


paint, top, steel = mat("bu_paint", (0.78, 0.76, 0.70), 0.7), mat("bu_top", (0.22, 0.20, 0.18), 0.5), mat("bu_steel", (0.72, 0.74, 0.76), 0.25, 0.9)
box((0.5, 0.76, 0.38), (0, 0.38, 0.01), paint, 0.005)                 # cabinet
box((0.5, 0.04, 0.4), (0, 0.78, 0), top, 0.004)                       # worktop
box((0.34, 0.012, 0.24), (0, 0.806, 0.03), steel)                     # basin plate
box((0.3, 0.02, 0.2), (0, 0.79, 0.03), mat("bu_dark", (0.05, 0.05, 0.05), 0.5))  # basin well
box((0.5, 0.07, 0.03), (0, 0.835, -0.185), top, 0.004)                # splashback
cyl(0.015, 0.2, (0, 0.9, -0.14), steel, 10)                           # tap stem
box((0.02, 0.02, 0.12), (0, 0.99, -0.08), steel, 0.005)               # spout
box((0.44, 0.66, 0.012), (0, 0.38, 0.205), paint, 0.004)              # door
cyl(0.012, 0.012, (0.18, 0.55, 0.218), steel, 8).rotation_euler = (1.5708, 0, 0)
finish("BasinUnit")
