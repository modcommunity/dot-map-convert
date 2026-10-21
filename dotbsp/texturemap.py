"""The family's one list of source texture names and what each becomes: `source_textures.tsv`.

A conversion used to carry its own `TEXTURE_MAP`, a substring table in that importer's file, so
the next map repository learned the same lessons again. This is the one reviewable list. Each
row is `pattern<TAB>material<TAB>tint`:

* `pattern` is a source texture name, upper- or lower-case (matching ignores case), with `*` and
  `?` as wildcards. A map's own folder (`MAPS/<map>/`) and a cubemap suffix (`_-128_64_0`) are
  taken off the name first, by `docboxes.classify_material`, so a row never names one map.
* `material` is a generic id (`wood_floor`, `carpet`, `brick_red`), never a game's own file. A game
  decides what the id looks like; the id says what the surface is.
* `tint` is empty, or `r,g,b` (0..1) or `#rrggbb`: the colour the mapper meant, kept so one carpet
  texture is a blue office and a red hall.

[b]The most specific row wins[/b], not the first: a row with no wildcard beats any glob, and
among globs the one with more literal characters beats the shorter. So `PLASTER/OFFWLLB` beats
`PLASTER/OFFWLL*` beats `*PLASTER*`, wherever they sit in the file. Equal rows go to the earlier
line. Order in the file is therefore only for the reader: group by family.
"""

import collections
import fnmatch
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "source_textures.tsv")


class Row:
    __slots__ = ("pattern", "material", "tint", "line", "literal", "exact", "_rx")

    def __init__(self, pattern, material, tint, line):
        self.pattern = pattern.upper()
        self.material = material
        self.tint = tint
        self.line = line
        self.exact = not any(c in pattern for c in "*?[")
        self.literal = len(re.sub(r"[*?]", "", self.pattern))
        self._rx = re.compile(fnmatch.translate(self.pattern))

    def matches(self, upper_name):
        return self._rx.match(upper_name) is not None

    def sort_key(self):
        # Exact first, then more literal characters, then the earlier line.
        return (0 if self.exact else 1, -self.literal, self.line)


def parse_tint(text, where=""):
    """`r,g,b` (0..1) or `#rrggbb` to a tuple, or None for empty."""
    text = text.strip()
    if not text:
        return None
    if text.startswith("#") and len(text) == 7:
        return tuple(round(int(text[i:i + 2], 16) / 255.0, 3) for i in (1, 3, 5))
    parts = text.split(",")
    if len(parts) == 3:
        try:
            return tuple(float(p) for p in parts)
        except ValueError:
            pass
    raise ValueError("%s: tint %r is not r,g,b or #rrggbb" % (where, text))


class TextureMap:
    def __init__(self, rows, path=""):
        self.rows = sorted(rows, key=Row.sort_key)
        self.path = path
        self._cache = {}

    def lookup(self, name):
        """(material, tint) for a source texture name, or None when no row matches.

        `name` should be the classified name (`docboxes.classify_material`); an unclassified one is
        matched as given, which is right for a name that never had a map folder."""
        key = name.upper()
        if key in self._cache:
            return self._cache[key]
        hit = None
        for row in self.rows:
            if row.matches(key):
                hit = (row.material, row.tint)
                break
        self._cache[key] = hit
        return hit

    def materials(self):
        return sorted({r.material for r in self.rows})


def load(path=None):
    """Read `source_textures.tsv` (or `path`). A bad row is an error naming its line: a silent
    skip would send a surface to the default for a reason nobody can see."""
    path = path or DEFAULT_PATH
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            cells = line.split("\t")
            if len(cells) < 2 or not cells[0].strip() or not cells[1].strip():
                raise ValueError("%s:%d: want pattern<TAB>material[<TAB>tint]" % (path, n))
            where = "%s:%d" % (path, n)
            rows.append(Row(cells[0].strip(), cells[1].strip(), parse_tint(cells[2] if len(cells) > 2 else "", where), n))
    return TextureMap(rows, path)


def unmapped(bsp, tmap, classify):
    """{classified texture name: face count} for every texture of a loaded Bsp that hits no row.

    Faces, not brushes, because the face lump is what a player sees; tools textures and the
    developer grid are not surfaces anyone chooses and are left out."""
    counts = collections.Counter()
    for name, n in face_counts(bsp).items():
        up = name.upper()
        if up.startswith("TOOLS/") or up.startswith("DEV/"):
            continue
        c = classify(name)
        if tmap.lookup(c) is None:
            counts[c] += n
    return counts


def face_counts(bsp):
    """{texture name: faces} over a loaded Bsp's face lump."""
    out = collections.Counter()
    for face in bsp.faces:
        ti = int(face[FACE_TEXINFO])
        if not 0 <= ti < len(bsp.texinfo):
            continue
        td = int(bsp.texinfo[ti][17])
        if 0 <= td < len(bsp.texdata):
            out[bsp.texnames[bsp.texdata[td][3]]] += 1
    return out


FACE_TEXINFO = 5   # the texinfo field of reader.FMT_FACE (plane, side, onnode, firstedge, numedges, texinfo)
