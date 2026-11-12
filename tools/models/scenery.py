"""Scenery and street stand-ins, CC0, for `rules/models/categories.tsv`: train car, security guard (lying), water tower,
speaker cluster, roof dish, gutter drain, broken dock, indoor bin, three gravestones, coffin lid, control-room monitor, desk clock.

blender -b --factory-startup --python scenery.py -- outdir
Writes dm_traincar, dm_securityguard, dm_watertower, dm_speakercluster, dm_roofdish, dm_gutterdrain, dm_dockbroken,
dm_indoorbin, dm_gravestoneroof, dm_gravestonewide, dm_gravestonetall, dm_coffinlid, dm_controlmonitor and dm_deskclock into outdir.
Blender Z is up, X the length, Y the depth; origin on the floor, centred. Plain colour materials.
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


def sphere(parts, c, s, m, seg=14):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=max(6, seg // 2), radius=0.5, location=c)
    o = bpy.context.object
    o.scale = s
    o.data.materials.append(m)
    parts.append(o)
    return o


# Train car: a boxcar 2.48 wide (Y) x 3.7 high x 10.6 long (X). Chassis, bogies with four wheels each, boxed body, sliding doors, roof.
p = mk.fresh()
body = mk.mat("tc_body", (0.42, 0.2, 0.14), 0.8)
dark = mk.mat("tc_dark", (0.12, 0.12, 0.13), 0.6, 0.4)
roof = mk.mat("tc_roof", (0.5, 0.5, 0.5), 0.7, 0.3)
door = mk.mat("tc_door", (0.33, 0.16, 0.11), 0.8)
mk.box(p, (0, 0, 0.72), (10.6, 2.3, 0.28), dark)
for x in (-3.8, 3.8):
    mk.box(p, (x, 0, 0.5), (2.2, 2.0, 0.2), dark)
    for s in (-1, 1):
        for dx in (-0.7, 0.7):
            mk.cyl(p, (x + dx, s * 0.95, 0.4), 0.4, 0.12, dark, verts=14, rot=(PI / 2, 0, 0))
mk.box(p, (0, 0, 2.28), (10.4, 2.48, 2.56), body)
mk.box(p, (0, 0, 3.62), (10.5, 2.1, 0.16), roof)
for s in (-1, 1):
    mk.box(p, (0.6, s * 1.27, 2.2), (2.4, 0.06, 2.2), door)
    mk.box(p, (0.6, s * 1.31, 3.3), (2.6, 0.06, 0.08), dark)
    for x in range(-4, 5):
        mk.box(p, (x * 1.1 - 0.2, s * 1.26, 2.3), (0.08, 0.04, 2.5), dark)
for x in (-5.45, 5.45):
    mk.box(p, (x, 0, 0.9), (0.4, 0.3, 0.25), dark)
mk.finish(p, "dm_traincar", out("dm_traincar"))

# Security guard: a figure lying on his back, 1.1 long (X) x 0.55 wide x 0.55 high at the chest. Dark uniform, cap, boots.
p = mk.fresh()
uni = mk.mat("sg_uni", (0.15, 0.2, 0.32), 0.9)
skin = mk.mat("sg_skin", (0.75, 0.55, 0.45), 0.8)
boot = mk.mat("sg_boot", (0.07, 0.07, 0.07), 0.6)
mk.box(p, (0.0, 0, 0.2), (0.5, 0.4, 0.22), uni)
sphere(p, (-0.38, 0, 0.18), (0.2, 0.18, 0.2), skin)
mk.cyl(p, (-0.38, 0, 0.3), 0.11, 0.05, uni, verts=10)
for s in (-1, 1):
    mk.box(p, (0.5, s * 0.1, 0.1), (0.5, 0.14, 0.14), uni)
    mk.box(p, (0.78, s * 0.1, 0.1), (0.14, 0.1, 0.1), boot)
    mk.box(p, (0.1, s * 0.27, 0.13), (0.4, 0.1, 0.1), uni, rot=(0, 0, s * 0.3))
mk.finish(p, "dm_securityguard", out("dm_securityguard"))

# Water tower: 6 m wide round tank on a braced steel frame, 11 m tall, conical roof, ladder.
p = mk.fresh()
steel = mk.mat("wt_steel", (0.4, 0.28, 0.2), 0.7, 0.3)
tank = mk.mat("wt_tank", (0.5, 0.42, 0.34), 0.8)
for i in range(4):
    a = PI / 4 + i * PI / 2
    x, y = 2.1 * math.cos(a), 2.1 * math.sin(a)
    mk.beam(p, (x, y, 0), (x * 1.0, y * 1.0, 6.5), 0.22, steel)
for z in (2.5, 4.5):
    r = 2.1
    for i in range(4):
        a1, a2 = PI / 4 + i * PI / 2, PI / 4 + (i + 1) * PI / 2
        mk.beam(p, (r * math.cos(a1), r * math.sin(a1), z), (r * math.cos(a2), r * math.sin(a2), z + 1.8), 0.1, steel)
        mk.beam(p, (r * math.cos(a1), r * math.sin(a1), z + 1.8), (r * math.cos(a2), r * math.sin(a2), z), 0.1, steel)
mk.cyl(p, (0, 0, 8.0), 3.0, 3.0, tank, verts=20)
bpy.ops.mesh.primitive_cone_add(vertices=20, radius1=3.2, radius2=0.2, depth=1.6, location=(0, 0, 10.3))
c = bpy.context.object
c.data.materials.append(steel)
p.append(c)
mk.cyl(p, (0, 0, 0.5 + 5.2), 0.45, 10.4, steel, verts=8)
mk.box(p, (3.05, 0, 4.5), (0.08, 0.5, 9.0), steel)
mk.finish(p, "dm_watertower", out("dm_watertower"))

# Speaker cluster: a pole with four horn speakers fanned round its top, 1.2 m wide x 2.2 high.
p = mk.fresh()
gry = mk.mat("sc_grey", (0.45, 0.46, 0.45), 0.6, 0.4)
dk = mk.mat("sc_dark", (0.1, 0.1, 0.1), 0.7)
mk.cyl(p, (0, 0, 0.9), 0.05, 1.8, gry, verts=8)
for i in range(4):
    a = i * PI / 2 + PI / 4
    x, y = 0.3 * math.cos(a), 0.3 * math.sin(a)
    bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=0.28, radius2=0.1, depth=0.45, location=(x, y, 1.95),
                                    rotation=(0.0, PI / 2 - 0.15, a))
    h = bpy.context.object
    h.data.materials.append(gry)
    p.append(h)
    mk.cyl(p, (x * 1.2, y * 1.2, 1.95), 0.12, 0.12, dk, verts=8, rot=(0, PI / 2, a))
mk.finish(p, "dm_speakercluster", out("dm_speakercluster"))

# Roof dish: a 1.2 m satellite dish on a short mast, tilted up, with the feed arm.
p = mk.fresh()
wh = mk.mat("rd_white", (0.85, 0.85, 0.82), 0.5)
mk.box(p, (0, 0, 0.04), (0.5, 0.5, 0.08), mk.mat("rd_base", (0.3, 0.3, 0.3), 0.8))
mk.cyl(p, (0, 0, 0.4), 0.05, 0.7, wh, verts=8)
bpy.ops.mesh.primitive_cone_add(vertices=18, radius1=0.6, radius2=0.05, depth=0.2, location=(0, 0, 0.9), rotation=(0, -PI / 2 - 0.5, 0))
d = bpy.context.object
d.data.materials.append(wh)
p.append(d)
mk.beam(p, (-0.05, 0, 0.9), (-0.45, 0, 1.35), 0.03, wh)
mk.cyl(p, (-0.46, 0, 1.38), 0.04, 0.1, mk.mat("rd_lnb", (0.2, 0.2, 0.2), 0.6), verts=8)
mk.finish(p, "dm_roofdish", out("dm_roofdish"))

# Gutter drain: a 3 m downpipe against a wall (0.12 wide, 0.12 deep), brackets and an elbow at the foot.
p = mk.fresh()
zn = mk.mat("gd_zinc", (0.5, 0.52, 0.5), 0.5, 0.6)
mk.cyl(p, (0, 0, 1.6), 0.05, 2.8, zn, verts=10)
for z in (0.5, 1.5, 2.5):
    mk.box(p, (0, -0.04, z), (0.12, 0.04, 0.04), zn)
mk.cyl(p, (0, 0.05, 0.1), 0.05, 0.2, zn, verts=10, rot=(0.6, 0, 0))
mk.cyl(p, (0, 0, 3.05), 0.07, 0.1, zn, verts=10)
mk.finish(p, "dm_gutterdrain", out("dm_gutterdrain"))

# Broken dock: a 2.5 m (X) x 4 m (Y) planked jetty on piles, the far end snapped off, loose boards.
p = mk.fresh()
plank = mk.mat("db_plank", (0.38, 0.3, 0.22), 0.9)
post = mk.mat("db_post", (0.25, 0.2, 0.15), 0.9)
for i in range(14):
    L = 2.5 if i < 10 else 1.2
    y = -1.9 + i * 0.29
    off = 0.0 if i < 10 else 0.6
    mk.box(p, (off, y, 0.55 + (0 if i < 10 else (i - 9) * 0.05)), (L, 0.26, 0.05), plank, rot=(0.02 * (i - 6) if i > 9 else 0, 0, 0))
for s in (-1, 1):
    mk.box(p, (s * 1.1, -0.2, 0.46), (0.1, 3.6, 0.1), post)
    for y in (-1.8, -0.4, 0.9):
        mk.cyl(p, (s * 1.15, y, 0.0), 0.1, 1.4, post, verts=8)
mk.cyl(p, (1.15, 1.8, 0.35), 0.1, 0.9, post, verts=8, rot=(0.9, 0, 0))
mk.finish(p, "dm_dockbroken", out("dm_dockbroken"))

# Indoor bin: a steel station litter bin, 0.45 x 0.45 x 0.7, open top with a liner, band round the middle.
p = mk.fresh()
st = mk.mat("ib_steel", (0.32, 0.36, 0.34), 0.5, 0.5)
liner = mk.mat("ib_liner", (0.05, 0.05, 0.06), 0.9)
mk.cyl(p, (0, 0, 0.35), 0.22, 0.7, st, verts=14)
mk.cyl(p, (0, 0, 0.69), 0.19, 0.03, liner, verts=14)
mk.cyl(p, (0, 0, 0.35), 0.23, 0.05, mk.mat("ib_band", (0.6, 0.55, 0.2), 0.5, 0.5), verts=14)
mk.finish(p, "dm_indoorbin", out("dm_indoorbin"))


def grave(name, w, d, h, shape, col):
    p = mk.fresh()
    m = mk.mat(name + "_stone", col, 0.95)
    mk.box(p, (0, 0, 0.04), (w * 1.5, d * 2.2, 0.08), mk.mat(name + "_base", (col[0] * 0.8, col[1] * 0.8, col[2] * 0.8), 1.0))
    mk.box(p, (0, 0, h / 2), (w, d, h - 0.2), m)
    if shape == "round":
        mk.cyl(p, (0, 0, h - 0.1), w / 2, d, m, verts=14, rot=(PI / 2, 0, 0))
    elif shape == "roof":
        mk.box(p, (0, 0, h - 0.06), (w * 1.1, d * 1.2, 0.12), m)
        mk.beam(p, (-w * 0.55, 0, h - 0.12), (0, 0, h + 0.06), d * 0.9, m)
        mk.beam(p, (w * 0.55, 0, h - 0.12), (0, 0, h + 0.06), d * 0.9, m)
    else:
        mk.box(p, (0, 0, h - 0.18), (w * 0.5, d, 0.1), m)
        mk.box(p, (0, 0, h - 0.4), (w * 1.6, d, 0.14), m)
    mk.finish(p, name, out(name))


# Gravestone, 0.16 wide x 0.77 high x 0.73 deep with roof; wide slab 0.39 x 0.68 x 1.06 ; tall cross-topped stone 0.8 high.
grave("dm_gravestoneroof", 0.5, 0.16, 0.77, "roof", (0.5, 0.5, 0.48))
grave("dm_gravestonewide", 1.0, 0.18, 0.68, "round", (0.55, 0.55, 0.52))
grave("dm_gravestonetall", 0.45, 0.14, 1.0, "cross", (0.45, 0.46, 0.45))

# Coffin lid piece: a 2.1 m splintered board, 0.4 wide at the shoulders tapering to 0.3, leaning, 0.4 high.
p = mk.fresh()
wd = mk.mat("cl_wood", (0.3, 0.2, 0.12), 0.85)
mk.box(p, (0, 0, 0.12), (2.1, 0.4, 0.05), wd, rot=(0.0, 0.16, 0))
mk.box(p, (-0.5, 0.0, 0.18), (0.8, 0.3, 0.04), wd, rot=(0, 0.1, 0.2))
mk.box(p, (0.2, 0.05, 0.3), (0.6, 0.06, 0.05), wd, rot=(0.7, 0.2, 0.0))
mk.finish(p, "dm_coffinlid", out("dm_coffinlid"))

# Control-room monitor: a CRT 0.6 wide x 0.5 high x 0.45 deep with a dark screen on a short neck.
p = mk.fresh()
case = mk.mat("cm_case", (0.55, 0.53, 0.48), 0.6)
scr = mk.mat("cm_screen", (0.05, 0.12, 0.1), 0.15)
mk.box(p, (0, 0, 0.03), (0.4, 0.3, 0.06), case)
mk.box(p, (0, 0, 0.1), (0.1, 0.1, 0.1), case)
mk.box(p, (0.0, 0.05, 0.3), (0.6, 0.35, 0.4), case)
mk.box(p, (0.0, 0.2, 0.3), (0.5, 0.06, 0.32), case)
mk.box(p, (0.0, -0.14, 0.3), (0.5, 0.02, 0.34), scr)
mk.finish(p, "dm_controlmonitor", out("dm_controlmonitor"))

# Desk clock: a 0.32 wide x 0.2 high angular digital clock on a foot.
p = mk.fresh()
cb = mk.mat("dc_case", (0.1, 0.1, 0.11), 0.5)
fc = mk.mat("dc_face", (0.9, 0.2, 0.1), 0.3)
mk.box(p, (0, 0, 0.1), (0.32, 0.1, 0.18), cb)
mk.box(p, (0, -0.052, 0.11), (0.26, 0.01, 0.1), fc)
mk.box(p, (0, 0.0, 0.01), (0.2, 0.12, 0.02), cb)
mk.finish(p, "dm_deskclock", out("dm_deskclock"))
