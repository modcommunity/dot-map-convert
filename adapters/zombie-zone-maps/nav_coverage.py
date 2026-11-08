"""How much of a Source map's own navigation mesh (.nav, version 16) the horde's graph stands on.

    ZZ_DEBUG_POINTS=pts.json import_bsp.py spec.json map.bsp outdir     # writes the graph's points
    ZZ_DEBUG_PROPS=props.json (same run, optional)
    python3 -P nav_coverage.py map.nav pts.json [y0] [--props props.json]

Area-weighted share of the .nav's areas with a main-ground point within 1.6 m (and 1.2 m of height); y0 is the spec's metres of floor offset.
build_nav's wide pass leaves cells round decor props (tables, beds, cars) off limits, so with --props the report gives the
coverage raw and with the areas inside those blocks discounted, and lists what is still uncovered by cause.
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


def load_points(path):
    """[(x, y, z, on_main)] from ZZ_DEBUG_POINTS."""
    return [tuple(p[:3]) + (int(p[3]),) for p in json.load(open(path))]


def load_props(path):
    """(cell, [(x, y, z, radius)]) from ZZ_DEBUG_PROPS: the decor props build_nav's wide pass keeps as blocks."""
    d = json.load(open(path))
    return d["cell"], [tuple(b) for b in d["blocks"]]


def classify(areas, pts, props=None, y0=0.0):
    """Split the .nav areas by what the graph does there.

    Returns {cause: m2}. Causes: covered (main-ground point within 1.6 m and 1.2 m of height); prop_blocked (not
    covered, and inside a kept prop's block, +-0.5 m of height: build_nav's wide pass puts that cell off limits, so
    the gap is the decor, not the floor); off_main (a point of another component is near); no_point (nothing near,
    split by 2 m height band as no_point_y<band>)."""
    grid = collections.defaultdict(list)
    for p in pts:
        grid[(int(p[0] // 2), int(p[2] // 2))].append(p)

    def near(x, y, z):
        found = 0
        for gx in range(int(x // 2) - 1, int(x // 2) + 2):
            for gz in range(int(z // 2) - 1, int(z // 2) + 2):
                for p in grid[(gx, gz)]:
                    if (p[0] - x) ** 2 + (p[2] - z) ** 2 <= 2.56 and abs(p[1] - y) <= 1.2:
                        if p[3]:
                            return 2
                        found = 1
        return found

    cell, blocks = props if props else (0.5, [])

    def prop_blocked(x, y, z):
        return any(abs(x - bx) <= r + cell and abs(z - bz) <= r + cell and abs(y - by) <= 0.5 for bx, by, bz, r in blocks)

    out = collections.defaultdict(float)
    for x, z, y, m2 in areas:
        y -= y0
        n = near(x, y, z)
        if n == 2:
            out["covered"] += m2
        elif prop_blocked(x, y, z):
            out["prop_blocked"] += m2
        elif n == 1:
            out["off_main"] += m2
        else:
            out["no_point_y%d" % (int(y // 2) * 2)] += m2
    return dict(out)


def report(res, n_areas):
    total = sum(res.values())
    covered = res.get("covered", 0.0)
    blocked = res.get("prop_blocked", 0.0)
    lines = ["%d areas, %.1f m2" % (n_areas, total),
             "raw coverage:            %.1f%%" % (100 * covered / total)]
    if blocked or "prop_blocked" in res:
        lines.append("prop-discounted coverage: %.1f%% (%.1f m2 inside kept props' blocks left out)" % (100 * covered / (total - blocked), blocked))
    lines.append("uncovered by cause:")
    for k, v in sorted(res.items(), key=lambda kv: -kv[1]):
        if k != "covered":
            lines.append("  %-16s %7.1f m2  %4.1f%% of the .nav" % (k, v, 100 * v / total))
    return "\n".join(lines)


def main(argv):
    args = argv[1:]
    props = None
    if "--props" in args:
        i = args.index("--props")
        props = load_props(args[i + 1])
        del args[i:i + 2]
    y0 = float(args[2]) if len(args) > 2 else 0.0
    areas = read_areas(args[0])
    print(report(classify(areas, load_points(args[1]), props, y0), len(areas)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
