# Base-game archives (internal only)

`dotbsp/vpk.py` reads Valve package archives (`*_dir.vpk` plus numbered parts, v1 and v2, CRC-checked) and keeps a decoded-texture cache, so an `_orig` conversion can show a base-game surface instead of prototype paint.

- **Internal only.** These are Valve's assets. The archives live in `~/mapsrc/basegame` and the cache in `~/mapsrc/basegame/cache`, both outside git; `TextureCache` refuses a directory inside a repository. Nothing from them is committed or published. Published packs use the free swaps in `free_textures.tsv`.
- **Install** (anonymous, no account): `steamcmd +force_install_dir ~/mapsrc/basegame/<app> +login anonymous +app_update <app> validate +quit` for the dedicated servers: CS:S 232330, HL2:DM 232370, DoD:S 232290, GMod 4020, SDK Base 2013 MP 243750, TF2 232250.
- **Gap.** The HL2 dedicated-server installs list `hl2_textures_dir.vpk` but ship no data parts, so the HL2 base textures (`brick/`, `concrete/`, ...) come only from a full game or from the servers that carry them; `BaseGame` skips an archive whose part is missing. CS:S textures are complete.
- Use: `BaseGame().material(name)` gives (vmt keys, vtf bytes); `TextureCache().png(name)` a cached PNG.
