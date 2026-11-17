"""Debris, shop and office stand-ins, CC0, for `rules/models/categories.tsv`: drive case, hanging shop light, small ceiling
lantern, concrete rubble pile and heap, broken slab and wall section, produce pile and spread, car battery, I-beam, wall
shelf, metal bunk, shoe, push broom, flat-panel TV, high-bay lamp, grocery chiller, plotter, cash bundle, low file
cabinet, propeller engine, crate stack, money pallet, beer case, box stack, exit sign, lab jar.

blender -b --factory-startup --python debris_goods.py -- outdir
Writes one dm_<name>.glb per model into outdir (the names are the mk.finish calls below). Blender Z is up, X the length,
Y the depth; origin on the floor, centred. Each size is the original's measured box where the model dims table has
one (Blender X = its z, Y = its x, Z = its y), else a typical size. Plain colour materials, seeded randomness.
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


def cone(parts, c, r1, r2, h, m, verts=16, rot=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=h, location=c)
    o = bpy.context.object
    o.rotation_euler = rot
    o.data.materials.append(m)
    parts.append(o)
    return o


def sphere(parts, c, s, m, seg=10):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=max(4, seg // 2), radius=0.5, location=c)
    o = bpy.context.object
    o.scale = s
    o.data.materials.append(m)
    parts.append(o)
    return o


def chunk(parts, rnd, c, size, m):
    """A broken block: a box turned at random, a little squashed."""
    s = (size * rnd.uniform(0.6, 1.2), size * rnd.uniform(0.5, 1.0), size * rnd.uniform(0.3, 0.7))
    return mk.box(parts, c, s, m, rot=(rnd.uniform(-0.5, 0.5), rnd.uniform(-0.5, 0.5), rnd.uniform(0, PI)))


def lift(parts):
    """Put the lowest point on z = 0."""
    bpy.context.view_layer.update()
    low = min((o.matrix_world @ v.co).z for o in parts for v in o.data.vertices)
    for o in parts:
        o.location.z -= low


def crate(parts, c, s, wood, batten):
    """A board crate: the body and an edge batten round each face."""
    x, y, z = c
    w, d, h = s
    mk.box(parts, c, (w - 0.02, d - 0.02, h - 0.02), wood)
    t = min(w, d, h) * 0.08
    for sx in (-1, 1):
        for sy in (-1, 1):
            mk.box(parts, (x + sx * (w / 2 - t / 2), y + sy * (d / 2 - t / 2), z), (t, t, h), batten)
        for sz in (-1, 1):
            mk.box(parts, (x + sx * (w / 2 - t / 2), y, z + sz * (h / 2 - t / 2)), (t, d, t), batten)
    for sy in (-1, 1):
        for sz in (-1, 1):
            mk.box(parts, (x, y + sy * (d / 2 - t / 2), z + sz * (h / 2 - t / 2)), (w, t, t), batten)
    for sy in (-1, 1):
        mk.beam(parts, (x - w / 2 + t, y + sy * (d / 2 + 0.004), z - h / 2 + t), (x + w / 2 - t, y + sy * (d / 2 + 0.004), z + h / 2 - t), t * 0.8, batten)


def cardboard(parts, c, s, m, tape):
    x, y, z = c
    w, d, h = s
    mk.box(parts, c, s, m)
    mk.box(parts, (x, y, z + h / 2 + 0.002), (w * 1.002, 0.05, 0.004), tape)
    mk.box(parts, (x, y, z + h / 2 + 0.001), (0.004, d * 0.995, 0.003), m)


# Drive case (desktop drive enclosure stood on its side): 0.14 x 0.37 x 0.38; bays and a vent face -Y.
p = mk.fresh()
case = mk.mat("dc_case", (0.72, 0.7, 0.64), 0.6, 0.2)
dark = mk.mat("dc_dark", (0.12, 0.12, 0.13), 0.5)
led = mk.mat("dc_led", (0.2, 0.8, 0.3), 0.3)
mk.box(p, (0, 0, 0.19), (0.14, 0.37, 0.37), case)
mk.box(p, (0, -0.186, 0.19), (0.13, 0.008, 0.36), dark)
for i in range(3):
    mk.box(p, (0, -0.19, 0.31 - i * 0.05), (0.11, 0.006, 0.04), case)
    mk.box(p, (0.035, -0.194, 0.31 - i * 0.05), (0.02, 0.004, 0.006), dark)
for i in range(6):
    mk.box(p, (0, -0.19, 0.06 + i * 0.018), (0.1, 0.006, 0.008), case)
mk.box(p, (-0.04, -0.192, 0.155), (0.012, 0.004, 0.012), led)
for sx in (-1, 1):
    for sy in (-1, 1):
        mk.box(p, (sx * 0.055, sy * 0.16, 0.004), (0.02, 0.03, 0.008), dark)
mk.finish(p, "dm_drivecase", out("dm_drivecase"))

# Hanging shop light: reflector 0.29 x 1.24 with two tubes, hung 0.82 on two chains.
p = mk.fresh()
shade = mk.mat("sl_shade", (0.82, 0.83, 0.8), 0.45, 0.4)
tube = mk.mat("sl_tube", (0.95, 0.95, 0.9), 0.3)
chain = mk.mat("sl_chain", (0.3, 0.3, 0.32), 0.5, 0.8)
mk.box(p, (0, 0, 0.1), (0.12, 1.22, 0.04), shade)
for s in (-1, 1):
    mk.box(p, (s * 0.1, 0, 0.065), (0.1, 1.22, 0.012), shade, rot=(0, s * 0.75, 0))
    mk.box(p, (0, s * 0.615, 0.07), (0.28, 0.012, 0.08), shade)
    mk.cyl(p, (s * 0.045, 0, 0.05), 0.016, 1.18, tube, verts=10, rot=(PI / 2, 0, 0))
    for i in range(14):
        z = 0.14 + i * 0.048
        mk.box(p, (0, s * 0.45, z), (0.008 if i % 2 else 0.022, 0.022 if i % 2 else 0.008, 0.05), chain)
    mk.cyl(p, (0, s * 0.45, 0.81), 0.04, 0.02, chain, verts=12)
lift(p)
mk.finish(p, "dm_shoplight", out("dm_shoplight"))

# Small ceiling lantern: canopy, stem, a globe in a wire cage. 0.15 x 0.15 x 0.17.
p = mk.fresh()
iron = mk.mat("cl_iron", (0.16, 0.15, 0.14), 0.5, 0.7)
glass = mk.mat("cl_glass", (0.95, 0.88, 0.7), 0.2)
mk.cyl(p, (0, 0, 0.162), 0.05, 0.016, iron, verts=16)
mk.cyl(p, (0, 0, 0.13), 0.008, 0.05, iron, verts=8)
mk.cyl(p, (0, 0, 0.1), 0.04, 0.02, iron, verts=14)
sphere(p, (0, 0, 0.055), (0.12, 0.12, 0.11), glass, seg=16)
for i in range(6):
    a = i * PI / 3
    mk.beam(p, (0.035 * math.cos(a), 0.035 * math.sin(a), 0.095), (0.072 * math.cos(a), 0.072 * math.sin(a), 0.05), 0.006, iron)
    mk.beam(p, (0.072 * math.cos(a), 0.072 * math.sin(a), 0.05), (0.02 * math.cos(a), 0.02 * math.sin(a), 0.0), 0.006, iron)
mk.cyl(p, (0, 0, 0.05), 0.073, 0.008, iron, verts=18)
lift(p)
mk.finish(p, "dm_ceilinglantern", out("dm_ceilinglantern"))

# Concrete rubble pile: broken blocks and a few bent rebar ends, 2.5 x 2.5 x 0.8, low and spread.
rnd = random.Random(71)
p = mk.fresh()
conc = mk.mat("rb_conc", (0.56, 0.55, 0.52), 0.95)
conc2 = mk.mat("rb_conc2", (0.47, 0.46, 0.44), 0.95)
dust = mk.mat("rb_dust", (0.62, 0.6, 0.56), 1.0)
rebar = mk.mat("rb_rebar", (0.35, 0.22, 0.14), 0.7, 0.6)
sphere(p, (0, 0, 0.0), (2.3, 2.3, 0.6), dust, seg=16)
for i in range(46):
    a, r = rnd.uniform(0, 2 * PI), 1.05 * math.sqrt(rnd.random())
    x, y = r * math.cos(a), r * math.sin(a)
    z = 0.24 * (1 - (r / 1.15) ** 2) + rnd.uniform(0, 0.06)
    chunk(p, rnd, (x, y, z), rnd.uniform(0.18, 0.42), conc if i % 3 else conc2)
for i in range(7):
    a = rnd.uniform(0, 2 * PI)
    x, y = 0.5 * math.cos(a), 0.5 * math.sin(a)
    mk.beam(p, (x, y, 0.2), (x + rnd.uniform(-0.5, 0.5), y + rnd.uniform(-0.5, 0.5), rnd.uniform(0.35, 0.6)), 0.016, rebar)
lift(p)
mk.finish(p, "dm_rubblepile", out("dm_rubblepile"))

# Concrete rubble heap (a barricade of debris): taller, 2.4 x 1.1 x 1.2, a broken slab leaning in it.
rnd = random.Random(72)
p = mk.fresh()
conc = mk.mat("rh_conc", (0.56, 0.55, 0.52), 0.95)
conc2 = mk.mat("rh_conc2", (0.45, 0.44, 0.42), 0.95)
rebar = mk.mat("rh_rebar", (0.35, 0.22, 0.14), 0.7, 0.6)
sphere(p, (0, 0, 0.0), (2.2, 1.0, 0.9), conc2, seg=16)
for i in range(38):
    x, y = rnd.uniform(-1.05, 1.05), rnd.uniform(-0.42, 0.42)
    z = 0.5 * (1 - (x / 1.15) ** 2) * (1 - (y / 0.5) ** 2) + rnd.uniform(0.0, 0.1)
    chunk(p, rnd, (x, y, z), rnd.uniform(0.2, 0.45), conc if i % 4 else conc2)
mk.box(p, (0.3, 0.1, 0.3), (1.2, 0.14, 0.7), conc, rot=(0.8, 0.15, 0.2))
for i in range(6):
    x = rnd.uniform(-0.8, 0.8)
    mk.beam(p, (x, 0, 0.5), (x + rnd.uniform(-0.3, 0.3), rnd.uniform(-0.4, 0.4), rnd.uniform(0.55, 0.7)), 0.018, rebar)
lift(p)
mk.finish(p, "dm_rubbleheap", out("dm_rubbleheap"))

# Broken floor slab: 1.22 x 1.22 x 0.15, one corner snapped off, rebar grid ends out of the break.
p = mk.fresh()
conc = mk.mat("cs_conc", (0.6, 0.59, 0.56), 0.95)
rebar = mk.mat("cs_rebar", (0.35, 0.22, 0.14), 0.7, 0.6)
mk.box(p, (-0.15, 0, 0.075), (0.92, 1.22, 0.15), conc)
mk.box(p, (0.42, -0.2, 0.075), (0.38, 0.82, 0.15), conc)
mk.box(p, (0.43, 0.36, 0.06), (0.28, 0.36, 0.12), conc, rot=(0.08, 0.06, 0.3))
for i in range(4):
    y = -0.45 + i * 0.3
    mk.beam(p, (0.4, y, 0.075), (0.62 + 0.03 * i, y + 0.04, 0.09 + 0.02 * (i % 2)), 0.012, rebar)
lift(p)
mk.finish(p, "dm_concreteslab", out("dm_concreteslab"))

# Broken wall section: 2.4 x 0.3 x 2.4 with a ragged top, a hole and rebar out of the break.
rnd = random.Random(74)
p = mk.fresh()
conc = mk.mat("cw_conc", (0.6, 0.59, 0.56), 0.95)
rebar = mk.mat("cw_rebar", (0.35, 0.22, 0.14), 0.7, 0.6)
mk.box(p, (0, 0, 0.6), (2.4, 0.3, 1.2), conc)
for i in range(8):
    x = -1.05 + i * 0.3
    h = rnd.uniform(0.5, 1.05)
    mk.box(p, (x, 0, 1.2 + h / 2), (0.3, 0.3, h), conc)
    mk.box(p, (x + 0.1, 0, 1.2 + h), (0.18, 0.28, 0.16), conc, rot=(0, rnd.uniform(-0.6, 0.6), 0))
    mk.beam(p, (x, 0, 1.1 + h), (x + rnd.uniform(-0.1, 0.1), rnd.uniform(-0.05, 0.05), 1.3 + h + rnd.uniform(0.1, 0.25)), 0.016, rebar)
mk.finish(p, "dm_concretewall", out("dm_concretewall"))

# Produce pile: a mound of oranges, apples and melons on a sacking cloth, 1.18 x 0.63 x 0.38.
rnd = random.Random(75)
p = mk.fresh()
cloth = mk.mat("pp_cloth", (0.55, 0.45, 0.3), 1.0)
cols = [mk.mat("pp_orange", (0.9, 0.45, 0.08), 0.6), mk.mat("pp_apple", (0.7, 0.1, 0.08), 0.5),
        mk.mat("pp_green", (0.45, 0.65, 0.15), 0.6), mk.mat("pp_yellow", (0.92, 0.8, 0.2), 0.6)]
melon = mk.mat("pp_melon", (0.2, 0.4, 0.15), 0.6)
mk.box(p, (0, 0, 0.005), (1.18, 0.63, 0.01), cloth)
for i in range(70):
    x, y = rnd.uniform(-0.52, 0.52), rnd.uniform(-0.26, 0.26)
    z = 0.28 * (1 - (x / 0.6) ** 2) * (1 - (y / 0.32) ** 2) + 0.03
    r = rnd.uniform(0.07, 0.1)
    sphere(p, (x, y, z), (r, r, r * 0.95), rnd.choice(cols), seg=8)
for x in (-0.32, 0.3):
    sphere(p, (x, 0.05, 0.1), (0.24, 0.17, 0.17), melon, seg=12)
lift(p)
mk.finish(p, "dm_producepile", out("dm_producepile"))

# Produce spread: one layer of fruit and veg in crates' worth of rows on a stall floor, 4.14 x 1.48 x 0.09.
rnd = random.Random(76)
p = mk.fresh()
cols = [mk.mat("ps_orange", (0.9, 0.45, 0.08), 0.6), mk.mat("ps_apple", (0.7, 0.1, 0.08), 0.5),
        mk.mat("ps_green", (0.45, 0.65, 0.15), 0.6), mk.mat("ps_yellow", (0.92, 0.8, 0.2), 0.6),
        mk.mat("ps_potato", (0.6, 0.45, 0.28), 0.9), mk.mat("ps_aubergine", (0.25, 0.08, 0.25), 0.4)]
for bx in range(6):
    m = cols[bx]
    x0 = -2.07 + bx * 0.69
    for i in range(7):
        for j in range(15):
            x = x0 + 0.05 + i * 0.085 + rnd.uniform(-0.01, 0.01)
            y = -0.7 + j * 0.1 + rnd.uniform(-0.01, 0.01)
            r = rnd.uniform(0.075, 0.09)
            sphere(p, (x, y, r / 2), (r, r, r * 0.95), m, seg=6)
lift(p)
mk.finish(p, "dm_producespread", out("dm_producespread"))

# Car battery: 0.3 x 0.18 x 0.2, black case, red and black terminals, a carry strap.
p = mk.fresh()
case = mk.mat("cb_case", (0.08, 0.08, 0.09), 0.5)
lid = mk.mat("cb_lid", (0.18, 0.18, 0.2), 0.5)
red = mk.mat("cb_red", (0.75, 0.08, 0.06), 0.5)
lead = mk.mat("cb_lead", (0.55, 0.55, 0.55), 0.4, 0.8)
label = mk.mat("cb_label", (0.85, 0.75, 0.1), 0.5)
mk.box(p, (0, 0, 0.085), (0.3, 0.18, 0.17), case)
mk.box(p, (0, 0, 0.18), (0.3, 0.18, 0.02), lid)
mk.box(p, (0, -0.091, 0.1), (0.2, 0.004, 0.06), label)
for s, m in ((-1, red), (1, lid)):
    mk.cyl(p, (s * 0.11, -0.05, 0.198), 0.012, 0.025, lead, verts=10)
    mk.cyl(p, (s * 0.11, -0.05, 0.193), 0.022, 0.012, m, verts=12)
mk.beam(p, (-0.12, 0.05, 0.19), (0, 0.05, 0.24), 0.012, case)
mk.beam(p, (0, 0.05, 0.24), (0.12, 0.05, 0.19), 0.012, case)
mk.finish(p, "dm_carbattery", out("dm_carbattery"))

# I-beam: a loose steel beam lying on its flange, 2.4 long, 0.15 x 0.3 section, rusty.
p = mk.fresh()
steel = mk.mat("ib_steel", (0.4, 0.25, 0.16), 0.8, 0.6)
for z in (0.008, 0.292):
    mk.box(p, (0, 0, z), (2.4, 0.15, 0.016), steel)
mk.box(p, (0, 0, 0.15), (2.4, 0.012, 0.28), steel)
for x in (-0.9, 0.0, 0.9):
    for s in (-1, 1):
        mk.box(p, (x, s * 0.04, 0.15), (0.01, 0.065, 0.27), steel)
mk.finish(p, "dm_ibeam", out("dm_ibeam"))

# Wall shelf: steel plate shelf on two brackets with a lip, 0.37 deep (X) x 0.95 wide (Y) x 0.39 high, back to +X.
p = mk.fresh()
steel = mk.mat("ws_steel", (0.45, 0.47, 0.46), 0.5, 0.6)
mk.box(p, (0, 0, 0.375), (0.37, 0.95, 0.025), steel)
mk.box(p, (-0.18, 0, 0.395), (0.012, 0.95, 0.04), steel)
for s in (-1, 1):
    mk.box(p, (0.175, s * 0.4, 0.2), (0.02, 0.04, 0.38), steel)
    mk.beam(p, (0.17, s * 0.4, 0.04), (-0.14, s * 0.4, 0.36), 0.025, steel)
mk.box(p, (0.18, 0, 0.36), (0.01, 0.95, 0.05), steel)
lift(p)
mk.finish(p, "dm_wallshelf", out("dm_wallshelf"))

# Metal bunk: welded steel frame, 2.0 x 0.8 x 0.55, flat strap deck, four legs.
p = mk.fresh()
steel = mk.mat("mb_steel", (0.38, 0.4, 0.4), 0.55, 0.6)
deck = mk.mat("mb_deck", (0.3, 0.32, 0.32), 0.6, 0.5)
for s in (-1, 1):
    mk.box(p, (0, s * 0.39, 0.45), (2.0, 0.04, 0.06), steel)
    mk.box(p, (s * 0.98, 0, 0.45), (0.04, 0.8, 0.06), steel)
    for t in (-1, 1):
        mk.box(p, (s * 0.96, t * 0.37, 0.24), (0.05, 0.05, 0.48), steel)
    mk.box(p, (s * 0.96, 0, 0.12), (0.04, 0.74, 0.04), steel)
for i in range(13):
    mk.box(p, (-0.9 + i * 0.15, 0, 0.47), (0.05, 0.76, 0.008), deck)
for i in range(3):
    mk.box(p, (0, -0.25 + i * 0.25, 0.465), (1.92, 0.04, 0.008), deck)
mk.box(p, (-0.98, 0, 0.53), (0.04, 0.8, 0.04), steel)
mk.finish(p, "dm_metalbed", out("dm_metalbed"))

# Shoe (a work boot): 0.12 wide (X) x 0.25 long (Y) x 0.19 high.
p = mk.fresh()
leather = mk.mat("sh_leather", (0.32, 0.2, 0.11), 0.7)
sole = mk.mat("sh_sole", (0.08, 0.07, 0.07), 0.9)
lace = mk.mat("sh_lace", (0.75, 0.7, 0.6), 0.8)
mk.box(p, (0, 0, 0.012), (0.11, 0.25, 0.024), sole)
mk.box(p, (0, 0.005, 0.05), (0.105, 0.22, 0.055), leather)
sphere(p, (0, -0.075, 0.05), (0.105, 0.11, 0.07), leather, seg=12)
mk.box(p, (0, 0.06, 0.11), (0.1, 0.11, 0.15), leather)
mk.box(p, (0, 0.06, 0.183), (0.106, 0.116, 0.014), leather)
for i in range(4):
    mk.box(p, (0, 0.002, 0.1 + i * 0.022), (0.07, 0.006, 0.006), lace, rot=(0.6, 0, 0))
mk.finish(p, "dm_shoe", out("dm_shoe"))

# Push broom lying with its handle on something: head 0.77 wide (Y), handle 1.49 long (X) rising to 0.51.
p = mk.fresh()
wood = mk.mat("pb_wood", (0.6, 0.42, 0.24), 0.7)
head = mk.mat("pb_head", (0.25, 0.2, 0.16), 0.7)
bristle = mk.mat("pb_bristle", (0.1, 0.09, 0.08), 0.9)
mk.box(p, (-0.68, 0, 0.07), (0.07, 0.77, 0.045), head)
mk.box(p, (-0.68, 0, 0.025), (0.06, 0.74, 0.05), bristle)
mk.beam(p, (-0.66, 0, 0.09), (0.72, 0, 0.5), 0.028, wood)
mk.beam(p, (-0.66, -0.16, 0.09), (-0.45, 0, 0.16), 0.016, head)
mk.beam(p, (-0.66, 0.16, 0.09), (-0.45, 0, 0.16), 0.016, head)
mk.finish(p, "dm_pushbroom", out("dm_pushbroom"))

# Flat-panel TV on a wall bracket: 1.14 x 0.72 screen, 0.13 deep with the bracket, screen faces -Y.
p = mk.fresh()
frame = mk.mat("tv_frame", (0.06, 0.06, 0.07), 0.35, 0.3)
screen = mk.mat("tv_screen", (0.02, 0.03, 0.05), 0.15)
steel = mk.mat("tv_steel", (0.35, 0.35, 0.37), 0.5, 0.7)
mk.box(p, (0, -0.035, 0.36), (1.14, 0.05, 0.72), frame)
mk.box(p, (0, -0.061, 0.37), (1.08, 0.004, 0.64), screen)
mk.box(p, (0, 0.01, 0.37), (0.6, 0.04, 0.4), frame)
mk.box(p, (0, 0.055, 0.37), (0.4, 0.02, 0.3), steel)
for s in (-1, 1):
    mk.box(p, (s * 0.15, 0.04, 0.37), (0.03, 0.04, 0.36), steel)
mk.box(p, (0.5, -0.062, 0.05), (0.02, 0.004, 0.008), mk.mat("tv_led", (0.2, 0.5, 1.0), 0.3))
mk.finish(p, "dm_plasmatv", out("dm_plasmatv"))

# High-bay lamp: a metal dome shade 0.56 across on a stem, a bulb and a guard, 0.52 high.
p = mk.fresh()
shade = mk.mat("hb_shade", (0.32, 0.38, 0.32), 0.5, 0.6)
inner = mk.mat("hb_inner", (0.9, 0.9, 0.88), 0.4)
bulb = mk.mat("hb_bulb", (1.0, 0.95, 0.8), 0.2)
steel = mk.mat("hb_steel", (0.3, 0.3, 0.3), 0.5, 0.7)
cone(p, (0, 0, 0.1), 0.28, 0.1, 0.2, shade, verts=24)
cone(p, (0, 0, 0.098), 0.27, 0.095, 0.19, inner, verts=24)
mk.cyl(p, (0, 0, 0.24), 0.1, 0.08, shade, verts=20)
mk.cyl(p, (0, 0, 0.4), 0.02, 0.24, steel, verts=8)
mk.cyl(p, (0, 0, 0.51), 0.05, 0.02, steel, verts=12)
sphere(p, (0, 0, 0.12), (0.1, 0.1, 0.12), bulb, seg=12)
mk.cyl(p, (0, 0, 0.004), 0.28, 0.008, steel, verts=24)
for i in range(4):
    a = i * PI / 2
    mk.beam(p, (0.28 * math.cos(a), 0.28 * math.sin(a), 0.004), (0, 0, 0.004), 0.006, steel)
mk.finish(p, "dm_industriallamp", out("dm_industriallamp"))

# Grocery chiller: an upright three-door glass chiller, 2.77 wide (X) x 0.91 deep x 1.85 high, doors face -Y.
p = mk.fresh()
body = mk.mat("gc_body", (0.85, 0.87, 0.88), 0.45, 0.3)
glass = mk.mat("gc_glass", (0.55, 0.7, 0.75), 0.1, 0.2)
trim = mk.mat("gc_trim", (0.3, 0.32, 0.34), 0.4, 0.6)
sign = mk.mat("gc_sign", (0.1, 0.35, 0.7), 0.5)
goods = [mk.mat("gc_g1", (0.8, 0.15, 0.1), 0.6), mk.mat("gc_g2", (0.95, 0.85, 0.3), 0.6), mk.mat("gc_g3", (0.2, 0.55, 0.25), 0.6),
         mk.mat("gc_g4", (0.95, 0.95, 0.95), 0.6)]
mk.box(p, (0, 0.05, 0.925), (2.77, 0.81, 1.85), body)
mk.box(p, (0, -0.34, 0.06), (2.77, 0.06, 0.12), trim)
mk.box(p, (0, -0.37, 1.72), (2.77, 0.06, 0.26), sign)
rnd = random.Random(77)
for i in range(3):
    x = -0.92 + i * 0.92
    mk.box(p, (x, -0.355, 0.9), (0.9, 0.03, 1.56), trim)
    mk.box(p, (x, -0.372, 0.9), (0.8, 0.008, 1.46), glass)
    mk.box(p, (x + 0.36, -0.4, 0.95), (0.03, 0.04, 0.6), trim)
    for r in range(5):
        z = 0.24 + r * 0.29
        mk.box(p, (x, -0.3, z), (0.84, 0.03, 0.02), trim)
        for k in range(7):
            mk.box(p, (x - 0.36 + k * 0.12, -0.3, z + 0.1), (0.08, 0.06, 0.18), goods[rnd.randrange(4)])
mk.finish(p, "dm_grocerychiller", out("dm_grocerychiller"))

# Wide-format plotter on its stand: 0.7 deep (X) x 0.9 wide (Y) x 1.1 high, paper basket under it.
p = mk.fresh()
body = mk.mat("pl_body", (0.82, 0.82, 0.8), 0.5)
dark = mk.mat("pl_dark", (0.15, 0.15, 0.17), 0.5)
paper = mk.mat("pl_paper", (0.95, 0.95, 0.93), 0.8)
mk.box(p, (0.05, 0, 0.95), (0.4, 0.9, 0.3), body)
mk.box(p, (-0.16, 0, 0.98), (0.04, 0.86, 0.12), dark)
mk.box(p, (0.1, 0.36, 1.11), (0.14, 0.12, 0.012), dark)
mk.box(p, (-0.22, 0, 0.84), (0.25, 0.8, 0.005), paper, rot=(0, 0.6, 0))
for s in (-1, 1):
    mk.box(p, (0.05, s * 0.4, 0.42), (0.06, 0.05, 0.72), dark)
    mk.box(p, (0.05, s * 0.4, 0.03), (0.6, 0.06, 0.05), dark)
    for t in (-1, 1):
        mk.cyl(p, (0.05 + t * 0.27, s * 0.4, 0.015), 0.02, 0.03, dark, verts=8)
mk.box(p, (0.05, 0, 0.4), (0.04, 0.8, 0.05), dark)
mk.beam(p, (-0.25, -0.38, 0.6), (-0.05, -0.38, 0.25), 0.012, dark)
mk.beam(p, (-0.25, 0.38, 0.6), (-0.05, 0.38, 0.25), 0.012, dark)
mk.box(p, (-0.14, 0, 0.42), (0.3, 0.76, 0.004), paper, rot=(0, -0.9, 0))
mk.finish(p, "dm_plotter", out("dm_plotter"))

# Cash bundle: a banded stack of notes, 0.08 x 0.16 x 0.03.
p = mk.fresh()
note = mk.mat("cn_note", (0.55, 0.65, 0.48), 0.8)
edge = mk.mat("cn_edge", (0.85, 0.87, 0.8), 0.9)
band = mk.mat("cn_band", (0.85, 0.7, 0.4), 0.7)
mk.box(p, (0, 0, 0.015), (0.075, 0.155, 0.028), edge)
mk.box(p, (0, 0, 0.0295), (0.074, 0.154, 0.002), note)
mk.box(p, (0, 0, 0.0005), (0.074, 0.154, 0.002), note)
mk.box(p, (0, 0, 0.015), (0.077, 0.03, 0.031), band)
mk.finish(p, "dm_cashbundle", out("dm_cashbundle"))

# Low two-drawer file cabinet: 0.41 deep (X) x 0.63 wide (Y) x 0.58 high, drawers face -X.
p = mk.fresh()
steel = mk.mat("fc_steel", (0.52, 0.54, 0.52), 0.5, 0.4)
dark = mk.mat("fc_dark", (0.18, 0.18, 0.2), 0.5, 0.6)
card = mk.mat("fc_card", (0.92, 0.9, 0.82), 0.8)
mk.box(p, (0, 0, 0.29), (0.41, 0.63, 0.58), steel)
for i in range(2):
    z = 0.15 + i * 0.27
    mk.box(p, (-0.208, 0, z), (0.012, 0.6, 0.25), steel)
    mk.box(p, (-0.22, 0, z + 0.04), (0.02, 0.14, 0.022), dark)
    mk.box(p, (-0.216, 0, z + 0.085), (0.004, 0.07, 0.035), card)
mk.box(p, (0, 0, 0.585), (0.41, 0.63, 0.01), dark)
mk.finish(p, "dm_filecabinetlow", out("dm_filecabinetlow"))

# Propeller engine (a bolted-down motor turning a fan): 0.53 x 0.51 x 0.64, three-blade propeller on the -X end.
p = mk.fresh()
iron = mk.mat("pe_iron", (0.28, 0.3, 0.27), 0.6, 0.6)
paint = mk.mat("pe_paint", (0.45, 0.13, 0.1), 0.6, 0.2)
blade = mk.mat("pe_blade", (0.55, 0.56, 0.55), 0.4, 0.8)
mk.box(p, (0.05, 0, 0.03), (0.45, 0.42, 0.06), iron)
mk.box(p, (0.1, 0, 0.2), (0.3, 0.3, 0.28), paint)
mk.cyl(p, (0.05, 0, 0.26), 0.14, 0.34, paint, verts=18, rot=(0, PI / 2, 0))
for i in range(6):
    mk.cyl(p, (-0.05 + i * 0.045, 0, 0.26), 0.16, 0.012, iron, verts=18, rot=(0, PI / 2, 0))
mk.cyl(p, (-0.16, 0, 0.26), 0.03, 0.12, iron, verts=10, rot=(0, PI / 2, 0))
mk.cyl(p, (-0.22, 0, 0.26), 0.05, 0.06, blade, verts=14, rot=(0, PI / 2, 0))
for i in range(3):
    a = i * 2 * PI / 3
    mk.box(p, (-0.22, 0.17 * math.cos(a), 0.26 + 0.17 * math.sin(a)), (0.012, 0.09, 0.26), blade, rot=(a + PI / 2, 0.35, 0))
mk.box(p, (0.24, 0, 0.42), (0.08, 0.14, 0.06), iron)
lift(p)
mk.finish(p, "dm_propellerengine", out("dm_propellerengine"))

# Crate stack: two 1.0 m crates side by side and one on top, 2.06 x 2.96 x 2.0 overall.
p = mk.fresh()
wood = mk.mat("cr_wood", (0.6, 0.45, 0.28), 0.85)
batten = mk.mat("cr_batten", (0.45, 0.32, 0.19), 0.85)
crate(p, (-0.52, -0.95, 0.5), (1.02, 1.02, 1.0), wood, batten)
crate(p, (0.52, -0.9, 0.5), (1.02, 1.1, 1.0), wood, batten)
crate(p, (-0.5, 0.35, 0.5), (1.0, 1.25, 1.0), wood, batten)
crate(p, (0.0, -0.6, 1.5), (1.0, 1.0, 1.0), wood, batten)
crate(p, (0.6, 0.45, 0.4), (0.8, 0.8, 0.8), wood, batten)
crate(p, (-0.4, 1.12, 0.35), (0.7, 0.7, 0.7), wood, batten)
mk.finish(p, "dm_cratestack", out("dm_cratestack"))

# Money pallet: a wooden pallet stacked with wrapped cash bricks under two straps, 1.2 x 1.2 x 1.23.
p = mk.fresh()
wood = mk.mat("mp_wood", (0.62, 0.48, 0.3), 0.85)
cash = mk.mat("mp_cash", (0.5, 0.6, 0.45), 0.7)
wrap = mk.mat("mp_wrap", (0.78, 0.82, 0.78), 0.2)
strap = mk.mat("mp_strap", (0.1, 0.1, 0.12), 0.6)
for i in range(5):
    mk.box(p, (0, -0.55 + i * 0.275, 0.13), (1.2, 0.1, 0.02), wood)
for i in range(3):
    mk.box(p, (-0.55 + i * 0.55, 0, 0.07), (0.1, 1.2, 0.1), wood)
mk.box(p, (0, 0, 0.01), (1.2, 1.2, 0.02), wood)
mk.box(p, (0, 0, 0.68), (1.14, 1.14, 1.08), wrap)
for k in range(6):
    for i in range(4):
        for j in range(4):
            mk.box(p, (-0.42 + i * 0.28, -0.42 + j * 0.28, 0.23 + k * 0.18), (0.27, 0.27, 0.17), cash)
for s in (-1, 1):
    mk.box(p, (s * 0.3, 0, 1.225), (0.04, 1.16, 0.008), strap)
    mk.box(p, (s * 0.3, -0.576, 0.68), (0.04, 0.008, 1.1), strap)
    mk.box(p, (s * 0.3, 0.576, 0.68), (0.04, 0.008, 1.1), strap)
mk.finish(p, "dm_moneypallet", out("dm_moneypallet"))

# Case of beer: a printed cardboard case with hand holes, 0.23 x 0.33 x 0.21.
p = mk.fresh()
card = mk.mat("bc_card", (0.75, 0.6, 0.38), 0.85)
print_ = mk.mat("bc_print", (0.1, 0.25, 0.55), 0.7)
gold = mk.mat("bc_gold", (0.85, 0.7, 0.2), 0.5)
dark = mk.mat("bc_dark", (0.1, 0.08, 0.06), 0.9)
mk.box(p, (0, 0, 0.105), (0.23, 0.33, 0.21), card)
mk.box(p, (0, 0, 0.09), (0.232, 0.332, 0.11), print_)
mk.box(p, (-0.117, 0, 0.09), (0.002, 0.18, 0.05), gold)
mk.box(p, (0.117, 0, 0.09), (0.002, 0.18, 0.05), gold)
for s in (-1, 1):
    mk.box(p, (0, s * 0.166, 0.175), (0.08, 0.002, 0.022), dark)
mk.finish(p, "dm_beercase", out("dm_beercase"))

# Box stack: taped cardboard boxes of three sizes, 1.29 x 1.33 x 1.23.
p = mk.fresh()
card = mk.mat("bs_card", (0.72, 0.56, 0.36), 0.85)
card2 = mk.mat("bs_card2", (0.64, 0.5, 0.32), 0.85)
tape = mk.mat("bs_tape", (0.85, 0.75, 0.55), 0.4)
cardboard(p, (-0.3, -0.33, 0.25), (0.6, 0.62, 0.5), card, tape)
cardboard(p, (0.33, -0.3, 0.22), (0.58, 0.68, 0.44), card2, tape)
cardboard(p, (-0.28, 0.35, 0.22), (0.66, 0.6, 0.44), card2, tape)
cardboard(p, (0.35, 0.36, 0.3), (0.56, 0.58, 0.6), card, tape)
cardboard(p, (-0.25, -0.2, 0.72), (0.56, 0.6, 0.44), card, tape)
cardboard(p, (0.3, 0.2, 0.82), (0.5, 0.52, 0.4), card2, tape)
cardboard(p, (-0.15, 0.3, 0.6), (0.44, 0.4, 0.32), card, tape)
cardboard(p, (0.0, -0.1, 1.08), (0.4, 0.42, 0.3), card2, tape)
lift(p)
mk.finish(p, "dm_boxstack", out("dm_boxstack"))

# Exit sign: a lit box 0.42 x 0.12 x 0.26, green panel on both faces with a running-figure plate.
p = mk.fresh()
case = mk.mat("ex_case", (0.88, 0.88, 0.86), 0.5)
green = mk.mat("ex_green", (0.1, 0.7, 0.3), 0.3)
white = mk.mat("ex_white", (0.95, 0.98, 0.95), 0.3)
mk.box(p, (0, 0, 0.13), (0.42, 0.1, 0.26), case)
for s in (-1, 1):
    mk.box(p, (0, s * 0.051, 0.13), (0.38, 0.004, 0.2), green)
    mk.box(p, (-0.1, s * 0.0535, 0.13), (0.07, 0.002, 0.13), white)
    mk.box(p, (0.07, s * 0.0535, 0.13), (0.17, 0.002, 0.03), white)
mk.box(p, (0, 0, 0.262), (0.1, 0.06, 0.008), case)
mk.finish(p, "dm_exitsign", out("dm_exitsign"))

# Lab jar: a glass jar with a screw lid and a label, 0.12 across x 0.2 high.
p = mk.fresh()
glass = mk.mat("lj_glass", (0.7, 0.82, 0.8), 0.1, 0.1)
liquid = mk.mat("lj_liquid", (0.6, 0.65, 0.3), 0.3)
lid = mk.mat("lj_lid", (0.2, 0.2, 0.22), 0.5, 0.5)
label = mk.mat("lj_label", (0.92, 0.9, 0.82), 0.8)
mk.cyl(p, (0, 0, 0.085), 0.06, 0.17, glass, verts=20)
mk.cyl(p, (0, 0, 0.06), 0.057, 0.11, liquid, verts=20)
mk.cyl(p, (0, 0, 0.18), 0.045, 0.02, glass, verts=20)
mk.cyl(p, (0, 0, 0.195), 0.05, 0.012, lid, verts=20)
mk.box(p, (0, -0.058, 0.09), (0.05, 0.006, 0.05), label)
mk.finish(p, "dm_labjar", out("dm_labjar"))
