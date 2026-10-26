"""`regen`: a map's shipped output rebuilt from its store entry and the rules, nothing else.

The same passes as `importer.ship`, but every table is read through the four rule tiers
(`rules.py`), every lookup is recorded, and a coverage report is written beside the manifest.
A class, texture, model or sound no tier names takes a fallback and is listed, never dropped.
"""

import contextlib
import json
import os
import sys

from . import classes, coverage, environment, licence, mapcfg, mesh, movers, pbrmap, reader, rules, scripts, standins, store, units


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


def build(path, name, sha, credit, out, rs, scale=units.VISUAL, y0=0.0, cat=None, pbr_store=None, model_store=None, crop=None):
    """Write the map at `out` (prefix); returns (manifest, coverage report, problems)."""
    with open(path, "rb") as f:
        bsp = reader.Bsp(path, data=f.read()).load()
    with applied(rs):
        m = mesh.build(bsp, tmap=rs.textures_view(), scale=scale, y0=y0, crop=crop, materials=rs.materials_view())
        report = classes.report(bsp)
        links = movers.links(bsp)
        ents = movers.generic(bsp)
        for e in ents:
            _t, _m, how, tier = rs.klass(e["classname"])
            e["component"] = rs.component(e["classname"])
            e["rule"] = tier if how != "fallback" else "fallback"
        every = movers.movers(bsp, scale, y0)
        # a mover the source gave no brush model (a door that is a .mdl prop) has nothing to animate
        drawn = {s.model for s in m.surfaces} | {h["model"] for h in m.hulls}
        # a prop_door_rotating is kept though it has no brush: DotMapDoorStandIn draws and swings it
        built = [r for r in every if r.get("model") in drawn or r["classname"] == "prop_door_rotating"]
        bare = [{k: r.get(k) for k in ("classname", "targetname", "entity", "model_path", "origin")}
                for r in every if r not in built]
        extra = {"movers": built, "movers_without_geometry": bare, "volumes": movers.volumes(bsp, scale, y0),
                 "destinations": movers.destinations(bsp, scale, y0), "spawns": movers.spawns(bsp, scale, y0), "pickups": movers.pickups(bsp, scale, y0), "entity_report": report,
                 "links": links, "entities": ents, "breakables": mesh.breakables(bsp, m),
                 "environment": environment.environment(bsp, scale, y0), "sounds": environment.sounds(bsp, scale, y0),
                 "settings": mapcfg.defaults(store.commands(bsp.entities)),
                 "scripts": scripts.analyse(bsp.entities), "roles": rs.roles_for(bsp.entities)}
    keep = mesh.crop_keep(crop)
    if keep is not None:
        extra = _cropped(extra, keep)
    doc = mesh.write(m, out, credit=credit, name=name, extra=extra)
    outdir = os.path.dirname(os.path.abspath(out))
    from . import importer
    shaped = standins.shape_matches(bsp, None, table=rs.models_view())
    licence.annotate(doc, outdir, table=rs.free_table(), models=importer.placed_models(bsp),
                     free_models=rs.models_view(), free_sounds=rs.sounds_view(), shaped=shaped,
                     pbr_store=os.path.abspath(pbr_store or os.path.join(outdir, os.pardir, "pbr-library")),
                     model_store=os.path.abspath(model_store or os.path.join(outdir, os.pardir, "model-library")))
    doc["props"] = standins.placements(bsp, None, table=rs.models_view(), scale=scale, y0=y0, shaped=shaped)
    if keep is not None:
        doc["props"] = [p for p in doc["props"] if keep(p["at"])]
    problems = licence.check(doc)
    # The starter per-map config: every map gets one, from the commands its entities send, commented out.
    mapcfg.write_suggestion(os.path.join(outdir, "dot_map", "map"), name.lower(), store.commands(bsp.entities))
    rep = coverage.build(rs, bsp, doc, links, name, sha, cat)
    with open(out + ".json", "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    store.ship_document(bsp.d, out, os.path.join(os.path.dirname(path), "doc.json"))
    with open(os.path.join(outdir, "CREDITS.md"), "w") as f:
        f.write(licence.credits_markdown(doc))
    with open(os.path.join(outdir, "credits.json"), "w") as f:
        json.dump({"map": {k: doc.get("credit", {}).get(k, "") for k in ("author", "page", "licence")}, "works": licence.credits_list(doc)}, f, indent=1)
        f.write("\n")
    return doc, rep, problems


def _point(rec):
    """Where a converter record stands (metres), or None when it names no place."""
    for k in ("at", "origin", "position"):
        v = rec.get(k) if isinstance(rec, dict) else None
        if isinstance(v, (list, tuple)) and len(v) == 3:
            return v
    if isinstance(rec, dict) and rec.get("mins") and rec.get("maxs"):
        return [(a + b) / 2 for a, b in zip(rec["mins"], rec["maxs"])]
    return None


def _cropped(extra, keep):
    """`extra`'s record lists with the ones standing outside the crop removed; records that name no place stay."""
    out = dict(extra)
    for k in ("movers", "movers_without_geometry", "spawns", "pickups"):
        out[k] = [r for r in extra[k] if _point(r) is None or keep(_point(r))]
    return out


def addon_dirs(args):
    """The addon tiers: the PBR library tier first (unless --no-pbr or no library here), then the given ones."""
    out = list(args.addon_rules or ())
    if not getattr(args, "no_pbr", False) and os.path.isfile(os.path.join(pbrmap.OUT_DIR, "textures.tsv")) \
            and os.path.isfile(os.path.join(pbrmap.library_root(), "manifest.tsv")):
        out.insert(0, pbrmap.OUT_DIR)
    return out


def _crop(text):
    return [float(v) for v in text.split(",")] if text else None


def cmd(args):
    root = args.root or store.default_root()
    pbrmap.ENABLED = not getattr(args, "no_pbr", False)
    standins.PICKS_ON = not getattr(args, "no_models", False) and os.path.isfile(standins.PICKS)
    try:
        rs = rules.RuleSet.build(addon=addon_dirs(args), game=args.game_rules, map_rules=args.map_rules)
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
                                   y0=args.y0, cat=coverage.catalogue(args.catalogue), crop=_crop(args.crop),
                                   pbr_store=getattr(args, "pbr_store", None), model_store=getattr(args, "model_store", None))
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
