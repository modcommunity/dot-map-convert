# defs

`build.py` generates `../rules/entity_defs.json`, the class catalogue: for every entity class its bases, keys (type, default, choice values), inputs and outputs, and which sources confirmed it (`fgd`, `css`, `l4d2`). `dotbsp/defs.py` reads it (`resolve` folds the bases in).

The file is derived data only: names, types and defaults, never descriptions or the definition files. The generator reads the definition files and the datamap dumps from outside the repository (`$DOTBSP_DEFS`, default `~/mapsrc/defs`, dumps in `../dumps`), so regenerating needs that machine:

    heavy -- python3 -I tools/bsp/defs/build.py        # rewrite
    heavy -- python3 -I tools/bsp/defs/build.py --check  # fail when stale

`map_classes` counts the distinct maps under `~/mapsrc` using each class and `unknown` lists those the catalogue lacks (mod-specific classes). The `gmod` dump held no datamaps, so it confirms nothing. Tests: `python3 -I tools/bsp/tests/test_defs.py`.
