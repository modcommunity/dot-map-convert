"""The per-map coverage report and the ratchet.

`build` says what each tier replaced and what fell through every tier to a fallback; nothing is
silently dropped, so each fallback is a name in a list. `ratchet` compares those lists with the
committed report: anything new that is missing fails, so a rule change can only shrink the lists.
"""

import collections
import json
import os

from . import classes as _classes, defs, movers

FORMAT = "dot-bsp-coverage"
VERSION = 1
LISTS = ("textures_unmapped", "textures_flat", "models_unmapped", "sounds_unmapped",
         "classes_unmapped", "keys_unmapped", "links_unresolved")
# Keys every entity may carry and the catalogue need not repeat.
COMMON_KEYS = frozenset(("classname", "origin", "angles", "targetname", "parentname", "hammerid", "id", "model"))


def handled(path=None):
    """[(class regex, key regex)] from `keys_handled.tsv`: keys a component applies or the importer drops on purpose."""
    import re
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys_handled.tsv")
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f.read().splitlines():
            if line.strip() and not line.startswith("#"):
                c = line.split("\t")
                out.append((re.compile(c[0], re.I), re.compile(c[1], re.I)))
    return out


def catalogue(path=None):
    """{class: set of key names} from `rules/entity_defs.json`, or None when it is not there.
    Inherited keys are followed through `bases`."""
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules", "entity_defs.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    # defs.resolve follows a class that names another class as a base (prop_physics_multiplayer -> prop_physics).
    raw.setdefault("classes", {})
    raw.setdefault("bases", {})
    for table in (raw["classes"], raw["bases"]):
        for d in table.values():
            if isinstance(d, dict):
                d.setdefault("in", [])
    memo = {}
    for name, d in raw["classes"].items():
        if isinstance(d, dict):
            r = defs.resolve(raw, name)
            memo[name] = {k.lower() for k in r["keys"]} if r else set()
    return memo


def _tiers(used):
    out = collections.Counter()
    for t in used.values():
        out[t or "fallback"] += 1
    return dict(sorted(out.items()))


def build(rs, bsp, doc, links, name, sha256, cat=None):
    """The coverage report of one regenerated map. `rs` carries what every lookup answered."""
    used = rs.used
    lic = (doc.get("licence") or {}).get("textures", [])
    flat = sorted({s for t in lic if t.get("how") == "flat" for s in t.get("sources", [])})
    real = collections.Counter()
    for t in lic:
        if t["kind"] == "generated" and t["generic"] == "flat":
            continue
        real[rs.free_tier(t["generic"]) or "nearest"] += len(t.get("sources", []))
    nearest = sorted({s for t in lic if t.get("how") not in ("table", "flat") for s in t.get("sources", [])})
    classes = collections.Counter(e.get("classname", "") for e in bsp.entities)
    if bsp.static_props():
        classes["prop_static"] += len(bsp.static_props())
    for c in classes:
        rs.klass(c)
    keys = {}
    hand = handled()
    if cat is not None:
        for e in bsp.entities:
            c = e.get("classname", "")
            known = cat.get(c)
            outs = {o["output"] for o in movers.outputs(e)}
            for k in e.keys():
                if k.lower() in COMMON_KEYS or k in outs:
                    continue
                if (known is None or k.lower() not in known) and not any(c.fullmatch(e.get("classname", "")) and kk.fullmatch(k) for c, kk in hand):
                    keys.setdefault(c, set()).add(k)
    unresolved = sorted({"%s.%s->%s" % (k["from_class"], k["output"], k["target"])
                         for k in links if not k["to"] and not k["special"]})
    lists = {
        "textures_unmapped": sorted(n for n, t in used["textures"].items() if t is None),
        "textures_flat": flat,
        "models_unmapped": sorted(n for n, t in used["models"].items() if t is None),
        "sounds_unmapped": sorted(n for n, t in used["sounds"].items() if t is None),
        "classes_unmapped": sorted(c for c in classes if used["classes"].get(c) is None),
        "keys_unmapped": sorted("%s.%s" % (c, k) for c, ks in keys.items() for k in ks),
        "links_unresolved": unresolved,
    }
    return {
        "format": FORMAT, "version": VERSION, "map": name, "sha256": sha256,
        "textures": {"looked_up": len(used["textures"]), "drawn": sum(len(t.get("sources", [])) for t in lic), "by_tier": _tiers(used["textures"]),
                     "free_by_tier": dict(sorted(real.items())),
                     "nearest_photo": nearest},
        "models": {"looked_up": len(used["models"]), "by_tier": _tiers(used["models"])},
        "sounds": {"looked_up": len(used["sounds"]), "by_tier": _tiers(used["sounds"])},
        "classes": {"distinct": len(classes), "entities": sum(classes.values()),
                    "by_tier": _tiers({c: used["classes"].get(c) for c in classes})},
        "keys": {"catalogue": cat is not None, "unmapped": {c: sorted(k) for c, k in sorted(keys.items())}},
        "links": {"total": len(links), "unresolved": len(unresolved)},
        "lists": lists,
        "counts": {k: len(v) for k, v in lists.items()},
    }


def ratchet(current, baseline):
    """Problems: every name in a list of `current` that the baseline's list does not have."""
    bad = []
    for k in LISTS:
        if k not in baseline.get("lists", {}):
            continue
        new = sorted(set(current["lists"].get(k, ())) - set(baseline["lists"][k]))
        if new:
            bad.append("%s: %d new (%s%s)" % (k, len(new), ", ".join(new[:6]), ", ..." if len(new) > 6 else ""))
    return bad


def text(rep):
    """A few lines for the console."""
    c = rep["counts"]
    t = rep["textures"]["by_tier"]
    out = ["  coverage: textures %s; models %s; sounds %s; classes %s" % (
        _fmt(t), _fmt(rep["models"]["by_tier"]), _fmt(rep["sounds"]["by_tier"]), _fmt(rep["classes"]["by_tier"]))]
    out.append("  unmapped: " + ", ".join("%s %d" % (k, v) for k, v in c.items()) +
               ("" if rep["keys"]["catalogue"] else "  (no class catalogue: keys not checked)"))
    return "\n".join(out)


def _fmt(d):
    return " ".join("%s %d" % kv for kv in d.items()) or "none"


def class_report(bsp, doc=None):
    """Per class of one map, against the catalogue: how many entities, the component that runs it,
    keys the catalogue lacks, outputs the class fires that it lacks, and inputs other entities
    send it that it lacks. A class the catalogue does not know is `known: False`."""
    doc = doc or defs.load()
    memo = {}

    def res(c):
        if c not in memo:
            memo[c] = defs.resolve(doc, c)
        return memo[c]

    out = {}
    for e in bsp.entities:
        c = e.get("classname", "")
        r = out.setdefault(c, {"count": 0, "component": _classes.component(c), "known": res(c) is not None,
                               "keys": set(), "outputs": set(), "inputs": set()})
        r["count"] += 1
        d = res(c)
        outs = {o["output"] for o in movers.outputs(e)}
        if d is None:
            continue
        for k in e.keys():
            if k.lower() not in COMMON_KEYS and k not in outs and k.lower() not in d["keys"]:
                r["keys"].add(k.lower())
        for o in outs:
            if o.lower() not in d["outputs"]:
                r["outputs"].add(o)
    for k in movers.links(bsp):
        for i in k["to"]:
            c = bsp.entities[i].get("classname", "")
            d = res(c)
            if d is not None and k["input"].lower() not in d["inputs"]:
                out[c]["inputs"].add(k["input"])
    return out


def class_text(rep):
    """One line per class that has something the catalogue lacks, then the totals."""
    lines = []
    for c, r in sorted(rep.items(), key=lambda kv: (-kv[1]["count"], kv[0])):
        miss = [("%s %s" % (w, ", ".join(sorted(r[w])))) for w in ("keys", "outputs", "inputs") if r[w]]
        if not r["known"]:
            miss.insert(0, "NOT IN THE CATALOGUE")
        if miss:
            lines.append("%-30s %4d  %s  | %s" % (c, r["count"], r["component"], "; ".join(miss)))
    return lines
