#!/usr/bin/env python3
"""The family's BSP map tool: inventory a folder of maps, or convert one to the intermediate.

    python3 -I tools/bsp/bsp.py convert <map.bsp | archive> --out <map.json> [--member NAME]
            [--credit credit.json | --author A --page URL --licence L] [--faces] [--displacements]
    python3 -I tools/bsp/bsp.py list <dir | file>... [--json] [--markdown] [--converted ROOT] [--queue]
    python3 -I tools/bsp/bsp.py --list <dir>...           (the same as `list`)
    python3 -I tools/bsp/bsp.py unmapped <dir | file>... [--table source_textures.tsv] [--top N] [--json] [--strict]
    python3 -I tools/bsp/bsp.py --unmapped <dir | file>...   (the same as `unmapped`)
    python3 -I tools/bsp/bsp.py mesh <map.bsp | archive> --out <prefix> [--member NAME] [credit flags]
            [--y0 M] [--coverage] [--allow-unknown]
    python3 -I tools/bsp/bsp.py classes [<dir | file>...] [--markdown | --keys]
    python3 -I tools/bsp/bsp.py audit <map.bsp> (--mesh <prefix> | --doc <doc.json> --y0 M) [--max-loss 0.002] [--within ..] [--band ..] [--skip ..] [--json F]
    python3 -I tools/bsp/bsp.py regen <hash | game/name> --out <prefix> [--game-rules DIR] [--addon-rules DIR]...
            [--map-rules FILE] [--ratchet] [--baseline FILE] [--coverage FILE] [--root R]
    python3 -I tools/bsp/bsp.py store <dir | file>... [--root R] [--game G] [credit flags] | store --check | store --scripts

`mesh` writes the full geometry (`<prefix>.json` + `<prefix>.bin`, dotbsp/mesh.py) with the
movers, volumes and teleport destinations (dotbsp/movers.py) and what became of every entity
(dotbsp/classes.py) in the manifest; it fails (3) on an entity class nobody decided about
unless `--allow-unknown`, and `--coverage` samples the source against what was written.
`audit` counts every brush by owner class and CONTENTS kind and asks the converted output (a
mesh's hulls or a document's boxes) for each player-solid one and for ground under every exposed
floor (dotbsp/audit.py); it fails (1) when either share lost is over `--max-loss`.
`classes` prints each class's treatment over the maps given, or the whole table; `--keys` reports each map's keys, outputs and inputs against the class catalogue, with the runtime component of each class.

`convert` writes the intermediate JSON (README.md, "The intermediate") that every game's
adapter reads. `list` prints one line a map: name, BSP version, size, entity and spawn
counts, and the game its prefix belongs to; `--converted ROOT` marks (and `--queue` drops)
maps a map repository under ROOT already has. Archives (.zip, .rar, .7z) are read in memory,
never extracted. Run with `python3 -I`: the maps are downloads.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotbsp import pbrmap, audit, classes, regen, units, docboxes, environment, gma, importer, intermediate, mesh, movers, reader, sources, store, terrain, texturemap  # noqa: E402


def _credit(args):
    credit = {}
    if args.credit:
        credit.update(json.load(open(args.credit)))
    for k in ("author", "page", "licence", "no_share_check"):
        v = getattr(args, k, None)
        if v:
            credit[k] = v
    return credit


def cmd_convert(args):
    found = sources.find([args.bsp])
    if args.member:
        found = [s for s in found if s.member == args.member or s.name == args.member.lower()]
    if len(found) != 1:
        print("%s holds %d maps%s; name one with --member" % (
            args.bsp, len(found), (": " + ", ".join(s.member or s.name for s in found)) if found else ""),
            file=sys.stderr)
        return 2
    src = found[0]
    try:
        bsp = reader.Bsp(src.member or src.origin, data=src.read()).load()
        doc = intermediate.build(bsp, credit=_credit(args), faces=args.faces,
                                 displacements=args.displacements, name=src.name,
                                 scale=args.scale)
    except (ValueError, OSError) as e:      # a cut-off or malformed map is a message, not a traceback
        print("%s: %s" % (src.label(), e), file=sys.stderr)
        return 1
    if not doc["credit"].get("author") or not doc["credit"].get("page"):
        print("warning: no author or page in the credit; a converted map ships with both", file=sys.stderr)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
        f.write("\n")
    c = doc["counts"]
    print("%s: VBSP v%d, %d brushes, %d entities, %d spawns, %d lights, %d static props, %d displacements -> %s" % (
        src.name, bsp.version, c["brushes"], c["entities"], c["spawns"], c["lights"], c["static_props"],
        c["displacements"], args.out))
    return 0


def _one(args):
    found = sources.find([args.bsp])
    if args.member:
        found = [s for s in found if s.member == args.member or s.name == args.member.lower()]
    if len(found) != 1:
        print("%s holds %d maps; name one with --member" % (args.bsp, len(found)), file=sys.stderr)
        return None
    return found[0]


def cmd_mesh(args):
    src = _one(args)
    if src is None:
        return 2
    try:
        bsp = reader.Bsp(src.member or src.origin, data=src.read()).load()
    except (ValueError, OSError) as e:
        print("%s: %s" % (src.label(), e), file=sys.stderr)
        return 1
    scale = units.parse_scale(args.scale)
    m = mesh.build(bsp, scale=scale, y0=args.y0)
    report = classes.report(bsp)
    extra = {"movers": movers.movers(bsp, scale, args.y0), "volumes": movers.volumes(bsp, scale, args.y0),
             "destinations": movers.destinations(bsp, scale, args.y0), "spawns": movers.spawns(bsp, scale, args.y0), "entity_report": report,
             "links": movers.links(bsp), "entities": movers.generic(bsp),
             "breakables": mesh.breakables(bsp, m),
             "environment": environment.environment(bsp, scale, args.y0), "sounds": environment.sounds(bsp, scale, args.y0)}
    if args.coverage:
        extra["coverage"] = mesh.coverage(bsp, m)
        extra["silhouette"] = mesh.silhouette_diff(bsp, m)
    doc = mesh.write(m, args.out, credit=_credit(args), name=src.name, extra=extra)
    c = doc["counts"]
    print("%s: %d surfaces, %d triangles, %d hulls, %d movers, %d volumes, bin %d bytes (%d gzip'd) -> %s.{json,bin}" % (
        src.name, c["surfaces"], c["triangles"], c["hulls"], len(extra["movers"]), len(extra["volumes"]),
        doc["bin"]["bytes"], doc["bin"]["stored_bytes"], args.out))
    for t, row in report["by_treatment"].items():
        print("  %-8s %5d  %s" % (t, sum(row.values()), ", ".join("%s %d" % kv for kv in sorted(row.items(), key=lambda kv: -kv[1])[:8])))
    odd = sorted({e["classname"] for e in extra["entities"] if e["treatment"] == "unknown"})
    print("  links: %d (%d unresolved); kept as data: %d entities; unknown classes: %s" % (
        len(extra["links"]), sum(1 for k in extra["links"] if not k["to"] and not k["special"]),
        len(extra["entities"]), ", ".join(odd) or "none"))
    if args.coverage:
        cv, sl = extra["coverage"], extra["silhouette"]
        print("  coverage: drawn %.4f of %d samples, solid %.4f of %d; silhouette kept top %.4f side %.4f/%.4f" % (
            cv["drawn"], cv["drawn_samples"], cv["solid"], cv["solid_samples"], sl["top"]["kept"],
            sl["side_x"]["kept"], sl["side_z"]["kept"]))
    if report["unknown"]:
        print("  undecided classes (add a row to dotbsp/classes.py): %s" % ", ".join(
            "%s %d" % kv for kv in sorted(report["unknown"].items())), file=sys.stderr)
        if not args.allow_unknown:
            return 3
    return 0


def cmd_audit(args):
    src = _one(args)
    if src is None:
        return 2
    bsp = reader.Bsp(src.member or src.origin, data=src.read()).load()
    if args.mesh:
        man, m = mesh.read(args.mesh)
        out, y0, scale = audit.Hulls(m.hulls), man["units"]["y0"], man["units"]["metres_per_unit"]
        classes_of = None
    else:
        with open(args.doc) as f:
            doc = json.load(f)
        field = terrain.Heightfield.decode(doc["terrain"])[0] if doc.get("terrain") else None
        out, y0, scale = audit.Boxes(doc.get("boxes", []), terrain=field), args.y0, units.parse_scale(args.scale)
        if doc.get("world_collision") and args.world:
            # the game collides with these hulls of the world pack as well as the boxes
            out = audit.Union(out, audit.Hulls(audit.collision_hulls(mesh.read(args.world)[1].hulls, doc["world_collision"])))
        # a box document stands still: the world and the classes dot-map treats as world collide
        classes_of = lambda c: c == "worldspawn" or (classes.treatment(c)[0] == "world" and c not in args.passable)  # noqa: E731
    r = audit.audit(bsp, out, scale, y0, classes_of, keep=audit.region(args.within, args.band, args.skip))
    print("%s: brushes collided %d of %d; floor samples with ground %d of %d" % (
        src.name, r["brushes_collided"], r["brushes_expected"], r["floor_samples"] - r["floor_missed"], r["floor_samples"]))
    print("  %-28s %-11s %6s %6s %6s" % ("class", "kind", "count", "solid", "kept"))
    for key, (n, exp, got) in r["brushes"].items():
        cls, kind = key.split("|")
        print("  %-28s %-11s %6d %6s %6s%s" % (cls, kind, n, exp or "-", got if exp else "-", "  LOST %d" % (exp - got) if got < exp else ""))
    for key, (miss, n) in sorted(r["floors"].items(), key=lambda kv: -kv[1][0])[:args.top]:
        print("  floor without ground: %5d of %5d  %s" % (miss, n, key.replace("|", "  ")))
    if args.json:
        with open(args.json, "w") as f:
            json.dump({k: v for k, v in r.items() if k not in ("floor_missed_points", "brushes_lost")}, f, indent=1, sort_keys=True)
            f.write("\n")
    bl = 1.0 - r["brushes_collided"] / r["brushes_expected"] if r["brushes_expected"] else 0.0
    fl = r["floor_missed"] / r["floor_samples"] if r["floor_samples"] else 0.0
    print("  lost: brushes %.4f, floor %.4f (limit %.4f)" % (bl, fl, args.max_loss))
    return 1 if bl > args.max_loss or fl > args.max_loss else 0


def cmd_import(args):
    src = _one(args)
    if src is None:
        return 2
    try:
        bsp = reader.Bsp(src.member or src.origin, data=src.read()).load()
    except (ValueError, OSError) as e:
        print("%s: %s" % (src.label(), e), file=sys.stderr)
        return 1
    scale = units.parse_scale(args.scale)
    credit = _credit(args)
    raw = importer.store_raw(bsp, src.name, args.game, credit=credit, root=args.raw_root, pak=args.pak, scale=scale, y0=args.y0)
    print("raw import stored: %s" % raw)
    if not args.out:
        return 0
    doc, problems = importer.ship(bsp, src.name, args.out, credit=credit, scale=scale, y0=args.y0,
                                  allow_unknown=args.allow_unknown)
    lic = doc["licence"]
    print("%s: %d surfaces; %d free replacements (%s); %d models stood in, %d skybox models skipped; %d ambient sounds, %d soundscapes; environment: %s -> %s.json" % (
        src.name, len(doc["surfaces"]), len(lic["textures"]), ", ".join(sorted({t["kind"] for t in lic["textures"]})),
        len(lic["models"]), lic.get("skipped_skybox_models", 0), len(doc["sounds"]["ambient"]), len(doc["sounds"]["soundscapes"]),
        ", ".join(k for k in doc["environment"] if k != "sky") or "sky only", args.out))
    for p in problems:
        print("  NOT SHIPPABLE: %s" % p, file=sys.stderr)
    return 4 if problems else 0


def cmd_classes_keys(args):
    """Per map: the keys, outputs and inputs the class catalogue lacks, and the component of each class."""
    from dotbsp import coverage
    rc = 0
    for s in sources.find(args.paths):
        try:
            bsp = reader.Bsp(s.member or s.origin, data=s.read()).load()
        except (ValueError, OSError) as e:
            print("%s: %s" % (s.label(), e), file=sys.stderr)
            rc = 1
            continue
        rep = coverage.class_report(bsp)
        plain = sum(1 for r in rep.values() if r["component"] == "DotMapEntity")
        print("%s: %d classes, %d without a component" % (s.label(), len(rep), plain))
        for line in coverage.class_text(rep):
            print("  " + line)
    return rc


def cmd_classes(args):
    if args.keys:
        return cmd_classes_keys(args)
    if not args.paths:
        print(classes.markdown(), end="")
        return 0
    maps = {}
    bad = 0
    for s in sources.find(args.paths):
        try:
            bsp = reader.Bsp(s.member or s.origin, data=s.read()).load()
        except (ValueError, OSError) as e:
            print("%s: %s" % (s.label(), e), file=sys.stderr)
            bad += 1
            continue
        for c in {e.get("classname", "") for e in bsp.entities} | ({"prop_static"} if bsp.static_props() else set()):
            maps[c] = maps.get(c, 0) + 1
    if args.markdown:
        print(classes.markdown(maps), end="")
    else:
        for c, n in sorted(maps.items(), key=lambda kv: -kv[1]):
            t, _m, how = classes.treatment(c)
            print("%-36s %4d  %s%s" % (c, n, t or "UNDECIDED", " (prefix)" if how == "prefix" else ""))
    undecided = [c for c in maps if classes.treatment(c)[0] is None]
    print("%d classes, %d undecided, %d unreadable maps" % (len(maps), len(undecided), bad), file=sys.stderr)
    return 3 if undecided else 0


def _row_notes(s):
    notes = []
    if s["version"] == 19:
        notes.append("v19")
    if s["compressed"]:
        notes.append("LZMA")
    if s["displacements"]:
        notes.append("%d displacements" % s["displacements"])
    if s["static_props"] > 0:
        notes.append("%d static props" % s["static_props"])
    if s["pak_files"]:
        notes.append("%d packed files" % s["pak_files"])
    if not s["spawns"]:
        notes.append("no spawns")
    return notes


def cmd_list(args):
    done = sources.converted(args.converted) if args.converted else {}
    rows, failed = [], []
    for src in sources.find(args.paths):
        try:
            data = src.read()
            s = intermediate.summary(reader.Bsp(src.member or src.origin, data=data), name=src.name, nbytes=len(data))
        except (ValueError, OSError, IndexError) as e:
            failed.append((src.label(), str(e)))
            continue
        s["origin"] = src.label()
        s["target"] = sources.target(src.name)
        s["converted"] = done.get(src.name)
        if args.queue and s["converted"]:
            continue
        rows.append(s)
    # One map can arrive twice (loose and archived, or two versions of one download).
    uniq = {}
    for s in rows:
        uniq.setdefault((s["name"], s["bytes"]), s)
    rows = sorted(uniq.values(), key=lambda s: (s["target"] is None, s["target"] or "", s["name"]))
    if args.json:
        json.dump({"maps": rows, "failed": failed}, sys.stdout, indent=1)
        print()
    elif args.markdown:
        print("| name | target game | MB | v | entities | spawns | notes |")
        print("| --- | --- | ---: | ---: | ---: | --- | --- |")
        for s in rows:
            sp = " ".join("%s %d" % kv for kv in sorted(s["spawns"].items()))
            print("| %s | %s | %.1f | %d | %d | %s | %s |" % (s["name"], s["target"] or "?", s["bytes"] / 1e6, s["version"],
                                                       s["entities"], sp or "-", ", ".join(_row_notes(s))))
    else:
        for s in rows:
            sp = " ".join("%s=%d" % kv for kv in sorted(s["spawns"].items()))
            print("%-36s v%d %7.1f MB  %5d ents  %5d brushes  %-24s %-18s %s" % (
                s["name"], s["version"], s["bytes"] / 1e6, s["entities"], s["brushes"], sp or "no-spawns",
                s["target"] or "?", ("converted:" + s["converted"]) if s["converted"] else ""))
    for label, err in failed:
        print("unreadable: %s: %s" % (label, err), file=sys.stderr)
    print("%d maps, %d unreadable" % (len(rows), len(failed)), file=sys.stderr)
    return 0


def cmd_unmapped(args):
    """Every texture of the given maps that hits no row of the shared list, with face counts."""
    try:
        tmap = texturemap.load(args.table)
    except (ValueError, OSError) as e:
        print("unmapped: %s" % e, file=sys.stderr)
        return 2
    total, per_map, failed, seen = {}, {}, [], set()
    maps = 0
    for src in sources.find(args.paths):
        try:
            data = src.read()
            key = (src.name, len(data))
            if key in seen:      # one map can arrive twice (loose and archived)
                continue
            seen.add(key)
            found = texturemap.unmapped(reader.Bsp(src.member or src.origin, data=data).load(), tmap, docboxes.classify_material)
        except (ValueError, OSError, IndexError) as e:
            failed.append((src.label(), str(e)))
            continue
        maps += 1
        for name, n in found.items():
            total[name] = total.get(name, 0) + n
            per_map.setdefault(name, []).append(src.name)
    rows = sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))
    if args.json:
        json.dump({"maps": maps, "unmapped": [{"texture": n, "faces": f, "maps": sorted(per_map[n])} for n, f in rows],
                   "failed": failed}, sys.stdout, indent=1)
        print()
    else:
        for name, n in rows[:args.top] if args.top else rows:
            ms = sorted(per_map[name])
            print("%6d  %-56s %s" % (n, name, ", ".join(ms[:3]) + (" +%d" % (len(ms) - 3) if len(ms) > 3 else "")))
    for label, err in failed:
        print("unreadable: %s: %s" % (label, err), file=sys.stderr)
    print("%d maps, %d unmapped textures (%d faces), %d unreadable; table %s (%d rows)" % (
        maps, len(rows), sum(total.values()), len(failed), tmap.path, len(tmap.rows)), file=sys.stderr)
    return 1 if args.strict and rows else 0


def main(argv):
    if len(argv) > 1 and argv[1] in ("--list", "--unmapped"):
        argv = [argv[0], argv[1][2:]] + argv[2:]
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert", help="one map to the intermediate JSON")
    c.add_argument("bsp")
    c.add_argument("--out", required=True)
    c.add_argument("--member", help="which map inside an archive holding several")
    c.add_argument("--credit", help="a JSON file with author, page, licence, no_share_check")
    c.add_argument("--author")
    c.add_argument("--page")
    c.add_argument("--licence")
    c.add_argument("--no-share-check", dest="no_share_check",
                   help="when and how the page was checked for a do-not-share note")
    c.add_argument("--scale", default="visual",
                   help="metres per unit: visual (0.01905, the default), hull (0.0254, a 72 unit player is 1.83 m) or a number")
    c.add_argument("--faces", action="store_true", help="include the world's drawn faces")
    c.add_argument("--displacements", action="store_true", help="include terrain triangles")
    lst = sub.add_parser("list", help="inventory maps")
    lst.add_argument("paths", nargs="+")
    lst.add_argument("--json", action="store_true")
    lst.add_argument("--markdown", action="store_true")
    lst.add_argument("--converted", metavar="ROOT", help="the directory holding the *-maps repositories")
    lst.add_argument("--queue", action="store_true", help="leave out maps already converted")
    um = sub.add_parser("unmapped", help="textures that hit no row of source_textures.tsv, with face counts")
    um.add_argument("paths", nargs="+")
    um.add_argument("--table", help="another table than dotbsp/source_textures.tsv")
    um.add_argument("--top", type=int, default=0, help="only the N most-used")
    um.add_argument("--json", action="store_true")
    um.add_argument("--strict", action="store_true", help="exit 1 when anything is unmapped")
    me = sub.add_parser("mesh", help="one map's full geometry, movers and volumes (dotbsp/mesh.py)")
    me.add_argument("bsp")
    me.add_argument("--out", required=True, help="prefix: writes <prefix>.json and <prefix>.bin")
    me.add_argument("--member")
    me.add_argument("--credit")
    me.add_argument("--author")
    me.add_argument("--page")
    me.add_argument("--licence")
    me.add_argument("--scale", default="visual")
    me.add_argument("--y0", type=float, default=0.0, help="metres subtracted from every height")
    me.add_argument("--coverage", action="store_true", help="sample the source against the output (slow on big maps)")
    me.add_argument("--allow-unknown", action="store_true", help="do not fail on an undecided entity class")
    au = sub.add_parser("audit", help="every brush and floor of the source against a converted output (dotbsp/audit.py)")
    au.add_argument("bsp")
    au.add_argument("--member")
    au.add_argument("--mesh", help="a dot-bsp-mesh prefix (its hulls)")
    au.add_argument("--doc", help="a document with `boxes` (metres, Godot axes)")
    au.add_argument("--y0", type=float, default=0.0, help="the document's y0 (a mesh carries its own)")
    au.add_argument("--scale", default="visual")
    au.add_argument("--max-loss", type=float, default=0.002, help="largest share of brushes or floor samples lost")
    au.add_argument("--top", type=int, default=12)
    au.add_argument("--world", help="the document's world pack prefix: its hulls count where the document has `world_collision`")
    au.add_argument("--within", help="x0,z0,x1,z1 (game metres): audit only this rectangle, for an output cropped on purpose")
    au.add_argument("--band", help="lo,hi (game metres): audit only heights in this band")
    au.add_argument("--skip", action="append", default=[], help="x0,y0,z0,x1,y1,z1 (game metres): a region removed on purpose; repeatable")
    au.add_argument("--passable", action="append", default=[], help="a brush entity class the document leaves passable on purpose (--doc); repeatable")
    au.add_argument("--json")
    cl = sub.add_parser("classes", help="entity classes and what each becomes")
    im = sub.add_parser("import", help="raw import outside the repo, then the licence pass into --out")
    im.add_argument("bsp")
    im.add_argument("--game", required=True, help="the game's folder under the raw root (zz, pg, ...)")
    im.add_argument("--raw-root", default=None, help="default $DOTBSP_RAW_ROOT or ~/mapsrc; the raw import is <root>/<game>/raw/<map>/")
    im.add_argument("--out", help="prefix of the shipped map; omit to store only the raw import")
    im.add_argument("--pak", action="store_true", help="also extract the packed vmt/vtf/sound files into the raw store")
    im.add_argument("--member")
    im.add_argument("--credit")
    im.add_argument("--author")
    im.add_argument("--page")
    im.add_argument("--licence")
    im.add_argument("--scale", default="visual")
    im.add_argument("--y0", type=float, default=0.0)
    im.add_argument("--allow-unknown", action="store_true")
    cl.add_argument("paths", nargs="*")
    cl.add_argument("--markdown", action="store_true")
    cl.add_argument("--keys", action="store_true", help="per map: keys, outputs and inputs the class catalogue lacks, and each class's component")
    st = sub.add_parser("store", help="copy maps into the lossless store (dotbsp/store.py), or --check it")
    st.add_argument("paths", nargs="*")
    st.add_argument("--root", help="default $DOTBSP_STORE or ~/mapsrc/store")
    st.add_argument("--check", action="store_true", help="rebuild every document from its source.bsp and compare")
    st.add_argument("--game")
    st.add_argument("--audit", action="store_true", help="list entries with an empty author, page, licence or no_share_check, and licence terms that restrict reuse; exit 1 only on a no_share_check of `forbidden`")
    st.add_argument("--scripts", action="store_true", help="list every distinct lua_run snippet with its count and whether the converter translates it")
    st.add_argument("--entry", help="update this stored entry's credit.json (<game>/<map> or hash prefix) from the credit flags, overwriting those keys")
    st.add_argument("--credit", help="a JSON file with author, page, licence, no_share_check")
    for k in ("author", "page", "licence", "no_share_check", "removal", "note"):
        st.add_argument("--" + k.replace("_", "-"), dest=k)
    rg = sub.add_parser("regen", help="rebuild a map from its store entry and the rule tiers, with a coverage report")
    rg.add_argument("entry", help="a store hash (prefix) or <game>/<map>")
    rg.add_argument("--out", required=True, help="prefix: writes <prefix>.json, .bin, .coverage.json")
    rg.add_argument("--root", help="the store; default $DOTBSP_STORE or ~/mapsrc/store")
    rg.add_argument("--addon-rules", action="append", metavar="DIR|FILE", help="an addon's tier (repeatable)")
    rg.add_argument("--game-rules", metavar="DIR|FILE", help="the game's tier, <maps repo>/tools/convert")
    rg.add_argument("--map-rules", metavar="FILE", help="the map's tier, tools/convert/maps/<id>.json")
    rg.add_argument("--ratchet", action="store_true", help="fail (5) when anything new is unmapped against the committed coverage")
    rg.add_argument("--baseline", help="the coverage to ratchet against; default <prefix>.coverage.json")
    rg.add_argument("--coverage", help="where to write the coverage; default <prefix>.coverage.json")
    rg.add_argument("--catalogue", help="the class catalogue; default rules/entity_defs.json")
    rg.add_argument("--name")
    rg.add_argument("--scale", default="visual")
    rg.add_argument("--y0", type=float, default=0.0)
    rg.add_argument("--no-pbr", action="store_true", help="leave out the PBR library tier (rules/pbr)")
    rg.add_argument("--pbr-store", help="where the shared PBR sets are written once, by id and tier (default: pbr-library beside the pack folder)")
    pm = sub.add_parser("pbrmap", help="pick a PBR library set for every texture name the converted maps use; writes rules/pbr")
    pm.add_argument("--root", action="append", help="a directory holding <game>/world/<map>/ (repeatable; default ~/godot)")
    pm.add_argument("--library", help="the library's materials folder; default $DOT_ART_LIBRARY or ~/art-library/materials")
    pm.add_argument("--out", help="the tier directory to write; default tools/bsp/rules/pbr")
    args = ap.parse_args(argv[1:])
    try:
        return {"convert": cmd_convert, "list": cmd_list, "unmapped": cmd_unmapped, "mesh": cmd_mesh,
                "classes": cmd_classes, "audit": cmd_audit, "import": cmd_import, "store": lambda a: store.cmd(a), "regen": regen.cmd, "pbrmap": pbrmap.cmd}[args.cmd](args)
    except gma.GmaMissing as e:
        print("bsp.py: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
