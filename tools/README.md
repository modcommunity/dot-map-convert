# What is where

Everything that converts a map, a model, a texture or a sound lives in this repository; a map or game repository keeps only its data (specs, rules, the converted documents) and thin launchers. Runtime code stays in the addons (`dot-map/addons/dot_map/*.gd`).

| Where | What |
| --- | --- |
| `bsp.py`, `dotbsp/` | the converter: reader, store, intermediate, mesh, `regen`, licence pass |
| `dotbsp/*.tsv`, `rules/` | the mapping tables: original texture, model and sound to its free replacement (or kept), classes, materials, PBR and model picks |
| `defs/` | entity definitions to `io/catalogue.json` |
| `tools/models/` | Blender (headless) scripts for the hand-made fixture models |
| `tools/bake_textures.gd`, `art_coverage.py` | texture bake (run with `godot --path ../dot-map --script`) and the art coverage report |
| `tools/audit_maps.py`, `audit_passes.py` | the shared audit of a maps repository's documents against their source maps (lost brushes and floor; recorded per-map exemptions in the repository's `tools/audit_exempt.json`), and the attribution of that loss to the importer pass that removed the boxes (`dotbsp/passledger.py`; import with `DOTBSP_PASS_LEDGER=1` to write `<document>.passes.json`) |
| `tools/build_provides.py` | the one writer of a maps repository's `provides.json`; each repository's `tools/build_provides.py` is a config |
| `tools/regen_worlds.sh`, `stage_stores.sh` | regenerate a maps repository's worlds from the store; stage the raw stores |
| `adapters/<repo>/` | the per-game importers (a game's own map document from an intermediate or a `.bsp`) and their checks |
| `adapters/adapter_launch.py` | runs an adapter in its map repository's namespace |

## Adapters

`<repo>/tools/<name>.py` is a three-line launcher that runs `adapters/<repo>/<name>.py` here with the launcher's `__file__`, so the adapter's paths relative to the map repository (`maps/`, `world/`, `tools/bsp/`) and its sibling imports (`build_maps`, `ambient`) behave as before. Edit the adapter here, never the launcher. Run a script exactly as before: `python3 -P tools/import_bsp.py ...` from the map repository.

| Adapter | Does |
| --- | --- |
| `zombie-zone-maps/import_bsp.py`, `build_worlds.py`, `auto_spec.py`, `completeness.py`, `coverage_report.py`, `check_worlds.py`, `make_stores_licence.py` | Zombie Zone document, drawn world, spec from a store entry, and the checks on them |
| `hide-n-seek-maps/import_bsp.py`, `murder-mystery-maps/import_bsp.py`, `game-playlot-maps/import_bsp.py` | those games' box documents |
| `mg-prop-hunt-maps/import_bsp.py`, `bsp_environment.py` | prop-hunt document and its environment pass |
| `mg-wipeout-maps/import_world.py` | wipeout course from a regenerated world |
| `mg-deathrun-maps/bsp_to_course.py`, `plan_route.py`, `draft_spec.py` | deathrun course from a spec, the route planner over the document the importer would write, and the first spec for a community map |
| `mg-look-at-me/bsp_layout.py` | floor skeleton (rooms on the 4 m grid) from an intermediate |
| `game-g2gfast/bsp_import.py`, `bsp_mechanics.py`, `bsp_props.py`, `vtf.py`, `stock_*.py`, `vrf_import.py`, `teleport_traps.py`, `migrate_batch.py` | the g2gfast mesh, lightmap and texture pipeline, its stock-asset stand-ins and surveys Also the arena maps: per-side spawns (`team` red/blue from `TeamNum`), `control_points`, `resupply` and the authored `flag_spawns` and `modes` of `zones/<id>.json` land in the manifest. `bsp_import.py` also writes `collision.hull_kinds` (hull indexes by kind: clip, glass, fence, sky; absent = all solid) from `dotbsp.materials.hull_kind`, the rule the drawn mesh uses; `migrate_batch.py` re-imports a batch headlessly (and with `--regen` runs `bsp.py regen g2g/<id>`) and writes a TSV of hull counts and kinds. |

## Stayed in the map and game repositories, on purpose

- `build_maps.py`, `ambient.py`, `worlds.tsv`, `prop_sizes.json`, `tools/bsp/*.json`, `tools/convert/` (specs, ship lists, per-map rules): the game's own data and hand authoring.
- `bsp_read.py` shims: they only name the reader for the adapter.
- `relight.sh`, `solid_props.sh`, `publish*.sh`, `g2gmaps.py`: a game's pipeline and publishing around the converter, not conversion.
- `mg-deathrun-maps` `apply_theme.py`: a table of per-map looks written into specs (the game's own data).
- `arena-dm-maps`, `arena-surf-dm-maps`, `hide-n-seek-maps` `tools/regen_worlds.sh`: launchers (or, for hide-n-seek, a `worlds.tsv` loop) over the shared script; `stage_packs.sh` differs per repository in its publish rule and stays.
- `zombie-zone-maps` `regen_all.sh`, `ship_*.sh`: they read that game's `convert/ship.tsv`, specs and ship lists; the generic loop is `tools/regen_worlds.sh` here.
- `dot-map/tools/*.gd|sh`: need a Godot project (screenshots, benches, occluder bake).
