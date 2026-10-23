# Entity classes, and what the importer makes of each

Every entity class found in 200 community maps (measured 2026-10-23 over the 105 readable maps in the lossless store, 296 classes counting `prop_static`), what it is in the original engine, and what `dotbsp` makes of it. The table is written from `dotbsp/classes.py` by `python3 -I tools/bsp/bsp.py classes --markdown <maps...>`, so a change goes there and this file is regenerated, never edited by hand. `bsp.py mesh` prints what became of every entity of the map it converts and fails on a class with no row and no prefix rule.

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

| Class | Maps | What it is | What it becomes | Component |
| --- | --- | --- | --- | --- |
| `worldspawn` | 105 | the world: every compiled brush, func_detail included, and the map's sky name and keys | `world` |  |
| `light` | 95 | a point light: `_light` colour and brightness | `point` |  |
| `prop_static` | 87 | a placed model (the static props game lump); models are studied, a game places its own | `point` |  |
| `func_breakable` | 83 | a brush that breaks when damaged; drawn and solid where it stands | `world`: listed in the manifest's `breakables`; an all-glass one is a DotMapGlass, any other breaking is the game's (ZZ: barricades) |  |
| `light_environment` | 82 | the sun and sky light of an outdoor map: direction, colour, ambient | `point` |  |
| `ambient_generic` | 81 | a sound played at a point, looped or on input | `point` |  |
| `func_button` | 77 | a button: pressed by use or touch, moves along `movedir` by its size minus `lip`, fires OnPressed | `mover` |  |
| `water_lod_control` | 72 | how far cheap water starts; kept as a look hint | `point` |  |
| `info_player_terrorist` | 67 | a spawn of one team | `point` |  |
| `func_door` | 65 | a sliding door: moves along `movedir` by its size minus `lip` at `speed`, opened by a touch, a use or an input | `mover` |  |
| `infodecal` | 65 | a decal (a stain, a sign) projected on a surface; its material is the source's, replaced like any texture | `point` |  |
| `info_player_counterterrorist` | 64 | a spawn of the other team | `point` |  |
| `prop_dynamic` | 64 | a placed model that may animate; models are studied | `point` |  |
| `prop_physics` | 63 | a placed physics model (a barrel, a crate); models are studied | `point` |  |
| `trigger_hurt` | 61 | damages a body inside by `damage` a second (pits, lava, crushers) | `volume` |  |
| `trigger_teleport` | 57 | sends a body that enters to its `target` destination | `volume` |  |
| `func_rotating` | 56 | a brush that spins about one axis at `maxspeed` (fans, wheels, rotating platforms) | `mover` |  |
| `light_spot` | 55 | a spot light: cone, direction, colour | `point` |  |
| `func_illusionary` | 53 | a brush that is drawn and never solid (foliage, light shafts, fake walls); one painted with water is water | `drawn` |  |
| `logic_auto` | 53 | fires outputs when the map starts | `data`: logic | `DotMapAuto` |
| `func_door_rotating` | 52 | a hinged door: turns `distance` degrees about its origin's axis at `speed` | `mover` |  |
| `trigger_multiple` | 52 | fires outputs each time a body enters, then waits `wait` seconds | `volume` | `DotMapTrigger` |
| `trigger_push` | 50 | pushes a body inside along `pushdir` at `speed` | `volume` |  |
| `func_physbox` | 48 | a brush simulated as a physics object; drawn and solid where it rests, not simulated | `world` |  |
| `info_player_start` | 48 | a spawn | `point` |  |
| `info_target` | 48 | a named point other entities aim at | `point` |  |
| `prop_physics_override` | 48 | as prop_physics | `point` |  |
| `info_teleport_destination` | 47 | where a teleport sends a body | `point` |  |
| `trigger_once` | 46 | fires outputs the first time a body enters | `volume` | `DotMapTrigger` |
| `env_sprite` | 45 | a glow sprite (a lamp's halo) | `point` |  |
| `func_brush` | 45 | a toggleable brush; drawn and solid unless `Solidity` 1, rendermode 10 or StartDisabled | `world`: toggling is the map's logic |  |
| `info_ladder` | 44 | a ladder volume as a point entity (mins and maxs keys) | `point` |  |
| `logic_timer` | 43 | fires outputs on a timer | `data`: logic | `DotMapTimer` |
| `sky_camera` | 42 | the 3D skybox's camera: where the miniature backdrop is and its scale (`mesh.skybox_of`) | `point` |  |
| `path_track` | 41 | a corner of a train's path; read by the movers for func_tracktrain | `data` |  |
| `point_spotlight` | 41 | a visible light beam and its light | `point` |  |
| `prop_physics_multiplayer` | 41 | as prop_physics | `point` |  |
| `func_tracktrain` | 37 | a train that runs along `path_track` corners (lifts, boats, trucks); the path is in `movers` | `mover` |  |
| `env_fog_controller` | 35 | distance fog: colour, start and end | `point` |  |
| `move_rope` | 35 | a rope or cable's first point, with its look | `point` |  |
| `point_template` | 35 | a template that spawns copies of entities | `data`: logic | `DotMapTemplate` |
| `prop_door_rotating` | 35 | a model door that swings; converted like func_door_rotating with its model studied | `mover` |  |
| `env_explosion` | 34 | an explosion by input | `data`: logic with a position |  |
| `prop_dynamic_override` | 34 | as prop_dynamic | `point` |  |
| `env_spark` | 32 | sparks | `point`: an effect position |  |
| `point_servercommand` | 31 | runs a server console command | `dropped`: a map does not run commands on this server | `DotMapServerCommand` |
| `env_fire` | 29 | a fire that burns and hurts | `point`: an effect position |  |
| `game_player_equip` | 29 | gives players weapons on spawn | `data`: the game decides kits |  |
| `env_soundscape` | 28 | an ambient soundscape in reach | `point` |  |
| `env_spritetrail` | 28 | a sprite trail on a moving thing | `point`: an effect position |  |
| `logic_relay` | 28 | relays inputs to outputs | `data`: logic | `DotMapRelay` |
| `env_steam` | 27 | a steam jet | `point`: an effect position a game may fill |  |
| `func_dustmotes` | 27 | a particle volume of floating dust | `dropped`: effects, left to a game (an open item for the look) |  |
| `env_laser` | 26 | a laser beam that may hurt | `point`: an effect |  |
| `logic_case` | 26 | picks an output by value | `data`: logic | `DotMapCase` |
| `func_areaportal` | 25 | a visibility portal (a door closes it); the renderer here culls on its own | `dropped` |  |
| `point_viewcontrol` | 25 | a scripted camera | `data`: logic |  |
| `shadow_control` | 25 | the direction and colour of dynamic shadows | `point` |  |
| `filter_activator_team` | 24 | passes activators by team | `data`: logic |  |
| `func_movelinear` | 24 | a brush moved between two positions by inputs (lifts, crushers): `movedir`, `movedistance`, `speed` | `mover` |  |
| `func_buyzone` | 23 | where a round-based shooter's team may buy weapons; no shop here | `dropped` |  |
| `math_counter` | 22 | a counter with outputs | `data`: logic | `DotMapCounter` |
| `keyframe_rope` | 21 | a rope's next point | `point` |  |
| `env_shake` | 19 | shakes the screen | `data`: logic |  |
| `env_sun` | 19 | the sun's sprite in the sky: its direction and colour | `point` |  |
| `player_speedmod` | 19 | changes a player's speed by input | `data`: logic |  |
| `env_tonemap_controller` | 17 | exposure limits and bloom | `point` |  |
| `info_node` | 17 | a ground navigation node of the original AI | `data` |  |
| `env_smokestack` | 16 | a smoke column | `point`: an effect position |  |
| `func_areaportalwindow` | 16 | a portal that fades with distance; as func_areaportal | `dropped` |  |
| `filter_activator_name` | 15 | passes activators by name | `data`: logic |  |
| `func_wall_toggle` | 15 | a wall an input shows or hides; drawn and solid unless it starts off (spawnflag 1) | `world` |  |
| `func_water_analog` | 15 | water as a movable brush; swum in, it does not move here | `volume` |  |
| `logic_compare` | 14 | compares a value | `data`: logic | `DotMapCompare` |
| `env_fade` | 13 | fades the screen by input | `data`: logic |  |
| `phys_thruster` | 13 | pushes a physics object | `data`: nothing is simulated |  |
| `func_breakable_surf` | 12 | breakable glass panes; drawn and solid | `world`: listed in the manifest's `breakables`; DotMapGlass breaks it |  |
| `game_score` | 12 | adds score by input | `data`: logic |  |
| `prop_ragdoll` | 12 | a placed ragdoll (a corpse); models are studied | `point` |  |
| `env_entity_maker` | 11 | spawns a template at a point | `data`: logic |  |
| `env_lightglow` | 11 | a glow seen around a light | `point` |  |
| `func_reflective_glass` | 11 | a mirror-like glass brush; drawn as glass | `world` |  |
| `info_player_human` | 11 | a survivors' spawn of a zombie mode | `point` |  |
| `info_player_zombie` | 11 | a zombies' spawn of a zombie mode | `point` |  |
| `func_physbox_multiplayer` | 10 | the networked physbox; as func_physbox | `world` |  |
| `func_tanktrain` | 10 | a drivable tank train; as func_tracktrain | `mover` |  |
| `game_text` | 10 | shows text on screens | `data`: logic; its text is kept |  |
| `phys_hinge` | 10 | a hinge constraint | `data`: nothing is simulated |  |
| `color_correction` | 9 | a colour grade with falloff; the grade's lookup file is the source's own and never shipped, its presence is kept | `point` |  |
| `func_dustcloud` | 9 | a particle volume of dust clouds | `dropped`: effects, as func_dustmotes |  |
| `func_occluder` | 9 | a visibility occluder; the renderer here culls on its own | `dropped` |  |
| `game_ui` | 9 | takes a player's controls for logic | `data` |  |
| `light_dynamic` | 9 | a light that may move or switch at run time | `point` |  |
| `point_camera` | 9 | a camera a monitor shows | `data`: logic |  |
| `env_beam` | 8 | a beam between two points | `point`: an effect |  |
| `env_hudhint` | 8 | a hint on the screen | `data`: logic |  |
| `env_wind` | 8 | wind for trees and particles | `point` |  |
| `filter_damage_type` | 8 | passes damage by type | `data`: logic |  |
| `func_wall` | 8 | a brush entity that is just a wall | `world` |  |
| `logic_branch` | 8 | a boolean switch | `data`: logic | `DotMapBranch` |
| `point_tesla` | 8 | electric arcs | `point`: an effect position |  |
| `env_bubbles` | 7 | a particle volume of bubbles | `dropped`: effects |  |
| `func_precipitation` | 7 | rain or snow in a volume; kept so a game can make weather (its bounds are the model's) | `data` |  |
| `func_smokevolume` | 7 | a particle volume of smoke | `dropped`: effects, as func_dustmotes |  |
| `player_weaponstrip` | 7 | takes weapons by input | `data`: logic |  |
| `trigger_soundscape` | 7 | switches the ambient soundscape in a volume | `data`: sound logic |  |
| `zombiegasses` | 7 | a mode script's zombie gas spawner | `data` |  |
| `env_embers` | 6 | a particle volume of embers | `dropped`: effects |  |
| `env_soundscape_triggerable` | 6 | a soundscape switched by triggers | `point` |  |
| `func_clip_vphysics` | 6 | blocks physics objects and never a player; nothing here is simulated | `dropped` |  |
| `func_fish_pool` | 6 | spawns fish models; models are studied, not imported | `dropped` |  |
| `info_node_hint` | 6 | a navigation hint | `data` |  |
| `info_particle_system` | 6 | a particle effect; its system is the source's own, so a position and a name | `point` |  |
| `phys_ballsocket` | 6 | a ball joint | `data`: nothing is simulated |  |
| `env_firesource` | 5 | what lights fires nearby | `data`: logic |  |
| `env_physexplosion` | 5 | a physics push by input | `data`: logic |  |
| `func_monitor` | 5 | a brush showing a camera's view; drawn as its plain surface | `world` |  |
| `info_node_air_hint` | 5 | an air navigation hint | `data` |  |
| `logic_waves` | 5 | a mode script's wave control | `data` |  |
| `trigger_gravity` | 5 | scales gravity for a body inside | `volume` |  |
| `env_splash` | 4 | a water splash | `point`: an effect position |  |
| `func_lod` | 4 | a brush that fades out with distance; drawn always | `world` |  |
| `func_rot_button` | 4 | a rotating button (a lever, a valve): turns `distance` degrees, fires OnPressed | `mover` |  |
| `func_useableladder` | 4 | a ladder climbed by using it; as func_ladder between its two points | `volume` |  |
| `info_hint` | 4 | an AI hint | `data` |  |
| `info_ladder_dismount` | 4 | where a ladder is left | `point` |  |
| `info_player_deathmatch` | 4 | a spawn | `point` |  |
| `info_player_zombie_boss` | 4 | a boss zombie's spawn | `point` |  |
| `lua_run` | 4 | runs a script on the server | `data`: never executed; template-matched snippets become whitelisted operations, the rest are reported (`DotMapScript`) |  |
| `npc_template_maker` | 4 | spawns monsters from a template | `data`: the game's director decides monsters |  |
| `aiscripted_schedule` | 3 | AI logic | `data` |  |
| `env_blood` | 3 | sprays blood by input | `data`: logic |  |
| `env_projectedtexture` | 3 | a light projecting a texture (a flashlight, a window's shadow) | `point` |  |
| `info_camera_link` | 3 | links a camera to a monitor | `data`: logic |  |
| `info_node_air` | 3 | an air navigation node | `data` |  |
| `npc_enemyfinder` | 3 | AI logic | `data` |  |
| `phys_keepupright` | 3 | keeps an object upright | `data`: nothing is simulated |  |
| `point_hurt` | 3 | hurts in a radius by input | `data`: logic |  |
| `prop_vehicle_airboat` | 3 | a drivable vehicle | `data`: a game's own vehicles replace it |  |
| `ai_changetarget` | 2 | AI logic | `data` |  |
| `color_correction_volume` | 2 | a colour grade inside a volume; its lookup file is the source's own and never shipped | `data` |  |
| `env_citadel_energy_core` | 2 | an energy effect | `point`: an effect position |  |
| `env_screenoverlay` | 2 | puts an overlay on the screen | `data`: logic; its material is never shipped |  |
| `env_texturetoggle` | 2 | switches a brush's texture frame | `data`: logic |  |
| `func_bomb_target` | 2 | a bomb site of a round-based shooter; another game's objective | `dropped` |  |
| `func_hostage_rescue` | 2 | a hostage rescue zone; another game's objective | `dropped` |  |
| `hostage_entity` | 2 | a hostage of a round-based shooter; another game's objective | `dropped` |  |
| `info_player_phx_spectator` | 2 | a spectator spawn of a mode script | `point` |  |
| `info_player_redeemed` | 2 | a returned survivor's spawn | `point` |  |
| `logic_gamerules` | 2 | a mode script's rules entity | `data` |  |
| `logic_winlose` | 2 | a mode script's round end | `data` |  |
| `math_colorblend` | 2 | maps a value to a colour | `data`: logic | `DotMapColorBlend` |
| `phys_constraint` | 2 | a fixed constraint | `data`: nothing is simulated |  |
| `phys_lengthconstraint` | 2 | a rope-length constraint | `data`: nothing is simulated |  |
| `phys_ragdollconstraint` | 2 | ties a ragdoll | `data`: nothing is simulated |  |
| `point_clientcommand` | 2 | runs a command on a client | `dropped`: refused for the same reason | `DotMapServerCommand` |
| `prop_vehicle_jeep` | 2 | a drivable vehicle | `data` |  |
| `scripted_sequence` | 2 | a scripted animation | `data`: logic |  |
| `trigger_look` | 2 | fires when a player looks at a target | `data`: logic |  |
| `env_ar2explosion` | 1 | an explosion effect by input | `data`: logic |  |
| `env_dustpuff` | 1 | a dust puff | `point`: an effect position |  |
| `env_global` | 1 | sets a global state | `data`: logic | `DotMapGlobal` |
| `env_headcrabcanister` | 1 | a scripted canister drop | `data`: logic |  |
| `env_microphone` | 1 | relays sound to a speaker | `data`: logic |  |
| `env_muzzleflash` | 1 | a muzzle flash | `point`: an effect position |  |
| `env_particlelight` | 1 | a light for particles | `point`: an effect position |  |
| `env_shooter` | 1 | throws gibs by input | `data`: logic |  |
| `env_viewpunch` | 1 | kicks the view | `data`: logic |  |
| `func_Detail` | 1 | a mis-cased func_detail left as an entity by one mapper; drawn and solid | `world` |  |
| `func_conveyor` | 1 | a conveyor belt: carries what stands on it along `movedir` at `speed`, the brush itself stays | `mover` |  |
| `func_detail_blocker` | 1 | stops detail sprites (grass) in a volume; no detail sprites are converted | `dropped` |  |
| `func_precipitation_blocker` | 1 | stops precipitation in a volume; no weather is converted | `dropped` |  |
| `func_status` | 1 | a mode script's status display brush; drawn and solid | `world` |  |
| `func_tanklaser` | 1 | a mounted laser's brush; as func_tankpulselaser | `world` |  |
| `func_tankpulselaser` | 1 | a mounted gun's brush; drawn and solid, it does not fire | `world` |  |
| `func_tankrocket` | 1 | a mounted rocket launcher's brush; as func_tankpulselaser | `world` |  |
| `func_x_animator_brush` | 1 | a mode script's animated brush; drawn and solid where compiled | `world` |  |
| `gmod_player_start` | 1 | a sandbox's spawn | `point` |  |
| `info_landmark` | 1 | a level-change landmark; kept as a named point | `point` |  |
| `info_mass_center` | 1 | a physics object's mass centre | `data` |  |
| `info_node_link` | 1 | a navigation link | `data` |  |
| `info_overlay_accessor` | 1 | lets logic reach an overlay | `data` |  |
| `info_player_hunters` | 1 | the seekers' spawn of a hide-and-seek mode | `point` |  |
| `info_player_props` | 1 | the hiders' spawn of a hide-and-seek mode | `point` |  |
| `info_player_undead` | 1 | a zombies' spawn | `point` |  |
| `ins_spawnpoint` | 1 | a tactical mode's spawn | `point` |  |
| `logic_beats` | 1 | a mode script's music beats | `data` |  |
| `logic_branch_listener` | 1 | watches branches | `data`: logic |  |
| `logic_collision_pair` | 1 | disables collision between two objects | `data`: logic |  |
| `logic_measure_movement` | 1 | copies one entity's movement to another | `data`: logic | `DotMapMeasureMovement` |
| `npc_maker` | 1 | spawns monsters | `data`: as npc_template_maker |  |
| `phys_constraintsystem` | 1 | groups constraints | `data`: nothing is simulated |  |
| `phys_magnet` | 1 | a physics magnet | `data`: nothing is simulated |  |
| `phys_motor` | 1 | spins a physics object | `data`: nothing is simulated |  |
| `point_devshot_camera` | 1 | a developer screenshot camera | `dropped` |  |
| `point_worldhint` | 1 | a hint shown to a player | `data` |  |
| `point_zsmessage` | 1 | a mode script's message point | `data` |  |
| `prop_vehicle_crane` | 1 | a drivable crane | `data` |  |
| `prop_vehicle_prisoner_pod` | 1 | a seat that carries a player | `data` |  |
| `trigger_apply_impulse` | 1 | pushes a body once by input | `data`: logic |  |
| `trigger_autosave` | 1 | saves a single-player game; no saves here | `dropped` |  |
| `env_cubemap` |  | a reflection probe position (also the cubemaps lump) | `point` |  |
| `env_fire_trail` |  | a fire trail | `point`: an effect position |  |
| `env_smoketrail` |  | a smoke trail | `point`: an effect position |  |
| `env_soundscape_proxy` |  | a soundscape proxy | `point` |  |
| `filter_activator_class` |  | passes activators by class | `data`: logic |  |
| `filter_multi` |  | combines filters | `data`: logic |  |
| `func_detail` |  | detail brushes; compiled into the world by the map compiler, so never seen as an entity | `world` |  |
| `func_ladder` |  | a climbable volume | `volume` |  |
| `func_plat` |  | an elevator platform that rises `height` when stood on | `mover` |  |
| `func_platrot` |  | a platform that rises and turns; as func_plat | `mover` |  |
| `func_train` |  | the older path train; as func_tracktrain | `mover` |  |
| `func_wall_illusionary` |  | the older name of func_illusionary | `drawn` |  |
| `func_water` |  | older water brush; swum in | `volume` |  |
| `game_weapon_manager` |  | caps dropped weapons; the game owns weapons | `dropped` |  |
| `info_overlay` |  | a decal laid on brush faces (the overlays lump) | `point` |  |
| `item_defuser` |  | a bomb defuser of a round-based shooter | `dropped` |  |
| `item_nvgs` |  | night vision of a round-based shooter | `dropped` |  |
| `momentary_rot_button` |  | a wheel held to turn; as func_rot_button | `mover` |  |
| `multi_manager` |  | the older multi-output relay | `data`: logic |  |
| `phys_pulleyconstraint` |  | a pulley | `data`: nothing is simulated |  |
| `point_teleport` |  | teleports an entity by input | `data`: logic |  |
| `trigger_remove` |  | removes entities that enter | `data`: logic |  |
| `trigger_vphysics_motion` |  | applies forces to physics objects inside | `data`: props are not simulated |  |

| Prefix | Map uses (classes) | What it is | What it becomes |
| --- | --- | --- | --- |
| `weapon_*` | 228 (64) | a weapon lying in the map; the game decides what stands there | `point` |
| `item_*` | 34 (13) | an item lying in the map (health, armour, ammunition) | `point` |
| `ammo_*` | 0 (0) | ammunition lying in the map | `point` |
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
