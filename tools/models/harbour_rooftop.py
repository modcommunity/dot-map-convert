"""Harbour, rooftop and fixture stand-ins, CC0, for `rules/models/categories.tsv`: the dock, crane and rooftop models a
--no-omit conversion keeps, which had only a flat generated block before.

blender -b --factory-startup --python harbour_rooftop.py -- outdir
Writes into outdir, each sized to the model it stands in for (metres, width x height x depth, Y up):
- dm_latticetower (5.4 x 9.6 x 5.4): a square steel crane tower, four legs, rings and cross bracing.
- dm_dockpileshort, dm_dockpile, dm_dockpiletall (0.32 m timber piles, 2.46, 4.9 and 7.93 m high, iron bands).
- dm_dockpilecluster (0.72 x 9.76 x 3.2) and dm_dockpileclustershort (0.57 x 4.89 x 3.19): a row of five piles with two wales on their face.
- dm_dockfendersquare (0.54 x 9.6 x 9.73), dm_dockfenderhalf (0.55 x 4.82 x 9.73), dm_dockfenderlong (0.76 x 9.79 x 19.49):
  a timber fender wall, vertical boards on horizontal wales, with hanging rubber tyres.
- dm_roofstackrow (1.43 x 1.46 x 7.76): four short flue stacks on a plinth.
- dm_roofdome (3.97 x 2.48 x 3.97): a dome on a low drum.
- dm_trackmarker (5.67 x 0.26 x 0.3): a striped concrete sleeper.
- dm_sprinklerpipe (0.12 x 0.41 x 9.78): a ceiling pipe run on hangers with drop heads; it hangs from its top.
- dm_linecrossarm (0.07 x 0.23 x 1.11): a pole cross-arm with three insulators.
- dm_lever (0.3 x 1.0 x 0.3): a control lever on a base box.
- dm_rooftophvac (12.2 x 5.6 x 6.2): a rooftop plant cluster, two air handlers, a fan box, ducts, a flue and a railing.
Origin on the floor, centred. Plain colour materials.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import modelkit as mk  # noqa: E402

outdir = sys.argv[sys.argv.index("--") + 1]


def out(name):
    return f"{outdir}/{name}.glb"


def sphere(parts, c, r, m, scale=(1.0, 1.0, 1.0), half=False):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=r, location=c)
    o = bpy.context.object
    if half:
        for v in o.data.vertices:
            v.co.z = max(v.co.z, 0.0)
    o.scale = scale
    o.data.materials.append(m)
    parts.append(o)
    return o


def torus(parts, c, r, t, m, rot=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_torus_add(major_segments=16, minor_segments=8, major_radius=r, minor_radius=t, location=c, rotation=rot)
    o = bpy.context.object
    o.data.materials.append(m)
    parts.append(o)
    return o


def ground(parts):
    """Lift the parts so the lowest point is on z = 0."""
    bpy.context.view_layer.update()
    low = min((o.matrix_world @ v.co).z for o in parts for v in o.data.vertices)
    for o in parts:
        o.location.z -= low


# Lattice crane tower: four legs, a ring every 2.4 m, an X of braces on every face between rings, a cap plate.
p = mk.fresh()
paint = mk.mat("tower_paint", (0.62, 0.48, 0.12), 0.6, 0.4)
W, H, L = 5.4, 9.57, 0.28
legs = [(sx * (W / 2 - L / 2), sy * (W / 2 - L / 2)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
for x, y in legs:
    mk.box(p, (x, y, H / 2), (L, L, H), paint)
rings = [0.15 + i * (H - 0.45) / 4 for i in range(5)]
for z in rings:
    for i in range(4):
        a, b = legs[i], legs[(i + 1) % 4]
        mk.beam(p, (a[0], a[1], z), (b[0], b[1], z), 0.18, paint)
for z0, z1 in zip(rings, rings[1:]):
    for i in range(4):
        a, b = legs[i], legs[(i + 1) % 4]
        mk.beam(p, (a[0], a[1], z0), (b[0], b[1], z1), 0.12, paint)
        mk.beam(p, (b[0], b[1], z0), (a[0], a[1], z1), 0.12, paint)
mk.box(p, (0, 0, H - 0.15), (W, W, 0.3), paint)
mk.finish(p, "dm_latticetower", out("dm_latticetower"))


def pile(parts, x, y, h, r, wood, iron):
    mk.cyl(parts, (x, y, h / 2), r, h, wood, verts=12)
    mk.cyl(parts, (x, y, h + 0.04), r * 0.8, 0.08, wood, verts=12)
    for z in (h * 0.35, h * 0.8):
        mk.cyl(parts, (x, y, z), r * 1.06, 0.06, iron, verts=12)


for name, h in (("dm_dockpileshort", 2.46), ("dm_dockpile", 4.9), ("dm_dockpiletall", 7.93)):
    p = mk.fresh()
    wood = mk.mat("pile_wood", (0.33, 0.25, 0.16), 0.95)
    iron = mk.mat("pile_iron", (0.2, 0.19, 0.18), 0.7, 0.5)
    pile(p, 0, 0, h - 0.08, 0.16, wood, iron)
    mk.finish(p, name, out(name))

# Pile cluster: five piles in a row along the depth, lashed by two wales, the middle one tallest.
for name, h, w, d in (("dm_dockpilecluster", 9.76, 0.72, 3.2), ("dm_dockpileclustershort", 4.89, 0.57, 3.19)):
    p = mk.fresh()
    wood = mk.mat("pile_wood", (0.33, 0.25, 0.16), 0.95)
    iron = mk.mat("pile_iron", (0.2, 0.19, 0.18), 0.7, 0.5)
    r = 0.17
    ys = [-d / 2 + r + i * (d - 2 * r) / 4 for i in range(5)]
    for i, y in enumerate(ys):
        top = h - 0.08 - (0.0 if i == 2 else 0.25 if i in (1, 3) else 0.5)
        pile(p, -w / 2 + r, y, top, r, wood, iron)
    for z in (h * 0.45, h * 0.75):
        mk.box(p, (w / 2 - 0.1, 0, z), (0.2, d, 0.3), wood)
    mk.finish(p, name, out(name))

# Fender walls: vertical boards on three wales, tyres hung on the face. The face is +X, the wall runs along Y.
for name, t, h, d in (("dm_dockfendersquare", 0.54, 9.6, 9.73), ("dm_dockfenderhalf", 0.55, 4.82, 9.73), ("dm_dockfenderlong", 0.76, 9.79, 19.49)):
    p = mk.fresh()
    board = mk.mat("fender_wood", (0.3, 0.24, 0.17), 0.95)
    wale = mk.mat("fender_wale", (0.24, 0.19, 0.14), 0.95)
    rubber = mk.mat("fender_rubber", (0.06, 0.06, 0.06), 0.9)
    back = t * 0.3
    mk.box(p, (-t / 2 + back / 2, 0, h / 2), (back, d, h), wale)
    n = max(4, int(d / 0.6))
    bw = d / n
    for i in range(n):
        mk.box(p, (-t / 2 + back + 0.08, -d / 2 + bw * (i + 0.5), h / 2), (0.16, bw * 0.86, h), board)
    for z in (h * 0.2, h * 0.55, h * 0.88):
        mk.box(p, (-t / 2 + back + 0.16 + 0.08, 0, z), (0.16, d, 0.3), wale)
    tr = min(0.42, h * 0.08)
    for i in range(max(2, int(d / 3.2))):
        y = -d / 2 + (i + 0.5) * d / max(2, int(d / 3.2))
        torus(p, (t / 2 - tr * 0.28, y, h * 0.55 - 0.3 - tr), tr, tr * 0.28, rubber, rot=(0.0, math.pi / 2, 0.0))
    ground(p)
    mk.finish(p, name, out(name))

# Rooftop flue row: a plinth and four short stacks of two heights, capped.
p = mk.fresh()
brick = mk.mat("stack_brick", (0.42, 0.3, 0.24), 0.95)
metal = mk.mat("stack_metal", (0.3, 0.3, 0.3), 0.5, 0.7)
mk.box(p, (0, 0, 0.15), (1.43, 7.76, 0.3), brick)
for i, (y, hh) in enumerate(zip((-2.9, -1.0, 1.0, 2.9), (1.16, 0.9, 1.16, 0.9))):
    mk.cyl(p, (0, y, 0.3 + hh / 2), 0.48, hh, metal, verts=16)
    mk.cyl(p, (0, y, 0.3 + hh - 0.04), 0.56, 0.08, metal, verts=16)
mk.finish(p, "dm_roofstackrow", out("dm_roofstackrow"))

# Dome: a low drum, a flattened half sphere and a finial.
p = mk.fresh()
copper = mk.mat("dome_copper", (0.32, 0.5, 0.44), 0.55, 0.6)
stone = mk.mat("dome_stone", (0.62, 0.6, 0.55), 0.9)
metal = mk.mat("dome_metal", (0.3, 0.3, 0.3), 0.5, 0.7)
R = 3.97 / 2
mk.cyl(p, (0, 0, 0.35), R, 0.7, stone, verts=24)
sphere(p, (0, 0, 0.7), R * 0.97, copper, scale=(1.0, 1.0, 1.45 / (R * 0.97)), half=True)
mk.cyl(p, (0, 0, 2.15 + 0.16), 0.06, 0.32, metal, verts=8)
mk.finish(p, "dm_roofdome", out("dm_roofdome"))

# Track marker: a concrete sleeper with yellow and black stripes on its top.
p = mk.fresh()
conc = mk.mat("marker_concrete", (0.55, 0.54, 0.5), 0.95)
yellow = mk.mat("marker_yellow", (0.8, 0.62, 0.08), 0.7)
black = mk.mat("marker_black", (0.05, 0.05, 0.05), 0.7)
mk.box(p, (0, 0, 0.12), (5.67, 0.3, 0.24), conc)
for i in range(10):
    mk.box(p, (-5.67 / 2 + 0.28 + i * 0.567, 0, 0.25), (0.5, 0.26, 0.02), yellow if i % 2 == 0 else black)
mk.finish(p, "dm_trackmarker", out("dm_trackmarker"))

# Sprinkler pipe: a red pipe run on hangers from the ceiling, with drop heads.
p = mk.fresh()
red = mk.mat("sprinkler_red", (0.55, 0.1, 0.08), 0.5, 0.3)
brass = mk.mat("sprinkler_brass", (0.6, 0.48, 0.2), 0.4, 0.8)
metal = mk.mat("sprinkler_hanger", (0.3, 0.3, 0.3), 0.5, 0.7)
mk.cyl(p, (0, 0, 0.29), 0.05, 9.78, red, verts=10, rot=(math.pi / 2, 0, 0))
for y in (-4.4, -1.5, 1.5, 4.4):
    mk.box(p, (0, y, 0.37), (0.02, 0.02, 0.08), metal)
    mk.box(p, (0, y, 0.40), (0.12, 0.04, 0.02), metal)
for y in (-3.0, 0.0, 3.0):
    mk.cyl(p, (0, y, 0.15), 0.015, 0.2, red, verts=8)
    mk.cyl(p, (0, y, 0.03), 0.035, 0.06, brass, verts=10)
ground(p)
mk.finish(p, "dm_sprinklerpipe", out("dm_sprinklerpipe"))

# Cross-arm: a timber arm with three glass insulators on top.
p = mk.fresh()
arm = mk.mat("arm_wood", (0.35, 0.27, 0.18), 0.9)
glass = mk.mat("insulator_glass", (0.35, 0.55, 0.45), 0.2)
mk.box(p, (0, 0, 0.05), (0.07, 1.11, 0.1), arm)
for y in (-0.48, 0.0, 0.48):
    mk.cyl(p, (0, y, 0.1 + 0.065), 0.035, 0.13, glass, verts=10)
mk.finish(p, "dm_linecrossarm", out("dm_linecrossarm"))

# Lever: a base box, a slot plate, the arm leaning forward and a red knob.
p = mk.fresh()
grey = mk.mat("lever_grey", (0.33, 0.34, 0.33), 0.6, 0.5)
dark = mk.mat("lever_dark", (0.12, 0.12, 0.12), 0.6, 0.5)
knob = mk.mat("lever_knob", (0.6, 0.08, 0.06), 0.5)
mk.box(p, (0, 0, 0.12), (0.3, 0.3, 0.24), grey)
mk.box(p, (0, 0, 0.245), (0.08, 0.22, 0.01), dark)
mk.beam(p, (0, -0.02, 0.24), (0, 0.1, 0.92), 0.035, dark)
sphere(p, (0, 0.11, 0.95), 0.05, knob)
mk.finish(p, "dm_lever", out("dm_lever"))

# Rooftop plant: two air handler boxes with fan grilles, a fan housing, a duct run between them, a flue, a low railing.
p = mk.fresh()
casing = mk.mat("hvac_casing", (0.66, 0.67, 0.64), 0.6, 0.3)
grille = mk.mat("hvac_grille", (0.15, 0.16, 0.16), 0.7, 0.4)
duct = mk.mat("hvac_duct", (0.55, 0.57, 0.58), 0.4, 0.7)
rail = mk.mat("hvac_rail", (0.7, 0.58, 0.1), 0.6, 0.3)
grey = mk.mat("hvac_base", (0.4, 0.4, 0.39), 0.9)
metal = mk.mat("hvac_flue", (0.3, 0.3, 0.3), 0.5, 0.7)
mk.box(p, (0, 0, 0.1), (12.2, 6.1, 0.2), grey)
for x in (-3.6, 0.2):
    mk.box(p, (x, -1.2, 1.4), (3.2, 2.6, 2.4), casing)
    for fx in (-0.75, 0.75):
        mk.cyl(p, (x + fx, -1.2, 2.62), 0.62, 0.06, grille, verts=20)
mk.box(p, (4.3, 1.6, 1.0), (2.6, 2.0, 1.6), casing)
mk.cyl(p, (4.3, 1.6, 1.85), 0.7, 0.12, grille, verts=20)
mk.box(p, (-1.6, 1.4, 2.0), (8.2, 0.9, 0.9), duct)
for x in (-3.6, 0.2):
    mk.box(p, (x, 0.5, 2.0), (0.9, 1.1, 0.9), duct)
mk.box(p, (2.95, 1.4, 1.4), (0.9, 0.9, 2.1), duct)
mk.cyl(p, (5.3, -1.9, 2.8), 0.28, 5.2, metal, verts=14)
mk.cyl(p, (5.3, -1.9, 5.48), 0.4, 0.16, metal, verts=14)
for z in (0.65, 1.15):
    for a, b in (((-6.05, -3.0), (6.05, -3.0)), ((-6.05, 3.0), (6.05, 3.0)), ((-6.05, -3.0), (-6.05, 3.0)), ((6.05, -3.0), (6.05, 3.0))):
        mk.beam(p, (a[0], a[1], z), (b[0], b[1], z), 0.05, rail)
for x in (-6.05, -3.0, 0.0, 3.0, 6.05):
    for y in (-3.0, 3.0):
        mk.box(p, (x, y, 0.68), (0.05, 0.05, 0.96), rail)
mk.finish(p, "dm_rooftophvac", out("dm_rooftophvac"))
