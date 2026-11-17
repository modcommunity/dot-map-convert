"""Last placeholders of the FC, surf, hide-and-seek and wipeout worlds, CC0, for `rules/models/categories.tsv`: overhead
power lines, a wall cable run, a fan rotor and its ceiling mount, a pulley block, a tripod floor sentry, a wall plug holder, a broken
building wall, a roadside billboard and a kitchen cooker hood.

blender -b --factory-startup --python fc_final.py -- outdir
Writes one dm_<name>.glb per model into outdir (the names are the mk.finish calls below). Blender Z is up, X the length,
Y the depth; origin on the floor, centred. Each size is the original's measured box (rules/models/model_dims.tsv); the
picker turns a model a quarter at a time, so the longest flat side is laid along X. Plain colour materials.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modelkit as mk  # noqa: E402

outdir = sys.argv[sys.argv.index("--") + 1]
PI = math.pi


def out(name):
    return f"{outdir}/{name}.glb"


def sag(parts, a, b, drop, thick, m, steps=12):
    """A hanging cable from a to b, sagging `drop` at the middle (a parabola, close enough to a catenary)."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        pts.append(tuple(a[k] + (b[k] - a[k]) * t for k in range(3)))
        pts[-1] = (pts[-1][0], pts[-1][1], pts[-1][2] - drop * 4 * t * (1 - t))
    for p0, p1 in zip(pts, pts[1:]):
        mk.beam(parts, p0, p1, thick, m)


# Overhead power lines (de_nuke/powerwires): six conductors 33.5 long hanging from a cross-arm 10.9 up at one end to a
# wall bracket 1 up at the other, 6.6 across, with insulator strings at both arms.
p = mk.fresh()
wire = mk.mat("pl_wire", (0.08, 0.08, 0.09), 0.5, 0.6)
porc = mk.mat("pl_insulator", (0.55, 0.6, 0.55), 0.3)
steel = mk.mat("pl_steel", (0.42, 0.43, 0.42), 0.5, 0.8)
L = 33.4
for x, top in ((-L / 2, 10.9), (L / 2, 1.0)):
    mk.box(p, (x, 0, top + 0.1), (0.18, 6.5, 0.16), steel)
    for y in (-3.0, -1.8, -0.6, 0.6, 1.8, 3.0):
        mk.cyl(p, (x, y, top - 0.15), 0.06, 0.4, porc, verts=10)
for y in (-3.0, -1.8, -0.6, 0.6, 1.8, 3.0):
    sag(p, (-L / 2, y, 10.55), (L / 2, y, 0.65), 2.6 + 0.1 * abs(y), 0.035, wire, steps=16)
mk.finish(p, "dm_powerlines", out("dm_powerlines"))

# Wall cable run (de_prodigy/prodcables128, props_silo/prodcables128): four cables 2.44 long laid along a wall, 0.21 high
# and 0.03 off it, held by flat clips every 0.6.
p = mk.fresh()
black = mk.mat("cr_black", (0.04, 0.04, 0.045), 0.6)
grey = mk.mat("cr_grey", (0.3, 0.3, 0.3), 0.6)
clip = mk.mat("cr_clip", (0.6, 0.6, 0.58), 0.4, 0.8)
for z, r, m in ((0.03, 0.011, black), (0.07, 0.013, grey), (0.12, 0.011, black), (0.175, 0.016, black)):
    mk.cyl(p, (0, 0, z), r, 2.44, m, verts=10, rot=(0, PI / 2, 0))
for i in range(5):
    mk.box(p, (-1.2 + 0.6 * i, 0.004, 0.105), (0.03, 0.026, 0.21), clip)
mk.finish(p, "dm_cablerun", out("dm_cablerun"))

# Fan rotor (de_inferno/ceiling_fan_blade, de_prodigy/fanoff): a hub 0.16 across with four pitched blades, 1.45 tip to tip,
# 0.06 deep; the blade arms are steel, the blades wood.
p = mk.fresh()
wood = mk.mat("fr_wood", (0.42, 0.27, 0.15), 0.6)
metal = mk.mat("fr_metal", (0.55, 0.5, 0.42), 0.35, 0.8)
mk.cyl(p, (0, 0, 0.03), 0.085, 0.06, metal, verts=20)
for i in range(4):
    a = i * PI / 2
    ca, sa = math.cos(a), math.sin(a)
    mk.box(p, (0.13 * ca, 0.13 * sa, 0.045), (0.12, 0.03, 0.008), metal, rot=(0, 0, a))
    mk.box(p, (0.44 * ca, 0.44 * sa, 0.04), (0.56, 0.14, 0.01), wood, rot=(0.12, 0, a))
mk.finish(p, "dm_fanrotor", out("dm_fanrotor"))

# Ceiling fan mount (de_inferno/ceiling_fan): a canopy on the ceiling, a downrod and the motor housing the rotor hangs from,
# 0.39 across and 0.48 high.
p = mk.fresh()
brass = mk.mat("fm_brass", (0.6, 0.48, 0.28), 0.35, 0.85)
dark = mk.mat("fm_dark", (0.12, 0.1, 0.08), 0.5, 0.6)
mk.cyl(p, (0, 0, 0.45), 0.08, 0.06, brass, verts=20)
mk.cyl(p, (0, 0, 0.32), 0.015, 0.22, dark, verts=10)
mk.cyl(p, (0, 0, 0.2), 0.05, 0.04, brass, verts=16)
mk.cyl(p, (0, 0, 0.11), 0.195, 0.14, brass, verts=28)
mk.cyl(p, (0, 0, 0.11), 0.2, 0.03, dark, verts=28)
mk.cyl(p, (0, 0, 0.025), 0.07, 0.05, dark, verts=16)
mk.finish(p, "dm_fanmount", out("dm_fanmount"))

# Pulley block (props_c17/pulleywheels_small01): two grooved wheels in a steel cheek frame under a mounting plate, 0.34 long,
# 0.27 deep, 0.35 high.
p = mk.fresh()
frame = mk.mat("pw_frame", (0.3, 0.32, 0.33), 0.5, 0.8)
wheel = mk.mat("pw_wheel", (0.5, 0.48, 0.45), 0.4, 0.9)
mk.box(p, (0, 0, 0.335), (0.34, 0.2, 0.03), frame)
for y in (-0.06, 0.06):
    mk.box(p, (0, y, 0.2), (0.32, 0.012, 0.24), frame)
for x in (-0.085, 0.085):
    mk.cyl(p, (x, 0, 0.17), 0.075, 0.09, wheel, verts=20, rot=(PI / 2, 0, 0))
    mk.cyl(p, (x, 0, 0.17), 0.062, 0.1, frame, verts=20, rot=(PI / 2, 0, 0))
    mk.cyl(p, (x, 0, 0.17), 0.012, 0.27, frame, verts=8, rot=(PI / 2, 0, 0))
mk.box(p, (0, 0, 0.05), (0.04, 0.12, 0.1), frame)
mk.finish(p, "dm_pulleywheels", out("dm_pulleywheels"))

# Floor sentry (combine_turrets/floor_turret): a gun body on a three-legged stand, 0.61 across and 1.22 high, with a
# sensor lens on the front and a short barrel.
p = mk.fresh()
shell = mk.mat("ft_shell", (0.32, 0.34, 0.36), 0.45, 0.6)
dark = mk.mat("ft_dark", (0.07, 0.07, 0.08), 0.5, 0.5)
lens = mk.mat("ft_lens", (0.7, 0.12, 0.08), 0.2)
for i in range(3):
    a = i * 2 * PI / 3 + PI / 2
    mk.beam(p, (0, 0, 0.62), (0.29 * math.cos(a), 0.29 * math.sin(a), 0.02), 0.035, dark)
    mk.box(p, (0.29 * math.cos(a), 0.29 * math.sin(a), 0.015), (0.08, 0.08, 0.03), dark)
mk.cyl(p, (0, 0, 0.66), 0.06, 0.1, dark, verts=12)
mk.box(p, (0, 0, 0.92), (0.34, 0.22, 0.48), shell)
mk.box(p, (0.0, 0, 1.18), (0.26, 0.18, 0.06), shell)
mk.cyl(p, (0.2, 0, 1.0), 0.03, 0.12, dark, verts=12, rot=(0, PI / 2, 0))
mk.cyl(p, (0.27, 0, 1.0), 0.018, 0.06, dark, verts=10, rot=(0, PI / 2, 0))
mk.cyl(p, (0.175, 0, 0.84), 0.04, 0.02, lens, verts=16, rot=(0, PI / 2, 0))
mk.finish(p, "dm_floorturret", out("dm_floorturret"))

# Wall plug holder (props_lab/tpplugholder_single): a wall box 0.46 wide and 0.35 high, 0.16 off the wall, with a round
# socket and a heavy plug seated in it, its cable dropping out of the bottom.
p = mk.fresh()
case = mk.mat("ph_case", (0.55, 0.56, 0.5), 0.6, 0.3)
dark = mk.mat("ph_dark", (0.08, 0.08, 0.08), 0.6)
yellow = mk.mat("ph_yellow", (0.8, 0.62, 0.1), 0.5)
mk.box(p, (0, 0.06, 0.175), (0.46, 0.04, 0.35), case)
mk.box(p, (0, 0.0, 0.2), (0.3, 0.08, 0.26), case)
mk.cyl(p, (0, -0.05, 0.22), 0.08, 0.03, dark, verts=20, rot=(PI / 2, 0, 0))
mk.cyl(p, (0, -0.075, 0.22), 0.06, 0.05, yellow, verts=20, rot=(PI / 2, 0, 0))
mk.box(p, (0, -0.075, 0.13), (0.04, 0.04, 0.12), dark)
mk.cyl(p, (0, -0.075, 0.035), 0.015, 0.07, dark, verts=8)
for x in (-0.2, 0.2):
    mk.cyl(p, (x, 0.04, 0.32), 0.01, 0.01, dark, verts=8, rot=(PI / 2, 0, 0))
    mk.cyl(p, (x, 0.04, 0.03), 0.01, 0.01, dark, verts=8, rot=(PI / 2, 0, 0))
mk.finish(p, "dm_plugholder", out("dm_plugholder"))

# Broken building wall (props_buildings/collapsedbuilding01awall): a 12.3 long stretch of brick wall 0.35 thick broken to a
# jagged top 1 to 3.9 high, with a window gap, rebar stubs and fallen chunks against its foot, 1.67 deep with the rubble.
p = mk.fresh()
random.seed(1117)
brick = mk.mat("rw_brick", (0.48, 0.3, 0.24), 0.9)
conc = mk.mat("rw_concrete", (0.55, 0.54, 0.5), 0.9)
steel = mk.mat("rw_rebar", (0.35, 0.22, 0.15), 0.7, 0.6)
L, n = 12.3, 14
w = L / n
for i in range(n):
    x = -L / 2 + w * (i + 0.5)
    h = 1.0 + 2.9 * (0.5 + 0.5 * math.sin(i * 0.9 + 0.6)) * random.uniform(0.75, 1.0)
    if i in (5, 6):
        mk.box(p, (x, 0, 0.45), (w, 0.35, 0.9), brick)
        mk.box(p, (x, 0, h - 0.2), (w, 0.35, 0.4), brick)
    else:
        mk.box(p, (x, 0, h / 2), (w, 0.35, h), brick)
    if i % 3 == 0:
        for k in range(2):
            mk.cyl(p, (x + (k - 0.5) * 0.25, 0, h + 0.15), 0.012, 0.3, steel, verts=6, rot=(random.uniform(-0.3, 0.3), 0, 0))
mk.box(p, (0, 0, 0.92), (L, 0.4, 0.06), conc)
for i in range(9):
    x = random.uniform(-L / 2 + 0.6, L / 2 - 0.6)
    s = random.uniform(0.3, 0.7)
    mk.box(p, (x, random.choice((-1, 1)) * random.uniform(0.35, 0.6), s * 0.5), (s, s * 0.8, s * 0.7), brick,
           rot=(random.uniform(-0.4, 0.4), random.uniform(-0.4, 0.4), random.uniform(0, PI)))
mk.finish(p, "dm_ruinwall", out("dm_ruinwall"))

# Roadside billboard (cs_assault/billboard): a blank poster board 4.55 long and 1.6 high on two posts, 2.6 high overall,
# with raking back struts that make it 1.07 deep; the poster is plain colour blocks, no lettering.
p = mk.fresh()
wood = mk.mat("bb_post", (0.36, 0.3, 0.24), 0.8)
frame = mk.mat("bb_frame", (0.22, 0.24, 0.25), 0.5, 0.6)
paper = mk.mat("bb_paper", (0.86, 0.84, 0.78), 0.8)
blue = mk.mat("bb_blue", (0.16, 0.32, 0.55), 0.7)
red = mk.mat("bb_red", (0.7, 0.2, 0.15), 0.7)
mk.box(p, (0, -0.33, 1.8), (4.55, 0.08, 1.6), frame)
mk.box(p, (0, -0.375, 1.8), (4.4, 0.02, 1.46), paper)
mk.box(p, (-1.0, -0.388, 1.95), (2.0, 0.01, 0.8), blue)
mk.box(p, (1.35, -0.388, 1.55), (1.1, 0.01, 0.5), red)
for x in (-1.5, 1.5):
    mk.box(p, (x, -0.25, 1.3), (0.15, 0.15, 2.6), wood)
    mk.beam(p, (x, -0.18, 1.9), (x, 0.38, 0.03), 0.09, wood)
    mk.box(p, (x, 0.25, 0.03), (0.2, 0.3, 0.06), wood)
mk.box(p, (0, -0.25, 0.95), (3.2, 0.06, 0.1), wood)
mk.finish(p, "dm_billboard", out("dm_billboard"))


# Kitchen cooker hood (props_idbs/go/kitchen_vent1): a steel canopy 1.2 wide and 0.65 deep stepping in over 0.4, a filter
# grille under it and a square flue to the ceiling, 1.03 high in all.
p = mk.fresh()
steel = mk.mat("kh_steel", (0.66, 0.67, 0.68), 0.35, 0.9)
dark = mk.mat("kh_grille", (0.12, 0.12, 0.13), 0.6, 0.5)
mk.box(p, (0, 0, 0.06), (1.2, 0.65, 0.12), steel)
mk.box(p, (0, 0, 0.18), (1.0, 0.55, 0.12), steel)
mk.box(p, (0, 0, 0.3), (0.7, 0.42, 0.12), steel)
mk.box(p, (0, 0, 0.005), (1.08, 0.53, 0.01), dark)
mk.box(p, (0, 0, 0.7), (0.32, 0.3, 0.66), steel)
mk.finish(p, "dm_kitchenhood", out("dm_kitchenhood"))
