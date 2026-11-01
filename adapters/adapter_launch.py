"""Runs an adapter that lives in dot-map-convert/adapters/<repo>/ as if it still sat in the map repository's tools/.

A map repository's `tools/<name>.py` is a three-line launcher that calls `run(globals(), "<repo>", "<name>.py")`. The code is compiled
from here but executes in the launcher's namespace, so `__file__`, `__name__` and `__doc__` are the launcher's: the adapter's
repo-relative paths (HERE/../maps) and its sibling imports (build_maps, ambient) keep resolving in the map repository, and
`import import_bsp` from a sibling script still works.
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(g, repo, name):
    path = os.path.join(ROOT, "adapters", repo, name)
    with open(path, encoding="utf-8") as f:
        src = f.read()
    g["__doc__"] = ast.get_docstring(ast.parse(src), clean=False)
    exec(compile(src, path, "exec"), g)
