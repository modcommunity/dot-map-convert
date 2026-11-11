"""Shared Blender helpers for the model scripts that import it (playground.py, helicopter.py): plain colour materials, boxes,
cylinders, bars, and a finish that joins, triangulates and exports one glb with Y up. Blender is Z up, so the scripts here place
parts in Blender axes (X length, Y depth, Z height); the glb comes out with the length along X and Y up.

Use from a script run as `blender -b --factory-startup --python x.py -- outdir`:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import modelkit as mk
"""
import math

import bpy
import mathutils


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return []


def mat(name, rgb, rough=0.8, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def box(parts, c, s, m, rot=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=c)
    o = bpy.context.object
    o.scale = s
    o.rotation_euler = rot
    o.data.materials.append(m)
    parts.append(o)
    return o


def cyl(parts, c, r, h, m, verts=10, rot=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=c)
    o = bpy.context.object
    o.rotation_euler = rot
    o.data.materials.append(m)
    parts.append(o)
    return o


def beam(parts, a, b, thick, m):
    """A square bar from point a to point b."""
    d = mathutils.Vector(b) - mathutils.Vector(a)
    o = box(parts, tuple((x + y) / 2 for x, y in zip(a, b)), (thick, thick, d.length), m)
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = mathutils.Vector((0, 0, 1)).rotation_difference(d)
    return o


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
