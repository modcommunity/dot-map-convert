"""The per-map coverage report and the ratchet.

`build` says what each tier replaced and what fell through every tier to a fallback; nothing is
silently dropped, so each fallback is a name in a list. `ratchet` compares those lists with the
committed report: anything new that is missing fails, so a rule change can only shrink the lists.
"""

import collections
import json
import os

from . import movers

FORMAT = "dot-bsp-coverage"
VERSION = 1
LISTS = ("textures_unmapped", "textures_flat", "models_unmapped", "sounds_unmapped",
         "classes_unmapped", "keys_unmapped", "links_unresolved")
# Keys every entity may carry and the catalogue need not repeat.
COMMON_KEYS = frozenset(("classname", "origin", "angles", "targetname", "parentname", "hammerid", "id", "model"))


def catalogue(path=None):
    """{class: set of key names} from `rules/entity_defs.json`, or None when it is not there.
    Inherited keys are followed through `bases`."""
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules", "entity_defs.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    defs, bases = raw.get("classes", raw), raw.get("bases", {})
    memo = {}

    def keys(d, seen=()):
        out = set(d.get("keys", {})) | set(d.get("extra", []))
        for b in d.get("bases", []) or []:
            if b not in seen and isinstance(bases.get(b), dict):
                out |= keys(bases[b], seen + (b,))
        return out

    for name, d in defs.items():
        if isinstance(d, dict):
            memo[name] = {k.lower() for k in keys(d) | keys(bases.get("_cbaseentity_", {}))}
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
    nearest = sorted({s for t in lic if t.get("how") not in ("table", "flat") for s in t.get("sources", [])})
    classes = collections.Counter(e.get("classname", "") for e in bsp.entities)
    if bsp.static_props():
        classes["prop_static"] += len(bsp.static_props())
    for c in classes:
        rs.klass(c)
    keys = {}
    if cat is not None:
        for e in bsp.entities:
            c = e.get("classname", "")
            known = cat.get(c)
            outs = {o["output"] for o in movers.outputs(e)}
            for k in e.keys():
                if k.lower() in COMMON_KEYS or k in outs:
                    continue
                if known is None or k.lower() not in known:
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
        "textures": {"looked_up": len(used["textures"]), "by_tier": _tiers(used["textures"]),
                     "free_by_tier": _tiers({t["generic"]: rs.free_tier(t["generic"]) for t in lic}),
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
