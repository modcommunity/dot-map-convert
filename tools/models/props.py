"""Prop stand-ins, CC0, for `rules/models/categories.tsv`: boarded window wall, watermelon, orange, burger patty, cliff rocks,
leaning sheetrock, stacked food trays, plastic bottle, hard drive, security light, tall pylon, harpoon, cannon carriage and barrel.

blender -b --factory-startup --python props.py -- outdir
Writes dm_boardedwindow, dm_watermelon, dm_orange, dm_patty, dm_rockcliff1, dm_rockcliff2, dm_sheetrock, dm_foodstack,
dm_plasticbottle, dm_harddrive, dm_securitylight, dm_pylontall, dm_harpoon, dm_cannoncarriage and dm_cannonbarrel into outdir.
Blender Z is up, X the length, Y the depth; origin on the floor, centred. Plain colour materials.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import modelkit as mk  # noqa: E402

outdir = sys.argv[sys.argv.index("--") + 1]
PI = math.pi


def out(name):
    return f"{outdir}/{name}.glb"


def sphere(parts, c, s, m, seg=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=max(6, seg // 2), radius=0.5, location=c)
    o = bpy.context.object
    o.scale = s
    o.data.materials.append(m)
    parts.append(o)
    return o


def cone(parts, c, r1, r2, h, m, rot, verts=12):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=h, location=c, rotation=rot)
    o = bpy.context.object
    o.data.materials.append(m)
    parts.append(o)
    return o


# Boarded window in a wall: 1.1 wide x 1.3 high x 0.14 deep. Frame, a sill, and planks nailed across the opening.
p = mk.fresh()
wood = mk.mat("bw_wood", (0.45, 0.33, 0.2), 0.85)
old = mk.mat("bw_old", (0.36, 0.27, 0.17), 0.9)
dark = mk.mat("bw_dark", (0.08, 0.1, 0.12), 0.3)
W, H, D = 1.1, 1.3, 0.14
for sx in (-1, 1):
    mk.box(p, (sx * (W / 2 - 0.05), 0, H / 2), (0.1, D, H), wood)
mk.box(p, (0, 0, 0.05), (W, D, 0.1), wood)
mk.box(p, (0, 0, H - 0.05), (W, D, 0.1), wood)
mk.box(p, (0, 0.01, 0.62), (W - 0.2, 0.02, 0.96), dark)
for i, (z, tilt) in enumerate(((0.28, 0.04), (0.52, -0.03), (0.76, 0.05), (1.0, -0.02))):
    mk.box(p, (0, -D / 2 - 0.015, z), (W + 0.08, 0.03, 0.15), old if i % 2 else wood, rot=(0, tilt, 0))
mk.box(p, (-0.18, -D / 2 - 0.045, 0.64), (0.14, 0.03, 0.9), old, rot=(0, 0.04, 0))
mk.finish(p, "dm_boardedwindow", out("dm_boardedwindow"))

# Watermelon: 0.28 x 0.28 x 0.28 oval, dark green with lighter stripes, stalk nub.
p = mk.fresh()
g1 = mk.mat("wm_g1", (0.12, 0.38, 0.14), 0.5)
g2 = mk.mat("wm_g2", (0.3, 0.55, 0.22), 0.5)
sphere(p, (0, 0, 0.14), (0.28, 0.28, 0.28), g1)
sphere(p, (0, 0, 0.14), (0.285, 0.2, 0.275), g2)
mk.cyl(p, (0, 0, 0.285), 0.012, 0.03, mk.mat("wm_stalk", (0.3, 0.25, 0.1), 0.8), verts=6)
mk.finish(p, "dm_watermelon", out("dm_watermelon"))

# Orange: 0.116 ball.
p = mk.fresh()
sphere(p, (0, 0, 0.058), (0.116, 0.116, 0.116), mk.mat("or_skin", (0.93, 0.45, 0.05), 0.6), seg=14)
mk.cyl(p, (0, 0, 0.116), 0.01, 0.01, mk.mat("or_leaf", (0.2, 0.5, 0.15), 0.7), verts=6)
mk.finish(p, "dm_orange", out("dm_orange"))

# Burger patty: 0.19 wide, 0.07 high; two bun halves, a patty, lettuce and cheese between.
p = mk.fresh()
bun = mk.mat("pt_bun", (0.82, 0.55, 0.25), 0.7)
meat = mk.mat("pt_meat", (0.28, 0.14, 0.08), 0.8)
leaf = mk.mat("pt_leaf", (0.3, 0.65, 0.2), 0.7)
cheese = mk.mat("pt_cheese", (0.95, 0.75, 0.15), 0.6)
sphere(p, (0, 0, 0.0), (0.19, 0.19, 0.04), bun, seg=14)
mk.cyl(p, (0, 0, 0.022), 0.09, 0.018, meat, verts=14)
mk.cyl(p, (0, 0, 0.034), 0.1, 0.008, leaf, verts=14)
mk.box(p, (0, 0, 0.042), (0.17, 0.17, 0.006), cheese, rot=(0, 0, PI / 4))
sphere(p, (0, 0, 0.058), (0.19, 0.19, 0.08), bun, seg=14)
mk.finish(p, "dm_patty", out("dm_patty"))


def cliff(name, seed, size):
    """Broken cliff face: a stack of displaced boulders, widest at the bottom, size = (x, y, z)."""
    rng = random.Random(seed)
    parts = mk.fresh()
    mats = [mk.mat("cl_a", (0.42, 0.37, 0.31), 0.95), mk.mat("cl_b", (0.34, 0.31, 0.27), 0.95)]
    n = 5
    for i in range(n):
        k = 1.0 - 0.5 * i / n
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.5, location=(
            (rng.random() - 0.5) * size[0] * 0.25, (rng.random() - 0.5) * size[1] * 0.2, size[2] * (i + 0.5) / n * 0.8))
        o = bpy.context.object
        for v in o.data.vertices:
            v.co.x *= 0.75 + 0.5 * rng.random()
            v.co.y *= 0.75 + 0.5 * rng.random()
            v.co.z *= 0.75 + 0.4 * rng.random()
        o.scale = (size[0] * k * 0.85, size[1] * (0.7 + 0.3 * rng.random()), size[2] / n * 2.0)
        o.rotation_euler = (0, 0, (rng.random() - 0.5) * 0.5)
        o.data.materials.append(mats[i % 2])
        parts.append(o)
    bpy.context.view_layer.update()
    lo = min((o.matrix_world @ v.co).z for o in parts for v in o.data.vertices)
    for o in parts:
        o.location.z -= lo
    mk.finish(parts, name, out(name))


cliff("dm_rockcliff1", 5, (5.0, 3.0, 4.5))
cliff("dm_rockcliff2", 9, (3.2, 2.6, 3.4))

# Sheetrock leaning on a wall: two 2.44 x 1.22 boards, 0.013 thick, leaning 0.4 m out; length along X.
p = mk.fresh()
board = mk.mat("sr_board", (0.82, 0.8, 0.74), 0.9)
face = mk.mat("sr_paper", (0.7, 0.68, 0.62), 0.9)
lean = math.atan2(0.4, 1.2)
for i, dy in enumerate((0.0, 0.03)):
    mk.box(p, (0, dy + 0.2, 0.6), (2.44, 0.013, 1.25), board if i == 0 else face, rot=(lean, 0, 0))
mk.finish(p, "dm_sheetrock", out("dm_sheetrock"))

# Stacked food trays: 1.9 wide x 1.19 high x 1.0 deep, crates of styrofoam trays on a pallet.
p = mk.fresh()
pal = mk.mat("fs_pal", (0.55, 0.42, 0.26), 0.9)
white = mk.mat("fs_tray", (0.95, 0.94, 0.9), 0.7)
crate = mk.mat("fs_crate", (0.2, 0.4, 0.62), 0.6)
mk.box(p, (0, 0, 0.07), (1.9, 1.0, 0.14), pal)
for sx in (-1, 1):
    for lvl in range(3):
        z = 0.14 + 0.17 + lvl * 0.34
        mk.box(p, (sx * 0.47, 0, z), (0.9, 0.9, 0.3), crate)
        mk.box(p, (sx * 0.47, 0, z + 0.16), (0.84, 0.84, 0.02), white)
mk.box(p, (0, 0, 1.17), (1.9, 1.0, 0.04), pal)
mk.finish(p, "dm_foodstack", out("dm_foodstack"))

# Plastic bottle: 2 litre, 0.135 across, 0.37 high.
p = mk.fresh()
pet = mk.mat("pb_pet", (0.75, 0.88, 0.92), 0.2)
label = mk.mat("pb_label", (0.8, 0.15, 0.12), 0.6)
cap = mk.mat("pb_cap", (0.1, 0.4, 0.8), 0.5)
mk.cyl(p, (0, 0, 0.14), 0.0675, 0.28, pet, verts=14)
mk.cyl(p, (0, 0, 0.19), 0.07, 0.12, label, verts=14)
mk.cyl(p, (0, 0, 0.315), 0.03, 0.07, pet, verts=10)
mk.cyl(p, (0, 0, 0.36), 0.032, 0.03, cap, verts=10)
mk.finish(p, "dm_plasticbottle", out("dm_plasticbottle"))

# Hard drive: a 3.5 inch drive, 0.147 x 0.102 x 0.026.
p = mk.fresh()
steel = mk.mat("hd_steel", (0.62, 0.64, 0.66), 0.35, 0.8)
black = mk.mat("hd_black", (0.08, 0.08, 0.09), 0.5)
mk.box(p, (0, 0, 0.015), (0.147, 0.102, 0.026), steel)
mk.box(p, (0, 0, 0.003), (0.147, 0.102, 0.006), black)
mk.box(p, (-0.07, 0, 0.016), (0.006, 0.09, 0.016), black)
mk.box(p, (0.04, -0.03, 0.029), (0.05, 0.03, 0.002), mk.mat("hd_label", (0.9, 0.9, 0.85), 0.8))
mk.finish(p, "dm_harddrive", out("dm_harddrive"))

# Security light: a floodlight on a wall bracket, 0.34 wide x 0.29 high x 0.34 out.
p = mk.fresh()
grey = mk.mat("sl_body", (0.55, 0.56, 0.56), 0.5, 0.4)
lens = mk.mat("sl_lens", (0.95, 0.95, 0.8), 0.2)
mk.box(p, (0, 0.15, 0.14), (0.1, 0.04, 0.2), grey)
mk.box(p, (0, 0.05, 0.14), (0.04, 0.2, 0.04), grey)
mk.box(p, (0, -0.07, 0.14), (0.34, 0.2, 0.24), grey, rot=(0.2, 0, 0))
mk.box(p, (0, -0.17, 0.12), (0.3, 0.02, 0.2), lens, rot=(0.2, 0, 0))
mk.box(p, (0, -0.07, 0.275), (0.36, 0.22, 0.02), grey)
mk.finish(p, "dm_securitylight", out("dm_securitylight"))

# Tall pylon: a 1.18 m slim post, 0.19 base, hazard stripes.
p = mk.fresh()
red = mk.mat("py_red", (0.8, 0.12, 0.08), 0.5)
white = mk.mat("py_white", (0.92, 0.92, 0.9), 0.5)
mk.box(p, (0, 0, 0.02), (0.194, 0.194, 0.04), mk.mat("py_base", (0.15, 0.15, 0.15), 0.8))
for i in range(6):
    mk.cyl(p, (0, 0, 0.13 + i * 0.18), 0.045 - i * 0.003, 0.18, red if i % 2 == 0 else white, verts=12)
mk.finish(p, "dm_pylontall", out("dm_pylontall"))

# Harpoon: a 1.6 m shaft along X, an iron head with two barbs.
p = mk.fresh()
wood = mk.mat("hp_wood", (0.45, 0.33, 0.2), 0.8)
iron = mk.mat("hp_iron", (0.3, 0.3, 0.32), 0.4, 0.8)
rope = mk.mat("hp_rope", (0.7, 0.6, 0.4), 0.9)
mk.cyl(p, (0, 0, 0.03), 0.022, 1.4, wood, verts=8, rot=(0, PI / 2, 0))
mk.cyl(p, (0.62, 0, 0.03), 0.028, 0.08, rope, verts=8, rot=(0, PI / 2, 0))
cone(p, (0.73, 0, 0.03), 0.03, 0.0, 0.26, iron, (0, PI / 2, 0), verts=6)
for s in (-1, 1):
    mk.box(p, (0.6, 0, 0.03 + s * 0.03), (0.1, 0.012, 0.01), iron, rot=(0, s * 0.5, 0))
mk.finish(p, "dm_harpoon", out("dm_harpoon"))

# Cannon carriage: wooden truck 1.5 long (X) x 0.85 wide x 0.85 high, two axles, trunnion cradle.
p = mk.fresh()
oak = mk.mat("cn_oak", (0.36, 0.25, 0.15), 0.85)
irn = mk.mat("cn_iron", (0.15, 0.15, 0.16), 0.5, 0.6)
for s in (-1, 1):
    mk.box(p, (0.0, s * 0.3, 0.38), (1.5, 0.12, 0.3), oak, rot=(0, -0.05, 0))
    mk.cyl(p, (-0.45, s * 0.43, 0.3), 0.3, 0.1, oak, verts=14, rot=(PI / 2, 0, 0))
    mk.cyl(p, (0.5, s * 0.43, 0.22), 0.22, 0.1, oak, verts=14, rot=(PI / 2, 0, 0))
mk.cyl(p, (-0.45, 0, 0.3), 0.04, 0.85, irn, verts=8, rot=(PI / 2, 0, 0))
mk.cyl(p, (0.5, 0, 0.22), 0.04, 0.85, irn, verts=8, rot=(PI / 2, 0, 0))
mk.box(p, (0.0, 0, 0.58), (0.4, 0.5, 0.1), oak)
mk.finish(p, "dm_cannoncarriage", out("dm_cannoncarriage"))

# Cannon barrel: 2.4 m long (X), elevated 0.4 rad, 0.3 across at the breech tapering to 0.2, cascabel knob, two reinforcing rings.
p = mk.fresh()
brz = mk.mat("cb_iron", (0.18, 0.18, 0.19), 0.45, 0.7)
T = 0.4  # elevation, as the source gun sits on its carriage
c, s_ = math.cos(T), math.sin(T)
cone(p, (0.0, 0, 0.15 + 0.0), 0.15, 0.1, 2.4, brz, (0, -PI / 2 + T, 0), verts=14)
sphere(p, (-1.3 * c, 0, 0.15 + 1.3 * s_), (0.14, 0.14, 0.14), brz, seg=10)
for x, r in ((-0.7, 0.17), (0.5, 0.14)):
    mk.cyl(p, (x * c, 0, 0.15 - x * s_), r, 0.08, brz, verts=14, rot=(0, PI / 2 - T, 0))
mk.finish(p, "dm_cannonbarrel", out("dm_cannonbarrel"))
