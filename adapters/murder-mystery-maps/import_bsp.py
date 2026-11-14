#!/usr/bin/env python3
"""Converts a Source 1 community .bsp (VBSP 19/20) into a murder_map document.

    tools/import_bsp.py <map.bsp> <id> "<Name>" <author> <page-url> [--out=maps/<id>.json] [--style=yard] [--field=round_seconds=300] [--drop-beside=x,z,kind] [--clear=x0,z0,x1,z1] [--prune-pockets] [--widen-doors] [--hang-doorways] [--dress=N] [--no-doors] [--slide-doors] [--floor=m] [--min-size=m] [--terrain[=material]] [--terrain-budget=bytes] [--graft-terrain=<doc.json>] [--dusk] [--skip-start=N] [--skip-door=x,z] [--one-way=x,z] [--cover=N] [--cover-gap=m] [--blurb=text] [--drop-kind=id] [--thin=id:N] [--merge-boxes] [--min-box-volume=0.05] [--min-box-thickness=0.15] [--max-boxes=N] [--max-wire=bytes] [--max-lights=N]

--merge-boxes, --min-box-volume=<m3> and --min-box-thickness=<m> shrink a trim-heavy map under the 6000-box limit: touching
same-material boxes join, then detail boxes below that size go (a panel a metre long stays). Off by default; counts are printed.
--max-boxes=N is a hard budget, run last: the smallest boxes go until N are left, keeping floors, stairs, door frames and the ground under a spawn, prop or light; the count cut, the largest cut and the spawns' reach before and after are printed. --max-wire=<bytes> then cuts further, smallest first with the same protections, until the document deflates to that size (the games' 60000-byte wire limit; 57000 leaves room for the header). Off by default.

Adapted from hide-n-seek-maps' importer (copied, not linked): one spawn group, `players`, from the author's starts plus the clearest open floor up to 24.

--field=<name>=<number> sets a document number (round_seconds); --drop-beside, --clear, --prune-pockets, --widen-doors, --no-doors, --slide-doors, --terrain, --drop-kind, --thin are as in that importer; a rerun keeps them.

What it does, and why each choice:

- The world's brushes become BOXES, because a map document has no meshes. Each brush's convex
  hull is found (dotbsp's reader, dot-map-convert) and its bounding
  box is written; a brush that is NOT a box (a roof slope, a stair) is cut into slabs along its
  longer horizontal axis, each slab as tall as the brush is at the slab's middle, so a ramp
  becomes a staircase of 0.3 m risers rather than a block twice its height.
- Axes: Source is Z-up, godot = (x, z, -y). Scale: 1 unit = 0.01905 m (the engine's own
  0.75 inch), which makes a 108-unit door 2.06 m, fits the game's 1.4 m x 2.3 m door convention.
- Textures are NOT carried. The author's textures are replaced with the game's own materials
  (Poly Haven and ambientCG photographs in the game, mm_materials.gd); dot-map's source_textures.tsv says which, by name.
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
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _dotbsp_path():
    """dot-map-convert: $DOTBSP_PATH, else the sibling checkout dot-bootstrap makes."""
    for p in (os.environ.get("DOTBSP_PATH", ""), os.path.join(HERE, "..", "..", "dot-map-convert")):
        if p and os.path.isfile(os.path.join(p, "dotbsp", "reader.py")):
            return os.path.abspath(p)
    sys.exit("import_bsp: dot-map-convert was not found; clone dot-map beside this "
             "repository (dot-bootstrap does) or set DOTBSP_PATH to its checkout")


sys.path.insert(1, _dotbsp_path())
from dotbsp import reader as bsp_read  # noqa: E402  (the family's one reader)
from dotbsp import boxes as dboxes, docboxes, passledger, lights as dlights, texturemap  # noqa: E402  (the shared passes over a document's boxes)
from dotbsp import terrain as dterrain  # noqa: E402
from dotbsp import sourceframe  # noqa: E402  (doc["source_frame"]: the origin shift and bounds, for the audit)
import build_maps  # noqa: E402

S = 0.01905
FLOOR = 0.0   # --floor=m: the author's ground, in metres of the finished map; subtracted so it stands at y = 0
MIN_SIZE = 0.0   # --min-size=m: boxes with a longest side under this are dropped

TERRAIN_TINT = (0.85, 0.9, 0.78)


terrain_tris = dterrain.terrain_tris  # swap_terrain and its helpers live in dot-map (dotbsp.terrain)
swap_terrain = dterrain.swap_terrain
SKIP_STARTS = set()   # --skip-start=N: the author's Nth start, which the build says is inside a box
ONE_WAY = []   # --one-way=x,z (a door's finished centre): pinned to swing one way, for a door the swing check refuses the other way
SKIP_DOORS = []   # --skip-door=x,z (finished coordinates): a doorway left open, for a door the game's swing check refuses

# This game's catalogue has no food_* or survival_*: a person hides, not a bottle. "" drops.
HS_SWAP = {
    "food_watermelon": "nature_crop_melon", "survival_barrel": "furniture_trashcan",
    "survival_bucket": "", "survival_bottle": "", "survival_bottle_large": "", "survival_box": "furniture_cardboard_box_closed",
    "food_carton_small": "", "food_soda_can": "", "survival_box_large": "furniture_cardboard_box_closed",
    "food_mug": "", "food_cup_coffee": "", "survival_chest": "furniture_cardboard_box_closed", "food_banana": "", "food_pot": "",
}
NOT_DOORS = ("lockerdoor", "door_oven")   # func_door_rotating targetnames that are a leaf of furniture, not a doorway (an unnamed one is a cabinet's)
SLAB = 28.0     # source units: ~0.53 m, a slope's riser

TOOLS = ("TOOLS/", "tools/")
# The surface of a brush comes from dot-map's shared list (dot-map-convert/dotbsp/source_textures.tsv), the one every
# conversion reads; a new texture goes there, never into this file. `bsp.py unmapped <bsp>` lists what it misses.
TEXTURE_MAP = texturemap.load()

# Shared ids this game's mm_materials.gd has no surface for (it would draw as flat grey), and what stands in.
GAME_SURFACE = {
    "roof_clay": ("roof_tiles", None),
    "carpet_red": ("carpet", (0.8, 0.5, 0.46)),
    "carpet_blue": ("carpet", (0.62, 0.70, 0.86)),
    "carpet_grey": ("carpet", (0.75, 0.75, 0.75)),
    "carpet_pattern": ("carpet", None),
    "ceiling_tile": ("ceiling", None),
    "rock": ("stone_wall", None),
    "wallpaper_decrepit": ("plaster_worn", None),
    "glass_frosted": ("glass", None),
}

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
    "file_cabinet1_group": "furniture_side_table_drawers",
    "microwave": "furniture_kitchen_microwave",
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
    # A winter meat factory (mm_factory_winter): shelves, offices, a cold-store's crates and a laundry.
    "furnitureshelf001b": "furniture_bookcase_open",
    "furniturecupboard001a": "furniture_bookcase_closed",
    "furniturecouch002a": "furniture_lounge_sofa",
    "tableantique": "furniture_table",
    "prison_bedframe001b": "furniture_bed_single",
    "furniture_chair03a": "furniture_chair",
    "controlroom_desk001b": "furniture_desk",
    "controlroom_chair001a": "furniture_chair_desk",
    "chair_office01a": "furniture_chair_desk",
    "controlroom_filecabinet002a": "furniture_side_table_drawers",
    "filecabinet02": "furniture_side_table_drawers",
    "lockers001a": "furniture_bookcase_closed_doors",
    "monitor02": "furniture_computer_screen",
    "harddrive02": "furniture_speaker_small",
    "dryer": "furniture_dryer",
    "laundry_cart002": "survival_box_large",
    "woodbarrel001": "survival_barrel",
    "cinderblock01a": "nature_stone_small_a",
    "wood_pallet001a": "survival_box",
    "crates_fruit1": "survival_box_large",
    "partsbin01": "survival_box",
    "pumpkin01": "nature_crop_pumpkin",
    "terracotta01": "nature_pot_small",
    "christmas_gift_box_3": "furniture_cardboard_box_closed",
    "cardboard_box002a": "furniture_cardboard_box_closed",
    "wall_lamp2": "furniture_lamp_wall",
    "desk_lamp01": "furniture_lamp_square_table",
    "ceiling_fan_blade": "furniture_ceiling_fan",
}


# The author left every wall that is not a house as a developer grid. Those are given a
# suburban surface by what the box IS, since its texture says nothing: size and height tell a
# neighbour's tall wall from a fence, a path, a roof slab or a shed. Every name is an existing
# PhMaterials surface; the tint only chooses which pastel family it is.


# Every entity class an author uses for a loose prop; the _dynamic ones are placed furniture
# that does not move in the original, which a catalogue prop is not either (it is a disguise).
PROP_CLASSES = ("prop_physics", "prop_physics_multiplayer", "prop_physics_override",
                "prop_dynamic", "prop_dynamic_override")
START_CLASSES = ("info_player_start", "info_player_terrorist", "info_player_counterterrorist",
                 "info_player_deathmatch", "info_player_teamspawn")


def gd(p):
    return (p[0] * S, p[2] * S - FLOOR, -p[1] * S)


def kv(e, k, default=None):
    return e.get(k, default)


def vec(s):
    return [float(x) for x in s.split()]


def planes_of(bsp, index):
    first, count, _ = bsp.brushes[index]
    return [bsp.planes[s[0]][:4] for s in bsp.brushsides[first:first + count] if not s[3]]


def brush_boxes(bsp, index):
    """[((x range), (y range), (z range), phi)] in Source units for one brush, and whether it had to
    be cut into slabs. dotbsp's decompose: a box, a box turned about the vertical, a prism's turned
    bounding box, else slabs along the slope. (The local copy this replaces took a wedge for a box,
    because a wedge's six corners are all box corners: a ramp came out as a block twice its height.)"""
    out = dboxes.decompose(planes_of(bsp, index), bsp.brush_hull(index), slab=SLAB)
    cut = any(b["kind"] not in ("box", "turned", "prism") for b in out)
    return [(b["x"], b["y"], b["z"], b["phi"]) for b in out], int(cut)


# Furniture a crouching person fits behind, for a map the author furnished too thinly to hide in
# (the author's own props were mostly bottles, which this game's catalogue has not: --cover).
COVER_INDOOR = ("furniture_bed_single", "furniture_bookcase_closed_wide", "furniture_cabinet_bed_drawer", "furniture_lounge_sofa",
                "furniture_kitchen_cabinet", "furniture_bed_double", "furniture_cabinet_television", "furniture_side_table_drawers")


# What an office has that the author's brushes and desk clutter leave out (--dress): plants,
# a bookcase, a sofa and a bin on the open floor of each room, seeded so a rerun is the same.
OFFICE_DRESS = ("furniture_potted_plant", "furniture_plant_small1", "furniture_potted_plant", "furniture_bookcase_closed_wide",
                "furniture_trashcan", "furniture_lounge_sofa", "furniture_coat_rack_standing", "furniture_plant_small2")


def pin_one_way(doc):
    """--one-way=x,z: the door whose centre is there swings one way only. Returns how many were pinned."""
    n = 0
    for d in doc["doors"]:
        if any(abs(d["at"][0] - a) < 0.1 and abs(d["at"][2] - b) < 0.1 for a, b in ONE_WAY):
            d["away"] = False
            n += 1
    return n


def hang_doorways(m, doc, log=print):
    """A door in every doorway the author left open (--hang-doorways). This map's meeting rooms and
    offices are bare openings, not door entities, so add_doors finds nothing; the doorway is the
    gap of 1.4 m (what --widen-doors makes of the author's) between two collinear wall slabs with a
    header over it, and the door fills it up to the header. It runs after the widening, on finished
    coordinates. Props in the panel's sweep go, as add_doors does."""
    walls = []
    for b in doc["boxes"]:
        w, h, d = b["size"]
        if b.get("solid", True) and not b.get("yaw") and h >= 2.3 and b["at"][1] - h / 2 < 0.5 and min(w, d) <= 0.4 < max(w, d):
            walls.append(b)
    hung = 0
    for a in walls:
        axis = 2 if a["size"][2] > a["size"][0] else 0
        cross = 0 if axis == 2 else 2
        for c in walls:
            if c is a or c["size"][axis] <= c["size"][cross] or abs(c["at"][cross] - a["at"][cross]) > 0.02:
                continue
            if abs(c["size"][1] - a["size"][1]) > 0.01 or abs(c["at"][1] - a["at"][1]) > 0.01:
                continue
            lo = a["at"][axis] + a["size"][axis] / 2
            hi = c["at"][axis] - c["size"][axis] / 2
            if not 1.38 <= hi - lo <= 1.42:
                continue
            mid = (lo + hi) / 2
            # The header: a box over the gap, thin across the wall, its underside the door's top.
            heads = [b for b in doc["boxes"] if b["at"][1] - b["size"][1] / 2 > 1.8 and b["at"][1] - b["size"][1] / 2 < a["at"][1] + a["size"][1] / 2 - 0.1
                     and abs(b["at"][cross] - a["at"][cross]) < 0.3 and abs(b["at"][axis] - mid) < 0.1 and abs(b["size"][axis] - (hi - lo)) < 0.1
                     and b["size"][cross] <= 0.4]
            if not heads:
                continue
            top = min(b["at"][1] - b["size"][1] / 2 for b in heads)
            floor_y = a["at"][1] - a["size"][1] / 2
            if any(abs(d["at"][axis] - mid) < 0.3 and abs(d["at"][cross] - a["at"][cross]) < 0.3 for d in doc["doors"]):
                continue
            at = (mid, a["at"][cross]) if axis == 0 else (a["at"][cross], mid)
            if any(abs(at[0] - sx) < 0.8 and abs(at[1] - sz) < 0.8 for sx, sz in SKIP_DOORS):
                continue   # --skip-door: left open, as add_doors does
            # The author's own leaf, left standing in the opening in whatever material (dot-map's
            # drop_door_leaves only takes wood): a door-high slab, under 15 cm thick, inside the gap.
            leaves = [b for b in doc["boxes"] if b is not a and b is not c and 1.9 <= b["size"][1] <= 2.3 and min(b["size"][0], b["size"][2]) < 0.15
                      and abs(b["at"][cross] - a["at"][cross]) < 0.3 and lo - 0.05 <= b["at"][axis] - b["size"][axis] / 2 and b["at"][axis] + b["size"][axis] / 2 <= hi + 0.05
                      and b["size"][axis] < 1.2 and b["at"][1] - b["size"][1] / 2 < floor_y + 0.2]
            for b in leaves:
                doc["boxes"].remove(b)
            m.door("x" if axis == 0 else "z", lo, hi, a["at"][cross], floor_y, top, name="door", hinge="start")
            hung += 1
            gone = [q for q in doc["props"]
                    if lo - 0.5 <= q["at"][axis] <= hi + 0.5 and abs(q["at"][cross] - a["at"][cross]) <= 1.6 + 0.35 and abs(q["at"][1] - floor_y) < 1.5]
            for q in gone:
                doc["props"].remove(q)
            if gone:
                at = (mid, a["at"][cross]) if axis == 0 else (a["at"][cross], mid)
                log("  doorway at (%.1f, %.1f): %d props cleared from its swing" % (at[0], at[1], len(gone)))
    log("doorways: %d hung" % hung)
    return hung

# What stands against a wall by the kind of room, which is told by the floor's texture and the storey
# (--dress-walls): a map's beds, shelves, cabinets and counters are not on open floor, so the open-floor
# scatter (--dress) never reaches them. Ids are catalogue ids; the first match in FLOOR_KINDS wins.
FLOOR_KINDS = [("MILFLR", "tile"), ("TILEFLOOR", "tile"), ("CONCRETEFLOOR", "concrete"), ("CARPET", "carpet"),
               ("FLOOR02", "wood"), ("WOODFLOOR", "wood")]
WALL_DRESS = {
    "bedroom": ("furniture_bed_single", "furniture_bed_double", "furniture_cabinet_bed_drawer", "furniture_bookcase_closed_wide",
                "furniture_side_table_drawers", "furniture_lamp_round_floor", "furniture_bookcase_closed", "furniture_bed_single"),
    "lounge": ("furniture_lounge_sofa", "furniture_cabinet_television", "furniture_bookcase_closed_wide", "furniture_side_table",
               "furniture_lamp_square_floor", "furniture_potted_plant", "furniture_bookcase_open", "furniture_coat_rack_standing"),
    "kitchen": ("furniture_kitchen_cabinet_drawer", "furniture_kitchen_fridge", "furniture_kitchen_stove", "furniture_kitchen_sink",
                "furniture_kitchen_cabinet", "furniture_washer", "furniture_dryer", "furniture_bathroom_cabinet_drawer"),
    "store": ("furniture_cardboard_box_closed", "furniture_bookcase_open", "furniture_cabinet_bed_drawer", "furniture_washer",
              "furniture_bench", "furniture_bookcase_open_low"),
}
# One of these per room at most (a second bed in a bedroom reads as a dormitory).
ONE_PER_ROOM = ("furniture_bed_single", "furniture_bed_double", "furniture_kitchen_fridge", "furniture_kitchen_stove", "furniture_lounge_sofa",
                "furniture_cabinet_television", "furniture_kitchen_sink", "furniture_lamp_round_floor", "furniture_lamp_square_floor")
ROOM_SIZE = 4.5   # metres: two props of ONE_PER_ROOM nearer than this are taken to be in one room
FRONT = 0.7       # metres kept clear in front of a wall piece: a person passes


def floor_zones(bsp):
    """The map's floors by texture: [(x0, x1, y, z0, z1, kind)] in the importer's coordinates before
    the origin shift, from every upward horizontal face of 1.5 m2 or more whose texture FLOOR_KINDS knows."""
    zones = []
    for f in bsp.model_faces(0):
        name, _flags = bsp.face_material(f)
        up = name.upper().split("/")[-1]
        kind = next((k for t, k in FLOOR_KINDS if up.startswith(t)), None)
        pts = bsp.face_points(f)
        if kind is None or len(pts) < 3 or f[1] != 0 or bsp.planes[f[0]][2] < 0.9:
            continue
        g = [gd(p) for p in pts]
        if max(p[1] for p in g) - min(p[1] for p in g) > 0.01:
            continue
        x0, x1 = min(p[0] for p in g), max(p[0] for p in g)
        z0, z1 = min(p[2] for p in g), max(p[2] for p in g)
        if (x1 - x0) * (z1 - z0) >= 1.5:
            zones.append((x0, x1, g[0][1], z0, z1, kind))
    return zones


def retexture_ceilings(boxes):
    """A thin skin in a floor material that hangs 2 to 4 m over a solid top is a ceiling the author
    painted with the floor's tile: the underside is what a player sees, so it takes the ceiling
    material (the hotel's lobby read as a marble checker overhead)."""
    n = 0
    for b in boxes:
        if b["size"][1] > 0.05 or b.get("mat") != "tile_floor":
            continue
        x, y, z = b["at"]
        for o in boxes:
            if o is b or not o.get("solid", True) or not docboxes.within(o, x, z):
                continue
            top = o["at"][1] + o["size"][1] / 2
            if 2.0 <= y - top <= 4.0:
                b["mat"] = "ceiling"
                b.pop("tint", None)
                n += 1
                break
    return n


def _roofed(m, x, y, z):
    """Something solid over (x, z) between 2 m and 4 m above y: a room, not the yard or a pool."""
    for b in m.boxes:
        if b.get("solid", True) and docboxes.within(b, x, z):
            bot = b["at"][1] - b["size"][1] / 2
            if y + 2.0 <= bot <= y + 4.0:
                return True
    return False


def dress_walls(m, zones, count, seed, log=print):
    """Furniture with its back to a wall, in every roofed room (--dress-walls), after the doors are
    hung: each candidate is a catalogue prop set against the inner face of a wall box with the whole
    prop on one wall and on floor, nothing solid or standing in it, 0.7 m clear in front of it, no
    low step-like box within 0.5 m (a stair's foot), and no door within 1.9 m of it (a swing and a
    doorway). The kind of prop is the room's: its floor texture, and on an upper storey a wooden
    floor is a bedroom. Seeded, so a rerun is the same."""
    rng = random.Random(seed)
    levels = sorted({round(z[2], 2) for z in zones})
    placed_by = {}
    # Every wall face at every level, as (side, face, lo, hi, level).
    cands = []
    for lv in levels:
        for b in m.boxes:
            if not b.get("solid", True) or b.get("yaw") or b.get("visible", True) is False:
                continue
            (bx, by, bz), (sx, sy, sz) = b["at"], b["size"]
            if by - sy / 2 > lv + 0.5 or by + sy / 2 < lv + 1.8 or sy < 1.8:
                continue
            for side, face, lo, hi in (("n", bz + sz / 2, bx - sx / 2, bx + sx / 2), ("s", bz - sz / 2, bx - sx / 2, bx + sx / 2),
                                       ("w", bx + sx / 2, bz - sz / 2, bz + sz / 2), ("e", bx - sx / 2, bz - sz / 2, bz + sz / 2)):
                if hi - lo >= 0.8:
                    cands.append((side, face, lo, hi, lv))
    cands = cands * 8   # a wall is tried at several places along it and with several props
    rng.shuffle(cands)
    storeys = [lv for lv in levels if any(_roofed(m, (z[0] + z[1]) / 2, z[2], (z[3] + z[4]) / 2) for z in zones if round(z[2], 2) == lv)]
    placed = []
    per_level = {lv: 0 for lv in storeys}
    quota = max(2, count // max(1, len(storeys)))
    taken = 0
    for pass_quota in (quota, quota * 2, count):
        for side, face, lo, hi, lv in cands:
            if taken >= count:
                break
            if lv not in per_level or per_level[lv] >= pass_quota:
                continue
            along = rng.uniform(lo + 0.6, hi - 0.6) if hi - lo > 1.2 else (lo + hi) / 2
            sign = {"n": 1, "w": 1, "s": -1, "e": -1}[side]
            probe = (along, face + sign * 0.5) if side in "ns" else (face + sign * 0.5, along)
            px, pz = (probe[0], probe[1]) if side in "ns" else (probe[0], probe[1])
            if not _roofed(m, px, lv, pz):
                continue
            zone = next((z for z in zones if z[0] <= px <= z[1] and z[3] <= pz <= z[4] and abs(z[2] - lv) < 0.1), None)
            kind = zone[5] if zone else "wood"
            room = {"tile": "kitchen", "concrete": "store"}.get(kind) or ("bedroom" if lv >= 2.0 else "lounge")
            pid = rng.choice(WALL_DRESS[room])
            w, d = build_maps.footprint(pid, {"n": 0.0, "s": 180.0, "w": 90.0, "e": -90.0}[side])
            # The prop's rectangle and the clear strip in front of it.
            if side in "ns":
                x0, x1 = along - w / 2, along + w / 2
                z0, z1 = (face, face + d) if side == "n" else (face - d, face)
                fx0, fx1 = x0, x1
                fz0, fz1 = (z1, z1 + FRONT) if side == "n" else (z0 - FRONT, z0)
                if x0 < lo + 0.05 or x1 > hi - 0.05:
                    continue
            else:
                z0, z1 = along - d / 2, along + d / 2
                x0, x1 = (face, face + w) if side == "w" else (face - w, face)
                fz0, fz1 = z0, z1
                fx0, fx1 = (x1, x1 + FRONT) if side == "w" else (x0 - FRONT, x0)
                if z0 < lo + 0.05 or z1 > hi - 0.05:
                    continue
            _, sy_, _ = build_maps.size_of(pid)
            if not _rect_clear(m, x0 + 0.06, x1 - 0.06, z0 + 0.06, z1 - 0.06, lv, 0.1, 1.9) or not _rect_clear(m, fx0, fx1, fz0, fz1, lv, 0.1, 1.9):
                continue
            if not _rect_floored(m, x0, x1, z0, z1, lv) or not _rect_floored(m, fx0, fx1, fz0, fz1, lv):
                continue
            # A stair's foot: a step-like box rising 5 to 75 cm above this floor within 0.5 m.
            if not _rect_clear(m, x0 - 0.5, x1 + 0.5, z0 - 0.5, z1 + 0.5, lv, 0.12, 0.75, whole_box=False):
                continue
            cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
            if any(abs(dd["at"][1] - lv - 1.0) < 1.6 and abs(dd["at"][0] - cx) < 1.9 and abs(dd["at"][2] - cz) < 1.9 for dd in m.doors):
                continue
            if any(abs(q["at"][1] - lv) < 1.5 and ((q["at"][0] - cx) ** 2 + (q["at"][2] - cz) ** 2) < 1.2 ** 2 for q in m.props):
                continue
            if pid in ONE_PER_ROOM and any(o == pid and abs(oy - lv) < 0.2 and (ox - cx) ** 2 + (oz - cz) ** 2 < ROOM_SIZE ** 2 for o, ox, oy, oz in placed):
                continue
            if any(abs(oy - lv) < 0.2 and (ox - cx) ** 2 + (oz - cz) ** 2 < 1.3 ** 2 for _o, ox, oy, oz in placed):
                continue
            if any(_overlap(q, pid, (x0, x1, z0, z1), lv) for q in m.props):
                continue
            m.against(pid, side, face, along, y=lv)
            placed.append((pid, cx, lv, cz))
            per_level[lv] += 1
            taken += 1
    for lv in storeys:
        log("wall dressing at floor %.2f: %d placed" % (lv, per_level[lv]))
    return taken


def _rect_clear(m, x0, x1, z0, z1, lv, lo_rel, hi_rel, whole_box=True):
    """No solid box between lv + lo_rel and lv + hi_rel (its top for a step test) in the rectangle.
    whole_box True: any box overlapping that height band; False: only a box whose top is in the band."""
    for b in m.boxes:
        if not b.get("solid", True):
            continue
        (bx, by, bz), (sx, sy, sz) = b["at"], b["size"]
        if b.get("yaw"):
            yaw = math.radians(b["yaw"])
            sx, sz = abs(sx * math.cos(yaw)) + abs(sz * math.sin(yaw)), abs(sx * math.sin(yaw)) + abs(sz * math.cos(yaw))
        if bx + sx / 2 <= x0 or bx - sx / 2 >= x1 or bz + sz / 2 <= z0 or bz - sz / 2 >= z1:
            continue
        top, bot = by + sy / 2, by - sy / 2
        if whole_box:
            if top > lv + lo_rel and bot < lv + hi_rel:
                return False
        elif lv + lo_rel < top < lv + hi_rel and bot < lv + 0.3 and sy < 1.0 and min(sx, sz) >= 0.25:   # not a skirting
            return False
    return True


def _rect_floored(m, x0, x1, z0, z1, lv):
    """Floor at this level under the rectangle's corners and middle."""
    for fx in (x0 + 0.03, (x0 + x1) / 2, x1 - 0.03):
        for fz in (z0 + 0.03, (z0 + z1) / 2, z1 - 0.03):
            if not m._floored(fx, lv, fz, edge=0.0):
                return False
    return True


def _overlap(q, pid, rect, lv):
    qw, qd = build_maps.footprint(q["id"], q.get("yaw", 0.0))
    if abs(q["at"][1] - lv) > 1.2:
        return False
    x0, x1, z0, z1 = rect
    return q["at"][0] + qw / 2 + 0.15 > x0 and q["at"][0] - qw / 2 - 0.15 < x1 and q["at"][2] + qd / 2 + 0.15 > z0 and q["at"][2] - qd / 2 - 0.15 < z1


def spread_spawns(m, levels, count, gap=3.5, log=print):
    """Spawns spread over rooms and floors (--spread-spawns=N), run last, after the doors are hung and
    the props down. The author's starts come in adjacent pairs 1.2 m apart (two to a doorway), so a start
    within `gap` metres of one already kept on its floor is dropped; the clearest open floor
    (`Map.spots`, which keeps 1.2 m off walls, props and 1.6 m off a door) tops up to N, farthest from
    what is chosen first, and no one floor takes more than its share until the rest cannot be filled.
    Floors that are not roofed (the yard) count as one floor, y 0."""
    def key(y):
        return round(y, 1)
    chosen = []
    for sp in m.spawns["players"]:
        x, y, z = sp["at"]
        if all(abs(key(y) - key(c[1])) > 0.2 or (x - c[0]) ** 2 + (z - c[2]) ** 2 >= gap ** 2 for c in chosen):
            chosen.append((x, y, z, sp["yaw"]))
    log("spawns: %d of the author's %d kept, %.1f m apart" % (len(chosen), len(m.spawns["players"]), gap))
    pool = []
    for lv in levels:
        for size, x, z in m.spots(y=lv, step=1.5, top=400):
            # A yard needs 2 m of clear floor round a spot; a room's spot may be as tight as 1.2 m (`spots` goes no lower).
            if (size >= 2.0 and abs(lv) < 0.2 and not _roofed(m, x, lv, z)) or _roofed(m, x, lv, z):
                pool.append((x, lv + 0.05, z))
    floors = sorted({key(y) for _x, y, _z in pool} | {key(c[1]) for c in chosen})
    for share in (max(2, -(-count // max(1, len(floors)))), count):
        while len(chosen) < count:
            tally = {}
            for c in chosen:
                tally[key(c[1])] = tally.get(key(c[1]), 0) + 1
            best, best_d = None, 0.0
            for x, y, z in pool:
                if tally.get(key(y), 0) >= share:
                    continue
                d = min(((x - c[0]) ** 2 + (z - c[2]) ** 2 + (0.0 if abs(y - c[1]) < 0.2 else 400.0)) for c in chosen) if chosen else 1e9
                if d > best_d:
                    best, best_d = (x, y, z), d
            if best is None or best_d < gap ** 2:
                break
            chosen.append((best[0], best[1], best[2], 0.0))
    m.spawns["players"][:] = []
    for x, y, z, yaw in chosen:
        m.spawn(x, z, yaw=yaw, y=y)
    log("spawns: %d spread over %d floors" % (len(chosen), len(floors)))
    return len(chosen)


# --- The author's sky, light, fog, weather and sound ---------------------------------------------------
#
# What the file says about the hour and the air, read for this game's own sky, sun, fog and weather (the
# author's sky textures are never carried; a name only says what mood to paint). Nothing here is in dot-map's
# reader yet: it wants a shared `environment` pass there (nightly item `dotbsp-environment`).

# skyname -> (zenith, horizon, the ground under the horizon). The horizon is the fog colour when the map has fog,
# since distance fades into the sky and any other horizon draws a seam along every ridge.
SKY_MOODS = {
    "office": ([0.46, 0.53, 0.65], [0.66, 0.70, 0.76], [0.30, 0.31, 0.32]),          # an overcast afternoon
    "sky_day02_09": ([0.42, 0.50, 0.62], [0.68, 0.74, 0.80], [0.52, 0.55, 0.58]),   # an overcast winter afternoon
    "jungle": ([0.26, 0.50, 0.82], [0.74, 0.85, 0.88], [0.28, 0.32, 0.24]),          # a clear green-tinged day
    "militia_hdr": ([0.27, 0.37, 0.60], [0.86, 0.72, 0.62], [0.30, 0.29, 0.27]),     # a clear dusk
}

PRECIP_RAIN = (0, 4)   # func_precipitation's preciptype: 0 and 4 rain; 1, 3 and 6 snow; 2 and 5 ash (drawn as snow)


def _colour3(s):
    return [round(max(0.0, min(1.0, float(c) / 255.0)), 3) for c in s.split()[:3]]


def model_bounds(bsp, index):
    """A brush model's bounding box in the document's axes, metres: ([x0, y0, z0], [x1, y1, z1]), or None."""
    lo = [1e9, 1e9, 1e9]
    hi = [-1e9, -1e9, -1e9]
    for bi in bsp.model_brushes(index):
        for (x0, x1), (y0, y1), (z0, z1), _phi in brush_boxes(bsp, bi)[0]:
            lo = [min(lo[0], x0 * S), min(lo[1], z0 * S - FLOOR), min(lo[2], -y1 * S)]
            hi = [max(hi[0], x1 * S), max(hi[1], z1 * S - FLOOR), max(hi[2], -y0 * S)]
    return None if lo[0] > hi[0] else (lo, hi)


def environment(bsp, fog_override=None):
    """The author's atmosphere: {"env": the document's environment fields, "weather": volumes in the
    document's axes before the origin shift (or None), "lights": extra lamps [(x, y, z, energy, colour)]}.

    Sun: the first light_environment's colour, brightness and angles (Source's yaw less 90 is godot's; pitch is
    the same sign), kept between 8 and 80 degrees so a sun never lies along the floor nor straight down.
    Ambient: its colour and brightness, as the colour of the shade (the game mixes it a quarter into its grey)
    and an energy 0.42 to 0.62. Fog: the controller's colour, start and end in metres, and its density cap."""
    world = next((e for e in bsp.entities if e.get("classname") == "worldspawn"), {})
    sky = str(world.get("skyname", "")).lower()
    top, horizon, ground = SKY_MOODS.get(sky, ([0.32, 0.52, 0.82], [0.72, 0.82, 0.92], [0.35, 0.33, 0.30]))
    env = {}
    sun = next((e for e in bsp.entities if e.get("classname") == "light_environment"), None)
    if sun is not None:
        c = vec(sun.get("_light", "255 255 255 200"))
        ang = vec(sun.get("angles", "0 0 0"))
        pitch = float(sun.get("pitch", ang[0]))
        env["sun_colour"] = [round(v / 255.0, 3) for v in c[:3]]
        env["sun_energy"] = round(max(0.6, min(1.0, math.sqrt(c[3] / 400.0) * 0.95)), 2)
        env["sun_pitch"] = -round(max(8.0, min(80.0, abs(pitch))))
        env["sun_yaw"] = round((ang[1] - 90.0) % 360.0)
        a = vec(sun.get("_ambient", "180 190 200 200"))
        env["ambient"] = [round(v / 255.0, 3) for v in a[:3]]
        env["ambient_energy"] = round(max(0.42, min(0.62, 0.30 + a[3] / 1000.0)), 2)
    fog = next((e for e in bsp.entities if e.get("classname") == "env_fog_controller" and str(e.get("fogenable", "1")) != "0"), None)
    if fog is not None:
        env["fog_colour"] = _colour3(fog.get("fogcolor", "180 190 200"))
        env["fog_start"] = round(float(fog.get("fogstart", 0)) * S, 1)
        env["fog_end"] = round(float(fog.get("fogend", 1000)) * S, 1)
        env["fog_max"] = round(float(fog.get("fogmaxdensity", 1.0)), 2)
    if fog_override:
        env["fog_start"], env["fog_end"], env["fog_max"] = fog_override
        env.setdefault("fog_colour", [0.7, 0.74, 0.78])
    if "fog_colour" in env:
        horizon = env["fog_colour"]
    env["sky_top"], env["sky_horizon"], env["ground"] = [round(v, 3) for v in top], [round(v, 3) for v in horizon], ground

    volumes = []
    kind = "snow"
    for e in bsp.entities:
        if e.get("classname") != "func_precipitation" or not str(e.get("model", "")).startswith("*"):
            continue
        b = model_bounds(bsp, int(e["model"][1:]))
        if b is None:
            continue
        kind = "rain" if int(float(e.get("preciptype", 0))) in PRECIP_RAIN else "snow"
        # The author stacks copies of one brush to thicken the fall; the document asks for density instead.
        if not any(v == b for v in volumes):
            volumes.append(b)
    lights = []
    for e in bsp.entities:
        cls = e.get("classname")
        if cls in ("point_spotlight", "env_fire"):
            gx, gy, gz = gd(vec(e["origin"]))
            spot = cls == "point_spotlight"
            lights.append((gx, gy - 0.4 if spot else gy + 0.3, gz, 0.9 if spot else 1.1,
                           _colour3(e["rendercolor"]) if spot and e.get("rendercolor") else [1.0, 0.62, 0.28]))
    return {"env": env, "weather": {"kind": kind, "volumes": volumes} if volumes else None, "lights": lights}


def weather_block(weather, shift, seed=1):
    """The document's `weather` (a dot-weather document) from environment()'s volumes, shifted with the map."""
    ox, oy, oz = shift
    vols = []
    for lo, hi in weather["volumes"]:
        vols.append({"min": [round(lo[0] - ox, 2), round(lo[1] - oy, 2), round(lo[2] - oz, 2)],
                     "max": [round(hi[0] - ox, 2), round(hi[1] - oy, 2), round(hi[2] - oz, 2)]})
    colour = [1.0, 1.0, 1.0] if weather["kind"] == "snow" else [0.78, 0.84, 0.95]
    return {"seed": seed, "precipitation": {"kind": weather["kind"], "density": 1.6, "colour": colour, "volumes": vols}}


def patch_environment(bsp, path, fog_override=None, ambience=None):
    """--env-only: put the environment into a finished document and touch nothing else (a hand-edited map)."""
    with open(path) as f:
        doc = json.load(f)
    doc["environment"].update(environment(bsp, fog_override)["env"])
    if ambience:
        doc.update(ambience)
    with open(path, "w") as f:
        f.write(json.dumps(doc, indent=1) + "\n")
    print("environment patched into", path)


def main(argv):
    global FLOOR, MIN_SIZE
    args = [a for a in argv[1:] if not a.startswith("--")]
    out_path = None
    style = ""
    fields = {}
    drops = []
    clears = []
    pockets = False
    box_budget = {}
    widen = False
    hang = False
    dress = 0
    dress_walls_n = 0
    spread_n = 0
    no_doors = False
    slide = False
    cover = 0
    dusk = False
    max_lights = 0  # 0 = keep every light: the games no longer cap a map (hide-n-seek cc47546, murder-mystery 9fe8314)
    cover = 0
    cover_gap = 3.0
    blurb = ""
    cover_gap = 2.5
    cover_clear = 2.0
    hiders_far = 0.0
    hiders_at = None
    cover_away = (0.0, 0.0)
    lobby = None
    cover_seed = 7
    drop_kinds = []
    thin = {}
    terrain = ""
    graft = None
    budget = 24000
    fog_override = None
    ambience = {}
    env_only = ""
    for a in argv[1:]:
        if a.startswith("--out="):
            out_path = a[6:]
        elif a.startswith("--fog="):
            fog_override = tuple(float(t) for t in a[6:].split(","))
        elif a.startswith("--ambience="):
            beds = a[11:].split(",")
            ambience["ambience"] = beds[0]
            if len(beds) > 1:
                ambience["ambience_indoor"] = beds[1]
        elif a.startswith("--env-only="):
            env_only = a[11:]
        elif a.startswith("--cover="):
            cover = int(a[8:])
        elif a.startswith("--cover-gap="):
            cover_gap = float(a[12:])
        elif a.startswith("--skip-door="):
            SKIP_DOORS.append(tuple(float(t) for t in a[12:].split(",")))
        elif a.startswith("--one-way="):
            ONE_WAY.append(tuple(float(t) for t in a[10:].split(",")))
        elif a.startswith("--skip-start="):
            SKIP_STARTS.add(int(a[13:]))
        elif a.startswith("--max-lights="):
            max_lights = int(a[13:])
        elif a == "--dusk":
            dusk = True
        elif a.startswith("--blurb="):
            blurb = a[8:]
        elif a == "--widen-doors":
            widen = True
        elif a == "--hang-doorways":
            hang = True
        elif a.startswith("--dress="):
            dress = int(a[8:])
        elif a.startswith("--dress-walls="):
            dress_walls_n = int(a[14:])
        elif a.startswith("--spread-spawns="):
            spread_n = int(a[16:])
        elif a == "--no-doors":
            no_doors = True
        elif a.startswith("--drop-kind="):
            drop_kinds.append(a[12:])
        elif a.startswith("--thin="):
            k, _, n = a[7:].partition(":")
            thin[k] = int(n)
        elif a == "--slide-doors":
            slide = True
        elif a.startswith("--floor="):
            FLOOR = float(a[8:])
        elif a.startswith("--min-size="):
            MIN_SIZE = float(a[11:])
        elif a == "--terrain" or a.startswith("--terrain="):
            terrain = a[10:] or "grass"
        elif a.startswith("--graft-terrain="):
            graft = a[16:]
        elif a.startswith("--terrain-budget="):
            budget = int(a[17:])
        elif docboxes.budget_flag(a, box_budget):
            pass
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
    if env_only:
        patch_environment(bsp_read.Bsp(args[0]).load(), env_only, fog_override, ambience)
        return
    if graft:
        # A committed document keeps its hand edits and its flags: only its stepped field changes.
        with open(graft) as f:
            doc = json.load(f)
        swap_terrain(doc, terrain_tris(bsp_read.Bsp(args[0]).load()), terrain or "grass", TERRAIN_TINT if (terrain or "grass") == "grass" else None, budget)
        with open(graft, "w") as f:
            f.write(json.dumps(doc, indent=1) + "\n")
        print("wrote", graft)
        return
    bsp_path, mid, name, author, url = args[:5]
    passledger.reset()
    bsp = bsp_read.Bsp(bsp_path).load()
    m = build_maps.Map(
        mid, name, blurb or "A map converted from a community original by %s (%s)." % (author, url),
        dict(build_maps.DUSK) if dusk else {"sky_top": [0.32, 0.52, 0.82], "sky_horizon": [0.72, 0.82, 0.92], "ground": [0.35, 0.33, 0.30],
         "sun_pitch": -55, "sun_yaw": 30, "sun_energy": 1.0, "ambient": [0.62, 0.66, 0.72], "ambient_energy": 0.5},
        kill_y=-20.0)
    atmosphere = environment(bsp, fog_override)
    m.doc["environment"].update(atmosphere["env"])
    m.doc["environment"].pop("fog", None)
    m.doc.update(ambience)
    m.doc["author"] = author
    m.doc.update(fields)
    m.doc["source"] = url

    sliced = skipped = 0
    for bi, (ox, oy, oz) in docboxes.world_brushes(bsp):
        names = docboxes.brush_material_names(bsp, bi)
        mt = docboxes.majority_material(names, TEXTURE_MAP, ("flat", None))
        if mt is not None and mt[0] in GAME_SURFACE:
            mt = GAME_SURFACE[mt[0]] if mt[1] is None else (GAME_SURFACE[mt[0]][0], mt[1])
        invisible = False
        if mt is None:
            # The author's sky box, clip, playerclip and nodraw solids are walls to a player: solid, drawn as nothing.
            if docboxes.stops_player(bsp, bi, names):
                mt, invisible = ("flat", None), True
            else:
                skipped += 1
                passledger.note("tool_only_brush", 1, "a brush with no solid contents the importer skips (trigger, hint, areaportal)")
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
                gx, gy, gz = gd((lx * c - ly * sn + ox, lx * sn + ly * c + oy, (z0 + z1) / 2 + oz))
                bx = m.box((gx, gy, gz), ((x1 - x0) * S, (z1 - z0) * S, (y1 - y0) * S), mt[0], mt[1], yaw=phi)
            else:
                # Source y is godot -z: the box's range flips.
                bx = m.span((x0 + ox) * S, (x1 + ox) * S, (z0 + oz) * S - FLOOR, (z1 + oz) * S - FLOOR, -(y1 + oy) * S, -(y0 + oy) * S, mt[0], mt[1])
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
            (x0, x1), (y0, y1), (z0, z1) = c["x"], c["z"], c["y"]
            m.span(x0 * S, x1 * S, y0 * S - FLOOR, y1 * S - FLOOR, -z1 * S, -z0 * S, terrain, (0.85, 0.9, 0.78) if terrain == "grass" else None)
            n += 1
        print("terrain: %d ground boxes from the displacements" % n)
    print("brushes %d  tool-only %d  sliced %d  boxes %d" % (len(bsp.model_brushes(0)), skipped, sliced, len(m.boxes)))

    docboxes.drop_door_leaves(m.boxes)
    print("ceilings: %d floor-tiled skins retextured" % retexture_ceilings(m.boxes))
    docboxes.prune_far_scenery(m.boxes, [gd(vec(e["origin"])) for e in bsp.entities if e.get("classname") in START_CLASSES])
    if MIN_SIZE:
        print("small boxes dropped: %d" % docboxes.drop_small(m.boxes, MIN_SIZE))

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
    lights = []
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
            c = c + [255.0, 255.0, 255.0, 200.0][len(c):]  # "r g b" without the brightness
            c = (list(c) + [255.0, 255.0, 255.0, 200.0][len(c):])[:4] if len(c) < 4 else c   # "r g b" without a brightness
            lights.append((gx, gy, gz, min(1.2, c[3] / 200.0), [c[0] / 255, c[1] / 255, c[2] / 255]))
    # --max-lights=N (default 0 = keep every light) and a browser draws 8 a surface: keep the author's lights
    # at least `gap` metres apart, widening the gap until they fit, each kept one a little stronger for those it stood for.
    lights += [(gx, gy, gz, en, col) for gx, gy, gz, en, col in atmosphere["lights"]]
    kept_l, gap = (lights, 0.0) if max_lights <= 0 else dlights.thin_by_gap(lights, max_lights)
    for gx, gy, gz, en, col in kept_l:
        m.light(gx, gy, gz, rng=9.0 + gap, energy=dlights.strengthen(en, gap), colour=col)
    if gap:
        print("lights: %d of the author's %d kept, %.1f m apart" % (len(kept_l), len(lights), gap))
        print("warning: %d lights dropped by --max-lights=%d (--max-lights=0 keeps all)" % (len(lights) - len(kept_l), max_lights), file=sys.stderr)
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
    author_y = []   # the floor each of the author's starts stands on, for the origin shift below
    starts = [e for e in bsp.entities if e.get("classname") in START_CLASSES]
    gstarts = [gd(vec(e["origin"])) for e in starts]
    ys = sorted((support(g[0], g[2], None, 0.0, g[1] + 0.6) or g[1] - 0.05) for g in gstarts)
    floor_y = 0.0
    if cover:
        # Furniture to crouch behind on each floor the author's starts stand on (a map furnished thinly),
        # a share of the count for each, seeded so a rerun is the same.
        levels = sorted({round(support(g[0], g[2], None, 0.0, g[1] + 0.6) or max(g[1] - 0.05, 0.0), 2) for g in gstarts})
        for lv in levels:
            print("cover furniture at floor %.2f: %d placed" % (lv, docboxes.scatter_cover(m, max(2, cover // len(levels)), 7, COVER_INDOOR, spacing=cover_gap, clear=1.6, floor_y=lv)))
    if dress:
        levels = sorted({round(support(g[0], g[2], None, 0.0, g[1] + 0.6) or max(g[1] - 0.05, 0.0), 2) for g in gstarts})
        for lv in levels:
            print("dressing at floor %.2f: %d placed" % (lv, docboxes.scatter_cover(m, max(2, dress // len(levels)), 11, OFFICE_DRESS, spacing=4.0, clear=1.5, floor_y=lv)))
    # Everybody starts apart: the author's starts (they stand on whatever floor is under them), then
    # the clearest open floor until there are 24, at least 6 m from any other start.
    for i, e in enumerate(starts):
        if i in SKIP_STARTS:
            continue
        gx, gy, gz = gstarts[i]
        ang = vec(e.get("angles", "0 0 0"))
        floor = support(gx, gz, None, 0.0, gy + 0.6)
        if floor is None:
            print("start %d at (%.1f, %.1f, %.1f) has no floor under it: left out" % (i, gx, gy, gz))
            continue
        m.spawn(gx, gz, yaw=ang[1] - 90.0, y=floor + 0.05)
        author_y.append(round(floor + 0.05, 2))
    have = [(sp["at"][0], sp["at"][2]) for sp in m.spawns["players"]]
    for size, x, z in m.spots(step=2.0, top=200):
        if len(m.spawns["players"]) >= 24:
            break
        if all((x - a) ** 2 + (z - b) ** 2 >= 36.0 for a, b in have):
            m.spawn(x, z, yaw=0.0, y=0.05)
            have.append((x, z))
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
        # The level is the author's own starts' (most of them first), never the median of every
        # spawn: the clearest open floor the builder adds lands on a terrain yard, which moved the
        # median off any floor with a slab under it and left the map unshifted (--terrain).
        levels = sorted(set(author_y), key=lambda v: (-author_y.count(v), v))
        median = sorted(sp["at"][1] for sp in doc["spawns"]["players"])
        levels.append(median[len(median) // 2])
        for lv in levels:
            oy = round(lv - 0.05, 3)
            ground = [b for b in doc["boxes"] if b.get("solid", True) and abs(b["at"][1] + b["size"][1] / 2 - oy) < 0.05
                      and b["size"][0] > 4.0 and b["size"][2] > 4.0]
            if ground:
                break
    ox = oz = 0.0
    if ground:
        cx = sum(sp["at"][0] for sp in doc["spawns"]["players"]) / len(doc["spawns"]["players"])
        cz = sum(sp["at"][2] for sp in doc["spawns"]["players"]) / len(doc["spawns"]["players"])
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
        passledger.rebase(-ox, -oy, -oz)
    if atmosphere["weather"] is not None:
        doc["weather"] = weather_block(atmosphere["weather"], (ox, oy, oz))
        print("weather: %s over %d volumes" % (atmosphere["weather"]["kind"], len(atmosphere["weather"]["volumes"])))
    # A start far below the rest is another area of the author's (a pit, a sealed cellar the conversion has no floor for).
    ysp = sorted(sp["at"][1] for sp in doc["spawns"]["players"])
    low = [sp for sp in doc["spawns"]["players"] if sp["at"][1] < ysp[len(ysp) // 2] - 8.0]
    for sp in low:
        doc["spawns"]["players"].remove(sp)
    if low:
        print("left out %d starts more than 8 m below the rest" % len(low))
    print("ground pads under %d spawn groups with no floor" % docboxes.pad_spawns(doc, list(doc["spawns"])))
    print("spawns snapped onto their floor: %d" % docboxes.snap_spawns(doc))
    if pockets:
        print("pruned %d props that left a pocket the bots cannot leave" % docboxes.prune_pockets(doc, build_maps.size_of, build_maps.footprint, spawn_key="players"))
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
    # Layered models of the author's (a shelf drawn as three) land on one catalogue prop in one place.
    stacked = []
    for q in doc["props"]:
        if not any(q["id"] == k["id"] and all(abs(q["at"][i] - k["at"][i]) < 0.05 for i in (0, 2)) and abs(q["at"][1] - k["at"][1]) < 0.1 for k in stacked):
            stacked.append(q)
    if len(stacked) != len(doc["props"]):
        print("dropped %d props stacked on an identical one" % (len(doc["props"]) - len(stacked)))
        doc["props"][:] = stacked
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
    if not no_doors:
        # add_doors hangs `prop_door_rotating` only, and this author's doors are brush entities with
        # their hinge as the origin; they are shown to it as that class. A locker leaf or an oven door
        # is not a doorway, and the ones that find no doorway are reported by add_doors.
        hinged = [dict(e, classname="prop_door_rotating") for e in bsp.entities
                  if e.get("classname") == "func_door_rotating" and e.get("targetname")
                  and not str(e["targetname"]).lower().startswith(NOT_DOORS)]
        docboxes.add_doors(m, doc, bsp.entities + hinged, (ox, oy + FLOOR, oz), slide, scale=S, skip=SKIP_DOORS)
        # A double door is two entities whose hinges each find the whole doorway: one leaf across it is kept.
        kept_d = []
        for d in doc["doors"]:
            if not any(abs(d["at"][0] - k["at"][0]) < 0.3 and abs(d["at"][1] - k["at"][1]) < 0.3 and abs(d["at"][2] - k["at"][2]) < 0.3 for k in kept_d):
                kept_d.append(d)
        if len(kept_d) != len(doc["doors"]):
            print("doors: %d double-hung doorways kept as one leaf" % (len(doc["doors"]) - len(kept_d)))
            doc["doors"][:] = kept_d
    if widen:
        print("widened %d doorways to 1.4 m" % docboxes.widen_doors(doc["boxes"], doors=doc["doors"]))
    if hang:
        hang_doorways(m, doc)
    pin_one_way(doc)   # after --hang-doorways: the doors it hung are pinned too
    # The budget runs after the doors are hung and widened: they look for the author's narrow, untrimmed slabs.
    docboxes.apply_budget(doc["boxes"], box_budget)
    if dress_walls_n or spread_n:
        zones = [(z[0] - ox, z[1] - ox, round(z[2] - oy, 3), z[3] - oz, z[4] - oz, z[5]) for z in floor_zones(bsp)]
    if dress_walls_n:
        dress_walls(m, zones, dress_walls_n, 17)
    if spread_n:
        spread_spawns(m, sorted({z[2] for z in zones} | {0.0}), spread_n)
        m._face_spawns()
    # The doors are hung after build() settled the spawns: one that stood against a doorway is in
    # the panel now, so settle again with the doors in the way.
    if doc["doors"] is m.doors and doc["boxes"] is m.boxes and doc["spawns"] is m.spawns:
        m._settle_spawns()
    else:
        raise SystemExit("the document no longer shares the map's lists: settle the spawns from the document")
    if terrain:
        swap_terrain(doc, tris, terrain, TERRAIN_TINT if terrain == "grass" else None, budget)
    docboxes.apply_cap(doc, box_budget, size_of=build_maps.size_of, footprint=build_maps.footprint)
    sourceframe.record(doc, bsp_path, S, (ox, oy + FLOOR, oz), None)
    out_path = out_path or os.path.join(build_maps.ROOT, "maps", mid + ".json")
    passledger.finish(out_path=out_path)
    with open(out_path, "w") as f:
        f.write(json.dumps(doc, indent=1) + "\n")
    print("wrote", out_path)


if __name__ == "__main__":
    main(sys.argv)
