"""Every entity class a community map uses, what it means, and what the importer makes of it.

One table, so a converter can say for every entity of a map what became of it, and so a class
nobody has decided about is a failure rather than something silently missing. `ROWS` holds the
classes surveyed over 200 maps (2026-10-21: the 98 under `inspirations/g2gfast` and every map
source under `~/mapsrc`, 318 classes); `PREFIXES` decides the long tails (`weapon_*`, `npc_*`)
so a new pistol does not need a row. `bsp.py classes --markdown` writes the table in
`docs/entity-classes.md` from here, with the survey's counts, so the document cannot drift.

What a class becomes (`TREATMENTS`):

- `world`: geometry, drawn and solid (`mesh.build`), like any world brush.
- `drawn`: geometry, drawn and never solid.
- `mover`: geometry that moves: a record in `movers.movers` (what moves, how far, how fast,
  what starts it) beside the drawn surfaces and hulls of its model.
- `volume`: a brush a body is affected by inside: `movers.volumes` (teleport, push, hurt,
  gravity, water, ladder), never drawn.
- `point`: a point entity converted to data a game uses as it is: spawns, lights, the sun,
  fog, the 3D sky, props, sounds, decals.
- `data`: kept verbatim in the intermediate's entity list for a game that wants it (map logic,
  paths, filters); nothing runs it, because a converter is not a scripting engine.
- `dropped`: deliberately left out, with the reason in the row.
"""

import collections

TREATMENTS = ("world", "drawn", "mover", "volume", "point", "data", "dropped")

# class, treatment, what it is in the original engine (and, after " -- ", why this treatment
# when it is not obvious).
_TABLE = """
worldspawn|world|the world: every compiled brush, func_detail included, and the map's sky name and keys
func_detail|world|detail brushes; compiled into the world by the map compiler, so never seen as an entity
func_wall|world|a brush entity that is just a wall
func_brush|world|a toggleable brush; drawn and solid unless `Solidity` 1, rendermode 10 or StartDisabled -- toggling is the map's logic
func_wall_toggle|world|a wall an input shows or hides; drawn and solid unless it starts off (spawnflag 1)
func_breakable|world|a brush that breaks when damaged; drawn and solid where it stands -- breaking is the game's (ZZ: barricades)
func_breakable_surf|world|breakable glass panes; drawn and solid
func_physbox|world|a brush simulated as a physics object; drawn and solid where it rests, not simulated
func_physbox_multiplayer|world|the networked physbox; as func_physbox
func_monitor|world|a brush showing a camera's view; drawn as its plain surface
func_reflective_glass|world|a mirror-like glass brush; drawn as glass
func_lod|world|a brush that fades out with distance; drawn always
func_Detail|world|a mis-cased func_detail left as an entity by one mapper; drawn and solid
func_status|world|a mode script's status display brush; drawn and solid
func_x_animator_brush|world|a mode script's animated brush; drawn and solid where compiled
func_tankpulselaser|world|a mounted gun's brush; drawn and solid, it does not fire
func_tankrocket|world|a mounted rocket launcher's brush; as func_tankpulselaser
func_tanklaser|world|a mounted laser's brush; as func_tankpulselaser
func_illusionary|drawn|a brush that is drawn and never solid (foliage, light shafts, fake walls); one painted with water is water
func_wall_illusionary|drawn|the older name of func_illusionary
func_door|mover|a sliding door: moves along `movedir` by its size minus `lip` at `speed`, opened by a touch, a use or an input
func_door_rotating|mover|a hinged door: turns `distance` degrees about its origin's axis at `speed`
func_movelinear|mover|a brush moved between two positions by inputs (lifts, crushers): `movedir`, `movedistance`, `speed`
func_button|mover|a button: pressed by use or touch, moves along `movedir` by its size minus `lip`, fires OnPressed
func_rot_button|mover|a rotating button (a lever, a valve): turns `distance` degrees, fires OnPressed
momentary_rot_button|mover|a wheel held to turn; as func_rot_button
func_rotating|mover|a brush that spins about one axis at `maxspeed` (fans, wheels, rotating platforms)
func_tracktrain|mover|a train that runs along `path_track` corners (lifts, boats, trucks); the path is in `movers`
func_tanktrain|mover|a drivable tank train; as func_tracktrain
func_train|mover|the older path train; as func_tracktrain
func_plat|mover|an elevator platform that rises `height` when stood on
func_platrot|mover|a platform that rises and turns; as func_plat
func_conveyor|mover|a conveyor belt: carries what stands on it along `movedir` at `speed`, the brush itself stays
trigger_teleport|volume|sends a body that enters to its `target` destination
trigger_push|volume|pushes a body inside along `pushdir` at `speed`
trigger_hurt|volume|damages a body inside by `damage` a second (pits, lava, crushers)
trigger_gravity|volume|scales gravity for a body inside
func_water_analog|volume|water as a movable brush; swum in, it does not move here
func_water|volume|older water brush; swum in
func_ladder|volume|a climbable volume
func_useableladder|volume|a ladder climbed by using it; as func_ladder between its two points
trigger_multiple|volume|fires outputs each time a body enters, then waits `wait` seconds
trigger_once|volume|fires outputs the first time a body enters
trigger_look|data|fires when a player looks at a target -- logic
trigger_soundscape|data|switches the ambient soundscape in a volume -- sound logic
trigger_vphysics_motion|data|applies forces to physics objects inside -- props are not simulated
trigger_remove|data|removes entities that enter -- logic
trigger_autosave|dropped|saves a single-player game; no saves here
trigger_apply_impulse|data|pushes a body once by input -- logic
func_buyzone|dropped|where a round-based shooter's team may buy weapons; no shop here
func_bomb_target|dropped|a bomb site of a round-based shooter; another game's objective
func_hostage_rescue|dropped|a hostage rescue zone; another game's objective
func_areaportal|dropped|a visibility portal (a door closes it); the renderer here culls on its own
func_areaportalwindow|dropped|a portal that fades with distance; as func_areaportal
func_occluder|dropped|a visibility occluder; the renderer here culls on its own
func_clip_vphysics|dropped|blocks physics objects and never a player; nothing here is simulated
func_dustmotes|dropped|a particle volume of floating dust -- effects, left to a game (an open item for the look)
func_dustcloud|dropped|a particle volume of dust clouds -- effects, as func_dustmotes
func_smokevolume|dropped|a particle volume of smoke -- effects, as func_dustmotes
func_precipitation|data|rain or snow in a volume; kept so a game can make weather (its bounds are the model's)
func_precipitation_blocker|dropped|stops precipitation in a volume; no weather is converted
func_fish_pool|dropped|spawns fish models; models are studied, not imported
func_detail_blocker|dropped|stops detail sprites (grass) in a volume; no detail sprites are converted
env_embers|dropped|a particle volume of embers -- effects
env_bubbles|dropped|a particle volume of bubbles -- effects
color_correction_volume|data|a colour grade inside a volume; its lookup file is the source's own and never shipped
info_player_terrorist|point|a spawn of one team
info_player_counterterrorist|point|a spawn of the other team
info_player_start|point|a spawn
info_player_deathmatch|point|a spawn
info_player_human|point|a survivors' spawn of a zombie mode
info_player_zombie|point|a zombies' spawn of a zombie mode
info_player_zombie_boss|point|a boss zombie's spawn
info_player_undead|point|a zombies' spawn
info_player_redeemed|point|a returned survivor's spawn
info_player_hunters|point|the seekers' spawn of a hide-and-seek mode
info_player_props|point|the hiders' spawn of a hide-and-seek mode
info_player_phx_spectator|point|a spectator spawn of a mode script
gmod_player_start|point|a sandbox's spawn
ins_spawnpoint|point|a tactical mode's spawn
light|point|a point light: `_light` colour and brightness
light_spot|point|a spot light: cone, direction, colour
light_dynamic|point|a light that may move or switch at run time
light_environment|point|the sun and sky light of an outdoor map: direction, colour, ambient
env_sun|point|the sun's sprite in the sky: its direction and colour
shadow_control|point|the direction and colour of dynamic shadows
env_fog_controller|point|distance fog: colour, start and end
sky_camera|point|the 3D skybox's camera: where the miniature backdrop is and its scale (`mesh.skybox_of`)
env_tonemap_controller|point|exposure limits and bloom
color_correction|point|a colour grade with falloff; the grade's lookup file is the source's own and never shipped, its presence is kept
water_lod_control|point|how far cheap water starts; kept as a look hint
env_cubemap|point|a reflection probe position (also the cubemaps lump)
infodecal|point|a decal (a stain, a sign) projected on a surface; its material is the source's, replaced like any texture
info_overlay|point|a decal laid on brush faces (the overlays lump)
info_overlay_accessor|data|lets logic reach an overlay
env_sprite|point|a glow sprite (a lamp's halo)
env_lightglow|point|a glow seen around a light
point_spotlight|point|a visible light beam and its light
env_projectedtexture|point|a light projecting a texture (a flashlight, a window's shadow)
env_steam|point|a steam jet -- an effect position a game may fill
env_smokestack|point|a smoke column -- an effect position
env_fire|point|a fire that burns and hurts -- an effect position
env_firesource|data|what lights fires nearby -- logic
env_spark|point|sparks -- an effect position
env_splash|point|a water splash -- an effect position
info_particle_system|point|a particle effect; its system is the source's own, so a position and a name
env_smoketrail|point|a smoke trail -- an effect position
env_fire_trail|point|a fire trail -- an effect position
env_spritetrail|point|a sprite trail on a moving thing -- an effect position
env_beam|point|a beam between two points -- an effect
env_laser|point|a laser beam that may hurt -- an effect
point_tesla|point|electric arcs -- an effect position
env_dustpuff|point|a dust puff -- an effect position
env_muzzleflash|point|a muzzle flash -- an effect position
env_citadel_energy_core|point|an energy effect -- an effect position
env_particlelight|point|a light for particles -- an effect position
env_wind|point|wind for trees and particles
move_rope|point|a rope or cable's first point, with its look
keyframe_rope|point|a rope's next point
prop_static|point|a placed model (the static props game lump); models are studied, a game places its own
prop_dynamic|point|a placed model that may animate; models are studied
prop_dynamic_override|point|as prop_dynamic
prop_physics|point|a placed physics model (a barrel, a crate); models are studied
prop_physics_override|point|as prop_physics
prop_physics_multiplayer|point|as prop_physics
prop_ragdoll|point|a placed ragdoll (a corpse); models are studied
prop_door_rotating|mover|a model door that swings; converted like func_door_rotating with its model studied
ambient_generic|point|a sound played at a point, looped or on input
env_soundscape|point|an ambient soundscape in reach
env_soundscape_triggerable|point|a soundscape switched by triggers
env_soundscape_proxy|point|a soundscape proxy
env_microphone|data|relays sound to a speaker -- logic
info_teleport_destination|point|where a teleport sends a body
info_target|point|a named point other entities aim at
info_landmark|point|a level-change landmark; kept as a named point
info_ladder|point|a ladder volume as a point entity (mins and maxs keys)
info_ladder_dismount|point|where a ladder is left
info_node|data|a ground navigation node of the original AI
info_node_hint|data|a navigation hint
info_node_air|data|an air navigation node
info_node_air_hint|data|an air navigation hint
info_node_link|data|a navigation link
info_hint|data|an AI hint
info_mass_center|data|a physics object's mass centre
info_camera_link|data|links a camera to a monitor -- logic
point_viewcontrol|data|a scripted camera -- logic
point_camera|data|a camera a monitor shows -- logic
point_devshot_camera|dropped|a developer screenshot camera
point_template|data|a template that spawns copies of entities -- logic
env_entity_maker|data|spawns a template at a point -- logic
point_teleport|data|teleports an entity by input -- logic
point_hurt|data|hurts in a radius by input -- logic
point_servercommand|dropped|runs a server console command -- a map does not run commands on this server
point_clientcommand|dropped|runs a command on a client -- refused for the same reason
lua_run|dropped|runs a script on the server -- refused, never executed
point_worldhint|data|a hint shown to a player
point_zsmessage|data|a mode script's message point
logic_auto|data|fires outputs when the map starts -- logic
logic_relay|data|relays inputs to outputs -- logic
logic_timer|data|fires outputs on a timer -- logic
logic_case|data|picks an output by value -- logic
logic_compare|data|compares a value -- logic
logic_branch|data|a boolean switch -- logic
logic_branch_listener|data|watches branches -- logic
logic_measure_movement|data|copies one entity's movement to another -- logic
logic_collision_pair|data|disables collision between two objects -- logic
logic_gamerules|data|a mode script's rules entity
logic_winlose|data|a mode script's round end
logic_waves|data|a mode script's wave control
logic_beats|data|a mode script's music beats
math_counter|data|a counter with outputs -- logic
math_colorblend|data|maps a value to a colour -- logic
multi_manager|data|the older multi-output relay -- logic
filter_activator_name|data|passes activators by name -- logic
filter_activator_class|data|passes activators by class -- logic
filter_activator_team|data|passes activators by team -- logic
filter_damage_type|data|passes damage by type -- logic
filter_multi|data|combines filters -- logic
path_track|data|a corner of a train's path; read by the movers for func_tracktrain
game_player_equip|data|gives players weapons on spawn -- the game decides kits
game_weapon_manager|dropped|caps dropped weapons; the game owns weapons
player_weaponstrip|data|takes weapons by input -- logic
player_speedmod|data|changes a player's speed by input -- logic
game_text|data|shows text on screens -- logic; its text is kept
game_ui|data|takes a player's controls for logic
game_score|data|adds score by input -- logic
env_hudhint|data|a hint on the screen -- logic
env_fade|data|fades the screen by input -- logic
env_shake|data|shakes the screen -- logic
env_viewpunch|data|kicks the view -- logic
env_screenoverlay|data|puts an overlay on the screen -- logic; its material is never shipped
env_explosion|data|an explosion by input -- logic with a position
env_physexplosion|data|a physics push by input -- logic
env_ar2explosion|data|an explosion effect by input -- logic
env_shooter|data|throws gibs by input -- logic
env_blood|data|sprays blood by input -- logic
env_global|data|sets a global state -- logic
env_texturetoggle|data|switches a brush's texture frame -- logic
env_headcrabcanister|data|a scripted canister drop -- logic
phys_thruster|data|pushes a physics object -- nothing is simulated
phys_hinge|data|a hinge constraint -- nothing is simulated
phys_ballsocket|data|a ball joint -- nothing is simulated
phys_constraint|data|a fixed constraint -- nothing is simulated
phys_constraintsystem|data|groups constraints -- nothing is simulated
phys_lengthconstraint|data|a rope-length constraint -- nothing is simulated
phys_pulleyconstraint|data|a pulley -- nothing is simulated
phys_ragdollconstraint|data|ties a ragdoll -- nothing is simulated
phys_keepupright|data|keeps an object upright -- nothing is simulated
phys_motor|data|spins a physics object -- nothing is simulated
phys_magnet|data|a physics magnet -- nothing is simulated
prop_vehicle_airboat|data|a drivable vehicle -- a game's own vehicles replace it
prop_vehicle_jeep|data|a drivable vehicle
prop_vehicle_crane|data|a drivable crane
prop_vehicle_prisoner_pod|data|a seat that carries a player
hostage_entity|dropped|a hostage of a round-based shooter; another game's objective
item_defuser|dropped|a bomb defuser of a round-based shooter
item_nvgs|dropped|night vision of a round-based shooter
ai_changetarget|data|AI logic
aiscripted_schedule|data|AI logic
scripted_sequence|data|a scripted animation -- logic
npc_template_maker|data|spawns monsters from a template -- the game's director decides monsters
npc_maker|data|spawns monsters -- as npc_template_maker
npc_enemyfinder|data|AI logic
zombiegasses|data|a mode script's zombie gas spawner
""".strip()

ROWS = {}
for _line in _TABLE.splitlines():
    _c, _t, _m = _line.split("|", 2)
    assert _t in TREATMENTS, _line
    ROWS[_c] = (_t, _m)

# Long tails, longest prefix first. A class here gets its treatment without a row.
PREFIXES = (
    ("weapon_", "point", "a weapon lying in the map; the game decides what stands there"),
    ("item_", "point", "an item lying in the map (health, armour, ammunition)"),
    ("ammo_", "point", "ammunition lying in the map"),
    ("npc_", "data", "a placed monster or person -- the game's director decides monsters"),
    ("info_node", "data", "a navigation node of the original AI"),
    ("info_player_", "point", "a spawn of some mode"),
    ("info_zs", "data", "a mode script's navigation point"),
    ("info_sigil", "data", "a mode script's objective point"),
    ("logic_", "data", "map logic"),
    ("filter_", "data", "a filter -- logic"),
    ("math_", "data", "a value -- logic"),
    ("phys_", "data", "a physics constraint -- nothing is simulated"),
    ("prop_vehicle", "data", "a vehicle"),
    ("ttt_", "data", "a mode script's own entity"),
    ("ph_", "data", "a mode script's own entity"),
    ("wlv_", "point", "a mode script's weapon"),
    ("trigger_", "data", "a trigger -- logic"),
    ("env_", "data", "an effect or screen logic"),
    ("point_", "data", "point logic"),
)


def treatment(classname):
    """(treatment, meaning, 'row' | 'prefix' | None) of one class; None means undecided."""
    if classname in ROWS:
        t, m = ROWS[classname]
        return t, m, "row"
    for p, t, m in PREFIXES:
        if classname.startswith(p):
            return t, m, "prefix"
    return None, None, None


def report(bsp):
    """What became of every entity of a loaded map: {"by_treatment": {t: {class: n}},
    "unknown": {class: n}, "entities": n}. An unknown class is one nobody decided about."""
    by = collections.defaultdict(collections.Counter)
    unknown = collections.Counter()
    for e in bsp.entities:
        c = e.get("classname", "")
        t, _m, _how = treatment(c)
        if t is None:
            unknown[c] += 1
        else:
            by[t][c] += 1
    props = len(bsp.static_props())
    if props:
        by["point"]["prop_static"] += props
    return {"entities": len(bsp.entities), "unknown": dict(unknown),
            "by_treatment": {t: dict(sorted(by[t].items())) for t in TREATMENTS if by[t]}}


def markdown(survey=None):
    """The table as Markdown; `survey` is {class: maps} to add a count column."""
    out = ["| Class | Maps | What it is | What it becomes |", "| --- | --- | --- | --- |"]
    names = set(ROWS) | set(survey or ())
    order = sorted(names, key=lambda c: (-(survey or {}).get(c, 0), c))
    for c in order:
        t, m, how = treatment(c)
        if how == "prefix":
            continue                                   # the prefix rows below say these
        if t is None:
            t, m = "undecided", "no row: add one"
        what, _, why = m.partition(" -- ")
        becomes = "`%s`" % t + (": " + why if why else "")
        out.append("| `%s` | %s | %s | %s |" % (c, (survey or {}).get(c, ""), what, becomes))
    out += ["", "| Prefix | Map uses (classes) | What it is | What it becomes |", "| --- | --- | --- | --- |"]
    for p, t, m in PREFIXES:
        hit = [c for c in (survey or {}) if c not in ROWS and treatment(c)[2] == "prefix" and c.startswith(p)
               and next(q for q, _t, _m in PREFIXES if c.startswith(q)) == p]
        n = sum((survey or {}).get(c, 0) for c in hit)
        what, _, why = m.partition(" -- ")
        out.append("| `%s*` | %s (%d) | %s | `%s`%s |" % (p, n, len(hit), what, t, ": " + why if why else ""))
    return "\n".join(out) + "\n"
