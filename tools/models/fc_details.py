"""Door, wall, roof and room details for the FC, surf, hide-and-seek and wipeout worlds, CC0, for
`rules/models/categories.tsv`: door knob, lever handle, ceiling air diffuser, shuttered stone window, rebar stubs in a
concrete chunk, plastered dome, jellyfish, ribbed metal wall pillar, wall push button, stacked I-beams, roof beam grid,
railway track, crenellated wall cap, scattered book pile, long-case clock and a teleporter ring stack.

blender -b --factory-startup --python fc_details.py -- outdir
Writes one dm_<name>.glb per model into outdir (the names are the mk.finish calls below). Blender Z is up, X the length,
Y the depth; origin on the floor, centred. Each size is the original's measured box (rules/models/model_dims.tsv); the
picker turns a model a quarter at a time, so the longest flat side is laid along X. Plain colour materials.
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


def sphere(parts, c, r, m, scale=(1.0, 1.0, 1.0), half=False, seg=20):
    """A UV sphere; `half` keeps the top half only (the lower vertices are flattened onto the centre plane)."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=max(4, seg // 2), radius=r, location=c)
    o = bpy.context.object
    if half:
        for v in o.data.vertices:
            v.co.z = max(v.co.z, 0.0)
    o.scale = scale
    o.data.materials.append(m)
    parts.append(o)
    return o


def torus(parts, c, r, t, m, rot=(0.0, 0.0, 0.0), seg=24):
    bpy.ops.mesh.primitive_torus_add(major_segments=seg, minor_segments=8, major_radius=r, minor_radius=t, location=c,
                                     rotation=rot)
    o = bpy.context.object
    o.data.materials.append(m)
    parts.append(o)
    return o


def ibeam(parts, c, length, h, w, m, rot_z=0.0):
    """An I-section steel beam along X (turned by rot_z): two flanges and a web."""
    t = h * 0.12
    mk.box(parts, (c[0], c[1], c[2] + h / 2 - t / 2), (length, w, t), m, rot=(0, 0, rot_z))
    mk.box(parts, (c[0], c[1], c[2] - h / 2 + t / 2), (length, w, t), m, rot=(0, 0, rot_z))
    mk.box(parts, (c[0], c[1], c[2]), (length, t * 0.8, h - 2 * t), m, rot=(0, 0, rot_z))


# Door knob (cs_office/doorknob, doorknobb): an escutcheon plate on each face of a door with a round knob, 0.15 through
# the door, 0.07 wide, 0.14 high; the spindle runs through.
p = mk.fresh()
brass = mk.mat("dk_brass", (0.72, 0.56, 0.3), 0.3, 0.9)
dark = mk.mat("dk_dark", (0.05, 0.05, 0.05), 0.6)
for sx in (-1, 1):
    mk.box(p, (sx * 0.042, 0, 0.07), (0.006, 0.05, 0.14), brass)
    mk.cyl(p, (sx * 0.052, 0, 0.09), 0.016, 0.016, brass, verts=16, rot=(0, PI / 2, 0))
    mk.cyl(p, (sx * 0.064, 0, 0.09), 0.026, 0.018, brass, verts=20, rot=(0, PI / 2, 0))
    mk.box(p, (sx * 0.0455, 0, 0.035), (0.002, 0.008, 0.018), dark)
mk.cyl(p, (0, 0, 0.09), 0.005, 0.12, brass, verts=8, rot=(0, PI / 2, 0))
mk.finish(p, "dm_doorknob", out("dm_doorknob"))

# Lever door handle (de_train/de_train_doorhandle_01, nooze/handle): a back plate on the door and a lever 0.15 long
# from a round boss, 0.07 off the door, 0.05 high.
p = mk.fresh()
steel = mk.mat("dl_steel", (0.62, 0.63, 0.62), 0.3, 0.9)
mk.box(p, (-0.06, -0.03, 0.025), (0.03, 0.008, 0.05), steel)
mk.cyl(p, (-0.06, -0.01, 0.025), 0.012, 0.035, steel, verts=14, rot=(PI / 2, 0, 0))
mk.box(p, (0.012, 0.012, 0.025), (0.14, 0.016, 0.014), steel)
mk.cyl(p, (0.075, 0.012, 0.025), 0.009, 0.016, steel, verts=10, rot=(PI / 2, 0, 0))
mk.finish(p, "dm_doorlever", out("dm_doorlever"))

# Ceiling air diffuser (de_nuke_gohr/airduct_hvac_001_vent_32): a square face 0.61 across with four stepped louvre
# rings and a duct neck 0.23 high.
p = mk.fresh()
white = mk.mat("cd_white", (0.85, 0.86, 0.84), 0.5, 0.2)
grey = mk.mat("cd_grey", (0.3, 0.31, 0.32), 0.6, 0.4)
mk.box(p, (0, 0, 0.012), (0.61, 0.61, 0.024), white)
for i, s in enumerate((0.5, 0.39, 0.28, 0.17)):
    mk.box(p, (0, 0, 0.026 + i * 0.012), (s, s, 0.012), white if i % 2 == 0 else grey)
mk.box(p, (0, 0, 0.15), (0.32, 0.32, 0.16), grey)
mk.box(p, (0, 0, 0.225), (0.36, 0.36, 0.01), grey)
mk.finish(p, "dm_ceilingdiffuser", out("dm_ceilingdiffuser"))

# Shuttered window (de_cbble/cb_wndsng16): a stone surround 1.35 wide and 1.76 high round a recessed glazed casement,
# two plank shutters opened out at an angle (0.39 deep in all) and a sill.
p = mk.fresh()
stone = mk.mat("sw_stone", (0.62, 0.58, 0.5), 0.9)
wood = mk.mat("sw_wood", (0.36, 0.22, 0.12), 0.8)
frame = mk.mat("sw_frame", (0.85, 0.82, 0.74), 0.7)
pane = mk.mat("sw_pane", (0.12, 0.15, 0.18), 0.15, 0.3)
W, H = 0.8, 1.5
mk.box(p, (0, 0.06, 0.08), (1.0, 0.18, 0.08), stone)
mk.box(p, (0, 0.06, 0.12 + H + 0.06), (1.0, 0.14, 0.12), stone)
for sx in (-1, 1):
    mk.box(p, (sx * (W / 2 + 0.05), 0.06, 0.12 + H / 2), (0.1, 0.14, H), stone)
mk.box(p, (0, 0.1, 0.12 + H / 2), (W, 0.02, H), pane)
for x in (-W / 2 + 0.02, 0, W / 2 - 0.02):
    mk.box(p, (x, 0.09, 0.12 + H / 2), (0.04, 0.03, H), frame)
for z in (0.14, 0.12 + H * 0.5, 0.1 + H):
    mk.box(p, (0, 0.09, z), (W, 0.03, 0.04), frame)
ang = 1.12
sw = W / 2
for sx in (-1, 1):
    hx = sx * (W / 2 + 0.1)
    cx = hx + sx * math.cos(ang) * sw / 2
    cy = -0.01 - math.sin(ang) * sw / 2
    mk.box(p, (cx, cy, 0.12 + H / 2), (sw, 0.035, H - 0.04), wood, rot=(0, 0, -sx * ang))
    for z in (0.35, 0.12 + H - 0.23):
        mk.box(p, (cx, cy - 0.022, z), (sw * 0.95, 0.012, 0.07), wood, rot=(0, 0, -sx * ang))
mk.box(p, (0, -0.035, 0.03), (1.0, 0.08, 0.06), stone)
mk.finish(p, "dm_shutterwindow", out("dm_shutterwindow"))

# Rebar stubs (props_debris/rebar_cluster001a, 002a): a broken concrete lump with five bent reinforcing bars standing out
# of it, 0.94 high over 0.27 by 0.22.
p = mk.fresh()
conc = mk.mat("rb_conc", (0.55, 0.54, 0.5), 0.95)
rust = mk.mat("rb_rust", (0.38, 0.2, 0.1), 0.8, 0.5)
mk.box(p, (0, 0, 0.095), (0.24, 0.2, 0.14), conc, rot=(0.12, -0.08, 0.3))

bars = [((-0.07, -0.05), (-0.11, -0.08, 0.94)), ((0.04, -0.03), (0.1, -0.02, 0.8)),
        ((0.0, 0.05), (-0.02, 0.09, 0.88)), ((0.06, 0.06), (0.12, 0.1, 0.55)),
        ((-0.05, 0.03), (-0.12, 0.08, 0.66))]
for (x0, y0), (x1, y1, z1) in bars:
    mid = ((x0 + x1) / 2 + 0.02, (y0 + y1) / 2, z1 * 0.55)
    mk.beam(p, (x0, y0, 0.1), mid, 0.014, rust)
    mk.beam(p, mid, (x1, y1, z1), 0.014, rust)
mk.finish(p, "dm_rebar", out("dm_rebar"))

# Plastered dome (de_dust/du_dome_d2b): a round drum 3.16 across with a rim moulding and a half-sphere cap, 1.93 high,
# and a small finial.
p = mk.fresh()
plaster = mk.mat("dd_plaster", (0.79, 0.7, 0.54), 0.9)
trim = mk.mat("dd_trim", (0.66, 0.57, 0.42), 0.9)
R = 1.5
mk.cyl(p, (0, 0, 0.3), R, 0.6, plaster, verts=32)
mk.cyl(p, (0, 0, 0.62), R + 0.08, 0.08, trim, verts=32)
sphere(p, (0, 0, 0.62), R * 0.97, plaster, scale=(1.0, 1.0, 0.85), half=True, seg=32)
mk.cyl(p, (0, 0, 1.82), 0.06, 0.22, trim, verts=10)
sphere(p, (0, 0, 1.88), 0.07, trim, seg=10)
mk.finish(p, "dm_dustdome", out("dm_dustdome"))

# Jellyfish (jellyfish2): a translucent bell 0.25 across over trailing tentacles, 0.29 high in all.
p = mk.fresh()
bell = mk.mat("jf_bell", (0.85, 0.45, 0.75), 0.2)
tent = mk.mat("jf_tent", (0.95, 0.65, 0.85), 0.3)
sphere(p, (0, 0, 0.2), 0.125, bell, scale=(1.0, 1.0, 0.72), half=True, seg=20)
mk.cyl(p, (0, 0, 0.2), 0.122, 0.01, bell, verts=20)
for i in range(8):
    a = i * PI / 4
    r = 0.085
    mk.beam(p, (r * math.cos(a), r * math.sin(a), 0.2), (r * 1.2 * math.cos(a + 0.3), r * 1.2 * math.sin(a + 0.3), 0.0),
            0.008, tent)
mk.cyl(p, (0, 0, 0.13), 0.03, 0.14, tent, verts=8)
mk.finish(p, "dm_jellyfish", out("dm_jellyfish"))

# Ribbed metal wall pillar (props_combine/combineinnerwall001a): a dark armoured column 19 high and 5.8 by 5.6 with
# stepped plinth and cap, vertical ribs and lit seams.
p = mk.fresh()
armour = mk.mat("cw_armour", (0.16, 0.18, 0.2), 0.5, 0.7)
rib = mk.mat("cw_rib", (0.26, 0.28, 0.3), 0.45, 0.8)
glow = mk.mat("cw_glow", (0.3, 0.6, 0.9), 0.3)
mk.box(p, (0, 0, 0.6), (5.83, 5.65, 1.2), rib)
mk.box(p, (0, 0, 9.5), (4.8, 4.6, 17.0), armour)
mk.box(p, (0, 0, 18.4), (5.6, 5.4, 1.2), rib)
mk.box(p, (0, 0, 18.92), (4.6, 4.4, 0.2), armour)
for s in (-1, 1):
    for o in (-1.4, 0.0, 1.4):
        mk.box(p, (o, s * 2.42, 9.5), (0.45, 0.4, 16.0), rib)
        mk.box(p, (s * 2.5, o, 9.5), (0.4, 0.45, 16.0), rib)
    for o in (-0.7, 0.7):
        mk.box(p, (o, s * 2.63, 9.5), (0.08, 0.04, 14.0), glow)
        mk.box(p, (s * 2.71, o, 9.5), (0.04, 0.08, 14.0), glow)
mk.finish(p, "dm_metalpillar", out("dm_metalpillar"))

# Wall push button (props_citizen_tech/firetrap_button01a, firetrap_buttonpad): a steel back box 0.1 wide and 0.11 high,
# 0.07 off the wall, a guard ring and a red mushroom button.
p = mk.fresh()
steel = mk.mat("pb_steel", (0.45, 0.46, 0.45), 0.5, 0.7)
red = mk.mat("pb_red", (0.75, 0.08, 0.06), 0.4)
mk.box(p, (0, 0.012, 0.055), (0.1, 0.024, 0.11), steel)
mk.cyl(p, (0, -0.005, 0.055), 0.034, 0.012, steel, verts=16, rot=(PI / 2, 0, 0))
mk.cyl(p, (0, -0.02, 0.055), 0.012, 0.022, steel, verts=10, rot=(PI / 2, 0, 0))
mk.cyl(p, (0, -0.036, 0.055), 0.026, 0.016, red, verts=16, rot=(PI / 2, 0, 0))
mk.finish(p, "dm_pushbutton", out("dm_pushbutton"))

# Stacked I-beams (props_junk/ibeam01a_cluster01): five rusty steel beams 3.8 long laid two layers deep, 0.7 high and
# 0.52 across, the top ones skewed.
p = mk.fresh()
rust = mk.mat("ib_rust", (0.36, 0.22, 0.14), 0.8, 0.6)
grey = mk.mat("ib_grey", (0.33, 0.33, 0.32), 0.6, 0.7)
for i, y in enumerate((-0.18, 0.0, 0.18)):
    ibeam(p, (0, y, 0.15), 3.6, 0.3, 0.16, rust if i != 1 else grey)
ibeam(p, (0.05, -0.09, 0.45), 3.7, 0.3, 0.16, grey, rot_z=0.03)
ibeam(p, (-0.05, 0.1, 0.45), 3.55, 0.3, 0.16, rust, rot_z=-0.04)
for x in (-1.2, 1.2):
    mk.box(p, (x, 0, 0.62), (0.06, 0.5, 0.03), grey)
mk.finish(p, "dm_ibeamstack", out("dm_ibeamstack"))

# Roof beam grid (de_train/de_train_roofbeams_01): two steel I-beams each way crossing over a 2.47 square, 0.32 deep,
# with gusset plates at the crossings.
p = mk.fresh()
steel = mk.mat("rf_steel", (0.4, 0.4, 0.38), 0.6, 0.7)
L = 2.47
for o in (-0.62, 0.62):
    ibeam(p, (0, o, 0.24), L, 0.16, 0.12, steel)
    ibeam(p, (o, 0, 0.08), L, 0.16, 0.12, steel, rot_z=PI / 2)
for x in (-0.62, 0.62):
    for y in (-0.62, 0.62):
        mk.box(p, (x, y, 0.16), (0.2, 0.2, 0.02), steel)
mk.finish(p, "dm_roofbeams", out("dm_roofbeams"))

# Railway track (de_train/railroadtracks256): two rails on eleven timber sleepers 1.98 long on a ballast bed, 4.97 long
# and 0.23 high.
p = mk.fresh()
ballast = mk.mat("rt_ballast", (0.42, 0.4, 0.37), 1.0)
timber = mk.mat("rt_timber", (0.3, 0.22, 0.15), 0.9)
rail = mk.mat("rt_rail", (0.5, 0.48, 0.46), 0.35, 0.9)
L = 4.97
mk.box(p, (0, 0, 0.04), (L, 1.98, 0.08), ballast)
for i in range(11):
    mk.box(p, (-L / 2 + 0.23 + i * (L - 0.46) / 10, 0, 0.11), (0.24, 1.98, 0.06), timber)
for y in (-0.72, 0.72):
    mk.box(p, (0, y, 0.15), (L, 0.15, 0.02), rail)
    mk.box(p, (0, y, 0.19), (L, 0.02, 0.06), rail)
    mk.box(p, (0, y, 0.225), (L, 0.07, 0.01), rail)
mk.finish(p, "dm_railtrack", out("dm_railtrack"))

# Crenellated wall cap (de_dust/dustteeth_5): a plastered coping 8.35 long and 0.67 thick with a row of round-topped
# merlons, 1.18 high.
p = mk.fresh()
plaster = mk.mat("dt_plaster", (0.79, 0.7, 0.54), 0.9)
L = 8.35
mk.box(p, (0, 0, 0.12), (L, 0.67, 0.24), plaster)
n = 10
step = L / n
for i in range(n):
    x = -L / 2 + step * (i + 0.5)
    mk.box(p, (x, 0, 0.58), (step * 0.55, 0.6, 0.7), plaster)
    mk.cyl(p, (x, 0, 0.93), step * 0.275, 0.6, plaster, verts=12, rot=(PI / 2, 0, 0))
mk.finish(p, "dm_dustteeth", out("dm_dustteeth"))

# Book pile (props_manor/bookpile_01): old books strewn over 2.1 by 1.43, low stacks and a few lying open, 0.35 high.
p = mk.fresh()
cols = [(0.45, 0.12, 0.1), (0.15, 0.25, 0.18), (0.2, 0.18, 0.35), (0.5, 0.38, 0.2), (0.3, 0.2, 0.12)]
mats = [mk.mat(f"bp_{i}", c, 0.8) for i, c in enumerate(cols)]
paper = mk.mat("bp_paper", (0.86, 0.82, 0.7), 0.9)
stacks = [(-0.62, -0.3, 6), (0.1, 0.36, 4), (0.66, -0.18, 5), (-0.2, -0.1, 2), (0.5, 0.4, 3), (-0.66, 0.4, 2)]
k = 0
for x, y, n in stacks:
    z = 0.0
    for j in range(n):
        w, d, t = 0.22 + 0.04 * (k % 3), 0.16 + 0.03 * (k % 2), 0.045 + 0.01 * (k % 3)
        bx, by, a = x + 0.015 * ((k * 7) % 5 - 2), y + 0.012 * ((k * 3) % 5 - 2), 0.35 * ((k * 5) % 7 - 3) / 3
        mk.box(p, (bx, by, z + t / 2), (w, d, t), mats[k % 5], rot=(0, 0, a))
        mk.box(p, (bx + 0.005, by, z + t / 2), (w - 0.02, d - 0.012, t * 0.8), paper, rot=(0, 0, a))
        z += t
        k += 1
for x, y, a in ((-0.3, 0.5, 0.4), (0.3, -0.5, -0.7), (0.86, 0.2, 1.2), (-0.84, -0.05, 0.2)):
    mk.box(p, (x, y, 0.012), (0.42, 0.26, 0.024), paper, rot=(0, 0, a))
    mk.box(p, (x, y, 0.004), (0.44, 0.28, 0.008), mats[k % 5], rot=(0, 0, a))
    k += 1
mk.finish(p, "dm_bookpile", out("dm_bookpile"))

# Long-case clock (props_manor/grandfather_clock_01): a wooden case 2.63 high, 0.6 wide and 0.4 deep: plinth, waist with
# a glazed door and pendulum, a hood with a round dial and a rounded top.
p = mk.fresh()
wood = mk.mat("gc_wood", (0.3, 0.16, 0.08), 0.6)
dark = mk.mat("gc_dark", (0.14, 0.08, 0.04), 0.6)
dial = mk.mat("gc_dial", (0.9, 0.86, 0.75), 0.6)
brass = mk.mat("gc_brass", (0.75, 0.58, 0.3), 0.3, 0.9)
glass = mk.mat("gc_glass", (0.08, 0.08, 0.08), 0.1, 0.3)
mk.box(p, (0, 0, 0.25), (0.6, 0.4, 0.5), wood)
mk.box(p, (0, 0, 0.53), (0.56, 0.37, 0.06), dark)
mk.box(p, (0, 0, 1.2), (0.44, 0.3, 1.3), wood)
mk.box(p, (0, -0.152, 1.2), (0.3, 0.01, 1.0), glass)
mk.cyl(p, (0, -0.16, 1.0), 0.07, 0.01, brass, verts=16, rot=(PI / 2, 0, 0))
mk.box(p, (0, -0.16, 1.35), (0.012, 0.008, 0.6), brass)
mk.box(p, (0, 0, 1.88), (0.54, 0.36, 0.06), dark)
mk.box(p, (0, 0, 2.17), (0.52, 0.34, 0.52), wood)
mk.cyl(p, (0, -0.172, 2.17), 0.19, 0.01, dial, verts=28, rot=(PI / 2, 0, 0))
mk.box(p, (0, -0.18, 2.2), (0.012, 0.004, 0.14), dark)
mk.box(p, (0.04, -0.18, 2.17), (0.1, 0.004, 0.01), dark)
mk.box(p, (0, 0, 2.46), (0.6, 0.4, 0.06), dark)
mk.cyl(p, (0, 0, 2.49), 0.14, 0.36, wood, verts=16, rot=(PI / 2, 0, 0))
for sx in (-0.25, 0.25):
    mk.cyl(p, (sx, 0, 2.55), 0.03, 0.16, brass, verts=8)
mk.finish(p, "dm_grandfatherclock", out("dm_grandfatherclock"))

# Teleporter ring stack (props_combine/breentp_rings): three heavy metal rings 3.26 across on a round floor plate, held
# apart by four struts, 3.06 high.
p = mk.fresh()
metal = mk.mat("tr_metal", (0.3, 0.32, 0.34), 0.4, 0.8)
glow = mk.mat("tr_glow", (0.4, 0.75, 1.0), 0.3)
mk.cyl(p, (0, 0, 0.08), 1.63, 0.16, metal, verts=32)
mk.cyl(p, (0, 0, 0.17), 1.2, 0.02, glow, verts=32)
for z in (0.9, 1.8, 2.9):
    torus(p, (0, 0, z), 1.5, 0.13, metal, seg=32)
for i in range(4):
    a = i * PI / 2 + PI / 4
    mk.box(p, (1.5 * math.cos(a), 1.5 * math.sin(a), 1.5), (0.14, 0.14, 2.9), metal, rot=(0, 0, a))
mk.finish(p, "dm_tprings", out("dm_tprings"))
