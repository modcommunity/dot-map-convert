"""Source textures: a vtf as RGBA pixels and a PNG, and the `$basetexture` of a vmt.

Reads the largest mip no bigger than `max_side` of the first frame, in the formats maps pack
(DXT1, DXT3, DXT5, BGRA8888, RGBA8888, BGR888, RGB888, I8, IA88). A format it does not know raises
`TextureError`; the caller keeps the material's average colour instead. Standard library only.
"""

import re
import struct
import zlib


class TextureError(ValueError):
    pass


# format id: (name, bytes per pixel, or block bytes for DXT)
FORMATS = {0: ("RGBA8888", 4), 2: ("RGB888", 3), 3: ("BGR888", 3), 12: ("BGRA8888", 4), 13: ("DXT1", 8),
           14: ("DXT3", 16), 15: ("DXT5", 16), 5: ("I8", 1), 6: ("IA88", 2), 1: ("ABGR8888", 4)}


def _size(fmt, w, h):
    name, b = FORMATS[fmt]
    if name.startswith("DXT"):
        return ((w + 3) // 4) * ((h + 3) // 4) * b
    return w * h * b


def _565(c):
    return ((c >> 11 & 31) * 255 // 31, (c >> 5 & 63) * 255 // 63, (c & 31) * 255 // 31)


def _colour_block(d, o, opaque_only):
    c0, c1, bits = struct.unpack_from("<HHI", d, o)
    a, b = _565(c0), _565(c1)
    if c0 > c1 or not opaque_only:
        pal = [a + (255,), b + (255,),
               tuple((2 * x + y) // 3 for x, y in zip(a, b)) + (255,),
               tuple((x + 2 * y) // 3 for x, y in zip(a, b)) + (255,)]
    else:
        pal = [a + (255,), b + (255,), tuple((x + y) // 2 for x, y in zip(a, b)) + (255,), (0, 0, 0, 0)]
    return [pal[bits >> (2 * i) & 3] for i in range(16)]


def _alpha_block(d, o):
    a0, a1 = d[o], d[o + 1]
    bits = int.from_bytes(d[o + 2:o + 8], "little")
    if a0 > a1:
        pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    else:
        pal = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
    return [pal[bits >> (3 * i) & 7] for i in range(16)]


def decode(fmt, w, h, d):
    """[(r, g, b, a)] row by row."""
    name = FORMATS[fmt][0]
    px = [None] * (w * h)
    if name.startswith("DXT"):
        bw, step = (w + 3) // 4, FORMATS[fmt][1]
        for by in range((h + 3) // 4):
            for bx in range(bw):
                o = (by * bw + bx) * step
                if name == "DXT1":
                    cols = _colour_block(d, o, True)
                elif name == "DXT3":
                    cols = _colour_block(d, o + 8, False)
                    al = int.from_bytes(d[o:o + 8], "little")
                    cols = [c[:3] + ((al >> (4 * i) & 15) * 17,) for i, c in enumerate(cols)]
                else:
                    cols = _colour_block(d, o + 8, False)
                    al = _alpha_block(d, o)
                    cols = [c[:3] + (al[i],) for i, c in enumerate(cols)]
                for i, c in enumerate(cols):
                    x, y = bx * 4 + i % 4, by * 4 + i // 4
                    if x < w and y < h:
                        px[y * w + x] = c
        return px
    n = FORMATS[fmt][1]
    for i in range(w * h):
        p = d[i * n:(i + 1) * n]
        px[i] = {"RGBA8888": lambda: tuple(p), "RGB888": lambda: tuple(p) + (255,), "BGR888": lambda: (p[2], p[1], p[0], 255),
                 "BGRA8888": lambda: (p[2], p[1], p[0], p[3]), "ABGR8888": lambda: (p[3], p[2], p[1], p[0]),
                 "I8": lambda: (p[0], p[0], p[0], 255), "IA88": lambda: (p[0], p[0], p[0], p[1])}[name]()
    return px


def read(data, max_side=512):
    """(width, height, [(r, g, b, a)]) of the largest mip that fits `max_side`."""
    if len(data) < 64 or data[:4] != b"VTF\0":
        raise TextureError("not a vtf")
    major, minor, hsize, w, h, flags, frames = struct.unpack_from("<IIIHHIH", data, 4)
    fmt = struct.unpack_from("<i", data, 52)[0]
    mips = data[56]
    low_fmt, lw, lh = struct.unpack_from("<iBB", data, 57)
    if fmt not in FORMATS:
        raise TextureError("vtf format %d" % fmt)
    faces = 6 if flags & 0x4000 else 1
    off = hsize
    if lw and lh and low_fmt in FORMATS:
        off += _size(low_fmt, lw, lh)
    elif lw and lh:
        raise TextureError("thumbnail format %d" % low_fmt)
    # mips are stored smallest first; each holds every frame (and face) of that size
    sizes = []
    for m in range(mips):
        mw, mh = max(1, w >> m), max(1, h >> m)
        sizes.append((mw, mh, _size(fmt, mw, mh) * frames * faces))
    pos = {}
    for m in range(mips - 1, -1, -1):
        pos[m] = off
        off += sizes[m][2]
    pick = next((m for m in range(mips) if max(sizes[m][0], sizes[m][1]) <= max_side), mips - 1)
    mw, mh, _ = sizes[pick]
    return mw, mh, decode(fmt, mw, mh, data[pos[pick]:pos[pick] + _size(fmt, mw, mh)])


def average(px):
    """Mean (r, g, b) over opaque-ish pixels, 0 to 1."""
    n = [c for c in px if c[3] > 32] or px
    return tuple(round(sum(c[k] for c in n) / len(n) / 255, 3) for k in range(3))


def png(w, h, px):
    raw = b"".join(b"\0" + bytes(v for c in px[y * w:(y + 1) * w] for v in c) for y in range(h))

    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def vmt_keys(text):
    """Lower-case key to value of the first block of a vmt, quotes removed: enough for `$basetexture`,
    `$translucent`, `$alphatest`, `$color`, `$model`."""
    out = {}
    for line in text.splitlines():
        line = re.sub(r"//.*$", "", line) if line.count('"') % 2 == 0 and not re.search(r'"[^"]*//[^"]*"', line) else line
        m = re.match(r'\s*"?(\$?[A-Za-z0-9_]+)"?\s+"([^"]*)"\s*$', line) or re.match(r'\s*"?(\$?[A-Za-z0-9_]+)"?\s+([^"\s]+)\s*$', line)
        if m:
            out.setdefault(m.group(1).lower(), m.group(2).strip())
    return out


def base_texture(vmt_text):
    """The vtf path inside `materials/` a vmt draws, or None."""
    t = vmt_keys(vmt_text).get("$basetexture")
    return t.replace("\\", "/").lower().strip("/") if t else None
