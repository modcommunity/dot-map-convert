"""A steel handrail panel and its right-angle corner, CC0, for `rules/models/categories.tsv`: two posts, a top rail and a mid rail, 0.76 m high.

blender -b --factory-startup --python handrail.py -- outdir
Writes dm_handrail (2 m long along X, 0.05 m deep) and dm_handrailcorner (0.7 m on each leg, an L in the X-Y plane) into outdir. Origin on the floor, centred. Plain colour materials.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modelkit as mk  # noqa: E402

outdir = sys.argv[sys.argv.index("--") + 1]
H = 0.76
T = 0.05


def leg(parts, a, b, m):
    """One run of rail from a to b on the floor plane: top and mid bars between two end posts."""
    for x, y in (a, b):
        mk.box(parts, (x, y, H / 2), (T, T, H), m)
    cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    along_x = abs(b[0] - a[0]) > abs(b[1] - a[1])
    length = abs(b[0] - a[0]) if along_x else abs(b[1] - a[1])
    size = (length, T * 0.8, T * 0.8) if along_x else (T * 0.8, length, T * 0.8)
    for z in (H - 0.03, H * 0.5):
        mk.box(parts, (cx, cy, z), size, m)


p = mk.fresh()
steel = mk.mat("handrail_steel", (0.44, 0.47, 0.47), 0.5, 0.6)
leg(p, (-1.0, 0.0), (1.0, 0.0), steel)
mk.box(p, (0.0, 0.0, 0.04), (2.0, T * 0.6, 0.08), steel)
mk.finish(p, "dm_handrail", f"{outdir}/dm_handrail.glb")

q = mk.fresh()
steel = mk.mat("handrail_steel", (0.44, 0.47, 0.47), 0.5, 0.6)
leg(q, (-0.35, -0.35), (0.35, -0.35), steel)
leg(q, (0.35, -0.35), (0.35, 0.35), steel)
mk.finish(q, "dm_handrailcorner", f"{outdir}/dm_handrailcorner.glb")
