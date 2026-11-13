"""Original textures for an `_orig` conversion: INTERNAL ONLY, never published, never committed.

A normal conversion replaces every texture with a free one (`licence.annotate`). An `_orig` pack
also carries the map's own textures, so the original look and its original UVs (the .bin already
holds the source texture coordinate over the source texture size) can be seen together. Each
surface's material is looked up first in the map's own pakfile (`.vmt` + `.vtf`), then in the
installed base games (`vpk.BaseGame`, cached by `vpk.TextureCache`). The PNGs are written to
`<out dir>/textures/orig/` and named by `surface["orig"]`; `doc["original_textures"]` records that
the pack is internal and lists what was found and what was not. Surfaces without a texture keep
only their free replacement, so the runtime falls back to it.
"""

import os
import re

from . import reader, vpk, vtf

DIR = "textures/orig"
MARK = "_orig"


def is_orig_name(name):
    return name.lower().endswith(MARK)


def safe(material):
    return re.sub(r"[^a-z0-9_.-]+", "_", reader.clean_material(material).lower())[:80] or "unnamed"


def pak_material(pak, material):
    """PNG-ready (w, h, px) of a material the map's own pakfile packs, or None. `pak` is {lowercase name: bytes}."""
    path = reader.clean_material(material).lower().replace("\\", "/")
    raw = pak.get("materials/%s.vmt" % path)
    if raw is None:
        raw = next((v for k, v in pak.items() if k.startswith("materials/maps/") and k.endswith("/%s.vmt" % path)), None)
    tex = None
    if raw is not None:
        base = vtf.base_texture(raw.decode("latin-1"))
        tex = pak.get("materials/%s.vtf" % base) if base else None
    else:
        tex = pak.get("materials/%s.vtf" % path)
    if tex is None:
        return None
    try:
        return vtf.read(tex, 512)
    except Exception:
        return None


def ship(doc, bsp, outdir, cache=None):
    """Write the original textures of every surface of `doc` under `outdir`; sets `surface["orig"]`. Returns the record."""
    pak = bsp.read_pak([], only=(".vmt", ".vtf"))
    cache = cache if cache is not None else vpk.TextureCache()
    root = os.path.join(outdir, DIR)
    found, missing, written = {}, set(), {}
    for s in doc["surfaces"]:
        m = s.get("material") or ""
        if m not in found and m not in missing:
            name = safe(m)
            png = None
            hit = pak_material(pak, m)
            src = "pak"
            if hit:
                png = vtf.png(*hit)
            elif cache.game:
                png = cache.png(m)
                src = "base"
            if png is None:
                missing.add(m)
            else:
                rel = "%s/%s.png" % (DIR, name)
                if rel not in written:
                    os.makedirs(root, exist_ok=True)
                    with open(os.path.join(outdir, rel), "wb") as f:
                        f.write(png)
                    written[rel] = src
                found[m] = rel
        if m in found:
            s["orig"] = found[m]
    rec = {"internal_only": True, "textures": len(written), "from_pak": sum(1 for v in written.values() if v == "pak"),
           "from_base": sum(1 for v in written.values() if v == "base"), "missing": sorted(missing),
           "note": "The map's own textures (Valve and the map author's): for the internal original pack only; never publish or commit this directory."}
    doc["original_textures"] = rec
    return rec
