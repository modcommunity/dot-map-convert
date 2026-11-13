#!/usr/bin/env python3
"""Converts a Source 1 community sandbox .bsp (VBSP 19/20) into a game-playlot map document.

    tools/import_bsp.py <map.bsp> <config-name> [--out=maps/<id>.json]

`CONFIGS` below says, per map, its id, name, author, page, how its author's textures become the
game's materials, where the spawn is and what is dropped. The reader (bsp_read.py) and the material
naming and majority pick (dotbsp.docboxes) and the brush-to-box cutting (dotbsp.boxes.decompose with
tilt=True) are dot-map's shared ones; this file keeps only the document format, the GAME_MATERIAL table
and the per-map configs. Re-importing gm_smallbase gives a byte-identical document.

What it does, and why each choice:

- A document has boxes and no meshes, so each world brush becomes a BOX: its convex hull is
  found (bsp_read.Bsp.brush_hull) and, when every corner is a box corner, that box is written;
  a box turned about the vertical axis keeps its turn; a prism of any plan is the smallest
  turned rectangle round it; anything else (a slope, a stair) is cut into slabs along its longer
  horizontal axis, each as tall as the brush is at the slab's middle, so a ramp becomes a flight
  of 0.5 m risers, which a player climbs (the game's climb limit is 1.035 m).
- Axes: Source is Z-up, godot is (x, z, -y). Scale: 1 unit = 0.01905 m, the family's.
- Textures are NOT carried. A brush's surface comes from dot-map's shared list
  (dot-map-convert/dotbsp/source_textures.tsv, a new texture goes there and `bsp.py unmapped <bsp>` lists
  what it misses); GAME_MATERIAL turns the list's generic ids into this game's materials and
  tints, drawn over Kenney's CC0 Prototype Textures grid like every other map.
- Tool brushes (skybox, clip, trigger, hint, nodraw-only) are dropped. A water brush becomes a
  water volume. A document has no meshes, so a displacement is not carried as one: a config with
  `terrain` ({"cell", "material", "colour", "thick"}) samples the map's displacements inside its region
  into a heightfield and lays tilted slabs on it (dotbsp.terrain.tilted_tiles), one per run of cells
  sharing a plane, so a hill is walked on and not climbed as steps. Without it the brush under one is all.
- The ground is shifted so the spawn's floor is y = 0.
- A config may hold what a converter cannot read out of the brushes: `stairs` (a file stairs/<name>.json of
  flights, each a run of box steps that carves its way through the boxes in its headroom; a staircase of
  the original is a tilted or sliced brush the survey cannot climb), `ramps`, `fill` (solid filler for a
  pit with no way out), `remove` (whole boxes standing where the original has a door or a beam that was
  not carried) and `declared` (ground meant to be out of reach). Upright boxes that meet with a hairline
  between them are welded (`weld_hairlines`), so the survey does not read the rounding as a slot.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bsp_read  # noqa: E402  (also puts dot-map-convert on sys.path)
from dotbsp import boxes as boxes_lib, docboxes, texturemap  # noqa: E402  (the passes and the texture list the map repositories share)
from dotbsp import gaps  # noqa: E402  (closes the cracks the survey reads as slots)
from dotbsp import sourceframe  # noqa: E402  (doc["source_frame"]: the ground shift, for the audit)
from dotbsp import terrain  # noqa: E402  (displacement ground as tilted slabs)

S = 0.01905
SLAB = 28.0     # source units: ~0.53 m, a slope's riser
MIN_SIDE = 0.04  # metres: a brush thinner than this in every direction is a bevel sliver, not a wall


def brush_boxes(bsp, index, slab=None):
    """dot-map's boxes.decompose for one brush: ([(u range), (v range), (z range), phi], cut), cut 0 for a
    box, 1 for slabs and 2 for a tilted ramp, whose box is then boxes.decompose's own ramp tuple."""
    planes = [bsp.planes[s[0]][:4] for s in bsp.brushsides[bsp.brushes[index][0]:][:bsp.brushes[index][1]] if not s[3]]
    parts = boxes_lib.decompose(planes, bsp.brush_hull(index), slab=slab or SLAB, tilt=True)
    if not parts:
        return [], 0
    if parts[0]["kind"] == "ramp":
        (x0, x1), (y0, y1), _z = parts[0]["x"], parts[0]["y"], parts[0]["z"]
        axis, zlow, zhigh, base, ang, sign = parts[0]["ramp"]
        return [(x0, x1, y0, y1, zlow, zhigh, base, ang, axis, sign)], 2
    out = [(p["x"], p["y"], p["z"], p["phi"]) for p in parts]
    return out, 1 if parts[0]["kind"] == "slab" else 0


# What the shared list's generic ids become here: (this game's material, colour or None). The game has no
# brick, plaster, tile or ceiling material (its surfaces are physical: concrete, rock, wood...), so the look
# is Kenney's grid under a tint, the tints the maps carried before the list (a brick wall is rock under
# #b0705a). The list's own tints are not used: they say what the mapper meant, these say what reads here.
# Anything not named is already one of the game's ids (concrete, metal, glass, grass, water) and passes through.
GAME_MATERIAL = {
    "wallpaper_decrepit": ("concrete", "#cfc6b4"), "carpet_blue": ("concrete", "#5f6f8a"), "carpet_grey": ("concrete", "#8a8a8a"),
    "carpet_pattern": ("concrete", "#8a6f5f"), "carpet_red": ("concrete", "#8a4a4a"), "roof_clay": ("concrete", "#b0705a"),
    "glass_frosted": ("glass", None), "fence": ("metal", None), "shield": ("metal", None), "ladder": ("metal", None), "foliage_card": ("foliage", None),
    "brick_red": ("rock", "#b0705a"), "stone_wall": ("rock", None),
    "plaster_painted": ("concrete", "#d9d2c3"), "plaster_worn": ("concrete", "#d9d2c3"), "wallpaper": ("concrete", "#d9d2c3"),
    "ceiling": ("concrete", "#8d8b86"), "ceiling_tile": ("concrete", "#8d8b86"), "bars": ("metal", None),
    "wood_planks": ("wood", None), "door_wood": ("wood", None), "wood_floor": ("wood", None), "parquet": ("wood", None),
    "roof_tiles": ("concrete", None), "tile_floor": ("concrete", None), "carpet": ("concrete", None), "flat": ("concrete", None),
    "mud": ("mud", None), "snow": ("snow", None), "grate": ("metal", None),
}

# Per map. "overrides" is (substring of the classified texture name, material, colour or None), first match
# wins and is tried before the shared list: only what the list cannot say, and each entry needs a reason.
CONFIGS = {
    "construct_small": {
        "id": "pgc_construct_small",
        "name": "Construct Small",
        "blurb": "A pool pit and a brick plant house under open sky: a concrete yard with a deep water basin, a long brick-walled lane and a grass field behind, ringed by tall plaster walls.",
        "author": "Wylie",
        "source": "gm_construct_small, https://gamebanana.com/mods/60385",
        "spawn_at": 0,
        # The basin is 8.5 m deep with a wall all round: a player thrown in could never leave, so
        # one ramp is added (metres in the document's frame).
        "ramps": [{"x": (-27.0, -9.75), "z": (-30.0, -26.0), "y": (-8.53, 0.0)}],
        # Tops of the tall outer walls and a rail, which no player is meant to stand on.
        "declared": [
            {"min": [-30.9, 18.9, -39.1], "max": [29.7, 20.1, 10.0], "why": "tops of the plaster walls"},
            {"min": [-0.5, 8.1, -29.5], "max": [0.7, 9.3, -1.0], "why": "the rail along the lane"},
            {"min": [-31.0, 29.1, -40.7], "max": [60.2, 30.3, 11.5], "why": "the tops of the tall outer walls"},
        ],
        # The list maps REFLECTIVITY (a developer pattern) to nothing a player reads; this map's grey
        # panels are drawn as a cool concrete. The source BSP is no longer on disk, so this entry
        # could not be re-checked against a re-import.
        "overrides": [("REFLECTIVITY", "concrete", "#a9aaae")],
    },
    "smallbase": {
        "id": "pgc_smallbase",
        "name": "Small Base",
        "blurb": "A small, lag-free concrete base for building and wiring: a brick-walled yard with a second storey, a grass patch and a small pool.",
        "author": "Rouglead",
        "source": "gm_smallbase, https://gamebanana.com/mods/60684",
        "spawn_at": 0,
        # The tops of the brick walls, which no player is meant to stand on.
        "declared": [
            {"min": [-12.4, 5.0, -12.4], "max": [12.4, 5.4, 12.4], "why": "tops of the upper brick walls"},
        ],
    },
    "mountain_resort": {
        "id": "pgc_mountain_resort",
        "name": "Mountain Resort",
        "blurb": "A snowbound mountain lodge for building and wiring: a small corner of the resort (terraces and the lodge front) around the author spawn, cut from a much larger valley.",
        "author": "prvec",
        "source": "gm_mountainresort, https://steamcommunity.com/sharedfiles/filedetails/?id=2312309380",
        "spawn_at": 24,
        "spawn_pad": True,
        # The valley is far larger than a sandbox needs and the document must stay small.
        "region": ((-81.0, -56.0), (-12.0, 30.0), (-92.0, -52.0)),
        "min_size": 1.0,
        # The lodge (stairs, galleries, a cellar), two ponds made of hundreds of slivers, and a wall of two thin
        # layers: cracks narrower than a player and floors no walk reaches.
        "exclude": [((-81.0, -64.0), (-76.0, -52.0)), ((-64.5, -57.5), (-72.5, -63.5)),
                    ((-64.0, -57.0), (-85.0, -81.0)), ((-75.0, -52.0), (-82.0, -81.0)),
                    ((-81.0, -69.0), (-83.0, -75.0)), ((-63.5, -58.5), (-92.5, -88.5)),
                    ((-62.5, -59.0), (-74.3, -73.1)), ((-62.2, -58.9), (-60.0, -58.8)), ((-63.8, -62.8), (-58.0, -55.3))],
    },
    "mallparking": {
        "id": "pgc_mallparking",
        "name": "Mall Parking",
        "blurb": "A mall car park for building and wiring: the central lot and its shopfront, cut from the larger map.",
        "author": "bean",
        "close_gaps": True, "slab": 15.0,
        "remove": [
            {"min": [-24.1, -1.3, 35.0], "max": [-14.3, -0.5, 35.7], "why": "beams hung from the floor grating across the pit, which split it in two"},
            {"min": [9.7, -9.8, 40.2], "max": [10.1, -7.3, 42.3], "why": "a gate leaf standing shut across the lower tunnel"},
        ],
        "source": "gm_mallparking, https://steamcommunity.com/sharedfiles/filedetails/?id=2619660952",
        "spawn_at": 1,
        "region": ((-41.6, 18.4), (-15.0, 45.0), (-1.7, 58.3)),
        "fill": [{"min": [-45.0, -10.5, 0.0], "max": [15.0, -4.88, 50.0]},
                 {"min": [-2.3, -4.88, -0.1], "max": [2.3, -1.2, 9.8]}, {"min": [-34.6, -4.88, 34.1], "max": [-25.7, -1.2, 37.7]}],
        "declared": [{"min": [-30.0, -5.5, 28.0], "max": [-25.0, -4.0, 29.5], "why": "a sump alcove beside the lower car park"}],
        "min_size": 1.0,
    },
    "shambles": {
        "id": "pgc_shambles",
        "name": "Shambles",
        "blurb": "A run-down settlement sandbox: the area around the author's spawn, cut from a larger map.",
        "author": "Fartomaticatron",
        "close_gaps": True, "slab": 15.0,
        "source": "gm_shambles, https://steamcommunity.com/sharedfiles/filedetails/?id=151544081",
        "spawn_at": 0,
        "region": ((82.0, 192.0), (-15.0, 45.0), (93.0, 203.0)),
        "fill": [{"min": [129.5, -6.5, 96.5], "max": [137.0, -2.0, 149.0], "why": "a cellar trench with no way out"},
                 {"min": [115.3, 0.5, 93.5], "max": [124.0, 2.5, 107.0], "why": "small rooms whose doors are not carried over"}],
        "declared": [{"min": [156.0, 7.8, 127.5], "max": [157.3, 8.6, 130.0], "why": "a roof ledge"},
                     {"min": [145.5, 7.8, 94.3], "max": [147.0, 8.6, 95.8], "why": "a roof ledge"}],
        "min_size": 0.5,
    },
    "valley": {
        "declared": [
            {"min": [112.0, 1.9, 41.5], "max": [139.5, 15.0, 61.0], "why": "the gallery, stair tower and flat roof of the central hall"},
            {"min": [112.0, 1.9, 74.5], "max": [116.5, 2.9, 76.5], "why": "a ledge on the hall's far side"},
        ],
        "fill": [{"min": [105.6, -8.0, 38.4], "max": [107.4, -3.5, 39.6]}],
        "id": "pgc_valley",
        "name": "Valley",
        "blurb": "A grassy valley sandbox: the area around the first spawn, cut from a larger valley.",
        "author": "SuspiciouslyAwesome (Tim Richter)",
        "close_gaps": True, "slab": 15.0,
        "source": "gm_valley, https://steamcommunity.com/sharedfiles/filedetails/?id=104483504",
        "spawn_at": 0,
        "region": ((57.2, 167.2), (-15.0, 45.0), (0.7, 110.7)),
        "min_size": 0.5,
    },
    "deadcity": {
        "declared": [
            {"min": [53.0, 0.9, -98.6], "max": [67.6, 18.0, -84.6], "why": "the far tower block: stair flights, landings and roof, whose risers this converter cuts too tall to climb"},
            {"min": [53.0, 0.9, -64.6], "max": [67.6, 18.0, -50.6], "why": "the near tower block: stair flights, landings and roof"},
            {"min": [-9.0, 9.0, -46.0], "max": [16.2, 12.0, -19.2], "why": "the raised deck above the plaza"},
            {"min": [-31.0, -0.3, -54.0], "max": [-26.5, 0.6, -15.0], "why": "a walled service strip"},
            {"min": [36.2, 2.0, -50.0], "max": [42.0, 2.9, -28.2], "why": "a ledge over the street"},
            {"min": [58.0, -0.2, -33.0], "max": [61.5, 0.5, -32.0], "why": "a sliver of kerb"},
            {"min": [36.0, -0.2, -28.6], "max": [37.0, 0.5, -27.5], "why": "a sliver of kerb"},
            {"min": [-16.0, -2.8, -68.3], "max": [-14.8, -2.0, -66.8], "why": "a drain corner"},
        ],
        "fill": [{"min": [46.8, -4.0, -68.4], "max": [48.1, -0.5, -39.0]}],
        "id": "pgc_deadcity",
        "name": "Dead City",
        "blurb": "A ruined city block, a recreation of a level of S.T.A.L.K.E.R. (GSC Game World) by NuclearGhost: the area around the spawn, cut from the full map.",
        "author": "NuclearGhost",
        "close_gaps": True, "slab": 15.0,
        "source": "rp_deadcity, https://steamcommunity.com/sharedfiles/filedetails/?id=1864156937",
        "spawn_at": 0,
        "region": ((-42.8, 67.2), (-15.0, 45.0), (-142.2, -32.2)),
        "min_size": 0.5,
    },
    "fork": {
        "id": "pgc_fork",
        "name": "Fork",
        "blurb": "A forked-road sandbox: the area around the author's spawn, cut from a larger map.",
        "author": "Blueberry_pie",
        "close_gaps": True, "slab": 15.0,
        "source": "gm_fork, https://steamcommunity.com/sharedfiles/filedetails/?id=326332456",
        "spawn_at": 0,
        "region": ((-55.0, 55.0), (-15.0, 45.0), (232.1, 342.1)),
        "declared": [{"min": [-31.1, 4.4, 247.9], "max": [-21.3, 7.0, 258.3], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-26.6, 7.0, 250.7], "max": [-21.3, 7.6, 254.8], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-29.6, 1.9, 254.4], "max": [-24.3, 2.5, 258.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-30.6, 1.5, 248.2], "max": [-29.3, 2.3, 250.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-61.1, 0.3, 272.4], "max": [-40.8, 0.9, 273.3], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-58.6, -0.3, 272.9], "max": [-24.3, 0.3, 279.3], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-61.1, 0.3, 278.9], "max": [-40.8, 0.9, 280.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}],
        "min_size": 0.5,
    },
    "balkans": {
        "id": "pgc_balkans",
        "name": "Balkans",
        "blurb": "A war-torn village sandbox: the area around the author's spawn, cut from a larger map.",
        "author": "Lg",
        "close_gaps": True, "slab": 15.0,
        "source": "gm_balkans, https://steamcommunity.com/sharedfiles/filedetails/?id=1307357127",
        "spawn_at": 0,
        "spawn_pad": True,
        "region": ((-294.0, -184.0), (-15.0, 45.0), (-308.6, -198.6)),
        "declared": [{"min": [-220.0, 4.4, -271.5], "max": [-205.1, 5.0, -257.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-228.2, -0.6, -273.3], "max": [-202.1, 7.6, -257.2], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-281.0, 2.8, -278.8], "max": [-260.4, 7.5, -257.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-280.5, -0.5, -277.8], "max": [-261.1, 0.1, -257.2], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-274.0, 7.4, -278.0], "max": [-273.4, 8.0, -258.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-268.0, 7.4, -278.0], "max": [-267.4, 8.0, -258.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-202.0, 2.4, -249.0], "max": [-197.4, 3.0, -238.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-201.7, -0.1, -248.0], "max": [-197.6, 0.5, -240.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-254.0, 3.8, -213.8], "max": [-236.1, 6.8, -208.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-256.2, -0.6, -219.5], "max": [-233.9, 0.2, -209.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-254.0, 3.9, -220.5], "max": [-236.1, 6.8, -213.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-259.7, -2.9, -278.3], "max": [-238.9, 1.9, -252.2], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-259.0, 4.3, -261.3], "max": [-247.1, 7.4, -253.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-258.2, 1.9, -260.5], "max": [-247.4, 2.5, -255.2], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-251.2, 1.6, -255.8], "max": [-247.4, 2.5, -253.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-215.7, 1.5, -259.5], "max": [-214.6, 2.1, -258.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-210.7, 1.5, -259.5], "max": [-209.9, 2.1, -258.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-206.0, 1.5, -259.5], "max": [-205.4, 2.1, -258.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-224.5, 8.4, -269.8], "max": [-218.9, 10.1, -264.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-215.7, 2.9, -263.8], "max": [-214.6, 3.8, -260.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-210.7, 2.4, -262.0], "max": [-209.9, 3.8, -260.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-267.5, 6.9, -278.3], "max": [-264.9, 7.5, -277.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-202.5, -0.4, -240.5], "max": [-201.6, 0.2, -239.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}],
        "remove": [{"min": [-215.86, 1.25, -261.05], "max": [-213.07, 4.04, -258.25]}, {"min": [-217.31, 1.25, -261.05], "max": [-214.52, 4.04, -258.25]}, {"min": [-210.98, 1.25, -261.05], "max": [-208.19, 4.04, -258.25]}, {"min": [-212.43, 1.25, -261.05], "max": [-209.64, 4.04, -258.25]}, {"min": [-257.38, 0.55, -255.64], "max": [-255.8, 2.13, -254.06]}, {"min": [-206.11, 1.25, -261.05], "max": [-203.31, 4.04, -258.25]}, {"min": [-222.19, 1.25, -261.05], "max": [-219.39, 4.04, -258.25]}, {"min": [-259.38, 0.55, -255.64], "max": [-257.8, 2.13, -254.06]}],
        "min_size": 0.5,
    },
    "vyten": {
        "id": "pgc_vyten",
        "name": "Vyten",
        "blurb": "A hillside sandbox: the area around the author's spawn, cut from a larger map.",
        "author": "Raxten",
        "close_gaps": True, "slab": 15.0,
        "source": "gm_vyten, https://steamcommunity.com/sharedfiles/filedetails/?id=1449731878",
        "spawn_at": 0,
        "region": ((-253.4, -143.4), (-15.0, 45.0), (129.1, 239.1)),
        "declared": [{"min": [-209.8, 3.8, 172.9], "max": [-188.7, 4.4, 197.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-210.6, 2.0, 190.4], "max": [-209.7, 2.6, 191.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-208.3, -0.4, 183.6], "max": [-206.7, 0.2, 187.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-204.6, -7.8, 192.4], "max": [-197.7, -5.9, 195.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-197.1, 2.0, 193.4], "max": [-196.5, 2.6, 194.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-197.1, 2.0, 176.6], "max": [-196.5, 2.6, 177.2], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.3, -7.8, 177.1], "max": [-189.0, -7.2, 180.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.3, -0.4, 177.1], "max": [-189.0, 0.2, 180.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.3, -7.8, 173.6], "max": [-189.0, -7.2, 176.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.3, -0.4, 173.6], "max": [-189.0, 0.2, 176.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.3, 2.0, 180.1], "max": [-188.7, 2.6, 181.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-192.6, 3.0, 180.9], "max": [-185.0, 3.8, 182.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.6, 2.0, 171.9], "max": [-188.7, 2.6, 173.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-188.8, 2.0, 173.4], "max": [-187.7, 2.6, 180.2], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.3, -7.8, 194.1], "max": [-189.0, -7.2, 197.2], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.3, -0.4, 194.1], "max": [-189.0, 0.2, 197.2], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.3, -7.8, 190.6], "max": [-189.0, -7.2, 193.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.3, -0.4, 190.6], "max": [-189.0, 0.2, 193.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-188.8, 2.0, 190.4], "max": [-187.7, 2.6, 197.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.6, 2.0, 197.4], "max": [-188.7, 2.6, 198.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-192.6, 3.0, 187.9], "max": [-185.0, 3.8, 189.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-191.3, 2.0, 189.6], "max": [-188.7, 2.6, 190.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-262.3, 5.6, 198.6], "max": [-163.2, 6.2, 258.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-262.3, 1.6, 209.4], "max": [-253.7, 2.2, 210.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-262.3, 1.6, 219.1], "max": [-253.7, 2.2, 219.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-262.3, 1.6, 228.9], "max": [-253.7, 2.2, 229.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-262.3, 1.6, 238.6], "max": [-253.7, 2.2, 239.2], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-262.3, 5.6, 112.1], "max": [-163.2, 6.2, 172.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-262.3, 1.6, 131.4], "max": [-253.7, 2.2, 132.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-262.3, 1.6, 141.1], "max": [-253.7, 2.2, 141.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-262.3, 1.6, 150.9], "max": [-253.7, 2.2, 151.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-262.3, 1.6, 160.6], "max": [-253.7, 2.2, 161.2], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-192.8, 4.4, 182.6], "max": [-185.2, 5.0, 188.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-222.8, -6.5, 175.9], "max": [-222.2, -5.9, 177.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-159.3, 18.8, 107.1], "max": [-155.2, 21.3, 263.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-156.1, 18.1, 129.1], "max": [-155.2, 20.0, 137.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-242.2, -0.3, 210.1], "max": [-223.6, 0.3, 219.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-222.7, -0.3, 210.1], "max": [-204.1, 0.3, 219.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-203.2, -0.3, 210.1], "max": [-184.6, 0.3, 219.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-183.7, -0.3, 210.1], "max": [-165.3, 0.3, 219.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-242.2, -0.3, 219.9], "max": [-223.6, 0.3, 228.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-222.7, -0.3, 219.9], "max": [-204.1, 0.3, 228.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-203.2, -0.3, 219.9], "max": [-184.6, 0.3, 228.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-183.7, -0.3, 219.9], "max": [-165.3, 0.3, 228.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-242.2, -0.3, 229.6], "max": [-223.6, 0.3, 238.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-222.7, -0.3, 229.6], "max": [-204.1, 0.3, 238.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-203.2, -0.3, 229.6], "max": [-184.6, 0.3, 238.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-183.7, -0.3, 229.6], "max": [-165.3, 0.3, 238.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-242.2, -0.3, 132.1], "max": [-223.6, 0.3, 141.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-222.7, -0.3, 132.1], "max": [-204.1, 0.3, 141.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-203.2, -0.3, 132.1], "max": [-184.6, 0.3, 141.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-183.7, -0.3, 132.1], "max": [-165.3, 0.3, 141.0], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-242.2, -0.3, 141.9], "max": [-223.6, 0.3, 150.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-222.7, -0.3, 141.9], "max": [-204.1, 0.3, 150.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-203.2, -0.3, 141.9], "max": [-184.6, 0.3, 150.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-183.7, -0.3, 141.9], "max": [-165.3, 0.3, 150.7], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-242.2, -0.3, 151.6], "max": [-223.6, 0.3, 160.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-222.7, -0.3, 151.6], "max": [-204.1, 0.3, 160.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-203.2, -0.3, 151.6], "max": [-184.6, 0.3, 160.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-183.7, -0.3, 151.6], "max": [-165.3, 0.3, 160.5], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}],
        "fill": [{"min": [-222.0, -7.3, 170.4], "max": [-204.8, 0.0, 200.4]}, {"min": [-223.5, -3.6, 171.7], "max": [-197.3, 0.0, 198.9]}, {"min": [-197.8, -4.8, 171.7], "max": [-188.5, 0.0, 198.9]}, {"min": [-197.5, -8.5, 171.9], "max": [-191.0, 0.0, 198.7]}, {"min": [-204.8, -8.5, 174.7], "max": [-197.5, 0.0, 178.9]}, {"min": [-191.8, -4.2, 173.2], "max": [-188.5, 0.0, 180.4]}, {"min": [-191.5, -6.0, 179.9], "max": [-188.5, 0.0, 181.4]}, {"min": [-191.5, -6.0, 171.7], "max": [-188.5, 0.0, 173.7]}, {"min": [-189.0, -6.0, 173.2], "max": [-187.5, 0.0, 180.4]}, {"min": [-191.8, -4.2, 190.2], "max": [-188.5, 0.0, 197.7]}, {"min": [-189.0, -6.0, 190.2], "max": [-187.5, 0.0, 197.7]}, {"min": [-191.5, -6.0, 197.2], "max": [-188.5, 0.0, 198.9]}, {"min": [-191.5, -6.0, 189.2], "max": [-188.5, 0.0, 190.7]}, {"min": [-262.5, -8.5, 198.7], "max": [-164.5, 0.0, 258.9]}, {"min": [-262.5, -8.5, 111.9], "max": [-164.5, 0.0, 171.9]}, {"min": [-191.5, -8.1, 181.4], "max": [-189.0, 0.0, 189.2]}, {"min": [-204.8, -6.3, 173.7], "max": [-202.0, 0.0, 175.2]}, {"min": [-205.8, -6.3, 174.9], "max": [-204.8, 0.0, 176.4]}, {"min": [-205.8, -6.3, 194.4], "max": [-204.8, 0.0, 195.9]}, {"min": [-204.8, -6.3, 195.7], "max": [-202.0, 0.0, 197.2]}, {"min": [-223.0, -7.2, 192.7], "max": [-222.0, 0.0, 195.4]}, {"min": [-204.9, -9.0, 192.2], "max": [-197.4, 0.0, 195.7]}, {"min": [-223.4, -9.0, 175.7], "max": [-221.9, 0.0, 177.9]}],
        "min_size": 0.5,
    },
    "southside": {
        "id": "pgc_southside",
        "name": "South Side",
        "blurb": "A city district sandbox of streets and alleys: the area around the author's spawn, cut from a larger map.",
        "author": "Fishke",
        "close_gaps": True, "slab": 15.0,
        "source": "rp_southside, https://steamcommunity.com/sharedfiles/filedetails/?id=2010286798",
        "spawn_at": 0,
        "region": ((-42.5, 67.5), (-15.0, 45.0), (-65.4, 44.6)),
        "declared": [{"min": [65.7, 13.8, -62.2], "max": [66.5, 14.4, -43.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-34.3, 8.2, 21.5], "max": [-3.5, 11.9, 47.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [19.4, 7.8, 19.3], "max": [36.8, 8.4, 44.1], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [19.9, -0.2, 19.8], "max": [21.3, 0.4, 28.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-33.8, -0.2, 23.3], "max": [-5.0, 0.4, 45.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-31.8, 4.1, -12.5], "max": [-19.2, 4.7, 2.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-19.6, 11.4, -12.5], "max": [-3.5, 12.0, 2.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-19.6, 15.1, -39.2], "max": [-3.5, 15.7, -15.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-24.3, 15.1, -62.2], "max": [-7.2, 15.7, -44.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-9.8, 3.3, -61.5], "max": [-9.0, 3.9, -60.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-21.8, 9.0, -58.2], "max": [-14.7, 9.6, -57.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-21.8, 9.0, -57.2], "max": [-14.7, 9.6, -56.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-16.1, 8.1, -56.7], "max": [-14.7, 8.7, -56.1], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-39.1, 11.4, -66.0], "max": [-3.5, 12.2, -39.1], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-22.1, 10.8, -41.5], "max": [-19.5, 11.4, -38.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-39.1, 16.3, -66.0], "max": [-24.2, 16.9, -53.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [13.2, 21.2, -66.0], "max": [44.0, 21.8, -44.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [31.2, 24.5, -62.2], "max": [38.0, 25.1, -54.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [24.4, 7.4, -61.7], "max": [32.3, 8.0, -59.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [24.4, 12.4, -61.7], "max": [32.3, 13.0, -59.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [24.4, 17.4, -61.7], "max": [34.8, 18.0, -59.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [26.7, -8.7, -59.7], "max": [30.0, -8.1, -56.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [26.7, -2.0, -59.7], "max": [30.0, -1.4, -56.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [14.2, 9.9, -65.5], "max": [43.5, 10.5, -45.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [14.2, 14.9, -65.5], "max": [43.5, 15.5, -45.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [14.2, 17.6, -65.7], "max": [25.0, 18.5, -45.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [18.7, 7.5, -65.5], "max": [23.0, 8.3, -59.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [18.7, 12.6, -65.5], "max": [23.0, 13.3, -59.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [23.9, 10.3, -63.0], "max": [24.5, 10.9, -61.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [21.9, 7.8, -60.0], "max": [22.5, 8.4, -56.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [21.9, 12.8, -60.0], "max": [22.5, 13.4, -56.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [21.9, 17.8, -60.0], "max": [22.5, 18.4, -56.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [14.4, 7.5, -55.5], "max": [18.5, 8.4, -45.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [14.4, 12.6, -55.5], "max": [18.5, 13.4, -45.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [21.9, 7.5, -53.5], "max": [25.0, 8.4, -50.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [21.9, 12.6, -53.5], "max": [25.0, 13.4, -50.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [44.9, 6.5, 26.3], "max": [70.3, 10.5, 44.1], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [44.9, 6.5, 24.3], "max": [70.3, 7.7, 26.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [45.7, -0.8, 25.0], "max": [70.0, -0.2, 43.1], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-26.3, 8.7, -58.5], "max": [-23.5, 9.7, -56.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-37.8, 7.1, -65.5], "max": [-25.7, 11.4, -56.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-33.1, 8.4, -59.2], "max": [-27.5, 9.0, -57.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-27.3, 7.5, -57.7], "max": [-26.7, 8.1, -57.1], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [32.4, 7.8, -53.5], "max": [34.8, 8.4, -50.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [32.4, 12.8, -53.5], "max": [34.8, 13.4, -50.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [32.4, 17.6, -53.5], "max": [42.8, 18.5, -45.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [32.7, 7.4, -65.5], "max": [43.3, 8.3, -56.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [34.2, 7.8, -60.2], "max": [34.8, 8.4, -56.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [34.2, 12.8, -60.0], "max": [34.8, 13.4, -56.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [32.2, 17.6, -65.5], "max": [43.3, 18.5, -55.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [37.9, 7.8, -60.0], "max": [42.8, 8.4, -50.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [37.9, 12.8, -60.0], "max": [42.8, 13.4, -55.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [39.2, 7.5, -50.5], "max": [42.8, 8.3, -45.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [39.2, 12.6, -50.5], "max": [42.8, 13.3, -45.9], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [32.9, 12.6, -65.5], "max": [43.3, 13.3, -60.1], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [34.7, 18.9, -61.7], "max": [36.8, 19.9, -57.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-12.6, -3.7, -64.0], "max": [-11.0, -3.1, -62.1], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-23.6, 8.1, -57.7], "max": [-22.7, 8.7, -57.1], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [-4.2, 0.9, 22.3], "max": [-3.1, 1.5, 23.4], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}, {"min": [19.8, -0.3, 19.8], "max": [25.4, 0.4, 37.6], "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"}],
        "fill": [{"min": [-15.5, -4.5, -44.2], "max": [16.5, 0.0, -25.9]}, {"min": [2.7, -8.8, -65.7], "max": [85.7, 0.0, -30.7]}, {"min": [11.7, -6.1, -65.7], "max": [85.7, 0.0, -30.7]}, {"min": [3.2, -10.6, -0.9], "max": [35.7, 0.0, 54.6]}, {"min": [-4.0, -10.2, -26.4], "max": [34.5, 0.0, 56.6]}, {"min": [-3.3, -13.1, -43.9], "max": [34.2, 0.0, 56.6]}, {"min": [-4.5, -10.6, -0.4], "max": [28.2, 0.0, 54.6]}, {"min": [-3.5, -5.1, -44.9], "max": [3.5, 0.0, -43.7]}, {"min": [-50.5, -8.8, -65.9], "max": [-2.8, 0.0, -16.9]}, {"min": [-3.5, -5.1, -26.4], "max": [3.5, 0.0, -25.2]}, {"min": [-47.3, -6.1, -65.9], "max": [-14.5, 0.0, -16.9]}, {"min": [-38.0, -4.4, -67.9], "max": [-16.8, 0.0, -53.9]}, {"min": [-17.8, -4.4, -61.4], "max": [-10.8, 0.0, -56.9]}, {"min": [-27.0, -8.8, -64.2], "max": [-25.8, 0.0, -56.4]}, {"min": [-19.3, -5.6, -65.7], "max": [-14.5, 0.0, -64.7]}, {"min": [7.0, -5.6, -41.9], "max": [12.2, 0.0, -37.9]}, {"min": [48.77, -0.12, -51.079], "max": [52.43, 0.28, -50.8]}, {"min": [48.77, -0.09, -52.508], "max": [52.43, 0.31, -52.221]}, {"min": [58.52, -7.66, -57.727], "max": [62.18, -7.26, -57.45]}, {"min": [58.52, -7.5, -61.968], "max": [62.18, -7.1, -61.691]}, {"min": [-3.05, -8.04, -24.457], "max": [3.05, -7.64, -24.18]}, {"min": [48.72, -0.17, -54.55], "max": [52.48, 0.5, -50.47]}, {"min": [58.47, -7.77, -58.91], "max": [62.23, -7.16, -55.988]}, {"min": [58.47, -7.6, -63.15], "max": [62.23, -6.99, -60.228]}, {"min": [-3.1, -8.15, -25.083], "max": [3.1, -7.53, -23.85]}],
        "remove": [{"min": [48.74, -0.15, -54.53], "max": [52.46, 0.48, -50.49]}, {"min": [58.49, -7.75, -58.89], "max": [62.21, -7.18, -56.008]}, {"min": [58.49, -7.58, -63.13], "max": [62.21, -7.01, -60.248]}, {"min": [-3.08, -8.13, -25.063], "max": [3.08, -7.55, -23.87]}],
        "min_size": 0.5,
    },
    "asheville": {
        "id": "pgc_asheville",
        "name": "Asheville",
        "blurb": "A small-town sandbox: the area around the author's spawn, cut from a larger map.",
        "author": "VanderAGSN",
        "close_gaps": True, "slab": 15.0,
        "source": "rp_asheville, https://steamcommunity.com/sharedfiles/filedetails/?id=2595136841",
        "declared": [
            {"min": [-235.9, 3.2, -174.9], "max": [-214.2, 4.4, -170.4], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-235.9, 5.3, -172.6], "max": [-214.2, 8.3, -167.2], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-235.9, 5.3, -178.1], "max": [-214.2, 8.2, -174.2], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-235.9, 5.9, -176.6], "max": [-214.2, 8.3, -172.7], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-224.1, 2.1, -189.9], "max": [-214.7, 3.3, -183.4], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-207.1, 3.1, -169.9], "max": [-185.4, 4.3, -145.4], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-206.6, -0.2, -169.1], "max": [-185.9, 1.0, -145.9], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-199.4, 6.5, -196.4], "max": [-187.4, 7.7, -176.9], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-198.9, 2.6, -196.4], "max": [-187.9, 5.1, -177.4], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-201.1, 0.2, -198.4], "max": [-185.4, 3.2, -175.2], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-174.1, 5.8, -228.4], "max": [-164.4, 7.0, -221.7], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-169.1, 2.7, -141.9], "max": [-167.9, 3.9, -129.2], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-201.4, 2.9, -144.4], "max": [-192.2, 4.1, -131.4], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-201.4, 0.5, -144.4], "max": [-188.9, 1.7, -131.9], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-235.9, 1.5, -166.1], "max": [-213.9, 3.6, -162.9], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-235.9, 1.7, -181.9], "max": [-213.9, 3.6, -179.2], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-231.1, 0.6, -201.9], "max": [-225.7, 1.8, -196.7], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-225.4, 22.5, -163.9], "max": [-217.4, 25.9, -146.9], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-194.9, 3.4, -229.6], "max": [-184.4, 4.6, -219.2], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-172.1, 0.4, -139.1], "max": [-168.2, 1.6, -132.2], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-172.4, -0.2, -136.6], "max": [-170.4, 1.0, -134.7], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-190.6, -0.1, -138.9], "max": [-188.9, 1.1, -136.9], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-169.6, 0.6, -168.6], "max": [-167.4, 1.8, -166.9], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-169.6, 0.0, -168.6], "max": [-165.4, 1.2, -164.9], "why": "building interior and yard ground the survey cannot reach"},
            {"min": [-169.6, 0.6, -166.6], "max": [-167.4, 1.8, -165.2], "why": "building interior and yard ground the survey cannot reach"},
        ],
        "spawn_at": 0,
        "region": ((-277.4, -167.4), (-15.0, 45.0), (-226.0, -116.0)),
        "min_size": 0.5,
    },
    "boreas": {
        "id": "pgc_boreas",
        "name": "Boreas",
        "blurb": "A snowy valley sandbox: rolling snowfields and the buildings around the author's spawn, cut from a larger map.",
        "author": "Blueberry_pie",
        "close_gaps": True, "slab": 15.0,
        "source": "gm_boreas, https://steamcommunity.com/sharedfiles/filedetails/?id=1572373847",
        "spawn_at": 2,
        # Cut short of the valley's far bank, a hollow behind cliff columns nobody climbs out of.
        "region": ((-148.9, -38.9), (-8.0, 55.0), (96.2, 186.0)),
        # The hut's arch trusses (0.03 m ribs stacked in steps) leave cracks under its roof; its end
        # wall and corner post stop a hand short of the snow slab they stand on. Both are rebuilt
        # whole, the wall to its full height and the post down to the slab's edge.
        "remove": [
            {"min": [-76.0, 3.5, z - 0.15], "max": [-63.0, 5.6, z + 0.15], "why": "arch truss ribs under the hut roof"}
            for z in (145.4, 148.4, 151.49, 154.53)
        ] + [
            {"min": [-80.7, -1.0, 155.85], "max": [-58.6, 4.5, 156.1], "why": "the hut end wall's stepped arch pieces"},
        ] + [
            {"min": [x - 0.12, -1.0, 143.8], "max": [x + 0.12, 4.1, 143.99], "why": "the hut's corner posts"}
            for x in (-82.865, -58.56)
        ],
        "fill": [
            {"min": [-80.92, -0.9, 155.9], "max": [-58.64, 4.46, 156.06], "material": "metal", "colour": "#7d8086"},
        ] + [
            {"min": [x - 0.08, -0.9, 143.83], "max": [x + 0.08, 4.02, 144.02], "material": "metal", "colour": "#7d8086"}
            for x in (-82.865, -58.56)
        ],
        # The valley floor is displacement terrain: laid as tilted snow slabs on a 3 m grid.
        "terrain": {"cell": 3.0, "material": "snow", "thick": 1.0},
        "declared": [{"min": lo, "max": hi, "why": "the hut roof, which the author reaches by props the converter does not carry (surveyed unreached, not a trap)"} for lo, hi in (
            ([-83.5, 3.7, 143.2], [-57.9, 6.0, 156.6]),
            ([-85.5, 1.0, 145.0], [-83.1, 1.9, 150.1]),
        )],
        "min_size": 0.5,
    },
    "bigisland": {
        "id": "pgc_bigisland",
        "name": "Big Island",
        "blurb": "A tropical island sandbox: beach, dunes and the ground around the author's spawn, cut from a larger map.",
        "author": "Comrade Stinger and Hiyu",
        "close_gaps": True, "slab": 15.0,
        "source": "gm_bigisland, https://steamcommunity.com/sharedfiles/filedetails/?id=169600867",
        "spawn_at": 0,
        "region": ((-117.8, -7.8), (-20.0, 45.0), (-118.9, -8.9)),
        # The island is displacement terrain: laid as tilted grass slabs on a 3 m grid.
        "terrain": {"cell": 3.0, "material": "grass", "thick": 1.0},
        "declared": [{"min": lo, "max": hi, "why": "island ground the cut leaves behind a dune or cliff no walk climbs (surveyed unreached, not a trap)"} for lo, hi in (
            ([-120.3, 5.6, -120.2], [-114.2, 7.5, -57.0]),
            ([-75.6, 10.0, -120.2], [-56.9, 15.3, -107.8]),
            ([-65.8, 11.4, -120.2], [-62.9, 12.0, -117.0]),
            ([-39.1, 13.6, -116.9], [-36.2, 14.2, -114.0]),
            ([-117.1, 10.4, -111.2], [-114.2, 11.0, -108.3]),
            ([-56.8, 11.9, -111.2], [-53.9, 12.5, -108.3]),
            ([-36.1, 16.0, -120.2], [-32.9, 16.6, -114.0]),
            ([-33.1, 14.3, -114.2], [-30.2, 14.9, -111.0]),
            ([-57.1, 13.7, -108.2], [-53.9, 14.3, -105.0]),
            ([-53.8, 11.6, -108.2], [-50.9, 12.2, -105.3]),
            ([-24.1, 15.7, -111.2], [-17.4, 18.7, -107.8]),
            ([-24.1, 18.8, -108.2], [-20.9, 19.4, -102.0]),
            ([-30.1, 16.3, -105.2], [-27.2, 16.9, -102.3]),
            ([-30.1, 16.9, -102.2], [-27.2, 17.5, -99.3]),
            ([-30.1, 17.6, -99.2], [-23.9, 18.2, -96.0]),
            ([-54.1, 14.8, -102.2], [-50.9, 15.4, -96.0]),
            ([-33.1, 15.9, -96.2], [-26.9, 16.8, -84.0]),
            ([-30.1, 18.5, -96.2], [-26.9, 19.1, -90.0]),
            ([-57.1, 14.2, -96.2], [-53.9, 14.8, -93.0]),
            ([-12.1, 13.8, -95.9], [-8.9, 14.4, -93.0]),
            ([-60.1, 13.5, -93.2], [-56.9, 14.1, -90.0]),
            ([-21.3, 7.6, -93.2], [-18.2, 8.7, -90.3]),
            ([-18.1, 18.7, -93.2], [-11.9, 19.3, -90.0]),
            ([-21.1, 15.2, -90.2], [-14.9, 15.8, -84.0]),
            ([-26.8, 7.8, -90.2], [-21.2, 9.5, -87.3]),
            ([-30.1, 18.9, -87.2], [-23.9, 19.5, -81.0]),
            ([-23.8, 18.4, -87.2], [-20.9, 19.0, -81.0]),
            ([-20.8, 11.7, -86.9], [-18.2, 12.5, -84.3]),
            ([-20.8, 15.0, -84.2], [-17.9, 15.6, -81.0]),
            ([-33.1, 15.3, -83.9], [-30.2, 15.9, -81.0]),
            ([-63.1, 13.4, -83.9], [-59.9, 14.0, -81.0]),
            ([-27.1, 14.3, -80.9], [-20.9, 14.9, -78.0]),
            ([-117.1, 9.9, -80.9], [-113.9, 11.0, -69.3]),
            ([-117.1, 10.8, -69.2], [-110.9, 11.5, -60.0]),
            ([-81.1, 10.1, -72.2], [-78.2, 10.7, -69.0]),
            ([-78.1, 11.2, -72.2], [-62.9, 12.3, -69.0]),
            ([-83.8, 3.1, -68.9], [-80.9, 3.7, -66.0]),
            ([-95.8, 8.5, -68.9], [-92.9, 9.1, -66.0]),
            ([-92.8, 6.8, -68.9], [-89.9, 7.4, -66.0]),
            ([-89.8, 5.4, -68.9], [-86.9, 6.0, -66.0]),
            ([-95.8, 3.4, -65.9], [-92.9, 4.0, -63.0]),
            ([-86.8, 4.4, -68.9], [-83.9, 5.0, -66.0]),
            ([-105.1, 11.4, -66.2], [-101.9, 12.0, -63.0]),
            ([-101.8, 7.0, -65.9], [-98.9, 7.6, -63.0]),
            ([-104.8, 2.9, -62.9], [-101.9, 3.5, -60.0]),
            ([-98.8, 4.6, -65.9], [-95.9, 5.2, -63.0]),
            ([-110.8, 4.6, -63.2], [-104.9, 5.2, -60.0]),
            ([-116.8, 5.3, -59.9], [-113.9, 5.9, -57.0]),
            ([-9.1, 13.9, -27.2], [-5.9, 14.5, -24.3]),
            ([-9.1, 16.2, -24.2], [-5.9, 16.8, -21.3]),
            ([-12.1, 13.9, -21.2], [-9.2, 14.5, -18.3]),
            ([-12.1, 16.2, -18.2], [-8.9, 16.8, -15.3]),
            ([-9.1, 18.8, -21.2], [-5.9, 19.4, -18.0]),
            ([-12.1, 19.5, -15.2], [-8.9, 20.1, -12.0]),
            ([-15.1, 18.5, -12.2], [-11.9, 19.1, -9.0]),
            ([-114.1, 10.9, -120.2], [-111.2, 11.5, -117.3]),
            ([-111.1, 13.4, -120.2], [-107.9, 14.0, -117.0]),
            ([-42.1, 15.5, -120.2], [-36.2, 16.1, -117.0]),
            ([-114.1, 11.7, -117.2], [-110.9, 12.3, -114.3]),
            ([-114.1, 12.5, -114.2], [-110.9, 13.1, -111.3]),
            ([-30.1, 16.7, -114.2], [-26.9, 17.3, -111.0]),
            ([-114.1, 13.7, -111.2], [-110.9, 14.3, -108.0]),
            ([-30.1, 13.2, -110.9], [-27.2, 13.8, -108.0]),
            ([-27.1, 14.3, -111.2], [-24.2, 14.9, -108.3]),
            ([-117.1, 11.6, -108.2], [-113.9, 12.2, -105.3]),
            ([-27.1, 17.1, -108.2], [-24.2, 17.7, -105.3]),
            ([-117.1, 12.2, -105.2], [-113.9, 13.1, -96.3]),
            ([-54.1, 13.2, -105.2], [-50.9, 13.8, -102.3]),
            ([-27.1, 18.0, -105.2], [-23.9, 18.6, -99.0]),
            ([-12.1, 17.4, -99.2], [-8.9, 18.0, -96.0]),
            ([-117.1, 13.0, -96.2], [-113.9, 13.6, -87.0]),
            ([-63.1, 15.9, -90.2], [-59.9, 16.5, -84.0]),
            ([-59.8, 12.3, -89.9], [-56.9, 12.9, -87.0]),
            ([-117.1, 12.3, -86.9], [-113.9, 12.9, -84.0]),
            ([-117.1, 11.6, -83.9], [-113.9, 12.2, -81.0]),
            ([-66.1, 13.2, -75.2], [-62.9, 13.8, -72.0]),
            ([-99.1, 12.0, -72.2], [-95.9, 12.6, -69.0]),
            ([-95.8, 10.7, -72.2], [-92.9, 11.3, -69.0]),
            ([-92.8, 9.5, -72.2], [-89.9, 10.1, -69.0]),
            ([-89.8, 8.7, -72.2], [-81.2, 9.5, -69.0]),
            ([-102.1, 11.2, -69.2], [-98.9, 11.8, -66.0]),
            ([-98.8, 10.1, -68.9], [-95.9, 10.7, -66.0]),
        )],
        "min_size": 0.5,
    },
    "rooftops": {
        "id": "pgc_rooftops",
        "name": "Rooftops",
        "blurb": "A cluster of city rooftops joined by ladders, planks and walkways above the streets: the area around the author's spawn.",
        "author": "youmenow1",
        "close_gaps": True, "slab": 15.0,
        "source": "ttt_rooftops_2016, https://steamcommunity.com/sharedfiles/filedetails/?id=534491717",
        "spawn_at": 0,
        # The street is 30 m below the roofs with no way back up: cut, so a fall off a roof is a
        # fall out of the map and a respawn, as in the original round, not a pit to stand in.
        "region": ((-55.2, 54.8), (-20.0, 45.0), (-52.6, 57.4)),
        "remove": [
            {"min": [46.0, -14.5, -12.6], "max": [54.3, -3.6, 5.2], "why": "ledge bands round a tower's walls, each a sill a fall lands on and cannot leave"},
            {"min": [47.1, -9.2, -41.3], "max": [51.6, -3.6, -36.7], "why": "the scaffold's cross beams under the catwalk, the same"},
            {"min": [14.3, 15.0, 20.7], "max": [14.95, 16.45, 20.9], "why": "a shutter leaving a crack against the wall"},
            {"min": [14.3, 10.2, 20.7], "max": [16.2, 11.52, 20.9], "why": "a door leaf standing shut"},
            {"min": [37.3, 6.1, -2.35], "max": [39.1, 8.2, -2.25], "why": "a sheet leaving a crack against the wall"},
        ] + [
            {"min": [x - 1.0, -2.4, 15.4], "max": [x + 1.0, 0.4, 20.2], "why": "a skylight's A-frame panels, laid as a solid ridge"}
            for x in (-8.23, -18.595)
        ],
        "fill": [
            {"min": [x - 0.91, 0.0, 16.9], "max": [x + 0.91, 1.0, 19.7]} for x in (-8.23, -18.595)
        ] + [
            # A wall step the ledge stands out from: built up flush with the roof above it.
            {"min": [58.52, -4.27, -18.9], "max": [62.18, 1.22, -17.68]},
        ],
        "declared": [{"min": lo, "max": hi, "why": "a roof, ledge or room the converter leaves without a climb or a door (surveyed unreached, not a trap)"} for lo, hi in (
            ([3.6, 2.3, -3.7], [6.2, 3.4, 0.2]),
            ([19.6, 5.6, -8.7], [41.5, 10.1, 7.4]),
            ([19.6, 8.3, -53.7], [27.0, 8.9, -48.8]),
            ([19.6, 13.1, -51.2], [25.7, 13.8, -43.8]),
            ([29.3, 13.2, -41.5], [55.0, 13.9, -21.3]),
            ([42.1, 23.0, -29.2], [47.7, 23.6, -23.1]),
            ([47.8, 20.5, -27.5], [53.2, 21.1, -24.8]),
            ([44.6, 28.4, -26.5], [45.0, 29.0, -26.1]),
            ([50.6, 12.6, 21.8], [51.5, 13.2, 26.9]),
            ([13.3, 17.3, 20.5], [17.2, 19.0, 24.7]),
            ([13.8, 12.0, 21.0], [16.7, 12.6, 23.9]),
            ([13.8, 14.4, 21.0], [16.7, 15.0, 23.9]),
            ([47.1, 37.5, -2.0], [53.2, 39.2, 0.4]),
            ([32.3, 18.1, -40.5], [33.2, 18.7, -37.6]),
            ([36.3, 8.5, -2.7], [39.2, 10.0, 1.4]),
            ([27.1, 3.0, -4.5], [34.0, 3.6, -0.8]),
            ([27.1, 3.0, -0.5], [34.0, 3.6, 3.2]),
            ([31.1, 17.1, -33.0], [31.5, 17.7, -30.3]),
            ([29.8, 18.1, -33.0], [30.7, 18.7, -30.3]),
            ([34.8, 18.1, -33.0], [35.7, 18.7, -30.3]),
            ([47.8, 9.6, -37.2], [48.5, 10.2, -36.8]),
            ([49.1, 9.6, -37.2], [49.7, 10.2, -36.8]),
            ([50.3, 9.6, -37.2], [51.0, 10.2, -36.8]),
            ([47.8, 9.6, -41.2], [48.5, 10.2, -40.8]),
            ([50.3, 9.6, -41.2], [51.0, 10.2, -40.8]),
            ([51.8, 15.7, 20.0], [52.7, 16.5, 28.7]),
            ([53.3, 18.3, 20.0], [53.7, 18.9, 28.7]),
            ([53.8, 19.3, 20.0], [54.7, 19.9, 28.7]),
            ([54.3, 20.6, 24.8], [55.0, 21.2, 26.2]),
            ([18.8, 12.8, -47.7], [19.7, 13.8, -47.3]),
            ([18.8, 12.8, -50.2], [19.7, 13.8, -49.8]),
        )],
        "min_size": 0.5,
    },
}

WATER = 0x20


TEXTURE_MAP = texturemap.load()


def material_for(cfg, names):
    # The majority pick (sorted, so a tie follows the name, not the hash seed) is dot-map's. The map's own
    # overrides are tried first; then the shared list, whose generic id the game turns into its own.
    pick = docboxes.majority_material(names, cfg.get("overrides", []), None)
    if pick is not None or not [n for n in names if not n.startswith("TOOLS/")]:
        return pick
    hit = docboxes.majority_material(names, TEXTURE_MAP, ("", None))
    if not hit[0]:
        return ("concrete", None)             # a texture the list does not map, or maps to nothing
    mat, colour = GAME_MATERIAL.get(hit[0], (hit[0], None))
    return (mat, colour)


def ramp_document_box(rb, mat, colour, y_off):
    """The document box for a [method ramp_box]: its top face is the sloped face, dropped along
    its own normal by half the thickness."""
    x0, x1, y0, y1, za, zb, base, ang, axis, sign = rb
    run = (x1 - x0) if axis == "x" else (y1 - y0)
    width = (y1 - y0) if axis == "x" else (x1 - x0)
    length = math.hypot(run, abs(zb - za))
    thick = max((max(za, zb) - base) * math.cos(math.radians(ang)), 8.0)
    # Surface midpoint, source units, then the normal in godot axes (x, z, -y).
    mx, my, mz = (x0 + x1) / 2, (y0 + y1) / 2, (za + zb) / 2
    t = math.radians(ang) * sign
    if axis == "x":
        n = (-math.sin(t), math.cos(t), 0.0)
        size = [length, thick, width]
        turn = [0, 0, 1, round(math.degrees(t), 2)]
    else:
        n = (0.0, math.cos(t), -math.sin(t))
        size = [width, thick, length]
        turn = [1, 0, 0, round(math.degrees(t), 2)]
    top = (mx * S, mz * S - y_off, -my * S)
    at = [round(top[k] - n[k] * thick * S / 2, 3) for k in range(3)]
    b = {"at": at, "size": [round(v * S, 3) for v in size], "material": mat, "turn": turn}
    if colour:
        b["colour"] = colour
    return b


def snap(b, grid=0.01):
    """Round an upright box's faces to a grid, so two brushes that meet in the author's map meet
    here: a face 0.4 mm short of its neighbour is a crack the survey reads as a slot."""
    if "turn" in b and b["turn"][3]:
        return b
    for k in range(3):
        lo = round((b["at"][k] - b["size"][k] / 2) / grid) * grid
        hi = round((b["at"][k] + b["size"][k] / 2) / grid) * grid
        if hi > lo:
            b["at"][k], b["size"][k] = round((lo + hi) / 2, 3), round(hi - lo, 3)
    return b


def stair_boxes(fl):
    """A flight of real steps (document frame, metres) that joins two levels the author joined with
    something the document cannot carry: a door, a displacement ramp, a prop. `from` is the top
    surface of the higher level at its edge, `dir` the horizontal way the flight runs (one of
    (+-1, 0) or (0, +-1)), `steps` how many, each `riser` lower and `tread` longer than the last,
    `width` across, and `base` the level every step is built down to (the lower floor, so the
    flight stands on it and does not hang over a drop)."""
    x, y, z = fl["from"]
    dx, dz = fl["dir"]
    w, riser, tread, base = fl["width"], fl["riser"], fl["tread"], fl["base"]
    out = []
    for k in range(1, fl["steps"] + 1):
        top = y - k * riser
        c0, c1 = 0.125 + (k - 1) * tread, 0.125 + k * tread
        if dx:
            a, b = sorted((x + dx * c0, x + dx * c1))
            lo, hi = [a, base, z - w / 2], [b, top, z + w / 2]
        else:
            a, b = sorted((z + dz * c0, z + dz * c1))
            lo, hi = [x - w / 2, base, a], [x + w / 2, top, b]
        out.append(snap({"at": [round((lo[i] + hi[i]) / 2, 3) for i in range(3)],
                         "size": [round(hi[i] - lo[i], 3) for i in range(3)],
                         "material": "concrete", "colour": "#a8a49a"}))
    return out


def _carve(b, lo, hi):
    """The pieces of an upright box b left when the volume lo..hi is taken out of it."""
    bl = [b["at"][i] - b["size"][i] / 2 for i in range(3)]
    bh = [b["at"][i] + b["size"][i] / 2 for i in range(3)]
    if any(bl[i] >= hi[i] - 1e-6 or bh[i] <= lo[i] + 1e-6 for i in range(3)):
        return [b]
    pieces, cl, ch = [], list(bl), list(bh)
    for i in range(3):
        for (a, c) in ((bl[i], lo[i]), (hi[i], bh[i])):
            if c - a > 0.02:
                pl, ph = list(cl), list(ch)
                pl[i], ph[i] = a, c
                p = dict(b)
                p["at"] = [round((pl[k] + ph[k]) / 2, 3) for k in range(3)]
                p["size"] = [round(ph[k] - pl[k], 3) for k in range(3)]
                pieces.append(p)
        cl[i], ch[i] = max(cl[i], lo[i]), min(ch[i], hi[i])
    return pieces


def add_stairs(boxes, flights):
    """Builds the flights and cuts each one's head room out of the upright boxes it passes through
    (a stair that goes down through a floor has a stairwell). Tilted boxes are never cut."""
    steps = [stair_boxes(fl) for fl in flights]
    for fl, flight in zip(flights, steps):
        for st in flight:
            lo = [st["at"][i] - st["size"][i] / 2 for i in range(3)]
            hi = [st["at"][i] + st["size"][i] / 2 for i in range(3)]
            lo[1], hi[1] = hi[1] + 0.05, hi[1] + 1.9
            cut = []
            for b in boxes:
                cut.extend(_carve(b, lo, hi) if not (b.get("turn") and b["turn"][3]) else [b])
            boxes = cut
    for flight in steps:
        boxes.extend(flight)
    return boxes


def weld_hairlines(boxes, eps=0.03):
    """Two upright boxes that meet at a corner or a face with a hairline between them (a rounding of a
    few thousandths of a metre) read to the survey as a slot. Grow the second across the hairline."""
    up = [b for b in boxes if "turn" not in b]
    for i, a in enumerate(up):
        for b in up[i + 1:]:
            lo_a = [a["at"][k] - a["size"][k] / 2 for k in range(3)]
            hi_a = [a["at"][k] + a["size"][k] / 2 for k in range(3)]
            lo_b = [b["at"][k] - b["size"][k] / 2 for k in range(3)]
            hi_b = [b["at"][k] + b["size"][k] / 2 for k in range(3)]
            if min(hi_a[1], hi_b[1]) - max(lo_a[1], lo_b[1]) <= 0.4:
                continue
            for k in (0, 2):
                g = max(lo_b[k] - hi_a[k], lo_a[k] - hi_b[k])
                other = 2 - k
                og = max(lo_b[other] - hi_a[other], lo_a[other] - hi_b[other])
                if 0 < g < eps and og < eps:
                    # grow b toward a along k
                    if lo_b[k] >= hi_a[k]:
                        lo_b[k] -= g + 0.004
                    else:
                        hi_b[k] += g + 0.004
                    b["at"][k] = round((lo_b[k] + hi_b[k]) / 2, 4)
                    b["size"][k] = round(hi_b[k] - lo_b[k], 4)


def terrain_boxes(bsp, cfg, y_off):
    """The map's displacements inside the region as tilted slabs (see the module doc)."""
    t = cfg["terrain"]
    region = cfg.get("region")
    tris = terrain.game_tris(terrain.terrain_tris(bsp), S, y_off)
    if region:
        tris = [tr for tr in tris if any(region[0][0] <= p[0] <= region[0][1] and region[2][0] <= p[2] <= region[2][1]
                                         and region[1][0] <= p[1] <= region[1][1] for p in tr)]
    if not tris:
        return []
    bounds = (region[0][0], region[2][0], region[0][1], region[2][1]) if region else None
    hf = terrain.Heightfield.from_tris(tris, float(t.get("cell", 2.0)), bounds=bounds)
    out = []
    # A cell steeper than max_slope stands as an upright column: two tilted slabs of very different
    # slope meet in plan with a sliver between them, which the survey reads as a slot.
    for b in terrain.tilted_tiles(hf, thick=float(t.get("thick", 1.0)), pad=float(t.get("pad", 0.1)),
                                    max_slope=float(t.get("max_slope", 0.8)), cliff_columns=True):
        b["material"] = t.get("material", "grass")
        if t.get("colour"):
            b["colour"] = t["colour"]
        b.setdefault("turn", [0, 1, 0, 0.0])
        out.append(b)
    print("  terrain: %d displacement triangles -> %dx%d cells at %.1f m -> %d tilted slabs"
          % (len(tris), hf.nx - 1, hf.nz - 1, hf.cell, len(out)))
    return out


def build(bsp_path, name):
    cfg = dict(CONFIGS[name])
    # The flights live beside this adapter (stairs/<config>.json), wherever the launcher runs from.
    stairs_file = os.path.join(os.path.dirname(os.path.abspath(sys.modules["adapter_launch"].__file__)),
                               "playlot-maps", "stairs", name + ".json") if "adapter_launch" in sys.modules else ""
    if stairs_file and os.path.exists(stairs_file):
        with open(stairs_file) as f:
            cfg["stairs"] = json.load(f)
    bsp = bsp_read.Bsp(bsp_path).load()
    # Garry's Mod maps use gmod_player_start where the others use info_player_start.
    starts = [e for e in bsp.entities if e.get("classname") in ("info_player_start", "gmod_player_start")]
    if not starts:   # TTT maps use info_player_deathmatch
        starts = [e for e in bsp.entities if e.get("classname") == "info_player_deathmatch"]
    sp = [float(v) for v in starts[cfg["spawn_at"]]["origin"].split()]
    sp_yaw = float(starts[cfg["spawn_at"]].get("angles", "0 0 0").split()[1])
    y_off = (sp[2] - 1.0) * S
    boxes, slabbed, dropped = [], 0, 0
    for i in sorted(bsp.model_brushes(0)):
        contents = bsp.brushes[i][2]
        names = docboxes.brush_material_names(bsp, i)
        pick = ("water", None) if contents & WATER else material_for(cfg, names)
        if pick is None:
            dropped += 1
            continue
        mat, colour = pick
        parts, cut = brush_boxes(bsp, i, cfg.get("slab"))
        slabbed += cut
        if cut == 2:
            b = ramp_document_box(parts[0], mat, colour, y_off)
            region = cfg.get("region", ((-1e9, 1e9),) * 3)
            if all(region[k][0] <= b["at"][k] <= region[k][1] for k in range(3)) and mat != "water":
                boxes.append(b)
            continue
        for (u0, u1), (v0, v1), (z0, z1), phi in parts:
            cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
            c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
            x, y = cu * c - cv * s, cu * s + cv * c         # back out of the turned frame
            size = [(u1 - u0) * S, (z1 - z0) * S, (v1 - v0) * S]
            if mat == "water":
                phi = 0.0                                     # a liquid is axis-aligned
            if max(size) < cfg.get("min_size", MIN_SIDE) or min(size) <= 0:
                continue
            at = [round(x * S, 3), round(((z0 + z1) / 2) * S - y_off, 3), round(-y * S, 3)]
            region = cfg.get("region", ((-1e9, 1e9),) * 3)
            if any(not (region[k][0] <= at[k] <= region[k][1]) for k in range(3)):
                continue                                      # outside the playable region
            b = {"at": at,
                 "size": [round(v, 3) for v in size], "material": mat}
            if colour:
                b["colour"] = colour
            if phi:
                b["turn"] = [0, 1, 0, round(phi, 2)]
            boxes.append(b)
    for r in cfg.get("ramps", []):
        xs, zs, ys = r["x"], r["z"], r["y"]
        rb = (xs[0] / S, xs[1] / S, -zs[1] / S, -zs[0] / S, (ys[0] + y_off) / S, (ys[1] + y_off) / S,
              (ys[0] - 0.4 + y_off) / S, math.degrees(math.atan((ys[1] - ys[0]) / (xs[1] - xs[0]))), "x", 1)
        boxes.append(ramp_document_box(rb, "concrete", "#b9b4aa", y_off))
    for f in cfg.get("fill", []):
        # Solid filler (document frame, metres) that lifts a pit floor level with its surroundings.
        lo, hi = f["min"], f["max"]
        boxes.append({"at": [round((lo[i] + hi[i]) / 2, 3) for i in range(3)],
                      "size": [round(hi[i] - lo[i], 3) for i in range(3)],
                      "material": f.get("material", "concrete"), "colour": f.get("colour", "#8a8780")})
    for (x0, x1), (z0, z1) in cfg.get("exclude", []):
        boxes = [b for b in boxes if not (x0 <= b["at"][0] <= x1 and z0 <= b["at"][2] <= z1)]
    for r in cfg.get("remove", []):
        # Whole boxes the author's map does not have in the way they stand here (a door's plug, a
        # beam hung across a pit), named by a document-frame volume that wholly holds each.
        lo, hi = r["min"], r["max"]
        boxes = [b for b in boxes if not all(lo[i] - 0.02 <= b["at"][i] - b["size"][i] / 2 and b["at"][i] + b["size"][i] / 2 <= hi[i] + 0.02 for i in range(3))]
    boxes = [snap(b) for b in boxes]
    if cfg.get("stairs"):
        boxes = add_stairs(boxes, cfg["stairs"])
    if cfg.get("close_gaps"):
        print("  tilted-only cracks left after closing gaps:", gaps.close_gaps(boxes))
    weld_hairlines(boxes)
    if cfg.get("terrain"):
        boxes.extend(terrain_boxes(bsp, cfg, y_off))
    if cfg.get("spawn_pad"):
        # The author's start stood on displacement terrain this converter leaves out.
        boxes.append({"at": [round(sp[0] * S, 3), -0.15, round(-sp[1] * S, 3)], "size": [4.0, 0.3, 4.0], "material": "concrete", "colour": "#b9b4aa"})
    doc = {
        "format": 1, "kind": "playground_map", "id": cfg["id"], "name": cfg["name"],
        "blurb": cfg["blurb"], "map_kind": "sandbox", "tier": 1, "author": cfg["author"],
        "attribution": ("Geometry converted from %s by %s. The author's textures are not carried: "
                        "surfaces use this game's materials over Kenney's Prototype Textures (CC0). "
                        "Removed on request." % (cfg["source"], cfg["author"])),
        "spawn": [round(sp[0] * S, 3), 1.0, round(-sp[1] * S, 3)],
        "spawn_yaw": round(sp_yaw - 90.0, 1),
        "boxes": boxes, "declared": cfg.get("declared", []),
    }
    sourceframe.record(doc, bsp_path, S, (0.0, y_off, 0.0))
    print("%s: %d boxes (%d brushes cut into slabs, %d tool brushes dropped)" % (cfg["id"], len(boxes), slabbed, dropped))
    return doc


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        return 2
    doc = build(args[0], args[1])
    out = next((a[6:] for a in argv if a.startswith("--out=")), os.path.join(HERE, "..", "maps", doc["id"] + ".json"))
    with open(out, "w") as f:
        f.write(json.dumps(doc, indent=1) + "\n")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
