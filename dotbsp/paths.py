"""Where the dot-map addon lives, relative to this repository."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def dot_map_dir():
    """The dot-map checkout: $DOT_MAP_DIR, else the sibling directory, else (in a git
    worktree, whose siblings are other worktrees) the sibling of the main checkout."""
    if os.environ.get("DOT_MAP_DIR"):
        return os.environ["DOT_MAP_DIR"]
    sib = os.path.join(os.path.dirname(REPO), "dot-map")
    if not os.path.isdir(sib):
        main = _main_checkout()
        if main and os.path.isdir(os.path.join(os.path.dirname(main), "dot-map")):
            return os.path.join(os.path.dirname(main), "dot-map")
    return sib


def _main_checkout():
    """The main checkout this worktree belongs to (None when this is not a worktree)."""
    git = os.path.join(REPO, ".git")
    try:
        if os.path.isfile(git):                 # "gitdir: <main>/.git/worktrees/<name>"
            gd = open(git).read().split("gitdir:", 1)[1].strip()
            return os.path.dirname(os.path.dirname(os.path.dirname(gd)))
    except (OSError, IndexError):
        pass
    return None


def addon_dir():
    return os.path.join(dot_map_dir(), "addons", "dot_map")
