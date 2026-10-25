"""Map every source texture name to a set of the CC0 PBR library (`~/art-library/materials`).

By name first (Source folders and words: `brick/`, `metalfloor005a`), then by the nearest average
colour inside that category. The picks are written as an `addon` rule tier (`textures.tsv` name ->
`pbr_<set id>`, `free_textures.tsv` the set's source, URL, author and licence, kind `pbr`), and the
importer copies the chosen set's albedo, normal, roughness and AO beside the map.

    python3 -I tools/bsp/bsp.py pbrmap [--root DIR] [--library DIR] [--out DIR]
"""

import csv
import glob
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "rules", "pbr")
GENERIC = "pbr_"
SEE_THROUGH = frozenset(("glass", "glass_frosted", "water", "bars", "grate", "fence", "shield", "foliage_card", "ladder", "invisible"))

# Library ids and tags that make no wall: food, signs, smudges, toys.
BLOCK = frozenset("""leather christmastreeornament pizza candy paymentcard sign footsteps smear fingerprints scratches chip
surfaceimperfections lava ice styrofoam sponge foam cork foil wicker bamboo tatami rope net chainmail solarpanel stickset
shells flowerset painting sticker rubber porcelain ivory onyx cardboard paper acousticfoam glazedterracotta""".split())

# Library category -> id tokens (and, for Poly Haven, tags) that put a set in it.
LIBRARY = {
    "brick": "brick bricks paintedbricks",
    "concrete": "concrete terrazzo cement",
    "metal": "metal metalplates metalwalkway diamondplate sheetmetal corrugatedsteel paintedmetal pipe pipes rails grate steel iron",
    "rust": "rust rusty",
    "wood": "wood planks paintedwood chipboard woodsiding veneer plywood logs",
    "woodfloor": "woodfloor parquet floorboards",
    "tile": "tiles tile officeceiling",
    "stone": "pavingstones rock rocks granite marble travertine stone cobblestone cliff slate",
    "ground": "ground gravel sand mud dirt soil pathway woodchips",
    "grass": "grass moss scatteredleaves leaf",
    "asphalt": "asphalt road tarmac",
    "plaster": "plaster paintedplaster facade wallpaper paint stucco",
    "fabric": "carpet fabric",
    "roof": "roofingtiles clay thatchedroof",
    "snow": "snow",
}
# Which category to widen to when one is empty.
WIDEN = {"rust": "metal", "woodfloor": "wood", "roof": "tile", "plaster": "concrete"}

# Source word -> category; the earliest word in the name wins, ties go to the earlier row.
NAMES = [
    ("snow", r"snow|ice"),
    ("fabric", r"carpet|carp|crpt|rug|fabric|cloth|couch|sofa|mattress|curtain|cushion"),
    ("brick", r"brick|bricks|brk"),
    ("rust", r"rust|rusty|corrod"),
    ("metal", r"corrug|container|shutter|metal|steel|iron|pipe|grate|vent|duct|rail|girder|catwalk|plate|alum|chrome|panel|truss|hull|beam|locker|tank|pump"),
    ("asphalt", r"asphalt|road|street|tarmac|highway"),
    ("tile", r"tile|tiles|tilefloor|checker|bathroom|kitchen"),
    ("woodfloor", r"parquet|woodfloor|wood_floor|hardwood"),
    ("wood", r"wood|plank|planks|door|crate|barrel|log|bark|timber|board|cabinet|desk|shelf|furniture"),
    ("grass", r"grass|lawn|moss|leaf|leaves|foliage|ivy|hedge|bush|plant"),
    ("ground", r"dirt|sand|mud|gravel|soil|path|terrain|ground|beach|swamp"),
    ("stone", r"rock|cliff|stone|cave|granite|marble|cobble|slate|pave"),
    ("roof", r"roof|shingle|thatch"),
    ("concrete", r"concrete|cement|conc|cinder|pavement|sidewalk|curb|bunker|cmu"),
    ("plaster", r"plaster|stucco|wallpaper|paint|drywall|wall|ceiling|trim"),
]
# A photo kind of the older tables -> category, for a name no word places.
KIND_CATEGORY = {
    "brick": "brick", "concrete": "concrete", "concrete_clean": "concrete", "metal": "metal", "rust": "rust",
    "corrugated": "metal", "plaster": "plaster", "plaster_worn": "plaster", "wallpaper": "plaster",
    "wallpaper_decrepit": "plaster", "tile_white": "tile", "tile_dark": "tile", "tile_checker": "tile",
    "ceiling_tile": "tile", "wood_planks": "wood", "wood_floor": "woodfloor", "grass": "grass", "ground": "ground",
    "sand": "ground", "rock": "stone", "stone_block": "stone", "asphalt": "asphalt", "snow": "snow",
    "roof_clay": "roof", "carpet_grey": "fabric", "carpet_pattern": "fabric", "carpet_red": "fabric", "carpet_blue": "fabric",
}
_NAMES = [(c, re.compile(r"(?<![a-z])(?:%s)" % p)) for c, p in NAMES]


def library_root():
    return os.environ.get("DOT_ART_LIBRARY") or os.path.expanduser("~/art-library/materials")


def _tokens(text):
    return set(t for t in re.split(r"[^a-z]+", text.lower()) if t)


def load_library(root=None):
    """{set id: entry} from the library manifest: source, url, author, licence, colour, categories, files."""
    root = root or library_root()
    out = {}
    with open(os.path.join(root, "manifest.tsv"), encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            if not row or row[0].startswith("#") or len(row) < 10:
                continue
            sid, source, url, author, lic, tags = row[:6]
            toks = _tokens(sid)
            if toks & BLOCK or not os.path.isdir(os.path.join(root, source.lower(), sid)):
                continue
            cats = {c for c, words in LIBRARY.items() if toks & set(words.split())}
            if not cats and source == "polyhaven":
                tt = _tokens(tags.replace(",", " "))
                cats = {c for c, words in LIBRARY.items() if tt & set(words.split())}
            out[sid] = {"id": sid, "source": source, "url": url, "author": author, "licence": lic,
                        "colour": (float(row[6]), float(row[7]), float(row[8])), "cats": cats,
                        "dir": os.path.join(root, source.lower(), sid), "files": row[9].split(",")}
            if any(_find(out[sid], suff) is None for suff in REQUIRED):
                del out[sid]
    return out


def category(material, kind_hint=None):
    """The library category of a source name: its last path segment first, then the folders, then
    the older photo kind the name already had; None when nothing places it."""
    path = str(material or "").lower().replace("\\", "/")
    for text in (path.rsplit("/", 1)[-1], path):
        best = None
        for i, (c, rx) in enumerate(_NAMES):
            m = rx.search(text)
            if m and (best is None or (m.start(), i) < best[:2]):
                best = (m.start(), i, c)
        if best:
            return best[2]
    return KIND_CATEGORY.get(kind_hint)


def pick(lib, cat, colour):
    """The set of category `cat` nearest `colour` (sRGB, Euclidean); any category when `cat` has none."""
    pool = [e for e in lib.values() if cat in e["cats"]]
    while not pool and cat in WIDEN:
        cat = WIDEN[cat]
        pool = [e for e in lib.values() if cat in e["cats"]]
    pool = pool or [e for e in lib.values() if e["cats"]]
    colour = colour or (0.5, 0.5, 0.5)
    return min(pool, key=lambda e: (sum((a - b) ** 2 for a, b in zip(colour, e["colour"])), e["id"]))


def seen(roots):
    """{material name: (average colour, photo kind it had)} over every converted map under `roots`
    (`<root>/*/world/*/`) that has a coverage file; see-through and invisible names are left out."""
    names, skip = {}, set()
    for root in roots:
        for cov in sorted(glob.glob(os.path.join(root, "*", "world", "*", "*.coverage.json"))):
            path = cov[:-len(".coverage.json")] + ".json"
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            kinds = {}
            for t in (doc.get("licence") or {}).get("textures", []):
                for s in t.get("sources", []):
                    kinds[s] = t
            acc = {}
            for s in doc.get("surfaces", []):
                a = acc.setdefault(s.get("material"), [0, 0, 0, 0])
                for i, c in enumerate((s.get("colour") or [0.5, 0.5, 0.5])[:3]):
                    a[i] += c
                a[3] += 1
            for name, t in kinds.items():
                if t["kind"] == "generated" and t["generic"] in SEE_THROUGH or t["generic"] in SEE_THROUGH:
                    skip.add(name)
                    continue
                a = acc.get(name)
                if a and a[3]:
                    prev = names.get(name)
                    col = tuple(c / a[3] for c in a[:3])
                    names[name] = (col, t["kind"] if t["kind"] != "generated" else (prev or (0, None))[1])
    return {n: v for n, v in names.items() if n not in skip}


def _glob_safe(name):
    return re.sub(r"[*?\[\]]", "?", name)


def build(roots, library=None, out=OUT_DIR):
    """Write the addon tier at `out`; returns (names mapped, distinct sets used)."""
    lib = load_library(library)
    picks = {}
    for name, (colour, kind) in sorted(seen(roots).items()):
        picks[name] = pick(lib, category(name, kind), colour)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "textures.tsv"), "w", encoding="utf-8") as f:
        f.write("# Source texture name -> PBR library set (tools/bsp/bsp.py pbrmap). Name words first, then the nearest average colour in that category.\n")
        for name, e in picks.items():
            f.write("%s\t%s%s\t\n" % (_glob_safe(name), GENERIC, e["id"]))
    used = {e["id"]: e for e in picks.values()}
    with open(os.path.join(out, "free_textures.tsv"), "w", encoding="utf-8") as f:
        f.write("# generic<TAB>kind<TAB>source<TAB>url<TAB>author<TAB>licence: the library sets pbrmap picked; kind pbr = albedo, normal, roughness, ao shipped beside the map.\n")
        for sid, e in sorted(used.items()):
            f.write("\t".join((GENERIC + sid, "pbr", e["source"], e["url"], e["author"], e["licence"])) + "\n")
    return len(picks), len(used)


REQUIRED = ((("_color.", "_diff_")), (("_normalgl.", "_nor_gl_")), (("_roughness.", "_rough_")))


def _find(entry, suffixes):
    for fn in entry["files"]:
        low = fn.lower()
        if any(s in low for s in suffixes):
            return os.path.join(entry["dir"], fn)
    return None


def ship(generic, outdir, library=None):
    """Copy the set `generic` names to `<outdir>/pbr/<id>/{albedo,normal,roughness,ao}.jpg`; ValueError
    when the library lacks the set. Existing files of the same size are left alone."""
    sid = generic[len(GENERIC):]
    lib = _cache.get(library)
    if lib is None:
        lib = _cache[library] = load_library(library)
    if sid not in lib and library is None and not os.path.isdir(library_root()):
        raise ValueError("PBR library %s not found (set DOT_ART_LIBRARY)" % library_root())
    e = lib.get(sid)
    if e is None:
        raise ValueError("PBR set %s is not in the library %s" % (sid, library or library_root()))
    dest = os.path.join(outdir, "pbr", sid)
    os.makedirs(dest, exist_ok=True)
    wants = (("albedo", ("_color.", "_diff_")), ("normal", ("_normalgl.", "_nor_gl_")),
             ("roughness", ("_roughness.", "_rough_")), ("ao", ("_ambientocclusion.", "_ao_")))
    for name, suff in wants:
        src = _find(e, suff)
        if src is None:
            if name in ("albedo", "normal", "roughness"):
                raise ValueError("PBR set %s has no %s map" % (sid, name))
            continue
        dst = os.path.join(dest, name + ".jpg")
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copyfile(src, dst)
    return dest


_cache = {}
ENABLED = False          # `regen` turns it on; the older `ship` path keeps the stock photo sets
_warned = []


def library():
    """The loaded library when the importer should use it, else None (with one warning when it is missing)."""
    if not ENABLED:
        return None
    root = library_root()
    lib = _cache.get(("auto", root))
    if lib is None:
        if os.path.isfile(os.path.join(root, "manifest.tsv")):
            lib = load_library(root)
        else:
            lib = {}
            print("warning: PBR library not found at %s (set DOT_ART_LIBRARY); textures use the stock photo sets" % root, file=sys.stderr)
        _cache[("auto", root)] = lib
    return lib or None


def choose(material, colour, kind_hint=None):
    """The library entry for a source texture, or None without a library."""
    lib = library()
    if lib is None:
        return None
    return pick(lib, category(material, kind_hint), colour)


def cmd(args):
    roots = args.root or [os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))]
    n, k = build(roots, args.library, args.out or OUT_DIR)
    print("pbrmap: %d source textures -> %d library sets, tier at %s" % (n, k, args.out or OUT_DIR))
    return 0
