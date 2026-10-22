"""The nearest free photographic set for a texture no row of `free_textures.tsv` names.

By name first (a wall called `brickwall12` is brick whatever its colour), then by average
colour among the photo sets when one is close enough; otherwise None and the caller generates
a flat image in the original's colour. A wrong photo is worse than a flat colour, so the
colour match has a ceiling.
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# First match wins; order is specific to general. Values are folders of addons/dot_map/surfaces.
NAME_RULES = [
    (r"snow", "snow"),
    (r"carpet|carp|crpt|rug", "carpet_grey"),
    (r"brick|bricks|brk", "brick"),
    (r"rust|rusty|corrod", "rust"),
    (r"corrug|container|shutter", "corrugated"),
    (r"asphalt|road|street|tarmac|highway", "asphalt"),
    (r"checker", "tile_checker"),
    (r"tile|tiles|tilefloor|bathroom|kitchen", "tile_white"),
    (r"parquet|woodfloor|wood_floor|hardwood", "wood_floor"),
    (r"plank|wood|door|crate|barrel|log|bark|timber|board", "wood_planks"),
    (r"grass|lawn|moss|leaf|leaves|foliage|ivy|hedge|bush", "grass"),
    (r"dirt|sand|mud|gravel|ground|soil|path|rock|cliff|stone|cave|terrain", "ground"),
    (r"metal|steel|iron|pipe|grate|vent|duct|rail|girder|catwalk|plate|alum|chrome|panel", "metal"),
    (r"concrete|cement|conc|cinder|pavement|sidewalk|curb", "concrete"),
    (r"plaster|stucco|wallpaper|paint|drywall|wall|ceiling|trim", "plaster"),
]


def load_colours(path=os.path.join(HERE, "photo_colours.tsv")):
    out = {}
    with open(path) as f:
        for line in f.read().splitlines():
            if line.strip() and not line.startswith("#"):
                k, r, g, b = line.split("\t")
                out[k] = (float(r), float(g), float(b))
    return out


def by_name(material):
    """The photo kind a texture's name points at, or None. Matches on word-ish fragments of
    the last two path segments, so `de_chateau/barrelside01` reads as wood and a folder
    called `walls` alone does not turn a floor into plaster."""
    parts = str(material or "").lower().replace("\\", "/").split("/")[-2:]
    text = "/".join(parts)
    for pat, kind in NAME_RULES:
        if re.search(r"(?<![a-z])(?:%s)" % pat, text):
            return kind
    return None


def by_colour(colour, colours=None, ceiling=0.2):
    """The photo kind whose average colour is nearest (Euclidean, 0..1 RGB), if within `ceiling`."""
    if not colour:
        return None
    colours = colours or load_colours()
    best, bd = None, 9.0
    for k, c in colours.items():
        d = sum((a - b) ** 2 for a, b in zip(colour[:3], c)) ** 0.5
        if d < bd:
            best, bd = k, d
    return best if bd <= ceiling else None


def nearest(material, colour, colours=None):
    """(kind, how) for a texture: `how` is "name" or "colour"; (None, None) when nothing fits."""
    k = by_name(material)
    if k:
        return k, "name"
    k = by_colour(colour, colours)
    return (k, "colour") if k else (None, None)
