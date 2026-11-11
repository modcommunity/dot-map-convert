#!/bin/bash
# Store each map's source .bsp and rebuild its world for a converted-maps repository.
#   [SRC=dir] [GAME=arena] tools/regen_worlds.sh <maps repo> [map ids...]
# Credit comes from <maps repo>/maps.json (id, author, source) or else maps/<id>/licence.json.
# Default ids: every maps/<id>. Writes worlds/<id>/<id>.*; art stores are <repo>/.stores/{pbr,model}-library when
# .stores exists (the dot-bootstrap lock-store layout the committed manifests point at), else <repo>/{pbr,model}-library.
set -u
# HEAVY= (empty) runs the regen unqueued, for a box without heavy (gpu.sh py).
HERE="$(cd "$(dirname "$0")" && pwd)"
BSP="${DOTBSP_PATH:-$HERE/..}/bsp.py"
ROOT="$(cd "${1:?usage: regen_worlds.sh <maps repo> [ids...]}" && pwd)"; shift
SRC="${SRC:-$ROOT/sources}"; GAME="${GAME:-arena}"
STORES="$ROOT"; [ -d "$ROOT/.stores" ] && STORES="$ROOT/.stores"
ids=("$@"); [ ${#ids[@]} -eq 0 ] && ids=($(ls "$ROOT/maps"))
rc=0
for m in "${ids[@]}"; do
    f="$(find "$SRC/" -maxdepth 2 -iname "*$m.bsp" | head -1)"
    [ -z "$f" ] && { echo "$m NO SOURCE"; rc=1; continue; }
    read -r author page < <(python3 -P -c 'import json,sys
r,m=sys.argv[1:3]
try:
    for e in json.load(open(r+"/maps.json"))["maps"]:
        if e["id"]==m: print(e.get("author","unknown").replace(" ","_"), e.get("source","-").replace(" ","_")); sys.exit()
except Exception: pass
try:
    for e in json.load(open(r+"/maps/"+m+"/licence.json")):
        if e.get("author") and e.get("source_url"): print(e["author"].replace(" ","_"), e["source_url"]); sys.exit()
except Exception: pass
print("unknown -")' "$ROOT" "$m")
    python3 -P "$BSP" store "$f" --game "$GAME" --author "${author//_/ }" --page "${page//_/ }" --licence "none stated" --no-share-check "credited with removal on request" > /dev/null 2>&1
    mkdir -p "$ROOT/worlds/$m"
    ${HEAVY-heavy --} timeout 1800 python3 -P "$BSP" regen "$GAME/$(basename "$f" .bsp | tr A-Z a-z)" --out "$ROOT/worlds/$m/$m" --pbr-store "$STORES/pbr-library" --model-store "$STORES/model-library" > "${TMPDIR:-/tmp}/regen-$m.log" 2>&1 < /dev/null
    r=$?; [ $r -ne 0 ] && rc=1
    echo "$m exit $r"
done
exit $rc
