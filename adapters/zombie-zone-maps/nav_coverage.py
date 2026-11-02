"""How much of a Source map's own navigation mesh (.nav, version 16) the horde's graph stands on.

    ZZ_DEBUG_POINTS=pts.json import_bsp.py spec.json map.bsp outdir     # writes the graph's points
    python3 -I nav_coverage.py map.nav pts.json [y0]

Area-weighted share of the .nav's areas with a main-ground point within 1.6 m (and 1.2 m of height); y0 is the spec's metres of floor offset.
"""
import collections
import json
import struct
import sys

S0 = 0.01905


def read_areas(path):
    d = open(path, "rb").read()
    o = 0

    def u(f):
        nonlocal o
        v = struct.unpack_from("<" + f, d, o)
        o += struct.calcsize(f)
        return v if len(v) > 1 else v[0]

    def skip(n):
        nonlocal o
        o += n

    u("I")
    if u("I") != 16:
        raise SystemExit("only .nav version 16 is read")
    u("I"), u("I"), u("B")
    for _ in range(u("H")):
        skip(u("H"))
    u("B")
    areas = []
    for _ in range(u("I")):
        u("I"), u("I")
        nw, se, (ne, sw) = u("3f"), u("3f"), u("2f")
        for _ in range(4):
            skip(4 * u("I"))
        skip(17 * u("B"))
        for _ in range(u("I")):
            skip(10)
            skip(5 * u("B"))
        u("H")
        for _ in range(2):
            skip(4 * u("I"))
        skip(24)
        skip(5 * u("I"))
        u("I")
        areas.append(((nw[0] + se[0]) / 2 * S0, (nw[2] + se[2] + ne + sw) / 4 * S0,
                      -(nw[1] + se[1]) / 2 * S0, abs(se[0] - nw[0]) * abs(se[1] - nw[1]) * S0 * S0))
    return areas


def main(argv):
    y0 = float(argv[3]) if len(argv) > 3 else 0.0
    grid = collections.defaultdict(list)
    for p in json.load(open(argv[2])):
        if p[3]:
            grid[(int(p[0] // 2), int(p[2] // 2))].append(p)

    def near(x, y, z):
        for gx in range(int(x // 2) - 1, int(x // 2) + 2):
            for gz in range(int(z // 2) - 1, int(z // 2) + 2):
                for p in grid[(gx, gz)]:
                    if (p[0] - x) ** 2 + (p[2] - z) ** 2 <= 2.56 and abs(p[1] - y) <= 1.2:
                        return True
        return False

    areas = read_areas(argv[1])
    total = sum(a[3] for a in areas)
    hit = sum(a[3] for a in areas if near(a[0], a[1] - y0, a[2]))
    print("%d areas, %.1f%% of the .nav's area has a main-ground point" % (len(areas), 100 * hit / total))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
