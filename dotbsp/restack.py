"""Restack: lowers a prop that floats onto the support below it (a box top or another prop's top).

A converted map keeps a prop at the height the source map put it; when the supports under it are
later shrunk (real-size props) it hangs in the air. Dropping it loses the dressing, so it is set
down on whatever is under it instead. The game's own geometry knowledge comes in as callables, so
the pass is the same for every game's document: `footprint(prop)` is its (width, depth)
and `rest_on(under, dx, dz, prop)` how high above `under`'s base the
prop comes to rest on it.
"""
from . import docboxes

# A prop within this far under its base counts as standing (matches the games' own audits).
TOUCH_BELOW = 0.12
TOUCH_ABOVE = 0.04


class RestackError(Exception):
    """A floating prop has no support within the allowed drop (strict mode)."""


def _samples(q, w, d):
    cx, cz = q["at"][0], q["at"][2]
    return [(cx + fx * w, cz + fz * d) for fx in (-0.3, 0.0, 0.3) for fz in (-0.3, 0.0, 0.3)]


def support_below(doc, q, footprint, rest_on):
    """The highest surface under the prop's sample points that is not above its base (plus a
    4 cm touch tolerance), or None."""
    top_limit = q["at"][1] + TOUCH_ABOVE
    solid = [b for b in doc["boxes"] if b.get("solid", True)]
    w, d = footprint(q)
    best = None
    for px, pz in _samples(q, w, d):
        for b in solid:
            t = b["at"][1] + b["size"][1] / 2
            if t <= top_limit and (best is None or t > best) and docboxes.within(b, px, pz, 0.0):
                best = t
        for o in doc["props"]:
            if o is q:
                continue
            ow, od = footprint(o)
            if abs(px - o["at"][0]) <= ow / 2 and abs(pz - o["at"][2]) <= od / 2:
                t = o["at"][1] + rest_on(o, px - o["at"][0], pz - o["at"][2], q)
                if t <= top_limit and (best is None or t > best):
                    best = t
    return best


def restack(doc, footprint, rest_on, max_drop=0.0, skip=lambda q: False, strict=False):
    """Lowers every floating prop of `doc` onto the support below, lowest props first so what
    stood on a lowered prop follows it (the order is repeated until nothing moves). A prop
    already standing, or one `skip` names (ceiling and water props), stays. `max_drop` is the
    furthest a prop may fall in metres (0 = unlimited). Returns (lowered, unsupported): the props
    moved and the props with no support within reach, left where they are; strict raises
    RestackError naming them instead."""
    lowered, lost = [], {}
    for _ in range(8):
        moved = False
        for q in sorted(doc["props"], key=lambda t: t["at"][1]):
            if skip(q) or id(q) in lost:
                continue
            base = q["at"][1]
            top = support_below(doc, q, footprint, rest_on)
            if top is None or (max_drop and base - top > max_drop):
                lost[id(q)] = q
                continue
            if base - top <= TOUCH_BELOW:
                continue
            q["at"][1] = round(top, 4)
            lowered.append(q)
            moved = True
        if not moved:
            break
    lost = list(lost.values())
    if strict and lost:
        raise RestackError("%d props float with no support within %s m: %s" % (
            len(lost), max_drop or "any", ", ".join("%s at %s" % (q["id"], q["at"]) for q in lost[:8])))
    return lowered, lost
