#!/bin/bash
# Stage a converted-maps repository's raw art stores (`.stores/pbr-library`, `.stores/model-library`, the folders its worlds'
# `licence.pbr_store` and `model_store` name) so a checkout draws the worlds with full art and no dot-cloud slices, and link
# them into each game that draws those worlds (`<game>/.stores`, kept out of git through the game's .git/info/exclude).
#   tools/stage_stores.sh <maps repo> [--from SRC] [--game <game project>]...
# SRC (or $DOT_STORES_FROM) is an rsync source holding pbr-library/ and model-library/ (`host:path/.stores`), a local folder,
# or an http(s) URL of a .tar of them. Re-running fetches only what changed. Without it a world draws its low-detail stand-ins.
set -euo pipefail
die() { echo "stage_stores: $*" >&2; exit 2; }
[ $# -ge 1 ] || die "usage: tools/stage_stores.sh <maps repo> [--from SRC] [--game <game project>]..."
MAPS="$(cd "$1" && pwd)"; shift
FROM="${DOT_STORES_FROM:-}"
GAMES=()
while [ $# -gt 0 ]; do
    case $1 in
        --from) FROM="${2:?--from needs a source}"; shift 2 ;;
        --game) GAMES+=("${2:?--game needs a project}"); shift 2 ;;
        *) die "unknown argument $1" ;;
    esac
done
[ -n "$FROM" ] || die "no source: --from host:path/.stores, a folder, or a .tar URL (see dot-map docs/content.md#without-the-slices)"
DEST="$MAPS/.stores"
mkdir -p "$DEST"
case $FROM in
    http://*|https://*)
        curl -fL --retry 3 "$FROM" | tar -x -C "$DEST" ;;
    *)
        # The slice build project beside the stores is tens of GB and never needed to draw.
        rsync -a "$([ -t 1 ] && echo --info=progress2 || echo --info=stats1)" --exclude '/project/' --exclude '/slices/' "${FROM%/}/" "$DEST/" ;;
esac
for d in pbr-library model-library; do
    [ -d "$DEST/$d" ] || die "$FROM has no $d/"
done
# Two GB of webp and glb read from files; an editor importing them would double that in .godot/.
[ -e "$DEST/.gdignore" ] || touch "$DEST/.gdignore"
for g in "${GAMES[@]}"; do
    g="$(cd "$g" && pwd)"
    if [ -e "$g/.stores" ] && [ ! -L "$g/.stores" ]; then
        echo "stage_stores: $g/.stores is a real folder, left alone" >&2
        continue
    fi
    ln -sfn "$(realpath --relative-to="$g" "$DEST")" "$g/.stores"
    ex="$(git -C "$g" rev-parse --git-path info/exclude 2>/dev/null || true)"
    [ -n "$ex" ] && { case $ex in /*) ;; *) ex="$g/$ex" ;; esac; grep -qx '/.stores' "$ex" 2>/dev/null || echo '/.stores' >> "$ex"; }
    echo "linked $g/.stores"
done
echo "staged $(du -sh "$DEST/pbr-library" | cut -f1) of PBR sets and $(du -sh "$DEST/model-library" | cut -f1) of models in $DEST"
