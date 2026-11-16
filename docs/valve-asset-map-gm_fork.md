# gm_fork: Valve texture and model replacements

Every base-game texture and model the workshop map gm_fork (workshop 326332456; gm_york is a different map whose BSP is not stored here yet) references, with the free or own asset the converter uses instead. Machine-readable: `docs/valve-asset-map-gm_fork.json` (Valve name, group, chosen asset, source URL, author, licence, attribution). No Valve asset is stored here. The workshop author's own packed and addon content (59 pak and 62 addon textures, 101 addon models) is not Valve's and is kept with the author's credit, so it is not listed.

## Coverage

- Textures: 169 of 170 mapped (88 library PBR sets from ambientCG and Poly Haven, the rest generic CC0 sets or generated functional textures); 1 unmapped (`overlays/darkedge`): the converter does not draw `info_overlay` decals yet, so no overlay texture reaches the map.
- Models: 241 of 241 mapped (library picks, free stand-ins, category rules, measured-piece blocks and generated own blocks); 0 omitted and 0 unmapped when converted with `--no-omit`. Without the flag the converter still leaves out the 35 skybox and small detail models listed below, so other maps keep their output.
- Licences of the mapped items: CC0-1.0 389, CC-BY-4.0 21. CC-BY-4.0 items (21 Sketchfab models) need the attribution in the JSON `attribution` field.

## Texture groups

other 44, concrete 44, metal 43, wood 22, brick 9, dirt 4, grass 2, sand 1, rock 1

## Model groups

buildings_structures 81, other_props 53, metal_pipes_vents 43, furniture 21, trees_plants 16, vehicles 15, barrels_crates 12

## Kept by `--no-omit`

The skybox and detail models the default rules leave out, and the three earlier wrong fits (`coolingtank02` was a fire extinguisher, `dome004` a ceiling lamp, `tire001a_tractor` a flatbed truck), with what the no-omission mode places. Props in the 3D skybox room are moved out and scaled like the room's faces, and are not solid. `own_box_*` are blocks the converter generates at the model's measured size and colour.

| Valve model | instances | asset | source | licence |
|---|---|---|---|---|
| `cranes/crane_docks` | 1 | `ph_overhead_crane` | Poly Haven | CC0-1.0 |
| `cranes/crane_frame` | 1 | `own_box_540x957x540_7a6a30` | Gamespice generated model | CC0-1.0 |
| `cranes/crane_frame_interior` | 1 | `own_box_476x784x476_7a6a30` | Gamespice generated model | CC0-1.0 |
| `props_buildings/project_building01_skybox` | 8 | `kenney_city-kit-commercial_building-f` | Kenney City Kit - Commercial | CC0-1.0 |
| `props_buildings/project_building02_skybox` | 4 | `kenney_city-kit-industrial_building-s` | Kenney City Kit - Industrial | CC0-1.0 |
| `props_buildings/project_building03_skybox` | 3 | `kenney_city-kit-commercial_building-i` | Kenney City Kit - Commercial | CC0-1.0 |
| `props_buildings/row_corner_1` | 3 | `kenney_city-kit-industrial_building-c` | Kenney City Kit - Industrial | CC0-1.0 |
| `props_buildings/row_corner_2` | 8 | `kenney_city-kit-industrial_building-c` | Kenney City Kit - Industrial | CC0-1.0 |
| `props_buildings/row_hill_cluster` | 3 | `kenney_city-kit-commercial_building-j` | Kenney City Kit - Commercial | CC0-1.0 |
| `props_buildings/row_industrial_cluster` | 1 | `kenney_city-kit-commercial_building-e` | Kenney City Kit - Commercial | CC0-1.0 |
| `props_buildings/row_res_1` | 1 | `kenney_city-kit-industrial_building-s` | Kenney City Kit - Industrial | CC0-1.0 |
| `props_buildings/row_res_1_ascend` | 2 | `kenney_city-kit-industrial_building-s` | Kenney City Kit - Industrial | CC0-1.0 |
| `props_buildings/row_res_2` | 4 | `kenney_city-kit-industrial_building-s` | Kenney City Kit - Industrial | CC0-1.0 |
| `props_buildings/row_res_2_ascend` | 5 | `kenney_city-kit-commercial_building-k` | Kenney City Kit - Commercial | CC0-1.0 |
| `props_buildings/row_upscale` | 7 | `kenney_city-kit-industrial_building-s` | Kenney City Kit - Industrial | CC0-1.0 |
| `props_c17/utilityconnecter002` | 2 | `own_box_7x23x111_606060` | Gamespice generated model | CC0-1.0 |
| `props_canal/refinery_03_skybox` | 2 | `sf_rusted_tank_storage_57be2e` | Sketchfab | CC-BY-4.0 |
| `props_docks/dock01_pole01a_128` | 8 | `own_cyl_32x246x32_5a4630` | Gamespice generated model | CC0-1.0 |
| `props_docks/dock01_pole01a_256` | 13 | `own_cyl_33x490x33_5a4630` | Gamespice generated model | CC0-1.0 |
| `props_docks/dock01_polecluster01b` | 7 | `own_cyl_72x976x320_5a4630` | Gamespice generated model | CC0-1.0 |
| `props_docks/dock01_polecluster01b_256` | 1 | `own_cyl_56x488x319_5a4630` | Gamespice generated model | CC0-1.0 |
| `props_docks/dock02_pole02a` | 1 | `own_cyl_32x793x32_5a4630` | Gamespice generated model | CC0-1.0 |
| `props_docks/dock_bumper01a` | 3 | `own_box_54x961x973_3a3a3a` | Gamespice generated model | CC0-1.0 |
| `props_docks/dock_bumper01b_256` | 1 | `own_box_55x482x973_3a3a3a` | Gamespice generated model | CC0-1.0 |
| `props_docks/dock_bumper02a` | 3 | `own_box_76x978x1948_3a3a3a` | Gamespice generated model | CC0-1.0 |
| `props_docks/dock_bumper03a` | 2 | `own_box_73x982x1948_3a3a3a` | Gamespice generated model | CC0-1.0 |
| `props_rooftop/chimneysmokestack_cluster01a` | 1 | `own_cyl_143x146x776_6a5a50` | Gamespice generated model | CC0-1.0 |
| `props_rooftop/dome004` | 1 | `own_cyl_397x248x397_8a8a80` | Gamespice generated model | CC0-1.0 |
| `props_rooftop/rooftopcluser09a` | 6 | `ph_exterior_aircon_unit` | Poly Haven | CC0-1.0 |
| `props_rooftop/satellitedish02` | 1 | `dm_roofdish` | dot-map Blender model | CC0-1.0 |
| `props_trainstation/trackmarkers01` | 12 | `own_box_567x26x30_606060` | Gamespice generated model | CC0-1.0 |
| `props_vehicles/tire001a_tractor` | 2 | `ph_old_tyre` | Poly Haven | CC0-1.0 |
| `props_vents/vent_large_corner001` | 1 | `ph_modular_airduct_rectangular_01` | Poly Haven | CC0-1.0 |
| `props_vents/vent_large_corner002` | 4 | `dm_ductrun` | dot-map Blender model | CC0-1.0 |
| `props_vents/vent_large_straight001` | 5 | `dm_ductrun` | dot-map Blender model | CC0-1.0 |
| `props_vents/vent_large_straight002` | 2 | `dm_ductrun` | dot-map Blender model | CC0-1.0 |
| `props_wasteland/coolingtank02` | 4 | `sf_rusted_tank_storage_57be2e` | Sketchfab | CC-BY-4.0 |
| `props_wasteland/prison_sprinkler001b` | 6 | `own_cyl_12x41x977_707070` | Gamespice generated model | CC0-1.0 |

## Open items

- The generated blocks (crane frame, dock bumpers and poles, dome, sprinkler, chimney, lever, crank and others) are placeholders until own Blender models replace them.
- `info_overlay` decals (`overlays/darkedge` and the other overlay textures) are not drawn.
