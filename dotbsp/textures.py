"""Generated stand-in textures: a deterministic tileable noise image in the original's average
colour, for a surface no free photographic set fits (carpet, glass, water, snow, an unmapped name).
Pure standard library; the PNG is written with `zlib`. Same inputs, same bytes."""

import os
import random
import struct
import zlib


def _png(w, h, rgb_rows):
    raw = b"".join(b"\x00" + bytes(row) for row in rgb_rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def generate(generic, colour, size=128, grain=0.12):
    """PNG bytes: `colour` (r, g, b in 0..1) with tileable value noise of `grain` amplitude.
    The noise lattice wraps, so the image tiles without a seam."""
    colour = [min(1.0, max(0.0, float(c))) for c in (colour or (0.5, 0.5, 0.5))[:3]]
    rng = random.Random("%s:%s" % (generic, ",".join("%.3f" % c for c in colour)))
    cells = 8
    lattice = [[rng.random() for _ in range(cells)] for _ in range(cells)]
    fine = [[rng.random() for _ in range(size)] for _ in range(size)]
    rows = []
    for y in range(size):
        fy = y * cells / size
        y0, ty = int(fy), fy - int(fy)
        row = []
        for x in range(size):
            fx = x * cells / size
            x0, tx = int(fx), fx - int(fx)
            a = lattice[y0 % cells][x0 % cells]
            b = lattice[y0 % cells][(x0 + 1) % cells]
            c = lattice[(y0 + 1) % cells][x0 % cells]
            d = lattice[(y0 + 1) % cells][(x0 + 1) % cells]
            v = (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty
            n = (v - 0.5) * 2 * grain + (fine[y][x] - 0.5) * grain * 0.5
            row += [min(255, max(0, round((ch + n) * 255))) for ch in colour]
        rows.append(row)
    return _png(size, size, rows)


def write(path, generic, colour, size=128):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(generate(generic, colour, size))
