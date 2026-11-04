"""A wall-mounted electrical power box (grey steel cabinet, hinged door, handle, conduit stubs), CC0, for `rules/models/categories.tsv`.

blender -b --factory-startup --python power_box.py -- out.glb
0.18 x 0.27 x 0.17 m, origin at the bottom centre, front towards +Z.
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


steel, dark, brass = mat("pb_steel", (0.38, 0.40, 0.38), 0.45, 0.6), mat("pb_dark", (0.08, 0.08, 0.08), 0.6), mat("pb_brass", (0.7, 0.55, 0.2), 0.4, 0.8)
box((0.18, 0.27, 0.15), (0, 0.135, -0.01), steel, 0.004)             # body
box((0.165, 0.255, 0.014), (0, 0.135, 0.075), steel, 0.004)          # door
box((0.03, 0.05, 0.012), (0.04, 0.135, 0.087), dark, 0.003)          # handle plate
box((0.014, 0.014, 0.008), (-0.05, 0.19, 0.083), brass, 0.002)       # lock
cyl(0.012, 0.04, (-0.04, 0.275, -0.01), dark, 10)                     # conduit up
cyl(0.012, 0.04, (0.04, -0.005, -0.01), dark, 10)                     # conduit down
finish("PowerBox")
