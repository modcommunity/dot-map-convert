"""A map's lights as a game's lights.

The intermediate already normalises `light`, `light_spot`, `light_environment` and
`light_dynamic` (colour, brightness, cone, the sun's angles). What each adapter then wrote by
hand was the map from those to its own units and its own cost: a brightness of 200 in the map
is an energy and a range in a renderer that has far fewer lights, and a map with 600 lamps
(each one a baked-lightmap helper) is a frame budget it cannot spend. Here:

* `to_game(lights, scale, y0)`: position in metres (Godot axes), colour 0..1, `range` and
  `energy` from the brightness, a spot's cone in degrees, the sun apart;
* `thin(lights, max_lights, min_spacing)`: the same lights every run, brightest kept first,
  none within `min_spacing` metres of one already kept, then cut to `max_lights`
  (the `--max-lights` murder-mystery-maps wrote);
* `spread_order(lamps)`: all of them, reordered so every prefix covers the whole map (a game
  that lights or sends the first N keeps its coverage; `thin` drops lamps, this drops none);
* `auto(cells, ...)`: for a map that has no lamps of its own (it was lit by baked light): one
  every `spacing` metres over the ground cells given, `height` above the floor.

The formulas are zombie-zone-maps' (range 3.5 + b/60 capped at 9 m, energy 0.4 + b/220 capped
at 1.6), kept because three games' lighting was tuned against them; they are parameters.
"""

import math

from . import units as _units


def _r3(v):
    return round(float(v), 3)


def sun_direction(angles, pitch=None):
    """The direction a `light_environment` shines (a unit vector, Godot axes) from its angles
    (pitch, yaw, roll; the entity's `pitch` key overrides the pitch)."""
    p = math.radians(angles[0] if pitch is None else pitch)
    y = math.radians(angles[1])
    # A light_environment's pitch is the direction itself: -90 is straight down (Hammer's
    # convention, the opposite of a camera's angles), so z = sin(pitch), not -sin(pitch).
    fx, fy, fz = math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)
    return (_r3(fx), _r3(fz), _r3(-fy))


def to_game(lights, scale=_units.VISUAL, y0=0.0, range_cap=9.0, energy_cap=1.6,
            range_base=3.5, range_per=1 / 60.0, energy_base=0.4, energy_per=1 / 220.0):
    """(lamps, suns): lamps are [{at, range, energy, colour, entity, spot?}] in metres; suns are
    [{direction, colour, energy, ambient?, entity}]. Order is the document's."""
    lamps, suns = [], []
    for L in lights:
        col = [_r3(c / 255.0) for c in L["colour"]]
        b = L.get("brightness", 200.0)
        if L.get("sun") or L["class"] == "light_environment":
            s = {"entity": L["entity"], "direction": list(sun_direction(L.get("angles", [0, 0, 0]), L.get("pitch"))),
                 "colour": col, "energy": _r3(min(2.0, b / 200.0 + 0.3))}
            if "ambient" in L:
                s["ambient"] = [_r3(c / 255.0) for c in L["ambient"][:3]]
            suns.append(s)
            continue
        at = _units.to_game(L["origin"], scale, y0)
        lamp = {"entity": L["entity"], "at": [_r3(v) for v in at],
                "range": _r3(min(range_cap, range_base + b * range_per)),
                "energy": _r3(min(energy_cap, energy_base + b * energy_per)), "colour": col}
        if L["class"] == "light_spot":
            lamp["spot"] = {"cone": L.get("cone", 45.0), "inner_cone": L.get("inner_cone", 30.0),
                            "direction": list(sun_direction(L.get("angles", [0, 0, 0]), L.get("pitch")))}
        lamps.append(lamp)
    return lamps, suns


def thin(lamps, max_lights=100, min_spacing=0.0):
    """Lamps cut to `max_lights`, deterministic: brightest first (energy, then range), then
    document order; a lamp within `min_spacing` metres (3D) of a kept one is dropped. The result
    keeps the document order, so a diff of two runs is a diff of the maps."""
    order = sorted(range(len(lamps)), key=lambda i: (-lamps[i]["energy"], -lamps[i]["range"], i))
    keep, kept_pts = [], []
    for i in order:
        if len(keep) >= max_lights:
            break
        a = lamps[i]["at"]
        if min_spacing > 0 and any(math.dist(a, b) < min_spacing for b in kept_pts):
            continue
        keep.append(i)
        kept_pts.append(a)
    return [lamps[i] for i in sorted(keep)]


def thin_by_gap(points, max_lights, step=0.5):
    """(kept, gap): murder-mystery-maps' `--max-lights`, exactly. Items stay in document order; the
    minimum gap between kept ones starts at 0 and widens by `step` metres until at most `max_lights`
    fit; an item is kept when it is at least `gap` from every one kept so far (3D, compared squared).
    `points` are [x, y, z] sequences or lamp dicts with an `at` of three numbers (both are read)."""
    def at(p):
        return p["at"] if isinstance(p, dict) else p

    gap = 0.0
    kept = list(points)
    while len(kept) > max_lights:
        gap += step
        kept = []
        for l in points:
            a = at(l)
            if all((a[0] - at(k)[0]) ** 2 + (a[1] - at(k)[1]) ** 2 + (a[2] - at(k)[2]) ** 2 >= gap * gap for k in kept):
                kept.append(l)
    return kept, gap


def spread_order(lamps):
    """Every lamp, reordered so that any prefix is spread over the map: the brightest first, then
    each next one the lamp farthest from all taken (farthest-point order, ties by document order).
    A game that can send or light only the first N of a map's lamps takes `lamps[:N]` and still
    covers the whole map; nothing is dropped, which `thin` does. Deterministic."""
    n = len(lamps)
    if n < 2:
        return list(lamps)
    first = min(range(n), key=lambda i: (-lamps[i]["energy"], -lamps[i]["range"], i))
    order = [first]
    near = [math.dist(lamps[i]["at"], lamps[first]["at"]) for i in range(n)]
    near[first] = -1.0
    while len(order) < n:
        nxt = max(range(n), key=lambda i: (near[i], -i))
        order.append(nxt)
        near[nxt] = -1.0
        a = lamps[nxt]["at"]
        for i in range(n):
            if near[i] >= 0.0:
                near[i] = min(near[i], math.dist(a, lamps[i]["at"]))
    return [lamps[i] for i in order]


def strengthen(energy, gap, cap=1.6, per_metre=1 / 8.0):
    """A kept lamp's energy after thinning to `gap`: a little stronger for those it stood for
    (murder-mystery-maps: `min(1.6, e * (1 + gap / 8))`). Its range is `9 + gap` there."""
    return min(cap, energy * (1.0 + gap * per_metre))


def auto(cells, cell=0.5, spacing=6.0, height=2.3, maximum=100, range_=7.0, energy=0.9, colour=(1.0, 0.93, 0.8)):
    """Lamps for a map with none. `cells` is {(ix, iz): floor y} (or an iterable of (ix, iz, y))
    of `cell`-metre ground cells, which the caller has already limited to the ground it wants lit
    (the flood's main area). One lamp per `spacing` metre square per floor height, `height` above
    the floor, taken in (ix, iz) order so the same map always gets the same lamps; this is
    zombie-zone-maps' order, and sorting by position instead lights different cells."""
    items = cells.items() if isinstance(cells, dict) else (((ix, iz), h) for ix, iz, h in cells)
    taken = {}
    for (ix, iz), h in sorted(items):
        cx, cz = (ix + 0.5) * cell, (iz + 0.5) * cell
        key = (int(math.floor(cx / spacing)), int(math.floor(cz / spacing)), round(h))
        if key not in taken:
            taken[key] = [_r3(cx), _r3(h + height), _r3(cz)]
    return [{"at": at, "range": range_, "energy": energy, "colour": list(colour)}
            for at in list(taken.values())[:maximum]]
