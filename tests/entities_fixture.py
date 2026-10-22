"""Writes examples/bsp_mesh/zm_4way_tunnel.entities.json, a real map's mover, volume and link data.

Run: python3 -I tools/bsp/tests/entities_fixture.py <zm_4way_tunnel_v2.bsp>. The map is a community
download and is not in the repository; only the entity data derived from it is, so the suites
(test_mesh.py, bsp_entities_demo.tscn) run without the map. Water and ladder volumes are left out.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import mesh, movers, reader      # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "examples", "bsp_mesh", "zm_4way_tunnel.entities.json")


def build(path):
    with open(path, "rb") as f:
        bsp = reader.Bsp(os.path.basename(path), data=f.read()).load()
    owners = mesh.model_entities(bsp)
    return {"format": "dot-bsp-mesh", "version": 1, "name": "zm_4way_tunnel", "partial": "entities only",
            "movers": movers.movers(bsp, owners=owners),
            "volumes": [v for v in movers.volumes(bsp, owners=owners) if v["kind"] not in ("water", "ladder")],
            "links": movers.links(bsp), "entities": movers.generic(bsp, owners)}


if __name__ == "__main__":
    doc = build(sys.argv[1])
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    print(OUT, {k: len(v) for k, v in doc.items() if isinstance(v, list)})
