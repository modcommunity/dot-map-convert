#!/usr/bin/env python3
"""The one writer of a map repository's provides.json (the Workshop listing), shared by every maps repo.

A repo's tools/build_provides.py is a thin config that imports this and calls `run`:

    sys.path.insert(0, <dot-map>/tools); import build_provides; sys.exit(build_provides.run(ROOT, ...))

    pack="single": one provides.json at the root, one `map` entry per document in `directory`
    pack="each":   maps/<id>/provides.json and licence.json per folder (each folder is its own pack), entry scene = <id>.json

Run with --check to exit 1 on a stale file, a bad id or a scene the pack lacks. Entries come from the
documents on disk, so a map added by the builders is listed with no second edit. `scene` is relative to
the pack root, as the publisher requires.
"""

import json
import os
import re
import sys


def _entry(mid, name, scene, map_kind):
    # The Workshop entry id allows only [a-z0-9_]; a hyphenated map id keeps its hyphens in the scene.
    return {"kind": "map", "id": mid.replace("-", "_"), "name": name, "scene": scene, "map_kind": map_kind}


def _single(root, title, games, directory, doc_kind, map_kind, argv):
    entries = []
    for name in sorted(os.listdir(os.path.join(root, directory))):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(root, directory, name)) as f:
            doc = json.load(f)
        if doc_kind is not None and doc.get("kind") != doc_kind:
            continue
        mid = name[:-5]
        kind = map_kind(doc) if callable(map_kind) else map_kind
        entries.append(_entry(mid, doc.get("name") or mid, directory + "/" + name, kind))
    doc = {"schema": 1, "title": title, "kinds": ["map"], "games": games, "entries": entries}

    bad = []
    seen = set()
    for e in entries:
        if not re.fullmatch(r"[a-z0-9_]+", e["id"]) or e["id"] in seen:
            bad.append("bad or repeated id " + e["id"])
        seen.add(e["id"])
        if not e["map_kind"]:
            bad.append("no map_kind for " + e["id"])
        if not os.path.isfile(os.path.join(root, e["scene"])):
            bad.append("missing " + e["scene"])
    if not entries:
        bad.append("no entries")

    text = json.dumps(doc, indent=4) + "\n"
    path = os.path.join(root, "provides.json")
    if "--check" in argv:
        have = open(path).read() if os.path.exists(path) else ""
        if have != text:
            bad.append("provides.json is stale (run tools/build_provides.py)")
        for b in bad:
            print(b)
        print("provides.json ok, %d maps" % len(entries) if not bad else "provides.json FAILED")
        return 1 if bad else 0
    if bad:
        print("\n".join(bad))
        return 1
    with open(path, "w") as f:
        f.write(text)
    print("wrote provides.json, %d maps" % len(entries))
    return 0


def _pack_licence(root, mid, worlds=False):
    """maps/<id>/licence.json text: base entry for original content plus the map's entry, prefixes relative to the pack root.

    The root licence.json names "maps/<id>"; a pack built from maps/<id> never sees that prefix, and the credited-map
    exception refuses "", so the map's files are named: <id> (its .json/.bin/lightmap/.import) and textures/; worlds=True adds worlds/<id>/ for packs that install under it.
    """
    src = os.path.join(root, "licence.json")
    if not os.path.isfile(src):
        return None
    entries = json.load(open(src))
    mine = [dict(e) for e in entries if ("maps/" + mid) in e.get("paths", [])]
    if not mine:
        return None
    base = next((dict(e) for e in entries if e.get("paths") == [""] and not e.get("exception")), None)
    if base is None:
        base = {"paths": [""], "licence": "MIT", "author": "TMC",
                "url": "https://github.com/zees-games/" + os.path.basename(os.path.abspath(root)),
                "title": os.path.basename(os.path.abspath(root)) + " (original content)"}
    for e in mine:
        e["paths"] = [mid, "textures/"] + (["worlds/" + mid + "/"] if worlds else [])
    return json.dumps([base] + mine, indent=2) + "\n"


def _each(root, games, skip, map_kind, argv, worlds=False):
    check = "--check" in argv
    bad = []
    count = 0
    for mid in sorted(os.listdir(os.path.join(root, "maps"))):
        folder = os.path.join(root, "maps", mid)
        if not os.path.isdir(folder) or mid in skip or not os.listdir(folder):
            continue
        if not re.fullmatch(r"[a-z0-9_-]+", mid):
            bad.append("bad id " + mid)
        if not os.path.isfile(os.path.join(folder, mid + ".json")):
            bad.append("missing " + mid + "/" + mid + ".json")
            continue
        name = " ".join(w if w.isdigit() else w.capitalize() for w in re.split("[_-]", mid))
        doc = {"schema": 1, "title": name, "kinds": ["map"], "games": games,
               "entries": [_entry(mid, name, mid + ".json", map_kind(mid))]}
        text = json.dumps(doc, indent=4) + "\n"
        path = os.path.join(folder, "provides.json")
        count += 1
        outs = [(path, text, "provides.json")]
        lic = _pack_licence(root, mid, worlds)
        if lic:
            outs.append((os.path.join(folder, "licence.json"), lic, "licence.json"))
        for p, t, label in outs:
            if check:
                if not os.path.exists(p) or open(p).read() != t:
                    bad.append("stale or missing " + mid + "/" + label)
            else:
                with open(p, "w") as f:
                    f.write(t)
    if check:
        print("\n".join(bad) if bad else "every map has its provides.json (%d)" % count)
    else:
        print("\n".join(bad) if bad else "wrote %d provides.json" % count)
    return 1 if bad else 0


def run(root, games, pack="single", title="", directory="maps", doc_kind=None, map_kind=None, skip=(), argv=None, worlds=False):
    argv = sys.argv if argv is None else argv
    if pack == "each":
        return _each(root, games, set(skip), map_kind, argv, worlds)
    return _single(root, title, games, directory, doc_kind, map_kind, argv)
