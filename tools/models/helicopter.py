"""A transport helicopter in three parts, CC0, for `rules/models/categories.tsv`: the fuselage (nose, cabin, tail boom, sponsons
and gear), the main rotor (hub and blades, flat) and the tail rotor, matching how a source map splits one (body, rotor, tail).

blender -b --factory-startup --python helicopter.py -- outdir
Writes dm_helifuselage (nose at -X, 27.7 m long with the tail boom, 8.5 m wide over the sponsons, about 6 m high),
dm_helirotor (27 m across on a 1.4 m mast), dm_helitailrotor (4.2 m, in the Y-Z plane), dm_heligear (a 0.66 m landing-gear strut) and
dm_heliwheel (a 0.75 m wheel, axle along X) into outdir. Origin on the floor, centred. Plain colour materials.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modelkit as mk  # noqa: E402

outdir = sys.argv[sys.argv.index("--") + 1]

p = mk.fresh()
green = mk.mat("heli_olive", (0.27, 0.3, 0.2), 0.7, 0.2)
dark = mk.mat("heli_dark", (0.1, 0.11, 0.1), 0.6, 0.4)
glass = mk.mat("heli_glass", (0.2, 0.3, 0.35), 0.2, 0.0)
L = 27.7
x0 = -L / 2
# Cabin, nose, cockpit glass, tail boom with fin and tailplane, engine housing.
mk.box(p, (x0 + 8.5, 0, 3.0), (17.0, 3.0, 3.2), green)
mk.box(p, (x0 + 0.9, 0, 2.7), (1.8, 2.6, 2.2), green)
mk.box(p, (x0 + 1.5, 0, 3.4), (1.6, 2.7, 1.1), glass)
mk.box(p, (x0 + 21.0, 0, 3.7), (9.0, 1.0, 1.1), green)
mk.box(p, (x0 + 26.0, 0, 5.0), (1.8, 0.3, 2.4), green, rot=(0, -0.35, 0))
mk.box(p, (x0 + 25.2, 0, 4.1), (1.8, 2.2, 0.15), green)
mk.cyl(p, (x0 + 15.0, 0, 5.1), 0.8, 1.3, dark)
mk.cyl(p, (x0 + 15.0, 0, 5.9), 0.2, 0.7, dark)
# Sponsons (side fuel tanks) with their wheels, and the nose wheel.
for y in (-3.0, 3.0):
    mk.box(p, (x0 + 9.0, y, 1.5), (7.5, 2.4, 1.6), green)
    mk.cyl(p, (x0 + 9.0, y, 0.38), 0.38, 0.3, dark, rot=(math.pi / 2, 0, 0))
    mk.beam(p, (x0 + 9.0, y * 0.7, 1.9), (x0 + 9.0, y, 0.45), 0.2, dark)
mk.cyl(p, (x0 + 2.5, 0, 0.38), 0.38, 0.3, dark, rot=(math.pi / 2, 0, 0))
mk.beam(p, (x0 + 2.5, 0, 1.6), (x0 + 2.5, 0, 0.4), 0.15, dark)
# Doors and the rear ramp.
for y in (-1.51, 1.51):
    mk.box(p, (x0 + 7.0, y, 3.1), (2.4, 0.04, 1.9), dark)
mk.box(p, (x0 + 17.1, 0, 2.5), (0.2, 2.4, 2.4), dark)
mk.finish(p, "HeliFuselage", f"{outdir}/dm_helifuselage.glb")


def rotor(name, radius, blades, hub, chord, mast=0.0, vertical=False):
    """A flat rotor: blades in the horizontal plane on a mast, or (vertical) in the Y-Z plane on a hub, as a tail rotor turns."""
    q = mk.fresh()
    m = mk.mat("heli_blade", (0.08, 0.08, 0.08), 0.6, 0.4)
    z0 = mast if not vertical else radius
    if vertical:
        mk.cyl(q, (0, 0, z0), hub, 0.3, m, rot=(0, math.pi / 2, 0))
    else:
        mk.cyl(q, (0, 0, mast / 2), hub / 2, mast, m)
        mk.cyl(q, (0, 0, mast), hub, 0.12, m)
    for i in range(blades):
        a = i * 2 * math.pi / blades
        r = (radius + hub) / 2
        if vertical:
            mk.box(q, (0, math.cos(a) * r, z0 + math.sin(a) * r), (0.06, radius - hub, chord), m, rot=(a, 0, 0))
        else:
            mk.box(q, (math.cos(a) * r, math.sin(a) * r, mast), (radius - hub, chord, 0.06), m, rot=(0, 0, a))
    mk.finish(q, name, f"{outdir}/{name}.glb")


rotor("dm_helirotor", 13.5, 7, 0.6, 0.6, mast=1.4)
rotor("dm_helitailrotor", 2.1, 4, 0.2, 0.25, vertical=True)


# The separate gear and wheel parts a source map places beside the fuselage.
g = mk.fresh()
dark = mk.mat("heli_dark", (0.1, 0.11, 0.1), 0.6, 0.4)
mk.beam(g, (0, 0, 0.62), (0, 0, 0.04), 0.14, dark)
mk.box(g, (0, 0, 0.62), (0.17, 0.25, 0.08), dark)
mk.box(g, (0, 0, 0.03), (0.17, 0.25, 0.06), dark)
mk.finish(g, "dm_heligear", f"{outdir}/dm_heligear.glb")

w = mk.fresh()
dark = mk.mat("heli_dark", (0.1, 0.11, 0.1), 0.6, 0.4)
tyre = mk.mat("heli_tyre", (0.06, 0.06, 0.06), 0.9, 0.0)
mk.cyl(w, (0, 0, 0.375), 0.375, 0.3, tyre, verts=16, rot=(0, math.pi / 2, 0))
mk.cyl(w, (0, 0, 0.375), 0.2, 0.32, dark, verts=12, rot=(0, math.pi / 2, 0))
mk.finish(w, "dm_heliwheel", f"{outdir}/dm_heliwheel.glb")
