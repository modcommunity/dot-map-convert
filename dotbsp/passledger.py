"""A ledger of what each box-document pass removes, so a lost brush can be attributed to the pass that dropped it.

The box importers (prop-hunt, murder-mystery, hide-n-seek) prune a map in a row of passes: far scenery, door leaves, small
boxes, trim, merging, the sky slab, the box cap. Each pass is wrapped with `tracked` (or compared with `diff`), which records
how many boxes and how many cubic metres it removed and added, the largest removed boxes, and keeps a copy of every removed
box so `tools/audit_passes.py` can put one pass's boxes back and measure how much of the audit's loss it explains.

Off the books by default: the table is printed at the end of an import (`finish`); with DOTBSP_PASS_LEDGER=1 the sidecar
`<document>.passes.json` is written beside the document. Boxes removed before the importer shifts the map (far scenery,
door leaves, small boxes) are held in the map's first frame; `rebase` moves them with the shift so the sidecar is in the
document's frame throughout.
"""
import copy
import functools
import json
import os

KEEP_SAMPLE = 5          # the largest removed boxes listed per pass
KEEP_ALL = 20000         # removed boxes kept per pass for the audit (a runaway cap, not a budget)


def volume(b):
    s = b["size"]
    return s[0] * s[1] * s[2]


class Ledger:
    def __init__(self):
        self.passes = {}      # name -> row
        self.order = []
        self.notes = {}       # name -> [count, why]

    def row(self, name):
        if name not in self.passes:
            self.passes[name] = {"removed": 0, "removed_m3": 0.0, "added": 0, "added_m3": 0.0, "solid_removed_m3": 0.0,
                                 "largest": [], "boxes": []}
            self.order.append(name)
        return self.passes[name]

    def diff(self, name, before, after):
        """Records what `before` (a list copy) had that `after` has not, and the reverse, by identity."""
        have = {id(b) for b in after}
        was = {id(b) for b in before}
        gone = [b for b in before if id(b) not in have]
        new = [b for b in after if id(b) not in was]
        if not gone and not new:
            return 0
        r = self.row(name)
        r["removed"] += len(gone)
        r["removed_m3"] += sum(volume(b) for b in gone)
        r["solid_removed_m3"] += sum(volume(b) for b in gone if b.get("solid", True))
        r["added"] += len(new)
        r["added_m3"] += sum(volume(b) for b in new)
        r["largest"] = sorted(r["largest"] + [copy.deepcopy(b) for b in gone], key=volume, reverse=True)[:KEEP_SAMPLE]
        room = KEEP_ALL - len(r["boxes"])
        r["boxes"].extend(copy.deepcopy(b) for b in gone[:max(0, room)])
        return len(gone)

    def note(self, name, count, why=""):
        """A drop that is not a box (a brush the importer skips, a crop): counted only."""
        if count:
            n = self.notes.setdefault(name, [0, why])
            n[0] += count

    def rebase(self, dx, dy, dz):
        """Moves every box held so far by (dx, dy, dz): the importer's shift of the finished map."""
        for r in self.passes.values():
            for b in r["boxes"] + r["largest"]:
                b["at"] = [round(b["at"][0] + dx, 3), round(b["at"][1] + dy, 3), round(b["at"][2] + dz, 3)]

    def table(self):
        lines = ["pass                     removed   m3 removed  m3 added  net m3"]
        for name in self.order:
            r = self.passes[name]
            lines.append("%-24s %7d %12.2f %9.2f %7.2f" % (name, r["removed"], r["removed_m3"], r["added_m3"], r["removed_m3"] - r["added_m3"]))
        for name, (n, why) in self.notes.items():
            lines.append("%-24s %7d  (not boxes) %s" % (name, n, why))
        return lines

    def save(self, path):
        out = {"passes": self.passes, "order": self.order, "notes": self.notes}
        with open(path, "w") as f:
            json.dump(out, f, separators=(",", ":"))


LEDGER = Ledger()


def reset():
    global LEDGER
    LEDGER = Ledger()
    return LEDGER


def diff(name, before, after):
    return LEDGER.diff(name, before, after)


def note(name, count, why=""):
    LEDGER.note(name, count, why)


def rebase(dx, dy, dz):
    LEDGER.rebase(dx, dy, dz)


def tracked(name, pick):
    """Decorator for a pass that edits a box list in place. `pick(*args, **kw)` returns that list."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kw):
            lst = pick(*args, **kw)
            before = list(lst) if lst is not None else None
            out = fn(*args, **kw)
            if before is not None:
                LEDGER.diff(name, before, pick(*args, **kw))
            return out
        return inner
    return wrap


def finish(log=print, out_path=None):
    """Prints the table; with DOTBSP_PASS_LEDGER set, writes `<out_path>.passes.json` too."""
    for line in LEDGER.table():
        log("pass ledger: " + line)
    if out_path and os.environ.get("DOTBSP_PASS_LEDGER"):
        LEDGER.save(out_path + ".passes.json")
        log("pass ledger: wrote %s.passes.json" % out_path)
