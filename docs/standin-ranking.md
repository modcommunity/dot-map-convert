# Stand-in ranking

Which source models and sounds are still drawn by a stand-in (a Kenney block, a generated plain shape or `placeholder_box`) instead of an equal-quality free model, ranked by how many converted maps use them. Source: the `licence` sections of the converted manifests in zombie-zone-maps (`world/*/*.json`) and g2gfast-maps (`worlds/*.json`), 44 manifests carry one; the rest are not yet through the licence pass, so counts are lower bounds. Regenerate with the same walk after a licence pass. Models are named by category; the key is the model's file name in the manifest.

The replacement layer is `rules/models/categories.tsv` (name regex to library ids) feeding `bsp.py modelmap` and `picks.tsv`; the Replaced column says what the first batch pinned.

The ranking is reproducible with `python3 -I tools/bsp/bsp.py standins <zombie-zone-maps/world> <g2gfast-maps/worlds>`: it sorts every shipped model into free, kenney, generated or placeholder, flags a world whose shipped stand-in differs from `picks.tsv` (regenerate it through the converter), lists the sound rows silent by rule, and with `--strict` exits 1 while anything of the listed tiers remains. `dm_wood_crate_cube` (a cubic wooden crate remodelled in Blender by `tools/models/wood_crate.py`, CC0, TMC) now serves the wooden crates in place of the Kenney crate with bottles; it lives in the library as `dotmap/dm_wood_crate_cube`.

## Models, top 40

| # | Maps | Instances | Category | Key | Current stand-in | Replaced |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 12 | 146 | wooden crate | `wood_crate001a` | `lib/kenney_pirate-kit_crate-bottles` | no (no suitable free model in the library) |
| 2 | 11 | 75 | wooden door, left leaf | `door01_left` | `lib/kenney_building-kit_door-rotate-square-c` | `sf_door_wood_afed97` (CC-BY-4.0) |
| 3 | 9 | 236 | small crate | `crate_extrasmall` | `lib/kenney_pirate-kit_crate-bottles` | no (no suitable free model in the library) |
| 4 | 7 | 158 | small crate, painted | `crate_extrasmallmill` | `lib/kenney_pirate-kit_crate-bottles` | `ph_wooden_military_crate` (CC0-1.0) |
| 5 | 7 | 72 | fluorescent tube, narrow | `lab_flourescentlight002b` | `lib/own_box_11x15x119_e8e8e0` | `sf_weathered_fluorescent_light_lamp_4096px_5d29d2` (CC-BY-4.0) |
| 6 | 7 | 69 | fluorescent fixture | `lights_florescent01a` | `lib/own_box_120x10x20_e8e8e0` | `sf_weathered_fluorescent_light_lamp_07c280` (CC-BY-4.0) |
| 7 | 7 | 14 | coffee table | `table_coffee` | `lib/kenney_furniture-kit_tableCloth` | `ph_CoffeeTable_01` (CC0-1.0) |
| 8 | 6 | 66 | extra-large crate, painted | `crate_extralargemill` | `lib/kenney_pirate-kit_crate-bottles` | `ph_wooden_military_crate` (CC0-1.0) |
| 9 | 6 | 30 | cinder block | `cinderblock01a` | `lib/kenney_nature-kit_cliff_cornerLarge_rock` | no (no suitable free model in the library) |
| 10 | 6 | 24 | milk carton | `garbage_milkcarton002a` | `lib/kenney_furniture-kit_trashcan` | `kenney_food-kit_carton` (CC0-1.0) |
| 11 | 6 | 18 | coffee mug | `garbage_coffeemug001a` | `lib/kenney_food-kit_mug` | `sf_coffee_mug_6c9589` (CC-BY-4.0) |
| 12 | 6 | 8 | computer keyboard | `computer01_keyboard` | `lib/kenney_furniture-kit_cabinetTelevisionDoors` | `kenney_furniture-kit_computerKeyboard` (CC0-1.0) |
| 13 | 6 | 8 | horizontal storage tank | `horizontalcoolingtank04` | `lib/own_box_600x229x200_b0b0a8` | no (no suitable free model in the library) |
| 14 | 6 | 7 | rubbish pile | `garbage128_composite001d` | `lib/kenney_retro-urban-kit_detail-dumpster-closed` | no (no suitable free model in the library) |
| 15 | 5 | 36 | cash register | `cashregister01a` | `lib/kenney_furniture-kit_laptop` | `ph_CashRegister_01` (CC0-1.0) |
| 16 | 5 | 32 | square crate | `du_crate_64x64` | `lib/kenney_pirate-kit_crate-bottles` | no (no suitable free model in the library) |
| 17 | 5 | 26 | power box | `powerbox02d` | `lib/kenney_furniture-kit_cardboardBoxClosed` | no (no suitable free model in the library) |
| 18 | 5 | 18 | kitchen sink | `furnituresink001a` | `lib/kenney_furniture-kit_bathroomSink` | no (no suitable free model in the library) |
| 19 | 5 | 10 | server rack | `servers` | `lib/kenney_furniture-kit_televisionModern` | no (no suitable free model in the library) |
| 20 | 5 | 7 | crate stack | `crates_indoor` | `lib/kenney_pirate-kit_crate-bottles` | no (no suitable free model in the library) |
| 21 | 5 | 6 | horizontal storage tank | `de_train_horizontalcoolingtank` | `lib/own_box_603x234x204_b0b0a8` | no (no suitable free model in the library) |
| 22 | 5 | 6 | cab-over truck | `truck001a` | `lib/kenney_car-kit_garbage-truck` | no (no suitable free model in the library) |
| 23 | 5 | 5 | forklift | `forklift` | `lib/kenney_car-kit_ambulance` | no (no suitable free model in the library) |
| 24 | 5 | 5 | freight trailer | `trailer002a` | `lib/kenney_car-kit_garbage-truck` | no (no suitable free model in the library) |
| 25 | 4 | 114 | recessed ceiling light | `light_inset` | `lib/own_box_21x3x21_e8e8e0` | no (no suitable free model in the library) |
| 26 | 4 | 30 | large crate | `crate_large` | `lib/kenney_pirate-kit_crate-bottles` | no (no suitable free model in the library) |
| 27 | 4 | 30 | iron fence panel | `fence03a` | `lib/kenney_pirate-kit_structure-fence-sides` | no (no suitable free model in the library) |
| 28 | 4 | 17 | watermelon | `watermelon01` | `lib/kenney_food-kit_muffin` | no (no suitable free model in the library) |
| 29 | 4 | 16 | extra-large crate | `crate_extralarge` | `lib/kenney_pirate-kit_crate-bottles` | no (no suitable free model in the library) |
| 30 | 4 | 12 | metal bucket | `metalbucket01a` | `lib/kenney_food-kit_can` | no (no suitable free model in the library) |
| 31 | 4 | 12 | wooden fence panel | `exterior_fence002c` | `lib/kenney_pirate-kit_structure-fence` | no (no suitable free model in the library) |
| 32 | 4 | 9 | bed | `furniturebed001a` | `lib/kenney_food-kit_egg-cup` | no (no suitable free model in the library) |
| 33 | 4 | 8 | banana bunch | `bananna_bunch` | `lib/kenney_food-kit_sausage-half` | no (no suitable free model in the library) |
| 34 | 4 | 7 | takeaway carton | `garbage_takeoutcarton001a` | `lib/kenney_furniture-kit_trashcan` | `kenney_food-kit_carton-small` (CC0-1.0) |
| 35 | 4 | 5 | plastic bottle | `garbage_plasticbottle003a` | `lib/kenney_food-kit_soda-bottle` | no (no suitable free model in the library) |
| 36 | 4 | 4 | fireplace | `furniturefireplace001a` | `lib/kenney_food-kit_egg-cup` | no (no suitable free model in the library) |
| 37 | 4 | 4 | tanker trailer | `tanker001a` | `lib/own_box_250x280x850_c8c8c0` | no (no suitable free model in the library) |
| 38 | 3 | 93 | cardboard box | `dryer_box` | `lib/kenney_furniture-kit_cardboardBoxClosed` | no (no suitable free model in the library) |
| 39 | 3 | 38 | burger patty | `patty` | `lib/kenney_food-kit_tomato` | no (no suitable free model in the library) |
| 40 | 3 | 32 | ceiling light panel | `light_ceiling` | `lib/own_box_122x11x61_e8e8e0` | no (no suitable free model in the library) |

## Sounds, top 20

Only ambient sound entities are counted (`sounds.ambient` with an empty stand-in). Music and voice stay silent by rule, so a free music or voice stand-in is a decision for the table owner, not a lookup. Most of the 102 unmatched names are used by one map.

| # | Maps | Entities | Category | Key (file name) | Replaced |
| --- | --- | --- | --- | --- | --- |
| 1 | 2 | 6 | voice or creature call (silent by rule) | `scream_loop1.wav` | no |
| 2 | 2 | 2 | voice or creature call (silent by rule) | `child_scream1.wav` | no |
| 3 | 2 | 2 | music track (silent by rule) | `(jingle)` | no |
| 4 | 2 | 2 | music track (silent by rule) | `(cartoon theme)` | no |
| 5 | 1 | 7 | music track (silent by rule) | `(music track)` | no |
| 6 | 1 | 4 | light hum | `flour_light.wav` | no |
| 7 | 1 | 4 | arcade jingle or effect | `boost.wav` | no |
| 8 | 1 | 4 | arcade jingle or effect | `(pipe jingle)` | no |
| 9 | 1 | 4 | voice or creature call (silent by rule) | `(creature alert)` | no |
| 10 | 1 | 4 | voice or creature call (silent by rule) | `(spoken line)` | no |
| 11 | 1 | 3 | music track (silent by rule) | `(music track)` | no |
| 12 | 1 | 3 | music track (silent by rule) | `(music track)` | no |
| 13 | 1 | 3 | music track (silent by rule) | `(music track)` | no |
| 14 | 1 | 3 | music track (silent by rule) | `(music track)` | no |
| 15 | 1 | 2 | music track (silent by rule) | `aurora.mp3` | no |
| 16 | 1 | 2 | music track (silent by rule) | `autumn.mp3` | no |
| 17 | 1 | 2 | music track (silent by rule) | `dust.mp3` | no |
| 18 | 1 | 2 | engine or rotor loop | `apc_idle1.wav` | no |
| 19 | 1 | 2 | music track (silent by rule) | `(music track)` | no |
| 20 | 1 | 2 | ambience or effect | `(vocal clip)` | no |

## What is left

The library (`~/art-library/models`) already holds every Poly Haven model and the Quaternius, Kenney and Sketchfab CC0/CC-BY sets, so the first batch is pins in `rules/models/categories.tsv` and a regenerated `picks.tsv`. A cubic wooden crate, a cinder block, a horizontal storage tank, a bed, a fireplace, trucks and a forklift have no free model in it: they need a Sketchfab or Poly Pizza download (an API token, or the Blender MCP with a running Blender, neither available on the build box) or a Blender remodel. Sound and music stand-ins are untouched.
