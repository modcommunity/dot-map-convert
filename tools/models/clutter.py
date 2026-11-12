"""Small clutter and rooftop/industrial fittings, CC0, for `rules/models/categories.tsv`: keyboard, milk carton, wall
electrical cabinet, saw blade, parts bin, driftwood heaps, rubbish heap, cable bundle, roof antenna, truss, vents, caged
lamp cluster.

blender -b --factory-startup --python clutter.py -- outdir
Writes dm_keyboard, dm_milkcarton, dm_electricalbox, dm_sawblade, dm_partsbin, dm_driftwood1..3, dm_trashcluster,
dm_wirebundle, dm_antenna, dm_truss, dm_ventgrille, dm_roofvent, dm_ductrun and dm_lampcluster into outdir. Blender Z is up;
X is the length, Y the depth; origin on the floor, centred. Plain colour materials.
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


def lift(parts):
    """Put the lowest point on z = 0."""
    bpy.context.view_layer.update()
    low = min((o.matrix_world @ v.co).z for o in parts for v in o.data.vertices)
    for o in parts:
        o.location.z -= low


# Keyboard: 0.45 x 0.15 x 0.03.
p = mk.fresh()
body = mk.mat("kb_body", (0.62, 0.62, 0.58), 0.6)
key = mk.mat("kb_key", (0.2, 0.2, 0.22), 0.5)
mk.box(p, (0, 0, 0.012), (0.45, 0.15, 0.024), body)
for r in range(4):
    for c in range(14):
        if r == 0 and 3 <= c <= 9:
            continue
        mk.box(p, (-0.2 + c * 0.0305, -0.05 + r * 0.032, 0.03), (0.026, 0.026, 0.012), key)
mk.box(p, (0, -0.05, 0.03), (0.2, 0.026, 0.012), key)
mk.finish(p, "dm_keyboard", out("dm_keyboard"))

# Milk carton: square body under a gable top. 0.1 x 0.1 x 0.30.
p = mk.fresh()
white = mk.mat("carton_white", (0.9, 0.9, 0.88), 0.7)
blue = mk.mat("carton_blue", (0.15, 0.3, 0.7), 0.7)
mk.box(p, (0, 0, 0.1), (0.1, 0.1, 0.2), white)
mk.box(p, (0, 0, 0.1), (0.102, 0.102, 0.06), blue)
mk.box(p, (-0.025, 0, 0.225), (0.07, 0.1, 0.014), white, rot=(0, -0.9, 0))
mk.box(p, (0.025, 0, 0.225), (0.07, 0.1, 0.014), white, rot=(0, 0.9, 0))
mk.box(p, (0, 0, 0.285), (0.012, 0.1, 0.03), white)
mk.finish(p, "dm_milkcarton", out("dm_milkcarton"))

# Wall electrical cabinet: 4.7 x 0.24 x 2.05, door seams, handles, warning plates.
p = mk.fresh()
grey = mk.mat("cab_grey", (0.55, 0.57, 0.55), 0.6, 0.3)
dark = mk.mat("cab_dark", (0.2, 0.2, 0.22), 0.6, 0.4)
warn = mk.mat("cab_warn", (0.85, 0.7, 0.1), 0.5)
W, H, D = 4.7, 2.05, 0.24
mk.box(p, (0, 0, H / 2), (W, D, H), grey)
mk.box(p, (0, 0, 0.06), (W + 0.04, D + 0.04, 0.12), dark)
for i in range(5):
    x = -W / 2 + (i + 0.5) * W / 5
    mk.box(p, (x, -D / 2 - 0.01, H * 0.55), (W / 5 - 0.08, 0.02, H * 0.8), grey)
    mk.box(p, (x + W / 12, -D / 2 - 0.03, H * 0.55), (0.04, 0.04, 0.22), dark)
    mk.box(p, (x, -D / 2 - 0.025, H * 0.9), (0.18, 0.01, 0.12), warn)
mk.finish(p, "dm_electricalbox", out("dm_electricalbox"))

# Saw blade: flat toothed disc with a hub, 0.69 across.
p = mk.fresh()
steel = mk.mat("saw_steel", (0.6, 0.6, 0.63), 0.35, 0.8)
mk.cyl(p, (0, 0, 0.0075), 0.32, 0.015, steel, verts=32)
for i in range(24):
    a = i * 2 * PI / 24
    mk.box(p, (0.335 * math.cos(a), 0.335 * math.sin(a), 0.0075), (0.05, 0.02, 0.015), steel, rot=(0, 0, a + 0.5))
mk.cyl(p, (0, 0, 0.0095), 0.05, 0.019, mk.mat("saw_hub", (0.25, 0.25, 0.27), 0.6, 0.6), verts=12)
mk.finish(p, "dm_sawblade", out("dm_sawblade"))

# Parts bin: open tray of grey metal with bolts and brackets. 0.45 x 0.22 x 0.25.
p = mk.fresh()
tin = mk.mat("bin_tin", (0.4, 0.43, 0.45), 0.5, 0.6)
bits = mk.mat("bin_bits", (0.5, 0.35, 0.18), 0.6, 0.5)
mk.box(p, (0, 0, 0.012), (0.45, 0.22, 0.024), tin)
mk.box(p, (-0.213, 0, 0.125), (0.024, 0.22, 0.25), tin)
mk.box(p, (0.213, 0, 0.125), (0.024, 0.22, 0.25), tin)
mk.box(p, (0, 0.1, 0.125), (0.45, 0.024, 0.25), tin)
mk.box(p, (0, -0.1, 0.05), (0.45, 0.024, 0.1), tin)
rng = random.Random(5)
for _ in range(14):
    mk.box(p, (rng.uniform(-0.18, 0.18), rng.uniform(-0.08, 0.08), 0.045 + rng.random() * 0.03),
           (rng.uniform(0.03, 0.08), rng.uniform(0.02, 0.05), 0.03), bits, rot=(0, 0, rng.random() * PI))
mk.finish(p, "dm_partsbin", out("dm_partsbin"))


def driftwood(name, seed, n, length, spread):
    """Bleached logs and root balls lying across each other."""
    rng = random.Random(seed)
    p = mk.fresh()
    mats = [mk.mat("dw_a", (0.52, 0.47, 0.4), 0.95), mk.mat("dw_b", (0.42, 0.37, 0.31), 0.95)]
    for i in range(n):
        ln = length * (0.45 + 0.55 * rng.random())
        r = 0.07 + 0.08 * rng.random()
        mk.cyl(p, (rng.uniform(-spread[0], spread[0]), rng.uniform(-spread[1], spread[1]), r * (1.0 + 0.8 * (i % 2))),
               r, ln, mats[i % 2], verts=7,
               rot=(PI / 2, rng.uniform(-0.12, 0.12), PI / 2 + rng.uniform(-0.5, 0.5)))
    for _ in range(2):
        mk.cyl(p, (rng.uniform(-spread[0], spread[0]), rng.uniform(-spread[1], spread[1]), 0.2), 0.22, 0.2, mats[1], verts=7)
    lift(p)
    mk.finish(p, name, out(name))


driftwood("dm_driftwood1", 3, 9, 6.0, (1.6, 2.4))
driftwood("dm_driftwood2", 8, 7, 4.5, (1.2, 1.8))
driftwood("dm_driftwood3", 14, 5, 3.0, (0.8, 1.0))

# Rubbish heap: bags, boxes and cans, about 1 x 1 x 0.5.
p = mk.fresh()
rng = random.Random(9)
cols = [mk.mat("tr_%d" % i, c, 0.9) for i, c in enumerate(((0.1, 0.1, 0.12), (0.45, 0.4, 0.3), (0.55, 0.52, 0.5), (0.25, 0.35, 0.28)))]
for i in range(9):
    x, y = rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3)
    z = 0.12 + 0.2 * (1 - (x * x + y * y) ** 0.5 / 0.45)
    if i % 3 == 0:
        o = mk.cyl(p, (x, y, z), 0.17, 0.3, cols[0], verts=8)
        o.scale = (1.0, 1.0 + rng.random() * 0.3, 0.8)
    else:
        mk.box(p, (x, y, z), (rng.uniform(0.15, 0.3), rng.uniform(0.15, 0.3), rng.uniform(0.1, 0.22)), cols[i % 4],
               rot=(rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.random() * PI))
for _ in range(6):
    mk.cyl(p, (rng.uniform(-0.45, 0.45), rng.uniform(-0.45, 0.45), 0.05), 0.04, 0.11, cols[2], verts=8)
lift(p)
mk.finish(p, "dm_trashcluster", out("dm_trashcluster"))

# Cable bundle: three black cables hanging between clamps, 1.5 tall.
p = mk.fresh()
rubber = mk.mat("wire_rubber", (0.06, 0.06, 0.07), 0.6)
clamp = mk.mat("wire_clamp", (0.4, 0.42, 0.44), 0.5, 0.6)
for k, dx in enumerate((-0.03, 0.0, 0.03)):
    pts = [(dx + 0.02 * math.sin(t * 3 + k), 0.025 * k + 0.03 * math.sin(t * PI), 1.5 * (1 - t)) for t in [i / 6 for i in range(7)]]
    for a, b in zip(pts, pts[1:]):
        mk.beam(p, a, b, 0.035, rubber)
for z in (0.05, 0.75, 1.45):
    mk.box(p, (0, 0.03, z), (0.12, 0.09, 0.04), clamp)
mk.finish(p, "dm_wirebundle", out("dm_wirebundle"))

# Roof antenna: mast on a tripod with five dipole elements, 3 tall.
p = mk.fresh()
alu = mk.mat("ant_alu", (0.7, 0.72, 0.74), 0.4, 0.8)
mk.cyl(p, (0, 0, 1.5), 0.02, 3.0, alu, verts=8)
for i in range(3):
    a = i * 2 * PI / 3
    mk.beam(p, (0.2 * math.cos(a), 0.2 * math.sin(a), 0.0), (0, 0, 0.6), 0.02, alu)
for k, z in enumerate((1.6, 1.95, 2.25, 2.55, 2.85)):
    mk.box(p, (0, 0, z), (0.9 - 0.12 * k, 0.015, 0.015), alu)
mk.finish(p, "dm_antenna", out("dm_antenna"))

# Truss: square-section lattice girder, 2 m long, 0.4 x 0.4 section.
p = mk.fresh()
girder = mk.mat("truss_steel", (0.55, 0.56, 0.52), 0.6, 0.6)
L, S = 2.0, 0.2
for y in (-S, S):
    for z in (0.0, 2 * S):
        mk.box(p, (0, y, z + 0.02), (L, 0.04, 0.04), girder)
for i in range(8):
    x0, x1 = -L / 2 + i * L / 8, -L / 2 + (i + 1) * L / 8
    sgn = 1 if i % 2 == 0 else -1
    for y in (-S, S):
        mk.beam(p, (x0, y, S - S * sgn), (x1, y, S + S * sgn), 0.025, girder)
mk.finish(p, "dm_truss", out("dm_truss"))

# Wall vent grille: frame with louvres over a dark opening, 1.2 x 0.9.
p = mk.fresh()
vt = mk.mat("vent_tin", (0.62, 0.64, 0.64), 0.5, 0.6)
mk.box(p, (0, 0, 0.87), (1.2, 0.08, 0.06), vt)
mk.box(p, (0, 0, 0.03), (1.2, 0.08, 0.06), vt)
for x in (-0.585, 0.585):
    mk.box(p, (x, 0, 0.45), (0.03, 0.08, 0.9), vt)
mk.box(p, (0, 0.03, 0.45), (1.14, 0.02, 0.8), mk.mat("vent_dark", (0.08, 0.08, 0.09), 0.9))
for i in range(7):
    mk.box(p, (0, -0.01, 0.1 + i * 0.12), (1.14, 0.07, 0.025), vt, rot=(0.5, 0, 0))
mk.finish(p, "dm_ventgrille", out("dm_ventgrille"))

# Roof vent: round stack with a rain cap, 0.36 x 0.36 x 0.97.
p = mk.fresh()
vt = mk.mat("vent_tin", (0.62, 0.64, 0.64), 0.5, 0.6)
mk.cyl(p, (0, 0, 0.4), 0.12, 0.8, vt, verts=12)
mk.cyl(p, (0, 0, 0.06), 0.15, 0.12, vt, verts=12)
for sx in (-0.1, 0.1):
    for sy in (-0.1, 0.1):
        mk.box(p, (sx, sy, 0.84), (0.02, 0.02, 0.08), vt)
mk.cyl(p, (0, 0, 0.93), 0.18, 0.04, vt, verts=12)
mk.finish(p, "dm_roofvent", out("dm_roofvent"))

# Duct run: rectangular duct with flanges and a tap, 1.5 x 0.4 x 0.3.
p = mk.fresh()
vt = mk.mat("vent_tin", (0.62, 0.64, 0.64), 0.5, 0.6)
mk.box(p, (0, 0, 0.15), (1.5, 0.4, 0.3), vt)
for x in (-0.74, -0.25, 0.25, 0.74):
    mk.box(p, (x, 0, 0.15), (0.04, 0.44, 0.34), vt)
mk.cyl(p, (0.35, 0, 0.38), 0.1, 0.16, vt, verts=12)
mk.finish(p, "dm_ductrun", out("dm_ductrun"))

# Lamp cluster: three caged industrial lamps on a bar, 0.9 x 0.2 x 0.5.
p = mk.fresh()
cage = mk.mat("lamp_cage", (0.15, 0.15, 0.16), 0.6, 0.6)
glow = mk.mat("lamp_glow", (1.0, 0.92, 0.6), 0.3)
mk.box(p, (0, 0, 0.47), (0.9, 0.06, 0.06), cage)
for x in (-0.3, 0.0, 0.3):
    mk.cyl(p, (x, 0, 0.33), 0.1, 0.22, glow, verts=10)
    mk.cyl(p, (x, 0, 0.33), 0.115, 0.04, cage, verts=10)
    mk.cyl(p, (x, 0, 0.2), 0.115, 0.04, cage, verts=10)
    mk.cyl(p, (x, 0, 0.43), 0.05, 0.06, cage, verts=10)
mk.finish(p, "dm_lampcluster", out("dm_lampcluster"))
