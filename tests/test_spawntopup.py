"""Prop Hunt start top-up: one start still gets hunters, raised floors are looked at their own height."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DOTBSP_PATH", ROOT)

import importlib.util  # noqa: E402

# Loaded by path: the module is pure, and the package import pulls numpy in for nothing here.
_spec = importlib.util.spec_from_file_location("spawntopup", os.path.join(ROOT, "dotbsp", "spawntopup.py"))
spawntopup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spawntopup)


class FakeMap:
    """Open floor at y = floor only: a spot query at any other height finds nothing (a raised floor)."""

    def __init__(self, floor, props=(), hunters=()):
        self.floor = floor
        self.spawns = {"props": [{"at": list(p)} for p in props], "hunters": [{"at": list(h)} for h in hunters]}

    def spots(self, y=0.0, step=1.0, top=40):
        if abs(y - self.floor) > 0.01 and y is not None:
            return []
        return [(3.0, float(i) * 4.0, 0.0) for i in range(40)]

    def spawn(self, side, x, z, yaw=0.0, y=0.05):
        self.spawns[side].append({"at": [x, y, z]})


class TopUp(unittest.TestCase):
    def test_single_start_gets_hunters(self):
        m = FakeMap(0.0, props=[(0, 0.05, 0)])
        spawntopup.top_up(m)
        self.assertGreaterEqual(len(m.spawns["hunters"]), 3)
        self.assertEqual(len(m.spawns["props"]), 8)

    def test_raised_floor_props_use_the_real_height(self):
        m = FakeMap(4.2, props=[(0, 4.25, 0), (8, 4.25, 0)], hunters=[(16, 4.25, 0)])
        spawntopup.top_up(m)
        self.assertEqual(len(m.spawns["props"]), 8)
        self.assertTrue(all(abs(sp["at"][1] - 4.25) < 1e-6 for sp in m.spawns["props"]))

    def test_one_or_two_hunters_untouched_by_default(self):
        m = FakeMap(0.0, props=[(0, 0.05, 0)], hunters=[(8, 0.05, 0)])
        spawntopup.top_up(m)
        self.assertEqual(len(m.spawns["hunters"]), 1)
        spawntopup.top_up(m, hunters_always=True)
        self.assertEqual(len(m.spawns["hunters"]), 3)


if __name__ == "__main__":
    unittest.main()
