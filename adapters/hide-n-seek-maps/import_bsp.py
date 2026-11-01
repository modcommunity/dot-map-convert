#!/usr/bin/env python3
"""Converts a Source 1 community prop-hunt or hide-and-seek .bsp (VBSP 19/20) into a hide-n-seek map document.

    tools/import_bsp.py <map.bsp> <id> "<Name>" <author> <page-url> [--out=maps/<id>.json] [--style=yard] [--field=round_seconds=300] [--drop-beside=x,z,kind] [--clear=x0,z0,x1,z1] [--prune-pockets] [--widen-doors] [--no-doors] [--terrain] [--terrain-budget=bytes] [--graft-terrain=<doc.json>] [--slide-doors] [--scale=k] [--drop-door=x,z] [--cover=N] [--cover-gap=m] [--lobby=r,gap] [--cover-seed=N] [--seekers-at=x,z] [--anchor=N] [--drop-kind=id] [--thin=id:N]

--field=<name>=<number> sets a document number the map's own band wants (round_seconds, hide_seconds), found by headless_bots, so a rerun of the importer keeps it.

--drop-beside=x,z,kind (repeatable, in the finished map's coordinates) drops the prop of that kind nearest that point (any kind if left out): the
headless_bots trace prints "cut off: (x, y, z) beside <prop>" for a place no route reaches, and spots
are found beside props, so this takes the place away. Reruns keep it.

--clear=x0,z0,x1,z1 (in the finished map's coordinates) drops every prop inside the rectangle: a cubby the
author walled in with counters too tall for a bot to step over, where one prop at a time is whack-a-mole.

--prune-pockets drops every floor prop that leaves a sliver of floor the bots' mesh cuts off (a small flat's
beds and bookcases a hand off a wall), by a flood fill over a grid, instead of one --drop-beside at a time.

--no-doors leaves every door out (the doorways stay open): a hotel's 0.9 m doors had stand-ins stuck beside the panels for 15 to 65 s on every cover seed tried.

--widen-doors widens a flat's metre-wide doorways to the game's 1.4 m, which the bots' mesh can pass.

--scale=k builds the whole map k times its real size (S in metres per unit), for a building so small that a seeker tours it in under a minute: rooms, doorways and stairs grow with it, props do not.

--drop-door=x,z (repeatable, finished coordinates) leaves out the doors within 1.5 m of that point, the doorway stays open: a hotel's one door that stand-ins stuck beside for 20 s on every cover seed.

--slide-doors makes every door slide into its wall instead of swinging, for a map whose doors stand
in a small room or a narrow lobby where a stand-in lingered against an open panel for ten seconds.

--drop-kind=<prop id> (repeatable) drops every prop of that kind, and --thin=<id>:N keeps one in N of it: the
author's hand-sized clutter (68 table lamps in a yard) is no cover, and a seeker's tour of the places
there is to look behind grows with it, so a lone seeker could not search a yard of 280 props in a round.

--cover=N adds N pieces of furniture (beds, wardrobes, sofas) on the clearest open floor, seeded, for a
map whose author left it bare; the bot suite finds a hider's places by cover.

--lobby=r,gap keeps only the hider starts within r metres of the author's seeker start (the lobby everybody arrives in) and keeps
--cover's furniture `gap` metres clear of them: with the author's starts in every room and furniture beside each, a hider hid
where it spawned (59 of 144 walked 8 m), and the game is the walk to somewhere the seekers have to look.

--cover-seed=N reseeds --cover's placement (7 by default); the bot bands of a small map move a good deal with which furniture lands where.

--hiders-at=x,z,r (finished map's coordinates) keeps only the hider starts within r metres of that point, and takes the extra starts from the open floor there: a flat only 15 m deep needs its hiders in one corner for the walk to cover to be 8 m.

--cover-away=h,s keeps --cover's furniture h metres from every hider start and s metres from every seeker start (the seekers' first three seconds, and a hider that hides where it spawned).

--hiders-far=m drops every hider start within m metres of a seeker start: a flat whose corridor starts are a few metres from the seekers had hiders caught in the first three seconds.

--cover-clear=m sets how much clear floor (2 m by default) a piece of cover wants round it: a small flat has no 2 m of open floor, so 0 pieces were placed.

--cover-gap=m sets how far apart --cover's furniture stands (2.5 m by default; a hotel of small rooms had room for 27 at that gap).

--anchor=N makes start number N (counting the .bsp's info_player_start entries from 0) the seekers' lobby, in place of the first: a map whose first start is a stray on another storey seeded the seekers into a basement.

--seekers-at=x,z (in the finished map's coordinates) stands the seekers in a 2 x 2 block there, whatever the author's starts
were: a small hotel's seekers began a few metres from the hiders' lobby, so the first was caught in two seconds and
the map's whole round lasted under thirty. The far end of the building makes the seekers walk the length of it.

--terrain turns the map's displacement ground (sculpted terrain, which is not a brush) into dot-map's heightfield (`terrain` in the
document, fitted to --terrain-budget bytes); without it a map whose yard is terrain has no floor. --graft-terrain=<doc.json> <bsp> swaps a
committed document's old stepped field of boxes for the heightfield and sets what stood on it down on the new ground, leaving the rest as it is.

--style=yard gives the developer-grid boxes a suburban surface by their shape (a yard map the
author left unskinned); other maps keep the surface their material names say.

What it does, and why each choice:

- The world's brushes become BOXES, because a map document has no meshes. Each brush's convex
  hull is found (bsp_read.Bsp.brush_hull, copied from game-g2gfast's importer) and its bounding
  box is written; a brush that is NOT a box (a roof slope, a stair) is cut into slabs along its
  longer horizontal axis, each slab as tall as the brush is at the slab's middle, so a ramp
  becomes a staircase of 0.3 m risers rather than a block twice its height.
- Axes: Source is Z-up, godot = (x, z, -y). Scale: 1 unit = 0.01905 m (the engine's own
  0.75 inch), which makes a 108-unit door 2.06 m, fits the game's 1.4 m x 2.3 m door convention.
- Textures are NOT carried. The author's textures are replaced with the game's own materials
  (Kenney's grid under pastels, ph_materials.gd); TEXTURE_MAP says which, by name.
- prop_physics become catalogue props by PROP_MAP (the author's HL2 models have no licence we can
  ship; the catalogue is Kenney, CC0). A model with no entry is dropped and counted. PROP_MAP is
  the prop-hunt importer's, whose catalogue has bottles and cans (a disguise); this game's has
  none, and a hider is a person, so HS_SWAP turns a crate or a barrel into a box or a bin a
  person crouches behind and drops what is hand-sized (bottles, mugs, cartons, cans).
- Each prop_door_rotating becomes a real door (`add_doors`): the doorway beside its hinge is
  measured from the finished boxes, and a door that does not find one is reported, not guessed.
- info_player_start entries are shared out between the two teams; `light` entities become omni lights.
- Tool brushes (skybox, clip, trigger, hint, nodraw-only) are dropped.

The output goes through build_maps.Map.build(), so spawns are settled and checked there.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bsp_read  # noqa: E402  (a shim over dot-map's shared reader; it puts dotbsp on sys.path)
from dotbsp import boxes as dboxes, docboxes  # noqa: E402  (the shared passes over a document's boxes)
from dotbsp import terrain as dterrain  # noqa: E402
import build_maps  # noqa: E402

S = 0.01905


TERRAIN_TINT = (0.85, 0.9, 0.78)


terrain_tris = dterrain.terrain_tris  # swap_terrain and its helpers live in dot-map (dotbsp.terrain)
swap_terrain = dterrain.swap_terrain

# This game's catalogue has no food_* or survival_*: a person hides, not a bottle. "" drops.
HS_SWAP = {
    "food_watermelon": "nature_crop_melon", "survival_barrel": "furniture_trashcan",
    "survival_bucket": "", "survival_bottle": "", "survival_bottle_large": "", "survival_box": "furniture_cardboard_box_closed",
    "food_carton_small": "", "food_soda_can": "", "survival_box_large": "furniture_cardboard_box_closed",
    "food_mug": "", "food_cup_coffee": "", "survival_chest": "furniture_cardboard_box_closed", "food_banana": "", "food_pot": "",
}
SLAB = 28.0     # source units: ~0.53 m, a slope's riser

TOOLS = ("TOOLS/", "tools/")
TEXTURE_MAP = [
    ("CEILINGTILE", "ceiling", None),
    ("OFFCEILING", "concrete", None),
    ("CARPET", "carpet", None),
    ("BLINDS", "glass", None),
    ("LIGHTCOVER", "glass", (1.00, 1.00, 0.92)),
    ("OFFWNDW", "glass", None),
    ("TRUSS", "metal", None),
    ("DRTRIM", "metal", None),
    ("ELEVDR", "metal", None),
    ("PARTICLEBOARD", "wood", None),
    ("OFFDR", "wood", None),
    ("DESKTOP", "wood", None),
    ("WALLOFFICE", "paint", (0.92, 0.94, 1.00)),
    ("OFFWLLB", "plaster", (0.90, 0.95, 1.00)),
    ("OFFWLLC", "paint", (0.96, 0.94, 0.88)),
    ("BUILDING_TEMPLATE", "plaster", (0.95, 0.90, 0.82)),
    ("GLASSWINDOW", "glass", None),
    ("CEILING01", "ceiling", None),
    ("BUILDING", "concrete", None),
    ("PLASTER", "plaster", (0.95, 0.92, 0.84)),
    ("GRASS", "grass", (0.85, 0.95, 0.75)),
    ("ACOUSTICCEILING", "ceiling", None),
    ("TILEFLOOR", "tile", None),
    ("WOODFLOOR", "parquet", None),
    ("TILEROOF", "roof", (1.00, 0.72, 0.62)),
    ("COMBINEGLASS", "glass", None),
    ("CONCRETE", "concrete", None),
    ("STONE", "stone", None),
    ("BRICK", "brick", None),
    ("WOOD", "wood", None),
    ("METAL", "metal", None),
    ("DEV/", "flat", (0.8, 0.8, 0.82)),
]

# HL2 model -> catalogue id. Pieces with no counterpart in the catalogue are left out.
PROP_MAP = {
    "furniture_lamp01a": "furniture_lamp_round_table",
    "watermelon01": "food_watermelon",
    "chair_wood01": "furniture_chair",
    "oildrum001": "survival_barrel",
    "metal_paintcan001a": "survival_bucket",
    "garbage_newspaper001a": "furniture_books",
    "cardboard_box001b": "furniture_cardboard_box_closed",
    "furnituretable001a": "furniture_table",
    "glassbottle01a": "survival_bottle",
    "trashbin01a": "furniture_trashcan",
    "plasticcrate01a": "survival_box",
    "garbage_milkcarton002a": "food_carton_small",
    "popcan01a": "food_soda_can",
    "wood_crate001a": "survival_box_large",
    "wood_crate002a": "survival_box",
    "furniturecouch001a": "furniture_lounge_sofa",
    "tv_monitor01": "furniture_television_vintage",
    "furnituredresser001a": "furniture_cabinet_bed_drawer_table",
    "breenglobe": "nature_pot_small",
    "monitor01a": "furniture_computer_screen",
    "computer01_keyboard": "furniture_computer_keyboard",
    "breenclock": "furniture_radio",
    "huladoll": "furniture_bear",
    # An office (ph_office221): paper, drawers, screens and boxes.
    "file_cabinet1": "furniture_side_table_drawers",
    "file_cabinet2": "furniture_side_table_drawers",
    "file_cabinet3": "furniture_side_table_drawers",
    "chair_office": "furniture_chair_desk",
    "binderredlabel": "furniture_books",
    "bindergreen": "furniture_books",
    "binderblue": "furniture_books",
    "bindergraylabel01a": "furniture_books",
    "bindergraylabel01b": "furniture_books",
    "binderbluelabel": "furniture_books",
    "bindergreenlabel": "furniture_books",
    "clipboard": "furniture_books",
    "cardboard_box01": "furniture_cardboard_box_closed",
    "cardboard_box02": "furniture_cardboard_box_closed",
    "cardboard_box03": "furniture_cardboard_box_closed",
    "cardboard_box001a": "furniture_cardboard_box_closed",
    "cardboard_box003a": "furniture_cardboard_box_open",
    "cardboard_box003b": "furniture_cardboard_box_open",
    "cardboard_box004a": "furniture_cardboard_box_closed",
    "box01a": "survival_box",
    "box01b": "survival_box",
    "file_box": "survival_box",
    "plant01": "furniture_potted_plant",
    "cactus": "nature_cactus_tall",
    "coffee_mug": "food_mug",
    "coffee_mug2": "food_mug",
    "coffee_mug3": "food_mug",
    "garbage_coffeemug001a_forevergibs": "food_cup_coffee",
    "phone": "furniture_speaker_small",
    "projector": "furniture_speaker_small",
    "projector_remote": "furniture_computer_mouse",
    "computer_caseb": "furniture_speaker",
    "computer_keyboard": "furniture_computer_keyboard",
    "computer_monitor": "furniture_computer_screen",
    "computer_mouse": "furniture_computer_mouse",
    "trash_can": "furniture_trashcan",
    "trash_can_p": "furniture_trashcan",
    "garbage_beercan01a": "food_soda_can",
    "garbage_plasticbottle001a": "survival_bottle",
    "garbage_plasticbottle002a": "survival_bottle",
    "garbage_plasticbottle002a_fullsheet": "survival_bottle",
    "garbage_takeoutcarton001a": "food_carton_small",
    "suitcase_passenger_physics": "survival_chest",
    "metalbucket01a": "survival_bucket",
    "pi_bucket": "survival_bucket",
    "tv_plasma": "furniture_television_modern",
    "table_coffee": "furniture_table_coffee",
    # A flat (ph_apartment): the kitchen table's leftovers, bedroom and living room.
    "garbage_metalcan002a": "food_soda_can",
    "garbage_plasticbottle003a": "survival_bottle",
    "garbage_coffeemug001a": "food_mug",
    "garbage_glassbottle001a": "survival_bottle",
    "garbage_glassbottle003a": "survival_bottle",
    "garbage_milkcarton001a": "food_carton_small",
    "water_bottle": "survival_bottle",
    "bottle03": "survival_bottle",
    "wood_table": "furniture_table",
    "furniture_shelf01a": "furniture_bookcase_closed",
    "furniturechair001a": "furniture_chair",
    "chairantique": "furniture_chair",
    "bed": "furniture_bed_double",
    "potted_plant1": "furniture_potted_plant",
    "potted_plant2": "furniture_potted_plant",
    "potted_plant3": "furniture_potted_plant",
    "bananna": "food_banana",
    "doll01": "furniture_bear",
    "trashdumpster01a": "survival_box_large",
    "furnituretable003a": "furniture_side_table",
    "desklamp01": "furniture_lamp_square_table",
    "radio": "furniture_radio",
    # A hotel (ph_hotel) and a ruined church with a cellar (ph_abandoned_church).
    "furniture_couch01a": "furniture_lounge_sofa",
    "couch": "furniture_lounge_sofa",
    "sofa": "furniture_lounge_sofa",
    "sofa_chair": "furniture_lounge_chair",
    "furnituredrawer001a": "furniture_cabinet_bed_drawer",
    "furnituredrawer002a": "furniture_cabinet_bed_drawer",
    "furnituredrawer003a": "furniture_side_table_drawers",
    "furniture_cabinetdrawer01a": "furniture_cabinet_bed_drawer",
    "bookshelf1": "furniture_bookcase_closed",
    "shelfunit01a": "furniture_bookcase_open",
    "furnitureshelf001a": "furniture_bookcase_open",
    "kitchen_shelf001a": "furniture_bookcase_open_low",
    "newspaperstack01": "furniture_books",
    "paper_towels": "food_carton_small",
    "furnituresink001a": "furniture_kitchen_sink",
    "furniturestove001a": "furniture_kitchen_stove",
    "cafeteria_table001a": "furniture_table",
    "cafeteria_bench001a": "furniture_bench",
    "furnituretable002a": "furniture_table",
    "chair02a": "furniture_chair",
    "controlroom_desk001a": "furniture_desk",
    "metalpot001a": "food_pot",
    "metalpot002a": "food_pot",
    "pot01a": "food_pot",
    "jar01a": "survival_bottle",
    "jar01b": "survival_bottle",
    "glassjug01": "survival_bottle_large",
    "vendingmachine": "furniture_kitchen_fridge_small",
    "kennel": "survival_box_large",
    "citizenradio": "furniture_radio",
    "pottery04a": "nature_pot_small",
    "pottery02a": "nature_pot_small",
    "metalbucket02a": "survival_bucket",
    "garbage_metalcan001a": "furniture_trashcan",
    "garbage_bag001a": "survival_bucket",
    "wine_barrel": "survival_barrel",
    "grainbasket01a": "survival_bucket",
    "grainbasket01b": "survival_bucket",
    "grainbasket01c": "survival_bucket",
    "claypot01": "nature_pot_small",
    "claypot01_damage_01": "nature_pot_small",
    "claypot01_damage_02": "nature_pot_small",
    "claypot01_damage_03": "nature_pot_small",
    "claypot01_damage_04": "nature_pot_small",
    "claypot02": "nature_pot_large",
    "claypot02_damage_01": "nature_pot_large",
    "claypot02_damage_02": "nature_pot_large",
    "claypot02_damage_03": "nature_pot_large",
    "claypot02_damage_04": "nature_pot_large",
    "pottery_large01a": "nature_pot_large",
    "gravestone001a": "nature_stone_large_a",
    "shrub_01a": "nature_plant_bush_small",
    "bramble001a": "nature_plant_bush",
    "militiarock05": "nature_rock_small_a",
    "hallo_pumpkin_l": "nature_crop_pumpkin",
    "hallo_pumpkin_m": "nature_crop_pumpkin",
    "hallo_pumpkin_s": "nature_crop_pumpkin",
    "hallo_pumpkin_xl": "nature_crop_pumpkin",
    "concrete_chunk03a": "nature_stone_small_a",
    "concrete_chunk04a": "nature_stone_small_a",
    "concrete_chunk05g": "nature_stone_small_a",
    "concrete_chunk02a": "nature_stone_small_a",
    "concrete_chunk09a": "nature_stone_small_a",
    "grainbasket01c_gib1": "survival_bucket",
    "grainbasket01c_gib2": "survival_bucket",
    "wood_pallet_debris_03": "survival_box",
    "wood_pallet_debris_04": "survival_box",
    "wood_pallet_debris_06": "survival_box",
    "wood_pallet_debris_11": "survival_box",
    "wood_pallet_debris_12": "survival_box",
}




# Every entity class an author uses for a loose prop; the _dynamic ones are placed furniture
# that does not move in the original, which a catalogue prop is not either (it is a disguise).
PROP_CLASSES = ("prop_physics", "prop_physics_multiplayer", "prop_physics_override",
                "prop_dynamic", "prop_dynamic_override")
START_CLASSES = ("info_player_start", "info_player_terrorist", "info_player_counterterrorist",
                 "info_player_deathmatch", "info_player_teamspawn")


def gd(p):
    return (p[0] * S, p[2] * S, -p[1] * S)


def kv(e, k, default=None):
    return e.get(k, default)


def vec(s):
    return [float(x) for x in s.split()]


def brush_boxes(bsp, index):
    """dot-map's boxes.decompose for one brush: ([(u range), (v range), (z range), phi], cut), cut 1 when
    it had to be cut into slabs. The ranges are in Source units, in a frame turned phi degrees."""
    first, count, _ = bsp.brushes[index]
    planes = [bsp.planes[s[0]][:4] for s in bsp.brushsides[first:first + count] if not s[3]]
    parts = dboxes.decompose(planes, bsp.brush_hull(index), slab=SLAB)
    return [(p["x"], p["y"], p["z"], p["phi"]) for p in parts], 1 if parts and parts[0]["kind"] == "slab" else 0


# Furniture a crouching person fits behind, for a map the author furnished too thinly to hide in
# (the author's own props were mostly bottles, which this game's catalogue has not: --cover).
COVER_INDOOR = ("furniture_bed_single", "furniture_bookcase_closed_wide", "furniture_cabinet_bed_drawer", "furniture_lounge_sofa",
                "furniture_kitchen_cabinet", "furniture_bed_double", "furniture_cabinet_television", "furniture_side_table_drawers")


def main(argv):
    global S
    args = [a for a in argv[1:] if not a.startswith("--")]
    out_path = None
    style = ""
    fields = {}
    drops = []
    clears = []
    pockets = False
    widen = False
    no_doors = False
    slide = False
    cover = 0
    seekers_at = None
    anchor = 0
    cover_gap = 2.5
    cover_clear = 2.0
    hiders_far = 0.0
    hiders_at = None
    cover_away = (0.0, 0.0)
    lobby = None
    drop_doors = []
    cover_seed = 7
    drop_kinds = []
    thin = {}
    terrain = False
    graft = None
    budget = 24000
    for a in argv[1:]:
        if a.startswith("--out="):
            out_path = a[6:]
        elif a == "--widen-doors":
            widen = True
        elif a == "--no-doors":
            no_doors = True
        elif a.startswith("--drop-kind="):
            drop_kinds.append(a[12:])
        elif a.startswith("--thin="):
            k, _, n = a[7:].partition(":")
            thin[k] = int(n)
        elif a.startswith("--anchor="):
            anchor = int(a[9:])
        elif a.startswith("--seekers-at="):
            seekers_at = tuple(float(t) for t in a[13:].split(","))
        elif a.startswith("--cover-seed="):
            cover_seed = int(a[13:])
        elif a.startswith("--lobby="):
            lobby = tuple(float(t) for t in a[8:].split(","))
        elif a.startswith("--hiders-at="):
            hiders_at = tuple(float(t) for t in a[12:].split(","))
        elif a.startswith("--cover-away="):
            cover_away = tuple(float(t) for t in a[13:].split(","))
        elif a.startswith("--hiders-far="):
            hiders_far = float(a[13:])
        elif a.startswith("--cover-clear="):
            cover_clear = float(a[14:])
        elif a.startswith("--cover-gap="):
            cover_gap = float(a[12:])
        elif a.startswith("--cover="):
            cover = int(a[8:])
        elif a == "--slide-doors":
            slide = True
        elif a.startswith("--drop-door="):
            drop_doors.append(tuple(float(t) for t in a[12:].split(",")))
        elif a.startswith("--scale="):
            S = 0.01905 * float(a[8:])
        elif a == "--terrain":
            terrain = True
        elif a.startswith("--graft-terrain="):
            graft = a[16:]
        elif a.startswith("--terrain-budget="):
            budget = int(a[17:])
        elif a == "--prune-pockets":
            pockets = True
        elif a.startswith("--style="):
            style = a[8:]
        elif a.startswith("--field="):
            k, _, v = a[8:].partition("=")
            fields[k] = float(v)
        elif a.startswith("--clear="):
            clears.append(tuple(float(t) for t in a[8:].split(",")))
        elif a.startswith("--drop-beside="):
            t = a[14:].split(",")
            drops.append((float(t[0]), float(t[1]), t[2] if len(t) > 2 else ""))
    if graft:
        # A committed document keeps its hand edits and its flags: only its stepped field changes.
        with open(graft) as f:
            doc = json.load(f)
        swap_terrain(doc, terrain_tris(bsp_read.Bsp(args[0]).load()), "grass", TERRAIN_TINT, budget)
        with open(graft, "w") as f:
            f.write(json.dumps(doc, indent=1) + "\n")
        print("wrote", graft)
        return
    bsp_path, mid, name, author, url = args[:5]
    bsp = bsp_read.Bsp(bsp_path).load()
    m = build_maps.Map(
        mid, name, "Converted from %s by %s (%s)." % (os.path.basename(bsp_path), author, url),
        {"sky_top": [0.32, 0.52, 0.82], "sky_horizon": [0.72, 0.82, 0.92], "ground": [0.35, 0.33, 0.30],
         "sun_pitch": -55, "sun_yaw": 30, "sun_energy": 1.0, "ambient": [0.62, 0.66, 0.72], "ambient_energy": 0.5},
        kill_y=-20.0)
    m.doc["author"] = author
    m.doc.update(fields)
    m.doc["source"] = url

    sliced = skipped = 0
    for bi in sorted(bsp.model_brushes(0)):
        names = docboxes.brush_material_names(bsp, bi)
        mt = docboxes.majority_material(names, TEXTURE_MAP, ("flat", None))
        invisible = False
        if mt is None:
            # The author's sky box is the map's wall: solid to a player, drawn as nothing.
            if any("TOOLSSKYBOX" in n for n in names):
                mt, invisible = ("flat", None), True
            else:
                skipped += 1
                continue
        boxes, was_sliced = brush_boxes(bsp, bi)
        sliced += was_sliced
        for (x0, x1), (y0, y1), (z0, z1), phi in boxes:
            if phi:
                # A turned box: its centre back out of the turned frame, its sides as measured,
                # its yaw the same angle (Source turns counter-clockwise seen from above, and so
                # does godot about +y once y is flipped to -z).
                if x1 - x0 < 0.05 or y1 - y0 < 0.05 or z1 - z0 < 0.05:
                    continue
                c, sn = math.cos(math.radians(phi)), math.sin(math.radians(phi))
                lx, ly = (x0 + x1) / 2, (y0 + y1) / 2
                gx, gy, gz = gd((lx * c - ly * sn, lx * sn + ly * c, (z0 + z1) / 2))
                bx = m.box((gx, gy, gz), ((x1 - x0) * S, (z1 - z0) * S, (y1 - y0) * S), mt[0], mt[1], yaw=phi)
            else:
                # Source y is godot -z: the box's range flips.
                bx = m.span(x0 * S, x1 * S, z0 * S, z1 * S, -y1 * S, -y0 * S, mt[0], mt[1])
            if invisible and bx is not None:
                bx["visible"] = False
            elif bx is not None and mt[0] == "flat" and style == "yard":
                bx["mat"], tint = docboxes.suburban_surface(bx["at"], bx["size"])
                if tint is not None:
                    bx["tint"] = list(tint)
                else:
                    bx.pop("tint", None)
    if terrain:
        n = 0
        tris = terrain_tris(bsp)
        # The field is cut as boxes so props and spawns settle on it, then swapped (swap_terrain).
        for c in dboxes.terrain_cells(tris):
            # terrain_cells names the axes as the map does (z is height); this loop's y is the height, z the map's y.
            (x0, x1), (y0, y1), (z0, z1), mat = c["x"], c["z"], c["y"], "grass"
            m.span(x0 * S, x1 * S, y0 * S, y1 * S, -z1 * S, -z0 * S, mat, (0.85, 0.9, 0.78))
            n += 1
        print("terrain: %d ground boxes from the displacements" % n)
    print("brushes %d  tool-only %d  sliced %d  boxes %d" % (len(bsp.model_brushes(0)), skipped, sliced, len(m.boxes)))

    docboxes.drop_door_leaves(m.boxes)
    docboxes.prune_far_scenery(m.boxes, [gd(vec(e["origin"])) for e in bsp.entities if e.get("classname") in START_CLASSES])

    # Props: sit on the highest solid box under the footprint when one is within reach of the
    # source height, else at the source height (a lamp on a table the author placed as a prop).
    def support(x, z, pid, yaw, ymax):
        """The highest thing under the footprint no higher than ymax: a box's top, or a prop
        already set down (`rest_on`, its collision as the game measured it). The catalogue's
        table is not the author's table, so a lamp set at the author's table-top height would
        hang in the air; it is put on whatever is really there instead."""
        best = 0.0 if ymax >= 0.0 else None
        fw, fd = build_maps.footprint(pid, yaw) if pid else (0.0, 0.0)
        for b in m.boxes:
            if not b.get("solid", True):
                continue
            if docboxes.within(b, x, z, 0.001):
                t = b["at"][1] + b["size"][1] / 2
                if t <= ymax and (best is None or t > best):
                    best = t
        for q in (m.props if pid else ()):
            qw, qd = build_maps.footprint(q["id"], q.get("yaw", 0.0))
            # Well inside the footprint, not on its rim: a round bin's corner is air.
            if abs(x - q["at"][0]) <= qw / 2 - 0.08 and abs(z - q["at"][2]) <= qd / 2 - 0.08:
                t = q["at"][1] + build_maps.rest_on(q, x - q["at"][0], z - q["at"][2], pid, yaw)
                if t <= ymax and (best is None or t > best):
                    best = t
        return best

    dropped = {}
    placed = []
    for e in bsp.entities:
        cls = e.get("classname")
        if cls in PROP_CLASSES:
            # Keys are matched lower-cased: authors spell one model Chair_office and chair_office.
            key = os.path.splitext(os.path.basename(e.get("model", "")))[0].lower()
            pid = PROP_MAP.get(key)
            pid = HS_SWAP.get(pid, pid)
            if not pid:
                dropped[key] = dropped.get(key, 0) + 1
                continue
            placed.append((vec(e["origin"])[2], e, pid))
        elif cls in ("light", "light_spot"):
            o = vec(e["origin"])
            gx, gy, gz = gd(o)
            c = vec(e.get("_light", "255 255 255 200"))
            m.light(gx, gy, gz, rng=9.0, energy=min(1.2, c[3] / 200.0), colour=[c[0] / 255, c[1] / 255, c[2] / 255])
    def floor_corners_ok(x, z, pid, yaw, y):
        """A prop standing on the ground has solid floor under every corner of its footprint:
        the author's cellar stair is a hole in the floor, and a crate on its rim hung half over it."""
        fw, fd = build_maps.footprint(pid, yaw)
        for dx in (-fw / 2 + 0.03, fw / 2 - 0.03):
            for dz in (-fd / 2 + 0.03, fd / 2 - 0.03):
                ok = False
                for b in m.boxes:
                    if not b.get("solid", True):
                        continue
                    if docboxes.within(b, x + dx, z + dz):
                        if abs(b["at"][1] + b["size"][1] / 2 - y) < 0.06:
                            ok = True
                            break
                if not ok:
                    return False
        return True

    # Lowest first, so a table is down before the lamp the author put on it.
    for _, e, pid in sorted(placed, key=lambda t: t[0]):
        ang = vec(e.get("angles", "0 0 0"))
        gx, gy, gz = gd(vec(e["origin"]))
        yaw = (ang[1] + 90.0) % 360.0
        y = support(gx, gz, pid, yaw, gy + 0.35)
        if y is None:
            y = max(gy, 0.0)
        if y < 0.06 and not floor_corners_ok(gx, gz, pid, yaw, y) and not any(
                abs(q["at"][0] - gx) < 0.01 and abs(q["at"][2] - gz) < 0.01 for q in m.props):
            dropped["(over a hole)"] = dropped.get("(over a hole)", 0) + 1
            continue
        m.prop(pid, gx, gz, yaw=yaw, y=y)
    starts = [e for e in bsp.entities if e.get("classname") in START_CLASSES]
    keep_hiders = None
    if lobby:
        g0 = [gd(vec(e["origin"])) for e in starts]
        near0 = sorted(range(len(starts)), key=lambda i: (g0[i][0] - g0[anchor][0]) ** 2 + (g0[i][2] - g0[anchor][2]) ** 2)
        seek0 = set(near0[:max(3, min(4, len(starts) // 3))])
        keep_hiders = {i for i in range(len(starts)) if i not in seek0
                       and (g0[i][0] - g0[anchor][0]) ** 2 + (g0[i][2] - g0[anchor][2]) ** 2 <= lobby[0] ** 2}
    gstarts = [gd(vec(e["origin"])) for e in starts]
    order = sorted(range(len(starts)), key=lambda i: (gstarts[i][0] - gstarts[anchor][0]) ** 2 + (gstarts[i][2] - gstarts[anchor][2]) ** 2)
    seek = set(order[:max(3, min(4, len(starts) // 3))])
    # The finished map is shifted so a floor box is centred on the origin (below); --hiders-at and --cover-away are
    # in the finished coordinates, so find that shift now, from the floor box nearest the seekers.
    ys = sorted((support(gstarts[i][0], gstarts[i][2], None, 0.0, gstarts[i][1] + 0.6) or gstarts[i][1] - 0.05) for i in seek)
    floor_y = round(ys[len(ys) // 2], 3) if ys and min(ys) > 0.5 else 0.0
    cxs = sum(gstarts[i][0] for i in seek) / len(seek)
    czs = sum(gstarts[i][2] for i in seek) / len(seek)
    floors = [b for b in m.boxes if b.get("solid", True) and abs(b["at"][1] + b["size"][1] / 2 - floor_y) < 0.05 and b["size"][0] > 4.0 and b["size"][2] > 4.0]
    early = min(floors, key=lambda b: (b["at"][0] - cxs) ** 2 + (b["at"][2] - czs) ** 2)["at"] if floors else (0.0, 0.0, 0.0)
    eox, eoz = early[0], early[2]
    if hiders_at:
        hiders_at = (hiders_at[0] + eox, hiders_at[1] + eoz, hiders_at[2])
    if cover:
        away = [(gstarts[i][0], gstarts[i][2], cover_away[1]) for i in seek] if not seekers_at else [(seekers_at[0] + eox, seekers_at[1] + eoz, cover_away[1])]
        if hiders_at:
            away.append((hiders_at[0], hiders_at[1], cover_away[0]))
        avoid = [(g0[i][0], g0[i][2], lobby[1]) for i in keep_hiders] if keep_hiders else []
        print("cover furniture: %d placed" % docboxes.scatter_cover(m, cover, cover_seed, COVER_INDOOR, spacing=cover_gap, avoid=avoid + away, clear=cover_clear, floor_y=floor_y))
    # Seekers count together at one end: the starts nearest the first one. Everybody else hides,
    # from wherever the author put them, spread out as the author spread them.
    for i, e in enumerate(starts):
        if keep_hiders is not None and i not in seek and i not in keep_hiders:
            continue
        if hiders_at and i not in seek and (gstarts[i][0] - hiders_at[0]) ** 2 + (gstarts[i][2] - hiders_at[1]) ** 2 > hiders_at[2] ** 2:
            continue
        if hiders_far and i not in seek and min((gstarts[i][0] - gstarts[j][0]) ** 2 + (gstarts[i][2] - gstarts[j][2]) ** 2 for j in seek) < hiders_far ** 2:
            continue
        gx, gy, gz = gstarts[i]
        ang = vec(e.get("angles", "0 0 0"))
        # Stands on whatever floor is under the start (a sunken room is below zero), not on zero.
        floor = support(gx, gz, None, 0.0, gy + 0.6)
        m.spawn("seekers" if i in seek else "hiders", gx, gz, yaw=ang[1] - 90.0, y=(max(gy, 0.0) if floor is None else floor) + 0.05)
    # A hiding game wants a dozen places to start from: more are taken from the clearest open
    # floor, at least 3 m from any other start.
    have = [(sp["at"][0], sp["at"][2]) for side in m.spawns.values() for sp in side]
    for size, x, z in m.spots(y=floor_y, step=1.0, top=400) if hiders_at else m.spots(step=1.5, top=60):
        if len(m.spawns["hiders"]) >= 12:
            break
        if hiders_at and (x - hiders_at[0]) ** 2 + (z - hiders_at[1]) ** 2 > hiders_at[2] ** 2:
            continue
        if all((x - a) ** 2 + (z - b) ** 2 >= (1.5 if hiders_at else 9.0) for a, b in have):
            m.spawn("hiders", x, z, yaw=0.0, y=floor_y + 0.05 if hiders_at else 0.0)
            have.append((x, z))
    hy = sorted(sp["at"][1] for sp in m.spawns["seekers"])
    fy = round(hy[len(hy) // 2] - 0.05, 3) if hy else 0.0
    for tid, near in (("football", 5.0), ("barrel", 5.0), ("beach_ball", 5.0), ("tyre", 5.0), ("bell", 5.0), ("horn", 5.0)):
        # Two metres from every start, then one and a half when a small flat's 44 starts leave none.
        spot = None
        for gap in (4.0, 2.25):
            spot = next(((x, z) for size, x, z in m.spots(y=fy, step=1.5, top=60) if all((x - a) ** 2 + (z - b) ** 2 >= gap for a, b in have)), None)
            if spot:
                break
        if spot:
            m.toy(tid, spot[0], spot[1], y=fy, near=near)
            have.append(spot)
    if len(m.spawns["hiders"]) > 64:
        # HsMapDoc.MAX_SPAWNS is 64 a side; a hundred starts spread over three storeys keep an even spread, farthest-point first.
        hs = m.spawns["hiders"]
        kept = [hs[0]]
        while len(kept) < 60:
            kept.append(max(hs, key=lambda h: min((h["at"][0] - k["at"][0]) ** 2 + (h["at"][1] - k["at"][1]) ** 2 * 4 + (h["at"][2] - k["at"][2]) ** 2 for k in kept)))
        print("hider starts thinned from %d to %d" % (len(hs), len(kept)))
        m.spawns["hiders"][:] = kept
    if len(m.lights) > 128:
        # The document takes 128 lights at most (HsMapDoc.MAX_LIGHTS). Keep the lights greedily, dropping any within a radius of one
        # already kept, and widen the radius until they fit: a lamp-per-ceiling-tile map keeps an even spread, not its first 128.
        before, radius = len(m.lights), 0.5
        while True:
            kept = []
            for lt in m.lights:
                if all((lt["at"][0] - k["at"][0]) ** 2 + (lt["at"][1] - k["at"][1]) ** 2 + (lt["at"][2] - k["at"][2]) ** 2 >= radius ** 2 for k in kept):
                    kept.append(lt)
            if len(kept) <= 128:
                break
            radius += 0.25
        m.lights[:] = kept
        print("lights thinned from %d to %d (radius %.2f m)" % (before, len(kept), radius))
    print("props %d  lights %d  spawns %d  dropped models %s" % (len(m.props), len(m.lights), len(starts), dropped))
    doc = m.build()
    # Move the map so its origin stands on open ground. The collision audit tests a drawn
    # MultiMesh by its bounds, which a headless renderer reports as a point at the origin; a
    # map whose origin hangs in the air (this one's was outside the yard) fails it for every prop.
    ground = [b for b in doc["boxes"] if b.get("solid", True) and abs(b["at"][1] + b["size"][1] / 2) < 0.05
              and b["size"][0] > 4.0 and b["size"][2] > 4.0]
    oy = 0.0
    if not ground:
        # A flat on the author's first floor (ph_apartment): the play floor is a metre or so above
        # the world's zero, with the building's footing under it. Lower the whole map so the floor
        # the spawns stand on is y = 0, which is where the game, the audit and the bots expect it.
        ys = sorted(sp["at"][1] for sp in doc["spawns"]["seekers"])
        oy = round(ys[len(ys) // 2] - 0.05, 3)
        ground = [b for b in doc["boxes"] if b.get("solid", True) and abs(b["at"][1] + b["size"][1] / 2 - oy) < 0.05
                  and b["size"][0] > 4.0 and b["size"][2] > 4.0]
    ox = oz = 0.0
    if ground:
        cx = sum(sp["at"][0] for sp in doc["spawns"]["seekers"]) / len(doc["spawns"]["seekers"])
        cz = sum(sp["at"][2] for sp in doc["spawns"]["seekers"]) / len(doc["spawns"]["seekers"])
        g = min(ground, key=lambda b: (b["at"][0] - cx) ** 2 + (b["at"][2] - cz) ** 2)
        ox, oz = g["at"][0], g["at"][2]
        def shift(o):
            if isinstance(o, dict):
                if isinstance(o.get("at"), list) and len(o["at"]) == 3:
                    o["at"] = [round(o["at"][0] - ox, 3), round(o["at"][1] - oy, 3), round(o["at"][2] - oz, 3)]
                for v in o.values():
                    shift(v)
            elif isinstance(o, list):
                for v in o:
                    shift(v)
        for key in ("boxes", "props", "lights", "spawns", "toys", "doors"):
            shift(doc.get(key))
    if pockets:
        print("pruned %d props that left a pocket the bots cannot leave" % docboxes.prune_pockets(doc, build_maps.size_of, build_maps.footprint))
    # Spots are found beside props, so taking the prop away takes the spot: for a place the
    # headless_bots trace names as cut off (a slot between a row of furniture and a wall).
    for x0, z0, x1, z1 in clears:
        gone = [q for q in doc["props"] if x0 <= q["at"][0] <= x1 and z0 <= q["at"][2] <= z1]
        for q in gone:
            doc["props"].remove(q)
        print("cleared %d props from the cubby (%.1f, %.1f) to (%.1f, %.1f)" % (len(gone), x0, z0, x1, z1))
    for dx, dz, kind in drops:
        near = [q for q in doc["props"] if not kind or q["id"] == kind]
        near.sort(key=lambda q: (q["at"][0] - dx) ** 2 + (q["at"][2] - dz) ** 2)
        if near and (near[0]["at"][0] - dx) ** 2 + (near[0]["at"][2] - dz) ** 2 <= 1.8 ** 2:
            doc["props"].remove(near[0])
            print("dropped %s at %s beside (%.1f, %.1f)" % (near[0]["id"], near[0]["at"], dx, dz))
    seen = {}
    kept = []
    for q in doc["props"]:
        if q["id"] in drop_kinds:
            continue
        if q["id"] in thin:
            seen[q["id"]] = seen.get(q["id"], 0) + 1
            if seen[q["id"]] % thin[q["id"]]:
                continue
        kept.append(q)
    if len(kept) != len(doc["props"]):
        print("dropped %d props by kind" % (len(doc["props"]) - len(kept)))
        doc["props"][:] = kept
    if seekers_at:
        old = doc["spawns"]["seekers"]
        for i, sp in enumerate(old):
            sp["at"] = [round(seekers_at[0] + (i % 2) * 1.2, 3), sp["at"][1], round(seekers_at[1] + (i // 2) * 1.2, 3)]
            sp["yaw"] = 0.0
        print("seekers moved to (%.1f, %.1f)" % seekers_at)
    if not no_doors:
        docboxes.add_doors(m, doc, bsp.entities, (ox, oy, oz), slide, scale=S)
    for dx, dz in drop_doors:
        near = [d for d in doc["doors"] if (d["at"][0] - dx) ** 2 + (d["at"][2] - dz) ** 2 <= 1.5 ** 2]
        for d in near:
            doc["doors"].remove(d)
        print("--drop-door=%.1f,%.1f: dropped %d door(s); the doorway stays open" % (dx, dz, len(near)))
    if widen:
        print("widened %d doorways to 1.4 m" % docboxes.widen_doors(doc["boxes"], doors=doc["doors"]))
    # The doors are hung after build() settled the spawns, so one that stood against a doorway is
    # in the panel now (hs_apartment's 31st): settle again, with the doors in the way.
    if doc["doors"] is m.doors and doc["boxes"] is m.boxes and doc["spawns"] is m.spawns:
        m._settle_spawns()
    else:
        raise SystemExit("the document no longer shares the map's lists: settle the spawns from the document")
    if terrain:
        swap_terrain(doc, tris, "grass", TERRAIN_TINT, budget)
    # The frame a world pack regenerated at this scale is drawn in (tools/worlds.tsv, regen_worlds.sh): the shift above, undone.
    doc["world"] = {"pack": "hs_world_" + mid, "metres_per_unit": round(S, 6), "offset": [round(-ox, 5), round(-oy, 5), round(-oz, 5)]}
    out_path = out_path or os.path.join(build_maps.ROOT, "maps", mid + ".json")
    with open(out_path, "w") as f:
        f.write(json.dumps(doc, indent=1) + "\n")
    print("wrote", out_path)


if __name__ == "__main__":
    main(sys.argv)
