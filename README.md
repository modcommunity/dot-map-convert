# dot-map-convert: the family's one BSP map converter

Reads community maps in the VBSP v19-21 format, inventories a folder of them, and writes each as one documented intermediate JSON that a game's thin adapter turns into that game's own map document. Python 3, standard library only (plus `unrar` or `7z` on the path to list `.rar`/`.7z` downloads, and `fastgmad` for `.gma` workshop archives).

It is the one place the family reads Source-engine (VBSP) maps. A map repository keeps only its data and a thin adapter; the reader, the brush cutter, the texture, model and sound mapping and the audits live here, so a fix reaches every game.

## Quick start

Always run it as `python3 -P` (never `-I`, which hides numpy): maps are downloads, and `-P` stops a planted module beside one from being imported. Archives are read in memory; nothing is extracted to disk.

```bash
python3 -P bsp.py list ~/mapsrc --markdown                 # inventory a folder of maps
python3 -P bsp.py convert map.zip --out map.json --author "A" --page https://... --licence "CC BY-NC-ND 4.0" --no-share-check "2026-10-19: none"
python3 -P bsp.py import map.bsp --game zz --out <map repo>/world/<id>/<id>   # raw import, then the licence pass
python3 -P bsp.py regen <hash | game/map> --out <prefix>   # rebuild a map from the store and the rules
python3 -P bsp.py audit map.bsp --mesh world/map           # every solid brush and standable top vs the output; exit 1 on loss
python3 -P bsp.py unmapped ~/mapsrc --top 40               # textures that hit no row of source_textures.tsv
```

The converter finds the dot-map addon it writes into as the sibling checkout `../dot-map` (or `$DOT_MAP_DIR`). A game finds the converter as `../dot-map-convert` (dot-bootstrap makes it) or `$DOTBSP_PATH`. Python 3, standard library only, plus `unrar` or `7z` for `.rar`/`.7z` downloads and `fastgmad` for `.gma` workshop archives.

## Commands

| Command | What it does |
| --- | --- |
| `list` | Inventory maps in folders and archives; `--converted` marks those a map repository already has |
| `convert` | One map to the documented intermediate JSON (see below) |
| `mesh` | The drawn mesh, collision hulls and movers, as `<prefix>.json` and `<prefix>.bin` |
| `import` | The raw import into the store, then the licence pass that swaps every texture, model and sound for a free stand-in |
| `store` | Copy maps into `$DOTBSP_STORE` (default `~/mapsrc/store`, outside every repository) with their credit |
| `regen` | Rebuild a map's manifest, textures and `CREDITS.md` from the store and the rules; `--ratchet` fails if coverage drops |
| `audit` | Check the output keeps every player-solid brush and walkable top |
| `unmapped`, `classes`, `modeldims`, `modelmap`, `pbrmap`, `standins` | Coverage reports and the mapping steps for textures, entity classes and models |
| `storepack`, `bundle` | Ship the texture and model stores as dot-cloud slices, or make a world self-contained for a map pack |

## How an import works

1. **Raw import**, outside every repository, at `<root>/<game>/raw/<map>/` (`--raw-root`, `$DOTBSP_RAW_ROOT`, default `~/mapsrc`): the mesh, every entity key, a texture and model census and the packed file list.
2. **Licence pass** (only with `--out`): each surface maps through `free_textures.tsv` to a CC0 PBR set from [ambientCG](https://ambientcg.com) or to a generated image in the original's average colour; each placed model to a free stand-in; each sound to a CC0 sound or silence. Only CC0, MIT and public-domain stand-ins are accepted. The manifest records every replacement with its URL, author and licence.
3. **Environment and sound** (sky, sun, fog, tone map, ambient sounds) ship as data that `DotMapBspMesh` applies at load. The author's own baked lightmap is imported too (`dotbsp/lightmap.py`).

Rules are read in four tiers, from the least to the most specific: default, addon, game, map. A tier is a folder of `textures.tsv`, `free_textures.tsv`, `models.tsv`, `sounds.tsv`, `classes.tsv`, `materials.tsv` and `roles.tsv`. `regen` writes `<prefix>.coverage.json`, which lists what each tier answered and every name that fell through.

The shared texture list `dotbsp/source_textures.tsv` has one row per pattern: `pattern<TAB>material<TAB>tint`. The most specific row wins (an exact name beats a glob, a longer glob beats a shorter one). A texture with no row shows up in `bsp.py unmapped`; add a row there, not a line in an importer.

The split: this converter reads the format and cuts brushes into boxes. The game's adapter decides what an entity means (which class is a spawn, which brush is a gate) and writes the game's own document. Adapters live in `adapters/<repo>/`; see [tools/README.md](tools/README.md) for what is where.

## Tests

```bash
python3 -P tests/test_dotbsp.py        # reader, boxes, intermediate, on maps written from scratch
python3 -P tests/test_mesh.py          # mesh, movers and the class table
python3 -P tests/test_licence.py       # raw store, licence pass, environment and sound data
python3 -P tests/test_regen.py         # rule tiers, fallbacks, regen, coverage ratchet
python3 -P tests/test_store.py         # the lossless store
python3 -P tests/test_audit.py         # the brush and floor audit
python3 -P tests/test_readers.py       # the reader plugin interface
python3 -P tests/test_texturemap.py    # the shared texture list
python3 -P tests/test_lift.py          # the shared helpers (flood, classifier, props, lights, plan, .gma)
python3 -P tests/test_provides_licence.py
DOTBSP_TEST_MAPS=~/maps python3 -P tests/test_dotbsp.py RealMaps   # and on real maps
```

## Layout

Per-game importers are in `adapters/<repo>/` (launchers stay in each map repository); see [tools/README.md](tools/README.md) for what is where.

| File | What it is |
| --- | --- |
| `dotbsp/reader.py` | `Bsp`: lumps (LZMA too), brushes and hulls, the BSP-tree walk to a model's brushes, faces, displacements, static props, the packed zip; unit and axis helpers |
| `dotbsp/audit.py` | `audit(bsp, out)`: every brush the map's models reach by owner class and CONTENTS kind (solid, detail, window, grate, ladder, clip, playerclip, npcclip, water, slime, sky, nodraw, origin, areaportal), which player-solid ones the output collides with, and a walk test (a 24-unit grid on every exposed top with body room above, inside the sealed world) asking the output for ground under each point; `Hulls` reads a mesh, `Boxes` a box document |
| `dotbsp/boxes.py` | `decompose(planes, hull)`: a brush as boxes, the union of the converters' fixes |
| `dotbsp/docboxes.py` | the importers' shared passes over a *document's* boxes (metres, Godot axes): `within`, `classify_material`, `brush_material_names`, `majority_material`, `suburban_surface`, `widen_doors`, `drop_door_leaves`, `add_doors`, `prune_far_scenery`, `prune_pockets`, `scatter_cover` |
| `dotbsp/intermediate.py` | `build(bsp, credit)` writes the intermediate; `summary` is what `list` prints; `check(doc)` before trusting one |
| `dotbsp/readers.py` | the reader plugin interface: `Reader(name, kind, extensions, read)`, `register`, `read(path, licence=...)` (refuses an input without author, URL and an accepted licence; attaches the record to the result), `load_plugins` (`$DOTBSP_READERS`); built in: `bsp-map`. Model, texture, heightmap and sound readers are plugins still to write |
| `dotbsp/sources.py` | finding maps in folders and archives; which game a prefix belongs to; which maps the `*-maps` repositories already have |
| `dotbsp/units.py` | the two scales (`VISUAL` 0.01905, `HULL` 0.0254), `to_game`, `from_metres` |
| `dotbsp/entities.py` | the entity classifier (`classify_entity`), the brush classifier (`classify_brush`), `teleports` / `teleport_destination` / `pad_rect` |
| `dotbsp/mdl.py`, `dotbsp/vtf.py`, `dotbsp/models.py` | the models a map packs in its pakfile: `mdl.parse` (studio v44-49 with vvd and the dx90 strips, LOD 0, body group 0) to triangles and `to_glb`; `vtf.read` (DXT1/3/5, BGRA, RGB, I8) to a PNG and `base_texture` of a vmt; `models.extract(bsp, dir)` writes `<raw>/models/<path>.glb` (textures embedded) and `models.json` (triangles, bounds, size and centre in metres, materials with average colours); `models.measure(bsp)` is the sizes alone, in memory, for an importer; `match_size` / `compatible` pick the catalogue prop of a measured shape. `standins.shape_matches` is the converter's own use of it: a placed model no name row knows, that the map packs, gets the nearest of the neutral blocks, drums and rocks in `free_model_dims.tsv` by measured shape (limit 0.4, nothing under 8 cm, over 3.5 m or a flat slab), set down on the model's middle at its measured longest side, with `shape: true` in the manifest's `props` and the stand-in credited like any other. Raw store only: the author's art is never shipped, a game's table of free props is chosen by the measured shape |
| `dotbsp/vpk.py`, `docs/vpk.md` | the base-game archives (`*_dir.vpk`, CRC-checked) and an internal-only decoded-texture cache, both outside git; Valve assets never committed or published |
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

The adapters in `adapters/` convert a map into each game's own document. A map repository (for example fc-dm-maps or zombie-zone-maps) keeps its data and a thin launcher that calls into this converter.

## Credits and removal

Converted maps keep their authors' credit and licence; each map's `CREDITS.md` lists them. If you made one of these maps and want it removed, open an issue.
