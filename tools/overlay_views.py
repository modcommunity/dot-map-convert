#!/usr/bin/env python3
"""overlay_views -- screenshot `--view` arguments that look at a map's info_overlay decals from above the ground.

An overlay's origin lies on its face's base plane; under a displacement that plane can be tens of
metres below the drawn hill, so a camera placed near the origin shoots from inside the terrain
(gm_fork's cliff04a views did). This aims at the middle of the decal as drawn, on the displaced
surface, from a point over the ground with a clear line down to it.

    tools/overlay_views.py <map.bsp> <texture part> [--doc <converted .json>] [--name PREFIX]

`--doc` reads the world pack's `metres_per_unit` and `offset` (a PLAYLOT document's `world` block),
so the views are in the game's metres; without it they are in map units, Godot axes. A decal in the 3D
skybox room is aimed at where the world pack draws it, moved out with the room. Prints one
`--view NAME:FX,FY,FZ:AX,AY,AZ` per overlay, or a `#` line for one with no clear view.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotbsp import mesh, overlays, reader  # noqa: E402


def frame_of(doc_path):
    """(metres per unit, offset) of a converted document's world block, (1, 0) without one."""
    if not doc_path:
        return 1.0, (0.0, 0.0, 0.0)
    with open(doc_path) as f:
        world = json.load(f).get("world") or {}
    if "metres_per_unit" not in world:
        raise SystemExit("%s has no world.metres_per_unit" % doc_path)
    return float(world["metres_per_unit"]), tuple(float(v) for v in world.get("offset", (0.0, 0.0, 0.0)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bsp")
    ap.add_argument("texture", help="part of the overlay's material name, e.g. cliff04a")
    ap.add_argument("--doc", help="the converted document whose world block gives scale and offset")
    ap.add_argument("--name", help="view name prefix (default: <map>_<texture>)")
    a = ap.parse_args(argv)
    s, off = frame_of(a.doc)
    bsp = reader.Bsp(a.bsp)
    bsp.load()

    def to(p):    # Source (x, y, z) -> Godot (x, z, -y)
        return (p[0] * s + off[0], p[2] * s + off[1], -p[1] * s + off[2])

    prefix = a.name or "%s_%s" % (os.path.splitext(os.path.basename(a.bsp))[0].split("_", 1)[-1], a.texture)
    # the 3D skybox room's decals are drawn moved out and scaled up, as the room's faces are
    sky, k = mesh._sky_setup(bsp, mesh.DRAWN_BRUSH_ENTITIES)
    views = overlays.overlay_views(bsp, a.texture, to, prefix, sky=(sky[0], k, sky[2]) if sky else None)
    if not views:
        raise SystemExit("no world overlay uses a material containing %r" % a.texture)
    for name, cam, at in views:
        if cam is None:
            print("# %s: no clear view of %.1f,%.1f,%.1f" % ((name,) + at))
        else:
            print("--view %s:%.1f,%.1f,%.1f:%.1f,%.1f,%.1f" % ((name,) + cam + at))
    return 0


if __name__ == "__main__":
    sys.exit(main())
