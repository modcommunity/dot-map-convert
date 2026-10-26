"""Surface properties: what a material is made of, from its own record, not from its name.

A packed `.vmt` says whether a surface is translucent, alpha-tested, additive or two-sided; its base
texture's alpha says how much of it is there. The original art is never shipped, so `kind` turns
those facts into one of the runtime's generated see-through looks (`DotMapBspMesh.GLASS_LOOKS`),
and a surface the converter would otherwise draw as an opaque slab is no longer one. A
`materials.tsv` row (texture glob or generic id, then `kind` and `flags`) overrides the derivation;
`kind` `opaque` keeps a surface solid-looking on purpose.
"""

import fnmatch
import re

from . import reader, vtf

SURF_TRANS = 0x10
SIDE = 64           # a base texture is read at this size: enough for the share of it that is there
OPAQUE_SHARE = 0.9  # a card at least this solid is drawn solid; its holes are not worth a pattern
FOLIAGE = re.compile(r"LEAF|LEAVES|BUSH|TREE|GRASS|IVY|VINE|PLANT|FLOWER|WEED|FERN|FOLIAGE|SHRUB|BRANCH|CARD|HEDGE|MOSS")
WIRE = re.compile(r"FENCE|WIRE|CHAIN|CAGE|MESH")
BARS = re.compile(r"BAR|RAIL|GATE|REBAR")
GRATE = re.compile(r"GRATE|GRILL|VENT|TRUSS|SCAFFOLD|LATTICE|STAIR")
KINDS = ("opaque", "glass", "glass_frosted", "fence", "grate", "bars", "ladder", "foliage_card", "shield", "glow")


def _flag(v):
    return str(v).strip().lower() in ("1", "true", "yes")


def vmt_record(pak, name):
    """The merged keys of a packed material (a patch's own keys over what it includes), or None."""
    keys = {}
    path = reader.clean_material(name).lower().replace("\\", "/")
    for _ in range(4):
        raw = pak.get("materials/%s.vmt" % path)
        if raw is None:
            return keys or None
        k = vtf.vmt_keys(raw.decode("latin-1"))
        for key, v in k.items():
            keys.setdefault(key, v)
        inc = k.get("include")
        if not inc:
            return keys
        inc = inc.replace("\\", "/").lower()
        path = inc[len("materials/"):-4] if inc.startswith("materials/") and inc.endswith(".vmt") else inc
    return keys


def _card_by_name(up):
    """The cut-out look a material's name asks for, or None."""
    if GRATE.search(up):
        return "grate"
    if WIRE.search(up):
        return "fence"
    if FOLIAGE.search(up):
        return "foliage_card"
    if BARS.search(up):
        return "bars"
    return None


class Resolver:
    """Surface properties of a map's materials, one lookup per name. `pak` is the map's packed files
    (`reader.Bsp.read_pak`); `rows` an object whose `get(name, generic)` is a `materials.tsv` row or None."""

    def __init__(self, pak=None, rows=None):
        self.pak, self.rows, self._cache = pak or {}, rows, {}

    def _texture(self, keys):
        base = vtf.base_texture("\"$basetexture\" \"%s\"" % keys.get("$basetexture", "")) if keys.get("$basetexture") else None
        data = self.pak.get("materials/%s.vtf" % base) if base else None
        if data is None:
            return None
        try:
            w, h, px = vtf.read(data, SIDE)
        except Exception:
            return None
        n = len(px) or 1
        return {"share": sum(1 for c in px if c[3] >= 128) / n, "mean": sum(c[3] for c in px) / n / 255.0,
                "mid": sum(1 for c in px if 32 < c[3] < 224) / n,
                "colour": vtf.average(px)}

    def properties(self, name, flags=0):
        """{translucent, alpha_test, additive, two_sided, selfillum, source, share?, mean?, colour?}."""
        key = (name, flags & SURF_TRANS)
        if key in self._cache:
            return self._cache[key]
        k = vmt_record(self.pak, name)
        p = {"translucent": bool(flags & SURF_TRANS), "alpha_test": False, "additive": False, "two_sided": False,
             "selfillum": False, "source": "flags" if flags & SURF_TRANS else "none"}
        if k is not None:
            p.update(translucent=_flag(k.get("$translucent", "0")) or p["translucent"], alpha_test=_flag(k.get("$alphatest", "0")),
                     additive=_flag(k.get("$additive", "0")), two_sided=_flag(k.get("$nocull", "0")),
                     selfillum=_flag(k.get("$selfillum", "0")), source="vmt")
            try:
                a = float(k.get("$alpha", "1"))
            except ValueError:
                a = 1.0
            if a < 1.0:
                p["alpha"] = a
            if p["translucent"] or p["alpha_test"] or p["additive"]:
                t = self._texture(k)
                if t:
                    p.update(t)
        self._cache[key] = p
        return p

    def row(self, name, generic):
        return self.rows.get(name, generic) if self.rows is not None else None

    def kind(self, name, generic, props):
        """(glass kind or None, why). The row's `kind` first, then what the properties say."""
        row = self.row(name, generic)
        if row and row.get("kind"):
            return (None if row["kind"] == "opaque" else row["kind"]), "row"
        if props["additive"]:
            return "glow", "additive"
        share, mean = props.get("share"), props.get("mean")
        if "alpha" in props and mean is not None:
            mean *= props["alpha"]
        elif "alpha" in props:
            mean = props["alpha"]
        up = name.upper()
        # translucent used as a cut-out (alpha almost all 0 or 255) is a card; smooth alpha is glass
        cut = props["translucent"] and share is not None and (share < 0.5 or props.get("mid", 1.0) < 0.25)
        card = props["alpha_test"] or cut
        if card:
            if share is not None and share >= OPAQUE_SHARE:
                return None, "solid"
            return (_card_by_name(up) or "foliage_card"), "alpha_test"
        if props["translucent"]:
            if mean is not None and mean >= OPAQUE_SHARE:
                return None, "solid"
            if mean is None and props["source"] == "flags":
                hint = _card_by_name(up)
                return (hint, "name") if hint else (None, "unknown")
            return "glass", "translucent"
        return None, "plain"


def tint(props):
    """The look's multiplier from the base texture's colour: its hue, kept bright enough not to blacken the look."""
    c = props.get("colour")
    if not c:
        return None
    m = max(c) or 1.0
    return [round(max(v / m, 0.35), 3) for v in c]
