#!/usr/bin/env python3
"""Converts a Source 1 community prop-hunt .bsp (VBSP 19/20) into a mg-prop-hunt map document.

    tools/import_bsp.py <map.bsp> <id> "<Name>" <author> <page-url> [--out=maps/<id>.json] [--style=yard] [--field=players_per_hunter=4] [--drop-beside=x,z,kind] [--clear=x0,z0,x1,z1] [--prune-pockets] [--widen-doors] [--widen-thick-doors] [--prune-levels] [--pocket-margin=0.07] [--terrain]

--field=<name>=<number> sets a document number the map's own band wants (players_per_hunter, round_seconds,
hide_seconds), found by headless_bots, so a rerun of the importer keeps it.

--drop-beside=x,z,kind (repeatable, in the finished map's coordinates) drops the prop of that kind nearest that point (any kind if left out): the
headless_bots trace prints "cut off: (x, y, z) beside <prop>" for a place no route reaches, and spots
are found beside props, so this takes the place away. Reruns keep it.

--clear=x0,z0,x1,z1 (in the finished map's coordinates) drops every prop inside the rectangle: a cubby the
author walled in with counters too tall for a bot to step over, where one prop at a time is whack-a-mole.

--prune-pockets drops every floor prop that leaves a sliver of floor the bots' mesh cuts off (a small flat's
beds and bookcases a hand off a wall), by a flood fill over a grid, instead of one --drop-beside at a time.

--widen-doors widens a flat's metre-wide doorways to the game's 1.4 m, which the bots' mesh can pass.

--terrain turns the map's displacement ground (sculpted terrain, which is not a brush) into a stepped field of
ground boxes; without it a map whose yard is terrain has no floor.
--terrain-cell=<cell>[,<quant>] is --terrain with a coarser (or finer) field, in source units (default 80,5): a map whose terrain would pass the 6000-box limit wants 120 or more.

--style=yard gives the developer-grid boxes a suburban surface by their shape (a yard map the
author left unskinned); other maps keep the surface their material names say.

What it does, and why each choice:

- The world's brushes become BOXES, because a map document has no meshes. Each brush's convex
  hull is found (dotbsp's Bsp.brush_hull, via the bsp_read shim) and its bounding
  box is written; a brush that is NOT a box (a roof slope, a stair) is cut into slabs along its
  longer horizontal axis, each slab as tall as the brush is at the slab's middle, so a ramp
  becomes a staircase of 0.3 m risers rather than a block twice its height.
- Axes: Source is Z-up, godot = (x, z, -y). Scale: 1 unit = 0.01905 m (the engine's own
  0.75 inch), which makes a 108-unit door 2.06 m, fits the game's 1.4 m x 2.3 m door convention.
- Textures are NOT carried. The author's textures are replaced with the game's own materials
  (Kenney's grid under pastels, ph_materials.gd); TEXTURE_MAP says which, by name.
- prop_physics become catalogue props by PROP_MAP (the author's HL2 models have no licence we can
  ship; the catalogue is Kenney, CC0). A model with no entry is dropped and counted.
- info_player_start entries are shared out between the two teams; `light` entities become omni lights.
- Tool brushes (skybox, clip, trigger, hint, nodraw-only) are dropped.

The output goes through build_maps.Map.build(), so spawns are settled and checked there.
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bsp_read  # noqa: E402  (a shim over dot-map's shared reader; it puts dotbsp on sys.path)
from dotbsp import docboxes  # noqa: E402  (the shared passes over a document's boxes)
from dotbsp import models as bsp_models  # noqa: E402  (the models a map packs in its pakfile)
from dotbsp import standins  # noqa: E402
import build_maps  # noqa: E402

S = 0.01905
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
    # An abandoned hotel / prison block (ph_abandoned_hotel).
    "bench01a": "furniture_bench",
    "bluebarrel001": "survival_barrel",
    "chair_office01a": "furniture_chair_desk",
    "prison_shelf002a": "furniture_bookcase_open_low",
    "monitor02": "furniture_computer_screen",
    "furnitureradiator001a": "furniture_cabinet_bed",
    "kitchen_shelf002a": "furniture_bookcase_open_low",
    "wood_pallet001a": "survival_box",
    "cinderblock01a": "nature_stone_small_a",
    "prison_bedframe001a": "furniture_bed_single",
    "trashcan_indoor001a": "furniture_trashcan",
    "consolebox05a": "furniture_speaker_small",
    "metalgascan": "survival_bucket",
    "plasticbucket001a": "survival_bucket",
    "prison_toilet01": "furniture_toilet",
    "harddrive02": "furniture_laptop",
    "prison_sink001b": "furniture_bathroom_sink",
    "lockers001a": "furniture_bookcase_closed_doors",
    "pot02a": "food_pot",
    "kitchen_counter001d": "furniture_kitchen_cabinet",
    "cardboard_box002a": "furniture_cardboard_box_closed",
    "furniturearmchair001a": "furniture_lounge_chair",
    # An elementary school (ph_elementary_school).
    "vendingmachinesoda01a": "furniture_kitchen_fridge",
    "furniturecouch002a": "furniture_lounge_sofa",
    "furniture_chair01a": "furniture_chair",
    "controlroom_desk001b": "furniture_desk",
    "pushcart01a": "survival_box_large",
    "playground_teetertoter_seat": "furniture_bench",
    # A getaway (ph_autumngetaway): trees, food, pottery, chess pieces, patio.
    "trees3": "nature_tree_oak_fall",
    "trees2": "nature_tree_default_fall",
    "hotdog": "food_loaf",
    "burger": "food_loaf_round",
    "potato": "food_apple",
    "orange": "food_apple",
    "donut": "food_cake",
    "bananna_bunch": "food_banana",
    "black_pawn": "food_pineapple",
    "white_pawn": "food_pineapple",
    "black_knight": "food_pineapple",
    "white_knight": "food_pineapple",
    "white_bishop": "food_pineapple",
    "black_bishop": "food_pineapple",
    "white_king": "food_pineapple",
    "white_rook": "food_pineapple",
    "black_rook": "food_pineapple",
    "caseofbeer01": "survival_box",
    "paper01": "furniture_books",
    "paintbucket01": "survival_bucket",
    "patio_chair2": "furniture_chair_rounded",
    "pottery01a": "nature_pot_small",
    "pottery09a": "nature_pot_small",
    "pottery03a": "nature_pot_small",
    "pottery08a": "nature_pot_small",
    "pottery07a": "nature_pot_small",
    "terracotta01": "nature_pot_small",
    "claypot03": "nature_pot_small",
    "claypot03_damage_01": "nature_pot_small",
    "nuclearcontainerboxclosed": "survival_barrel",
    "bushgreenbig": "nature_plant_bush_large",
    "trash_can_p1": "furniture_trashcan",
    "furnituremattress001a": "furniture_bed_single",
    "dynamite": "food_carton",
    "consolebox03a": "furniture_speaker_small",
    "light_chandelier02": "furniture_lamp_square_ceiling",
    # A manor and its grounds (ph_wolfsmanor): reeds, a kennel, a playground's blocks, a rack of servers. Cars, bicycles,
    # containers and the climbing frames have no counterpart the size of the original and stay out.
    "cattails": "nature_plant_bush_small",
    "kennel_physics": "survival_box_large",
    "playgroundtick-tack-toe_block01a": "survival_box",
    "frame002a": "furniture_bathroom_mirror",
    "servers": "furniture_bookcase_closed_doors",
    "tree_cliff_02a": "nature_tree_default",
    "chair_stool01a": "furniture_stool_bar",
    "plant01_p1": "furniture_potted_plant",
    "planterplantsunlit": "nature_plant_bush_small",
    "winerack_small": "furniture_bookcase_open_low",
    "bench_concrete": "furniture_bench",
    "vending_turtle": "furniture_kitchen_fridge_small",
    "radiator01a": "furniture_cabinet_bed",
    "propanecanister001a": "survival_barrel",
    "potted_plant3_p1": "furniture_potted_plant",
    "potted_plant1_p1": "furniture_potted_plant",
    "potted_plant2_p1": "furniture_potted_plant",
    "furnitureshelf001b": "furniture_bookcase_open",
    "furnitureshelf002a": "furniture_bookcase_open",
    "gravestone002a": "nature_stone_large_a",
    "tv_console": "furniture_cabinet_television",
    "television_console01": "furniture_cabinet_television",
    "sinkkitchen01a": "furniture_kitchen_sink",
    "table_meeting": "furniture_table",
    "furniturewashingmachine001a": "furniture_washer",
    "dryer": "furniture_dryer",
    "file_box_p1": "survival_box",
    "microwave": "furniture_kitchen_microwave",
    "breendesk": "furniture_desk",
    "computer": "furniture_computer_screen",
    "breenchair": "furniture_chair_desk",
    "filecabinet02": "furniture_side_table_drawers",
    "armchair": "furniture_lounge_chair",
    "gun_cabinet": "furniture_bookcase_closed_doors",
    "scrapyarddumpster": "survival_box_large",
    "fern01": "furniture_plant_small1",
    "succulant": "furniture_plant_small2",
    "pi_shrub": "nature_plant_bush_small",
    "rockcliff_cluster01a": "nature_rock_large_a",
    "it_mkt_container3a": "survival_box_large",
    "fountain_plants": "nature_plant_bush",
    "furnituretable002a_chunk08": "furniture_table_coffee",
    "fireplace": "furniture_cabinet_television_doors",
    # A bank and a Halloween church (ph_bank, ph_abandoned_church workshop).
    "chair_office2": "furniture_chair_desk",
    "fan_ceiling_blade": "furniture_ceiling_fan",
    "paper_tray": "furniture_books",
    "lamp_table02": "furniture_lamp_round_table",
    "vending_machine": "furniture_kitchen_fridge_small",
    "wood_board04a": "survival_resource_wood",
    "brokenboard_damage_02": "survival_resource_wood",
    "brokenboard_damage_01": "survival_resource_wood",
    "brokenboard": "survival_resource_wood",
    # A volcano resort (ph_Volcano).
    "plantairport01": "furniture_potted_plant",
    "patio_chair": "furniture_chair_rounded",
    "cola": "food_soda_can",
    "styrofoam_cups_p1": "food_cup_coffee",
    "styrofoam_cups": "food_cup_coffee",
    "mall_bigleaves_plant03": "nature_plant_bush_large",
    "mall_small_palm01": "furniture_potted_plant",
    "newspaper1": "furniture_books",
    "trash_can_p2": "furniture_trashcan",
    "cabbage1": "nature_crop_melon",
    "cabbage2": "nature_crop_melon",
    "dish_soap": "food_bottle_oil",
    "lamp_tall": "furniture_lamp_square_floor",
    "champagne": "food_wine_red",
    "champagneplate": "food_plate",
    "trashcan01": "furniture_trashcan",
    "trash_can_p7": "furniture_trashcan",
    "water_cooler": "furniture_speaker",
    "champglass": "food_mug",
    "endtable1": "furniture_side_table",
    "digestive": "food_pizza_box",
    "miniwheats": "food_pizza_box",
    "pandapuffs": "food_pizza_box",
    "kellogscornflakes": "food_pizza_box",
    "juice": "food_carton",
    "vendingmachine01": "furniture_kitchen_fridge_small",
    "table_gewerbe": "furniture_table",
    "patio_table": "furniture_table_round",
    "trashcan": "furniture_trashcan",
    "gm_sink": "furniture_kitchen_sink",
    "pizzabox": "food_pizza_box",
    "gascan001a": "survival_bucket",
    "gm_stove": "furniture_kitchen_stove",
    "mcdburgerboxclosed": "food_pizza_box",
    "coffeepot01": "food_pot",
    "desk1": "furniture_desk",
    "file_box_p2": "survival_box",
    "file_cabinet1_group": "furniture_side_table_drawers",
    "table_kitchen": "furniture_table",
    "bookshelf3": "furniture_bookcase_closed",
    "bookshelf2": "furniture_bookcase_closed",
    "coffeemachine01": "furniture_kitchen_coffee_machine",
    # A frontier town (ph_westerncity).
    "hay_bails": "survival_box_large",
    "woodbarrel001": "survival_barrel",
    "357ammo": "furniture_books",
    "boxbuckshot": "furniture_books",
    "barstool01": "furniture_stool_bar",
    "wood_board02a": "survival_resource_wood",
    "flower04": "furniture_plant_small1",
    "garbage_glassbottle002a": "survival_bottle",
    "crate_small": "survival_box",
    "bench_indoor001a": "furniture_bench",
    "sawhorse": "survival_workbench",
    "cr_log_singlebig": "nature_log_large",
    "cr_log_singlesmall": "nature_log",
    "flower_barrel": "survival_barrel_open",
    "wood_bench": "furniture_bench",
    "crate_fruit_break_p1": "survival_box",
    "sofa_chair02": "furniture_lounge_chair",
    "cashregister01a": "furniture_computer_screen",
    "pot_big": "nature_pot_large",
    "bench_wood": "furniture_bench",
    "bush2": "nature_plant_bush",
    "clock01": "furniture_radio",
    "bookcase_small": "furniture_bookcase_open_low",
    "boxmrounds": "survival_box",
    "boxsrounds": "survival_box",
    "school_locker": "furniture_bookcase_closed_doors",
    "desk_motel": "furniture_desk",
    "gravestone003a": "nature_stone_large_a",
    "gravestone004a": "nature_stone_large_a",
    "gravestone_cross001a": "nature_stone_large_a",
    "r_plant3": "furniture_potted_plant",
    "tree_springers_01a": "nature_tree_oak",
    "piano": "furniture_cabinet_television_doors",
    "piano_bench": "furniture_bench",
    "vending_cart": "survival_box_large",
    "flower01": "furniture_plant_small2",
    "table_shed": "furniture_table",
    "tvset02": "furniture_television_vintage",
    "tablecoffee": "furniture_table_coffee",
    "desk": "furniture_desk",
    "furniturecupboard001a": "furniture_bookcase_closed",
    "tnttimed": "survival_box",
    "bunkbed2": "furniture_bed_bunk",
    "bunkbed": "furniture_bed_bunk",
    "crates_fruit2": "survival_box_large",
    "chair_office02": "furniture_chair_desk",
    "chairlobby01": "furniture_chair_cushion",
    "school_lockers_5": "furniture_bookcase_closed_doors",
    "shelves": "furniture_bookcase_open",
    "footlocker01_closed": "survival_chest",
    "cardboard_box002a_gib01": "furniture_cardboard_box_open",
    "spool": "survival_barrel_open",
    # gas station
    "cigs": "food_carton_small",
    "sosis": "food_loaf",
    "garbage_beancan01a": "food_soda_can",
    "urban_tree01_small": "nature_tree_small",
    "crate_extrasmallmill": "survival_box",
    "telephone_pole001": "survival_signpost",
    "telephone_pole002": "survival_signpost",
    "bottle02": "survival_bottle",
    "wood_crate001a_damaged": "survival_box",
    "mill_railing_128": "nature_fence_simple",
    "mill_railing_corner": "nature_fence_simple",
    "exterior_fence_notbarbed002d": "nature_fence_planks",
    "exterior_fence_notbarbed002e": "nature_fence_planks",
    "static_crate_40": "survival_box",
    "garbage_popcorn_box": "food_carton",
    "garbage_cerealbox01a_fullsheet": "food_carton",
    "garbage_cerealbox02a_fullsheet": "food_carton",
    "garbage_sixpackbox01a_fullsheet": "food_carton",
    "garbage_smallbox01a_fullsheet": "food_carton_small",
    "cardboard_box07": "furniture_cardboard_box_closed",
    "cardboard_box002b": "furniture_cardboard_box_closed",
    "washer_box2": "furniture_cardboard_box_closed",
    "soap_dispenser": "food_bottle_oil",
    "garbage_coffeecup01a_fullsheet": "food_cup_coffee",
    "styrofoam_cups_p4": "food_cup_coffee",
    "urban_tree01": "nature_tree_default",
    "urban_tree01_medium": "nature_tree_detailed",
    "trashcluster01a_corner": "furniture_trashcan",
    "stopsign01": "nature_sign",
    "gnome": "furniture_bear",
    "teddy_bear": "furniture_bear",
    "garbage_spraypaintcan01a_fullsheet": "food_soda_can",
    "garbage_cleanercan01a_fullsheet": "food_bottle_musterd",
    "clothing_pants02": "furniture_pillow",
    "clothing_tshirts": "furniture_pillow",
    "backpack": "furniture_pillow_long",
    "toaster": "furniture_toaster",
    "tea_pot-1": "food_pot",
    "pumpkin01": "nature_crop_pumpkin",
    "pottery05a": "nature_pot_small",
    "pot-1": "nature_pot_small",
    "pot-2": "nature_pot_small",
    "piepan": "food_plate",
    "microwave01": "furniture_kitchen_microwave",
    "luggage1": "survival_chest",
    "vault": "survival_chest",
    "kitchen_fridge001a": "furniture_kitchen_fridge",
    "refrigerator01": "furniture_kitchen_fridge",
    "ice_machine001": "furniture_kitchen_fridge_large",
    "garbage_pizza_box": "food_pizza_box",
    "furniture_chair03a": "furniture_chair",
    "explosive_box001": "survival_box_open",
    "computer_monitor_p1": "furniture_computer_screen",
    "computer_caseb_p8a": "furniture_speaker",
    "computer_caseb_p2a": "furniture_speaker",
    "coffee_maker": "furniture_kitchen_coffee_machine",
    "briefcase001a": "furniture_cardboard_box_open",
    "washer": "furniture_washer",
    "vcr": "furniture_radio",
    "newspaper_dispensers": "survival_box",
    "mail_dropbox": "survival_box",
    "garbage_plasticbottle001a_fullsheet": "food_soda_bottle",
    "cash_register": "furniture_computer_screen",
    "cashregister01": "furniture_computer_screen",
    "atm01": "furniture_cabinet_television",
    "bottle01": "survival_bottle",
    "sleeping_bag3": "survival_bedroll",
    "dogobject_wood_crate001a_damagedmax": "survival_box",
    "urban_tree_giant01_small": "nature_tree_tall",
    # bikini bottom
    "seaweed": "nature_grass_large",
    "krusty_bag": "food_carton_small",
    "kids_meal": "food_carton",
    "krabbypatty_static": "food_loaf_round",
    "killer_patty": "food_loaf_round",
    "nasty_patty": "food_loaf_round",
    "kk_barrel_seat": "survival_barrel",
    "ketchup": "food_bottle_ketchup",
    "biki_flower_s": "nature_flower_red_a",
    "biki_flower_m": "nature_flower_yellow_a",
    "sundae": "food_cup_coffee",
    "pan-2": "food_frying_pan",
    "guest_chair": "furniture_chair",
    "radio_p1": "furniture_radio",
    "coral01": "nature_rock_small_a",
    "biki_jellyfish": "nature_plant_bush_small",
    # swimming pool
    "stackingchair01": "furniture_chair",
    "planter_01": "nature_pot_large",
    "bogroll": "food_loaf_round",
    "urban_pot_fancy01": "nature_pot_large",
    "potted_plant_05": "furniture_potted_plant",
    "tall_plant_b": "furniture_potted_plant",
    "mall_bench2": "furniture_bench",
    "plant01a": "furniture_plant_small1",
    "pillow": "furniture_pillow",
    "urban_pot_clay02": "nature_pot_small",
    "soda": "food_soda_can",
    "servingplate": "food_plate",
    "pool_recliner": "furniture_lounge_chair_relax",
    "deckchair2": "furniture_lounge_chair_relax",
    "burger_box": "food_carton",
    "toiletpaper1": "food_loaf_round",
    "toiletpaper2": "food_loaf_round",
    "mopbucket01": "survival_bucket",
    "kursi": "furniture_chair",
    "gm_vase": "nature_pot_small",
    "cafe_barstool1": "furniture_stool_bar",
    "wolvin_laptop_phys": "furniture_laptop",
    "table_picnic": "furniture_table",
    "restaurant_table": "furniture_table_round",
    "suitcase001a": "survival_chest",
    "plastic_water_jug001": "food_carton",
    "candle": "furniture_lamp_round_table",
    "amp": "furniture_speaker",
    "toolbox": "survival_box_open",
    "sprunk1": "food_soda_can",
    "soda_nostraw": "food_soda_can",
    "milk": "food_carton_small",
    "mic": "furniture_speaker_small",
    "lemoncleaner": "food_bottle_musterd",
    "crate_extrasmall": "survival_box",
    "chair_cafeteria": "furniture_chair",
    "cake": "food_cake",
    "champagneonplate": "food_wine_red",
    "cookies": "food_plate",
    "bagette": "food_loaf",
    "bacon_2": "food_plate",
    "chicken": "food_plate",
    "bed_andrea_1st": "furniture_bed_single",
    "gm_coffeemaker": "furniture_kitchen_coffee_machine",
    "gm_stereo": "furniture_radio",
    "largedesk": "furniture_desk",
    "digestive2": "food_plate",
    "kitchen_tray001b": "food_plate",
    "cillitbang": "food_bottle_musterd",
    "mcdmeal": "food_carton",
    "mcdmeal2": "food_carton",
    "mcdburgerbox": "food_carton",
    "mcdburgerboxempty": "food_carton",
    "bbq_grill": "survival_barrel_open",
    "locker_bench": "furniture_bench",
    # restaurant
    "office_furniture_plant_pot": "furniture_potted_plant",
    "urban_pot_bigplant01": "nature_pot_large",
    "messhall_plate": "food_plate",
    "controlroom_chair001a": "furniture_chair_desk",
    "table_cafeteria": "furniture_table",
    "wood_crate_fruit_closed": "survival_box",
    "urban_small_palm01": "nature_tree_small",
    "trashcan_indoor001b": "furniture_trashcan",
    "pool_cue_rack": "furniture_bookcase_open_low",
    "gas_12kg": "survival_barrel",
    "gas_50kg": "survival_barrel",
    "ensuite_toiletries_idbs": "food_bottle_oil",
    "couch_2er": "furniture_lounge_sofa",
    "cola_bottle_01": "food_soda_bottle",
    "survival_junk_05": "survival_box_open",
    "plant_spider": "furniture_plant_small2",
    "plant_cactus": "nature_cactus_tall",
    "office_furniture_coffee_table": "furniture_table_coffee",
    "messhall_fruitbowl": "food_bowl",
    "messhall_food_04": "food_plate",
    "messhall_food_02": "food_plate",
    "messhall_food_01": "food_plate",
    "it_mkt_shelf1": "furniture_bookcase_open",
    "dresser_short": "furniture_cabinet_bed_drawer",
    "doughnuts": "food_plate",
    "crate_winea": "survival_box",
    "crate_wineb": "survival_box",
    "breakfast": "food_plate",
    "box_a": "survival_box",
    "box_b": "survival_box",
    "barrel_a": "survival_barrel",
    "barrel_b": "survival_barrel_open",
    "sink_industrial01": "furniture_kitchen_sink",
    "refrigerator03": "furniture_kitchen_fridge",
    "paper_cup": "food_cup_coffee",
    "office_chair": "furniture_chair_desk",
    "keyboard": "furniture_computer_keyboard",
    "hospital_bucket": "survival_bucket",
    "din_planter": "nature_pot_large",
    "coffee_chair": "furniture_chair",
    "messhall_tray": "food_plate",
    "messhall_pecanpie": "food_cake",
    "acunit2": "furniture_dryer",
    # oceanwaves
    "ceiling_fan": "furniture_ceiling_fan",
    "planningrm_laptop": "furniture_laptop",
    "v_res_fh_kitnstool_high": "furniture_stool_bar",
    "planningrm_monitor": "furniture_computer_screen",
    "v_res_m_dinechair_high": "furniture_chair",
    "v_res_fa_radioalrm": "furniture_radio",
    "mall_pot_large01": "nature_pot_large",
    "pineapple": "food_pineapple",
    "boombox_01": "furniture_speaker",
    "beach_chair": "furniture_lounge_chair_relax",
    "planningrm_mousemat": "furniture_computer_mouse",
    "prop_toaster_01_high": "furniture_toaster",
    "prop_laptop_02": "furniture_laptop",
    "planningrm_speaker": "furniture_speaker_small",
    "planningrm_keyboard_black": "furniture_computer_keyboard",
    "apa_mp_h_acc_fruitbowl_01": "food_bowl",
    "apa_mp_h_acc_fruitbowl_02": "food_bowl",
    "apa_mp_h_acc_candles_01_high": "furniture_lamp_round_table",
    "apa_mpa6_din_chair_00_high": "furniture_chair",
    "v_res_mp_sofa_high_box_table": "furniture_lounge_sofa",
    "suite_bath": "furniture_bathtub",
    "prop_coffee_mac_02": "furniture_kitchen_coffee_machine",
    "plant_int_04b": "furniture_potted_plant",
    "oildrum001_explosive": "survival_barrel",
    "knife": "food_knife_block",
    "kitchentable": "furniture_table",
    "dining_table_round": "furniture_table_round",
    "condo_toilet": "furniture_toilet",
    "condo_fridge": "furniture_kitchen_fridge",
    "comfybed": "furniture_bed_double",
    "coffeetable": "furniture_table_coffee",
    "fancy_blender": "furniture_kitchen_blender",
    "cut_board": "food_cutting_board",
    "apa_mp_h_01_dining_plant2_high": "furniture_potted_plant",
    "toolchest_05": "survival_box_open",
    "toolchest_03": "survival_box_open",
    "beachball": "food_pineapple",
    "planningrm_printer": "furniture_speaker_small",
    "beach_ring": "survival_bucket",
    # midwest apartment
    "garbage_sodacan01a": "food_soda_can",
    "garbage_tunacan01a": "food_soda_can",
    "trashbin01": "furniture_trashcan",
    "garbage_cerealbox02a": "food_carton",
    "trashcankitchen01": "furniture_trashcan",
    "pan-1": "food_frying_pan",
    "garbage_sodacan01a_crushed": "food_soda_can",
    "garbage_cellphone01a": "furniture_computer_mouse",
    "chair2": "furniture_chair",
    "tv": "furniture_television_vintage",
    "table_motel": "furniture_table",
    "garbage_takeoutbox01a": "food_carton",
    "garbage_pizzabox01a": "food_pizza_box",
    "garbage_cleanercan01a": "food_bottle_musterd",
    "chair01": "furniture_chair",
    "trashdumpster02": "survival_box_large",
    "sofa01": "furniture_lounge_sofa",
    "garbage_sodacup01a": "food_cup_coffee",
    "garbage_smallbox01a": "food_carton_small",
    "garbage_sixpackbox01a": "food_carton",
    "garbage_milkcarton002a_fullsheet": "food_carton_small",
    "garbage_coffeemug001a_fullsheet": "food_mug",
    "garbage_cerealbox01a": "food_carton",
    "dvd_player": "furniture_radio",
    "books02": "furniture_books",
    "garbage_remotecontrol01a": "furniture_computer_mouse",
    # cyber diner
    "spph_trash_p1": "survival_bottle",
    "spph_trash_p2": "food_carton_small",
    "spph_trash_p3": "furniture_cardboard_box_closed",
    "spph_trash_p4": "food_cup_coffee",
    "spph_trash_p5": "food_carton",
    "spph_trash_p6": "survival_bucket",
    "spph_trash_p7": "furniture_books",
    "spph_trash_p8": "food_soda_can",
    "spph_trash_p9": "survival_bottle",
    "spph_trash_p10": "food_carton_small",
    "spph_trash_p11": "furniture_cardboard_box_closed",
    "spph_trash_p12": "food_cup_coffee",
    "spph_trash_p14": "survival_bucket",
    "spph_trash_p15": "furniture_books",
    "spph_trash_p16": "food_soda_can",
    "phcy_trash_box": "furniture_cardboard_box_open",
    "trash_2_0": "food_carton",
    "trash_cantain": "furniture_trashcan",
    "vedro_trash": "survival_bucket",
    "cofe_cup": "food_cup_coffee",
    "cyph_prop_pizza_1": "food_pizza_box",
    "cyph_prop_pizza_2": "food_pizza_box",
    "cyph_prop_pizza_3": "food_pizza_box",
    "cyph_prop_eat_4": "food_plate",
    "cyph_prop_eat_5": "food_bowl",
    "cyph_prop_eat_6": "food_plate",
    "cyph_prop_eat_7": "food_bowl",
    "cyph_prop_eat_8": "food_plate",
    "cyph_prop_eat_9": "food_mug",
    "cyph_prop_bottle_4": "food_soda_bottle",
    "cyph_prop_bottle_7": "food_bottle_oil",
    "beer_1": "food_soda_bottle",
    "beer_2": "food_soda_bottle",
    "radio_nc": "furniture_radio",
    "tv_circle_c": "furniture_television_modern",
    "cyph_prop_pechka": "furniture_kitchen_stove",
    "cyph_prop_chines_lamp": "furniture_lamp_round_floor",
    "cyph_prop_sakura": "nature_tree_small",
    # ph_wolfsmanor (gamebanana 61511)
    "furniturebathtub001a": "furniture_bathtub",
    "kitchen_stove001a": "furniture_kitchen_stove",
    "furniturefridge001a": "furniture_kitchen_fridge",
    "furniturebed001a": "furniture_bed_single",
    "furniture_desk01a": "furniture_desk",
    "furniture_cabinetdrawer02a": "furniture_cabinet_bed_drawer",
    "kitchen_counter001c": "furniture_kitchen_cabinet",
    "laundry_cart001": "survival_box_open",
    "workspace001": "furniture_desk",
    "workspace002": "furniture_desk",
    "workspace003": "furniture_desk",
    "oak_tree01": "nature_tree_oak",
    "tree_deciduous_02a": "nature_tree_default_fall",
    "tree_deciduous_03a": "nature_tree_default_fall",
    "tree_deciduous_03b": "nature_tree_oak_fall",
    "tree_poplar_01": "nature_tree_tall",
    "wood_fence01a": "nature_fence_planks",
    "driftwood_01a": "nature_log",
    "driftwood_03a": "nature_log",
}


# Every entity class an author uses for a loose prop; the _dynamic ones are placed furniture
# that does not move in the original, which a catalogue prop is not either (it is a disguise).
MAX_PACKED_SIDE = 3.0   # a packed model longer than this is scenery (a sign, a car, a vent run), not a hiding prop
GUESS_LIMIT = 1.5       # bsp_models.shape_distance a name guess may be from the measured size and stand
SHAPE_LIMIT = 0.7       # and a catalogue prop picked by shape alone (a stricter bar: nothing else says what it is)
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


def planes_of(bsp, index):
    first, count, _ = bsp.brushes[index]
    return [bsp.planes[s[0]][:4] for s in bsp.brushsides[first:first + count] if not s[3]]


def z_range(planes, x, y):
    lo, hi = -1e9, 1e9
    for nx, ny, nz, d in planes:
        if abs(nz) < 1e-6:
            continue
        z = (d - nx * x - ny * y) / nz
        if nz > 0:
            hi = min(hi, z)
        else:
            lo = max(lo, z)
    return lo, hi


def box_in_frame(pts, phi, tol):
    """The hull's extents in a frame turned phi degrees about z, or None when some corner is not
    a corner of that bounding box. (x0, x1), (y0, y1), (z0, z1), in the turned frame."""
    c, sn = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    q = [(p[0] * c + p[1] * sn, -p[0] * sn + p[1] * c, p[2]) for p in pts]
    x0, x1 = min(p[0] for p in q), max(p[0] for p in q)
    y0, y1 = min(p[1] for p in q), max(p[1] for p in q)
    z0, z1 = min(p[2] for p in q), max(p[2] for p in q)
    for p in q:
        if not ((abs(p[0] - x0) < tol or abs(p[0] - x1) < tol) and (abs(p[1] - y0) < tol or abs(p[1] - y1) < tol)
                and (abs(p[2] - z0) < tol or abs(p[2] - z1) < tol)):
            return None
    return (x0, x1), (y0, y1), (z0, z1)


def turned_box(bsp, index, pts):
    """(box, phi) when the brush is a box turned about the vertical axis, else None. The author's
    building is not always on the grid (a room at thirty degrees to the rest), and cutting such a
    wall into axis-aligned slabs gives a saw-tooth the players catch on. The angle is each upright
    side's direction modulo 90, tried in turn; the document's boxes carry a yaw."""
    first, count, _ = bsp.brushes[index]
    tried = set()
    for sd in bsp.brushsides[first:first + count]:
        if sd[3]:
            continue
        nx, ny, nz, _d = bsp.planes[sd[0]][:4]
        if abs(nz) > 1e-4:
            continue
        phi = round(math.degrees(math.atan2(ny, nx)) % 90.0, 2)
        if phi in tried or phi < 0.05 or phi > 89.95:
            continue
        tried.add(phi)
        # Four-decimal planes at 1000 units leave a unit of slack in the corners.
        box = box_in_frame(pts, phi, 1.5)
        if box is not None:
            return box, phi
    return None


def prism_box(pts):
    """(box, phi) for a brush that is a vertical prism of any plan shape: the smallest turned
    rectangle round its plan. A curved wall is a run of such wedges and a column of a round room
    is one; the box overhangs the wedge by a sliver, where cutting it into axis-aligned slabs (a
    slope's treatment, wrong for a plan shape) bit chunks out of the room. None for a brush whose
    top or bottom is not flat and level."""
    zs = sorted({round(p[2], 1) for p in pts})
    if len(zs) != 2:
        return None
    low = {(round(p[0], 1), round(p[1], 1)) for p in pts if abs(p[2] - zs[0]) < 0.15}
    high = {(round(p[0], 1), round(p[1], 1)) for p in pts if abs(p[2] - zs[1]) < 0.15}
    if low != high or len(low) < 3:
        return None
    plan = [(x, y, zs[0]) for x, y in low]
    best = None
    for (ax, ay), (bx_, by) in ((p, q) for p in low for q in low if p != q):
        phi = math.degrees(math.atan2(by - ay, bx_ - ax)) % 90.0
        box = box_in_frame(plan, phi, 1e9)
        area = (box[0][1] - box[0][0]) * (box[1][1] - box[1][0])
        if best is None or area < best[0] - 1e-6:
            best = (area, phi, box)
    _a, phi, box = best
    return (box[0], box[1], (zs[0], zs[1])), phi


def brush_boxes(bsp, index):
    """[((x range), (y range), (z range), phi)] in Source units, the ranges in a frame turned phi
    degrees (0 for most), and whether the brush had to be cut into slabs."""
    pts = bsp.brush_hull(index)
    if len(pts) < 4:
        return [], 0
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    z0, z1 = min(p[2] for p in pts), max(p[2] for p in pts)
    box_vol = (x1 - x0) * (y1 - y0) * (z1 - z0)
    # Hull volume from the corner points: a brush is a box when every corner is a box corner.
    corners = sum(1 for p in pts if (abs(p[0] - x0) < 0.5 or abs(p[0] - x1) < 0.5) and (abs(p[1] - y0) < 0.5 or abs(p[1] - y1) < 0.5) and (abs(p[2] - z0) < 0.5 or abs(p[2] - z1) < 0.5))
    if corners == len(pts):
        return [((x0, x1), (y0, y1), (z0, z1), 0.0)], 0
    tb = turned_box(bsp, index, pts)
    if tb is not None:
        return [tb[0] + (tb[1],)], 0
    pb = prism_box(pts)
    if pb is not None:
        return [pb[0] + (pb[1],)], 0
    pl = planes_of(bsp, index)
    out = []
    if x1 - x0 >= y1 - y0:
        n = max(1, math.ceil((x1 - x0) / SLAB))
        for i in range(n):
            a, b = x0 + (x1 - x0) * i / n, x0 + (x1 - x0) * (i + 1) / n
            lo, hi = z_range(pl, (a + b) / 2, (y0 + y1) / 2)
            lo, hi = max(lo, z0), min(hi, z1)
            if hi - lo > 0.5:
                out.append(((a, b), (y0, y1), (lo, hi), 0.0))
    else:
        n = max(1, math.ceil((y1 - y0) / SLAB))
        for i in range(n):
            a, b = y0 + (y1 - y0) * i / n, y0 + (y1 - y0) * (i + 1) / n
            lo, hi = z_range(pl, (x0 + x1) / 2, (a + b) / 2)
            lo, hi = max(lo, z0), min(hi, z1)
            if hi - lo > 0.5:
                out.append(((x0, x1), (a, b), (lo, hi), 0.0))
    return out, 1


def widen_doors(boxes, want=1.4, thick=0.4, narrowest=0.8):
    """Widens the doorways a flat's author made about a metre wide (--widen-doors).

    A door is a gap between two collinear wall slabs, a header box over it and a thin trim post
    either side (ph_apartment's are 0.91 m clear). The bots' mesh is eroded by the body radius
    on each side, a doorway that narrow bakes as a sliver or not at all, and every room behind
    one becomes an island. The game's own door convention is 1.4 m. Each slab end moves back,
    the header is stretched over the new gap, and the trim posts and lintels are dropped (they are
    what made the opening narrower than the wall's gap).

    thick / narrowest (--widen-thick-doors) reach a yard house's doorway cut through a wall up to
    1.3 m thick and as narrow as 0.6 m, which the thin-wall rule leaves a 0.75 m slot the bots
    cannot pass: the room behind it was a whole island."""
    walls = []
    for b in boxes:
        w, h, d = b["size"]
        if not b.get("solid", True) or b.get("yaw") or h < 2.3 or b["at"][1] - h / 2 > 0.5:
            continue
        if min(w, d) <= thick < max(w, d):
            walls.append(b)
    done = 0
    for a in walls:
        axis = 2 if a["size"][2] > a["size"][0] else 0        # the run's axis; the other is across it
        cross = 0 if axis == 2 else 2
        for c in walls:
            if c is a or c["size"][axis] <= c["size"][cross] or abs(c["at"][cross] - a["at"][cross]) > 0.02:
                continue
            if abs(c["size"][1] - a["size"][1]) > 0.01 or abs(c["at"][1] - a["at"][1]) > 0.01:
                continue
            a_end = a["at"][axis] + a["size"][axis] / 2
            c_start = c["at"][axis] - c["size"][axis] / 2
            gap = c_start - a_end
            if not narrowest <= gap <= 1.2:
                continue
            grow = (want - gap) / 2
            mid = (a_end + c_start) / 2
            for piece in (a, c):
                piece["size"][axis] = round(piece["size"][axis] - grow, 3)
            a["at"][axis] = round(a["at"][axis] - grow / 2, 3)
            c["at"][axis] = round(c["at"][axis] + grow / 2, 3)
            for b in list(boxes):
                if b is a or b is c or abs(b["at"][cross] - a["at"][cross]) > 0.3 or abs(b["at"][axis] - mid) > want / 2 + 0.2:
                    continue
                w, h, d = b["size"]
                if b["at"][1] - h / 2 > 1.8 and abs(b["size"][axis] - gap) < 0.1 and b["size"][cross] <= thick:
                    b["size"][axis] = round(want, 3)               # the header over the door
                    b["at"][axis] = round(mid, 3)
                elif b["mat"] in ("concrete", "wood", "parquet") and (min(w, d) < 0.1) and b["at"][1] - h / 2 < 2.2:
                    boxes.remove(b)                                 # a trim post or lintel
            done += 1
    return done


def drop_trim_posts(boxes):
    """Drops the door-frame trim posts: tall boxes under 16 cm either way (--widen-thick-doors).

    A frame's trim is a post a few centimetres square either side of the opening. It stands in
    the doorway's clear width, and the bots' mesh (eroded by the body radius) turns a 1.4 m
    opening with two posts in it into a slot it cannot pass; the room behind is an island. The
    wall and the lintel stay, so the opening still reads as a doorway."""
    gone = [b for b in boxes if b.get("solid", True) and not b.get("yaw") and b["size"][0] <= 0.16
            and b["size"][2] <= 0.16 and 1.8 <= b["size"][1] <= 2.4]
    for b in gone:
        boxes.remove(b)
    return len(gone)


def widen_sliced_doors(boxes, want=1.4, thick=1.3):
    """Widens a doorway cut through a thick wall that the importer sliced into stacked boxes (--widen-thick-doors).

    A wall a metre thick with a 0.9 m door arrives as a low slab either side of the door (floor to
    lintel), more slabs above it, and a few header pieces over the gap, none of them a full-height
    slab, so widen_doors does not see it. The bots' mesh is eroded by the body radius, and 0.9 m
    bakes as a sliver: the room behind is an island. Every slab in that wall line that ends at the
    gap moves back, and the header pieces are replaced by one box over the wider gap."""
    done = 0
    solids = [b for b in boxes if b.get("solid", True) and not b.get("yaw")]
    lows = [b for b in solids if ((b["at"][1] - b["size"][1] / 2 <= 0.1 and b["at"][1] + b["size"][1] / 2 >= 1.3)
                                  or b["size"][1] >= 2.3)
            and min(b["size"][0], b["size"][2]) <= thick]
    for a in lows:
        axis = 2 if a["size"][2] > a["size"][0] else 0
        cross = 2 - axis
        for c in lows:
            if c is a or c["size"][axis] <= c["size"][cross] or abs(c["at"][cross] - a["at"][cross]) > 0.02:
                continue
            if abs(c["size"][1] - a["size"][1]) > 0.01 or abs(c["at"][1] - a["at"][1]) > 0.01:
                continue
            a_end = a["at"][axis] + a["size"][axis] / 2
            c_start = c["at"][axis] - c["size"][axis] / 2
            gap = c_start - a_end
            if not 0.6 <= gap <= 1.2:
                continue
            line = [b for b in solids if b in boxes and abs(b["at"][cross] - a["at"][cross]) < 0.02
                    and abs(b["size"][cross] - a["size"][cross]) < 0.02]
            inside = [b for b in line if b["at"][axis] - b["size"][axis] / 2 >= a_end - 0.02
                      and b["at"][axis] + b["size"][axis] / 2 <= c_start + 0.02]
            floor_y = a["at"][1] - a["size"][1] / 2
            sill = [b for b in inside if b["at"][1] + b["size"][1] / 2 <= floor_y + 0.5]
            for b in sill:                                          # the floor through the doorway: as wide as the new gap
                b["size"][axis] = round(want, 3)
                b["at"][axis] = round((a_end + c_start) / 2, 3)
            inside = [b for b in inside if b not in sill]
            if any(b["at"][1] - b["size"][1] / 2 < floor_y + 1.8 for b in inside):
                continue                                           # something solid in the doorway: not a door
            grow = (want - gap) / 2
            # A trim post either side of the opening (a few centimetres of frame) is what made it
            # narrower than the gap: the bots' mesh is eroded round it.
            for b in [b for b in solids if b in boxes and min(b["size"][0], b["size"][2]) < 0.2
                      and b["size"][1] > 1.5 and b["at"][1] - b["size"][1] / 2 < floor_y + 0.5
                      and a_end - 0.12 <= b["at"][axis] <= c_start + 0.12
                      and abs(b["at"][cross] - a["at"][cross]) <= a["size"][cross] / 2 + 0.15]:
                boxes.remove(b)
            for b in line:
                if b in inside:
                    continue
                lo, hi = b["at"][axis] - b["size"][axis] / 2, b["at"][axis] + b["size"][axis] / 2
                if abs(hi - a_end) < 0.02:
                    b["size"][axis] = round(b["size"][axis] - grow, 3)
                    b["at"][axis] = round(b["at"][axis] - grow / 2, 3)
                elif abs(lo - c_start) < 0.02:
                    b["size"][axis] = round(b["size"][axis] - grow, 3)
                    b["at"][axis] = round(b["at"][axis] + grow / 2, 3)
            if inside:
                y0 = min(b["at"][1] - b["size"][1] / 2 for b in inside)
                y1 = max(b["at"][1] + b["size"][1] / 2 for b in inside)
                head = dict(inside[0])
                head["at"] = list(inside[0]["at"])
                head["size"] = list(inside[0]["size"])
                head["at"][axis] = round((a_end + c_start) / 2, 3)
                head["size"][axis] = round(want, 3)
                head["at"][1] = round((y0 + y1) / 2, 3)
                head["size"][1] = round(y1 - y0, 3)
                for b in inside:
                    boxes.remove(b)
                boxes.append(head)
                solids.append(head)
            done += 1
    return done


def prune_pockets(doc, rounds=4, levels=False, margin=0.0, floor_lo=-0.05):
    """Drops floor props that leave a pocket the bots cannot walk out of (--prune-pockets).

    mg-prop-hunt's headless_bots holds every hiding place reachable from the props' first start,
    and a place is "beside" a piece of floor furniture (0.45 m off its side). A bed, a bookcase
    or a table left a hand's width off a wall makes a sliver of floor that the bots' walkable mesh
    (eroded by the body radius, 0.35 m) cuts off from the rest, and a small flat has dozens. This
    does what the headless_bots trace asks for, in one pass over every prop instead of one
    whack-a-mole drop at a time: it finds the walkable cells on a 0.1 m grid (floor within a step's
    height, nothing solid between knee and head, nothing furniture), floods them from the start,
    and drops a prop whose every free side lands in a cell the flood did not reach.

    floor_lo is how low a walkable top may be: a map whose ground is terrain sits below zero (--terrain passes -1), and with the
    default every cell of it was "not floor", the flood found no start and the pass did nothing.

    margin (--pocket-margin=0.07) widens the body radius the grid erodes by: the bots' mesh also
    erodes a cell's worth for its cell size, so a 0.75 m gap the grid calls walkable bakes as a
    sliver island with places on it.

    levels (--prune-levels) also drops a prop standing more than half a metre below, or two metres above, the floor the
    grid models: a cellar or lower floor reached only by a ladder or a lift, which a map document
    cannot express (it has no ladder and no link), so the bots' mesh leaves it an island and
    every place on it "cut off". The grid has no floor cells down there, so the flood cannot tell."""
    R, RAD, BESIDE = 0.1, 0.35, 0.45
    # With levels on, a slab up to the mesh's 0.4 m climb is floor (a 0.3 m sidewalk is not a wall).
    STEP = 0.4 if levels else 0.3
    boxes = [b for b in doc["boxes"] if b.get("solid", True)]
    xs0 = min(b["at"][0] - b["size"][0] / 2 for b in boxes)
    xs1 = max(b["at"][0] + b["size"][0] / 2 for b in boxes)
    zs0 = min(b["at"][2] - b["size"][2] / 2 for b in boxes)
    zs1 = max(b["at"][2] + b["size"][2] / 2 for b in boxes)
    W, H = int((xs1 - xs0) / R) + 1, int((zs1 - zs0) / R) + 1
    total = 0
    for _ in range(rounds):
        floor = bytearray(W * H)
        block = bytearray(W * H)

        def cells(b, test):
            hx, hz = b["size"][0] / 2, b["size"][2] / 2
            reach = math.hypot(hx, hz) if b.get("yaw") else None
            ax, az = (reach, reach) if reach else (hx, hz)
            for zi in range(max(0, int((b["at"][2] - az - zs0) / R)), min(H, int((b["at"][2] + az - zs0) / R) + 2)):
                for xi in range(max(0, int((b["at"][0] - ax - xs0) / R)), min(W, int((b["at"][0] + ax - xs0) / R) + 2)):
                    if docboxes.within(b, xs0 + (xi + 0.5) * R, zs0 + (zi + 0.5) * R):
                        test(zi * W + xi)

        for b in boxes:
            lo, hi = b["at"][1] - b["size"][1] / 2, b["at"][1] + b["size"][1] / 2
            if floor_lo <= hi <= STEP:
                cells(b, lambda i: floor.__setitem__(i, 1))
            if hi > STEP and lo < 1.4:
                cells(b, lambda i: block.__setitem__(i, 1))
        for q in doc["props"]:
            if q["at"][1] > STEP:
                continue
            sx, sy, sz = build_maps.size_of(q["id"])
            if sy < 0.3:
                continue
            fw, fd = build_maps.footprint(q["id"], q.get("yaw", 0.0))
            cells({"at": q["at"], "size": [fw, sy, fd]}, lambda i: block.__setitem__(i, 1))
        bad = bytearray(W * H)
        k = int(math.ceil(RAD / R))
        for i in range(W * H):
            if block[i] or not floor[i]:
                zi, xi = divmod(i, W)
                for dz in range(-k, k + 1):
                    for dx in range(-k, k + 1):
                        if dx * dx + dz * dz <= k * k and 0 <= zi + dz < H and 0 <= xi + dx < W:
                            bad[(zi + dz) * W + xi + dx] = 1
        sp = doc["spawns"]["props"][0]["at"]
        start = (int((sp[2] - zs0) / R), int((sp[0] - xs0) / R))
        near = next(((zi, xi) for rr in range(0, 40) for zi in range(start[0] - rr, start[0] + rr + 1)
                     for xi in range(start[1] - rr, start[1] + rr + 1)
                     if 0 <= zi < H and 0 <= xi < W and not bad[zi * W + xi]), None)
        if near is None:
            return total
        seen = bytearray(W * H)
        seen[near[0] * W + near[1]] = 1
        stack = [near]
        while stack:
            zi, xi = stack.pop()
            for dz, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nz, nx = zi + dz, xi + dx
                if 0 <= nz < H and 0 <= nx < W and not seen[nz * W + nx] and not bad[nz * W + nx]:
                    seen[nz * W + nx] = 1
                    stack.append((nz, nx))

        def nearest_free(x, z):
            """The closest walkable cell within 0.35 m of (x, z): (reached?, found?)."""
            ci, cj = int((z - zs0) / R), int((x - xs0) / R)
            best = None
            for zi in range(ci - 4, ci + 5):
                for xi in range(cj - 4, cj + 5):
                    if 0 <= zi < H and 0 <= xi < W and not bad[zi * W + xi]:
                        d2 = (zi - ci) ** 2 + (xi - cj) ** 2
                        if d2 <= 12 and (best is None or d2 < best[0]):
                            best = (d2, bool(seen[zi * W + xi]))
            return best

        gone = []
        for q in doc["props"]:
            if q["at"][1] > STEP:
                if levels and q["at"][1] > 2.0:
                    gone.append(q)                    # an upper floor: no table is that high
                continue
            sx, sy, sz = build_maps.size_of(q["id"])
            fw, fd = build_maps.footprint(q["id"], q.get("yaw", 0.0))
            ys = math.radians(q.get("yaw", 0.0))
            states = []
            for lx, lz in ((fw / 2 + BESIDE, 0), (-fw / 2 - BESIDE, 0), (0, fd / 2 + BESIDE), (0, -fd / 2 - BESIDE)):
                n = nearest_free(q["at"][0] + lx, q["at"][2] + lz)
                if n is not None:
                    states.append(n[1])
            if (states and not any(states)) or (levels and q["at"][1] < -0.5):
                gone.append(q)
        if not gone:
            if not levels:
                break
            # A spawn the flood never reached is in a sealed room (a shed with no door): a bot
            # that starts there hides inside it for the round and the hunters can never meet it.
            # It moves to the nearest cell the flood did reach (the game wants its 8 and 3 spawns).
            for team in ("props", "hunters"):
                for i, sp in enumerate(doc["spawns"][team]):
                    if (i == 0 and team == "props") or (nearest_free(sp["at"][0], sp["at"][2]) or (0, True))[1]:
                        continue
                    ci, cj = int((sp["at"][2] - zs0) / R), int((sp["at"][0] - xs0) / R)
                    best = min(((zi - ci) ** 2 + (xi - cj) ** 2, zi, xi)
                               for zi in range(max(0, ci - 60), min(H, ci + 61))
                               for xi in range(max(0, cj - 60), min(W, cj + 61)) if seen[zi * W + xi])
                    sp["at"][0], sp["at"][2] = round(xs0 + (best[2] + 0.5) * R, 3), round(zs0 + (best[1] + 0.5) * R, 3)
                    sp["at"][1] = 0.05
                    total += 1
            break
        for q in gone:
            doc["props"].remove(q)
        total += len(gone)
    return total


def start_entities(bsp):
    return [e for e in bsp.entities if e.get("classname") in START_CLASSES]


def starts_unfloored(bsp, boxes):
    """How many of the author's starts have no solid box top within reach of their feet."""
    n = 0
    for e in start_entities(bsp):
        gx, gy, gz = gd(vec(e["origin"]))
        if not any(b.get("solid", True) and gy - 0.3 <= b["at"][1] + b["size"][1] / 2 <= gy + 0.6 and docboxes.within(b, gx, gz, 0.001)
                   for b in boxes):
            n += 1
    return n


def terrain_boxes(bsp, cell=80.0, quant=5.0, depth=52.0):
    """The map's displacement ground as a stepped field of boxes (--terrain).

    A displacement is a heightmap the mapper sculpted over a quad, not a brush, so the box
    pass above finds no ground at all in a map whose yard is terrain (the church's spawns
    stood on nothing). The surfaces are sampled at the middle of cells of `cell` source units
    (about 1.5 m, nine sub-samples averaged so a cell half under a wall still has a height),
    the height rounded to `quant` units (about 0.1 m) and equal neighbours merged: a long
    flat yard is a few boxes, not a thousand, and the document's box limit is shared with the
    walls. Yields ((x0, x1), (y0, y1), (z0, z1), material) in source units.
    """
    tris = []
    for f in bsp.model_faces(0):
        if f[6] >= 0:
            tris += bsp.displacement_tris(f)
    if not tris:
        return []
    x0 = min(p[0] for t in tris for p in t)
    y0 = min(p[1] for t in tris for p in t)
    nx = int((max(p[0] for t in tris for p in t) - x0) // cell) + 1
    ny = int((max(p[1] for t in tris for p in t) - y0) // cell) + 1
    acc = {}
    sub = (0.17, 0.5, 0.83)
    for a, b, c in tris:
        mnx, mxx = min(q[0] for q in (a, b, c)), max(q[0] for q in (a, b, c))
        mny, mxy = min(q[1] for q in (a, b, c)), max(q[1] for q in (a, b, c))
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-9:
            continue
        for i in range(int((mnx - x0) // cell), int((mxx - x0) // cell) + 1):
            for j in range(int((mny - y0) // cell), int((mxy - y0) // cell) + 1):
                for fx in sub:
                    for fy in sub:
                        px, py = x0 + (i + fx) * cell, y0 + (j + fy) * cell
                        l1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / d
                        l2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / d
                        l3 = 1 - l1 - l2
                        if min(l1, l2, l3) >= -1e-6:
                            acc.setdefault((i, j), []).append(l1 * a[2] + l2 * b[2] + l3 * c[2])
    h = {k: round(sum(v) / len(v) / quant) * quant for k, v in acc.items()}
    # Runs along x of one height, then runs of identical runs along y.
    runs = {}
    for j in range(ny):
        i = 0
        while i < nx:
            if (i, j) not in h:
                i += 1
                continue
            e = i
            while (e + 1, j) in h and h[(e + 1, j)] == h[(i, j)]:
                e += 1
            runs[(i, e, h[(i, j)], j)] = j
            i = e + 1
    out = []
    done = set()
    for (i, e, ht, j) in sorted(runs, key=lambda k: (k[3], k[0])):
        if (i, e, ht, j) in done:
            continue
        j2 = j
        while (i, e, ht, j2 + 1) in runs:
            j2 += 1
            done.add((i, e, ht, j2))
        out.append(((x0 + i * cell, x0 + (e + 1) * cell), (ht - depth, ht), (y0 + j * cell, y0 + (j2 + 1) * cell), "grass"))
    return out


def drop_buried(boxes, field, cell=80.0):
    """The boxes whose top lies at or under the terrain field over their whole footprint are dropped (--terrain).

    Sliced wedge brushes below a sea bed were thousands of thin slabs that crowded the box limit and forced a
    coarse field. `field` is terrain_boxes' output in source units, made at `cell`."""
    if not field:
        return boxes
    c = cell * S
    top = {}
    fx = min(b[0][0] for b in field) * S
    fz = min(-b[2][1] for b in field) * S
    for (x0, x1), (_lo, hi), (y0, y1), _m in field:
        for i in range(int(round((x1 - x0) / cell))):
            for j in range(int(round((y1 - y0) / cell))):
                top[(int(round((x0 * S - fx) / c)) + i, int(round((-y1 * S - fz) / c)) + j)] = hi * S
    keep = []
    for b in boxes:
        x, y, z = b["at"]
        w, h, d = b["size"]
        t = y + h / 2
        buried = True
        for i in range(int(math.floor((x - w / 2 - fx) / c)), int(math.floor((x + w / 2 - 1e-6 - fx) / c)) + 1):
            for j in range(int(math.floor((z - d / 2 - fz) / c)), int(math.floor((z + d / 2 - 1e-6 - fz) / c)) + 1):
                if top.get((i, j), -1e9) < t:
                    buried = False
                    break
            if not buried:
                break
        if not buried:
            keep.append(b)
    print("terrain: %d boxes under the ground dropped" % (len(boxes) - len(keep)))
    return keep


def audit_props(doc):
    """Drops what mg-prop-hunt's headless_maps would refuse, in the document's own coordinates: a prop
    whose middle is inside a solid box (an author's prop in a pit or a wall) and one with nothing
    under its base (a ray down from 4 cm above it finds no box top or prop top within 12 cm, from
    the nine points that audit samples). Repeats, because a dropped table leaves what stood on it
    floating. Returns the number dropped."""
    solid = [b for b in doc["boxes"] if b.get("solid", True)]
    gone = 0
    for _ in range(8):
        changed = False
        for q in sorted(doc["props"], key=lambda t: t["at"][1]):
            pid, yaw = q["id"], q.get("yaw", 0.0)
            w, h, d = build_maps.footprint(pid, yaw)[0], build_maps.size_of(pid)[1], build_maps.footprint(pid, yaw)[1]
            cx, cy, cz = q["at"][0], q["at"][1] + h / 2, q["at"][2]
            sunk = any(docboxes.within(b, cx, cz, 0.0) and b["at"][1] - b["size"][1] / 2 + 0.02 < cy < b["at"][1] + b["size"][1] / 2 - 0.02 for b in solid)
            floating = False
            if not sunk and "ceiling" not in pid and "lily" not in pid:
                base = q["at"][1]
                floating = True
                for fx in (-0.3, 0.0, 0.3):
                    for fz in (-0.3, 0.0, 0.3):
                        px, pz = cx + fx * w, cz + fz * d
                        for b in solid:
                            t = b["at"][1] + b["size"][1] / 2
                            if base - 0.12 <= t <= base + 0.04 and docboxes.within(b, px, pz, 0.0):
                                floating = False
                        for o in doc["props"]:
                            if o is q:
                                continue
                            ow, od = build_maps.footprint(o["id"], o.get("yaw", 0.0))
                            if abs(px - o["at"][0]) <= ow / 2 and abs(pz - o["at"][2]) <= od / 2:
                                t = o["at"][1] + build_maps.rest_on(o, px - o["at"][0], pz - o["at"][2], pid, yaw)
                                if base - 0.12 <= t <= base + 0.04:
                                    floating = False
                        if not floating:
                            break
                    if not floating:
                        break
            if sunk or floating:
                doc["props"].remove(q)
                gone += 1
                changed = True
        if not changed:
            break
    return gone


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    out_path = None
    style = ""
    fields = {}
    drops = []
    clears = []
    pockets = False
    levels = False
    margin = 0.0
    widen = False
    thick_doors = False
    terrain = False
    terrain_args = {}
    for a in argv[1:]:
        if a.startswith("--out="):
            out_path = a[6:]
        elif a == "--widen-doors":
            widen = True
        elif a == "--widen-thick-doors":
            widen, thick_doors = True, True
        elif a == "--terrain":
            terrain = True
        elif a.startswith("--terrain-cell="):
            # cell,quant in source units: coarser ground for a map that would pass the box limit
            terrain = True
            t_cell, _, t_quant = a[15:].partition(",")
            terrain_args = dict(cell=float(t_cell), quant=float(t_quant or 5.0))
        elif a == "--prune-pockets":
            pockets = True
        elif a.startswith("--pocket-margin="):
            pockets, margin = True, float(a[16:])
        elif a == "--prune-levels":
            pockets, levels = True, True
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
        mt = docboxes.majority_material(names, TEXTURE_MAP, default=("flat", None))
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
    if not terrain and starts_unfloored(bsp, m.boxes) * 2 > len(start_entities(bsp)) and any(f[6] >= 0 for f in bsp.model_faces(0)):
        # The ground is sculpted (Bikini Bottom's sea bed), so the box pass found none under the starts.
        terrain = True
        print("starts stand on nothing and the map has displacements: --terrain")
    if terrain:
        n = 0
        field = terrain_boxes(bsp, **terrain_args)
        # The document's box limit is 6000 (PhMapDoc.MAX_BOXES): coarsen the field until the walls and the ground fit.
        # Boxes the ground covers are dropped first: a coarse field steps more than a body can climb.
        if not terrain_args and len(m.boxes) + len(field) > 5600:
            m.boxes[:] = drop_buried(m.boxes, field)
        for cell in (120.0, 160.0, 240.0):
            if terrain_args or len(m.boxes) + len(field) <= 5600:
                break
            field = terrain_boxes(bsp, cell=cell)
            print("terrain: cell %.0f for the box limit" % cell)
        for (x0, x1), (y0, y1), (z0, z1), mat in field:
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
        for q in (m.props if pid else []):
            qw, qd = build_maps.footprint(q["id"], q.get("yaw", 0.0))
            # Well inside the footprint, not on its rim: a round bin's corner is air.
            if abs(x - q["at"][0]) <= qw / 2 - 0.08 and abs(z - q["at"][2]) <= qd / 2 - 0.08:
                t = q["at"][1] + build_maps.rest_on(q, x - q["at"][0], z - q["at"][2], pid, yaw)
                if t <= ymax and (best is None or t > best):
                    best = t
        return best

    dropped = {}
    placed = []
    packed = bsp_models.measure(bsp)
    catalogue = {k: v["size"] for k, v in build_maps.SIZES.items() if v.get("disguise", True) and v.get("size")}
    by_shape = {}
    for e in bsp.entities:
        cls = e.get("classname")
        if cls in PROP_CLASSES:
            # Keys are matched lower-cased: authors spell one model Chair_office and chair_office.
            key = os.path.splitext(os.path.basename(e.get("model", "")))[0].lower()
            pid = PROP_MAP.get(key)
            rec = packed.get(e.get("model", ""))
            if rec is not None:
                # The map packs this model, so its real size is known. A name guess (PROP_MAP, by
                # file stem) stands only if it is about that size; otherwise the catalogue prop of
                # the model's own shape does, and the stand-in is put on the model's middle.
                k = float(e.get("modelscale") or 1.0) if str(e.get("modelscale", "")).replace(".", "", 1).isdigit() else 1.0
                size = rec["size"]
                if pid is not None and not bsp_models.compatible(size, catalogue.get(pid, size), limit=GUESS_LIMIT, scale=k):
                    by_shape["%s: %s -> " % (key, pid)] = by_shape.get("%s: %s -> " % (key, pid), 0) + 1
                    pid = None
                if pid is None and not standins.is_skybox(e.get("model")) and max(size) * k <= MAX_PACKED_SIDE:
                    pid = bsp_models.match_size(size, catalogue, limit=SHAPE_LIMIT, scale=k)
                    if pid is not None:
                        by_shape[key + " => " + pid] = by_shape.get(key + " => " + pid, 0) + 1
            if pid is None:
                dropped[key] = dropped.get(key, 0) + 1
                continue
            placed.append((vec(e["origin"])[2], e, pid, rec))
        elif cls in ("light", "light_spot"):
            o = vec(e["origin"])
            gx, gy, gz = gd(o)
            c = vec(e.get("_light", "255 255 255 200"))
            c = (list(c) + [255, 255, 255, 200][len(c):])[:4]  # a light may omit its brightness (or all of it)
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
    for _, e, pid, rec in sorted(placed, key=lambda t: t[0]):
        ang = vec(e.get("angles", "0 0 0"))
        gx, gy, gz = gd(vec(e["origin"]))
        if rec is not None:
            # A model's origin is where its author put it, not its middle: the footprint is centred.
            cx, cz = rec["centre"][0], -rec["centre"][2]
            a = math.radians(ang[1])
            gx += cx * math.cos(a) - cz * math.sin(a)
            gz += -(cx * math.sin(a) + cz * math.cos(a))
        yaw = (ang[1] + 90.0) % 360.0
        y = support(gx, gz, pid, yaw, gy + 0.35)
        if y is None:
            y = max(gy, 0.0)
        if y < 0.06 and not floor_corners_ok(gx, gz, pid, yaw, y) and not any(
                abs(q["at"][0] - gx) < 0.01 and abs(q["at"][2] - gz) < 0.01 for q in m.props):
            dropped["(over a hole)"] = dropped.get("(over a hole)", 0) + 1
            if os.environ.get("PH_DEBUG"):
                print("over a hole: %s at %.2f %.2f %.2f" % (pid, gx, y, gz))
            continue
        m.prop(pid, gx, gz, yaw=yaw, y=y)
    starts = [e for e in bsp.entities if e.get("classname") in START_CLASSES]
    for i, e in enumerate(starts):
        o = vec(e["origin"])
        gx, gy, gz = gd(o)
        ang = vec(e.get("angles", "0 0 0"))
        # Stands on whatever floor is under the start (a sunken room is below zero), not on zero.
        floor = support(gx, gz, None, 0.0, gy + 0.6)
        if os.environ.get("PH_DEBUG"):
            print("start %d at %.2f %.2f %.2f floor %s floored %s" % (i, gx, gy, gz, floor, m._floored(gx, (max(gy, 0.0) if floor is None else floor), gz)))
        sy = (max(gy, 0.0) if floor is None else floor) + 0.05
        # A start the author put in a prop or a wall with nothing clear and floored within four
        # metres (a bin on a rooftop, a hole in the terrain) is dropped: the builder would stop
        # the whole build rather than move it.
        if m._blocked(gx, sy, gz) is not None and not any(
                m._blocked(gx + r * 0.5 * math.cos(a * math.pi / (4 * r)), sy, gz + r * 0.5 * math.sin(a * math.pi / (4 * r))) is None
                and m._floored(gx + r * 0.5 * math.cos(a * math.pi / (4 * r)), sy, gz + r * 0.5 * math.sin(a * math.pi / (4 * r)))
                for r in range(1, 9) for a in range(8 * r)):
            continue
        # Nor is one over nothing: a start on a prop or a ledge that this document does not carry
        # (Island House: a hunter start in a stairwell pit) fails headless_maps' "stands on a floor".
        if not m._floored(gx, sy - 0.05, gz):
            continue
        m.spawn("props" if i % 2 == 0 else "hunters", gx, gz, yaw=ang[1] - 90.0, y=(max(gy, 0.0) if floor is None else floor) + 0.05)
    # The author gave six starts; a prop hunt wants six hiding starts and three hunter ones.
    # More are taken from the clearest open floor, at least 3 m from any other start.
    have = [(sp["at"][0], sp["at"][2]) for side in m.spawns.values() for sp in side]
    for size, x, z in m.spots(step=1.5, top=60):
        if len(m.spawns["props"]) >= 8:
            break
        if all((x - a) ** 2 + (z - b) ** 2 >= 9.0 for a, b in have):
            m.spawn("props", x, z, yaw=0.0)
            have.append((x, z))
    hy = sorted(sp["at"][1] for sp in m.spawns["hunters"])
    fy = round(hy[len(hy) // 2] - 0.05, 3) if hy else 0.0
    # The median level first (every earlier map keeps its toys), then the other levels the hunters
    # start on, most used first: a map with starts on four levels can have a median that is no floor
    # (Island House found no toy).
    hlevels = {}
    for sp in m.spawns["hunters"]:
        k = round(sp["at"][1] - 0.05, 3)
        hlevels[k] = hlevels.get(k, 0) + 1
    order = [fy] + [k for k in sorted(hlevels, key=lambda k: -hlevels[k]) if k != fy]
    for tid, near in (("football", 5.0), ("barrel", 5.0), ("beach_ball", 5.0)):
        # Two metres from every start, then one and a half when a small flat's 44 starts leave none.
        spot = None
        for ty in order:
            for gap in (4.0, 2.25):
                spot = next(((x, z) for size, x, z in m.spots(y=ty, step=1.5, top=60) if all((x - a) ** 2 + (z - b) ** 2 >= gap for a, b in have)), None)
                if spot:
                    break
            if spot:
                break
        if spot:
            m.toy(tid, spot[0], spot[1], y=ty, near=near)
            have.append(spot)
    # The game refuses more than 128 lights: keep an evenly spaced subset.
    if len(m.lights) > 128:
        n = len(m.lights)
        m.lights = [m.lights[i * n // 128] for i in range(128)]
    print("props %d  lights %d  spawns %d  dropped models %s" % (len(m.props), len(m.lights), len(starts), dropped))
    if by_shape:
        print("from the packed models' sizes: %s" % by_shape)
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
        ys = sorted(sp["at"][1] for sp in doc["spawns"]["hunters"])
        if not ys:
            sys.exit("no start stands on a floor in this map: the ground may be terrain (--terrain) or a prop")
        oy = round(ys[len(ys) // 2] - 0.05, 3)
        ground = [b for b in doc["boxes"] if b.get("solid", True) and abs(b["at"][1] + b["size"][1] / 2 - oy) < 0.05
                  and b["size"][0] > 4.0 and b["size"][2] > 4.0]
    if ground:
        cx = sum(sp["at"][0] for sp in doc["spawns"]["hunters"]) / len(doc["spawns"]["hunters"])
        cz = sum(sp["at"][2] for sp in doc["spawns"]["hunters"]) / len(doc["spawns"]["hunters"])
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
        for key in ("boxes", "props", "lights", "spawns", "toys"):
            shift(doc.get(key))
    if widen:
        n_doors = widen_doors(doc["boxes"])
        if thick_doors:
            n_doors += widen_sliced_doors(doc["boxes"])
            print("dropped %d door trim posts" % drop_trim_posts(doc["boxes"]))
        print("widened %d doorways to 1.4 m" % n_doors)
    if pockets:
        print("pruned %d props that left a pocket the bots cannot leave" % prune_pockets(doc, levels=levels, margin=margin, floor_lo=-1.0 if terrain else -0.05))
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
    # A sliver brush can come out with a zero or negative side; the game refuses the whole document for one.
    doc["boxes"] = [b for b in doc["boxes"] if min(b["size"]) > 0.005]
    print("audit: dropped %d props sunk in a wall or standing on nothing" % audit_props(doc))
    out_path = out_path or os.path.join(build_maps.ROOT, "maps", mid + ".json")
    with open(out_path, "w") as f:
        f.write(json.dumps(doc, indent=1) + "\n")
    print("wrote", out_path)


if __name__ == "__main__":
    main(sys.argv)
