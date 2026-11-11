"""Add the Kenney Prototype Textures (CC0) to the PBR library as pin-only sets.

Each `PNG/<Colour>/texture_NN.png` becomes `<library>/kenney/kenney_prototype_<colour>_NN/` with the albedo
(`_Color.png`, the 1024 px original as RGB), a flat normal (`_NormalGL.png`) and a constant roughness
(`_Roughness.png`), and one `manifest.tsv` row (source Kenney, folder `kenney`, the asset page URL, author Kenney, CC0-1.0).
Rows of an earlier run are replaced; other sources' rows are kept. `pbrmap` never picks a `kenney` set by
colour: a source texture gets one only through `rules/pbr/pins.tsv`. One texture covers 1 m in the original;
`DotMapSurfaces` draws a set over 2 m, so its 2x2 big squares are 1 m each.

    python3 -P tools/kenney_prototypes.py "<Kenney bundle>/2D assets/Prototype Textures" [--library DIR]
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import pbrmap  # noqa: E402

SOURCE = "kenney"          # the library folder; the manifest row says Kenney
URL = "https://kenney.nl/assets/prototype-textures"
AUTHOR = "Kenney"
LICENCE = "CC0-1.0"
ROUGHNESS = 0.85
FLAT_PX = 256


def set_id(colour, number):
    return "kenney_prototype_%s_%02d" % (colour.lower(), number)


def build(src, library):
    """Write every set and merge its rows into `<library>/manifest.tsv`; returns the number of sets."""
    from PIL import Image, ImageStat
    lic = os.path.join(src, "License.txt")
    with open(lic, encoding="utf-8", errors="replace") if os.path.isfile(lic) else open(os.devnull) as f:
        if "creativecommons.org/publicdomain/zero" not in f.read():
            raise SystemExit("%s: no CC0 License.txt; not the Kenney Prototype Textures folder" % src)
    png = os.path.join(src, "PNG")
    rows = []
    for colour in sorted(os.listdir(png)):
        for fn in sorted(os.listdir(os.path.join(png, colour))):
            if not (fn.startswith("texture_") and fn.endswith(".png")):
                continue
            sid = set_id(colour, int(fn[len("texture_"):-len(".png")]))
            dest = os.path.join(library, SOURCE, sid)
            os.makedirs(dest, exist_ok=True)
            with Image.open(os.path.join(png, colour, fn)) as im:
                im = im.convert("RGB")
                im.save(os.path.join(dest, sid + "_Color.png"), optimize=True)
                r, g, b = (c / 255.0 for c in ImageStat.Stat(im.resize((64, 64))).mean)
            Image.new("RGB", (FLAT_PX, FLAT_PX), (128, 128, 255)).save(os.path.join(dest, sid + "_NormalGL.png"))
            v = round(ROUGHNESS * 255)
            Image.new("RGB", (FLAT_PX, FLAT_PX), (v, v, v)).save(os.path.join(dest, sid + "_Roughness.png"))
            files = sorted(f for f in os.listdir(dest) if f.endswith(".png"))
            rows.append("\t".join((sid, "Kenney", URL, AUTHOR, LICENCE, "prototype,grid,kenney,%s" % colour.lower(),
                                   "%.3f" % r, "%.3f" % g, "%.3f" % b, ",".join(files))))
            open(os.path.join(dest, ".done"), "w").close()
    man = os.path.join(library, "manifest.tsv")
    kept = []
    if os.path.isfile(man):
        with open(man, encoding="utf-8") as f:
            kept = [ln.rstrip("\n") for ln in f if ln.strip() and (ln.startswith("#") or [c.lower() for c in ln.split("\t")[1:2]] != [SOURCE])]
    tmp = man + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(kept + rows) + "\n")
    os.replace(tmp, man)
    return len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", help="the Prototype Textures folder of the Kenney bundle (PNG/, License.txt)")
    ap.add_argument("--library", help="the PBR library; default $DOT_ART_LIBRARY or ~/art-library/materials")
    a = ap.parse_args(argv)
    lib = a.library or pbrmap.library_root()
    print("kenney_prototypes: %d sets in %s" % (build(a.src, lib), os.path.join(lib, SOURCE)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
