"""Station, bridge and canal-dock models for gm_fork, CC0: the concrete bridge pier, the canal dock wrecks, the train-station
iron arches, wall lamp, signal post, finials, hip roof, striped awnings, a sign pole, a cable mount, a steel trestle
and a scaffold bay.

blender -b --factory-startup --python fork_station.py -- outdir
Writes dm_concretepier, dm_dockwreck, dm_dockwrecklong, dm_dockwrecksquare, dm_ironfinial, dm_stationfinial, dm_awningsmall, dm_awningwide,
dm_stationarch, dm_stationbracket, dm_stationlamp, dm_hiproof, dm_railsignal, dm_signpole, dm_cablemount, dm_steeltrestle and dm_scaffoldbay into outdir.
Blender Z is up; each model keeps the axes and extents of the original it stands for (modelmap fits size, centre and base).
Plain colour materials.
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


def cone(parts, c, r1, r2, h, m, verts=4, rot=(0.0, 0.0, PI / 4)):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=h, location=c)
    o = bpy.context.object
    o.rotation_euler = rot
    o.data.materials.append(m)
    parts.append(o)
    return o


def arch_web(parts, x, curve, top, post, m_rib, m_web, thick=0.24, web=0.06):
    """An iron arch panel in the Y-Z plane at x: a post (y0, y1) from the foot to the top band, the top band (y0, y1, z0, z1),
    the arched rib along `curve` [(y, z), ...] and a thin web filling from the rib up to the band."""
    (py0, py1, pz0), (ty0, ty1, tz0, tz1) = post, top
    mk.box(parts, (x, (py0 + py1) / 2, (pz0 + tz0) / 2), (thick, py1 - py0, tz0 - pz0), m_rib)
    mk.box(parts, (x, (ty0 + ty1) / 2, (tz0 + tz1) / 2), (thick * 0.9, ty1 - ty0, tz1 - tz0), m_rib)
    for (ya, za), (yb, zb) in zip(curve, curve[1:]):
        mk.beam(parts, (x, ya, za), (x, yb, zb), 0.14, m_rib)
        ym, zm = (ya + yb) / 2, (za + zb) / 2
        mk.box(parts, (x, ym, (zm + tz0) / 2), (web, abs(yb - ya) + 0.02, max(0.02, tz0 - zm)), m_web)
    # two round piercings in the web, drawn as dark discs on both faces
    return parts


def pierce(parts, x, y, z, r, m):
    mk.cyl(parts, (x, y, z), r, 0.08, m, verts=16, rot=(0, PI / 2, 0))


# Concrete bridge pier (medbridge_strut01): a 0.61 x 1.82 column 6.1 m high under a corbel seat that reaches 1.83 m out.
p = mk.fresh()
con = mk.mat("cp_concrete", (0.62, 0.61, 0.58), 0.95)
stain = mk.mat("cp_stain", (0.44, 0.43, 0.4), 0.95)
mk.box(p, (0.305, 0, -3.2), (0.61, 1.82, 5.8), con)
mk.box(p, (0.305, 0, -6.04), (0.66, 1.86, 0.12), stain)
mk.box(p, (0.915, 0, -0.15), (1.83, 1.82, 0.3), con)
mk.box(p, (0.915, 0, -0.33), (1.8, 1.7, 0.06), stain)
mk.beam(p, (0.45, 0, -1.9), (1.7, 0, -0.42), 0.5, con)
mk.box(p, (0.76, 0, -0.9), (0.3, 1.22, 1.1), con)
for z in (-4.88, -2.44):
    mk.box(p, (0.305, 0, z), (0.63, 1.84, 0.05), stain)
mk.finish(p, "dm_concretepier", out("dm_concretepier"))

# Iron finial (trainstation_ornament002): 0.26 square foot, a collar, a neck, a cap and a spike, 0.48 high.
p = mk.fresh()
iron = mk.mat("if_iron", (0.24, 0.16, 0.12), 0.6, 0.6)
mk.box(p, (0, 0, 0.075), (0.26, 0.26, 0.15), iron)
mk.box(p, (0, 0, 0.175), (0.28, 0.28, 0.05), iron)
mk.box(p, (0, 0, 0.235), (0.38, 0.38, 0.07), iron)
mk.cyl(p, (0, 0, 0.3), 0.07, 0.06, iron, verts=12)
mk.box(p, (0, 0, 0.35), (0.38, 0.38, 0.04), iron)
cone(p, (0, 0, 0.42), 0.12, 0.0, 0.12, iron, verts=8, rot=(0, 0, 0))
mk.finish(p, "dm_ironfinial", out("dm_ironfinial"))

# Station finial (trainstation_ornament001): a 0.76 square plinth, a stepped shaft and a pyramid tip, 1.9 high, rusty iron.
p = mk.fresh()
rust = mk.mat("sf_rust", (0.33, 0.2, 0.14), 0.75, 0.4)
dark = mk.mat("sf_dark", (0.2, 0.16, 0.13), 0.7, 0.4)
mk.box(p, (0, 0, 0.285), (0.76, 0.76, 0.57), rust)
mk.box(p, (0, 0, 0.6), (0.62, 0.62, 0.06), dark)
mk.box(p, (0, 0, 0.705), (0.54, 0.54, 0.15), rust)
cone(p, (0, 0, 0.96), 0.38, 0.48, 0.4, rust)
mk.box(p, (0, 0, 1.16), (0.68, 0.68, 0.06), dark)
cone(p, (0, 0, 1.46), 0.46, 0.3, 0.6, rust)
mk.box(p, (0, 0, 1.715), (0.38, 0.38, 0.07), dark)
cone(p, (0, 0, 1.825), 0.27, 0.0, 0.15, rust)
mk.finish(p, "dm_stationfinial", out("dm_stationfinial"))

def awning(name, width):
    """A striped canvas awning `width` wide (Y) curving from the wall top (x -0.27, z 0.4) out and down to x 0.27,
    z -0.26 (awning001a / 002a), blue and rust stripes, two side arms and a valance."""
    p = mk.fresh()
    blue = mk.mat(name + "_blue", (0.2, 0.27, 0.4), 0.9)
    rust = mk.mat(name + "_rust", (0.62, 0.32, 0.22), 0.9)
    arm = mk.mat(name + "_arm", (0.15, 0.15, 0.15), 0.5, 0.7)
    n_seg = 8
    pts = [(-0.24 + 0.5 * (1 - math.cos(a * PI / 2 / n_seg)), 0.38 - 0.62 * math.sin(a * PI / 2 / n_seg))
           for a in range(n_seg + 1)]
    half = width / 2
    stripes = max(4, int(round(width / 0.155)))
    for i in range(stripes):
        y = -half + (i + 0.5) * width / stripes
        m = blue if i % 2 == 0 else rust
        for (xa, za), (xb, zb) in zip(pts, pts[1:]):
            seg = math.hypot(xb - xa, zb - za)
            mk.box(p, ((xa + xb) / 2, y, (za + zb) / 2), (seg + 0.01, width / stripes, 0.012), m,
                   rot=(0, math.atan2(-(zb - za), xb - xa), 0))
    x_end, z_end = pts[-1]
    for i in range(stripes):
        mk.box(p, (x_end + 0.005, -half + (i + 0.5) * width / stripes, z_end - 0.06), (0.012, width / stripes, 0.12),
               rust if i % 2 == 0 else blue)
    for s in (-1, 1):
        mk.beam(p, (-0.27, s * (half + 0.01), -0.38), (x_end, s * (half + 0.01), z_end), 0.02, arm)
        mk.box(p, (-0.265, s * (half + 0.01), 0.0), (0.02, 0.03, 0.8), arm)
    mk.finish(p, name, out(name))


awning("dm_awningsmall", 1.24)   # awning002a
awning("dm_awningwide", 2.46)    # awning001a


# Station arch (column_arch001a): a cast-iron arch panel 4.88 long (Y) and 2.02 high between two posts, with a top band,
# the arched rib and a pierced web; pale grey paint.
p = mk.fresh()
paint = mk.mat("sa_paint", (0.66, 0.67, 0.66), 0.7, 0.3)
hole = mk.mat("sa_hole", (0.08, 0.08, 0.09), 0.9)
half = [(2.15, -0.48), (2.06, -0.19), (1.93, 0.09), (1.73, 0.32), (1.49, 0.52), (1.21, 0.66), (0.92, 0.74), (0.61, 0.78),
        (0.3, 0.8), (0.0, 0.8)]
for s in (-1, 1):
    curve = [(s * y, z) for y, z in half]
    arch_web(p, 0, curve, (-2.44 if s < 0 else 0.0, 0.0 if s < 0 else 2.44, 0.78, 1.01),
             (min(s * 2.44, s * 2.15), max(s * 2.44, s * 2.15), -1.01), paint, paint)
    for y, z, r in ((1.95, 0.52, 0.17), (1.35, 0.8 - 0.02, 0.0)):
        if r:
            pierce(p, 0, s * y, z, r, hole)
    mk.box(p, (0, s * 2.3, -0.95), (0.28, 0.34, 0.12), paint)
    mk.box(p, (0, s * 2.3, 0.85), (0.26, 0.32, 0.1), paint)
mk.finish(p, "dm_stationarch", out("dm_stationarch"))

# Station half-arch bracket (ceiling_arch001a): one post at y -0.91..-0.57, a top band out to y 0.99 and the quarter rib.
p = mk.fresh()
paint = mk.mat("sb_paint", (0.66, 0.67, 0.66), 0.7, 0.3)
hole = mk.mat("sb_hole", (0.08, 0.08, 0.09), 0.9)
curve = [(-0.63, -0.48), (-0.53, -0.19), (-0.4, 0.09), (-0.21, 0.32), (0.03, 0.52), (0.31, 0.66), (0.61, 0.74), (0.92, 0.77)]
arch_web(p, 0, curve, (-0.91, 0.99, 0.78, 1.01), (-0.91, -0.57, -1.01), paint, paint)
pierce(p, 0, -0.42, 0.52, 0.17, hole)
mk.box(p, (0, -0.74, -0.95), (0.26, 0.36, 0.12), paint)
mk.finish(p, "dm_stationbracket", out("dm_stationbracket"))

# Station wall lamp (column_light001a): a mounting box at the top, a drop rod with a cable, a cowl and a hanging lamp.
p = mk.fresh()
iron = mk.mat("sl_iron", (0.16, 0.16, 0.17), 0.5, 0.7)
glass = mk.mat("sl_glass", (0.95, 0.88, 0.65), 0.2)
mk.box(p, (0, 0.04, 0.945), (0.44, 0.98, 0.15), iron)
mk.box(p, (0, 0.04, 0.85), (0.3, 0.6, 0.05), iron)
mk.cyl(p, (0, -0.43, 0.42), 0.025, 0.86, iron, verts=8)
mk.cyl(p, (0.03, -0.45, -0.25), 0.012, 0.6, iron, verts=6, rot=(0.12, 0, 0))
cone(p, (0.02, -0.44, -0.33), 0.03, 0.1, 0.12, iron, verts=12, rot=(0, 0, 0))
mk.cyl(p, (0.02, -0.44, -0.45), 0.07, 0.14, glass, verts=12)
mk.cyl(p, (-0.05, -0.24, -0.8), 0.012, 0.5, iron, verts=6)
cone(p, (-0.05, -0.24, -0.92), 0.05, 0.14, 0.16, iron, verts=12, rot=(0, 0, 0))
mk.cyl(p, (-0.05, -0.24, -1.03), 0.09, 0.08, glass, verts=12)
mk.finish(p, "dm_stationlamp", out("dm_stationlamp"))

# Hip roof (dome005): a 7.44 square pyramid roof of rusty sheet with an eave band, four hip ridges and a finial, 2.95 high.
p = mk.fresh()
sheet = mk.mat("hr_sheet", (0.45, 0.2, 0.14), 0.8, 0.3)
ridge = mk.mat("hr_ridge", (0.3, 0.15, 0.11), 0.7, 0.4)
mk.box(p, (0, 0, 0.045), (7.44, 7.44, 0.09), ridge)
cone(p, (0, 0, 0.09 + 1.245), 3.66 * math.sqrt(2), 0.2, 2.49, sheet)
for sx in (-1, 1):
    for sy in (-1, 1):
        mk.beam(p, (sx * 3.66, sy * 3.66, 0.12), (sx * 0.15, sy * 0.15, 2.58), 0.14, ridge)
mk.cyl(p, (0, 0, 2.66), 0.2, 0.16, ridge, verts=12)
mk.box(p, (0, 0, 2.86), (0.6, 0.6, 0.18), ridge)
mk.finish(p, "dm_hiproof", out("dm_hiproof"))


def wreck(p, rnd, x0, x1, y0, y1, zdeck, rail_y, rail_x, rail_top, wood, dark):
    """A sunken, broken canal jetty: stringers along X, cross planks with gaps and a few tilted, a railing on one side."""
    for y in (y0 + 0.2, (y0 + y1) / 2, y1 - 0.2):
        mk.box(p, ((x0 + x1) / 2, y, zdeck - 0.16), (x1 - x0, 0.2, 0.22), dark, rot=(rnd.uniform(-0.03, 0.03), rnd.uniform(-0.04, 0.04), 0))
    x = x0 + 0.15
    while x < x1 - 0.1:
        if rnd.random() > 0.18:
            w = (y1 - y0) * rnd.uniform(0.55, 1.0)
            yc = y0 + w / 2 if rnd.random() < 0.5 else y1 - w / 2
            mk.box(p, (x, yc, zdeck + rnd.uniform(-0.04, 0.04)), (0.24, w, 0.06), wood,
                   rot=(rnd.uniform(-0.08, 0.08), rnd.uniform(-0.05, 0.05), rnd.uniform(-0.04, 0.04)))
        x += 0.28
    for i, x in enumerate(rail_x):
        mk.box(p, (x, rail_y, (zdeck + rail_top) / 2), (0.16, 0.16, rail_top - zdeck), dark, rot=(rnd.uniform(-0.06, 0.06), 0, 0))
    for zr in (rail_top - 0.1, (zdeck + rail_top) / 2):
        mk.box(p, ((rail_x[0] + rail_x[-1]) / 2, rail_y + 0.1, zr), (rail_x[-1] - rail_x[0] + 0.2, 0.06, 0.14), wood)
    for _ in range(3):
        xa = rnd.uniform(x0 + 0.5, x1 - 0.5)
        mk.beam(p, (xa, rnd.uniform(y0, y1), zdeck - 0.3), (xa + rnd.uniform(-1.2, 1.2), rnd.uniform(y0, y1), zdeck + rnd.uniform(0.5, 1.2)),
                0.12, wood)


# Canal dock wrecks (canal_dock02a / 03a): sunken jetty sections with a broken railing, weathered grey wood.
for name, x0, x1, rail_x, rail_y, top, zmin, seed in (
        ("dm_dockwreck", -3.6, 3.75, [-0.5, 0.7, 1.9, 3.1, 3.7], 1.3, 1.5, -1.36, 5),
        ("dm_dockwrecklong", -3.7, 5.2, [-3.0, -1.2, 0.3, 1.8, 3.4, 5.0], 1.0, 1.3, -1.64, 7)):
    p = mk.fresh()
    wood = mk.mat(name + "_wood", (0.36, 0.33, 0.29), 0.95)
    dark = mk.mat(name + "_dark", (0.22, 0.2, 0.18), 0.95)
    rnd = random.Random(seed)
    wreck(p, rnd, x0, x1, -1.96, 2.0, -1.0, rail_y, rail_x, top, wood, dark)
    mk.box(p, (x0 + 0.2, 1.0, (zmin - 1.0) / 2), (0.18, 0.18, abs(zmin + 1.0) + 0.2), dark)
    mk.finish(p, name, out(name))

# Broken dock section (dock_broken01a): a 9.7 square deck of planks in the X-Z plane (Y is its up), cross beams near one end,
# planks broken short and a few sprung loose.
p = mk.fresh()
wood = mk.mat("ds_wood", (0.36, 0.33, 0.29), 0.95)
dark = mk.mat("ds_dark", (0.22, 0.2, 0.18), 0.95)
rnd = random.Random(11)
x = -3.65
while x < 3.8:
    if rnd.random() > 0.12:
        z1 = 4.85 if rnd.random() < 0.75 else rnd.uniform(2.4, 4.4)
        z0 = -4.88 if rnd.random() < 0.55 else rnd.uniform(-2.0, 2.5)
        mk.box(p, (x, 1.45 + rnd.uniform(-0.03, 0.03), (z0 + z1) / 2), (0.26, 0.07, z1 - z0), wood,
               rot=(rnd.uniform(-0.02, 0.02), 0, rnd.uniform(-0.02, 0.02)))
    x += 0.3
for z, w in ((4.7, 9.7), (4.3, 9.6), (2.9, 7.6), (-4.82, 7.9)):
    mk.box(p, (0, 1.2, z), (w, 0.36, 0.22), dark)
for xs in (-3.7, -1.3, 1.2, 3.7):
    mk.box(p, (xs, -0.2, 4.5), (0.24, 3.2, 0.24), dark)
    mk.box(p, (xs, -0.2, 2.9), (0.22, 3.0, 0.22), dark)
for _ in range(4):
    xa = rnd.uniform(-3.5, 3.5)
    mk.beam(p, (xa, 1.3, rnd.uniform(-1, 3)), (xa + rnd.uniform(-1.5, 1.5), rnd.uniform(-1.7, 0.5), rnd.uniform(-3, 4.5)), 0.14, wood)
mk.finish(p, "dm_dockwrecksquare", out("dm_dockwrecksquare"))

# Rail signal post (light_signal001a): a 0.23 square lattice post 2.5 m to a grated platform with a hand rail, the
# signal head (a tall hooded box with three lamps) and a relay box on the post.
p = mk.fresh()
iron = mk.mat("rs_iron", (0.17, 0.17, 0.18), 0.6, 0.6)
grey = mk.mat("rs_grey", (0.5, 0.5, 0.48), 0.6, 0.4)
lamp = mk.mat("rs_lamp", (0.75, 0.2, 0.12), 0.3)
mk.box(p, (0.015, 0.06, -0.56), (0.23, 0.23, 2.54), iron)
for z in [-1.6 + 0.3 * i for i in range(8)]:
    mk.box(p, (0.015, -0.06, z), (0.25, 0.02, 0.08), grey)
mk.box(p, (0.015, 0.06, 0.73), (0.66, 1.0, 0.05), iron)
for x in (-0.31, 0.31):
    for y in (-0.42, 0.55):
        mk.cyl(p, (x, y, 1.2), 0.02, 0.9, grey, verts=6)
    mk.box(p, (x, 0.06, 1.63), (0.03, 1.0, 0.03), grey)
    mk.box(p, (x, 0.06, 1.2), (0.03, 1.0, 0.03), grey)
mk.box(p, (0.065, 0.45, 1.3), (0.3, 0.3, 1.1), iron)
mk.box(p, (0.065, 0.45, 1.88), (0.32, 0.32, 0.06), iron)
for z in (1.0, 1.3, 1.6):
    mk.cyl(p, (0.065, 0.62, z), 0.07, 0.06, lamp, verts=12, rot=(PI / 2, 0, 0))
    mk.box(p, (0.065, 0.67, z + 0.08), (0.18, 0.1, 0.02), iron)
mk.box(p, (0.015, -0.12, -0.9), (0.2, 0.12, 0.3), grey)
mk.finish(p, "dm_railsignal", out("dm_railsignal"))

# Sign pole (signpole001): a galvanised pipe 2.1 m high, 0.05 across, with a cap and two sign clamps.
p = mk.fresh()
galv = mk.mat("sp_galv", (0.55, 0.56, 0.55), 0.45, 0.8)
mk.cyl(p, (0, 0, 1.05), 0.024, 2.1, galv, verts=10)
mk.cyl(p, (0, 0, 2.09), 0.027, 0.02, galv, verts=10)
for z in (1.55, 1.95):
    mk.cyl(p, (0, 0, z), 0.027, 0.03, galv, verts=10)
mk.finish(p, "dm_signpole", out("dm_signpole"))

# Cable mount (mount_connection001a): a wall plate at x -0.52 with two arms out to an end plate at x 0.5 and a diagonal brace
# and drop rod, galvanised steel, 1.1 long.
p = mk.fresh()
steel = mk.mat("cm_steel", (0.48, 0.5, 0.5), 0.6, 0.6)
dark = mk.mat("cm_dark", (0.25, 0.2, 0.17), 0.7, 0.5)
mk.box(p, (-0.52, 0, 0.0), (0.06, 0.42, 0.82), steel)
mk.box(p, (0.0, 0, 0.33), (1.08, 0.08, 0.06), steel)
for y in (-0.29, 0.29):
    mk.box(p, (0.0, y, 0.27), (1.08, 0.06, 0.06), steel)
mk.box(p, (0.45, 0, 0.27), (0.12, 0.72, 0.1), steel)
mk.beam(p, (-0.5, 0, -0.34), (0.45, 0, 0.22), 0.06, steel)
mk.cyl(p, (-0.1, 0, -0.03), 0.02, 0.6, dark, verts=6)
mk.finish(p, "dm_cablemount", out("dm_cablemount"))

# Steel trestle (canal_bridge02): a riveted rail bridge 19.5 long (Y), 6.06 wide (X) and 5.49 high: two deep plate girders on
# top with cross ties, carried by three bents of two columns on concrete footings with X bracing; rusty steel.
p = mk.fresh()
rust = mk.mat("st_rust", (0.3, 0.19, 0.14), 0.75, 0.5)
blue = mk.mat("st_paint", (0.22, 0.25, 0.28), 0.7, 0.5)
tie = mk.mat("st_tie", (0.16, 0.15, 0.14), 0.85)
con = mk.mat("st_concrete", (0.6, 0.59, 0.56), 0.95)
L, W, H = 19.5, 6.06, 5.49
for s in (-1, 1):
    x = s * 2.55
    mk.box(p, (x, 0, H - 0.55), (0.12, L, 0.9), rust)          # girder web
    mk.box(p, (x, 0, H - 0.07), (0.5, L, 0.08), blue)          # top flange
    mk.box(p, (x, 0, H - 1.0), (0.5, L, 0.08), blue)           # bottom flange
    for i in range(14):
        y = -L / 2 + 0.6 + i * (L - 1.2) / 13
        mk.box(p, (x + s * 0.09, y, H - 0.55), (0.06, 0.12, 0.84), blue)   # web stiffeners
for i in range(13):
    y = -L / 2 + 0.75 + i * (L - 1.5) / 12
    mk.box(p, (0, y, H - 0.2), (W - 0.3, 0.42, 0.22), tie)
for y in (-L / 2 + 0.9, 0.0, L / 2 - 0.9):
    for s in (-1, 1):
        x = s * 2.55
        mk.box(p, (x, y, 0.35), (1.3, 1.3, 0.7), con)
        mk.box(p, (x, y, (0.7 + H - 1.04) / 2), (0.62, 0.62, H - 1.74), rust)
        mk.box(p, (x, y, H - 1.2), (0.8, 0.8, 0.2), blue)
        mk.box(p, (x, y, 0.78), (0.8, 0.8, 0.16), blue)
    mk.box(p, (0, y, H - 1.35), (5.0, 0.3, 0.5), rust)       # cap beam
    mk.box(p, (0, y, 1.3), (4.5, 0.24, 0.3), rust)            # lower strut
    mk.beam(p, (-2.25, y, 1.4), (2.25, y, H - 1.5), 0.18, blue)
    mk.beam(p, (2.25, y, 1.4), (-2.25, y, H - 1.5), 0.18, blue)
for s in (-1, 1):
    for ya, yb in ((-L / 2 + 0.9, 0.0), (0.0, L / 2 - 0.9)):
        mk.beam(p, (s * 2.55, ya, H - 1.25), (s * 2.55, yb, 1.4), 0.12, rust)
mk.finish(p, "dm_steeltrestle", out("dm_steeltrestle"))

# Scaffold bay (scaffolding01a): galvanised tube scaffolding 4.88 long (Y), 1.62 deep (X) and 2.7 high: four standards on base
# plates, ledgers and transoms at three lifts, a face brace and a plank deck with a toe board on top.
p = mk.fresh()
tube = mk.mat("sc_tube", (0.58, 0.6, 0.6), 0.45, 0.8)
wood = mk.mat("sc_plank", (0.55, 0.42, 0.26), 0.9)
hx, hy, H = 0.75, 2.38, 2.7
for x in (-hx, hx):
    for y in (-hy, hy):
        mk.cyl(p, (x, y, H / 2), 0.03, H, tube, verts=8)
        mk.box(p, (x, y, 0.01), (0.15, 0.15, 0.02), tube)
    for z in (0.15, 1.35, 2.5):
        mk.beam(p, (x, -hy - 0.05, z), (x, hy + 0.05, z), 0.05, tube)
    mk.beam(p, (x, -hy, 0.15), (x, hy, 2.5), 0.05, tube)
for y in (-hy, 0.0, hy):
    for z in (0.15, 1.35, 2.5):
        mk.beam(p, (-hx - 0.05, y, z), (hx + 0.05, y, z), 0.05, tube)
for i in range(5):
    x = -hx + 0.15 + i * (2 * hx - 0.3) / 4
    mk.box(p, (x, 0, 2.56), (0.28, 2 * hy + 0.2, 0.05), wood)
for x in (-hx - 0.02, hx + 0.02):
    mk.box(p, (x, 0, 2.66), (0.03, 2 * hy, 0.12), wood)
mk.finish(p, "dm_scaffoldbay", out("dm_scaffoldbay"))
