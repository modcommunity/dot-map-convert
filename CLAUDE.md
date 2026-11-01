# dot-map-convert

The family's one map converter: community BSP maps (VBSP v19-21) to the documented intermediate, the drawn mesh and the per-game manifests, plus every table that maps an original texture, model or sound to its free replacement or records that it is kept. Python 3 standard library only, no Godot project. It moved here from `dot-map/tools/bsp` on 2026-11-01 with its history; the engine-runtime code stays in `dot-map`.

Read README.md first (layout, rule tiers, the lossless store, the intermediate).

## Rules

- **One converter.** A reader fix, a table row or a class definition goes here, never into a game or map repository. Game adapters (`<maps repo>/tools/import_*.py`) stay thin and import `dotbsp` from here.
- **Always `python3 -I`.** Maps are downloads.
- **Finding things.** Callers find this checkout as the sibling `../dot-map-convert` or `$DOTBSP_PATH` (or `$DOT_MAP_CONVERT_PATH` for the tools). This converter finds the dot-map addon (assets, `io/catalogue.json`) through `dotbsp/paths.py`: sibling `../dot-map` or `$DOT_MAP_DIR`.
- **Output must not drift.** Changing a table or rule changes every regenerated manifest; prove a refactor with a `regen` before and after and compare hashes.
- Mapping tables carry source, URL, author and licence per row; only CC0-1.0, MIT and public-domain replacements (`licence.check` refuses the rest).
- Family conventions apply: short `##`/`#` comments that say why, markdown never hard-wrapped, no other game or engine named in public files.

## Checks

Each suite is `python3 -I tests/test_<name>.py` from this directory (all of them are headless and need no maps; `DOTBSP_TEST_MAPS=<dir>` adds real ones). `tests/test_defs.py` needs the entity definition checkout only for its optional case. Run the suites that cover what you touched; run all of them once before committing.

## Not here

`addons/dot_map/*.gd` (runtime), and the screenshot and bench helpers that need a Godot project (`dot-map/tools/`). `bake_textures.gd` is here but runs as `godot --path ../dot-map --script <abs path>`.
