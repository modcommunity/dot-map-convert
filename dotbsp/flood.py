"""Reachable space: a flood fill over a game's boxes, with the step limits of a walking body.

Lifted from zombie-zone-maps' `build_nav`, which was the only copy that worked on a cell grid
with a step limit; prop-hunt, hide-n-seek and murder-mystery-maps each had a second, cruder
flood (0.1 m cells, one floor height, `prune_pockets`) for the same question, "can a body get
from the start to here?". This is the one. It answers it for boxes (a game's own document
after the brushes are cut), not for brushes, so it is the same for every game.

A box is a dict in **metres, Godot axes** (y up): {"at": [x, y, z], "size": [sx, sy, sz],
"yaw": degrees (optional)}; `solid: False`, `nav: False` and `_sky` take a box out. A cell is
`cell` metres square. A cell's *surfaces* are the tops of the boxes covering its centre that
have `head` metres of room above. The flood walks from the starts over surfaces: a neighbour
at most `step` higher or lower is walked; one up to `jump` higher or `drop` lower is crossed
(and recorded in `links` as a jump or a drop, for a game with an AI graph); `wide` demands a
two-cell-wide way, so a doorway a prop half-fills does not count.

Where the repositories differed:

* the flood samples a cell at its centre, so a wall thinner than a cell fell between samples
  and the flood walked through it (Run For Your Life's 2 cm dividers). `thin_walls=True`
  counts a wall that overlaps a cell at all; `thin_lintels=True` also counts a thin beam over a
  doorway. Off by default because converted maps were authored against the old behaviour.
* a ledge 12 cm under another (a kerb) is one floor: `snap` merges heights within 0.12 m.
"""

import math
from collections import deque


class Flood:
    def __init__(self, boxes, cell=0.5, head=1.7, step=0.42, jump=0.9, drop=3.0,
                 thin_walls=False, thin_lintels=False, min_floor_y=None):
        self.cell, self.head, self.step, self.jump, self.drop = cell, head, step, jump, drop
        self.thin_walls, self.thin_lintels, self.min_floor_y = thin_walls, thin_lintels, min_floor_y
        self.boxes = [b for b in boxes if b.get("solid", True) and b.get("nav", True) is not False and not b.get("_sky")]
        self.grid = cell_index(self.boxes, cell)
        self.surf = {}
        for ix, iz in list(self.grid):
            s = self.surfaces_at(ix, iz)
            if self.min_floor_y is not None:
                s = [h for h in s if h >= self.min_floor_y]
            if s:
                self.surf[(ix, iz)] = s
        self.seen, self.parent, self.dist, self.links = set(), {}, {}, {}

    # -- cells ----------------------------------------------------------------------------
    def cell_of(self, x, z):
        return int(math.floor(x / self.cell)), int(math.floor(z / self.cell))

    def centre_of(self, ix, iz):
        return (ix + 0.5) * self.cell, (iz + 0.5) * self.cell

    def _thin_wall_over(self, b, ix, iz):
        c = self.cell
        if not self.thin_walls or b.get("yaw") or min(b["size"][0], b["size"][2]) >= c:
            return False
        # A thin beam over a doorway (7 cm, 1.5 m up) is as much in a body's way as a wall; a
        # thin plate on the floor is not.
        if b["size"][1] <= self.head and not (self.thin_lintels and b["at"][1] - b["size"][1] / 2 > 0.8):
            return False
        return (abs(b["at"][0] - (ix + 0.5) * c) < (b["size"][0] + c) / 2
                and abs(b["at"][2] - (iz + 0.5) * c) < (b["size"][2] + c) / 2)

    def surfaces_at(self, ix, iz):
        """Walkable heights in a cell: box tops with headroom above."""
        cx, cz = self.centre_of(ix, iz)
        spans = []
        for bi in self.grid.get((ix, iz), ()):
            b = self.boxes[bi]
            if inside_box(b, cx, cz) or self._thin_wall_over(b, ix, iz):
                spans.append((b["at"][1] - b["size"][1] / 2, b["at"][1] + b["size"][1] / 2))
        out = []
        for lo, hi in spans:
            if any(l2 < hi + self.head and h2 > hi + 0.05 for l2, h2 in spans if (l2, h2) != (lo, hi)):
                continue
            out.append(round(hi, 2))
        return sorted(set(out))

    # -- the flood ------------------------------------------------------------------------
    def run(self, starts, blocked=None, wide=False):
        """Flood from `starts` ((x, y, z) metres). `blocked` is {(ix, iz): [heights]} of cells
        something else occupies (a prop). Fills `seen` ((ix, iz, h) triples), `parent`, `dist`
        (cells walked) and `links` ({key: [x0, y0, z0, x1, y1, z1]} jumps and drops). Returns self."""
        surf, step, jump, drop = self.surf, self.step, self.jump, self.drop
        blocked = blocked or {}
        self.seen, self.parent, self.dist, self.links = set(), {}, {}, {}
        seen, parent, dist, links = self.seen, self.parent, self.dist, self.links
        dq = deque()

        def is_open(ix, iz, h):
            return not any(abs(by - h) <= 0.5 for by in blocked.get((ix, iz), ()))

        def is_wide(ix, iz, h):
            """A way narrower than two cells has no point in it, and a prop in the middle of a
            doorway takes the rest: only a 2x2 block of open cells counts."""
            for ox in (-1, 0):
                for oz in (-1, 0):
                    if all(any(abs(h2 - h) <= step and is_open(ix + ox + i, iz + oz + j, h2)
                               for h2 in surf.get((ix + ox + i, iz + oz + j), ())) for i in (0, 1) for j in (0, 1)):
                        return True
            return False

        for st in starts:
            ix, iz = self.cell_of(st[0], st[2])
            cands = [h for h in surf.get((ix, iz), []) if h <= st[1] + 0.6]
            if cands:
                h = max(cands)
                seen.add((ix, iz, h))
                dist[(ix, iz, h)] = 0
                dq.append((ix, iz, h))
        while dq:
            ix, iz, h = dq.popleft()
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, nz = ix + dx, iz + dz
                for h2 in surf.get((nx, nz), ()):
                    if (nx, nz, h2) in seen:
                        continue
                    dh = h2 - h
                    ok = not wide or (is_open(nx, nz, h2) and is_wide(nx, nz, h2))
                    if (-drop <= dh < -step or step < dh <= jump) and ok:
                        key = (ix // 3, iz // 3, round(h, 1), round(h2, 1))
                        if key not in links:
                            c0, c1 = self.centre_of(ix, iz), self.centre_of(nx, nz)
                            links[key] = [round(c0[0], 3), round(h, 3), round(c0[1], 3), round(c1[0], 3), round(h2, 3), round(c1[1], 3)]
                    if (abs(dh) <= step or -drop <= dh <= jump) and ok:
                        seen.add((nx, nz, h2))
                        parent[(nx, nz, h2)] = (ix, iz, h)
                        dist[(nx, nz, h2)] = dist[(ix, iz, h)] + 1
                        dq.append((nx, nz, h2))
        return self

    def reachable(self, x, y, z, slack=0.8):
        """Is the point (metres) on ground the flood reached? The floor height there, or None."""
        ix, iz = self.cell_of(x, z)
        hs = [h for h in self.surf.get((ix, iz), []) if (ix, iz, h) in self.seen and h <= y + slack]
        return max(hs) if hs else None

    def standing(self, x, y, z, slack=0.6):
        """Floor height under a point (metres) from the surfaces alone, flood or no flood; None
        when there is none at or below `y + slack`."""
        ix, iz = self.cell_of(x, z)
        hs = [h for h in self.surf.get((ix, iz), []) if h <= y + slack]
        return max(hs) if hs else None

    def keep_starts(self, starts, max_below=8.0):
        """(kept, dropped): the start points (x, y, z metres) a spawn list should keep. A start
        with no floor under it (a point inside a wall, or over a void) is dropped, and so is one
        more than `max_below` metres under the median start (a map's cellar spawn that nobody
        else shares). murder-mystery-maps wrote this as its start filter."""
        if not starts:
            return [], []
        ys = sorted(p[1] for p in starts)
        median = ys[len(ys) // 2]
        kept, dropped = [], []
        for p in starts:
            ok = self.standing(p[0], p[1], p[2]) is not None and p[1] >= median - max_below
            (kept if ok else dropped).append(p)
        return kept, dropped

    def cells(self):
        """{(ix, iz)} walked, any height."""
        return {(a, b) for a, b, _ in self.seen}

    def points(self):
        """[(x, floor y, z)] at every walked cell's centre, for `lights.auto`."""
        return [(self.centre_of(ix, iz)[0], h, self.centre_of(ix, iz)[1]) for ix, iz, h in self.seen]

    def lost(self, other):
        """Cells `other` (an earlier flood) reached that this one did not: a prop that cut a
        room off shows here."""
        return other.cells() - self.cells()

    # -- floors ---------------------------------------------------------------------------
    def floor_rects(self, greedy=False, snap_within=0.12, inset=0.05):
        """The walked cells as rectangles [x0, z0, x1, z1, y] (metres), per floor height.

        Heights within `snap_within` are one floor (a kerb, a worn step): a game joins nav
        points by distance and two floors 0.1 m apart that merely touch are not joined. The
        default merges rows with identical runs; `greedy` takes the longest run from the first
        free cell and grows it down while the whole run stays free, which is far fewer pieces
        on an irregular plan (hundreds of slivers fell over a document's 800-floor budget).
        """
        c = self.cell
        hs = sorted({h for _, _, h in self.seen})
        snap, i = {}, 0
        while i < len(hs):
            j = i
            while j + 1 < len(hs) and hs[j + 1] - hs[i] <= snap_within:
                j += 1
            for k in range(i, j + 1):
                snap[hs[k]] = hs[j]
            i = j + 1
        byh = {}
        for ix, iz, h in self.seen:
            byh.setdefault(snap[h], set()).add((ix, iz))
        out = []

        def rect(ax, az, bx, bz, h):
            out.append([round(ax * c + inset, 3), round(az * c + inset, 3), round((bx + 1) * c - inset, 3),
                        round((bz + 1) * c - inset, 3), round(h, 3)])

        for h, cells in sorted(byh.items()):
            if greedy:
                free = set(cells)
                for iz, ix in sorted((q[1], q[0]) for q in cells):
                    if (ix, iz) not in free:
                        continue
                    xe = ix
                    while (xe + 1, iz) in free:
                        xe += 1
                    ze = iz
                    while all((x, ze + 1) in free for x in range(ix, xe + 1)):
                        ze += 1
                    for z in range(iz, ze + 1):
                        for x in range(ix, xe + 1):
                            free.discard((x, z))
                    rect(ix, iz, xe, ze, h)
                continue
            rows = {}
            for ix, iz in cells:
                rows.setdefault(iz, []).append(ix)
            runs = {}
            for iz, xs in rows.items():
                xs.sort()
                a = prev = xs[0]
                for x in xs[1:] + [None]:
                    if x is not None and x == prev + 1:
                        prev = x
                        continue
                    runs.setdefault((a, prev), []).append(iz)
                    if x is not None:
                        a = prev = x
            for (a, bb), izs in runs.items():
                izs.sort()
                s = p = izs[0]
                for z in izs[1:] + [None]:
                    if z is not None and z == p + 1:
                        p = z
                        continue
                    rect(a, s, bb, p, h)
                    if z is not None:
                        s = p = z
        return out


def inside_box(b, x, z):
    """Is the point (x, z) inside the box's footprint (turned by its yaw about its centre)?"""
    dx, dz = x - b["at"][0], z - b["at"][2]
    yaw = b.get("yaw", 0)
    if yaw:
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        lx, lz = dx * c - dz * s, dx * s + dz * c
    else:
        lx, lz = dx, dz
    return abs(lx) <= b["size"][0] / 2 and abs(lz) <= b["size"][2] / 2


def cell_index(boxes, cell=0.5):
    """{(ix, iz): [box index]}: which boxes could cover a cell (a turned box by its circle)."""
    grid = {}
    for bi, b in enumerate(boxes):
        if b.get("yaw"):
            r = math.hypot(b["size"][0], b["size"][2]) / 2
            x0, x1, z0, z1 = b["at"][0] - r, b["at"][0] + r, b["at"][2] - r, b["at"][2] + r
        else:
            x0, x1 = b["at"][0] - b["size"][0] / 2, b["at"][0] + b["size"][0] / 2
            z0, z1 = b["at"][2] - b["size"][2] / 2, b["at"][2] + b["size"][2] / 2
        for ix in range(int(math.floor(x0 / cell)), int(math.floor(x1 / cell)) + 1):
            for iz in range(int(math.floor(z0 / cell)), int(math.floor(z1 / cell)) + 1):
                grid.setdefault((ix, iz), []).append(bi)
    return grid
