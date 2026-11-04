"""A 42U server rack cabinet with rows of rack units and status lights, CC0, for `rules/models/categories.tsv`.

blender -b --factory-startup --python server_rack.py -- out.glb
0.6 x 2.0 x 0.8 m, origin on the floor, centred, front towards +Z.
"""
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, rgb, rough, metal=0.0, emit=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = 2.0
    return m


frame, unit, face, led = mat("rack_frame", (0.06, 0.06, 0.07), 0.5, 0.6), mat("rack_unit", (0.12, 0.12, 0.13), 0.4, 0.7), mat("rack_face", (0.2, 0.2, 0.22), 0.45, 0.5), mat("rack_led", (0.1, 0.9, 0.2), 0.3, 0.0, (0.1, 0.9, 0.2))
parts = []


def box(size, loc, m):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0], -loc[2], loc[1]))
    o = bpy.context.object
    o.scale = (size[0], size[2], size[1])   # arguments are glTF axes (x, y up, z); Blender is Z up
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(m)
    parts.append(o)


W, H, D = 0.6, 2.0, 0.8
box((W, 0.04, D), (0, H - 0.02, 0), frame)       # top
box((W, 0.08, D), (0, 0.04, 0), frame)           # base
for s in (-1, 1):
    box((0.03, H - 0.12, D), (s * (W / 2 - 0.015), H / 2, 0), frame)   # sides
box((W - 0.06, H - 0.12, 0.02), (0, H / 2, -D / 2 + 0.01), frame)      # back
for i in range(22):   # rack units
    z0 = 0.14 + i * 0.083
    h = 0.075 if i % 5 else 0.16
    box((W - 0.1, h, 0.58), (0, z0 + h / 2, 0.0), unit)
    box((W - 0.07, h, 0.02), (0, z0 + h / 2, D / 2 - 0.1), face)
    for k in range(3):
        box((0.012, 0.012, 0.01), (-0.2 + k * 0.03, z0 + h / 2, D / 2 - 0.085), led)
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
bpy.context.object.name = "ServerRack"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True, export_yup=True)
