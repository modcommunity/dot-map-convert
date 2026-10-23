"""Every entity class a community map uses, what it means, and what the importer makes of it.

One table (`classes.tsv`: class or `prefix*`, treatment, meaning, runtime component), so a
converter can say for every entity of a map what became of it, and so a class nobody has
decided about is a failure rather than something silently missing. `ROWS` holds the
classes surveyed over 200 maps; `PREFIXES` decides the long tails (`weapon_*`, `npc_*`)
so a new pistol does not need a row. `bsp.py classes --markdown` writes the table in
`docs/entity-classes.md` from here, with the survey's counts, so the document cannot drift.

What a class becomes (`TREATMENTS`):

- `world`: geometry, drawn and solid (`mesh.build`), like any world brush.
- `drawn`: geometry, drawn and never solid.
- `mover`: geometry that moves: a record in `movers.movers` (what moves, how far, how fast,
  what starts it) beside the drawn surfaces and hulls of its model.
- `volume`: a brush a body is affected by inside: `movers.volumes` (teleport, push, hurt,
  gravity, water, ladder), never drawn.
- `point`: a point entity converted to data a game uses as it is: spawns, lights, the sun,
  fog, the 3D sky, props, sounds, decals.
- `data`: kept verbatim in the intermediate's entity list for a game that wants it (map logic,
  paths, filters); the converter does not run it, `DotMapIO` does (the `component` column).
- `dropped`: deliberately left out, with the reason in the row.
"""

import collections
import os

TREATMENTS = ("world", "drawn", "mover", "volume", "point", "data", "dropped")

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "classes.tsv")
ROWS = {}          # class -> (treatment, meaning)
COMPONENTS = {}    # class or prefix -> the DotMapIO component that implements it
PREFIXES = []      # (prefix, treatment, meaning), file order: longest first


def _load(path=PATH):
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f.read().splitlines(), 1):
            if not line.strip() or line.startswith("#"):
                continue
            c = (line.split("\t") + ["", "", ""])[:4]
            if c[1] not in TREATMENTS:
                raise ValueError("%s:%d: treatment %r" % (path, n, c[1]))
            if c[0].endswith("*"):
                PREFIXES.append((c[0][:-1], c[1], c[2]))
            else:
                ROWS[c[0]] = (c[1], c[2])
            if c[3]:
                COMPONENTS[c[0].rstrip("*")] = c[3]


_load()
PREFIXES = tuple(PREFIXES)


def component(classname):
    """The DotMapIO component class that implements `classname`, or 'DotMapEntity' (kept, every
    input recorded as unimplemented)."""
    if classname in COMPONENTS and classname in ROWS:
        return COMPONENTS[classname]
    for p, _t, _m in PREFIXES:
        if classname.startswith(p) and p in COMPONENTS:
            return COMPONENTS[p]
    return "DotMapEntity"


def treatment(classname):
    """(treatment, meaning, 'row' | 'prefix' | None) of one class; None means undecided."""
    if classname in ROWS:
        t, m = ROWS[classname]
        return t, m, "row"
    for p, t, m in PREFIXES:
        if classname.startswith(p):
            return t, m, "prefix"
    return None, None, None


def report(bsp):
    """What became of every entity of a loaded map: {"by_treatment": {t: {class: n}},
    "unknown": {class: n}, "entities": n}. An unknown class is one nobody decided about."""
    by = collections.defaultdict(collections.Counter)
    unknown = collections.Counter()
    for e in bsp.entities:
        c = e.get("classname", "")
        t, _m, _how = treatment(c)
        if t is None:
            unknown[c] += 1
        else:
            by[t][c] += 1
    props = len(bsp.static_props())
    if props:
        by["point"]["prop_static"] += props
    return {"entities": len(bsp.entities), "unknown": dict(unknown),
            "by_treatment": {t: dict(sorted(by[t].items())) for t in TREATMENTS if by[t]}}


def markdown(survey=None):
    """The table as Markdown; `survey` is {class: maps} to add a count column."""
    out = ["| Class | Maps | What it is | What it becomes | Component |", "| --- | --- | --- | --- | --- |"]
    names = set(ROWS) | set(survey or ())
    order = sorted(names, key=lambda c: (-(survey or {}).get(c, 0), c))
    for c in order:
        t, m, how = treatment(c)
        if how == "prefix":
            continue                                   # the prefix rows below say these
        if t is None:
            t, m = "undecided", "no row: add one"
        what, _, why = m.partition(" -- ")
        becomes = "`%s`" % t + (": " + why if why else "")
        out.append("| `%s` | %s | %s | %s | %s |" % (c, (survey or {}).get(c, ""), what, becomes,
                                                       "" if component(c) == "DotMapEntity" else "`%s`" % component(c)))
    out += ["", "| Prefix | Map uses (classes) | What it is | What it becomes |", "| --- | --- | --- | --- |"]
    for p, t, m in PREFIXES:
        hit = [c for c in (survey or {}) if c not in ROWS and treatment(c)[2] == "prefix" and c.startswith(p)
               and next(q for q, _t, _m in PREFIXES if c.startswith(q)) == p]
        n = sum((survey or {}).get(c, 0) for c in hit)
        what, _, why = m.partition(" -- ")
        out.append("| `%s*` | %s (%d) | %s | `%s`%s |" % (p, n, len(hit), what, t, ": " + why if why else ""))
    return "\n".join(out) + "\n"
