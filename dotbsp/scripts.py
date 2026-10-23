"""`lua_run`: a map's embedded script, classified and never executed.

The converter holds no script host. A snippet is matched whole against a short list of exact
templates (`TEMPLATES`, data); a match becomes a list of whitelisted operations (`OPS`) that
`DotMapScript` hands to the game as events, and anything else is `unhandled` with its text kept
for a person to port into an addon. Nothing here evaluates, imports or shells out: the snippet is
only ever a string compared against a pattern with `fullmatch`.
"""

import re

from . import movers

CLASS = "lua_run"
INPUTS = ("runcode", "runpassedcode")

# Operation name -> {argument: (type, low, high) or tuple of allowed strings}. The runtime holds
# the same table and refuses anything outside it, so a hand-edited document gains nothing.
OPS = {
    "set_player_speed": {"kind": ("run", "walk"), "value": ("number", 1, 5000)},
    "kill_players": {},
    "cleanup_map": {"delay": ("number", 0, 60)},
}

_NUM = r"(\d{1,4}(?:\.\d{1,3})?|\.\d{1,3})"
_ID = r"[A-Za-z_][A-Za-z0-9_]{0,15}"
# (name, regex over the whole snippet, builder from the match to operations)
TEMPLATES = [
    ("speed", re.compile(r"for\s+(%s)\s*,\s*(%s)\s+in\s+pairs\s*\(\s*player\.GetAll\(\)\s*\)\s+do\s+if\s*\(\s*\2:IsValid\(\)\s*\)\s+then\s+\2:Set(Run|Walk)Speed\(\s*%s\s*\)\s+end\s+end"
                      % (_ID, _ID, _NUM)),
     lambda m: [{"op": "set_player_speed", "kind": m.group(3).lower(), "value": float(m.group(4))}]),
    ("reset", re.compile(r"for\s+(%s)\s*,\s*(%s)\s+in\s+pairs\s*\(\s*player\.GetAll\(\)\s*\)\s+do\s+\2:Kill\(\)\s+end\s+timer\.Simple\(\s*%s\s*,\s*function\(\)\s*game\.CleanUpMap\(\s*false\s*\)\s*end\s*\)"
                       % (_ID, _ID, _NUM)),
     lambda m: [{"op": "kill_players"}, {"op": "cleanup_map", "delay": float(m.group(3))}]),
]

# Why a snippet is not translated, from its shape: only for the report, never for behaviour.
_CATEGORIES = [
    ("wire", re.compile(r"\bWMI\.SetWMIOut\s*\(|\bWire_|\bWireLib\b")),
    ("definition", re.compile(r"^\s*(?:local\s+)?function\b|\bconcommand\.Add\b")),
    ("call", re.compile(r"^[A-Za-z_][\w.:]*\s*\(.*\)$", re.S)),
]


def valid_op(op):
    """True when [op] is a whitelisted operation with every argument inside its range."""
    spec = OPS.get(op.get("op")) if isinstance(op, dict) else None
    if spec is None or set(op) != set(spec) | {"op"}:
        return False
    for k, rule in spec.items():
        v = op[k]
        if rule[0] == "number":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not rule[1] <= v <= rule[2]:
                return False
        elif v not in rule:
            return False
    return True


def classify(code):
    """(status, ops, category) for one snippet: `translated` with its operations, else `unhandled`."""
    text = code.strip()
    if len(text) <= 600 and "\n" not in text:
        for _name, rx, build in TEMPLATES:
            m = rx.fullmatch(text)
            if m:
                ops = build(m)
                if all(valid_op(o) for o in ops):
                    return "translated", ops, "template"
    for name, rx in _CATEGORIES:
        if rx.search(text):
            return "unhandled", [], name
    return "unhandled", [], "other"


def analyse(ents):
    """One record per `lua_run` entity (by index) and per `RunPassedCode` input aimed at a script
    entity: `{entity, targetname, source, code, status, ops, category, fired_by}`.
    [ents] are bsp entities or document entity records."""
    out = []
    names = {}
    rec = []
    for i, e in enumerate(ents):
        if hasattr(e, "pairs"):
            pairs, cls, tn, outs = e.pairs, e.get("classname", ""), e.get("targetname", ""), movers.outputs(e)
        else:
            pairs, cls, tn, outs = e["pairs"], e["classname"], e["targetname"], e["outputs"]
        rec.append((i, cls, tn, pairs, outs))
        if cls == CLASS:
            names.setdefault(tn.lower(), []).append(i)
    fired = {}
    passed = []
    for i, cls, tn, pairs, outs in rec:
        for o in outs:
            t = names.get(o["target"].lower()) if o["target"] else None
            if t and o["input"].lower() == "runcode":
                for j in t:
                    fired[j] = fired.get(j, 0) + 1
            elif t and o["input"].lower() == "runpassedcode":
                passed.append((i, o["target"], o["param"]))
    for i, cls, tn, pairs, outs in rec:
        if cls != CLASS:
            continue
        code = next((v for k, v in pairs if k.lower() == "code"), "")
        status, ops, cat = classify(code) if code.strip() else ("unhandled", [], "empty")
        out.append({"entity": i, "targetname": tn, "source": "code", "code": code, "status": status,
                    "ops": ops, "category": cat, "fired_by": fired.get(i, 0)})
    for i, target, param in passed:
        out.append({"entity": names[target.lower()][0], "targetname": target, "source": "RunPassedCode",
                    "from": i, "code": param, "status": "unhandled", "ops": [],
                    "category": "passed call", "fired_by": 1})
    return out


def shape(code):
    """A snippet with its literals blanked, so repeats count as one: `WMI.SetWMIOut('w','input3a','Switch State',0)`
    and its siblings are one shape."""
    s = re.sub(r"'[^']*'|\"[^\"]*\"", "S", code)
    return re.sub(r"\d+(?:\.\d+)?", "N", s)


def inventory(docs):
    """(shape -> {count, maps, status, category, example}) over an iterable of (map label, entities)."""
    inv = {}
    for label, ents in docs:
        for r in analyse(ents):
            row = inv.setdefault(shape(r["code"]), {"count": 0, "maps": set(), "status": r["status"],
                                                    "category": r["category"], "example": r["code"]})
            row["count"] += 1
            row["maps"].add(label)
    return inv


def annotate(records):
    """Document entity records with a `script` field on every `lua_run` that a template translated;
    the rest carry `{status: unhandled, category}`. Returns the analysis rows."""
    rows = analyse(records)
    for r in rows:
        if r["source"] == "code":
            records[r["entity"]]["script"] = {"status": r["status"], "ops": r["ops"], "category": r["category"]}
    return rows
