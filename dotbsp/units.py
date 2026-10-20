"""Map units to metres, and the two scales the family uses.

The converter's documents are in map units; a game converts on the way out. Two scales are in
use and they are both right for what they measure:

* `VISUAL` 0.01905 m/unit (3/4 inch): what the map's art was modelled to; the default of the
  intermediate and of every box game that keeps the source's look (a 72 unit player is 1.37 m).
* `HULL` 0.0254 m/unit (a true inch): what makes the 72 unit player hull 1.83 m. A game whose
  rooms, jumps and trap timings must feel like the source's (deathrun, a plan for a level
  generator) converts with this one. Chosen per game, never mixed inside a document.

`intermediate.build(..., scale=)` and `bsp.py convert --scale` record the choice in the
document's `units` block as `metres_per_unit`, so a reader does not have to guess.
"""

VISUAL = 0.01905
HULL = 0.0254
NAMES = {"visual": VISUAL, "hull": HULL}


def parse_scale(text):
    """`visual`, `hull` or a number of metres per unit; ValueError on anything else or <= 0."""
    if isinstance(text, (int, float)):
        v = float(text)
    else:
        t = str(text).strip().lower()
        v = NAMES[t] if t in NAMES else float(t)
    if not v > 0:
        raise ValueError("scale must be positive, got %r" % (text,))
    return v


def to_game(p, scale=VISUAL, y0=0.0):
    """Map (x, y, z) units to Godot metres (x, z - y0, -y): the one axis swap every adapter wrote."""
    return (p[0] * scale, p[2] * scale - y0, -p[1] * scale)


def from_metres(m, scale=VISUAL):
    """Metres to map units (a slab of 0.4 m is `from_metres(0.4, scale)` units)."""
    return m / scale
