#!/usr/bin/env python3
"""Puts the author's own atmosphere into a finished map document: sun, shade, fog, a sky mood and the lamps the
importer dropped. Touches nothing else, so a tuned map (its balance numbers, its pruned props) stays as it is.

    tools/bsp_environment.py <map.bsp> <maps/ph_x.json> [--fog=start,end,max] [--ambience=amb_x[,amb_indoor_x]] [--night]

What it reads: the first `light_environment` (sun colour, brightness and angles; the ambient as the colour of the shade),
the `env_fog_controller` (colour, start, end, density cap), the sky's name (only to choose a mood to paint: the author's
sky textures are never carried), and the `point_spotlight` / `env_fire` entities, which `import_bsp.py` leaves out.
A map the author lit with lamps alone (no `light_environment`) keeps the environment it has. No community map in this
repository has a `func_precipitation`, so none has weather; when one does, this is where it is read (the same pass in
murder-mystery-maps' importer writes a dot-weather block).

This lives here, not in dot-map's shared reader, only until nightly item `dotbsp-environment` moves it there: every
game's converter reads the same entities, and murder-mystery-maps carries the same code.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsp_read  # noqa: E402
import import_bsp as ib  # noqa: E402

S = ib.S

# skyname -> (zenith, horizon, the ground under the horizon). The horizon is the fog colour when the map has fog,
# since distance fades into the sky and any other horizon draws a seam along every ridge.
CLEAR = ([0.32, 0.52, 0.82], [0.72, 0.82, 0.92], [0.35, 0.33, 0.30])
NIGHT = ([0.05, 0.07, 0.16], [0.13, 0.15, 0.27], [0.06, 0.06, 0.09])
SKY_MOODS = {
    "sky_borealis01": NIGHT,     # a night with an aurora
    "skycustom_03": NIGHT,
    "sky_day01_09": ([0.20, 0.28, 0.50], [0.62, 0.55, 0.60], [0.25, 0.24, 0.26]),       # an evening
    "sky_wasteland02": ([0.50, 0.57, 0.66], [0.82, 0.76, 0.64], [0.38, 0.33, 0.27]),    # dusty haze
    "bikibot": ([0.28, 0.60, 0.94], [0.76, 0.90, 0.95], [0.30, 0.38, 0.40]),            # a bright seaside
    "militia_hdr": ([0.27, 0.45, 0.76], [0.80, 0.80, 0.78], [0.30, 0.29, 0.27]),
}
FOG_END_LEAST = 160.0   # metres
FOG_MAX_MOST = 0.7
NIGHT_SKIES = ("sky_borealis01", "skycustom_03")


def _colour3(s):
    return [round(max(0.0, min(1.0, float(c) / 255.0)), 3) for c in s.split()[:3]]


def environment(bsp, fog_override=None, night=False):
    """{"env": the document's environment fields (may be empty), "lights": [(x, y, z, energy, colour)] unshifted}."""
    world = next((e for e in bsp.entities if e.get("classname") == "worldspawn"), {})
    sky = str(world.get("skyname", "")).lower()
    top, horizon, ground = SKY_MOODS.get(sky, CLEAR)
    env = {}
    sun = next((e for e in bsp.entities if e.get("classname") == "light_environment"), None)
    if sun is not None:
        c = ib.vec(sun.get("_light", "255 255 255 200"))
        c = (c + [255, 255, 255, 200][len(c):])[:4]
        ang = ib.vec(sun.get("angles", "0 0 0"))
        pitch = float(sun.get("pitch", ang[0]))
        dark = c[3] < 60 or night or sky in NIGHT_SKIES
        env["sun_colour"] = [round(v / 255.0, 3) for v in c[:3]]
        # A night sun (brightness under 60, or a night sky) is dim but not out: hunters still have to see.
        env["sun_energy"] = round(max(0.35 if dark else 0.6, min(1.0, math.sqrt(c[3] / 400.0) * 0.95)), 2)
        env["sun_pitch"] = -round(max(8.0, min(80.0, abs(pitch))))
        env["sun_yaw"] = round((ang[1] - 90.0) % 360.0)
        a = ib.vec(sun.get("_ambient", "180 190 200 200"))
        a = (a + [180, 190, 200, 200][len(a):])[:4]
        env["ambient"] = [round(v / 255.0, 3) for v in a[:3]]
        env["ambient_energy"] = round(max(0.36 if dark else 0.42, min(0.62, 0.30 + a[3] / 1000.0)), 2)
    fog = next((e for e in bsp.entities if e.get("classname") == "env_fog_controller" and str(e.get("fogenable", "1")) != "0"), None)
    if fog is not None:
        env["fog_colour"] = _colour3(fog.get("fogcolor", "180 190 200"))
        env["fog_start"] = round(float(fog.get("fogstart", 0)) * S, 1)
        env["fog_end"] = round(float(fog.get("fogend", 1000)) * S, 1)
        env["fog_max"] = round(float(fog.get("fogmaxdensity", 1.0)), 2)
        # A hunt is played by looking for something small: the author's fog may not close in on a player nearer than
        # 160 m nor go fully opaque (the bank's ended at 95 m and buried the overview, and every building past it).
        env["fog_end"] = max(env["fog_end"], FOG_END_LEAST)
        env["fog_max"] = min(env["fog_max"], FOG_MAX_MOST)
    if fog_override:
        env["fog_start"], env["fog_end"], env["fog_max"] = fog_override
        env.setdefault("fog_colour", [0.7, 0.74, 0.78])
    if "fog_colour" in env:
        horizon = env["fog_colour"]
    if sun is not None or fog is not None:
        env["sky_top"], env["sky_horizon"], env["ground"] = [round(v, 3) for v in top], [round(v, 3) for v in horizon], ground
    lights = []
    for e in bsp.entities:
        cls = e.get("classname")
        if cls in ("point_spotlight", "env_fire"):
            gx, gy, gz = ib.gd(ib.vec(e["origin"]))
            spot = cls == "point_spotlight"
            lights.append((gx, gy - 0.4 if spot else gy + 0.3, gz, 0.9 if spot else 1.1,
                           _colour3(e["rendercolor"]) if spot and e.get("rendercolor") else [1.0, 0.62, 0.28]))
    return {"env": env, "lights": lights}


def find_shift(bsp, doc):
    """The origin shift the importer applied: what turns the author's `light` positions into the document's."""
    sources = [ib.gd(ib.vec(e["origin"])) for e in bsp.entities if e.get("classname") in ("light", "light_spot") and e.get("origin")]
    if not sources or not doc["lights"]:
        sys.exit("no lights to anchor the origin shift on")
    best = (0, None)
    for l in doc["lights"][:6]:
        for s in sources:
            sh = (s[0] - l["at"][0], s[1] - l["at"][1], s[2] - l["at"][2])
            hit = sum(1 for q in doc["lights"] if any(abs(p[0] - q["at"][0] - sh[0]) < 0.02 and abs(p[1] - q["at"][1] - sh[1]) < 0.02
                                                      and abs(p[2] - q["at"][2] - sh[2]) < 0.02 for p in sources))
            if hit > best[0]:
                best = (hit, sh)
    if best[0] < 0.8 * len(doc["lights"]):
        sys.exit("origin shift not found (%d of %d lights agree)" % (best[0], len(doc["lights"])))
    return best[1]


def add_lamps(doc, lamps, shift, cap=128, gap=2.5):
    """The dropped lamps, those not within `gap` metres of a light the document has; the author's own lights are thinned
    evenly to make room when the document would pass the game's 128."""
    new = []
    for x, y, z, en, col in lamps:
        at = [round(x - shift[0], 3), round(y - shift[1], 3), round(z - shift[2], 3)]
        if any(math.dist(at, l["at"]) < gap for l in doc["lights"]) or any(math.dist(at, n["at"]) < gap for n in new):
            continue
        new.append({"at": at, "range": 9.0, "energy": en, "colour": col})
    room = cap - len(new)
    if room < 0:
        new = new[:cap]
        room = 0
    old = doc["lights"]
    if len(old) > room:
        old = [old[i * len(old) // room] for i in range(room)] if room else []
    doc["lights"] = old + new
    return len(new)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    fog_override, ambience, night = None, [], False
    for a in argv[1:]:
        if a.startswith("--fog="):
            fog_override = tuple(float(t) for t in a[6:].split(","))
        elif a.startswith("--ambience="):
            ambience = a[11:].split(",")
        elif a == "--night":
            night = True
    bsp = bsp_read.Bsp(args[0]).load()
    path = args[1]
    with open(path) as f:
        doc = json.load(f)
    at = environment(bsp, fog_override, night)
    doc["environment"].update(at["env"])
    if ambience:
        doc["ambience"] = ambience[0]
        if len(ambience) > 1:
            doc["ambience_indoor"] = ambience[1]
    added = add_lamps(doc, at["lights"], find_shift(bsp, doc)) if at["lights"] and doc.get("lights") else 0
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(json.dumps(doc, indent=1) + "\n")
    os.replace(tmp, path)
    print("%s: environment %s, %d lamps added, %d lights" % (os.path.basename(path), sorted(at["env"]), added, len(doc.get("lights", []))))


if __name__ == "__main__":
    main(sys.argv)
