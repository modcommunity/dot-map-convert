# gm_fork: Valve texture and model replacements

Every base-game texture and model the workshop map gm_fork (the brief's "gm_york" is taken to be this map; no gm_york file exists locally) references, with the free or own asset the converter uses instead. Machine-readable: `docs/valve-asset-map-gm_fork.json` (Valve name, group, chosen asset, source URL, author, licence, attribution). No Valve asset is stored here. The workshop author's own packed and addon content (59 pak and 62 addon textures, 101 addon models) is not Valve's and is kept with the author's credit, so it is not listed.

## Coverage

- Textures: 169 of 170 mapped (88 library PBR sets from ambientCG and Poly Haven, the rest generic CC0 sets or generated functional textures); 1 unmapped (`overlays/darkedge`, a screen-edge overlay with nothing to replace).
- Models: 206 of 241 mapped (library picks, free stand-ins, category rules and measured-piece blocks); 35 omitted on purpose by the converter (skybox models and small detail or distant-backdrop models such as the row buildings, cranes, dock poles and bumpers, vents and sprinklers); 0 unmapped.
- Licences of the mapped items: CC0-1.0 353, CC-BY-4.0 22. CC-BY-4.0 items (22 Sketchfab models) need the attribution in the JSON `attribution` field.

## Texture groups

other 44, concrete 44, metal 43, wood 22, brick 9, dirt 4, grass 2, sand 1, rock 1

## Model groups

buildings_structures 81, other_props 53, metal_pipes_vents 43, furniture 21, trees_plants 16, vehicles 15, barrels_crates 12

## Omitted on purpose

These stay out of the converted map by the `standins` skybox and detail rules (not a gap in the mapping); a map that wants them placed adds them to `DETAIL_KEEP` and a `categories.tsv` row.

- `models/cranes/crane_docks.mdl` (small detail model)
- `models/cranes/crane_frame.mdl` (small detail model)
- `models/cranes/crane_frame_interior.mdl` (small detail model)
- `models/props_buildings/project_building01_skybox.mdl` (skybox model)
- `models/props_buildings/project_building02_skybox.mdl` (skybox model)
- `models/props_buildings/project_building03_skybox.mdl` (skybox model)
- `models/props_buildings/row_corner_1.mdl` (small detail model)
- `models/props_buildings/row_corner_2.mdl` (small detail model)
- `models/props_buildings/row_hill_cluster.mdl` (small detail model)
- `models/props_buildings/row_industrial_cluster.mdl` (small detail model)
- `models/props_buildings/row_res_1.mdl` (small detail model)
- `models/props_buildings/row_res_1_ascend.mdl` (small detail model)
- `models/props_buildings/row_res_2.mdl` (small detail model)
- `models/props_buildings/row_res_2_ascend.mdl` (small detail model)
- `models/props_buildings/row_upscale.mdl` (small detail model)
- `models/props_c17/utilityconnecter002.mdl` (small detail model)
- `models/props_canal/refinery_03_skybox.mdl` (skybox model)
- `models/props_docks/dock01_pole01a_128.mdl` (small detail model)
- `models/props_docks/dock01_pole01a_256.mdl` (small detail model)
- `models/props_docks/dock01_polecluster01b.mdl` (small detail model)
- `models/props_docks/dock01_polecluster01b_256.mdl` (small detail model)
- `models/props_docks/dock02_pole02a.mdl` (small detail model)
- `models/props_docks/dock_bumper01a.mdl` (small detail model)
- `models/props_docks/dock_bumper01b_256.mdl` (small detail model)
- `models/props_docks/dock_bumper02a.mdl` (small detail model)
- `models/props_docks/dock_bumper03a.mdl` (small detail model)
- `models/props_rooftop/chimneysmokestack_cluster01a.mdl` (small detail model)
- `models/props_rooftop/rooftopcluser09a.mdl` (small detail model)
- `models/props_rooftop/satellitedish02.mdl` (small detail model)
- `models/props_trainstation/trackmarkers01.mdl` (small detail model)
- `models/props_vents/vent_large_corner001.mdl` (small detail model)
- `models/props_vents/vent_large_corner002.mdl` (small detail model)
- `models/props_vents/vent_large_straight001.mdl` (small detail model)
- `models/props_vents/vent_large_straight002.mdl` (small detail model)
- `models/props_wasteland/prison_sprinkler001b.mdl` (small detail model)

## Weak picks to revisit

A few CC-BY library picks fit by size, not by look: `props_wasteland/coolingtank02` (fire extinguisher), `props_rooftop/dome004` (ceiling lamp), `props_vehicles/tire001a_tractor` (flatbed truck). They are open items for the model-ranking pass.
