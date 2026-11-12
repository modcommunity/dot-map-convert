"""Industrial and rock stand-ins, CC0, for `rules/models/categories.tsv`: a rising handrail (the stair run), a cable spool,
a freight-elevator call post, a vertical pipe bundle and three rock clusters.

blender -b --factory-startup --python industrial.py -- outdir
Writes dm_handrailrise (1.3 m run, rises 0.6 m), dm_cablespool (1.15 m reel, axis up), dm_freightbutton (0.15 m post, 1.7 m
high, a call plate on it), dm_pipeclustertall (0.4 x 1.2 x 0.4 m, three pipes and two bands) and dm_rockcluster1..3 (about
6 x 3.5 x 5 m: a broad heap, a taller one, a long low ledge) into outdir. Origin on the floor, centred. Plain colour materials.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import modelkit as mk  # noqa: E402

outdir = sys.argv[sys.argv.index("--") + 1]


def out(name):
    return f"{outdir}/{name}.glb"


# Rising handrail: posts at both ends, top and mid rail climbing 0.6 m over the 1.3 m run.
p = mk.fresh()
steel = mk.mat("handrail_steel", (0.44, 0.47, 0.47), 0.5, 0.6)
H, T, RUN, RISE = 0.76, 0.05, 1.3, 0.6
for x, z in ((-RUN / 2, 0.0), (RUN / 2, RISE)):
    mk.box(p, (x, 0, z + H / 2), (T, T, H), steel)
for dz in (H - 0.03, H * 0.5):
    mk.beam(p, (-RUN / 2, 0, dz), (RUN / 2, 0, RISE + dz), T * 0.8, steel)
mk.finish(p, "dm_handrailrise", out("dm_handrailrise"))

# Cable spool: two flanges and a core, axis up.
p = mk.fresh()
wood = mk.mat("spool_wood", (0.5, 0.36, 0.22), 0.9)
core = mk.mat("spool_cable", (0.12, 0.12, 0.13), 0.8)
mk.cyl(p, (0, 0, 0.03), 0.575, 0.06, wood, verts=20)
mk.cyl(p, (0, 0, 0.77), 0.575, 0.06, wood, verts=20)
mk.cyl(p, (0, 0, 0.4), 0.38, 0.7, core, verts=20)
mk.finish(p, "dm_cablespool", out("dm_cablespool"))

# Freight-elevator call post: a steel post with a box on it and one lit plate.
p = mk.fresh()
steel = mk.mat("post_steel", (0.35, 0.37, 0.38), 0.6, 0.5)
plate = mk.mat("post_plate", (0.85, 0.65, 0.1), 0.5)
mk.box(p, (0, 0, 0.85), (0.1, 0.1, 1.7), steel)
mk.box(p, (0, 0, 1.2), (0.15, 0.12, 0.3), steel)
mk.box(p, (0, -0.065, 1.2), (0.07, 0.02, 0.07), plate)
mk.finish(p, "dm_freightbutton", out("dm_freightbutton"))

# Vertical pipe bundle: three upright pipes held by two bands.
p = mk.fresh()
iron = mk.mat("pipe_iron", (0.32, 0.3, 0.28), 0.7, 0.5)
for x, y, r in ((-0.1, 0.0, 0.09), (0.1, 0.05, 0.08), (0.0, -0.12, 0.07)):
    mk.cyl(p, (x, y, 0.6), r, 1.2, iron, verts=12)
for z in (0.25, 0.9):
    mk.box(p, (0, 0, z), (0.4, 0.4, 0.05), iron)
mk.finish(p, "dm_pipeclustertall", out("dm_pipeclustertall"))


def rock(parts, c, size, rng, m):
    """One displaced icosphere, flattened."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.5, location=c)
    o = bpy.context.object
    for v in o.data.vertices:
        v.co.x *= 0.65 + 0.7 * rng.random()
        v.co.y *= 0.65 + 0.7 * rng.random()
        v.co.z *= 0.55 + 0.6 * rng.random()
    o.scale = size
    o.rotation_euler = (0, 0, rng.random() * math.pi)
    o.data.materials.append(m)
    parts.append(o)


def cluster(name, seed, n, spread, big, flat):
    """A big rock and n-1 smaller ones around it; seeds are fixed so the output is stable. The lowest point is put on z = 0."""
    rng = random.Random(seed)
    p = mk.fresh()
    mats = [mk.mat("rock_a", (0.36, 0.33, 0.29), 0.95), mk.mat("rock_b", (0.3, 0.28, 0.25), 0.95)]
    for i in range(n):
        s = big * (1.0 if i == 0 else 0.35 + 0.45 * rng.random())
        c = (0, 0) if i == 0 else (rng.uniform(-spread[0], spread[0]), rng.uniform(-spread[1], spread[1]))
        rock(p, (c[0], c[1], s * flat * 0.3), (s, s * (0.8 + 0.4 * rng.random()), s * flat), rng, mats[i % 2])
    bpy.context.view_layer.update()
    low = min((o.matrix_world @ v.co).z for o in p for v in o.data.vertices)
    for o in p:
        o.location.z -= low
    mk.finish(p, name, out(name))


cluster("dm_rockcluster1", 11, 7, (2.0, 1.5), 4.0, 0.8)
cluster("dm_rockcluster2", 23, 6, (1.4, 1.2), 3.2, 1.3)
cluster("dm_rockcluster3", 37, 8, (2.6, 0.9), 2.6, 0.6)
