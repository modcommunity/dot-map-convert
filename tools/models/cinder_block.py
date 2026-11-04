"""A hollow concrete block (two cores, bevelled edges, rough grey), CC0, for `rules/models/categories.tsv`.

blender -b --factory-startup --python cinder_block.py -- out.glb
39 x 19 x 19 cm, origin on the floor, centred. One plain material, under 300 triangles.
"""
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
m = bpy.data.materials.new("concrete")
m.use_nodes = True
b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
b.inputs["Base Color"].default_value = (0.52, 0.51, 0.49, 1.0)
b.inputs["Roughness"].default_value = 0.95

L, W, H = 0.39, 0.19, 0.19


def cube(cx, cy, cz, sx, sy, sz):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    o = bpy.context.object
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    return o


blk = cube(0, 0, H / 2, L, W, H)
bev = blk.modifiers.new("bev", "BEVEL")
bev.width = 0.004
bev.segments = 1
bpy.ops.object.modifier_apply(modifier="bev")
wall, web = 0.03, 0.03
core_l = (L - 2 * wall - web) / 2
for sx in (-1, 1):
    c = cube(sx * (web / 2 + core_l / 2), 0, H / 2 + 0.02, core_l, W - 2 * wall, H)
    mod = blk.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = c
    mod.solver = "EXACT"
    bpy.context.view_layer.objects.active = blk
    bpy.ops.object.modifier_apply(modifier="cut")
    bpy.data.objects.remove(c)
blk.data.materials.append(m)
blk.name = "CinderBlock"
bpy.context.view_layer.objects.active = blk
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.quads_convert_to_tris()
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True, export_yup=True)
