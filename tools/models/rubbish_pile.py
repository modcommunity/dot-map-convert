"""A pile of rubbish (torn bags, a crate, cartons and cans heaped together), CC0, for `rules/models/categories.tsv`.

blender -b --factory-startup --python rubbish_pile.py -- out.glb
0.9 x 0.6 x 0.8 m, origin on the floor, centred.
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


bag, bag2, card, can, crate = mat("rp_bag", (0.05, 0.05, 0.06), 0.4), mat("rp_bag2", (0.25, 0.30, 0.22), 0.45), mat("rp_card", (0.55, 0.42, 0.26), 0.9), mat("rp_can", (0.6, 0.6, 0.62), 0.35, 0.8), mat("rp_crate", (0.32, 0.2, 0.1), 0.8)
import math
for i, (x, z, r) in enumerate([(-0.2, -0.1, 0.24), (0.15, 0.1, 0.27), (0.0, -0.2, 0.2), (-0.15, 0.2, 0.2), (0.28, -0.15, 0.18)]):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=12, ring_count=8, location=(x, -z, r * 0.85))
    o = bpy.context.object
    o.scale = (1.0, 0.9, 0.85)
    bpy.ops.object.shade_smooth()
    o.data.materials.append(bag if i % 2 == 0 else bag2)
    parts.append(o)
box((0.4, 0.28, 0.3), (-0.05, 0.14, 0.05), crate, 0.01, (0, 0.5, 0))
box((0.3, 0.22, 0.22), (0.22, 0.45, 0.0), card, 0.01, (0.2, -0.4, 0.15))
box((0.34, 0.1, 0.24), (-0.28, 0.1, -0.22), card, 0.01, (0, 0.7, 0))
for x, y, z, rx in [(0.3, 0.06, 0.28, 1.5), (-0.3, 0.08, 0.3, 0.2), (0.0, 0.32, 0.3, 1.2), (0.38, 0.1, 0.0, 0.5)]:
    c = cyl(0.04, 0.11, (x, y, z), can, 10)
    c.rotation_euler = (rx, 0.3, 0)
finish("RubbishPile")
