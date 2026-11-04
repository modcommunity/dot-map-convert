"""A horizontal industrial storage tank (domed ends, two saddles, manway, top ladder), CC0, for `rules/models/categories.tsv`.

blender -b --factory-startup --python cooling_tank.py -- out.glb
6 x 2.3 x 2 m (length along X), origin on the floor, centred. Two plain materials (shell, steel), about 1500 triangles.
"""
import math
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, rgb, rough, metal):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


shell, steel = mat("tank_shell", (0.62, 0.64, 0.62), 0.55, 0.6), mat("tank_steel", (0.22, 0.23, 0.24), 0.6, 0.7)
parts = []
R, L, CZ = 0.95, 6.0, 1.3   # shell radius, overall length, axis height
body = L - 2 * 0.45


def add(o, m):
    o.data.materials.append(m)
    parts.append(o)


bpy.ops.mesh.primitive_cylinder_add(radius=R, depth=body, vertices=32, location=(0, 0, CZ), rotation=(0, math.pi / 2, 0))
add(bpy.context.object, shell)
for s in (-1, 1):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=R, segments=32, ring_count=12, location=(s * body / 2, 0, CZ))
    o = bpy.context.object
    o.scale = (0.47 / R, 1, 1)
    add(o, shell)
for s in (-1, 1):   # girth rings
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=0.025, major_segments=32, minor_segments=8,
                                     location=(s * body * 0.28, 0, CZ), rotation=(0, math.pi / 2, 0))
    add(bpy.context.object, steel)
for s in (-1, 1):   # saddles: a cradle block and a base plate
    bpy.ops.mesh.primitive_cube_add(size=1, location=(s * 1.8, 0, 0.18))
    o = bpy.context.object
    o.scale = (0.3, 2.0, 0.36)
    add(o, steel)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(s * 1.8, 0, 0.62))
    o = bpy.context.object
    o.scale = (0.2, 1.5, 0.52)
    add(o, steel)
bpy.ops.mesh.primitive_cylinder_add(radius=0.28, depth=0.1, vertices=24, location=(0.9, 0, CZ + R + 0.02))   # manway
add(bpy.context.object, steel)
bpy.ops.mesh.primitive_cylinder_add(radius=0.18, depth=0.18, vertices=16, location=(-0.9, 0, CZ + R + 0.04))   # vent
add(bpy.context.object, steel)
for s in (-1, 1):   # ladder rails and rungs up the south side
    bpy.ops.mesh.primitive_cylinder_add(radius=0.018, depth=2.2, vertices=8, location=(-2.55, s * 0.18 + 1.12, 1.15))
    add(bpy.context.object, steel)
for i in range(8):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.014, depth=0.36, vertices=8, location=(-2.55, 1.12, 0.25 + i * 0.27),
                                        rotation=(math.pi / 2, 0, 0))
    add(bpy.context.object, steel)
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
c = bpy.context.object
c.name = "CoolingTank"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.shade_smooth()
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True, export_yup=True)
