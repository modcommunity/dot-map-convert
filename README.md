# tools/bsp: the family's one BSP map converter

Reads community maps in the VBSP v19-21 format, inventories a folder of them, and writes each as one documented intermediate JSON that a game's thin adapter turns into that game's own map document. Python 3, standard library only (plus `unrar` or `7z` on the path to list `.rar`/`.7z` downloads, and `fastgmad` for `.gma` workshop archives).

```bash
python3 -I tools/bsp/bsp.py list ~/godot/inspirations/g2gfast --converted ~/godot --markdown
python3 -I tools/bsp/bsp.py convert map.zip --out map.json --author "A" --page https://... --licence "CC BY-NC-ND 4.0" --no-share-check "2026-10-19: none"
python3 -I tools/bsp/tests/test_dotbsp.py            # 26 tests on maps written from scratch
python3 -I tools/bsp/tests/test_texturemap.py        # the shared texture list: specificity, tints, the unmapped report
python3 -I tools/bsp/bsp.py unmapped ~/mapsrc --top 40   # every texture that hits no row of source_textures.tsv, with face counts
python3 -I tools/bsp/bsp.py mesh map.bsp --out world/map --author "A" --page https://... --coverage   # the drawn mesh, hulls, movers
python3 -I tools/bsp/bsp.py classes ~/mapsrc --markdown   # every entity class, what the importer makes of it and which runtime component runs it
python3 -I tools/bsp/bsp.py classes <map | dir> --keys    # per map: keys, outputs and inputs the class catalogue lacks, and each class's component
python3 -I tools/bsp/defs/runtime.py                      # rewrites addons/dot_map/io/catalogue.json (what DotMapIO.load_catalogue reads) from rules/entity_defs.json
python3 -I tools/bsp/tests/test_mesh.py              # the mesh, movers and class table on maps written from scratch
python3 -I tools/bsp/tests/test_licence.py           # the raw store, the licence pass, environment and sound data
python3 -I tools/bsp/tests/test_regen.py             # rule tiers, fallbacks, regen, coverage, ratchet
python3 -I tools/bsp/tests/test_store.py             # the lossless store, repeated keys, outputs of any name
python3 -I tools/bsp/tests/test_audit.py             # the brush and floor audit on maps written from scratch
python3 -I tools/bsp/bsp.py audit map.bsp --mesh world/map            # every player-solid brush and standable top vs the output's collision; exit 1 on loss
python3 -I tools/bsp/bsp.py audit map.bsp --doc maps/map.json --y0 5.49   # the same against a game's box document (its terrain field counts; --passable CLASS, --within, --band, --skip for what it leaves out on purpose)
python3 -I tools/bsp/tests/test_lift.py              # the pieces lifted from the adapters (flood, classifier, props, lights, plan, .gma, guards)
DOTBSP_TEST_MAPS=~/maps python3 -I tools/bsp/tests/test_dotbsp.py RealMaps   # and on real ones
```

Always `python3 -I`: the maps are downloads, and `-I` keeps a planted module beside one from being imported. Archives are read in memory (zip by `zipfile`, rar by `unrar p`, 7z by `7z e -so`); nothing is extracted to disk and no path inside an archive is used as a path.

## The import order: raw, licence pass, environment (2026-10-22)

`python3 -I tools/bsp/bsp.py import map.bsp --game zz [--out <map repo>/world/<id>/<id>] [--pak] [credit flags]` does two things in this order (`dotbsp/importer.py`):

1. **The plain raw import**, outside every repository, at `<root>/<game>/raw/<map>/` (root: `--raw-root`, `$DOTBSP_RAW_ROOT`, default `~/mapsrc`; today `~/mapsrc/zz/raw/` holds 35 Zombie Zone maps, 208 MB). `mesh.json` + `mesh.bin` (every face with the source texture names, movers, volumes, links, entities, environment, sounds), `intermediate.json` (with faces and displacements), `entities.json` (every key of every entity), `census.json` (each texture with face counts and average colour, each placed model with its count), `pak.txt` (the packed file list), `models/` (every model the pakfile packs as glb with its textures, and `models.json`; `models-notes.txt` lists any that did not convert), `SOURCE.txt`, and with `--pak` the packed vmt/vtf/sound files. Nothing is replaced here; later passes and reconversions read from it. The author's work: never copy it into a repository.
2. **The licence pass** (`dotbsp/licence.py`, only with `--out`). Every surface's generic id (`source_textures.tsv`) maps through `free_textures.tsv` to a free replacement: a photographic CC0 set from `addons/dot_map/surfaces/` (ambientCG; URL, author and licence per row) or an image `dotbsp/textures.py` generates in the original's average colour (carpet, glass, water, snow, and any name no row knows). The manifest gains a `licence` block (every replacement with URL, author, licence and which source names it stands for; every placed model with its stand-in, `placeholder_box` when the game's `PropTable` has none) and `free` on each surface; `CREDITS.md` is written beside it. `licence.check` must be clean or the command exits 4 and the map is not to be committed. No source texture or model file is ever written to the output; the original names stay only as the names a replacement stands for.

**Environment and sound are data** in the shipped manifest and the raw store (`dotbsp/environment.py`): `environment` has `sky` (name), `sun` (`light_environment`: pitch, yaw, colour, ambient, HDR variants, spread), `env_sun`, `fog` (colour, start, end, max density, in metres), `shadows`, `tonemap`, `cubemaps` (the `env_cubemap` probes), `wind`, `sky_camera`; `sounds` has `ambient` (each `ambient_generic`: file, volume, radius in metres, pitch, looped, starts silent, plays everywhere, empty `stand_in`), `soundscapes` (`env_soundscape*` with radius and positions), `triggers` (`trigger_soundscape`) and `files` (every sound the map names). The sound files themselves are the author's and are not shipped: the licence pass fills each `ambient[].stand_in` from `free_sounds.tsv` (below). `tests/test_licence.py` covers all of it.

**Free stand-ins (2026-10-22)**, all in the licence pass, all tables with source, URL, author and licence per row (only CC0-1.0, MIT, Public Domain; `licence.check` refuses the rest):

- `free_sounds.tsv`: regex on the source sound name to a stand-in id, an ogg in `addons/dot_map/sounds/` (Kenney Sci-Fi, Interface and Foley sounds, CC0) or a dot-audio stock bed (`amb_*`, synthesised, CC0). Music and voices map to nothing on purpose (an empty id: silent, not replaced). Written into each `sounds.ambient[].stand_in` and the `licence.sounds` block.
- `free_models.tsv`: regex on the model path to a glb in `addons/dot_map/props/` (Kenney Furniture, Survival and Nature kits, CC0). A model the game's `PropTable` knows keeps the game's; one neither knows is, in order: shape-matched when the map packs it; a size-correct neutral block (`measured_box`, `standins._box_ok`: prop-sized, solid, not a decal, hung light or lattice); left out on purpose (`detail`, `standins.DETAIL`: effects, characters, vents, wires, pictures, hanging growth, distant buildings); else `placeholder_box` and unplaced. `standins.placements` writes the matched ones as the manifest's `props` (stand_in, at, yaw, scale), which `DotMapBspMesh.build_props` places.
- `modeldims.py` (`bsp.py modeldims`) ranks every placed model over the store (`rules/models/ranking.tsv`) and records each one's size (`model_dims.tsv`): exact from the packed model, else from the stock model's header hull (`--game-vpk` or `$DOTBSP_GAME_VPK`; a few percent large). `modelmap.py` (`bsp.py modelmap`) picks a CC0 or CC-BY model from the library (`~/art-library/models`, or `$DOT_MODEL_LIBRARY`, `manifest.tsv`) for each ranked model: name words from `rules/models/categories.tsv` (ordered alternatives, default size, and the plain shape and colour to generate when nothing fits), then the nearest size after a uniform scale, turning a quarter when the other pairing fits better. Picks go to `rules/models/picks.tsv` (id, scale, turns, source, URL, author, licence, file). `regen` applies them by default (`--no-models` leaves them out), copies each used model once into a shared store (`--model-store`, default `<out>/../model-library`, the library-relative path kept so a pack's models share its textures), and lists them in `CREDITS.md`; the manifest's `licence.model_store` points at it and `DotMapBspMesh` loads a `lib/` stand-in with `GLTFDocument`, standing it on its bottom centre and fitting it to the recorded size. Generated fixtures (`own/`, author TMC) are CC0. Skybox and detail props are left out on purpose. `modelmap` runs a second, looser pass when no model is within reach, ignores a target side under 10 cm, matches names on the file name only (never the folder), and picks an unnamed model by measured shape alone from household-sized Poly Haven, Sketchfab and Kenney furniture/survival/food models (`--report FILE` lists every generated stand-in with its reason; by instance 85.1% library, 6.2% plain light fixtures, 0.5% no fit, 0.1% no category). `ship` warns when a glb names a texture the library lacks. Not done: a Blender normalise pass (origin and facing are fixed at load instead), the store's delivery in packs, and showing CC-BY credits in game.
- `pbrmap.py` (`bsp.py pbrmap`) maps every texture name the converted maps use to a set of the CC0 PBR library (`~/art-library/materials`, or `$DOT_ART_LIBRARY`): by name words (`brick/`, `metalfloor005a`), then the nearest average colour inside that category. The picks are the `addon` tier in `rules/pbr/` (`textures.tsv`: name to `pbr_<set id>`; `free_textures.tsv`, the same six columns, kind `pbr`, with URL, author and licence), which `regen` adds by default when the library is on the machine (`--no-pbr` leaves it out). The licence pass writes each chosen set once into a shared store (`--pbr-store`, default `<out>/../pbr-library`, `<id>/<tier>/{albedo,normal,roughness,ao}.webp`; tier 2k for a set covering at least 5% of the map's surface area, else 1k), and the manifest's `licence.pbr_store` points at it, so packs share sets by id instead of each carrying a copy (house_outbreak: 2.5 MB pack, 64 MB store). `CREDITS.md` lists them. A `blend*` displacement carries per-vertex alpha (`alpha_offset`) and two library layers (`free`, `free2`) chosen from its name words (grass, rock, sand, gravel, dirt), not its average colour. `DotMapSurfaces.world_material_for` draws a set as a world-triplanar `StandardMaterial3D`, or through the lightmapped shader, which uses the normal, roughness and AO maps and mixes the two blend layers by vertex alpha. Not done: GPU texture compression (Godot has no KTX2 loader at runtime; needs the import pipeline), and the store's delivery by dot-cloud. See-through kinds (glass, water, grates) keep their generated look. Re-run `pbrmap` after converting new maps.
- `nearest.py` for an unmapped texture: by name (`brickwall12` is brick), then by average colour against `photo_colours.tsv` within 0.2, else the flat generated image. The record's `how` says which (`table`, `name`, `colour`, `flat`). Rows for every photo kind are in `free_textures.tsv` so credits resolve.

`DotMapBspMesh` applies the data with hooks and no scene path or autoload: `build_environment()` (sky, sun, fog, tonemap, probes), `build_sounds(stream_for, make_node)` (a callable for the stream, one for the node so a game can play through dot-audio), `build_props(scene_for)`, `licence()`, `is_free()`. `tools/screenshot.sh <world prefix> <png>` renders a frame of a converted map dressed this way.

## Rule tiers, `regen` and the coverage ratchet (converter v2, package 3)

`bsp.py regen <hash | game/map> --out <prefix> [--addon-rules DIR]... [--game-rules DIR] [--map-rules FILE] [--ratchet]` rebuilds a map's manifest, `.bin`, textures and `CREDITS.md` from its store entry (`source.bsp` and `credit.json`, which must name author and page) and the rules alone. Rules are read in four tiers, default (the lists beside `dotbsp/` and `tools/bsp/rules/`) < addon < game < map. A tier is a directory of `textures.tsv`, `free_textures.tsv`, `models.tsv`, `sounds.tsv`, `classes.tsv` (class or `prefix*`, treatment, meaning, component), `materials.tsv`, `roles.tsv`, or one JSON file with the same tables as keys (a map's `tools/convert/maps/<id>.json`). The highest tier with a matching row answers, the most specific row inside it; a path that does not exist is an error. Nothing is dropped: a texture no row names goes to the nearest photo set or a flat image, a model to `placeholder_box`, a sound to silence, a class to `DotMapEntity` (`rule: "fallback"` in the manifest's `entities`).

`<prefix>.coverage.json` lists, per map, which tier answered how many textures, models, sounds and classes, and the names that fell through: `textures_unmapped`, `textures_flat`, `models_unmapped`, `sounds_unmapped`, `classes_unmapped`, `keys_unmapped` (keys of a class that `rules/entity_defs.json` does not know, a class based on another class inheriting its keys, and not those `dotbsp/keys_handled.tsv` names as read by a component or dropped on purpose, with the reason), `links_unresolved`. Commit it with the map. `--ratchet` compares against the committed report and exits 5 when any list holds a name the baseline did not (the report is then not rewritten); with no baseline it exits 2. Inputs no component implements are not in the report yet: they need the runtime of package 5.

## The author's baked lighting (`dotbsp/lightmap.py`)

`mesh.build` imports the map's own lightmap, with no caps: lump 8 (LDR, else lump 53 with the HDR face lump 58), the base sample of light style 0 per face (a bumped face's three directional samples and the animated styles are not kept), decoded as `c * 2^e / 255`, packed into 2048-wide RGB9E5 pages with a texel of border, and a second UV set per vertex pointing at the texel centres (a displacement uses its flat quad's lightmap vectors). A face with no lighting reads a white patch. The manifest becomes version 2: `lightmap` (pages, `scale`, `ambient`), and per surface `uv2_offset`, `lightmap_page`, `emissive` (SURF_LIGHT). v20 per-leaf ambient cubes (lumps 52 and 56) go in as `lightmap.ambient`, read by `DotMapBspMesh.ambient_at`. A map with no lighting stays version 1. The material is `DotMapSurfaces.world_material_for`'s `lightmapped.gdshader`: world-triplanar albedo, the lightmap as emission, the scene's sun on top (its energy is floored at 1.0 on a lightmapped world, because an outdoor bake is often near black, and its diffuse fades where the bake is bright) and `light_floor()` as the ambient floor so nothing is black; `use_lightmap = false` draws the lit materials. Not done: light styles, the bump directions, ambient for v19 maps, lightmapped props.

## The lossless store (converter v2, package 1)

`bsp.py store <dir | file>...` copies each map into `$DOTBSP_STORE` (default `~/mapsrc/store`, outside every repository) as `<sha256>/source.bsp`, `credit.json` and `doc.json` (entities with every key in file order, repeats kept, and outputs of any key whose value has the `target,input,param,delay,times` shape), and `index.json` maps `<game>/<map>` to the hash. `doc.json` also lists `commands` (console commands the map sends to `point_servercommand`/`point_clientcommand`, recorded and never run; a later package emits them as per-map config). `credit.json` and rules are the small data meant for git; originals stay outside git, referenced by sha256. `store --scripts` lists every distinct `lua_run` snippet with its count and whether `dotbsp/scripts.py` translates it (never executed; see [io](../../docs/io.md#map-scripts)). `store --check` rebuilds each `doc.json` from its `source.bsp`. A cut-off file is reported and skipped. Entities from `reader.parse_entities` are dicts as before, with `.pairs` holding the ordered keys; `movers.outputs` appends non-`On` outputs after the `On` ones, so existing manifests only gain links.

## Why here, and why not in the games

Six copies of the reader and five box converters had grown in the map repositories and in game-g2gfast, each with a fix the others lacked (the table below). A reader fix reached one game. It lives in dot-map because dot-map is the content addon every map-using game already links and clones beside itself, and outside `addons/dot_map` so it never ships in an addon copy or a pack (`.gdignore` keeps Godot from scanning it). A game finds it as the sibling checkout `../dot-map/tools/bsp` that dot-bootstrap makes, or at `$DOTBSP_PATH`.

The split is: dot-map reads the format and cuts brushes into boxes; the game decides what an entity means (which class is a spawn, which brush entity is a gate, which material is glass) and writes its own document. That is the adapter, and it is the only per-game part.

## Layout

| File | What it is |
| --- | --- |
| `dotbsp/reader.py` | `Bsp`: lumps (LZMA too), brushes and hulls, the BSP-tree walk to a model's brushes, faces, displacements, static props, the packed zip; unit and axis helpers |
| `dotbsp/audit.py` | `audit(bsp, out)`: every brush the map's models reach by owner class and CONTENTS kind (solid, detail, window, grate, ladder, clip, playerclip, npcclip, water, slime, sky, nodraw, origin, areaportal), which player-solid ones the output collides with, and a walk test (a 24-unit grid on every exposed top with body room above, inside the sealed world) asking the output for ground under each point; `Hulls` reads a mesh, `Boxes` a box document |
| `dotbsp/boxes.py` | `decompose(planes, hull)`: a brush as boxes, the union of the converters' fixes |
| `dotbsp/docboxes.py` | the importers' shared passes over a *document's* boxes (metres, Godot axes): `within`, `classify_material`, `brush_material_names`, `majority_material`, `suburban_surface`, `widen_doors`, `drop_door_leaves`, `add_doors`, `prune_far_scenery`, `prune_pockets`, `scatter_cover` |
| `dotbsp/intermediate.py` | `build(bsp, credit)` writes the intermediate; `summary` is what `list` prints; `check(doc)` before trusting one |
| `dotbsp/sources.py` | finding maps in folders and archives; which game a prefix belongs to; which maps the `*-maps` repositories already have |
| `dotbsp/units.py` | the two scales (`VISUAL` 0.01905, `HULL` 0.0254), `to_game`, `from_metres` |
| `dotbsp/entities.py` | the entity classifier (`classify_entity`), the brush classifier (`classify_brush`), `teleports` / `teleport_destination` / `pad_rect` |
| `dotbsp/mdl.py`, `dotbsp/vtf.py`, `dotbsp/models.py` | the models a map packs in its pakfile: `mdl.parse` (studio v44-49 with vvd and the dx90 strips, LOD 0, body group 0) to triangles and `to_glb`; `vtf.read` (DXT1/3/5, BGRA, RGB, I8) to a PNG and `base_texture` of a vmt; `models.extract(bsp, dir)` writes `<raw>/models/<path>.glb` (textures embedded) and `models.json` (triangles, bounds, size and centre in metres, materials with average colours); `models.measure(bsp)` is the sizes alone, in memory, for an importer; `match_size` / `compatible` pick the catalogue prop of a measured shape. `standins.shape_matches` is the converter's own use of it: a placed model no name row knows, that the map packs, gets the nearest of the neutral blocks, drums and rocks in `free_model_dims.tsv` by measured shape (limit 0.4, nothing under 8 cm, over 3.5 m or a flat slab), set down on the model's middle at its measured longest side, with `shape: true` in the manifest's `props` and the stand-in credited like any other. Raw store only: the author's art is never shipped, a game's table of free props is chosen by the measured shape |
| `dotbsp/props.py` | `PropTable` and `placed_props`: a map's placed models (entities and static props) matched to a game's own, `model_census` |
| `dotbsp/lights.py` | `to_game` (lights to metres, range and energy, suns apart), `thin`, `thin_by_gap` and `strengthen` (the `--max-lights` loop exactly), `auto` |
| `dotbsp/gamebox.py` | `model_boxes`: a model's brushes as game-metre boxes with the source material and kind |
| `dotbsp/flood.py` | `Flood`: reachable space over boxes with step, jump, drop and head room, and over terrain by slope; `floor_rects`, `keep_starts`, `terrain_walk` |
| `dotbsp/terrain.py` | `Heightfield`: displacement triangles as a heightfield in metres (highest surface wins), `encode`/`decode` (predicted int16 residuals, deflated, with a walk mask), `fit` to a byte budget over the reached ground, `walk_points`, and a skirt (`outer_edges`, `skirt_level`: `swap_terrain` writes one float, `skirt`, and `DotMapTerrain` hangs a double-sided wall from the field's outer rim down to it, mesh only, so a rim over open air never floats with sky under it; holes the field surrounds get none; `skirt=False` leaves it out); the game reads it with `DotMapTerrain` (collision shape, mesh, nav points). Replaces `boxes.terrain_cells`' stepped boxes, which no flood or body could climb past a step per cell |
| `dotbsp/plan.py` | `extract`: a room plan from walls that do not close (seal, outside flood, doorway erosion, rooms on a coarse grid) |
| `dotbsp/gma.py` | `.gma` workshop archives through fastgmad (`sources.find` and `bsp.py` take a `.gma` like a zip) |
| `dotbsp/texturemap.py`, `dotbsp/source_textures.tsv` | the one list of source texture names to generic material ids (`wood_floor`, `carpet`, `brick_red`...) with an optional tint, most specific row first; `bsp.py unmapped` lists what it misses |
| `dotbsp/mesh.py` | `build(bsp)`: every face the map draws as triangles per (model, material) with normals and texture UVs, displacements, the 3D skybox room moved to where it is seen, and one convex hull (points and planes) per player-solid brush; `write`/`read` (`<prefix>.json` + `<prefix>.bin`, `dot-bsp-mesh` v1); `coverage` and `silhouette_diff`, which sample the source and ask the output |
| `dotbsp/movers.py` | `links` (the output to input graph) and `generic` (entities kept as data) beside `movers`: doors, buttons, rotators, trains with their paths, lifts and conveyors as records (direction, distance, speed, wait, what opens them); `volumes` (teleport, push, hurt, gravity, water, ladder with brush planes); `destinations` |
| `dotbsp/classes.py`, `dotbsp/classes.tsv`, `docs/entity-classes.md` | the one table of entity classes (`classes.tsv`: class or `prefix*`, treatment, meaning, runtime component; the default tier of `rules.py`): what each meant in the source and what it becomes (world, drawn, mover, volume, point, data, dropped); `report(bsp)` is the coverage report `mesh` prints, and an undecided class fails it |
| `bsp.py` | the CLI |
| `tests/` | `synth.py` writes a small VBSP file from scratch (v19, v20, v21 in both record orders, a brush entity); `test_dotbsp.py`; `test_mesh.py` (with `faces=True` synth writes the drawn faces too) |

## Fixes merged, and where each came from

| Fix | From |
| --- | --- |
| Leaf size by the file's version (56 bytes in v19, 32 from v20), not by which size divides the lump | every copy of `bsp_read.py` |
| A v21 lump directory can be stored version, offset, length; both orders are tried and the one that fits the file wins | new here: a v21 map read the plain way slices plausible bytes from the wrong place |
| Texture names are Latin-1, not ASCII | game-g2gfast `bsp_read.py` |
| Packed zip read entry by entry, so one bad entry costs that entry; names decoded as the mapper's codepage, not cp437 | game-g2gfast `bsp_import.py` |
| Bevel sides skipped in hulls and planes | every copy |
| Static props from the `sprp` game lump, v4 to v11 | game-g2gfast `bsp_props.py` |
| A brush turned about the vertical is one box: every upright side's angle tried, corners within 1.5 units | mg-prop-hunt-maps and hide-n-seek-maps (zombie-zone-maps tried one angle at 0.5) |
| An upright prism (a column, a curved wall's segment) is one turned box | mg-prop-hunt-maps; here only when its plan fills 80% of the box, because the box round a triangular column is twice the column |
| A single-slope ramp as one tilted box, for a document that can tilt one (`tilt=True`) | game-playground-maps |
| Slabs cut along the slope, each spanning the brush's own cross-section at its middle | zombie-zone-maps (the others cut along the longer axis, across the bounding box) |
| A wedge is not a box: an axis box wants all eight corners | new here, found by the tests; three copies wrote a ramp as a block because a wedge's six corners are all box corners |

## The pieces lifted out of the adapters (2026-10-20, nightly dot-map-bsp-import-1)

Each maps repository grew these on its own. They are here now, each with a test in `tests/test_lift.py`; an adapter keeps only what a *game* decides (its materials, its spec keys, its document).

**The flood** (`flood.Flood`) is zombie-zone-maps' `build_nav` with the module globals made parameters, and reproduces it exactly: on twelve runs over six committed zombie maps (with and without `wide`, both floor packers) the cells, parents, distances, links, surfaces and floor rectangles are identical. It works on boxes in metres, so any game's document can ask "can a body walk from the start to here?". Disagreement: prop-hunt, hide-n-seek and murder-mystery-maps each had a second, 0.1 m flat flood (`prune_pockets`) with one floor height; the cell flood is multi-storey, has the step, jump, drop and head-room limits and `wide`, so it is the one kept. `Flood(boxes, cell=0.1, head=1.4, step=0.3)` is the closest equivalent to the flat one; whether the bots' mesh erosion (0.35 m) is the adapter's to add on top was not settled, so `prune_pockets` is not deleted yet.

**The classifiers** (`entities`). `classify_entity` merges the class lists of five adapters (the physics-prop and rotating-door/button classes were missing from some). `classify_brush` is zombie-zone's: tools-only brushes are invisible or sky, clip contents are invisible, the *top* face's material names a solid. Prop-hunt's and hide-n-seek's `classify(name)` are material-name to surface-kind tables; those are the game's and stay in the adapter.

**Prop matching** (`props`) is case-blind and slash-blind for entities *and* static props. zombie-zone-maps lower-cased the table for static props but matched entities exactly first; one rule now.

**Lights** (`lights`) keep zombie-zone-maps' range and energy formulas (three games were tuned against them) as defaults. `thin` is murder-mystery-maps' `--max-lights`, made deterministic (brightest first, optional minimum spacing). A `light_environment` is a sun with a direction, not a lamp at its origin; its `pitch` is the direction itself (-90 is straight down), the opposite sign of a camera's.

**`.gma`**: fastgmad does the reading (nothing was written, on purpose). It extracts into a fresh temporary directory; only `*.bsp` files are read back into memory; the directory is removed before the call returns. `bsp.py list` and `convert` take a `.gma`; an unreadable archive is one `unreadable:` line, not the end of a listing. dot-bootstrap must install fastgmad (not done here; it is another repository).

**Reader guards.** `game_lumps` returned a `struct.error` on an empty or short lump; it now returns `{}` for a lump too short for its own directory, an entry pointing outside the file, or a bad LZMA stream (zombie-zone-maps caught every exception instead). Separately `load()` now refuses a file whose lump table points past its end with a message naming the lumps. **Helix's "model brush crash" was neither**: `deathrun_helix_b8.bsp` in `~/mapsrc/deathrun/126992/x` is a 4.2 MB piece of a 23 MB file (an incomplete extraction), and the traceback was the game lump on a cut-off file. `deathrun_helix_b8-1.bsp` (23 MB, the complete one) reads and converts: 3797 brushes, 1076 entities, 45 spawns, with brush models. Re-extract the .rar rather than looking for a model-brush bug.

**Scale.** `intermediate.build(scale=)` and `bsp.py convert --scale visual|hull|<number>` write `units.metres_per_unit` (default 0.01905, unchanged geometry). Both scales stay: 0.01905 is what the art was modelled to and what the box games keep, 0.0254 is what makes the 72-unit player hull 1.83 m, which deathrun's timings and look-at-me's room sizes need. A document never mixes them. Box slabs are given in metres through `gamebox.model_boxes(slab_m=, scale=)` so a 0.0254 game gets the same physical slab.

**Teleports.** `entities.teleports(doc)` resolves every `trigger_teleport` to its destination (the `info_teleport_destination` first when a decoy shares the targetname), returns `None` rather than raising when the map names one that does not exist, and carries a landmark. `pad_rect` widens a thin trigger to a stride. The *pad itself* (the game piece) is GDScript and not lifted.

**Plan from open walls** (`plan.extract`) is look-at-me's `bsp_layout.py` without numpy and scipy, plus: walls from brush entities of chosen classes (`func_brush` by default), explicit rectangles, and static props by model name with a footprint; and a *seal* that grows the walls before the outside is flooded, so doorways and broken windows narrower than twice the seal do not let the outside in (without it the whole building is "outside" and the plan comes back empty, which the test shows).

### What each adapter can now delete

Deleted nowhere yet: the maps repositories were being edited by conversion agents, so these are the statements for the per-repo builders.

| Repository | Can delete, using |
| --- | --- |
| zombie-zone-maps `tools/import_bsp.py` | `_safe_game_lumps` and the `reader.Bsp.game_lumps` patch; `Brush`, `read_brush`, `classify`, `boxes_from_brush`, `model_boxes` (to `gamebox.model_boxes` + its `material_for`); `inside_box`, `cell_index`, `_thin_wall_over`, `surfaces_at`, `build_nav`, `floor_at` and the `CELL`/`DROP`/`JUMP`/`STEP`/`HEAD`/`THIN_*`/`GREEDY_FLOORS`/`MIN_FLOOR_Y` globals (to `flood.Flood`); the prop-model matching of entities and static props (`props.placed_props`); the light loop and `auto_lights` (`lights.to_game`/`thin`/`auto`); the `gate_classes`/`solid_classes` defaults (`entities`) |
| mg-deathrun-maps `tools/bsp_to_course.py` | `planes_of`, `z_range`, `box_in_frame`, `turned_box`, `prism_box`, `brush_boxes` (to `boxes.decompose`, converting with `units.HULL`); the `trigger_teleport` / `info_teleport_destination` lookups with `next()` (to `entities.teleports`, `pad_rect`); `bsp_read.py` shim once it imports `dotbsp` directly. Helix: re-extract `deathrun_helix_b8` from the .rar |
| hide-n-seek-maps `tools/import_bsp.py` | `planes_of`, `z_range`, `box_in_frame`, `turned_box`, `prism_box`, `brush_boxes`, `terrain_boxes` (`boxes.terrain_cells`); `prune_pockets`'s flood after a trial on `flood.Flood`; the prop-model lookup (`PropTable`); the light loop; the `prop_door_rotating`/door class tests (`entities`) |
| mg-prop-hunt-maps `tools/import_bsp.py`, `bsp_read.py` | the same as hide-n-seek-maps (the two are copies); `bsp_read.py` becomes the shim |
| murder-mystery-maps `tools/import_bsp.py` | the box helpers (`dboxes.decompose`); `--max-lights` thinning (`lights.thin`); the start filter (`Flood.keep_starts`); `prune_pockets`; the prop lookups; the light loop |
| game-playground-maps `tools/import_bsp.py` | `planes_of`, `z_range`, `box_in_frame`, `turned_box`, `prism_box`, `ramp_box`, `brush_boxes` (to `boxes.decompose(tilt=True)`); light conversion; entity class tests |
| mg-wipeout-maps | no importer yet (`tools/build.py` only): start from `gamebox`, `entities`, `props`, `lights`; `bsp.py convert` takes the workshop `.gma` directly |
| mg-look-at-me (a game, not a maps repo) | `tools/bsp_layout.py` becomes a call to `plan.extract` (and `plan.ascii_plan` for `--ascii`); numpy and scipy go |

## The intermediate (`dot-bsp-intermediate`, version 1)

One JSON object. Map units and map axes throughout (Z up, 1 unit = 0.01905 m, Godot = (x, z, -y), yaw about +Z from +X); a game converts on the way out, so one document serves games with different scales.

| Key | Holds |
| --- | --- |
| `format`, `version` | `"dot-bsp-intermediate"`, `1`. A reader refuses a newer version (`intermediate.check`) |
| `units` | the conventions above, in words, and `metres_per_unit` (0.01905 by default; `--scale hull` writes 0.0254) |
| `source` | `name`, `file`, `bytes`, `sha256`, `bsp_version`, `revision`: which download this was |
| `credit` | `author`, `page`, `licence`, `no_share_check` (`DATE, STATUS: evidence URL`; STATUS is `none` when nothing forbids it, `ask` when the author or licence wants to be asked first (NC/ND, permission to alter), `forbidden` when the author refuses; `store --audit` counts the unchecked and exits 1 only on `forbidden`), `notes`, and any other key the caller passed (a credit line for the map-change screen). `convert` warns when there is no author or page |
| `world` | `mins`, `maxs`, and the worldspawn `keys` (sky name and so on) |
| `materials` | `[{name, clean}]`; sides and faces index into it. `clean` drops the compiler's decoration |
| `models` | `[{index, entity, origin, mins, maxs, brushes}]`: model 0 is the world, the rest one brush entity each, already moved to the entity's origin |
| `brushes` | `[{id, model, contents, contents_names, player_solid, sides: [{plane: [nx, ny, nz, d], material, flags}], hull: [[x, y, z]...], mins, maxs, boxes}]`. Planes and hull are where the map put the brush. `boxes` is `decompose` at the default 28-unit slab; an adapter with another scale recomputes from `sides` and `hull` |
| `entities` | `[{index, classname, keys, origin?, model_index?}]`, every key as the map wrote it |
| `spawns` | `[{entity, class, team, origin, yaw}]` for the player-start classes the format's games use (`team` is red, blue or any) |
| `lights` | `[{entity, class, origin, colour, brightness, ...}]`, spot cones and the sun's angles included |
| `static_props` | `[{model, origin, angles, solid, skin, scale}]` (model paths only; the models themselves are the author's art and are never used) |
| `counts` | brushes, entities, spawns, lights, static props, displacements |
| `faces`, `displacements` | only with `--faces` / `--displacements`: drawn world polygons by material, and terrain triangles |

## Games

| Game | Converter | State |
| --- | --- | --- |
| game-zombie-zone | `zombie-zone-maps/tools/import_bsp.py`, an adapter reading a `.bsp` or an intermediate `.json` | migrated 2026-10-19; Nuke and Run For Your Life re-convert with identical floors, spawns, routes and props and better boxes (below) |
| game-g2gfast | `game-g2gfast/tools/bsp_import.py` (a mesh, lightmap and texture pipeline); its `bsp_read.py` is now a shim over `dotbsp.reader` | migrated at reader level 2026-10-19; six maps (v19, v20, LZMA) import byte-identical |
| mg-prop-hunt, game-hide-n-seek, game-playground, mg-deathrun | their own `import_bsp.py` / `bsp_to_course.py` and a copy of `bsp_read.py` in the map repository | not migrated (see the note) |

Zombie-zone's re-conversion against the committed maps: Nuke differs only in the last digit of 19 boxes (planes now pass through the document's rounding) and a few boxes turned under half a degree written square; Run For Your Life's invisible boundary walls, turned about one degree, were 129 saw-tooth slabs and are now 14 turned boxes. Nav floors, spawns, routes, items and props are unchanged, and game-zombie-zone's `headless_maps` gives the same result on both. Raven Street re-converts with one box 1 mm taller and was left as it was, because its committed lightmap is hashed against the document; it moves with its next bake.

### Migrating the other four

Each is the same change zombie-zone-maps made, a few hours a game:

1. Delete the repository's `tools/bsp_read.py` and import `dotbsp` (`reader`, `boxes`, `intermediate`) from `$DOTBSP_PATH` or `../../dot-map/tools/bsp`, exiting with a message when neither exists. Copy `_dotbsp_path()` from zombie-zone-maps' importer.
2. Replace the local `turned_box` / `prism_box` / `slice_brush` / `ramp_box` with `boxes.decompose(planes, hull, slab=..., min_size=..., tilt=...)` in the game's units (prop-hunt and hide-n-seek: metres, so `slab=0.4 / 0.01905`; playground passes `tilt=True`; deathrun's scale is 0.0254, so convert with that, not `METRES_PER_UNIT`). `boxes.centre(b)` and `boxes.size(b)` give a box's centre in map coordinates and its turned-frame size.
3. Read brushes from `intermediate.build(...)` (or a saved document) rather than walking `bs.brushes` by hand: a brush entity's planes and hull are already moved to its origin, which every copy did by hand.
4. Re-convert every map the repository ships and compare with the committed documents. Expect fewer, larger boxes where a map has ramps wider than they are long (slabs now follow the slope) and on narrow upright prisms (now slabs, not their bounding box), and ramps that used to be blocks (the wedge fix). Render one and look.

hide-n-seek-maps had another agent's uncommitted importer work on 2026-10-19; merge that first.

## Conversion queue

From `bsp.py list ~/godot/inspirations/g2gfast ~/godot/inspirations/bsp-maps --converted ~/godot` on 2026-10-19: 109 maps found, 99 already in a map repository, 1 unreadable (`surf_pox.rar`, not an archive), leaving these 9 (all g2gfast genres). Ranked easiest first: size is mostly the packed zip (the author's textures and models, which are never used), so the brush and entity counts are the work.

Sourcing rule (2026-10-19): maps from the community map sites may be converted in bulk unless the author says not to share, port or reupload; each is credited in the README and on screen at map change, linked, and removed on request. Every page below was read on 2026-10-19 and none carries such a note. All nine are CC BY-NC-ND 4.0, which is why the rule above applies to them and the art rule still keeps their textures, models and sounds out.

| # | Map | Target | MB | Brushes | Notes | Page | Author | Licence | Do-not-share note |
| ---: | --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| 1 | surf_greatriver_awesome | game-g2gfast | 1.6 | 362 | no displacements or props; the `.rar` copy (0.5 MB) is truncated, use `pending/surf_greatriver_awesome.bsp` | https://gamebanana.com/mods/122168 | Stavros Xanthis (key author), submitted by Spoz; original by Ace of spades13 and Monkeydie | CC BY-NC-ND 4.0 | checked, none |
| 2 | bhop_grove_backwards | game-g2gfast | 13.2 | 698 | the reversed layout of bhop_grove, which g2gfast already ships (same page); 144 displacements, 328 props | https://gamebanana.com/mods/125167 | tmontana | CC BY-NC-ND 4.0 | checked, none ("you may add both versions to your server") |
| 3 | surf_buck-wild | game-g2gfast | 17.4 | 3202 | 28 props; 20 spawns a side | https://gamebanana.com/mods/121787 | BuckNasty | CC BY-NC-ND 4.0 | checked, none |
| 4 | bhop_mario_fxd | game-g2gfast | 121.4 | 5604 | 20 displacements, 13 props; page lists it as bhop_mario | https://gamebanana.com/mods/125494 | DroN | CC BY-NC-ND 4.0 | checked, none |
| 5 | bhop_woodenspace | game-g2gfast | 121.9 | 3499 | 230 displacements, 204 props; one spawn | https://gamebanana.com/mods/126357 | FlowBhop, Rem, loshadkaxd, Antosha | CC BY-NC-ND 4.0 | checked, none |
| 6 | bhop_zelda_final | game-g2gfast | 267.2 | 6437 | no displacements or props: brushes only, the size is its packed textures | https://gamebanana.com/mods/126396 | Whimsy | CC BY-NC-ND 4.0 | checked, none |
| 7 | bhop_umbra | game-g2gfast | 251.7 | 7894 | 305 displacements, 350 props | https://gamebanana.com/mods/126278 | Ntag | CC BY-NC-ND 4.0 | checked, none |
| 8 | bhop_lost_world_v2 | game-g2gfast | 236.3 | 7977 | 470 displacements, 699 props, 1704 packed files | https://gamebanana.com/mods/125470 | teh_grave | CC BY-NC-ND 4.0 | checked, none |
| 9 | bhop_shutdown2 | game-g2gfast | 308.8 | 6576 | 480 displacements, 1173 props, 3337 packed files: the largest | https://gamebanana.com/mods/125964 | sodawater, Benchmarked, wet | CC BY-NC-ND 4.0 | checked, none |

Nothing in the two folders belongs to zombie-zone, prop-hunt, hide-n-seek, deathrun or playground that is not already converted; a new batch for those starts with a new download and `list --converted`.

## Where a lift differs from its original

Compared function by function against the importers it came from (follow-up to the first lift):

- `plan.extract` against mg-look-at-me's `bsp_layout.py`: the same rasteriser, 4-neighbour erosion with the raster edge counted empty (scipy's `border_value=0`), per-blob growth cut to the building afterwards, 60% fill and greedy rectangles. Differences: pure Python (no scipy, so slower on a large bbox), `seal_m` (default 0, the original had none), `wall_classes` / `wall_rects` / `wall_props` as extra wall sources (the original read only world brushes), and `ascii_plan` takes its 12% threshold from the original.
- `lights.spread_order(lamps)` (all lamps, any prefix covers the map: for a game that sends or lights only the first N; nothing is dropped, unlike `thin`) came from zombie-zone-maps, which no longer caps its lamps. `lights.thin` against murder-mystery-maps: `thin` (brightest first, fixed spacing) is a different, deterministic policy and stays. The original is now `lights.thin_by_gap(lamps, max_lights)` -> `(kept, gap)` plus `lights.strengthen(energy, gap)` (the survivors' range is `9 + gap` in that game); byte-identical output on Hollow Hill with `--max-lights=6` (below).
- `Flood.keep_starts` against murder-mystery-maps' start filter: the same "8 m below the median start" rule, plus a dropped start with no floor under it.
- `PropTable` against prop-hunt-maps' `PROP_MAP`: that table keys by file stem; a key with no "/" now matches that way, a key with a folder matches the whole path.
- `prune_pockets` against hide-n-seek-maps, prop-hunt-maps and murder-mystery-maps: `docboxes.prune_pockets(doc, size_of, footprint, spawn_key=)` is the original 0.1 m flat flood moved unchanged (the three copies differed only in the spawn list the flood starts from: `hiders`, `props`, `players`). `flood.Flood` is still not a drop-in for it (see the table above).
- wipeout has no importer, only `tools/build.py`: nothing to compare.

## The document-box passes (`docboxes`, 2026-10-20)

hide-n-seek-maps, mg-prop-hunt-maps and murder-mystery-maps carried copies of the same passes over a finished document; the copies were identical except where a parameter now stands. Each function is tested against the repositories' own copy on their committed documents (`tests/test_dotbsp.py`, `DocBoxes`), and murder-mystery-maps' importer was rewired in a scratch copy: `mu_silence.bsp` re-imports **byte-identical** to the unmodified importer's output, with and without `--prune-pockets --terrain --max-lights=6` (the committed `mm_silence_hollow.json` was edited by hand afterwards, so it is not the comparison).

| Function | Replaces (in) | Parameters where the copies differ |
| --- | --- | --- |
| `within(box, x, z, slack)` | `within` (all three) | none |
| `classify_material`, `brush_material_names`, `majority_material(names, table, default)` | `classify`, `brush_material`, `pick_material` (all three; `classify` and the same majority pick also in game-playground-maps' `material_for`) | the table and the default: `("flat", None)` or a config's own. The pick is `classify(max(sorted(set(pool)), key=pool.count))`: a tie follows the sorted name, not the hash seed |
| `suburban_surface(at, size, palette)` | `suburban_surface` and its five colour constants (all three) | `palette` |
| `widen_doors(boxes, want, doors)` | `widen_doors` (all three) | prop-hunt's has no `doors`; the default `()` is its behaviour |
| `drop_door_leaves(boxes)` | `drop_door_leaves` (all three) | takes `m.boxes`, not the map |
| `add_doors(m, doc, entities, shift, slide, scale, skip, log)` | `add_doors` (hide-n-seek, murder-mystery) | `skip` is murder-mystery's `SKIP_DOORS`; `scale` the importer's `S`; `log` replaces `print` |
| `prune_far_scenery(boxes, starts, reach, log)` | `prune_far_scenery` (all three) | takes `m.boxes`; returns the count |
| `prune_pockets(doc, size_of, footprint, rounds, spawn_key)` | `prune_pockets` (all three) | the catalogue's `size_of` / `footprint` (the repo's `build_maps`), and `spawn_key` |
| `scatter_cover(m, count, seed, kinds, ...)` | `scatter_cover` (hide-n-seek, murder-mystery) | `kinds` (their `COVER_INDOOR`) is now required |
| `boxes.terrain_cells(tris, ...)` (already there) | `terrain_boxes` (all three) | the importer keeps the three lines that collect the triangles; the cells have the same order |
| `lights.thin_by_gap`, `lights.strengthen` | the `--max-lights` loop (murder-mystery) | `step`, `cap`, `per_metre` |

Not moved: deathrun's `merge` (one copy, and it keys on that importer's `invisible`, `tint` and `top`), the material tables (`TEXTURE_MAP`, `PROP_MAP`, the palette's use) and `classify` in zombie-zone-maps (a different function, on a brush). `fastgmad` is also looked up under `%LOCALAPPDATA%\fastgmad`, `%LOCALAPPDATA%\Programs\fastgmad` and `%LOCALAPPDATA%` on Windows (`gma.find_fastgmad`), and nowhere else.

## The shared texture list (2026-10-20)

Every importer carried its own `TEXTURE_MAP` (a substring table in its own file), so each new conversion relearned that `PLASTER/OFFWLL*` is a painted wall and `CARPET/*` a carpet. `dotbsp/source_textures.tsv` is the one list: `pattern<TAB>material<TAB>tint`, reviewable as a diff.

* `pattern` is a source texture name (matching ignores case) with `*` and `?` wildcards. The map's own folder (`MAPS/<map>/`) and a cubemap suffix are stripped first.
* `material` is a generic id, what the surface *is*: `wood_floor`, `parquet`, `carpet`, `tile_floor`, `tile_wall`, `plaster_painted`, `plaster_worn`, `wallpaper`, `wallpaper_decrepit`, `concrete`, `brick_red`, `stone_wall`, `wood_planks`, `ceiling`, `roof_tiles`, `snow`, `mud`, `metal`, `door_wood`, `glass`, `grass`, `water`, `flat`. A game draws each id from its own art; an id it does not know is drawn flat.
* `tint` (`r,g,b` in 0..1 or `#rrggbb`) keeps the colour the mapper meant, so one carpet is a blue office and a red hall.
* The **most specific row wins**, not the first: an exact name beats any glob, a glob with more literal characters beats a shorter one, a tie goes to the earlier line. Order in the file is for the reader.

`texturemap.load()` returns a `TextureMap`; `docboxes.majority_material(names, table, default)` takes it where it took the old list. `python3 -I tools/bsp/bsp.py unmapped <maps...>` (`--top N`, `--json`, `--strict`) lists every texture of the given maps that hits no row, with face counts and the maps it is in. A texture that turns up there gets a row in the list, not a line in an importer.

Used by murder-mystery-maps' `import_bsp.py`. **Next (not done): the other importers keep their own `TEXTURE_MAP`s and still work** (hide-n-seek-maps, mg-prop-hunt-maps, mg-deathrun-maps, mg-wipeout-maps, zombie-zone-maps, g2gfast-maps, game-playground-maps), because each names its own game's material ids (`paint`, `plaster`, `tile`...). Moving one is a mapping from the generic ids to that game's ids in its adapter, then deleting its table; `test_material_helpers_match_every_copy` compares the old tables, so it goes with them.
