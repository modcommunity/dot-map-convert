"""Which entity classes of a map nothing converts, and the check that none is left unlisted.

A class is converted when its treatment is not `data` (geometry, a mover, a volume, a point the
games read) or when `classes.tsv` names a DotMapIO component for it. What stays is `unconverted`:
kept verbatim as `data` with the generic component (every input recorded, nothing run), or with
no row at all. `rules/unconverted_ignore.tsv` (class or `prefix*`, a reason) lists what no game
needs run; anything else on a map and not on that list fails `check`, so a new class is a
decision and a map with a gameplay entity nobody converted is not shipped by accident.
"""

import collections
import os

from . import classes

IGNORE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules", "unconverted_ignore.tsv")


def load_ignore(path=None):
    """([(class, reason)] exact, [(prefix, reason)]) from the tsv; a row without a reason is an error."""
    exact, prefixes = {}, []
    with open(path or IGNORE_PATH, encoding="utf-8") as f:
        for n, line in enumerate(f.read().splitlines(), 1):
            if not line.strip() or line.startswith("#"):
                continue
            c = line.split("\t")
            if len(c) < 2 or not c[1].strip():
                raise ValueError("%s:%d: %r has no reason" % (path or IGNORE_PATH, n, c[0]))
            if c[0].endswith("*"):
                prefixes.append((c[0][:-1], c[1].strip()))
            else:
                exact[c[0]] = c[1].strip()
    return exact, prefixes


def is_converted(classname):
    t = classes.treatment(classname)[0]
    return t is not None and (t != "data" or classes.component(classname) != "DotMapEntity")


def ignored(classname, ignore):
    """The reason `classname` is on the ignore list, or None."""
    exact, prefixes = ignore
    if classname in exact:
        return exact[classname]
    for p, why in prefixes:
        if classname.startswith(p):
            return why
    return None


def of_map(bsp):
    """{class: count} of every entity of the map that nothing converts."""
    out = collections.Counter()
    for e in bsp.entities:
        c = e.get("classname", "")
        if not is_converted(c):
            out[c] += 1
    return dict(out)


def check(found, ignore=None):
    """(listed, missing): `found` ({class: count}) split into what the ignore list covers and what it does not."""
    ignore = ignore or load_ignore()
    listed = {c: n for c, n in found.items() if ignored(c, ignore) is not None}
    return listed, {c: n for c, n in found.items() if c not in listed}


def stale(ignore=None):
    """Exact ignore rows for a class that is converted or has no row: the list must not outlive the need."""
    exact, _p = ignore or load_ignore()
    return sorted(c for c in exact if is_converted(c) or classes.treatment(c)[0] is None)


def text(found, ignore=None):
    listed, missing = check(found, ignore)
    fmt = lambda d: ", ".join("%s %d" % kv for kv in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))) or "none"
    return ["unconverted, ignored on purpose: " + fmt(listed), "UNCONVERTED, not on the ignore list: " + fmt(missing)]
