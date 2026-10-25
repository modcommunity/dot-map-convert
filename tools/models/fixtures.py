"""Hand-modelled stand-ins for fixtures no free library carries (water cooler, towel rack, shower tray, poster board,
address sign, tiered fountain, plush doll). Blender, headless:

    blender -b --factory-startup --python tools/models/fixtures.py -- <library models dir> [id ...]

Writes `<dir>/own/<id>/<id>.glb` and `model.json` (CC0, TMC); re-run `~/art-library/tools/index_models.py` after. Z up in
Blender, front toward -Y (glTF +Z), origin at the bottom centre. Sizes are the originals' real ones in metres.
"""
import json
import math
import os
import sys

import bpy
import bmesh

AUTHOR = "TMC (modelled for dot-map)"
URL = "https://github.com/modcommunity/dot-map"


def mat(name, rgb, rough=0.6, metal=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*[c / 255.0 for c in rgb], 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND"
    return m


def finish(obj, m, smooth=True):
    obj.data.materials.append(m)
    if smooth:
        for p in obj.data.polygons:
            p.use_smooth = True
    return obj


def box(name, size, at, m, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=at)
    o = bpy.context.object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        bpy.ops.object.modifier_add(type="BEVEL")
        o.modifiers["Bevel"].width = bevel
        o.modifiers["Bevel"].segments = 2
        bpy.ops.object.modifier_apply(modifier="Bevel")
    return finish(o, m, smooth=bool(bevel))


def cyl(name, r, h, at, m, r2=None, verts=32):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r2 is None else r2, depth=h, location=at)
    o = bpy.context.object
    o.name = name
    return finish(o, m)


def sphere(name, r, at, m, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=r, location=at)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    return finish(o, m)


def build_water_cooler():
    body = mat("cooler_body", (232, 236, 240), 0.35)
    dark = mat("cooler_dark", (60, 66, 74), 0.5)
    water = mat("cooler_water", (150, 200, 235), 0.1)
    box("cabinet", (0.30, 0.30, 0.92), (0, 0, 0.46), body, 0.015)
    box("tap_panel", (0.24, 0.02, 0.16), (0, -0.155, 0.80), dark, 0.005)
    box("drip_tray", (0.20, 0.06, 0.02), (0, -0.17, 0.70), dark, 0.004)
    for x in (-0.05, 0.05):
        cyl("tap", 0.012, 0.04, (x, -0.17, 0.78), mat("tap%s" % x, (200, 60, 50) if x < 0 else (60, 90, 200)))
        bpy.context.object.rotation_euler = (math.pi / 2, 0, 0)
    cyl("jug_neck", 0.06, 0.06, (0, 0, 0.95), body, r2=0.10)
    cyl("jug", 0.14, 0.26, (0, 0, 1.11), water)
    cyl("jug_top", 0.14, 0.02, (0, 0, 1.25), water, r2=0.05)
    return (0.30, 0.30, 1.26)


def build_towel_rack():
    steel = mat("steel", (200, 202, 205), 0.25, 0.9)
    towel_a = mat("towel_a", (235, 235, 230), 0.9)
    towel_b = mat("towel_b", (120, 170, 200), 0.9)
    box("plate", (0.60, 0.012, 0.62), (0, 0.044, 0.31), steel)
    for i, z in enumerate((0.20, 0.42)):
        c = cyl("bar%d" % i, 0.008, 0.58, (0, -0.002, z), steel)
        c.rotation_euler = (0, math.pi / 2, 0)
        for x in (-0.28, 0.28):
            a = cyl("arm", 0.007, 0.05, (x, 0.02, z), steel)
            a.rotation_euler = (math.pi / 2, 0, 0)
    box("towel_a", (0.40, 0.03, 0.30), (-0.05, -0.012, 0.31), towel_a, 0.01)
    box("towel_b", (0.34, 0.03, 0.26), (0.08, -0.03, 0.55), towel_b, 0.01)
    return (0.60, 0.09, 0.62)


def build_shower_tray():
    ceramic = mat("ceramic", (225, 228, 222), 0.3)
    metal = mat("drain", (150, 152, 155), 0.3, 0.9)
    box("tray", (0.56, 0.99, 0.08), (0, 0, 0.04), ceramic, 0.012)
    box("basin", (0.46, 0.89, 0.02), (0, 0, 0.075), mat("basin", (214, 218, 212), 0.3))
    cyl("drain", 0.045, 0.012, (0, 0.2, 0.082), metal)
    return (0.56, 0.99, 0.085)


def build_poster_board():
    frame = mat("frame", (60, 50, 44), 0.5)
    face = mat("face", (232, 220, 190), 0.8)
    red = mat("red", (190, 50, 40), 0.7)
    ink = mat("ink", (40, 40, 40), 0.9)
    box("frame", (0.76, 0.04, 1.22), (0, 0, 0.61), frame, 0.008)
    box("face", (0.68, 0.01, 1.14), (0, -0.022, 0.61), face)
    box("title", (0.56, 0.005, 0.18), (0, -0.029, 1.03), red)
    for i in range(7):
        w = 0.5 if i % 3 else 0.38
        box("line%d" % i, (w, 0.005, 0.03), (-0.03 * (i % 2), -0.029, 0.80 - i * 0.09), ink)
    box("photo", (0.5, 0.005, 0.22), (0, -0.029, 0.20), mat("photo", (110, 150, 110), 0.8))
    return (0.76, 0.045, 1.22)


def build_address_sign():
    plate = mat("plate", (236, 234, 224), 0.5)
    rim = mat("rim", (60, 62, 66), 0.5)
    ink = mat("ink", (30, 30, 34), 0.5)
    box("rim", (3.61, 0.14, 0.82), (0, 0, 0.41), rim, 0.02)
    box("plate", (3.49, 0.04, 0.70), (0, -0.07, 0.41), plate)
    x = -1.5
    for w in (0.3, 0.18, 0.3, 0.3, 0.18, 0.3, 0.3, 0.18, 0.3, 0.3):
        box("glyph", (w, 0.03, 0.46), (x + w / 2, -0.095, 0.41), ink)
        x += w + 0.1
    return (3.61, 0.14, 0.82)


def build_fountain():
    stone = mat("stone", (186, 184, 174), 0.8)
    water = mat("water", (110, 170, 205), 0.05)
    cyl("basin", 1.05, 0.45, (0, 0, 0.225), stone)
    cyl("water", 0.95, 0.02, (0, 0, 0.42), water)
    cyl("pedestal", 0.22, 0.60, (0, 0, 0.65), stone, r2=0.14)
    cyl("bowl", 0.55, 0.14, (0, 0, 0.98), stone, r2=0.30)
    cyl("bowl_water", 0.45, 0.02, (0, 0, 1.06), water)
    cyl("stem", 0.07, 0.20, (0, 0, 1.17), stone)
    cyl("top", 0.20, 0.08, (0, 0, 1.30), stone, r2=0.10)
    sphere("finial", 0.07, (0, 0, 1.38), stone)
    return (2.10, 2.10, 1.45)


def build_doll():
    skin = mat("skin", (240, 205, 175), 0.9)
    dress = mat("dress", (200, 70, 110), 0.9)
    hair = mat("hair", (110, 70, 40), 0.9)
    dark = mat("dark", (30, 30, 30), 0.5)
    sphere("legs", 0.07, (0, 0, 0.09), dress, (1.0, 0.8, 1.2))
    sphere("body", 0.11, (0, 0, 0.27), dress, (1.0, 0.75, 1.3))
    sphere("head", 0.12, (0, 0, 0.50), skin)
    sphere("hair", 0.125, (0, 0.02, 0.53), hair, (1.0, 1.0, 0.85))
    for x in (-1, 1):
        sphere("arm", 0.045, (x * 0.15, 0, 0.28), skin, (0.8, 0.8, 1.6))
        sphere("eye", 0.015, (x * 0.04, -0.11, 0.51), dark)
    return (0.30, 0.26, 0.64)


def build_drinking_fountain():
    steel = mat("steel", (205, 207, 210), 0.25, 0.9)
    dark = mat("dark", (50, 52, 56), 0.5)
    box("back", (0.30, 0.04, 0.34), (0, 0.13, 0.45), steel, 0.008)
    box("basin", (0.35, 0.22, 0.10), (0, 0.03, 0.40), steel, 0.03)
    box("well", (0.24, 0.14, 0.02), (0, 0.02, 0.455), dark)
    c = cyl("spout", 0.012, 0.10, (0, 0.06, 0.52), steel)
    c.rotation_euler = (math.pi / 2, 0, 0)
    cyl("button", 0.025, 0.02, (0.11, 0.08, 0.46), dark)
    box("pipe", (0.06, 0.06, 0.34), (0, 0.10, 0.17), steel)
    return (0.35, 0.30, 0.62)


def build_urinal():
    china = mat("china", (240, 240, 236), 0.25)
    steel = mat("steel", (200, 202, 205), 0.3, 0.8)
    box("back", (0.34, 0.04, 0.80), (0, 0.13, 0.50), china, 0.01)
    sphere("bowl", 0.5, (0, 0.04, 0.46), china, scale=(0.30, 0.30, 0.56))
    box("cistern", (0.22, 0.06, 0.06), (0, 0.09, 0.76), steel, 0.01)
    cyl("flush", 0.015, 0.06, (0, 0.10, 0.82), steel)
    return (0.34, 0.31, 0.90)


BUILDERS = {
    "fxurinal": build_urinal,
    "fxdrinkfountain": build_drinking_fountain,
    "fxcooler": build_water_cooler, "fxtowelrack": build_towel_rack, "fxshowertray": build_shower_tray,
    "fxadpanel": build_poster_board, "fxplaque": build_address_sign, "fxfountain": build_fountain,
    "fxplushdoll": build_doll,
}


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    root, only = args[0], args[1:]
    for ident, fn in BUILDERS.items():
        if only and ident not in only:
            continue
        bpy.ops.wm.read_factory_settings(use_empty=True)
        dims = fn()
        bpy.ops.object.select_all(action="SELECT")
        folder = os.path.join(root, "own", ident)
        os.makedirs(folder, exist_ok=True)
        rel = "own/%s/%s.glb" % (ident, ident)
        bpy.ops.export_scene.gltf(filepath=os.path.join(root, rel), export_format="GLB", export_apply=True,
                                  export_yup=True, export_materials="EXPORT")
        with open(os.path.join(folder, "model.json"), "w") as f:
            json.dump({"id": ident, "source": "Modelled for dot-map", "url": URL, "author": AUTHOR, "licence": "CC0-1.0",
                       "tags": "fixture,%s" % ident[2:], "files": [rel]}, f)
        print("wrote", rel, dims)


main()
