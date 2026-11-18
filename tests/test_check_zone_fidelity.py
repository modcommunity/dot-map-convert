"""tools/check_zone_fidelity.py: a converted pit catches a player only where Source's trigger did.

Run: python3 -P tests/test_check_zone_fidelity.py

The two bhop_arcane_v2 faults, as the manifest records them, must fail; the same triggers
grown by the importer as it grows them now must pass; and the known-file ratchet must hold
a map only at exactly the counts it records.
"""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("check_zone_fidelity",
                                              os.path.join(ROOT, "tools", "check_zone_fidelity.py"))
czf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(czf)

AUDIT = {"teleports": 2, "pits": 2, "claimed": 0, "broken": []}
# bhop_arcane_v2's Restart door, trigger_teleport 423, Source axes.
DOOR = ([1544, -32, 3712], [1552, 32, 3808])
# One of its 1-unit gap strips between the stage-4 red blocks (tops at -5056 here).
STRIP = ([0, 0, -5089], [64, 128, -5088])


def vol(lo, hi, orig, **kw):
    v = {"min": list(lo), "max": list(hi), "original_min": list(orig[0]),
         "original_max": list(orig[1]), "track": 0}
    v.update(kw)
    return v


def godot(lo, hi):
    """Source-axes box to the manifest's Godot axes (x, up, -y)."""
    return [lo[0], lo[2], -hi[1]], [hi[0], hi[2], -lo[1]]


def block(lo, hi):
    a, b = godot(lo, hi)
    return {"min": a, "max": b, "class": "block"}


def doc(volumes, blocks=(), zones=(), audit=AUDIT):
    d = {"respawn_volumes": list(volumes), "zones": list(zones),
         "mechanics": {"blocks": list(blocks)}}
    if audit is not None:
        d["teleport_audit"] = audit
    return d


def kinds(d):
    return sorted({p[0] for p in czf.check(d)})


class ArcaneBefore(unittest.TestCase):
    def test_door_grown_to_192_overreaches(self):
        d = doc([vol([1452, -96, 3616], [1644, 96, 3808], DOOR)])
        self.assertEqual(kinds(d), ["overreach"])

    def test_strip_grown_centred_is_above_its_sheet_and_over_the_blocks(self):
        blocks = [block([-64, 0, -5120], [0, 128, -5056]), block([64, 0, -5120], [128, 128, -5056])]
        d = doc([vol([-64, -32, -5184.5], [128, 160, -4991.5], STRIP)], blocks)
        self.assertEqual(kinds(d), ["above_sheet", "over_landing", "overreach"])


class ArcaneAfter(unittest.TestCase):
    def test_door_grown_by_the_hull_passes(self):
        d = doc([vol([1528, -48, 3616], [1568, 48, 3808], DOOR)])
        self.assertEqual(kinds(d), [])

    def test_strip_hung_from_its_sheet_passes(self):
        blocks = [block([-64, 0, -5120], [0, 128, -5056]), block([64, 0, -5120], [128, 128, -5056])]
        d = doc([vol([-16, -16, -5280], [80, 144, -5088], STRIP, hung=True)], blocks)
        self.assertEqual(kinds(d), [])


class Rules(unittest.TestCase):
    def test_no_audit(self):
        self.assertEqual(kinds(doc([], audit=None)), ["no_audit"])

    def test_broken_and_unaccounted(self):
        audit = dict(AUDIT, broken=[{"entity": 1, "problem": "shadowed"}], no_volume=1)
        self.assertEqual(kinds(doc([], audit=audit)), ["audit_broken", "unaccounted"])

    def test_wide_side_may_not_grow_at_all(self):
        orig = ([0, 0, 0], [512, 512, 1])
        self.assertEqual(kinds(doc([vol([-1, 0, -191], [512, 512, 1], orig)])), ["overreach"])
        self.assertEqual(kinds(doc([vol([0, 0, -191], [512, 512, 1], orig)])), [])

    def test_cleared_pit_keeps_one_tick_above(self):
        orig = ([0, 0, -880], [512, 512, -879])
        self.assertEqual(kinds(doc([vol([0, 0, -895], [512, 512, -863], orig, cleared=True)])), [])
        self.assertEqual(kinds(doc([vol([0, 0, -895], [512, 512, -863], orig)])), ["above_sheet"])
        self.assertEqual(kinds(doc([vol([0, 0, -1071], [512, 512, -863], orig, cleared=True)])),
                         ["above_sheet"])

    def test_buried_route_zone(self):
        pit = {"kind": "RESPAWN", "track": 0, "min": [0, 0, 0], "max": [100, 100, 100]}
        stage = {"kind": "STAGE", "number": 2, "track": 0, "min": [10, 10, 10], "max": [90, 90, 90]}
        free = {"kind": "STAGE", "number": 3, "track": 0, "min": [10, 10, 10], "max": [90, 200, 90]}
        other = dict(stage, track=1)
        self.assertEqual(kinds(doc([], zones=[pit, stage])), ["zone_buried"])
        self.assertEqual(kinds(doc([], zones=[pit, free, other])), [])


class Ratchet(unittest.TestCase):
    def run_main(self, known):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "maps" / "m").mkdir(parents=True)
            (root / "tools").mkdir()
            bad = doc([vol([1452, -96, 3616], [1644, 96, 3808], DOOR)])
            (root / "maps" / "m" / "m.json").write_text(json.dumps(bad))
            if known is not None:
                (root / "tools" / "zone_fidelity_known.json").write_text(json.dumps(known))
            return czf.main([], root=root)

    def test_unknown_failure_fails(self):
        self.assertEqual(self.run_main(None), 1)

    def test_exact_known_count_holds(self):
        self.assertEqual(self.run_main({"m": {"fails": {"overreach": 1}, "reason": "x"}}), 0)

    def test_changed_count_fails(self):
        self.assertEqual(self.run_main({"m": {"fails": {"overreach": 2}, "reason": "x"}}), 1)


if __name__ == "__main__":
    unittest.main()
