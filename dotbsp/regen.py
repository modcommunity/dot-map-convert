"""`regen`: a map's shipped output rebuilt from its store entry and the rules, nothing else.

The same passes as `importer.ship`, but every table is read through the four rule tiers
(`rules.py`), every lookup is recorded, and a coverage report is written beside the manifest.
A class, texture, model or sound no tier names takes a fallback and is listed, never dropped.
"""

import contextlib
import json
import os
import sys

from . import classes, coverage, environment, licence, mesh, movers, reader, rules, standins, store, units


def _json(path):
    with open(path) as f:
        return json.load(f)


def resolve(spec, root):
    """(source.bsp path, credit dict, name, sha256) of a store entry named by hash prefix or `<game>/<name>`."""
    ipath = os.path.join(root, "index.json")
    index = _json(ipath) if os.path.isfile(ipath) else {}
    name = spec.split("/", 1)[-1]
    h = index.get(spec)
    if h is None:
        hs = sorted({v for v in index.values() if v.startswith(spec)} or
                    {d for d in os.listdir(root) if d.startswith(spec) and os.path.isdir(os.path.join(root, d))}) if os.path.isdir(root) else []
        if len(hs) != 1:
            raise ValueError("%r names %d store entries in %s" % (spec, len(hs), root))
        h = hs[0]
        name = next((k.split("/", 1)[-1] for k, v in index.items() if v == h), h[:12])
    d = os.path.join(root, h)
    cp = os.path.join(d, "credit.json")
    credit = _json(cp) if os.path.isfile(cp) else {}
    return os.path.join(d, "source.bsp"), credit, name.split("~")[0], h


@contextlib.contextmanager
def applied(rs):
    """The converter's class decisions read through the rules for the length of one regen."""
    orig = classes.treatment
    classes.treatment = rs.treatment
    try:
        yield
    finally:
        classes.treatment = orig


def build(path, name, sha, credit, out, rs, scale=units.VISUAL, y0=0.0, cat=None):
    """Write the map at `out` (prefix); returns (manifest, coverage report, problems)."""
    with open(path, "rb") as f:
        bsp = reader.Bsp(path, data=f.read()).load()
    with applied(rs):
        m = mesh.build(bsp, tmap=rs.textures_view(), scale=scale, y0=y0)
        report = classes.report(bsp)
        links = movers.links(bsp)
        ents = movers.generic(bsp)
        for e in ents:
            _t, _m, how, tier = rs.klass(e["classname"])
            e["component"] = "DotMapEntity"
            e["rule"] = tier if how != "fallback" else "fallback"
        extra = {"movers": movers.movers(bsp, scale, y0), "volumes": movers.volumes(bsp, scale, y0),
                 "destinations": movers.destinations(bsp, scale, y0), "entity_report": report,
                 "links": links, "entities": ents, "breakables": mesh.breakables(bsp, m),
                 "environment": environment.environment(bsp, scale, y0), "sounds": environment.sounds(bsp, scale, y0)}
    doc = mesh.write(m, out, credit=credit, name=name, extra=extra)
    outdir = os.path.dirname(os.path.abspath(out))
    from . import importer
    licence.annotate(doc, outdir, table=rs.free_table(), models=importer.placed_models(bsp),
                     free_models=rs.models_view(), free_sounds=rs.sounds_view())
    doc["props"] = standins.placements(bsp, None, table=rs.models_view(), scale=scale, y0=y0)
    problems = licence.check(doc)
    # The starter per-map config: every map gets one, from the commands its entities send, commented out.
    from . import mapcfg, store
    mapcfg.write_suggestion(os.path.join(outdir, "dot_map", "map"), name.lower(), store.commands(bsp.entities))
    rep = coverage.build(rs, bsp, doc, links, name, sha, cat)
    with open(out + ".json", "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(outdir, "CREDITS.md"), "w") as f:
        f.write(licence.credits_markdown(doc))
    return doc, rep, problems


def cmd(args):
    root = args.root or store.default_root()
    try:
        rs = rules.RuleSet.build(addon=args.addon_rules or (), game=args.game_rules, map_rules=args.map_rules)
        path, credit, name, sha = resolve(args.entry, root)
    except (ValueError, OSError) as e:
        print("regen: %s" % e, file=sys.stderr)
        return 2
    if not os.path.isfile(path):
        print("regen: no source.bsp for %s" % args.entry, file=sys.stderr)
        return 2
    if not credit.get("author") or not credit.get("page"):
        print("regen: %s has no author and page in its credit.json; a map ships with both" % args.entry, file=sys.stderr)
        return 2
    out = args.out
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    cpath = args.baseline or out + ".coverage.json"
    base = None
    if args.ratchet:
        if not os.path.isfile(cpath):
            print("regen --ratchet: no baseline at %s (commit one, or pass --baseline)" % cpath, file=sys.stderr)
            return 2
        base = _json(cpath)
    try:
        doc, rep, problems = build(path, args.name or name, sha, credit, out, rs, scale=units.parse_scale(args.scale),
                                   y0=args.y0, cat=coverage.catalogue(args.catalogue))
    except (ValueError, OSError) as e:
        print("regen: %s" % e, file=sys.stderr)
        return 1
    c = doc["counts"]
    print("%s: %d surfaces, %d triangles, %d hulls -> %s.{json,bin}" % (name, c["surfaces"], c["triangles"], c["hulls"], out))
    print(coverage.text(rep))
    for p in problems:
        print("  NOT SHIPPABLE: %s" % p, file=sys.stderr)
    worse = coverage.ratchet(rep, base) if base else []
    for w in worse:
        print("  RATCHET: %s" % w, file=sys.stderr)
    if not worse:
        with open(args.coverage or out + ".coverage.json", "w") as f:
            json.dump(rep, f, indent=1)
            f.write("\n")
    return 5 if worse else (4 if problems else 0)
