"""Wall fixtures, racks, rails and lift stand-ins, CC0, for `rules/models/categories.tsv`: door keypad, triangular wall
bracket, vertical wall pipe run, truck cab glass, freight lift cage, overhead line pole, long and double-rise handrails,
canal bridge railing, wooden shelving, pallet rack, plank wall with a window opening (narrow and wide).

blender -b --factory-startup --python detail_fixtures.py -- outdir
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


def glass(name, rgb):
    """A see-through pane: alpha blended, a little rough."""
    m = mk.mat(name, rgb, 0.1, 0.0)
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Alpha"].default_value = 0.35
    m.blend_method = "BLEND"
    return m


# Door keypad (props_lab/keypad): a wall box 0.125 wide, 0.03 deep, 0.22 high, a small screen and a 3 x 4 key grid.
p = mk.fresh()
body = mk.mat("kp_body", (0.62, 0.63, 0.6), 0.5, 0.4)
dark = mk.mat("kp_dark", (0.08, 0.09, 0.1), 0.4)
key = mk.mat("kp_key", (0.78, 0.78, 0.74), 0.5)
lit = mk.mat("kp_lit", (0.25, 0.75, 0.35), 0.3)
mk.box(p, (0, 0, 0.11), (0.125, 0.022, 0.22), body)
mk.box(p, (0, -0.012, 0.18), (0.09, 0.006, 0.04), dark)
mk.box(p, (0.035, -0.014, 0.18), (0.012, 0.004, 0.012), lit)
for r in range(4):
    for c in range(3):
        mk.box(p, ((c - 1) * 0.03, -0.013, 0.135 - r * 0.028), (0.022, 0.008, 0.02), key)
for sz in (-1, 1):
    mk.cyl(p, (0, 0.012, 0.11 + sz * 0.095), 0.006, 0.008, dark, verts=8, rot=(PI / 2, 0, 0))
mk.finish(p, "dm_keypad", out("dm_keypad"))

# Triangular wall bracket (props_wasteland/prison_bracket001a): a wall post 1.02 high, an arm 1.26 out at the top and a
# diagonal brace; angle iron 0.095 wide.
p = mk.fresh()
iron = mk.mat("wb_iron", (0.3, 0.29, 0.27), 0.7, 0.6)
L, H, t = 1.263, 1.017, 0.06
mk.box(p, (-L / 2 + t / 2, 0, H / 2), (t, 0.095, H), iron)
mk.box(p, (0, 0, H - t / 2), (L, 0.095, t), iron)
mk.beam(p, (-L / 2 + t, 0, t * 1.5), (L / 2 - 0.12, 0, H - t), t * 0.9, iron)
mk.box(p, (-L / 2 + 0.008, 0, H * 0.25), (0.016, 0.095, 0.16), iron)
mk.box(p, (-L / 2 + 0.008, 0, H * 0.8), (0.016, 0.095, 0.16), iron)
for x in (-0.2, 0.3):
    mk.box(p, (x, 0, H - t * 0.5), (0.05, 0.1, t * 1.15), iron)
mk.finish(p, "dm_wallbracket", out("dm_wallbracket"))

# Vertical wall pipe run (props_pipes/interiorpipecluster02a): four pipes of mixed bore 3.52 high over 1.18 of wall,
# 0.23 out, held by straps, one with a valve wheel.
p = mk.fresh()
pipe = mk.mat("wp_pipe", (0.45, 0.47, 0.46), 0.5, 0.6)
paint = mk.mat("wp_paint", (0.55, 0.2, 0.15), 0.6, 0.3)
strap = mk.mat("wp_strap", (0.22, 0.22, 0.23), 0.6, 0.7)
H = 3.52
runs = [(-0.46, 0.1, pipe), (-0.17, 0.07, paint), (0.1, 0.11, pipe), (0.42, 0.06, pipe)]
for x, r, m in runs:
    mk.cyl(p, (x, 0, H / 2), r, H, m, verts=14)
    for z in (0.3, H - 0.3):
        mk.cyl(p, (x, 0, z), r * 1.25, 0.06, strap, verts=14)
    for z in (0.9, 1.9, 2.9):
        mk.cyl(p, (x, 0, z), r * 1.18, 0.05, strap, verts=14)
for z in (1.1, 2.6):
    mk.box(p, (0, 0.1, z), (1.18, 0.03, 0.05), strap)
mk.cyl(p, (-0.17, -0.09, 1.4), 0.09, 0.03, paint, verts=12, rot=(PI / 2, 0, 0))
mk.box(p, (-0.17, -0.06, 1.4), (0.02, 0.06, 0.02), paint)
mk.finish(p, "dm_wallpiperun", out("dm_wallpiperun"))

# Truck cab glass (props/de_nuke/truck_nuke_glass): a raked windscreen across the 1.57 cab and two side windows along
# its 1.22 length, 0.65 high, in thin frames.
p = mk.fresh()
pane = glass("cg_glass", (0.55, 0.65, 0.7))
frame = mk.mat("cg_frame", (0.1, 0.1, 0.11), 0.5, 0.3)
L, W, H = 1.22, 1.574, 0.654
mk.box(p, (L / 2 - 0.12, 0, H / 2), (0.012, W - 0.06, H / math.cos(0.35)), pane, rot=(0, -0.35, 0))
for sy in (-1, 1):
    mk.box(p, (-0.06, sy * (W / 2 - 0.01), H / 2), (L - 0.36, 0.012, H - 0.04), pane)
    mk.box(p, (-0.06, sy * (W / 2 - 0.01), H - 0.015), (L - 0.34, 0.03, 0.03), frame)
    mk.box(p, (-0.06, sy * (W / 2 - 0.01), 0.015), (L - 0.34, 0.03, 0.03), frame)
    mk.box(p, (-L / 2 + 0.12, sy * (W / 2 - 0.01), H / 2), (0.04, 0.03, H), frame)
mk.box(p, (L / 2 - 0.235, 0, H - 0.015), (0.04, W, 0.03), frame)
mk.box(p, (L / 2 - 0.005, 0, 0.015), (0.04, W, 0.03), frame)
mk.finish(p, "dm_cabglass", out("dm_cabglass"))

# Freight lift cage (props_lab/freightelevator): a 3.28 x 2.78 steel floor, corner posts 3.31 high, mesh bars on three
# sides, a folding gate on the open side and a roof frame with the hoist beam.
p = mk.fresh()
steel = mk.mat("fe_steel", (0.32, 0.33, 0.32), 0.6, 0.7)
tread = mk.mat("fe_tread", (0.42, 0.42, 0.4), 0.5, 0.8)
yellow = mk.mat("fe_yellow", (0.8, 0.62, 0.1), 0.6, 0.2)
L, W, H = 3.28, 2.78, 3.31
mk.box(p, (0, 0, 0.1), (L, W, 0.2), steel)
mk.box(p, (0, 0, 0.205), (L - 0.1, W - 0.1, 0.01), tread)
for sx in (-1, 1):
    for sy in (-1, 1):
        mk.box(p, (sx * (L / 2 - 0.05), sy * (W / 2 - 0.05), H / 2), (0.1, 0.1, H), steel)
for z in (1.1, H - 0.05):
    for sy in (-1, 1):
        mk.box(p, (0, sy * (W / 2 - 0.05), z), (L, 0.08, 0.08), steel)
    mk.box(p, (-L / 2 + 0.05, 0, z), (0.08, W, 0.08), steel)
mk.box(p, (L / 2 - 0.05, 0, H - 0.05), (0.08, W, 0.08), steel)
for i in range(1, 16):
    x = -L / 2 + i * L / 16
    for sy in (-1, 1):
        mk.box(p, (x, sy * (W / 2 - 0.05), (0.2 + H) / 2), (0.02, 0.02, H - 0.2), steel)
for i in range(1, 14):
    y = -W / 2 + i * W / 14
    mk.box(p, (-L / 2 + 0.05, y, (0.2 + H) / 2), (0.02, 0.02, H - 0.2), steel)
for i in range(7):
    y = -W / 2 + 0.25 + i * (W - 0.5) / 6
    mk.box(p, (L / 2 - 0.05, y, 0.21 + 1.0), (0.03, 0.03, 1.9), yellow)
for z in (0.35, 1.0, 1.9):
    mk.box(p, (L / 2 - 0.05, 0, 0.21 + z), (0.04, W - 0.2, 0.05), yellow)
for i in range(1, 4):
    mk.box(p, (-L / 2 + i * L / 4, 0, H - 0.05), (0.08, W, 0.08), steel)
mk.box(p, (0, 0, H - 0.15), (L * 0.5, 0.2, 0.2), steel)
mk.box(p, (0, 0, H - 0.3), (0.3, 0.3, 0.2), steel)
mk.finish(p, "dm_freightelevator", out("dm_freightelevator"))

# Overhead line pole (props_trainstation/pole_448connection002b): an H-section steel pole 8.55 high on a plinth, a cross
# arm 0.83 across near the top with hanging insulators and a mid-height bracket.
p = mk.fresh()
steel = mk.mat("cp_steel", (0.28, 0.32, 0.3), 0.6, 0.7)
conc = mk.mat("cp_conc", (0.55, 0.54, 0.5), 0.9)
ins = mk.mat("cp_ins", (0.55, 0.3, 0.2), 0.4)
H = 8.55
mk.box(p, (0, 0, 0.15), (0.32, 0.32, 0.3), conc)
for sy in (-1, 1):
    mk.box(p, (0, sy * 0.13, H / 2), (0.3, 0.025, H - 0.02), steel)
mk.box(p, (0, 0, H / 2), (0.02, 0.26, H - 0.02), steel)
mk.box(p, (0, 0, H - 0.01), (0.3, 0.3, 0.02), steel)
for z in (H - 0.55, H - 1.25):
    mk.box(p, (0, 0, z), (0.83, 0.12, 0.1), steel)
    for sx in (-1, 1):
        mk.cyl(p, (sx * 0.36, 0, z - 0.17), 0.04, 0.24, ins, verts=10)
        mk.beam(p, (sx * 0.15, 0, z - 0.35), (sx * 0.39, 0, z - 0.05), 0.04, steel)
mk.box(p, (0.2, 0, 4.4), (0.4, 0.08, 0.08), steel)
mk.beam(p, (0.15, 0, 4.0), (0.38, 0, 4.36), 0.05, steel)
mk.cyl(p, (0.36, 0, 4.25), 0.035, 0.18, ins, verts=10)
mk.finish(p, "dm_catenarypole", out("dm_catenarypole"))


def handrail(parts, L, H, rise, posts, m, d=0.04):
    """A tube rail over L, its far end `rise` higher, a mid rail, and posts from the slope up."""
    for zr in (H, H * 0.5):
        mk.beam(parts, (-L / 2, 0, zr), (L / 2, 0, zr + rise), d, m)
    for i in range(posts):
        x = -L / 2 + 0.02 + i * (L - 0.04) / (posts - 1)
        z0 = rise * (x + L / 2) / L
        mk.box(parts, (x, 0, z0 + H / 2), (d, d, H), m)


# Long handrail (props_silo/handrail_alley-upperdeck): 4.95 long, 0.76 high, five posts; 0.038 tube.
p = mk.fresh()
rail = mk.mat("hl_rail", (0.44, 0.47, 0.47), 0.5, 0.7)
handrail(p, 4.953, 0.762, 0.0, 5, rail, 0.038)
mk.finish(p, "dm_handraillong", out("dm_handraillong"))

# Double-rise handrail (props_c17/handrail04_doublerise): a stair rail climbing 2.47 over 3.84, 0.76 above the nosings.
p = mk.fresh()
rail = mk.mat("hd_rail", (0.44, 0.47, 0.47), 0.5, 0.7)
handrail(p, 3.84, 0.762, 3.23 - 0.762, 5, rail, 0.047)
mk.finish(p, "dm_handraildoublerise", out("dm_handraildoublerise"))

# Canal bridge railing (props_canal/canal_bridge_railing02): a concrete kerb 25.2 long and 0.59 wide, steel posts every
# 2.1 m and two rails, 0.78 high.
p = mk.fresh()
conc = mk.mat("br_conc", (0.5, 0.49, 0.46), 0.9)
steel = mk.mat("br_steel", (0.2, 0.24, 0.22), 0.6, 0.6)
L, W, H = 25.2, 0.593, 0.778
mk.box(p, (0, 0, 0.14), (L, W, 0.28), conc)
mk.box(p, (0, 0, 0.29), (L, W - 0.08, 0.02), conc)
n = 13
for i in range(n):
    x = -L / 2 + 0.15 + i * (L - 0.3) / (n - 1)
    mk.box(p, (x, 0, (0.3 + H) / 2), (0.06, 0.06, H - 0.3), steel)
    mk.box(p, (x, 0, 0.31), (0.14, 0.14, 0.02), steel)
mk.box(p, (0, 0, H - 0.025), (L, 0.07, 0.05), steel)
mk.box(p, (0, 0, 0.55), (L, 0.04, 0.04), steel)
mk.finish(p, "dm_bridgerailing", out("dm_bridgerailing"))

# Wooden shelving (props_forest/shelves_wood): 2.46 long, 0.64 deep, 1.8 high, three bays of four plank shelves.
p = mk.fresh()
wood = mk.mat("ws_wood", (0.45, 0.32, 0.2), 0.85)
dark = mk.mat("ws_dark", (0.32, 0.22, 0.13), 0.85)
L, D, H = 2.455, 0.635, 1.8
for x in (-L / 2 + 0.03, -L / 6, L / 6, L / 2 - 0.03):
    for sy in (-1, 1):
        mk.box(p, (x, sy * (D / 2 - 0.03), H / 2), (0.06, 0.06, H), dark)
    for z in (0.1, H - 0.1):
        mk.box(p, (x, 0, z), (0.05, D, 0.05), dark)
for z in (0.12, 0.6, 1.08, 1.56):
    for j in range(3):
        mk.box(p, (0, -D / 2 + 0.11 + j * (D - 0.22) / 2, z + 0.06), (L, (D - 0.08) / 3 - 0.01, 0.025), wood)
mk.beam(p, (-L / 2 + 0.03, D / 2 - 0.03, 0.1), (-L / 6, D / 2 - 0.03, H - 0.1), 0.03, dark)
mk.beam(p, (L / 2 - 0.03, D / 2 - 0.03, 0.1), (L / 6, D / 2 - 0.03, H - 0.1), 0.03, dark)
mk.finish(p, "dm_woodshelves", out("dm_woodshelves"))

# Pallet rack (props_industrial/warehouse_shelf003): blue upright frames 3.06 apart with braced sides, orange beams at
# three levels, wire decking, 2.45 high and 1.31 deep.
p = mk.fresh()
blue = mk.mat("pr_blue", (0.1, 0.25, 0.55), 0.5, 0.4)
orange = mk.mat("pr_orange", (0.9, 0.42, 0.08), 0.5, 0.4)
deck = mk.mat("pr_deck", (0.55, 0.56, 0.55), 0.5, 0.7)
L, D, H = 3.059, 1.309, 2.449
for sx in (-1, 1):
    x = sx * (L / 2 - 0.04)
    for sy in (-1, 1):
        mk.box(p, (x, sy * (D / 2 - 0.04), H / 2), (0.08, 0.08, H), blue)
        mk.box(p, (x, sy * (D / 2 - 0.04), 0.005), (0.08, 0.08, 0.01), blue)
    z = 0.15
    while z < H - 0.3:
        mk.beam(p, (x, -D / 2 + 0.05, z), (x, D / 2 - 0.05, z + 0.45), 0.03, blue)
        z += 0.5
    for z in (0.12, H - 0.08):
        mk.box(p, (x, 0, z), (0.04, D - 0.1, 0.04), blue)
for z in (0.15, 1.2, 2.25):
    for sy in (-1, 1):
        mk.box(p, (0, sy * (D / 2 - 0.04), z), (L - 0.16, 0.05, 0.12), orange)
    mk.box(p, (0, 0, z + 0.065), (L - 0.16, D - 0.12, 0.01), deck)
    for i in range(1, 6):
        mk.box(p, (-L / 2 + i * L / 6, 0, z + 0.04), (0.03, D - 0.12, 0.04), deck)
mk.finish(p, "dm_palletrack", out("dm_palletrack"))


def windowwall(parts, W, H, D, wood, dark, frame):
    """Vertical planks W wide and H high, a window opening in the upper middle with a frame and sill."""
    ow, oh, oz = W * 0.55, H * 0.42, H * 0.6
    n = max(4, int(round(W / 0.15)))
    pw = W / n
    for i in range(n):
        x = -W / 2 + pw * (i + 0.5)
        m = wood if i % 3 else dark
        if abs(x) < ow / 2:
            lo = oz - oh / 2
            hi = H - (oz + oh / 2)
            mk.box(parts, (x, 0, lo / 2), (pw - 0.006, D * 0.6, lo), m)
            mk.box(parts, (x, 0, H - hi / 2), (pw - 0.006, D * 0.6, hi), m)
        else:
            mk.box(parts, (x, 0, H / 2), (pw - 0.006, D * 0.6, H), m)
    for z in (0.15, H - 0.15):
        mk.box(parts, (0, D * 0.35, z), (W, D * 0.3, 0.1), dark)
    for sx in (-1, 1):
        mk.box(parts, (sx * (ow / 2 + 0.03), 0, oz), (0.06, D, oh + 0.12), frame)
    mk.box(parts, (0, 0, oz + oh / 2 + 0.03), (ow + 0.12, D, 0.06), frame)
    mk.box(parts, (0, -D * 0.1, oz - oh / 2 - 0.03), (ow + 0.18, D * 0.8, 0.06), frame)
    mk.box(parts, (0, 0, oz), (ow, 0.04, 0.04), frame)


# Plank wall with a window opening (props_wasteland/woodwall030b_window02a and 03a): 1.07 and 1.83 wide, 1.22 high,
# 0.16 thick; an open window, not boarded.
for name, W in (("dm_woodwallwindow", 1.067), ("dm_woodwallwindowwide", 1.829)):
    p = mk.fresh()
    wood = mk.mat("ww_wood", (0.48, 0.36, 0.24), 0.9)
    dark = mk.mat("ww_dark", (0.33, 0.24, 0.16), 0.9)
    frame = mk.mat("ww_frame", (0.58, 0.55, 0.48), 0.8)
    windowwall(p, W, 1.223, 0.163, wood, dark, frame)
    mk.finish(p, name, out(name))

# Bent wall pipe run (props_pipes/interiorpipecluster01a): three pipes along 2.97 of wall under the ceiling, 2.38 up,
# two of them dropping to the floor at the ends; 0.15 out, on straps.
p = mk.fresh()
pipe = mk.mat("wb_pipe", (0.45, 0.47, 0.46), 0.5, 0.6)
paint = mk.mat("wb_paint", (0.55, 0.2, 0.15), 0.6, 0.3)
strap = mk.mat("wb_strap", (0.22, 0.22, 0.23), 0.6, 0.7)
L, H = 2.97, 2.38
for z, r, m in ((H - 0.07, 0.065, pipe), (H - 0.24, 0.05, paint), (H - 0.4, 0.07, pipe)):
    mk.cyl(p, (0, 0, z), r, L - 0.3, m, verts=14, rot=(0, PI / 2, 0))
    for x in (-0.9, 0.0, 0.9):
        mk.cyl(p, (x, 0, z), r * 1.22, 0.05, strap, verts=14, rot=(0, PI / 2, 0))
for sx, z, r, m in ((-1, H - 0.07, 0.065, pipe), (1, H - 0.4, 0.07, pipe)):
    x = sx * (L / 2 - 0.15)
    mk.cyl(p, (x, 0, z / 2), r, z, m, verts=14)
    mk.cyl(p, (x, 0, z), r * 1.35, r * 2.4, strap, verts=14)
    mk.cyl(p, (x, 0, 0.04), r * 1.5, 0.08, strap, verts=14)
for sx, z, r in ((-1, H - 0.24, 0.05),):
    x = sx * (L / 2 - 0.15)
    mk.cyl(p, (x, 0, z), r * 1.4, r * 2.4, strap, verts=14)
for sx, z in ((1, H - 0.07), (1, H - 0.24), (-1, H - 0.4)):
    mk.cyl(p, (sx * (L / 2 - 0.08), 0, z), 0.08, 0.16, strap, verts=14, rot=(0, PI / 2, 0))
mk.box(p, (0, 0.065, H - 0.24), (0.06, 0.02, 0.5), strap)
mk.finish(p, "dm_wallpipebend", out("dm_wallpipebend"))
