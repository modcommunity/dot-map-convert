"""Writes examples/bsp_mesh/fixture.{json,bin}, the mesh the Godot suite reads.

Run: python3 -I tools/bsp/tests/mesh_fixture.py (test_mesh.py checks the files are current).
A floor slab, a wall, and a door (a func_door brush entity with a targetname and a button that
opens it), from synth.py, so the Godot side has a world, a hull per brush and a mover.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                 # noqa: E402
from dotbsp import mesh, movers, reader      # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "examples", "bsp_mesh", "fixture")


def bsp():
    b = reader.Bsp("fixture.bsp", data=synth.build(
        boxes=((0, 0, 0, 512, 512, 16), (0, 496, 16, 512, 512, 192)),
        materials=("concrete/concretefloor001", "metal/metalwall001"), faces=True,
        entity_box=(-4, -32, 0, 4, 32, 112), entity_origin=(256, 256, 16),
        entity_keys={"targetname": "gate", "movedir": "-90 0 0", "speed": "100", "lip": "8"})).load()
    b.entities.append({"classname": "func_button", "targetname": "b", "OnPressed": "gate,Open,,0,-1"})
    return b


def write(prefix=OUT):
    b = bsp()
    m = mesh.build(b)
    extra = {"movers": movers.movers(b), "volumes": movers.volumes(b)}
    return mesh.write(m, prefix, credit={"author": "dot-map tests"}, name="fixture", extra=extra)


if __name__ == "__main__":
    d = write()
    print("%s.{json,bin}: %s" % (OUT, d["counts"]))
