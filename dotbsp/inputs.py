"""Which inputs the runtime implements, read from the GDScript so the list cannot drift.

`DotMapIO._init` maps a class name to a component script; each component answers inputs in
`match name:` blocks (its own `_input`, or `DotMapEntity.accept` for the ones every entity has).
A component with several kinds in one file (movers: doors, buttons, trains) counts as the union,
so this under-reports an input a sibling kind implements: it never claims one that nothing does.
"""

import os
import re

IO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                      "addons", "dot_map", "io")
_cache = {}


def _read(name):
    with open(os.path.join(IO_DIR, name), encoding="utf-8") as f:
        return f.read()


def _match_inputs(text):
    """Lowercase string cases of every `match name:` block (the input name variable) in `text`."""
    out, depth = set(), None
    for line in text.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip("\t"))
        if depth is not None and stripped and indent <= depth:
            depth = None
        if stripped == "match name:":
            depth = indent
            continue
        if depth is not None and indent == depth + 1 and stripped.endswith(":"):
            out.update(re.findall(r'"([^"]+)"', stripped))
    return out


def _tables():
    if _cache:
        return _cache
    files, parents = {}, {}
    for fn in sorted(os.listdir(IO_DIR)):
        if not fn.endswith(".gd"):
            continue
        text = _read(fn)
        m = re.search(r"^class_name (\w+)", text, re.M)
        if m:
            e = re.search(r"^extends (\w+)", text, re.M)
            files[m.group(1)] = _match_inputs(text)
            parents[m.group(1)] = e.group(1) if e else None
    io = _read("dot_map_io.gd")
    init = io[io.index("func _init()"):]
    init = init[:init.index("\n\n\n")]
    classes = dict(re.findall(r'"(\w+)":\s*(DotMap\w+)', init))
    for names, comp in re.findall(r"for \w+ in \[([^\]]*)\]:\s*\n\s*_classes\[\w+\] = (\w+)", init):
        for n in re.findall(r'"(\w+)"', names):
            classes[n] = comp
    _cache.update(files=files, parents=parents, classes=classes)
    return _cache


def component_of(classname):
    """The component script the runtime builds for `classname`, 'DotMapEntity' when none is registered."""
    return _tables()["classes"].get(classname, "DotMapEntity")


def implemented(classname):
    """The lowercase inputs an entity of `classname` accepts: its component, the scripts it extends, DotMapEntity."""
    t = _tables()
    out, c = set(), component_of(classname)
    while c and c in t["files"]:
        out |= t["files"][c]
        c = t["parents"].get(c)
    return out


def unimplemented(bsp, links):
    """Sorted 'class.input' for every input a map's links send to a class whose component does not implement it.
    Specials (console commands, the player, !activator) have no entity and are not counted."""
    out = set()
    for k in links:
        for i in k["to"]:
            c = bsp.entities[i].get("classname", "")
            if k["input"].lower() not in implemented(c):
                out.add("%s.%s" % (c, k["input"]))
    return sorted(out)
