"""Low-poly building and street props, CC0, for `rules/models/categories.tsv`: utility pole, ceiling lights, pipes and military crates.

blender -b --factory-startup --python building_props.py -- outdir [id ...]
Writes dm_<id>.glb into outdir (all when no id is given). Z up in Blender (glTF Y up), the long axis along X, origin on the floor, centred. Plain colour materials (lights emissive), real-world metres, under 900 triangles each; the picker rescales.
"""
import math
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
outdir = args[0]
only = set(args[1:])
M = {}


def mat(name, rgb, rough=0.7, metal=0.0, glow=0.0):
    if name not in M:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Base Color"].default_value = (*rgb, 1.0)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        if glow:
            b.inputs["Emission Color"].default_value = (*rgb, 1.0)
            b.inputs["Emission Strength"].default_value = glow
        M[name] = m
    return M[name]


def steel(): return mat("steel", (0.55, 0.57, 0.6), 0.45, 0.7)
def paintw(): return mat("whitepaint", (0.9, 0.9, 0.88), 0.5)
def dark(): return mat("dark", (0.1, 0.1, 0.11), 0.9)
def lamp(): return mat("lamp", (1.0, 0.95, 0.8), 0.3, 0.0, 3.0)


def add(parts, m, o):
    o.data.materials.append(m)
    parts.append(o)
    return o


def box(parts, x0, x1, y0, y1, z0, z1, m, rot=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    o = bpy.context.object
    o.scale = (x1 - x0, y1 - y0, z1 - z0)
    if rot:
        o.rotation_euler = rot
    return add(parts, m, o)


def cylz(parts, x, y, z0, z1, r, m, r2=None, n=16):
    bpy.ops.mesh.primitive_cone_add(vertices=n, radius1=r, radius2=r if r2 is None else r2, depth=z1 - z0, location=(x, y, (z0 + z1) / 2))
    return add(parts, m, bpy.context.object)


def cylx(parts, x0, x1, y, z, r, m, n=16):
    bpy.ops.mesh.primitive_cylinder_add(vertices=n, radius=r, depth=x1 - x0, location=((x0 + x1) / 2, y, z), rotation=(0, math.pi / 2, 0))
    return add(parts, m, bpy.context.object)


def cyly(parts, x, y0, y1, z, r, m, n=16):
    bpy.ops.mesh.primitive_cylinder_add(vertices=n, radius=r, depth=y1 - y0, location=(x, (y0 + y1) / 2, z), rotation=(math.pi / 2, 0, 0))
    return add(parts, m, bpy.context.object)


def finish(parts, name):
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
    bpy.ops.export_scene.gltf(filepath=f"{outdir}/dm_{name}.glb", export_format="GLB", export_apply=True, export_yup=True)


MODELS = {}


def model(f):
    MODELS[f.__name__] = f
    return f


@model
def utilitypole():
    """Wooden utility pole, 5 m: tapered trunk, two cross arms with insulators, a pole transformer."""
    p = []
    wood = mat("pole", (0.3, 0.21, 0.13), 0.95)
    cylz(p, 0, 0, 0, 5.0, 0.15, wood, 0.1, 12)
    for z, half in ((4.55, 0.85), (4.05, 0.55)):
        box(p, -0.06, 0.06, -half, half, z, z + 0.12, wood)
        for s in (-1, 1):
            box(p, -0.04, 0.04, s * 0.16, s * 0.5, z - 0.38, z - 0.3, wood, rot=(0, 0, 0))   # brace blocks
        for y in (-half + 0.08, 0.0, half - 0.08):
            cylz(p, 0, y, z + 0.12, z + 0.28, 0.035, mat("insul", (0.55, 0.62, 0.66), 0.3), 0.02, 8)
    cylz(p, 0.26, 0, 3.1, 3.75, 0.19, mat("xfmr", (0.45, 0.48, 0.46), 0.6, 0.4), None, 14)
    cylz(p, 0.26, 0, 3.75, 3.82, 0.1, mat("xfmr", (0.45, 0.48, 0.46), 0.6, 0.4), 0.05, 12)
    box(p, 0.12, 0.2, -0.05, 0.05, 3.2, 3.6, dark())                                           # mounting strap
    for z in (1.5, 1.9, 2.3, 2.7):                                                             # climbing pegs
        box(p, -0.03, 0.03, -0.3 if z % 0.8 else 0.1, 0.3, z, z + 0.03, steel())
    finish(p, "utilitypole")


@model
def lighttroffer():
    """Recessed fluorescent troffer, 1.22 x 0.61 x 0.11 m, diffuser face down at the origin plane."""
    p = []
    box(p, -0.61, 0.61, -0.305, 0.305, 0.03, 0.11, paintw())
    for x0, x1, y0, y1 in ((-0.61, 0.61, -0.305, -0.275), (-0.61, 0.61, 0.275, 0.305), (-0.61, -0.58, -0.305, 0.305), (0.58, 0.61, -0.305, 0.305)):
        box(p, x0, x1, y0, y1, 0.0, 0.035, paintw())
    box(p, -0.58, 0.58, -0.275, 0.275, 0.0, 0.02, lamp())
    for x in (-0.3, 0.0, 0.3):
        box(p, x - 0.008, x + 0.008, -0.275, 0.275, 0.0, 0.025, paintw())
    finish(p, "lighttroffer")


@model
def lightdisc():
    """Flush round ceiling light, 0.4 m across and 0.04 m deep."""
    p = []
    cylz(p, 0, 0, 0.012, 0.04, 0.2, paintw(), None, 24)
    cylz(p, 0, 0, 0.0, 0.016, 0.16, lamp(), None, 24)
    finish(p, "lightdisc")


@model
def lightpendant():
    """Hanging light, 0.2 m across and 0.6 m tall: a cable, a dome shade and a bulb at the origin plane."""
    p = []
    cylz(p, 0, 0, 0.3, 0.6, 0.006, dark(), None, 6)
    cylz(p, 0, 0, 0.2, 0.3, 0.015, mat("shade", (0.82, 0.8, 0.74), 0.4), 0.1, 16)
    cylz(p, 0, 0, 0.0, 0.2, 0.01, dark(), None, 6)
    cylz(p, 0, 0, 0.0, 0.1, 0.06, lamp(), 0.012, 12)
    finish(p, "lightpendant")


def flange(p, x, y, z, r, t=0.03):
    cylx(p, x - t / 2, x + t / 2, y, z, r, steel(), 16)


@model
def pipestraight():
    """Straight flanged pipe, 1.0 m long, 0.2 m across, axis along X, resting on the floor."""
    p = []
    r = 0.09
    cylx(p, -0.5, 0.5, 0, r + 0.001, r, mat("pipe", (0.45, 0.47, 0.5), 0.5, 0.7))
    for x in (-0.485, 0.485):
        flange(p, x, 0, r, r + 0.035, 0.03)
    flange(p, 0.0, 0, r, r + 0.02, 0.025)
    finish(p, "pipestraight")


@model
def pipecoupling():
    """Flange ring on a short stub, 0.225 m across and 0.034 m thick, axis along X."""
    p = []
    cylx(p, -0.017, 0.017, 0, 0.1125, 0.1125, steel(), 20)
    cylx(p, -0.017, 0.017, 0, 0.1125, 0.07, mat("pipe", (0.45, 0.47, 0.5), 0.5, 0.7), 16)
    for i in range(8):
        a = i * math.pi / 4
        cylx(p, 0.012, 0.024, 0.0 + 0.092 * math.cos(a), 0.1125 + 0.092 * math.sin(a), 0.01, dark(), 6)
    finish(p, "pipecoupling")


@model
def pipeelbow():
    """Mitred 90 degree pipe elbow, legs of 0.5 m, 0.16 m across, on the floor; one leg along X, the other along Y."""
    p = []
    r = 0.08
    pm = mat("pipe", (0.45, 0.47, 0.5), 0.5, 0.7)
    cylx(p, -0.1, 0.5, 0.0, r + 0.001, r, pm)
    cyly(p, 0.0, 0.0, 0.5, r + 0.001, r, pm)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=r * 1.04, location=(0, 0, r + 0.001))
    add(p, pm, bpy.context.object)
    flange(p, 0.5, 0, r + 0.001, r + 0.03)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=r + 0.03, depth=0.03, location=(0, 0.5, r + 0.001), rotation=(math.pi / 2, 0, 0))
    add(p, steel(), bpy.context.object)
    finish(p, "pipeelbow")


@model
def pipecluster():
    """Bundle of three pipes on floor clamps, 2.4 x 0.95 x 0.72 m, axis along X."""
    p = []
    pm = mat("pipe", (0.45, 0.47, 0.5), 0.5, 0.7)
    for y, z, r in ((-0.27, 0.2, 0.2), (0.27, 0.2, 0.2), (0.0, 0.57, 0.15)):
        cylx(p, -1.2, 1.2, y, z, r, pm)
        for x in (-1.19, 1.19):
            flange(p, x, y, z, r + 0.03, 0.03)
    for x in (-0.8, 0.0, 0.8):
        box(p, x - 0.04, x + 0.04, -0.47, 0.47, 0.0, 0.04, steel())
        box(p, x - 0.025, x + 0.025, -0.47, -0.43, 0.0, 0.2, steel())
        box(p, x - 0.025, x + 0.025, 0.43, 0.47, 0.0, 0.2, steel())
        box(p, x - 0.025, x + 0.025, -0.4, 0.4, 0.42, 0.45, steel())
    finish(p, "pipecluster")


def crate(name, w, h, olive):
    p = []
    wood = mat(f"{name}wood", olive, 0.9)
    batten = mat(f"{name}batten", tuple(c * 0.7 for c in olive), 0.9)
    lid = mat(f"{name}lid", tuple(c * 1.15 for c in olive), 0.9)
    stencil = mat("stencil", (0.85, 0.82, 0.6), 0.9)
    hw = w / 2
    t = w * 0.06
    box(p, -hw, hw, -hw, hw, 0.0, h, wood)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(p, min(sx * hw, sx * (hw - t)), max(sx * hw, sx * (hw - t)), min(sy * hw, sy * (hw - t)), max(sy * hw, sy * (hw - t)), 0.0, h + 0.005, batten)
    for z in (0.0, h - t):
        box(p, -hw - 0.005, hw + 0.005, -hw - 0.005, hw + 0.005, z, z + t, batten)
    box(p, -hw - 0.003, hw + 0.003, -hw - 0.003, hw + 0.003, h * 0.45, h * 0.45 + h * 0.06, stencil)
    box(p, -hw - 0.01, hw + 0.01, -hw - 0.01, hw + 0.01, h, h + 0.015, lid)
    for sy in (-1, 1):
        box(p, -hw * 0.45, hw * 0.45, sy * (hw + 0.012) - 0.01, sy * (hw + 0.012) + 0.01, h * 0.72, h * 0.72 + 0.035, dark())
    return p


@model
def milcrate():
    """Military supply crate, 0.92 m cube: olive planks, corner battens, a stencil band, rope-hole handles."""
    finish(crate("milcrate", 0.92, 0.92, (0.3, 0.34, 0.2)), "milcrate")


@model
def milcratetall():
    """Large military crate, 1.84 x 2.45 x 1.84 m, the small one's build stretched in height."""
    finish(crate("milcratetall", 1.84, 2.45, (0.3, 0.34, 0.2)), "milcratetall")


for name, f in MODELS.items():
    if only and name not in only:
        continue
    bpy.ops.wm.read_factory_settings(use_empty=True)
    M.clear()
    f()
