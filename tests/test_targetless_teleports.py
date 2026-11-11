"""A trigger_teleport with no target is dropped, not sent to the spawn.
Run: python3 -P tests/test_targetless_teleports.py
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "adapters", "game-g2gfast"))
sys.path.insert(0, ROOT)

# bsp_import reads through game-airdrift's `bsp_read` shim, which lives in that game's repo.
os.environ.setdefault("DOTBSP_PATH", ROOT)
for READER in (os.environ.get("G2G_TOOLS", ""),
               os.path.join(os.path.dirname(ROOT), "game-g2gfast", "tools"),
               "/home/gamedev/godot/game-g2gfast/tools"):
    if READER and os.path.isfile(os.path.join(READER, "bsp_read.py")):
        sys.path.append(READER)
        break
try:
    import bsp_import  # noqa: E402
except ModuleNotFoundError as err:
    raise unittest.SkipTest("bsp_read not found (set G2G_TOOLS): %s" % err)


def zoner(entities):
    return bsp_import.Zoner(types.SimpleNamespace(entities=entities))


class Targetless(unittest.TestCase):
    def setUp(self):
        self.z = zoner([
            {"classname": "trigger_teleport", "targetname": "xStage1TimerTele"},
            {"classname": "trigger_teleport", "targetname": "blank", "target": "  "},
            {"classname": "trigger_teleport", "target": "dest"},
            {"classname": "info_teleport_destination", "targetname": "dest"},
            {"classname": "trigger_hurt"},
        ])

    def test_drops_only_the_empty_targets(self):
        self.assertEqual(bsp_import.targetless_teleports(self.z), 2)
        self.assertEqual(self.z.claimed, {0, 1})
        self.assertEqual([i for i, _ in self.z.entities("trigger_teleport")], [2])

    def test_logs_them_by_name(self):
        bsp_import.targetless_teleports(self.z)
        self.assertEqual(len(self.z.notes), 1)
        self.assertIn("2 teleports dropped that have no target", self.z.notes[0])
        self.assertIn("xStage1TimerTele", self.z.notes[0])

    def test_nothing_to_drop_logs_nothing(self):
        z = zoner([{"classname": "trigger_teleport", "target": "a"}])
        self.assertEqual(bsp_import.targetless_teleports(z), 0)
        self.assertEqual(z.notes, [])

    def test_a_claimed_teleport_is_left_alone(self):
        self.z.claimed.add(0)
        self.assertEqual(bsp_import.targetless_teleports(self.z), 1)


if __name__ == "__main__":
    unittest.main()
