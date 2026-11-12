"""Household and warehouse clutter, CC0, for `rules/models/categories.tsv`: kitchen sink, coffee mug, small shelf unit,
takeout carton, appliance carton, ceiling truss grid, traffic cone, grocery shelving, fridge door.

blender -b --factory-startup --python household.py -- outdir
Writes dm_kitchensink, dm_coffeemug, dm_shelfsmall, dm_takeoutcarton, dm_appliancebox, dm_ceilingtruss, dm_trafficcone,
dm_grocery_shelving and dm_fridgedoor into outdir. Blender Z is up; X is the width, Y the depth; origin on the floor, centred.
Plain colour materials.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import modelkit as mk  # noqa: E402

outdir = sys.argv[sys.argv.index("--") + 1]
PI = math.pi


def out(name):
    return f"{outdir}/{name}.glb"


# Kitchen sink on a base cabinet: 0.44 wide x 0.52 deep x 0.68 high, steel basin, tap, two doors.
p = mk.fresh()
cab = mk.mat("sink_cab", (0.82, 0.82, 0.78), 0.6)
steel = mk.mat("sink_steel", (0.7, 0.72, 0.74), 0.3, 0.8)
dark = mk.mat("sink_dark", (0.3, 0.3, 0.32), 0.6)
mk.box(p, (0, 0, 0.3), (0.44, 0.52, 0.6), cab)
mk.box(p, (0, 0, 0.64), (0.44, 0.52, 0.04), steel)
mk.box(p, (0, 0, 0.665), (0.34, 0.4, 0.012), dark)
mk.box(p, (0, 0.23, 0.68), (0.44, 0.04, 0.02), steel)
mk.cyl(p, (0, 0.2, 0.72), 0.012, 0.1, steel, verts=8)
mk.box(p, (0, 0.14, 0.76), (0.014, 0.12, 0.014), steel)
for sx in (-1, 1):
    mk.box(p, (sx * 0.1, -0.265, 0.3), (0.2, 0.012, 0.52), cab)
    mk.box(p, (sx * 0.03, -0.275, 0.4), (0.012, 0.012, 0.1), steel)
mk.box(p, (0, 0, 0.02), (0.42, 0.5, 0.04), dark)
mk.finish(p, "dm_kitchensink", out("dm_kitchensink"))

# Coffee mug: 0.095 across the handle, 0.1 high.
p = mk.fresh()
glaze = mk.mat("mug_glaze", (0.88, 0.86, 0.8), 0.35)
coffee = mk.mat("mug_coffee", (0.18, 0.1, 0.06), 0.3)
mk.cyl(p, (0, 0, 0.05), 0.04, 0.1, glaze, verts=16)
mk.cyl(p, (0, 0, 0.097), 0.034, 0.012, coffee, verts=16)
mk.box(p, (0.052, 0, 0.055), (0.03, 0.012, 0.012), glaze)
mk.box(p, (0.052, 0, 0.03), (0.03, 0.012, 0.012), glaze)
mk.box(p, (0.064, 0, 0.043), (0.012, 0.012, 0.04), glaze)
mk.finish(p, "dm_coffeemug", out("dm_coffeemug"))

# Small wooden shelf unit: 0.81 wide x 0.29 deep x 0.31 high, an upright at each end and a board between.
p = mk.fresh()
wood = mk.mat("shelf_wood", (0.5, 0.36, 0.22), 0.8)
mk.box(p, (0, 0, 0.012), (0.81, 0.29, 0.024), wood)
mk.box(p, (0, 0, 0.155), (0.81, 0.29, 0.02), wood)
mk.box(p, (0, 0, 0.3), (0.81, 0.29, 0.02), wood)
mk.box(p, (-0.39, 0, 0.155), (0.024, 0.29, 0.31), wood)
mk.box(p, (0.39, 0, 0.155), (0.024, 0.29, 0.31), wood)
mk.box(p, (0, 0.14, 0.155), (0.81, 0.012, 0.31), wood)
mk.finish(p, "dm_shelfsmall", out("dm_shelfsmall"))

# Takeout carton: tapering white pail with folded flaps and a wire handle, 0.138 x 0.132 x 0.207 high.
p = mk.fresh()
paper = mk.mat("carton_paper", (0.92, 0.9, 0.86), 0.8)
red = mk.mat("carton_red", (0.75, 0.15, 0.12), 0.8)
wire = mk.mat("carton_wire", (0.6, 0.6, 0.62), 0.4, 0.7)
mk.box(p, (0, 0, 0.07), (0.1, 0.1, 0.14), paper)
mk.box(p, (0, 0, 0.12), (0.138, 0.132, 0.1), paper)
mk.box(p, (0, -0.067, 0.11), (0.08, 0.004, 0.06), red)
for sx in (-1, 1):
    mk.box(p, (sx * 0.035, 0, 0.176), (0.07, 0.13, 0.012), paper, rot=(0, sx * 0.45, 0))
mk.box(p, (0, 0, 0.2), (0.12, 0.008, 0.008), wire)
mk.box(p, (-0.06, 0, 0.185), (0.008, 0.008, 0.03), wire)
mk.box(p, (0.06, 0, 0.185), (0.008, 0.008, 0.03), wire)
mk.finish(p, "dm_takeoutcarton", out("dm_takeoutcarton"))

# Appliance carton: tall cardboard box, taped flaps and a printed panel, 0.81 x 0.80 x 1.18.
p = mk.fresh()
card = mk.mat("box_card", (0.7, 0.55, 0.36), 0.9)
tape = mk.mat("box_tape", (0.55, 0.42, 0.26), 0.5)
print_ = mk.mat("box_print", (0.12, 0.2, 0.4), 0.9)
mk.box(p, (0, 0, 0.59), (0.81, 0.8, 1.18), card)
mk.box(p, (0, 0, 1.18), (0.78, 0.04, 0.005), tape)
mk.box(p, (0, -0.4, 0.8), (0.4, 0.006, 0.25), print_)
mk.box(p, (0, -0.4, 0.4), (0.06, 0.006, 0.6), tape)
mk.box(p, (0.405, 0, 0.5), (0.006, 0.5, 0.12), print_)
mk.finish(p, "dm_appliancebox", out("dm_appliancebox"))

# Ceiling truss grid: a 1 x 1 m square frame, 0.25 m deep, cross members and diagonals; scales to the 64 to 128 unit panels.
p = mk.fresh()
steel = mk.mat("truss_steel", (0.45, 0.46, 0.44), 0.55, 0.5)
t, h = 0.03, 0.25
for z in (0.02, h):
    for a in (-0.485, 0.485):
        mk.box(p, (a, 0, z), (t, 1.0, t), steel)
        mk.box(p, (0, a, z), (1.0, t, t), steel)
    mk.box(p, (0, 0, z), (t, 1.0, t), steel)
    mk.box(p, (0, 0, z), (1.0, t, t), steel)
for a in (-0.485, 0.485):
    for b in (-0.485, 0.485):
        mk.box(p, (a, b, h / 2), (t, t, h), steel)
for i in range(4):
    x = -0.5 + (i + 0.5) * 0.25
    mk.beam(p, (x - 0.125, -0.485, 0.02), (x + 0.125, -0.485, h), 0.02, steel)
    mk.beam(p, (x - 0.125, 0.485, h), (x + 0.125, 0.485, 0.02), 0.02, steel)
mk.finish(p, "dm_ceilingtruss", out("dm_ceilingtruss"))

# Traffic cone: orange cone on a square base with a white band, 0.31 x 0.57 high.
p = mk.fresh()
orange = mk.mat("cone_orange", (0.9, 0.35, 0.05), 0.6)
white = mk.mat("cone_white", (0.9, 0.9, 0.88), 0.6)
mk.box(p, (0, 0, 0.012), (0.31, 0.31, 0.024), orange)
bpy.ops.mesh.primitive_cone_add(vertices=14, radius1=0.12, radius2=0.025, depth=0.54, location=(0, 0, 0.294))
cone = bpy.context.object
cone.data.materials.append(orange)
p.append(cone)
bpy.ops.mesh.primitive_cone_add(vertices=14, radius1=0.082, radius2=0.062, depth=0.1, location=(0, 0, 0.32))
band = bpy.context.object
band.data.materials.append(white)
p.append(band)
mk.finish(p, "dm_trafficcone", out("dm_trafficcone"))

# Grocery shelving: an upright gondola 1.38 wide x 0.43 deep x 1.75 high, five shelves and end panels.
p = mk.fresh()
frame = mk.mat("gro_frame", (0.78, 0.78, 0.74), 0.6, 0.3)
board = mk.mat("gro_board", (0.62, 0.6, 0.55), 0.7)
tins = [mk.mat("gro_t%d" % i, c, 0.6) for i, c in enumerate(((0.75, 0.2, 0.15), (0.2, 0.45, 0.25), (0.85, 0.75, 0.2)))]
L, D, H = 1.38, 0.43, 1.75
for sx in (-1, 1):
    mk.box(p, (sx * (L / 2 - 0.02), 0, H / 2), (0.04, D, H), frame)
mk.box(p, (0, D / 2 - 0.01, H / 2), (L, 0.02, H), board)
for i in range(5):
    z = 0.12 + i * 0.4
    mk.box(p, (0, 0, z), (L - 0.04, D, 0.025), frame)
    for j in range(7):
        mk.box(p, (-L / 2 + 0.12 + j * 0.19, -0.05, z + 0.1), (0.14, 0.22, 0.17), tins[(i + j) % 3])
mk.finish(p, "dm_grocery_shelving", out("dm_grocery_shelving"))

# Fridge door: a slab 0.61 wide, 1.06 high, 0.18 thick, with a handle bar.
p = mk.fresh()
white = mk.mat("fr_white", (0.88, 0.88, 0.86), 0.4)
chrome = mk.mat("fr_chrome", (0.7, 0.7, 0.72), 0.3, 0.8)
mk.box(p, (0, 0, 0.53), (0.61, 0.18, 1.06), white)
mk.box(p, (0.25, -0.11, 0.7), (0.025, 0.03, 0.4), chrome)
mk.box(p, (0, -0.092, 0.53), (0.55, 0.006, 1.0), mk.mat("fr_inset", (0.8, 0.8, 0.78), 0.5))
mk.finish(p, "dm_fridgedoor", out("dm_fridgedoor"))
