"""Prop Hunt start top-up: the hiders' and hunters' starts a BSP's author did not give.

The importer deals the author's starts out (even index hiders, odd hunters); a map with one or two starts
leaves a side short.  This tops them up from the clearest open floor, at least 3 m from every other start.
Pure over a build_maps.Map-like `m` (m.spawns, m.spots(y=, step=, top=), m.spawn(side, x, z, yaw=, y=)) so a
test can drive it with a fake.
"""

GAP2 = 9.0


def levels_of(spawns):
    """Floor heights (m, most used first) the given spawn dicts stand on; spawns carry floor + 0.05."""
    n = {}
    for sp in spawns:
        k = round(sp["at"][1] - 0.05, 3)
        n[k] = n.get(k, 0) + 1
    return sorted(n, key=lambda k: (-n[k], k))


def _fill(m, side, want, levels, have):
    for ly in levels:
        for size, x, z in m.spots(y=ly, step=1.5, top=60):
            if len(m.spawns[side]) >= want:
                return
            if all((x - a) ** 2 + (z - b) ** 2 >= GAP2 for a, b in have):
                m.spawn(side, x, z, yaw=0.0, y=ly + 0.05)
                have.append((x, z))


def top_up(m, props_to=8, hunters_to=3, hunters_always=False):
    """Props up to `props_to`, always.  Hunters up to `hunters_to` when the map has none (the importer would
    crash and a game cannot start), or with `hunters_always` also when it has one or two.  Both look on the
    floor level(s) the author's starts stand on, not on y = 0 (a raised floor has no spot at zero)."""
    have = [(sp["at"][0], sp["at"][2]) for side in m.spawns.values() for sp in side]
    levels = levels_of(m.spawns["props"] + m.spawns["hunters"]) or [0.0]
    _fill(m, "props", props_to, levels, have)
    short = not m.spawns["hunters"] or hunters_always
    if short:
        own = levels_of(m.spawns["hunters"])
        _fill(m, "hunters", hunters_to, own + [k for k in levels if k not in own], have)
    # Still short (the starts stood on ground left out, so no floor at their level): the nearest clear
    # floor to the hiders keeps the two sides joined.
    if short and m.spawns["props"] and len(m.spawns["hunters"]) < hunters_to:
        cx = sum(sp["at"][0] for sp in m.spawns["props"]) / len(m.spawns["props"])
        cz = sum(sp["at"][2] for sp in m.spawns["props"]) / len(m.spawns["props"])
        for size, x, z in sorted(m.spots(step=1.5, top=60), key=lambda t: (t[1] - cx) ** 2 + (t[2] - cz) ** 2):
            if len(m.spawns["hunters"]) >= hunters_to:
                break
            if all((x - a) ** 2 + (z - b) ** 2 >= GAP2 for a, b in have):
                m.spawn("hunters", x, z, yaw=0.0)
                have.append((x, z))
