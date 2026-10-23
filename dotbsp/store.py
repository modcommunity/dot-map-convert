"""The lossless store: one directory per source file, keyed by the sha256 of its bytes.

`<root>/<sha256>/` holds `source.bsp` (the file byte for byte), `credit.json` and `doc.json`
(the source document: every entity with its keys as written, in order, repeats kept, and its
outputs whatever the key is called). `<root>/index.json` maps `<game>/<map id>` to the hash.
The root is `$DOTBSP_STORE`, default `~/mapsrc/store`, outside every repository: the files
are the authors' work, kept so a map can be regenerated, and never shipped.
"""

import hashlib
import json
import os
import sys

from . import movers, reader, scripts, sources

FORMAT = "dot-bsp-source"
VERSION = 1
CREDIT_KEYS = ("author", "page", "licence", "no_share_check", "download", "member", "contact", "removal", "note")


def default_root():
    return os.environ.get("DOTBSP_STORE") or os.path.expanduser("~/mapsrc/store")


def _entity_record(i, e):
    pairs = [list(p) for p in e.pairs]
    return {"index": i, "classname": e.get("classname", ""), "targetname": e.get("targetname", ""),
            "parentname": e.get("parentname", ""), "pairs": pairs, "outputs": movers.outputs(e)}


COMMAND_CLASSES = ("point_servercommand", "point_clientcommand")


def commands(ents):
    """Console commands a map's entities send, recorded and never run: a later package turns
    them into per-map config. One row per `Command` input aimed at a command entity."""
    named = {}
    for i, e in enumerate(ents):
        if e.get("classname") in COMMAND_CLASSES and e.get("targetname"):
            named.setdefault(e["targetname"].lower(), []).append(i)
    out = []
    for i, e in enumerate(ents):
        for o in movers.outputs(e):
            if o["input"].lower() == "command" and o["target"].lower() in named:
                for t in named[o["target"].lower()]:
                    out.append({"entity": t, "classname": ents[t]["classname"], "from": i,
                                "output": o["output"], "command": o["param"], "delay": o["delay"]})
    return out


def ship_document(data, prefix, stored=None):
    """`<prefix>.doc.json` beside a shipped manifest: the source document (the map's entities and
    their outputs) that `DotMapWorld` reads, so a shipped map needs no store. `stored` is the
    store entry's `doc.json` when there is one; otherwise it is built from `data`."""
    doc = _load(stored) if stored and os.path.isfile(stored) else document(data)
    scripts.annotate(doc["entities"])
    with open(prefix + ".doc.json", "w") as f:
        json.dump(doc, f, sort_keys=True, separators=(",", ":"))
        f.write("\n")


def document(data):
    """The source document of one .bsp's bytes. Raises ValueError for a cut-off or unknown file."""
    bsp = reader.Bsp("store", data=data).load()
    return {"format": FORMAT, "version": VERSION, "sha256": hashlib.sha256(data).hexdigest(),
            "bsp_version": bsp.version, "size": len(data),
            "entities": [_entity_record(i, e) for i, e in enumerate(bsp.entities)],
            "commands": commands(bsp.entities)}


def entity_text(doc):
    """The entity lump text rebuilt from a document: what the round trip is compared against."""
    out = []
    for ent in doc["entities"]:
        out.append("{\n" + "".join('"%s" "%s"\n' % (k, v) for k, v in ent["pairs"]) + "}\n")
    return "".join(out)


def _load(path, mode="r"):
    with open(path, mode) as f:
        return json.load(f) if mode == "r" else f.read()


def _dump(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def put(root, game, name, data, credit=None):
    """Store one file; returns (hash, was_new). The credit of an existing entry is kept and
    only filled where it was empty."""
    doc = document(data)
    h = doc["sha256"]
    d = os.path.join(root, h)
    new = not os.path.isfile(os.path.join(d, "source.bsp"))
    os.makedirs(d, exist_ok=True)
    if new:
        with open(os.path.join(d, "source.bsp"), "wb") as f:
            f.write(data)
    _dump(os.path.join(d, "doc.json"), doc)
    cpath = os.path.join(d, "credit.json")
    cred = _load(cpath) if os.path.isfile(cpath) else {}
    for k in CREDIT_KEYS:
        if (credit or {}).get(k) and not cred.get(k):
            cred[k] = credit[k]
    cred.setdefault("first_import", None)
    cred["missing"] = [k for k in ("author", "page") if not cred.get(k)]
    _dump(cpath, cred)
    from . import mapcfg
    mapcfg.write_suggestion(d, "mapcfg", doc["commands"], map_name=name)
    ipath = os.path.join(root, "index.json")
    index = _load(ipath) if os.path.isfile(ipath) else {}
    key = "%s/%s" % (game, name)
    if index.get(key, h) != h:
        key = "%s~%s" % (key, h[:8])
    index[key] = h
    _dump(ipath, dict(sorted(index.items())))
    return h, new


def set_credit(root, entry, credit):
    """Overwrite the given credit keys of an existing entry (`<game>/<name>` or a hash prefix);
    returns its hash. `put` only fills blanks, so this is how a wrong or late credit is corrected."""
    index = _load(os.path.join(root, "index.json"))
    h = index.get(entry) or next(iter(sorted({v for v in index.values() if v.startswith(entry)})), None)
    if h is None or not os.path.isdir(os.path.join(root, h)):
        raise ValueError("no store entry %r" % entry)
    cpath = os.path.join(root, h, "credit.json")
    cred = _load(cpath) if os.path.isfile(cpath) else {}
    cred.update({k: v for k, v in credit.items() if k in CREDIT_KEYS and v})
    cred["missing"] = [k for k in ("author", "page") if not cred.get(k)]
    _dump(cpath, cred)
    return h


def check(root):
    """Rebuild every entry's document from its source.bsp. Returns the problems found."""
    bad = []
    for h in sorted(os.listdir(root)):
        d = os.path.join(root, h)
        if not os.path.isdir(d):
            continue
        try:
            data = _load(os.path.join(d, "source.bsp"), "rb")
            if hashlib.sha256(data).hexdigest() != h:
                bad.append((h, "source.bsp does not hash to its directory"))
            elif document(data) != _load(os.path.join(d, "doc.json")):
                bad.append((h, "doc.json differs from a rebuild"))
        except (OSError, ValueError) as e:
            bad.append((h, str(e)))
    return bad


def audit(root):
    """(key, problems, flags) per entry: problems are credit fields still empty (regen needs author and
    page; licence and no_share_check should be there); flags are licence terms that restrict reuse."""
    index = _load(os.path.join(root, "index.json"))
    out = []
    for key, h in sorted(index.items()):
        c = _load(os.path.join(root, h, "credit.json"))
        problems = [k for k in ("author", "page", "licence", "no_share_check") if not c.get(k)]
        lic = (c.get("licence") or "").lower()
        flags = [t for t, hit in (("NC", "-nc" in lic or "noncommercial" in lic), ("ND", "nd " in lic + " " or "-nd" in lic),
                                  ("no licence", "no licen" in lic or "none stated" in lic), ("unknown", "unknown" in lic or "not recorded" in lic)) if hit]
        out.append((key, problems, flags))
    return out


def _walk(paths):
    """(game, Source) for every map under each path, directories searched all the way down."""
    for p in paths:
        p = os.path.abspath(p)
        dirs = [p] if os.path.isdir(p) else [os.path.dirname(p)]
        if os.path.isdir(p):
            dirs = [r for r, _, _ in os.walk(p)]
        for d in sorted(dirs):
            rel = os.path.relpath(d, os.path.expanduser("~/mapsrc"))
            game = rel.split(os.sep)[0] if not rel.startswith("..") and rel != "." else "local"
            for s in sources.find([d] if os.path.isdir(p) else [p]):
                yield game, s


def scripts_report(root):
    """Every distinct `lua_run` snippet in the store with its count, maps and what the converter does with it."""
    index = _load(os.path.join(root, "index.json"))
    docs = [(key, _load(os.path.join(root, h, "doc.json"))["entities"]) for key, h in sorted(index.items())]
    inv = scripts.inventory(docs)
    for shape, r in sorted(inv.items(), key=lambda kv: (-kv[1]["count"], kv[0])):
        print("%4d x %d map(s)  %-10s %-12s %s" % (r["count"], len(r["maps"]), r["status"], r["category"], r["example"][:90].replace("\n", " ")))
    print("store --scripts: %d distinct, %d translated, %d unhandled" % (
        len(inv), sum(1 for r in inv.values() if r["status"] == "translated"), sum(1 for r in inv.values() if r["status"] != "translated")))
    return 0


def cmd(args):
    root = args.root or default_root()
    if getattr(args, "scripts", False):
        return scripts_report(root)
    if getattr(args, "audit", False):
        rows = audit(root)
        for key, problems, flags in rows:
            if problems or flags:
                print("%-48s missing: %-34s flags: %s" % (key, ",".join(problems) or "-", ",".join(flags) or "-"))
        print("store --audit: %d entries, %d with a missing field" % (len(rows), sum(1 for r in rows if r[1])))
        return 1 if any("author" in r[1] or "page" in r[1] for r in rows) else 0
    if args.check:
        if not os.path.isdir(root):
            print("store: no store at %s" % root, file=sys.stderr)
            return 2
        bad = check(root)
        for h, why in bad:
            print("BAD %s: %s" % (h[:12], why))
        n = len([x for x in os.listdir(root) if os.path.isdir(os.path.join(root, x))])
        print("store --check: %d entries, %d bad" % (n, len(bad)))
        return 1 if bad else 0
    os.makedirs(root, exist_ok=True)
    credit = {k: getattr(args, k, None) for k in CREDIT_KEYS}
    if args.credit:
        credit.update(_load(args.credit))
    if getattr(args, "entry", None):
        try:
            h = set_credit(root, args.entry, credit)
        except (ValueError, OSError) as e:
            print("store: %s" % e, file=sys.stderr)
            return 2
        print("store: credit of %s updated (%s)" % (args.entry, h[:12]))
        return 0
    stored = new = 0
    cut = []
    for game, s in _walk(args.paths):
        if game == "store":
            continue
        try:
            _, was_new = put(root, args.game or game, s.name, s.read(), credit)
        except ValueError as e:
            cut.append((s.label(), str(e)))
            continue
        stored += 1
        new += was_new
    for label, why in cut:
        print("skipped (unreadable): %s: %s" % (label, why[:100]), file=sys.stderr)
    print("store: %d stored (%d new), %d unreadable, root %s" % (stored, new, len(cut), root))
    return 0
