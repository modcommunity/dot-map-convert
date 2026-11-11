"""Playground gear, CC0, for `rules/models/categories.tsv`: swing set, slide, jungle gym, teeter-totter (plank and fulcrum),
carousel, and the tic-tac-toe post and block of the Source playground props.

blender -b --factory-startup --python playground.py -- outdir
Writes dm_swingset, dm_slide, dm_junglegym, dm_teeterplank, dm_teeterstand, dm_carousel, dm_tictactoepost and dm_tictactoeblock
(.glb) into outdir. Origin on the floor, centred, the long side along X. Plain colour materials, a few hundred triangles each.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modelkit as mk  # noqa: E402

outdir = sys.argv[sys.argv.index("--") + 1]


def colours():
    return (mk.mat("play_steel", (0.55, 0.56, 0.6), 0.5, 0.8), mk.mat("play_red", (0.75, 0.15, 0.12), 0.7),
            mk.mat("play_yellow", (0.9, 0.7, 0.12), 0.7), mk.mat("play_blue", (0.15, 0.3, 0.7), 0.7),
            mk.mat("play_wood", (0.55, 0.4, 0.25), 0.9), mk.mat("play_rubber", (0.12, 0.12, 0.13), 0.9))


def out(name):
    return f"{outdir}/{name}.glb"


# Swing set: two A-frames and a top bar, two seats on chains. 3.6 x 1.8 x 2.4.
p = mk.fresh()
steel, red, yellow, blue, wood, rubber = colours()
L, D, H = 3.6, 1.8, 2.4
for x in (-L / 2 + 0.1, L / 2 - 0.1):
    mk.beam(p, (x, -D / 2, 0), (x, 0, H), 0.1, steel)
    mk.beam(p, (x, D / 2, 0), (x, 0, H), 0.1, steel)
mk.cyl(p, (0, 0, H), 0.07, L, steel, rot=(0, math.pi / 2, 0))
for x in (-0.7, 0.7):
    for dx in (-0.2, 0.2):
        mk.box(p, (x + dx, 0, H / 2 + 0.2), (0.015, 0.015, H - 0.5), steel)
    mk.box(p, (x, 0, 0.45), (0.5, 0.2, 0.05), rubber)
mk.finish(p, "Swingset", out("dm_swingset"))

# Slide: ladder at one end, platform, tilted chute. 3.0 x 0.8 x 2.0.
p = mk.fresh()
steel, red, yellow, blue, wood, rubber = colours()
for y in (-0.35, 0.35):
    mk.beam(p, (-1.3, y, 0), (-1.3, y, 1.4), 0.07, steel)
    mk.beam(p, (-0.7, y, 0), (-0.7, y, 1.4), 0.07, steel)
for i in range(1, 5):
    mk.box(p, (-1.0, 0, i * 0.28), (0.04, 0.7, 0.05), steel)
mk.box(p, (-1.0, 0, 1.4), (0.75, 0.8, 0.06), yellow)
for y in (-0.38, 0.38):
    mk.box(p, (-1.0, y, 1.7), (0.7, 0.03, 0.55), steel)
a, b = (-0.62, 0, 1.4), (1.45, 0, 0.12)
ang = math.atan2(a[2] - b[2], b[0] - a[0])
cx, cz = (a[0] + b[0]) / 2, (a[2] + b[2]) / 2
ln = math.hypot(b[0] - a[0], b[2] - a[2])
mk.box(p, (cx, 0, cz + 0.03), (ln, 0.6, 0.04), red, rot=(0, ang, 0))
for y in (-0.31, 0.31):
    mk.box(p, (cx, y, cz + 0.1), (ln, 0.03, 0.14), red, rot=(0, ang, 0))
mk.beam(p, (0.4, -0.3, 0), (0.4, -0.3, 0.8), 0.05, steel)
mk.beam(p, (0.4, 0.3, 0), (0.4, 0.3, 0.8), 0.05, steel)
mk.finish(p, "Slide", out("dm_slide"))

# Jungle gym: a cube of bars with a ladder lattice on top. 2.4 x 2.4 x 2.0.
p = mk.fresh()
steel, red, yellow, blue, wood, rubber = colours()
W, H = 2.4, 2.0
for x in (-W / 2 + 0.05, W / 2 - 0.05):
    for y in (-W / 2 + 0.05, W / 2 - 0.05):
        mk.box(p, (x, y, H / 2), (0.08, 0.08, H), red)
for z in (0.7, 1.35, H - 0.05):
    for s in (-1, 1):
        mk.box(p, (0, s * (W / 2 - 0.05), z), (W, 0.05, 0.05), yellow)
        mk.box(p, (s * (W / 2 - 0.05), 0, z), (0.05, W, 0.05), yellow)
for i in range(-2, 3):
    mk.box(p, (i * 0.45, 0, H - 0.05), (0.04, W, 0.04), yellow)
    mk.box(p, (0, i * 0.45, H - 0.1), (W, 0.04, 0.04), blue)
mk.finish(p, "JungleGym", out("dm_junglegym"))

# Teeter-totter: the plank (a handle at each end) and the fulcrum stand.
p = mk.fresh()
steel, red, yellow, blue, wood, rubber = colours()
mk.box(p, (0, 0, 0.45), (2.4, 0.3, 0.07), wood)
for x in (-1.0, 1.0):
    mk.box(p, (x, 0, 0.6), (0.04, 0.26, 0.04), steel)
    for y in (-0.12, 0.12):
        mk.box(p, (x, y, 0.53), (0.04, 0.03, 0.15), steel)
mk.finish(p, "TeeterPlank", out("dm_teeterplank"))
p = mk.fresh()
steel, red, yellow, blue, wood, rubber = colours()
mk.beam(p, (0, -0.15, 0), (0, 0, 0.45), 0.07, steel)
mk.beam(p, (0, 0.15, 0), (0, 0, 0.45), 0.07, steel)
mk.box(p, (0, 0, 0.45), (0.1, 0.35, 0.06), steel)
mk.finish(p, "TeeterStand", out("dm_teeterstand"))

# Carousel: disc with a hub, four rails and four spokes. 2.4 x 2.4 x 0.9.
p = mk.fresh()
steel, red, yellow, blue, wood, rubber = colours()
mk.cyl(p, (0, 0, 0.3), 1.2, 0.08, blue, verts=24)
mk.cyl(p, (0, 0, 0.55), 0.06, 0.9, steel)
for i in range(4):
    a = i * math.pi / 2
    c, s = math.cos(a) * 1.1, math.sin(a) * 1.1
    mk.beam(p, (0, 0, 0.8), (c, s, 0.8), 0.04, steel)
    mk.beam(p, (c, s, 0.3), (c, s, 0.8), 0.04, steel)
mk.finish(p, "Carousel", out("dm_carousel"))

# Tic-tac-toe: a post, and a turning block (cube on a pin).
p = mk.fresh()
steel, red, yellow, blue, wood, rubber = colours()
mk.cyl(p, (0, 0, 0.7), 0.06, 1.4, steel)
mk.box(p, (0, 0, 0.03), (0.3, 0.3, 0.06), steel)
mk.finish(p, "TicTacToePost", out("dm_tictactoepost"))
p = mk.fresh()
steel, red, yellow, blue, wood, rubber = colours()
mk.box(p, (0, 0, 0.3), (0.5, 0.5, 0.5), yellow)
for z in (0.1, 0.5):
    mk.box(p, (0, 0, z), (0.52, 0.52, 0.04), red)
mk.finish(p, "TicTacToeBlock", out("dm_tictactoeblock"))
