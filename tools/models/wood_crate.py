"""A 1 m cubic wooden shipping crate (corner posts, slatted faces, lid battens), CC0, for `rules/models/categories.tsv`.

blender -b --factory-startup --python wood_crate.py -- out.glb
Origin on the floor, centred. Two plain colour materials (planks, battens), about 200 triangles.
"""
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = 0.85
    return m


plank, batten = mat("crate_plank", (0.52, 0.36, 0.20)), mat("crate_batten", (0.38, 0.25, 0.13))
parts = []


def box(cx, cy, cz, sx, sy, sz, m):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    o = bpy.context.object
    o.scale = (sx, sy, sz)
    o.data.materials.append(m)
    parts.append(o)


S, P, T = 1.0, 0.09, 0.035   # side, corner post, slat depth
h = S / 2
for sx in (-1, 1):
    for sy in (-1, 1):
        box(sx * (h - P / 2), sy * (h - P / 2), h, P, P, S, batten)
slats, gap = 5, 0.012
sh = (S - gap * (slats - 1)) / slats
for i in range(slats):
    z = sh / 2 + i * (sh + gap)
    for side in (-1, 1):
        box(side * (h - T / 2), 0, z, T, S - 2 * P, sh, plank)
        box(0, side * (h - T / 2), z, S - 2 * P, T, sh, plank)
for z in (T / 2, S - T / 2):
    box(0, 0, z, S - 2 * P, S - 2 * P, T, plank)
for off in (-0.3, 0.3):
    box(off, 0, S + 0.015, 0.09, S, 0.03, batten)
bpy.ops.object.select_all(action="DESELECT")
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
c = bpy.context.object
c.name = "WoodCrate"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.quads_convert_to_tris()
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True, export_yup=True)
