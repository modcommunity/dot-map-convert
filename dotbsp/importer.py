"""The importer, in the order the family wants it.

1. `store_raw`: the whole map, plain and unprocessed (full mesh with the source texture names,
   the intermediate with faces and displacements, every entity, the texture and model census,
   optionally the packed materials), under `<root>/<game>/raw/<map>/`, outside every repository.
   Later passes read from there, never from a download again.
2. `ship`: the same map through the licence pass (`licence.py`: every texture replaced by a free
   one, models stand-ins, sounds named), with the environment and sound as data, into a map
   repository's own directory. `licence.check` must be clean before it returns.
"""

import collections
import json
import os
import re

from . import environment, intermediate, licence, mesh, movers, props, reader, units

DEFAULT_ROOT = os.path.expanduser(os.environ.get("DOTBSP_RAW_ROOT", "~/mapsrc"))


def raw_dir(game, name, root=None):
    """`<root>/<game>/raw/<map>`; game and map are single path segments, nothing else is accepted."""
    for part in (game, name):
        if not re.fullmatch(r"[A-Za-z0-9._-]+", part or "") or part in (".", ".."):
            raise ValueError("not a plain name: %r" % part)
    return os.path.join(root or DEFAULT_ROOT, game, "raw", name)


def placed_models(bsp):
    """Every model path the map places: static props and entities with a `model` key that is a file."""
    out = [p["model"] for p in bsp.static_props()]
    out += [e["model"] for e in bsp.entities if str(e.get("model", "")).lower().endswith(".mdl")]
    return out


def census(bsp, m):
    """The textures and models of a map as counted, for the raw store."""
    tex = collections.OrderedDict()
    for s in m.surfaces:
        t = tex.setdefault(s.material, {"material": s.material, "generic": s.generic, "tint": s.tint,
                                        "colour": s.colour, "texels": s.texels, "surfaces": 0, "triangles": 0})
        t["surfaces"] += 1
        t["triangles"] += len(s.index) // 3
    models = collections.Counter(props.norm_model(x) for x in placed_models(bsp))
    return {"textures": list(tex.values()), "models": [{"model": k, "count": v} for k, v in sorted(models.items())]}


def _safe(name):
    """A packed file's path as a relative path inside the raw store, or None if it would leave it."""
    n = name.replace("\\", "/").lstrip("/")
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if not parts or ".." in parts or ":" in parts[0]:
        return None
    return "/".join(parts)


def store_raw(bsp, name, game, credit=None, root=None, pak=False, scale=units.VISUAL, y0=0.0):
    """Write the plain import; returns its directory. Nothing here is replaced or dropped."""
    d = raw_dir(game, name, root)
    os.makedirs(d, exist_ok=True)
    m = mesh.build(bsp, scale=scale, y0=y0)
    extra = {"movers": movers.movers(bsp, scale, y0), "volumes": movers.volumes(bsp, scale, y0),
             "destinations": movers.destinations(bsp, scale, y0), "links": movers.links(bsp),
             "entities": movers.generic(bsp), "environment": environment.environment(bsp, scale, y0),
             "sounds": environment.sounds(bsp, scale, y0)}
    mesh.write(m, os.path.join(d, "mesh"), credit=credit, name=name, extra=extra)
    doc = intermediate.build(bsp, credit=credit or {}, faces=True, displacements=True, name=name, scale=scale)
    with open(os.path.join(d, "intermediate.json"), "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    with open(os.path.join(d, "census.json"), "w") as f:
        json.dump(census(bsp, m), f, indent=1)
    with open(os.path.join(d, "entities.json"), "w") as f:
        json.dump([{"index": i, **{k: str(v) for k, v in e.items()}} for i, e in enumerate(bsp.entities)], f, indent=0)
    names = bsp.pak_names()
    with open(os.path.join(d, "pak.txt"), "w") as f:
        f.write("\n".join(names) + ("\n" if names else ""))
    if pak:
        notes = []
        for key, data in bsp.read_pak(notes).items():
            rel = _safe(key)
            if rel and rel.rsplit(".", 1)[-1] in ("vmt", "vtf", "txt", "wav", "mp3"):
                p = os.path.join(d, "pak", rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(data)
        with open(os.path.join(d, "pak-notes.txt"), "w") as f:
            f.write("\n".join(notes) + ("\n" if notes else ""))
    with open(os.path.join(d, "SOURCE.txt"), "w") as f:
        f.write("%s\nsha256 %s\nbsp version %d\nThe author's work, kept for reconversion only; never copied into a repository.\n" % (
            bsp.path, m.source["sha256"], bsp.version))
    return d


def ship(bsp, name, prefix, credit=None, prop_table=None, scale=units.VISUAL, y0=0.0, allow_unknown=False):
    """Write the shipped map at `prefix` (`.json`, `.bin`, `textures/`, `CREDITS.md`).
    Returns (manifest, problems); problems is non-empty when the licence check fails or a class
    is undecided, and the caller must not commit such a map."""
    from . import classes
    m = mesh.build(bsp, scale=scale, y0=y0)
    report = classes.report(bsp)
    extra = {"movers": movers.movers(bsp, scale, y0), "volumes": movers.volumes(bsp, scale, y0),
             "destinations": movers.destinations(bsp, scale, y0), "entity_report": report,
             "links": movers.links(bsp), "entities": movers.generic(bsp),
             "environment": environment.environment(bsp, scale, y0), "sounds": environment.sounds(bsp, scale, y0)}
    doc = mesh.write(m, prefix, credit=credit, name=name, extra=extra)
    outdir = os.path.dirname(os.path.abspath(prefix))
    licence.annotate(doc, outdir, prop_table=prop_table, models=placed_models(bsp))
    for s in doc["sounds"]["ambient"]:
        s.setdefault("stand_in", "")
    problems = licence.check(doc)
    if report["unknown"] and not allow_unknown:
        problems.append("undecided entity classes: %s" % ", ".join(sorted(report["unknown"])))
    with open(prefix + ".json", "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(outdir, "CREDITS.md"), "w") as f:
        f.write(licence.credits_markdown(doc))
    return doc, problems
