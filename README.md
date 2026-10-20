# tools/bsp: the family's one BSP map converter

Reads community maps in the VBSP v19-21 format, inventories a folder of them, and writes each as one documented intermediate JSON that a game's thin adapter turns into that game's own map document. Python 3, standard library only (plus `unrar` or `7z` on the path to list `.rar`/`.7z` downloads, and `fastgmad` for `.gma` workshop archives).

```bash
python3 -I tools/bsp/bsp.py list ~/godot/inspirations/g2gfast --converted ~/godot --markdown
python3 -I tools/bsp/bsp.py convert map.zip --out map.json --author "A" --page https://... --licence "CC BY-NC-ND 4.0" --no-share-check "2026-10-19: none"
python3 -I tools/bsp/tests/test_dotbsp.py            # 26 tests on maps written from scratch
python3 -I tools/bsp/tests/test_lift.py              # the pieces lifted from the adapters (flood, classifier, props, lights, plan, .gma, guards)
DOTBSP_TEST_MAPS=~/maps python3 -I tools/bsp/tests/test_dotbsp.py RealMaps   # and on real ones
```

Always `python3 -I`: the maps are downloads, and `-I` keeps a planted module beside one from being imported. Archives are read in memory (zip by `zipfile`, rar by `unrar p`, 7z by `7z e -so`); nothing is extracted to disk and no path inside an archive is used as a path.

## Why here, and why not in the games

Six copies of the reader and five box converters had grown in the map repositories and in game-g2gfast, each with a fix the others lacked (the table below). A reader fix reached one game. It lives in dot-map because dot-map is the content addon every map-using game already links and clones beside itself, and outside `addons/dot_map` so it never ships in an addon copy or a pack (`.gdignore` keeps Godot from scanning it). A game finds it as the sibling checkout `../dot-map/tools/bsp` that dot-bootstrap makes, or at `$DOTBSP_PATH`.

The split is: dot-map reads the format and cuts brushes into boxes; the game decides what an entity means (which class is a spawn, which brush entity is a gate, which material is glass) and writes its own document. That is the adapter, and it is the only per-game part.

## Layout

| File | What it is |
| --- | --- |
| `dotbsp/reader.py` | `Bsp`: lumps (LZMA too), brushes and hulls, the BSP-tree walk to a model's brushes, faces, displacements, static props, the packed zip; unit and axis helpers |
| `dotbsp/boxes.py` | `decompose(planes, hull)`: a brush as boxes, the union of the converters' fixes |
| `dotbsp/intermediate.py` | `build(bsp, credit)` writes the intermediate; `summary` is what `list` prints; `check(doc)` before trusting one |
| `dotbsp/sources.py` | finding maps in folders and archives; which game a prefix belongs to; which maps the `*-maps` repositories already have |
| `dotbsp/units.py` | the two scales (`VISUAL` 0.01905, `HULL` 0.0254), `to_game`, `from_metres` |
| `dotbsp/entities.py` | the entity classifier (`classify_entity`), the brush classifier (`classify_brush`), `teleports` / `teleport_destination` / `pad_rect` |
| `dotbsp/props.py` | `PropTable` and `placed_props`: a map's placed models (entities and static props) matched to a game's own, `model_census` |
| `dotbsp/lights.py` | `to_game` (lights to metres, range and energy, suns apart), `thin`, `auto` |
| `dotbsp/gamebox.py` | `model_boxes`: a model's brushes as game-metre boxes with the source material and kind |
| `dotbsp/flood.py` | `Flood`: reachable space over boxes with step, jump, drop and head room; `floor_rects`, `keep_starts` |
| `dotbsp/plan.py` | `extract`: a room plan from walls that do not close (seal, outside flood, doorway erosion, rooms on a coarse grid) |
| `dotbsp/gma.py` | `.gma` workshop archives through fastgmad (`sources.find` and `bsp.py` take a `.gma` like a zip) |
| `bsp.py` | the CLI |
| `tests/` | `synth.py` writes a small VBSP file from scratch (v19, v20, v21 in both record orders, a brush entity); `test_dotbsp.py` |

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
| `credit` | `author`, `page`, `licence`, `no_share_check` (when and what the page said about sharing), `notes`, and any other key the caller passed (a credit line for the map-change screen). `convert` warns when there is no author or page |
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
- `lights.thin` against murder-mystery-maps: NOT equivalent. The original keeps lights in document order and widens a minimum gap by 0.5 m until at most `max_lights` fit, then raises range and energy of the survivors; `thin` keeps the brightest first at a fixed spacing. An adapter that wants the original result keeps its own loop.
- `Flood.keep_starts` against murder-mystery-maps' start filter: the same "8 m below the median start" rule, plus a dropped start with no floor under it.
- `PropTable` against prop-hunt-maps' `PROP_MAP`: that table keys by file stem; a key with no "/" now matches that way, a key with a folder matches the whole path.
- `Flood.prune_pockets` against hide-n-seek-maps: not equivalent (see the table above); the original uses a 0.1 m grid.
- wipeout has no importer, only `tools/build.py`: nothing to compare.
