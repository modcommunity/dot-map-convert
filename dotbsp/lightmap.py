"""A map's baked lighting (vrad's lightmap) packed into atlas pages, one placement per face.

Source stores a face's lighting as `width x height` RGBE texels at `lightofs` in lump 8 (LDR) or
53 (HDR): per light style, one base sample and, on a bumped face (`SURF_BUMPLIGHT`), three
directional ones after it. Only the base sample of style 0 is read; the bump directions and the
other styles (flicker, pulse) are not kept. A texel is `c * 2^e / 255` in linear light.

The atlas pages are `RGB9E5` (Godot's `Image.FORMAT_RGBE9995`): four bytes a texel, HDR, filterable.
A face is placed with one texel of replicated border, and its vertices sample the texel centres.
"""

import numpy as np

from . import reader

PAGE = 2048
PAD = 1
SURF_LIGHT, SURF_NOLIGHT, SURF_BUMPLIGHT = 0x1, 0x400, 0x800
LUMP_LIGHTING_HDR, LUMP_FACES_HDR = 53, 58
WHITE = 4           # the unlit patch at the page-0 origin, in texels


def rgb9e5(rgb):
    """float (..., 3) -> uint32 (...) in the shared-exponent format the GPU reads."""
    c = np.clip(rgb.astype(np.float64), 0.0, 65408.0)
    top = np.maximum(c.max(axis=-1), 2.0 ** -16)
    exp = np.maximum(-16.0, np.floor(np.log2(top))) + 16
    denom = 2.0 ** (exp - 24)
    over = np.floor(top / denom + 0.5) >= 512
    exp = np.where(over, exp + 1, exp)
    denom = np.where(over, denom * 2, denom)
    m = np.minimum(np.floor(c / denom[..., None] + 0.5), 511).astype(np.uint32)
    return m[..., 0] | (m[..., 1] << 9) | (m[..., 2] << 18) | (exp.astype(np.uint32) << 27)


class Atlas:
    """Pages of packed luxels; `place[id(face)]` is (page, x, y) of the face's first texel."""

    def __init__(self):
        self.pages = []
        self.heights = []
        self.place = {}
        self.lit_faces = 0
        self.texels = 0


def _light_lump(bsp):
    ldr = bsp._lump(reader.LUMP_LIGHTING)
    if len(ldr):
        return ldr, bsp.faces
    hdr = bsp._lump(LUMP_LIGHTING_HDR)
    hf = bsp._lump(LUMP_FACES_HDR)
    if len(hdr) and len(hf) == 56 * len(bsp.faces):
        import struct
        return hdr, [struct.unpack_from(reader.FMT_FACE, hf, 56 * i) for i in range(len(bsp.faces))]
    return b"", bsp.faces


def luxels(bsp, face, lumps):
    """The (h, w, 3) linear base-sample colours of one face, or None when it has no lighting."""
    light, faces = lumps
    ti = bsp.texinfo[face[5]] if 0 <= face[5] < len(bsp.texinfo) else None
    if ti is None or int(ti[16]) & SURF_NOLIGHT:
        return None
    w, h = face[13] + 1, face[14] + 1
    slot = [s for s in face[8][:4]].index(0) if 0 in face[8][:4] else -1
    if slot < 0 or face[9] < 0:
        return None
    per = 4 if int(ti[16]) & SURF_BUMPLIGHT else 1
    at = face[9] + slot * per * w * h * 4
    if at + w * h * 4 > len(light):
        return None
    raw = np.frombuffer(light, dtype=np.uint8, count=w * h * 4, offset=at).reshape(h, w, 4)
    e = raw[..., 3].astype(np.int8).astype(np.float64)
    return raw[..., :3].astype(np.float64) * (2.0 ** e)[..., None] / 255.0


def pack(bsp, faces):
    """An `Atlas` holding every lit face of `faces` (tuples of `bsp.faces`), or None if there is none."""
    lumps = _light_lump(bsp)
    if not len(lumps[0]):
        return None
    jobs = []
    for f in faces:
        lx = luxels(bsp, f, lumps)
        if lx is not None:
            jobs.append((f, lx))
    if not jobs:
        return None
    jobs.sort(key=lambda j: -j[1].shape[0])
    atlas = Atlas()
    cur = {"x": WHITE + 2 * PAD, "y": 0, "shelf": WHITE + 2 * PAD, "blocks": []}
    pages = []

    def new_page():
        cur.update(x=0, y=0, shelf=0, blocks=[])
        pages.append(cur["blocks"])

    cur["blocks"] = []
    pages.append(cur["blocks"])
    for f, lx in jobs:
        h, w = lx.shape[:2]
        pw, ph = w + 2 * PAD, h + 2 * PAD
        if cur["x"] + pw > PAGE:
            cur["x"], cur["y"], cur["shelf"] = 0, cur["y"] + cur["shelf"], 0
        if cur["y"] + ph > PAGE:
            new_page()
        cur["blocks"].append((cur["x"], cur["y"], lx))
        atlas.place[id(f)] = (len(pages) - 1, cur["x"] + PAD, cur["y"] + PAD)
        cur["x"] += pw
        cur["shelf"] = max(cur["shelf"], ph)
        atlas.texels += w * h
    atlas.lit_faces = len(jobs)
    white = rgb9e5(np.ones((WHITE + 2 * PAD, WHITE + 2 * PAD, 3)))
    for i, blocks in enumerate(pages):
        height = max(b[1] + b[2].shape[0] + 2 * PAD for b in blocks)
        if i == 0:
            height = max(height, WHITE + 2 * PAD)
        height = 1 << (height - 1).bit_length()
        img = np.zeros((height, PAGE), dtype=np.uint32)
        if i == 0:
            img[:WHITE + 2 * PAD, :WHITE + 2 * PAD] = white
        for x, y, lx in blocks:
            padded = np.pad(lx, ((PAD, PAD), (PAD, PAD), (0, 0)), mode="edge")
            img[y:y + padded.shape[0], x:x + padded.shape[1]] = rgb9e5(padded)
        atlas.pages.append(img)
        atlas.heights.append(height)
    return atlas


def uv2(atlas, f, ti, p):
    """(page, (u, v)) of map-unit point `p` on face `f`; an unlit face reads the white patch."""
    pl = atlas.place.get(id(f))
    if pl is None:
        page, u, v = 0, WHITE * 0.5 + PAD, WHITE * 0.5 + PAD
    else:
        page = pl[0]
        lu = p[0] * ti[8] + p[1] * ti[9] + p[2] * ti[10] + ti[11] - f[11]
        lv = p[0] * ti[12] + p[1] * ti[13] + p[2] * ti[14] + ti[15] - f[12]
        u = pl[1] + min(max(lu, 0.0), float(f[13])) + 0.5
        v = pl[2] + min(max(lv, 0.0), float(f[14])) + 0.5
    return page, (u / PAGE, v / atlas.heights[page])


LUMP_AMBIENT_INDEX, LUMP_AMBIENT = 52, 56


def ambient(bsp, scale, y0):
    """Per-leaf ambient cubes (lumps 52 and 56) as [(x, y, z, [6 x (r, g, b)])], metres, Godot axes.

    The colours are +x, -x, +y, -y, +z, -z in Godot's axes (the source's +z is up, +y is -z).
    A leaf's sample sits at x/255 of the way across its bounds, or the leaf's centre when the map
    stores one cube per leaf. Empty for a v19 map, whose leaves carry their cube inline. The colours are
    `c * 2^e` with no /255: measured on three maps that lands at about a third of the lightmap's
    level, which a sphere average should; with /255 it is 300 times too dark.
    """
    import struct
    idx, amb = bsp._lump(LUMP_AMBIENT_INDEX), bsp._lump(LUMP_AMBIENT)
    leaves = len(bsp.leafs)
    if len(amb) == 24 * leaves and not len(idx):
        return [_cube(amb, 24 * i, [(l + h) / 2.0 for l, h in zip(leaf[3:6], leaf[6:9])], scale, y0)
                for i, leaf in enumerate(bsp.leafs) if leaf[1] >= 0]
    n = len(idx) // 4
    if not n or len(amb) % 28 or n != leaves:
        return []
    out = []
    for li, leaf in enumerate(bsp.leafs):
        count, first = struct.unpack_from("<HH", idx, 4 * li)
        for k in range(first, first + count):
            if (k + 1) * 28 > len(amb):
                break
            fx, fy, fz = struct.unpack_from("<3B", amb, 28 * k + 24)
            lo, hi = leaf[3:6], leaf[6:9]
            p = [lo[i] + (hi[i] - lo[i]) * f / 255.0 for i, f in enumerate((fx, fy, fz))]
            out.append(_cube(amb, 28 * k, p, scale, y0))
    return out


def _cube(amb, at, p, scale, y0):
    import struct
    cube = []
    for j in range(6):
        r, g, b, e = struct.unpack_from("<3Bb", amb, at + 4 * j)
        cube.append([c * 2.0 ** e for c in (r, g, b)])
    order = (0, 1, 4, 5, 3, 2)
    return (p[0] * scale, p[2] * scale - y0, -p[1] * scale, [cube[i] for i in order])
