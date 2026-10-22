# Entity classes, and what the importer makes of each

Every entity class found in 200 community maps (2026-10-21: the 98 under `inspirations/g2gfast` and every map source under `~/mapsrc`, 318 classes; two cut-off downloads unreadable), what it is in the original engine, and what `dotbsp` makes of it. The table is written from `dotbsp/classes.py` by `python3 -I tools/bsp/bsp.py classes --markdown <maps...>`, so a change goes there and this file is regenerated, never edited by hand. `bsp.py mesh` prints what became of every entity of the map it converts and fails on a class with no row and no prefix rule.

What a class becomes:

- `world`: geometry, drawn and solid (`dotbsp/mesh.py`), like any world brush.
- `drawn`: geometry, drawn and never solid.
- `mover`: geometry that moves: a record in the mesh manifest's `movers` (what moves, which way, how far, how fast, what starts it, and the outputs that drive it) beside its model's surfaces and hulls (`dotbsp/movers.py`).
- `volume`: a brush a body is affected by inside: the manifest's `volumes` (multiple, once, teleport, push, hurt, gravity, water, ladder) with each brush's planes; never drawn.
- `point`: a point entity a game uses as it is: spawns, lights, the sun, fog, the 3D sky, props, sounds, decals, effect positions (the intermediate's `entities`, `lights`, `spawns`, `static_props`).
- `data`: kept verbatim in the intermediate's entity list (map logic, paths, filters). Nothing runs it: a converter is not a scripting engine. The one exception is an output that drives a mover (`button -> door,Open`), which `movers` records as `opened_by`, because a button that opens a door and a lift is what the escape and zombie maps are built around.
- `dropped`: deliberately left out, with the reason in the row.

## What changes how a map looks

| What | Where it goes |
| --- | --- |
| World brushes and `func_detail` | `mesh` surfaces, by material; every texture is replaced (`source_textures.tsv` generic ids), never shipped |
| Displacements (terrain) | `mesh` surfaces flagged `displacement`, collided as triangles |
| `func_illusionary`, `func_brush`, `func_wall`, breakables, doors, buttons | `mesh` surfaces of their model, offset by the entity origin; hidden ones (`rendermode 10`, alpha 0, a func_brush that starts disabled) are not drawn |
| `sky_camera` and its room (the 3D skybox) | the room's faces are moved out and scaled up around the world origin as the engine draws them, flagged `sky3d`, never solid (`mesh.skybox_of`) |
| `light`, `light_spot`, `light_environment`, `env_sun`, `shadow_control` | the intermediate's `lights` and the sun (`dotbsp/lights.py`) |
| `env_fog_controller`, `env_tonemap_controller`, `color_correction`, `water_lod_control` | `point` data a game reads for its environment; colour-grade lookup files are the source's own and never shipped |
| Water (`func_water_analog`, water-content brushes) | drawn as their surfaces (`water` flag) and a `water` volume |
| Static props, `prop_*` | `point` data; models are studied, a game places its own (`dotbsp/props.py` matches them) |
| `infodecal`, overlays | `point` data; their materials are replaced like any texture |
| `env_cubemap` | `point` data (reflection probe positions) |
| `func_areaportal`, `func_occluder` | dropped: visibility hints; the renderer culls on its own |
| `func_dustmotes`, `func_smokevolume`, `env_embers` | dropped: particle volumes (an open item for the look) |

## Every class

| Class | Maps | What it is | What it becomes |
| --- | --- | --- | --- |
| `worldspawn` | 200 | the world: every compiled brush, func_detail included, and the map's sky name and keys | `world` |
| `light` | 174 | a point light: `_light` colour and brightness | `point` |
| `light_environment` | 160 | the sun and sky light of an outdoor map: direction, colour, ambient | `point` |
| `trigger_teleport` | 155 | sends a body that enters to its `target` destination | `volume` |
| `info_player_terrorist` | 150 | a spawn of one team | `point` |
| `water_lod_control` | 149 | how far cheap water starts; kept as a look hint | `point` |
| `info_teleport_destination` | 140 | where a teleport sends a body | `point` |
| `info_player_counterterrorist` | 139 | a spawn of the other team | `point` |
| `func_button` | 138 | a button: pressed by use or touch, moves along `movedir` by its size minus `lip`, fires OnPressed | `mover` |
| `ambient_generic` | 134 | a sound played at a point, looped or on input | `point` |
| `trigger_multiple` | 130 | fires outputs each time a body enters | `volume`: fires outputs each time a body enters, then waits `wait` seconds |
| `func_illusionary` | 124 | a brush that is drawn and never solid (foliage, light shafts, fake walls); one painted with water is water | `drawn` |
| `trigger_push` | 122 | pushes a body inside along `pushdir` at `speed` | `volume` |
| `func_breakable` | 116 | a brush that breaks when damaged; drawn and solid where it stands | `world`: breaking is the game's (ZZ: barricades) |
| `prop_dynamic` | 109 | a placed model that may animate; models are studied | `point` |
| `func_door` | 104 | a sliding door: moves along `movedir` by its size minus `lip` at `speed`, opened by a touch, a use or an input | `mover` |
| `func_rotating` | 102 | a brush that spins about one axis at `maxspeed` (fans, wheels, rotating platforms) | `mover` |
| `info_target` | 99 | a named point other entities aim at | `point` |
| `logic_auto` | 98 | fires outputs when the map starts | `data`: logic |
| `infodecal` | 95 | a decal (a stain, a sign) projected on a surface; its material is the source's, replaced like any texture | `point` |
| `func_brush` | 94 | a toggleable brush; drawn and solid unless `Solidity` 1, rendermode 10 or StartDisabled | `world`: toggling is the map's logic |
| `trigger_hurt` | 91 | damages a body inside by `damage` a second (pits, lava, crushers) | `volume` |
| `light_spot` | 87 | a spot light: cone, direction, colour | `point` |
| `env_sprite` | 84 | a glow sprite (a lamp's halo) | `point` |
| `info_ladder` | 78 | a ladder volume as a point entity (mins and maxs keys) | `point` |
| `point_spotlight` | 77 | a visible light beam and its light | `point` |
| `info_player_start` | 74 | a spawn | `point` |
| `logic_timer` | 74 | fires outputs on a timer | `data`: logic |
| `prop_physics` | 74 | a placed physics model (a barrel, a crate); models are studied | `point` |
| `game_player_equip` | 73 | gives players weapons on spawn | `data`: the game decides kits |
| `point_template` | 73 | a template that spawns copies of entities | `data`: logic |
| `trigger_once` | 73 | fires outputs the first time a body enters | `volume`: fires outputs the first time a body enters |
| `func_door_rotating` | 69 | a hinged door: turns `distance` degrees about its origin's axis at `speed` | `mover` |
| `point_viewcontrol` | 67 | a scripted camera | `data`: logic |
| `sky_camera` | 66 | the 3D skybox's camera: where the miniature backdrop is and its scale (`mesh.skybox_of`) | `point` |
| `path_track` | 64 | a corner of a train's path; read by the movers for func_tracktrain | `data` |
| `func_physbox` | 60 | a brush simulated as a physics object; drawn and solid where it rests, not simulated | `world` |
| `func_dustmotes` | 58 | a particle volume of floating dust | `dropped`: effects, left to a game (an open item for the look) |
| `func_tracktrain` | 58 | a train that runs along `path_track` corners (lifts, boats, trucks); the path is in `movers` | `mover` |
| `prop_physics_multiplayer` | 57 | as prop_physics | `point` |
| `env_fog_controller` | 56 | distance fog: colour, start and end | `point` |
| `env_soundscape` | 56 | an ambient soundscape in reach | `point` |
| `filter_damage_type` | 56 | passes damage by type | `data`: logic |
| `prop_dynamic_override` | 55 | as prop_dynamic | `point` |
| `env_fire` | 54 | a fire that burns and hurts | `point`: an effect position |
| `move_rope` | 54 | a rope or cable's first point, with its look | `point` |
| `prop_physics_override` | 54 | as prop_physics | `point` |
| `filter_activator_name` | 52 | passes activators by name | `data`: logic |
| `logic_relay` | 50 | relays inputs to outputs | `data`: logic |
| `math_counter` | 49 | a counter with outputs | `data`: logic |
| `point_servercommand` | 49 | runs a server console command | `dropped`: a map does not run commands on this server |
| `env_spritetrail` | 48 | a sprite trail on a moving thing | `point`: an effect position |
| `func_areaportal` | 48 | a visibility portal (a door closes it); the renderer here culls on its own | `dropped` |
| `func_movelinear` | 46 | a brush moved between two positions by inputs (lifts, crushers): `movedir`, `movedistance`, `speed` | `mover` |
| `env_explosion` | 44 | an explosion by input | `data`: logic with a position |
| `env_spark` | 43 | sparks | `point`: an effect position |
| `filter_activator_team` | 42 | passes activators by team | `data`: logic |
| `func_water_analog` | 39 | water as a movable brush; swum in, it does not move here | `volume` |
| `logic_case` | 39 | picks an output by value | `data`: logic |
| `func_buyzone` | 38 | where a round-based shooter's team may buy weapons; no shop here | `dropped` |
| `env_sun` | 37 | the sun's sprite in the sky: its direction and colour | `point` |
| `env_entity_maker` | 36 | spawns a template at a point | `data`: logic |
| `env_laser` | 36 | a laser beam that may hurt | `point`: an effect |
| `keyframe_rope` | 36 | a rope's next point | `point` |
| `env_steam` | 35 | a steam jet | `point`: an effect position a game may fill |
| `prop_door_rotating` | 35 | a model door that swings; converted like func_door_rotating with its model studied | `mover` |
| `shadow_control` | 34 | the direction and colour of dynamic shadows | `point` |
| `env_shake` | 32 | shakes the screen | `data`: logic |
| `env_lightglow` | 31 | a glow seen around a light | `point` |
| `env_tonemap_controller` | 30 | exposure limits and bloom | `point` |
| `player_weaponstrip` | 29 | takes weapons by input | `data`: logic |
| `env_smokestack` | 25 | a smoke column | `point`: an effect position |
| `func_areaportalwindow` | 24 | a portal that fades with distance; as func_areaportal | `dropped` |
| `info_particle_system` | 24 | a particle effect; its system is the source's own, so a position and a name | `point` |
| `env_fade` | 23 | fades the screen by input | `data`: logic |
| `player_speedmod` | 23 | changes a player's speed by input | `data`: logic |
| `func_wall_toggle` | 22 | a wall an input shows or hides; drawn and solid unless it starts off (spawnflag 1) | `world` |
| `env_hudhint` | 21 | a hint on the screen | `data`: logic |
| `logic_compare` | 20 | compares a value | `data`: logic |
| `env_beam` | 19 | a beam between two points | `point`: an effect |
| `game_text` | 19 | shows text on screens | `data`: logic; its text is kept |
| `func_breakable_surf` | 18 | breakable glass panes; drawn and solid | `world` |
| `phys_thruster` | 18 | pushes a physics object | `data`: nothing is simulated |
| `point_camera` | 18 | a camera a monitor shows | `data`: logic |
| `func_dustcloud` | 17 | a particle volume of dust clouds | `dropped`: effects, as func_dustmotes |
| `func_physbox_multiplayer` | 17 | the networked physbox; as func_physbox | `world` |
| `info_node` | 17 | a ground navigation node of the original AI | `data` |
| `func_rot_button` | 15 | a rotating button (a lever, a valve): turns `distance` degrees, fires OnPressed | `mover` |
| `game_score` | 15 | adds score by input | `data`: logic |
| `game_ui` | 15 | takes a player's controls for logic | `data` |
| `logic_branch` | 15 | a boolean switch | `data`: logic |
| `point_tesla` | 15 | electric arcs | `point`: an effect position |
| `env_embers` | 14 | a particle volume of embers | `dropped`: effects |
| `func_conveyor` | 14 | a conveyor belt: carries what stands on it along `movedir` at `speed`, the brush itself stays | `mover` |
| `point_clientcommand` | 14 | runs a command on a client | `dropped`: refused for the same reason |
| `prop_ragdoll` | 14 | a placed ragdoll (a corpse); models are studied | `point` |
| `trigger_soundscape` | 14 | switches the ambient soundscape in a volume | `data`: sound logic |
| `env_soundscape_triggerable` | 13 | a soundscape switched by triggers | `point` |
| `func_monitor` | 13 | a brush showing a camera's view; drawn as its plain surface | `world` |
| `func_precipitation` | 13 | rain or snow in a volume; kept so a game can make weather (its bounds are the model's) | `data` |
| `func_wall` | 13 | a brush entity that is just a wall | `world` |
| `func_occluder` | 12 | a visibility occluder; the renderer here culls on its own | `dropped` |
| `func_smokevolume` | 12 | a particle volume of smoke | `dropped`: effects, as func_dustmotes |
| `func_tanktrain` | 12 | a drivable tank train; as func_tracktrain | `mover` |
| `trigger_gravity` | 12 | scales gravity for a body inside | `volume` |
| `info_landmark` | 11 | a level-change landmark; kept as a named point | `point` |
| `info_player_human` | 11 | a survivors' spawn of a zombie mode | `point` |
| `info_player_zombie` | 11 | a zombies' spawn of a zombie mode | `point` |
| `phys_hinge` | 11 | a hinge constraint | `data`: nothing is simulated |
| `color_correction` | 10 | a colour grade with falloff; the grade's lookup file is the source's own and never shipped, its presence is kept | `point` |
| `env_bubbles` | 10 | a particle volume of bubbles | `dropped`: effects |
| `filter_activator_class` | 10 | passes activators by class | `data`: logic |
| `func_bomb_target` | 10 | a bomb site of a round-based shooter; another game's objective | `dropped` |
| `func_reflective_glass` | 10 | a mirror-like glass brush; drawn as glass | `world` |
| `env_wind` | 9 | wind for trees and particles | `point` |
| `light_dynamic` | 9 | a light that may move or switch at run time | `point` |
| `phys_ballsocket` | 9 | a ball joint | `data`: nothing is simulated |
| `func_fish_pool` | 8 | spawns fish models; models are studied, not imported | `dropped` |
| `env_physexplosion` | 7 | a physics push by input | `data`: logic |
| `filter_multi` | 7 | combines filters | `data`: logic |
| `func_clip_vphysics` | 7 | blocks physics objects and never a player; nothing here is simulated | `dropped` |
| `zombiegasses` | 7 | a mode script's zombie gas spawner | `data` |
| `func_lod` | 6 | a brush that fades out with distance; drawn always | `world` |
| `info_node_hint` | 6 | a navigation hint | `data` |
| `phys_keepupright` | 6 | keeps an object upright | `data`: nothing is simulated |
| `env_firesource` | 5 | what lights fires nearby | `data`: logic |
| `env_projectedtexture` | 5 | a light projecting a texture (a flashlight, a window's shadow) | `point` |
| `env_splash` | 5 | a water splash | `point`: an effect position |
| `info_camera_link` | 5 | links a camera to a monitor | `data`: logic |
| `info_node_air_hint` | 5 | an air navigation hint | `data` |
| `logic_waves` | 5 | a mode script's wave control | `data` |
| `env_global` | 4 | sets a global state | `data`: logic |
| `func_useableladder` | 4 | a ladder climbed by using it; as func_ladder between its two points | `volume` |
| `info_hint` | 4 | an AI hint | `data` |
| `info_ladder_dismount` | 4 | where a ladder is left | `point` |
| `info_player_deathmatch` | 4 | a spawn | `point` |
| `info_player_zombie_boss` | 4 | a boss zombie's spawn | `point` |
| `item_defuser` | 4 | a bomb defuser of a round-based shooter | `dropped` |
| `lua_run` | 4 | runs a script on the server | `dropped`: refused, never executed |
| `npc_template_maker` | 4 | spawns monsters from a template | `data`: the game's director decides monsters |
| `phys_constraint` | 4 | a fixed constraint | `data`: nothing is simulated |
| `phys_motor` | 4 | spins a physics object | `data`: nothing is simulated |
| `point_hurt` | 4 | hurts in a radius by input | `data`: logic |
| `point_teleport` | 4 | teleports an entity by input | `data`: logic |
| `ai_changetarget` | 3 | AI logic | `data` |
| `aiscripted_schedule` | 3 | AI logic | `data` |
| `env_blood` | 3 | sprays blood by input | `data`: logic |
| `env_screenoverlay` | 3 | puts an overlay on the screen | `data`: logic; its material is never shipped |
| `env_texturetoggle` | 3 | switches a brush's texture frame | `data`: logic |
| `game_weapon_manager` | 3 | caps dropped weapons; the game owns weapons | `dropped` |
| `info_node_air` | 3 | an air navigation node | `data` |
| `logic_measure_movement` | 3 | copies one entity's movement to another | `data`: logic |
| `npc_enemyfinder` | 3 | AI logic | `data` |
| `phys_lengthconstraint` | 3 | a rope-length constraint | `data`: nothing is simulated |
| `prop_vehicle_airboat` | 3 | a drivable vehicle | `data`: a game's own vehicles replace it |
| `trigger_look` | 3 | fires when a player looks at a target | `data`: logic |
| `color_correction_volume` | 2 | a colour grade inside a volume; its lookup file is the source's own and never shipped | `data` |
| `env_citadel_energy_core` | 2 | an energy effect | `point`: an effect position |
| `env_muzzleflash` | 2 | a muzzle flash | `point`: an effect position |
| `env_particlelight` | 2 | a light for particles | `point`: an effect position |
| `env_shooter` | 2 | throws gibs by input | `data`: logic |
| `env_soundscape_proxy` | 2 | a soundscape proxy | `point` |
| `func_hostage_rescue` | 2 | a hostage rescue zone; another game's objective | `dropped` |
| `func_water` | 2 | older water brush; swum in | `volume` |
| `hostage_entity` | 2 | a hostage of a round-based shooter; another game's objective | `dropped` |
| `info_player_phx_spectator` | 2 | a spectator spawn of a mode script | `point` |
| `info_player_redeemed` | 2 | a returned survivor's spawn | `point` |
| `logic_gamerules` | 2 | a mode script's rules entity | `data` |
| `logic_winlose` | 2 | a mode script's round end | `data` |
| `math_colorblend` | 2 | maps a value to a colour | `data`: logic |
| `multi_manager` | 2 | the older multi-output relay | `data`: logic |
| `phys_constraintsystem` | 2 | groups constraints | `data`: nothing is simulated |
| `phys_ragdollconstraint` | 2 | ties a ragdoll | `data`: nothing is simulated |
| `point_devshot_camera` | 2 | a developer screenshot camera | `dropped` |
| `prop_vehicle_jeep` | 2 | a drivable vehicle | `data` |
| `scripted_sequence` | 2 | a scripted animation | `data`: logic |
| `trigger_vphysics_motion` | 2 | applies forces to physics objects inside | `data`: props are not simulated |
| `env_ar2explosion` | 1 | an explosion effect by input | `data`: logic |
| `env_dustpuff` | 1 | a dust puff | `point`: an effect position |
| `env_fire_trail` | 1 | a fire trail | `point`: an effect position |
| `env_headcrabcanister` | 1 | a scripted canister drop | `data`: logic |
| `env_microphone` | 1 | relays sound to a speaker | `data`: logic |
| `env_smoketrail` | 1 | a smoke trail | `point`: an effect position |
| `env_viewpunch` | 1 | kicks the view | `data`: logic |
| `func_Detail` | 1 | a mis-cased func_detail left as an entity by one mapper; drawn and solid | `world` |
| `func_detail_blocker` | 1 | stops detail sprites (grass) in a volume; no detail sprites are converted | `dropped` |
| `func_precipitation_blocker` | 1 | stops precipitation in a volume; no weather is converted | `dropped` |
| `func_status` | 1 | a mode script's status display brush; drawn and solid | `world` |
| `func_tanklaser` | 1 | a mounted laser's brush; as func_tankpulselaser | `world` |
| `func_tankpulselaser` | 1 | a mounted gun's brush; drawn and solid, it does not fire | `world` |
| `func_tankrocket` | 1 | a mounted rocket launcher's brush; as func_tankpulselaser | `world` |
| `func_x_animator_brush` | 1 | a mode script's animated brush; drawn and solid where compiled | `world` |
| `gmod_player_start` | 1 | a sandbox's spawn | `point` |
| `info_mass_center` | 1 | a physics object's mass centre | `data` |
| `info_node_link` | 1 | a navigation link | `data` |
| `info_overlay_accessor` | 1 | lets logic reach an overlay | `data` |
| `info_player_hunters` | 1 | the seekers' spawn of a hide-and-seek mode | `point` |
| `info_player_props` | 1 | the hiders' spawn of a hide-and-seek mode | `point` |
| `info_player_undead` | 1 | a zombies' spawn | `point` |
| `ins_spawnpoint` | 1 | a tactical mode's spawn | `point` |
| `item_nvgs` | 1 | night vision of a round-based shooter | `dropped` |
| `logic_beats` | 1 | a mode script's music beats | `data` |
| `logic_branch_listener` | 1 | watches branches | `data`: logic |
| `logic_collision_pair` | 1 | disables collision between two objects | `data`: logic |
| `momentary_rot_button` | 1 | a wheel held to turn; as func_rot_button | `mover` |
| `npc_maker` | 1 | spawns monsters | `data`: as npc_template_maker |
| `phys_magnet` | 1 | a physics magnet | `data`: nothing is simulated |
| `phys_pulleyconstraint` | 1 | a pulley | `data`: nothing is simulated |
| `point_worldhint` | 1 | a hint shown to a player | `data` |
| `point_zsmessage` | 1 | a mode script's message point | `data` |
| `prop_vehicle_crane` | 1 | a drivable crane | `data` |
| `prop_vehicle_prisoner_pod` | 1 | a seat that carries a player | `data` |
| `trigger_apply_impulse` | 1 | pushes a body once by input | `data`: logic |
| `trigger_autosave` | 1 | saves a single-player game; no saves here | `dropped` |
| `trigger_remove` | 1 | removes entities that enter | `data`: logic |
| `env_cubemap` |  | a reflection probe position (also the cubemaps lump) | `point` |
| `func_detail` |  | detail brushes; compiled into the world by the map compiler, so never seen as an entity | `world` |
| `func_ladder` |  | a climbable volume | `volume` |
| `func_plat` |  | an elevator platform that rises `height` when stood on | `mover` |
| `func_platrot` |  | a platform that rises and turns; as func_plat | `mover` |
| `func_train` |  | the older path train; as func_tracktrain | `mover` |
| `func_wall_illusionary` |  | the older name of func_illusionary | `drawn` |
| `info_overlay` |  | a decal laid on brush faces (the overlays lump) | `point` |
| `prop_static` | 0 | a placed model (the static props game lump); models are studied, a game places its own | `point` |

| Prefix | Map uses (classes) | What it is | What it becomes |
| --- | --- | --- | --- |
| `weapon_*` | 732 (64) | a weapon lying in the map; the game decides what stands there | `point` |
| `item_*` | 36 (14) | an item lying in the map (health, armour, ammunition) | `point` |
| `ammo_*` | 16 (7) | ammunition lying in the map | `point` |
| `npc_*` | 9 (5) | a placed monster or person | `data`: the game's director decides monsters |
| `info_node*` | 0 (0) | a navigation node of the original AI | `data` |
| `info_player_*` | 0 (0) | a spawn of some mode | `point` |
| `info_zs*` | 2 (1) | a mode script's navigation point | `data` |
| `info_sigil*` | 8 (2) | a mode script's objective point | `data` |
| `logic_*` | 0 (0) | map logic | `data` |
| `filter_*` | 0 (0) | a filter | `data`: logic |
| `math_*` | 0 (0) | a value | `data`: logic |
| `phys_*` | 0 (0) | a physics constraint | `data`: nothing is simulated |
| `prop_vehicle*` | 0 (0) | a vehicle | `data` |
| `ttt_*` | 7 (5) | a mode script's own entity | `data` |
| `ph_*` | 5 (4) | a mode script's own entity | `data` |
| `wlv_*` | 1 (1) | a mode script's weapon | `point` |
| `trigger_*` | 0 (0) | a trigger | `data`: logic |
| `env_*` | 0 (0) | an effect or screen logic | `data` |
| `point_*` | 0 (0) | point logic | `data` |
