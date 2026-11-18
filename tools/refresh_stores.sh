#!/bin/bash
# Bring a maps repository's raw model store up to date with the model library, so it cannot go stale.
#   tools/refresh_stores.sh <maps repo> [library]      (library: $GS_MODEL_LIBRARY, $DOT_MODEL_LIBRARY, ~/art-library/models)
# `<maps repo>/.stores/model-library` is mostly symlinks into the library, made once; a model added to the library later (a new
# kit, a new `own` stand-in) was missing and storepack/regen failed on it. This adds a link for every library file the store lacks
# (or links to nothing), and never touches a file already there (regen writes real copies of generated models, `.import` files
# are the engine's). Idempotent; prints the number of links added.
set -euo pipefail
[ $# -ge 1 ] || { echo "usage: tools/refresh_stores.sh <maps repo> [library]" >&2; exit 2; }
DEST="$(cd "$1" && pwd)/.stores/model-library"
LIB="${2:-${GS_MODEL_LIBRARY:-${DOT_MODEL_LIBRARY:-$HOME/art-library/models}}}"
[ -d "$LIB" ] || { echo "refresh_stores: no model library at $LIB" >&2; exit 2; }
[ -d "$DEST" ] || { echo "refresh_stores: $DEST does not exist (stage it with tools/stage_stores.sh)" >&2; exit 2; }
LIB="$(cd "$LIB" && pwd)"
n=0
while IFS= read -r -d '' f; do
    rel="${f#"$LIB"/}"
    [ -e "$DEST/$rel" ] && continue
    mkdir -p "$DEST/$(dirname "$rel")"
    ln -sfn "$f" "$DEST/$rel"
    n=$((n + 1))
done < <(find "$LIB" \( -type f -o -type l \) -print0)
echo "refresh_stores: $n links added to $DEST"
