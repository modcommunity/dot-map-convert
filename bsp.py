#!/usr/bin/env python3
"""The family's BSP map tool: inventory a folder of maps, or convert one to the intermediate.

    python3 -I tools/bsp/bsp.py convert <map.bsp | archive> --out <map.json> [--member NAME]
            [--credit credit.json | --author A --page URL --licence L] [--faces] [--displacements]
    python3 -I tools/bsp/bsp.py list <dir | file>... [--json] [--markdown] [--converted ROOT] [--queue]
    python3 -I tools/bsp/bsp.py --list <dir>...           (the same as `list`)

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
from dotbsp import intermediate, reader, sources  # noqa: E402


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
    bsp = reader.Bsp(src.member or src.origin, data=src.read()).load()
    doc = intermediate.build(bsp, credit=_credit(args), faces=args.faces,
                             displacements=args.displacements, name=src.name)
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


def main(argv):
    if len(argv) > 1 and argv[1] == "--list":
        argv = [argv[0], "list"] + argv[2:]
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
    c.add_argument("--faces", action="store_true", help="include the world's drawn faces")
    c.add_argument("--displacements", action="store_true", help="include terrain triangles")
    lst = sub.add_parser("list", help="inventory maps")
    lst.add_argument("paths", nargs="+")
    lst.add_argument("--json", action="store_true")
    lst.add_argument("--markdown", action="store_true")
    lst.add_argument("--converted", metavar="ROOT", help="the directory holding the *-maps repositories")
    lst.add_argument("--queue", action="store_true", help="leave out maps already converted")
    args = ap.parse_args(argv[1:])
    return cmd_convert(args) if args.cmd == "convert" else cmd_list(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
