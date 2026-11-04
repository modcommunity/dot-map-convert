"""A recessed ceiling light panel (thin steel frame around an emissive diffuser), CC0, for `rules/models/categories.tsv`.

blender -b --factory-startup --python light_inset.py -- out.glb
0.21 x 0.03 x 0.21 m, origin at the top, diffuser facing -Y (down).
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


frame, glow = mat("li_frame", (0.80, 0.80, 0.78), 0.5), mat("li_glow", (1.0, 0.97, 0.88), 0.4, 0.0, 3.0)
box((0.21, 0.03, 0.21), (0, -0.015, 0), frame, 0.004)
box((0.17, 0.01, 0.17), (0, -0.032, 0), glow)
finish("LightInset")
