#!/usr/bin/env python3
"""Write a converter spec (tools/bsp/<id>.json) from a store entry's BSP entities and credit, nothing by hand.

    python3 -P tools/auto_spec.py zz/zs_lens [more store keys]

The mode follows the map's prefix (`ze_` escape, anything else survival); the survivor and zombie
spawn classes are the ones the map actually has the most of. The result is a starting point that
import_bsp.py runs as it is; a hand-tuned spec of the same id is never overwritten.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BSP = os.environ.get("DOTBSP_PATH", os.path.join(HERE, "..", "..", "dot-map-convert"))
sys.path.insert(0, BSP)
from dotbsp import reader  # noqa: E402

STORE = os.environ.get("DOTBSP_STORE", os.path.expanduser("~/mapsrc/store"))
SURVIVORS = ["info_player_human", "info_player_counterterrorist", "info_player_start"]
ZOMBIES = ["info_player_zombie", "info_player_undead", "info_player_terrorist"]
PROPS = {  # model name fragments -> Kenney ids, the families every converted map shares
    "car": "cars_sedan", "truck": "cars_truck", "barrel": "survival_barrel", "oildrum": "survival_barrel",
    "crate": "survival_box", "box": "survival_box", "chair": "furniture_chair", "table": "furniture_table",
    "desk": "furniture_table", "couch": "furniture_lounge_sofa", "bed": "furniture_bed_single",
    "tree": "nature_tree_default", "shelf": "furniture_bookcase_closed", "locker": "furniture_bookcase_closed_doors",
    "monitor": "furniture_television_modern", "toilet": "furniture_toilet", "sink": "furniture_bathroom_sink",
    "dumpster": "roads_dumpster", "pallet": "urban_pallet", "bench": "furniture_bench", "fence": "survival_fence",
}


def map_id(name):
    base = re.sub(r"(_v\d.*|_b\d.*|_a\d+|_beta|_final|_fix|_\d+(_.*)?|_v\d+)$", "", name)
    return base or name


def prop_models(bs):
    out = {}
    for e in bs.entities:
        m = (e.get("model") or "").lower()
        if e.get("classname", "").startswith("prop_") and m.endswith(".mdl") and m not in out:
            hit = next((v for k, v in PROPS.items() if k in m.rsplit("/", 1)[-1]), None)
            if hit:
                out[m] = hit
    return out


def spec_for(key):
    sys.path.insert(0, BSP)
    idx = json.load(open(os.path.join(STORE, "index.json")))
    h = idx[key]
    d = os.path.join(STORE, h)
    credit = json.load(open(os.path.join(d, "credit.json")))
    bs = reader.Bsp(os.path.join(d, "source.bsp"), data=open(os.path.join(d, "source.bsp"), "rb").read()).load()
    count = {}
    for e in bs.entities:
        count[e.get("classname")] = count.get(e.get("classname"), 0) + 1
    name = key.split("/", 1)[1].split("~")[0]
    mid = map_id(name)
    surv = max(SURVIVORS, key=lambda c: count.get(c, 0))
    zomb = [c for c in ZOMBIES if count.get(c, 0)]
    zomb = [max(zomb, key=lambda c: count[c])] if zomb else []
    escape = name.startswith("ze_")
    pretty = " ".join(w.capitalize() for w in re.sub(r"^(ze|zm|zs)_", "", mid).split("_"))
    spec = {
        "id": mid, "name": pretty, "source": name + ".bsp", "author": credit["author"], "page": credit["page"],
        "licence": credit["licence"],
        "blurb": "Run for it: an escape map converted from %s's %s." % (credit["author"].split(" (")[0], name) if escape
        else "Hold out against the horde.",
        "mode": "exodus" if escape else "survival", "survivors": 8,
        "survivor_class": surv, "zombie_classes": zomb, "solid_classes": ["func_brush"],
        "flood_step": 0.3, "thin_walls": True, "toys": [["barrel", "spawn", 3, -2], ["tyre", "spawn", -3, 2]],
        "items_auto": True, "auto_lights": {"spacing": 6.0, "height": 2.3, "range": 7.0, "energy": 0.9},
        "prop_models": prop_models(bs), "max_boxes": 3500, "generated": True,
        "keep_treads": True, "nav_min_depth": 1, "drop_lids": True,
    }
    if escape:
        spec.update({"gate_classes": ["func_door", "func_door_rotating", "func_movelinear"],
                     "solid_classes": ["func_breakable", "func_brush", "func_tracktrain"], "holdout": 25,
                     "gate_label": "Open the door", "drop_buried": True, "route_bridge": True})
    else:
        spec.update({"survive_seconds": 600, "posts": 6, "caches_near_posts": True, "drop_ramps": 0.9,
                     "greedy_floors": True, "thin_lintels": True, "drop_small": [0.15, 1.5]})
    return mid, spec


def main(argv):
    for key in argv[1:]:
        mid, spec = spec_for(key)
        path = os.path.join(HERE, "bsp", mid + ".json")
        if os.path.exists(path) and not json.load(open(path)).get("generated"):
            print(mid, "hand-tuned spec kept")
            continue
        with open(path, "w") as f:
            json.dump(spec, f, indent=1)
            f.write("\n")
        print(mid, key)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
