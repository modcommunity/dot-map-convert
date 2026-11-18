#!/usr/bin/env python3
"""Run the gameplay-fidelity audit (`dotbsp/fidelity.py`) over many maps and total it.

    python3 -P tools/fidelity_audit.py OUT.json MAP_OR_DIR [...] [--jobs N] [--md OUT.md]

A directory is walked for `.bsp` files; a slim directory from `tools/fidelity_slim.py` also has
`<key>.json` beside each map, whose `paths` name it in the report (and whose counted lumps fill
the other-categories table). Writes one JSON with every map's findings and the totals per
finding class and per entity class (status and how many maps use it); `--md` writes the tables.
"""

import argparse
import collections
import json
import os
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotbsp import fidelity, reader  # noqa: E402

# Entity classes counted per category for the other-mappable-categories table.
CATEGORIES = {
    "sound": ("ambient_generic", "env_soundscape", "env_soundscape_triggerable", "env_soundscape_proxy",
              "trigger_soundscape", "point_soundevent", "env_microphone", "env_speaker"),
    "particles": ("info_particle_system", "env_smokestack", "env_steam", "env_spark", "env_smoketrail",
                  "func_dustmotes", "func_dustcloud", "env_splash", "env_bubbles", "env_embers", "func_smokevolume",
                  "env_fire", "env_firesource", "env_explosion", "env_shooter", "env_dustpuff"),
    "sprites_beams": ("env_sprite", "env_sprite_oriented", "env_glow", "env_lightglow", "env_beam", "env_laser",
                      "env_spritetrail", "point_spotlight", "beam_spotlight"),
    "decals_overlays": ("infodecal", "info_overlay", "info_projecteddecal", "info_overlay_transition"),
    "sky_fog_post": ("sky_camera", "env_fog_controller", "env_sun", "env_tonemap_controller", "color_correction",
                     "color_correction_volume", "postprocess_controller", "env_skypaint", "shadow_control",
                     "env_cascade_light", "env_wind", "func_precipitation"),
    "lights": ("light", "light_spot", "light_environment", "light_dynamic", "env_projectedtexture"),
    "cubemaps": ("env_cubemap",),
    "physics_props": ("prop_physics", "prop_physics_multiplayer", "prop_physics_override", "prop_ragdoll",
                      "func_physbox", "func_physbox_multiplayer", "phys_constraint", "phys_hinge", "phys_ballsocket",
                      "phys_lengthconstraint", "phys_pulleyconstraint", "phys_slideconstraint", "phys_thruster",
                      "phys_motor", "phys_keepupright", "phys_spring", "phys_ragdollmagnet", "point_push"),
    "nav_ai": ("info_node", "info_node_hint", "info_hint", "info_node_air", "info_node_air_hint", "info_node_link",
               "info_node_link_controller", "path_corner", "path_track", "assault_rallypoint", "ai_goal_*",
               "scripted_sequence", "aiscripted_schedule"),
    "commands": ("point_servercommand", "point_clientcommand", "point_broadcastclientcommand", "game_text",
                 "env_hudhint", "game_player_equip", "game_ui", "game_end", "game_score", "game_round_end",
                 "info_map_parameters", "func_buyzone", "logic_script"),
    "water": ("func_water_analog", "func_water", "water_lod_control", "func_precipitation"),
}


def walk(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for dp, _dn, fn in os.walk(p):
                out += [os.path.join(dp, n) for n in fn if n.lower().endswith(".bsp")]
        else:
            out.append(p)
    return sorted(out)


def one(path):
    side = os.path.splitext(path)[0] + ".json"
    info = {}
    if os.path.isfile(side):
        with open(side, encoding="utf-8") as f:
            info = json.load(f)
    rec = {"path": path, "paths": info.get("paths", [path]), "lumps": info.get("lumps", {}),
           "pak_sounds": sum(1 for n in info.get("pak", []) if n.startswith("sound/")),
           "pak_texts": sorted(info.get("texts", {}))}
    try:
        bsp = reader.Bsp(path).load()
        rep = fidelity.findings(bsp)
    except Exception as ex:  # noqa: BLE001 - a map that cannot be audited is a finding itself
        rec["error"] = "%s: %s" % (type(ex).__name__, ex)
        rec["trace"] = traceback.format_exc()[-1500:]
        return rec
    rec.update(rep)
    cats = collections.Counter()
    for e in bsp.entities:
        c = e.get("classname", "")
        for cat, names in CATEGORIES.items():
            if any(c == n or (n.endswith("*") and c.startswith(n[:-1])) for n in names):
                cats[cat] += 1
    rec["categories"] = dict(cats)
    rec["gameplay_lost"] = len(fidelity.gameplay_lost(rep))
    return rec


def name_of(rec):
    p = rec["paths"][0]
    return os.path.splitext(os.path.basename(p))[0]


def game_of(rec):
    for p in rec["paths"]:
        for g, hint in (("Airdrift", "/airdrift"), ("ZZ", "/zz/"), ("Deathrun", "/deathrun/"), ("Wipeout", "/wipeout/"),
                        ("HnS", "/hideseek/"), ("PH", "/prophunt/"), ("MM", "/murder/"), ("Playlot", "/pg/"),
                        ("FC", "/basegame/"), ("FC", "/holdback/"), ("FC", "/maps/")):
            if hint in p:
                return g
    return "other"


def totals(maps):
    by_find = collections.defaultdict(lambda: [0, 0])     # class -> [maps, items]
    by_cls = collections.defaultdict(lambda: [0, collections.Counter()])
    cats = collections.defaultdict(lambda: [0, 0])
    for r in maps:
        for k, v in r.get("counts", {}).items():
            by_find[k][0] += 1
            by_find[k][1] += v
        for c, s in r.get("classes", {}).items():
            by_cls[c][0] += 1
            by_cls[c][1][s] += 1
        for k, v in r.get("categories", {}).items():
            cats[k][0] += 1
            cats[k][1] += v
    return ({k: {"maps": a, "items": b, "severity": fidelity.FINDINGS.get(k, ("?",))[0]} for k, (a, b) in by_find.items()},
            {c: {"maps": n, "status": s.most_common(1)[0][0]} for c, (n, s) in by_cls.items()},
            {k: {"maps": a, "entities": b} for k, (a, b) in cats.items()})


def markdown(maps, find, cls, cats):
    ok = [m for m in maps if "error" not in m]
    out = ["## Totals", "", "%d distinct maps audited, %d could not be read." % (len(ok), len(maps) - len(ok)), "",
           "| Finding | Severity | Maps | Items | Meaning |", "| --- | --- | --- | --- | --- |"]
    for k in sorted(find, key=lambda k: (fidelity.SEVERE.index(find[k]["severity"]) if find[k]["severity"] in fidelity.SEVERE else 9, -find[k]["maps"])):
        v = find[k]
        out.append("| `%s` | %s | %d | %d | %s |" % (k, v["severity"], v["maps"], v["items"], fidelity.FINDINGS.get(k, ("", ""))[1]))
    out += ["", "## Entity classes", "", "| Status | Classes | Of which gameplay |", "| --- | --- | --- |"]
    st = collections.Counter(v["status"] for v in cls.values())
    gp = collections.Counter(v["status"] for c, v in cls.items() if fidelity.gameplay_class(c))
    for s in ("implemented", "approximated", "ignored", "unknown"):
        out.append("| %s | %d | %d |" % (s, st[s], gp[s]))
    out += ["", "Gameplay classes not implemented, by maps using them:", "", "| Class | Status | Maps |", "| --- | --- | --- |"]
    for c, v in sorted(cls.items(), key=lambda kv: -kv[1]["maps"]):
        if fidelity.gameplay_class(c) and v["status"] != "implemented":
            out.append("| `%s` | %s | %d |" % (c, v["status"], v["maps"]))
    out += ["", "## Other mappable categories", "", "| Category | Maps | Entities |", "| --- | --- | --- |"]
    for k, v in sorted(cats.items(), key=lambda kv: -kv[1]["maps"]):
        out.append("| %s | %d | %d |" % (k, v["maps"], v["entities"]))
    lumps = collections.Counter()
    for m in ok:
        for k, v in m.get("lumps", {}).items():
            if v:
                lumps[k] += 1
    out += ["", "Maps carrying: " + ", ".join("%s %d" % kv for kv in sorted(lumps.items())),
            "Maps packing sounds: %d; packing sound scripts or soundscapes: %d" % (
                sum(1 for m in ok if m.get("pak_sounds")),
                sum(1 for m in ok if any("sound" in t for t in m.get("pak_texts", []))))]
    out += ["", "## Per map", "", "| Game | Map | Entities | Severe | Top findings |", "| --- | --- | --- | --- | --- |"]
    for m in sorted(ok, key=lambda m: (game_of(m), name_of(m))):
        top = sorted(((k, v) for k, v in m.get("counts", {}).items()
                      if fidelity.FINDINGS.get(k, ("lost",))[0] in fidelity.SEVERE), key=lambda kv: -kv[1])[:4]
        out.append("| %s | %s | %d | %d | %s |" % (game_of(m), name_of(m), m.get("entities", 0), m["gameplay_lost"],
                                                   ", ".join("%s %d" % kv for kv in top)))
    bad = [m for m in maps if "error" in m]
    if bad:
        out += ["", "## Not audited", ""] + ["- %s: %s" % (name_of(m), m["error"][:160]) for m in bad]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--jobs", type=int, default=0, help="processes (0 = one per core)")
    ap.add_argument("--md")
    a = ap.parse_args(argv)
    paths = walk(a.paths)
    with ProcessPoolExecutor(max_workers=a.jobs or os.cpu_count()) as ex:
        maps = list(ex.map(one, paths, chunksize=2))
    find, cls, cats = totals([m for m in maps if "error" not in m])
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"maps": maps, "findings": find, "classes": cls, "categories": cats}, f, indent=1, sort_keys=True)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as f:
            f.write(markdown(maps, find, cls, cats))
    bad = sum(1 for m in maps if "error" in m)
    print("%d maps, %d not audited, %d with severe findings" % (len(maps), bad,
                                                              sum(1 for m in maps if m.get("gameplay_lost"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
