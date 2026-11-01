"""Where the dot-map addon lives, relative to this repository."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def dot_map_dir():
    """The dot-map checkout: $DOT_MAP_DIR, else the sibling directory."""
    return os.environ.get("DOT_MAP_DIR") or os.path.join(os.path.dirname(REPO), "dot-map")


def addon_dir():
    return os.path.join(dot_map_dir(), "addons", "dot_map")
