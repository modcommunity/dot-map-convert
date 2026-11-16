# gm_fork: Valve texture and model replacements

Every base-game texture and model the workshop map gm_fork (workshop 326332456; gm_york is a different map: workshop 2546826319 (gm_york_remaster) and 1727393665 (gm_york), stored privately in mapsrc, never in this repository) references, with the free or own asset the converter uses instead. Machine-readable: `docs/valve-asset-map-gm_fork.json` (Valve name, group, chosen asset, source URL, author, licence, attribution). No Valve asset is stored here. The workshop author's own packed and addon content (59 pak and 62 addon textures, 101 addon models) is not Valve's and is kept with the author's credit, so it is not listed.

## Coverage

- Textures: 170 of 170 mapped (88 library PBR sets from ambientCG and Poly Haven, the rest generic CC0 sets or generated functional textures). `info_overlay` decals are drawn with `--no-omit` (or `regen --overlays`), each in its texture row's look; `overlays/darkedge` is a generated dark see-through sheet.
- Models: 241 of 241 mapped (library picks, free stand-ins, category rules, measured-piece blocks and own Blender models); 0 omitted and 0 unmapped when converted with `--no-omit`. Without the flag the converter still leaves out the 35 skybox and small detail models listed below, so other maps keep their output.
- Licences of the mapped items: CC0-1.0 389, CC-BY-4.0 21. CC-BY-4.0 items (21 Sketchfab models) need the attribution in the JSON `attribution` field.

## Texture groups

other 44, concrete 44, metal 43, wood 22, brick 9, dirt 4, grass 2, sand 1, rock 1

## Model groups

buildings_structures 81, other_props 53, metal_pipes_vents 43, furniture 21, trees_plants 16, vehicles 15, barrels_crates 12

## Kept by `--no-omit`

The skybox and detail models the default rules leave out, and the three earlier wrong fits (`coolingtank02` was a fire extinguisher, `dome004` a ceiling lamp, `tire001a_tractor` a flatbed truck), with what the no-omission mode places. Props in the 3D skybox room are moved out and scaled like the room's faces, and are not solid. `dm_*` are own Blender models (CC0, `tools/models/harbour_rooftop.py`, kept in the model library under `dotmap/`) made at the Valve model's measured size; they replaced the 16 flat generated blocks on 2026-11-16. `rooftopcluser09a` is a 12 m rooftop plant cluster, so it now picks `dm_rooftophvac` instead of one air conditioner drawn 15.8 m long.

| Valve model | instances | asset | source | licence |
|---|---|---|---|---|
| `cranes/crane_docks` | 1 | `ph_overhead_crane` | Poly Haven | CC0-1.0 |
| `cranes/crane_frame` | 1 | `dm_latticetower` | dot-map Blender model | CC0-1.0 |
| `cranes/crane_frame_interior` | 1 | `dm_latticetower` | dot-map Blender model | CC0-1.0 |
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
| `props_c17/utilityconnecter002` | 2 | `dm_linecrossarm` | dot-map Blender model | CC0-1.0 |
| `props_canal/refinery_03_skybox` | 2 | `sf_rusted_tank_storage_57be2e` | Sketchfab | CC-BY-4.0 |
| `props_docks/dock01_pole01a_128` | 8 | `dm_dockpileshort` | dot-map Blender model | CC0-1.0 |
| `props_docks/dock01_pole01a_256` | 13 | `dm_dockpile` | dot-map Blender model | CC0-1.0 |
| `props_docks/dock01_polecluster01b` | 7 | `dm_dockpilecluster` | dot-map Blender model | CC0-1.0 |
| `props_docks/dock01_polecluster01b_256` | 1 | `dm_dockpileclustershort` | dot-map Blender model | CC0-1.0 |
| `props_docks/dock02_pole02a` | 1 | `dm_dockpiletall` | dot-map Blender model | CC0-1.0 |
| `props_docks/dock_bumper01a` | 3 | `dm_dockfendersquare` | dot-map Blender model | CC0-1.0 |
| `props_docks/dock_bumper01b_256` | 1 | `dm_dockfenderhalf` | dot-map Blender model | CC0-1.0 |
| `props_docks/dock_bumper02a` | 3 | `dm_dockfenderlong` | dot-map Blender model | CC0-1.0 |
| `props_docks/dock_bumper03a` | 2 | `dm_dockfenderlong` | dot-map Blender model | CC0-1.0 |
| `props_rooftop/chimneysmokestack_cluster01a` | 1 | `dm_roofstackrow` | dot-map Blender model | CC0-1.0 |
| `props_rooftop/dome004` | 1 | `dm_roofdome` | dot-map Blender model | CC0-1.0 |
| `props_rooftop/rooftopcluser09a` | 6 | `dm_rooftophvac` | dot-map Blender model | CC0-1.0 |
| `props_rooftop/satellitedish02` | 1 | `dm_roofdish` | dot-map Blender model | CC0-1.0 |
| `props_trainstation/trackmarkers01` | 12 | `dm_trackmarker` | dot-map Blender model | CC0-1.0 |
| `props_vehicles/tire001a_tractor` | 2 | `ph_old_tyre` | Poly Haven | CC0-1.0 |
| `props_vents/vent_large_corner001` | 1 | `ph_modular_airduct_rectangular_01` | Poly Haven | CC0-1.0 |
| `props_vents/vent_large_corner002` | 4 | `dm_ductrun` | dot-map Blender model | CC0-1.0 |
| `props_vents/vent_large_straight001` | 5 | `dm_ductrun` | dot-map Blender model | CC0-1.0 |
| `props_vents/vent_large_straight002` | 2 | `dm_ductrun` | dot-map Blender model | CC0-1.0 |
| `props_wasteland/coolingtank02` | 4 | `sf_rusted_tank_storage_57be2e` | Sketchfab | CC-BY-4.0 |
| `props_wasteland/prison_sprinkler001b` | 6 | `dm_sprinklerpipe` | dot-map Blender model | CC0-1.0 |

## Open items

- Detail of the own Blender models is blockout level (no textures, flat material colours); a textured pass is still open.
- `info_overlay` decals are drawn as mesh lifted off their faces, with hard edges: the runtime has no decal blending, so an overlay whose material fades out at its border (dirt tracks, gravel paths, cliff edges) shows its full quad.
- gm_fork's 45585 detail sprites all stand in the 3D skybox room; `--no-omit` draws them there, moved out and scaled up with the room, as crossed cards in the `foliage_card` look rather than the map's own grass sheet.
