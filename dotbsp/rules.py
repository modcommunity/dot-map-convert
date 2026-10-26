"""The replacement rules, read in four tiers: default < addon < game < map.

Each tier is a directory of tables, a JSON file with the same tables, or both:

| table | file | key | gives |
| --- | --- | --- | --- |
| `textures` | `textures.tsv` | texture name glob | generic material id and tint (`texturemap` format) |
| `free` | `free_textures.tsv` | generic id | the free replacement (kind, source, url, author, licence) |
| `models` | `models.tsv` | regex on the model path | stand-in id and its credit (`standins` format) |
| `sounds` | `sounds.tsv` | regex on the sound name | stand-in id (empty = silent on purpose) |
| `classes` | `classes.tsv` | class name, or `prefix*` | treatment, meaning, component |
| `materials` | `materials.tsv` | texture name glob or generic id | `kind`: a see-through look (`materials.KINDS`) or `opaque`, overriding what the material's own record implies |
| `roles` | `roles.tsv` | `class` or `class[key=regex]` (class may end in `*`) | `role`: what the game calls the entity; `regen` writes the matches to the manifest's `roles` |

The highest tier with any matching row answers, and inside a tier the most specific row; so a map's
row beats a game's, a game's beats an addon's, and a tier never needs to repeat the one below it.
Nothing is dropped: what no tier names is answered `None` here and handled by a fallback in
`regen.py`, and every lookup is recorded so the coverage report can say which tier answered.
"""

import fnmatch
import json
import os
import re

from . import classes as _classes
from . import materials as _materials
from . import standins, texturemap

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_DIR = os.path.join(os.path.dirname(HERE), "rules")
TIERS = ("default", "addon", "game", "map")
TABLES = ("textures", "free", "models", "sounds", "classes", "materials", "roles")
FILES = {"textures": "textures.tsv", "free": "free_textures.tsv", "models": "models.tsv",
         "sounds": "sounds.tsv", "classes": "classes.tsv", "materials": "materials.tsv", "roles": "roles.tsv"}
FALLBACK_CLASS = ("data", "no rule names this class: kept, placed and reported (DotMapEntity)", "fallback")
_ROLE_KEY = re.compile(r"^([^\[\]]+)(?:\[([^=\]]+)=(.*)\])?$")
_FREE_COLS = ("kind", "source", "url", "author", "licence")


_CATS = []


def _named_category(name):
    """True when `modelmap`'s categories name the model (a row of its own, not the shape-only fallback), so its pick is a real kind of thing."""
    from . import modelmap
    if not _CATS:
        _CATS.append(modelmap.categories())
    return modelmap.category_of(name, _CATS[0]) is not None


class Rows:
    """A regex table in file order; `get(name)` is the first matching row or None."""

    def __init__(self, rows=()):
        self.rows = list(rows)

    def get(self, name):
        n = str(name or "").lower().replace("\\", "/")
        for rx, row in self.rows:
            if rx.search(n):
                return row
        return None


class Tier:
    """One tier's tables; every table may be empty."""

    def __init__(self, name):
        self.name = name
        self.textures = texturemap.TextureMap([])
        self.free = {}
        self.models = Rows()
        self.sounds = Rows()
        self.classes = {}
        self.materials = {}
        self.roles = {}

    def class_row(self, name):
        if name in self.classes:
            return self.classes[name]
        best = None
        for k, v in self.classes.items():
            if k.endswith("*") and name.startswith(k[:-1]) and (best is None or len(k) > best[0]):
                best = (len(k), v)
        return best[1] if best else None


def _kv(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f.read().splitlines(), 1):
            if not line.strip() or line.startswith("#"):
                continue
            c = line.split("\t")
            out[c[0]] = c[1:]
    return out


def _class_row(key, cells, where):
    if not cells or cells[0] not in _classes.TREATMENTS:
        raise ValueError("%s: class %s: treatment must be one of %s" % (where, key, ", ".join(_classes.TREATMENTS)))
    cells = list(cells) + ["", ""]
    return (cells[0], cells[1], "row" if not key.endswith("*") else "prefix", cells[2])


def _regex_rows(table, where):
    rows = []
    for pat, row in table.items():
        try:
            rows.append((re.compile(pat), dict(zip(standins.COLUMNS, [row.get(c, "") for c in standins.COLUMNS]))))
        except re.error as e:
            raise ValueError("%s: bad pattern %r: %s" % (where, pat, e))
    return rows


def _from_json(tier, doc, where):
    unknown = set(doc) - set(TABLES) - {"note"}
    if unknown:
        raise ValueError("%s: unknown tables %s (known: %s)" % (where, ", ".join(sorted(unknown)), ", ".join(TABLES)))
    rows = [texturemap.Row(p, r["material"], texturemap.parse_tint(str(r.get("tint", "")), where), n)
            for n, (p, r) in enumerate((doc.get("textures") or {}).items(), 1)]
    if rows:
        tier.textures = texturemap.TextureMap(rows, where)
    tier.free.update({k: dict(zip(_FREE_COLS, [r.get(c, "") for c in _FREE_COLS])) for k, r in (doc.get("free") or {}).items()})
    tier.models = Rows(tier.models.rows + _regex_rows(doc.get("models") or {}, where))
    tier.sounds = Rows(tier.sounds.rows + _regex_rows(doc.get("sounds") or {}, where))
    for k, r in (doc.get("classes") or {}).items():
        tier.classes[k] = _class_row(k, [r.get("treatment"), r.get("meaning", ""), r.get("component", "")], where)
    tier.materials.update(doc.get("materials") or {})
    tier.roles.update(doc.get("roles") or {})


def _from_dir(tier, d):
    p = os.path.join(d, FILES["textures"])
    if os.path.isfile(p):
        tier.textures = texturemap.load(p)
    p = os.path.join(d, FILES["free"])
    if os.path.isfile(p):
        tier.free.update({k: dict(zip(_FREE_COLS, c)) for k, c in _kv(p).items()})
    for t in ("models", "sounds"):
        p = os.path.join(d, FILES[t])
        if os.path.isfile(p):
            setattr(tier, t, Rows(standins._load(p) + getattr(tier, t).rows))
    p = os.path.join(d, FILES["classes"])
    if os.path.isfile(p):
        for k, c in _kv(p).items():
            tier.classes[k] = _class_row(k, c, p)
    for t in ("materials", "roles"):
        p = os.path.join(d, FILES[t])
        if os.path.isfile(p):
            getattr(tier, t).update(_kv(p))
    p = os.path.join(d, "rules.json")
    if os.path.isfile(p):
        _from_json(tier, _read_json(p), p)


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_tier(name, path=None):
    """A tier from a directory, a JSON file, or None (an empty tier). A path that does not exist
    is an error: a typo would otherwise silently run without the rules."""
    t = Tier(name)
    if path is None:
        return t
    if os.path.isdir(path):
        _from_dir(t, path)
    elif os.path.isfile(path):
        _from_json(t, _read_json(path), path)
    else:
        raise ValueError("%s tier: %s does not exist" % (name, path))
    return t


def default_tier():
    """The family's own tables: the shared lists beside this file, then `tools/bsp/rules/`."""
    t = Tier("default")
    t.textures = texturemap.load()
    from . import licence
    t.free = licence.load()
    t.models = Rows(standins.models().rows)
    t.sounds = Rows(standins.sounds().rows)
    t.default_class = _classes.treatment      # captured before regen swaps the module's function
    if os.path.isdir(RULES_DIR):
        _from_dir(t, RULES_DIR)
        if os.path.isfile(os.path.join(RULES_DIR, FILES["textures"])):
            base = texturemap.load()
            t.textures = texturemap.TextureMap(base.rows + t.textures.rows, RULES_DIR)
    return t


class RuleSet:
    """The tiers in order, with every answer recorded in `used` for the coverage report."""

    def __init__(self, tiers=None):
        self.tiers = tiers or [default_tier()]
        self.used = {"textures": {}, "models": {}, "sounds": {}, "classes": {}, "materials": {}}

    @classmethod
    def build(cls, addon=(), game=None, map_rules=None):
        tiers = [default_tier()]
        for i, a in enumerate(addon):
            tiers.append(load_tier("addon", a))
        tiers.append(load_tier("game", game))
        tiers.append(load_tier("map", map_rules))
        return cls(tiers)

    def _high_first(self):
        return reversed(self.tiers)

    def texture(self, name):
        """(material, tint, tier name) or None."""
        for t in self._high_first():
            hit = t.textures.lookup(name)
            if hit:
                self.used["textures"][name] = t.name
                return hit[0], hit[1], t.name
        self.used["textures"].setdefault(name, None)
        return None

    def free_tier(self, generic):
        for t in self._high_first():
            if generic in t.free:
                return t.name
        return None

    def free_table(self):
        out = {}
        for t in self.tiers:
            out.update(t.free)
        return out

    def _regex(self, kind, name):
        for t in self._high_first():
            row = getattr(t, kind).get(name)
            if row is not None:
                self.used[kind][name] = t.name
                return row
        self.used[kind].setdefault(name, "skybox" if kind == "models" and standins.is_skybox(name) else "detail" if kind == "models" and standins.is_detail(name)
                                   else "category" if kind == "models" and _named_category(name) else None)
        return None

    def klass(self, name):
        """(treatment, meaning, 'row' | 'prefix' | 'fallback', tier name). Never None."""
        for t in self._high_first():
            r = t.class_row(name)
            if r:
                self.used["classes"][name] = t.name
                return r[0], r[1], r[2], t.name
            if t.name == "default":
                tr, m, how = t.default_class(name)
                if tr is not None:
                    self.used["classes"][name] = "default"
                    return tr, m, how, "default"
        self.used["classes"][name] = None
        return FALLBACK_CLASS + ("fallback",)

    def component(self, name):
        """The DotMapIO component class of a class: the highest tier's row, else the default table's."""
        for t in self._high_first():
            r = t.class_row(name)
            if r:
                return (r[3] if len(r) > 3 and r[3] else "DotMapEntity") if t.name != "default" else _classes.component(name)
        return _classes.component(name)

    def roles_for(self, entities):
        """[{entity, classname, targetname, role}] for every source entity a `roles.tsv` row matches; the highest tier's row wins, then the one with a key test."""
        rows = []
        for rank, t in enumerate(self.tiers):
            for k, cells in t.roles.items():
                m = _ROLE_KEY.match(k)
                if m and cells and cells[0]:
                    rows.append((rank, m.group(2) is not None, m.group(1), m.group(2), re.compile(m.group(3) or ""), cells[0]))
        rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
        out = []
        for i, e in enumerate(entities):
            cls = e.get("classname", "")
            for _rank, _kt, pat, key, rx, role in rows:
                if (cls == pat or (pat.endswith("*") and cls.startswith(pat[:-1]))) and (key is None or rx.search(str(e.get(key, "")))):
                    out.append({"entity": i, "classname": cls, "targetname": e.get("targetname", ""), "role": role})
                    break
        return out

    def treatment(self, name):
        """`classes.treatment` with the tiers and the fallback: the signature the converter calls."""
        return self.klass(name)[:3]

    def textures_view(self):
        return _TexView(self)

    def material(self, name, generic):
        """The highest tier's `materials.tsv` row for the texture (a glob on its name, else its generic id) as {kind}, or None."""
        n = str(name or "").upper()
        for t in self._high_first():
            best = None
            for key, cells in t.materials.items():
                k = key.upper()
                hit = fnmatch.fnmatchcase(n, k) or (generic is not None and key == generic)
                if hit and (best is None or len(key) > best[0]):
                    best = (len(key), cells)
            if best is not None:
                self.used["materials"][name] = t.name
                cells = best[1] if isinstance(best[1], (list, tuple)) else [best[1].get("kind", "")] if isinstance(best[1], dict) else []
                kind = cells[0] if cells else ""
                if kind and kind not in _materials.KINDS:
                    raise ValueError("materials row %s: kind %r is not one of %s" % (name, kind, ", ".join(_materials.KINDS)))
                return {"kind": kind}
        return None

    def materials_view(self):
        return _MatView(self)

    def models_view(self):
        return _RegexView(self, "models")

    def sounds_view(self):
        return _RegexView(self, "sounds")


class _TexView:
    """What `mesh.build` takes as `tmap`."""

    def __init__(self, rs):
        self.rs = rs

    def lookup(self, name):
        hit = self.rs.texture(name)
        return (hit[0], hit[1]) if hit else None


class _MatView:
    """What `mesh.build` takes as `materials`."""

    def __init__(self, rs):
        self.rs = rs

    def get(self, name, generic=None):
        return self.rs.material(name, generic)


class _RegexView:
    """What `licence.annotate` and `standins.placements` take as a model or sound table."""

    def __init__(self, rs, kind):
        self.rs, self.kind = rs, kind

    def get(self, name):
        return self.rs._regex(self.kind, str(name or "").lower().replace("\\", "/"))
