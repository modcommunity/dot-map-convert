"""A thin trigger is thickened the way Source's hull touches it: sideways by the hull,
and a pit only ever downward from the sheet the mapper drew.

Run: python3 -P tests/test_zone_inflation.py

bhop_arcane_v2 (the 2026-11-17 footage) had both faults at once: its stage-4/5
Restart doors, trigger_teleports 8 units thick, were grown to 192 and sent a player
strafing 90 units past the frame back to spawn; and the 1-unit pit strips in the gaps
between its stage-4 red blocks were grown centred, 96 units above the sheet and 64 over
the block tops, so every hop across a gap was respawned to the stage start.
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "adapters", "game-airdrift"))
sys.path.insert(0, ROOT)

os.environ.setdefault("DOTBSP_PATH", ROOT)
for READER in (os.environ.get("AIRDRIFT_TOOLS", "") or os.environ.get("G2G_TOOLS", ""),
               os.path.join(os.path.dirname(ROOT), "game-airdrift", "tools"),
               "/home/gamedev/godot/game-airdrift/tools"):
    if READER and os.path.isfile(os.path.join(READER, "bsp_read.py")):
        sys.path.append(READER)
        break
try:
    import bsp_import as bi  # noqa: E402
except ModuleNotFoundError as err:
    raise unittest.SkipTest("bsp_read not found (set AIRDRIFT_TOOLS): %s" % err)

MIN = bi.MIN_ZONE_THICKNESS
HULL = 2.0 * bi.PLAYER_HALF_WIDTH
TICK = 3500.0 / 128.0


def zoner(solids=()):
    return bi.Zoner(types.SimpleNamespace(entities=[]), MIN, list(solids))


def contains(outer, inner):
    return all(outer[0][i] <= inner[0][i] and inner[1][i] <= outer[1][i] for i in range(3))


class Door(unittest.TestCase):
    """bhop_arcane_v2 trigger_teleport 423: a Restart door, 8 x 64 x 96, aimed at spawn."""
    DOOR = ([1544.0, -32.0, 3712.0], [1552.0, 32.0, 3808.0])

    def test_thin_side_grows_by_the_hull_not_to_the_minimum(self):
        zone = zoner().add("RESPAWN", 0, box=self.DOOR)
        self.assertAlmostEqual(zone["max"][0] - zone["min"][0], 8.0 + HULL)
        self.assertAlmostEqual(zone["max"][1] - zone["min"][1], 64.0 + HULL)
        # Within the hull of the frame, and no further: Source's touch test.
        self.assertAlmostEqual(zone["min"][0], 1544.0 - bi.PLAYER_HALF_WIDTH)
        self.assertAlmostEqual(zone["max"][0], 1552.0 + bi.PLAYER_HALF_WIDTH)

    def test_still_thicker_than_a_tick_at_ceiling_speed(self):
        zone = zoner().add("RESPAWN", 0, box=self.DOOR)
        for axis in range(3):
            self.assertGreater(zone["max"][axis] - zone["min"][axis], TICK)

    def test_never_above_the_drawn_top(self):
        zone = zoner().add("RESPAWN", 0, box=self.DOOR)
        self.assertEqual(zone["max"][2], 3808.0)
        self.assertTrue(contains((zone["min"], zone["max"]), self.DOOR))


class GapStrip(unittest.TestCase):
    """The stage-4 red blocks: a 1-unit pit strip in the gap between two blocks."""
    STRIP = ([0.0, 0.0, -5089.0], [64.0, 128.0, -5088.0])
    # Blocks either side of the gap, tops 32 over the sheet; nothing inside the gap.
    BLOCKS = [([-128.0, 0.0, -5120.0], [0.0, 128.0, -5056.0]),
              ([64.0, 0.0, -5120.0], [192.0, 128.0, -5056.0])]

    def test_pit_never_reaches_above_the_sheet(self):
        zone = zoner(self.BLOCKS).add("RESPAWN", 0, box=self.STRIP)
        self.assertEqual(zone["max"][2], -5088.0)
        self.assertAlmostEqual(zone["max"][2] - zone["min"][2], MIN)
        self.assertTrue(zone.get("hung"))

    def test_a_hop_over_the_gap_is_not_in_the_pit(self):
        zone = zoner(self.BLOCKS).add("RESPAWN", 0, box=self.STRIP)
        # Feet leaving a block top and crossing the gap are always over -5056.
        for x in range(0, 65, 8):
            feet = (float(x), 64.0, -5056.0 + 1.0)
            inside = all(zone["min"][i] <= feet[i] < zone["max"][i] for i in range(3))
            self.assertFalse(inside, feet)

    def test_a_player_falling_into_the_gap_is(self):
        zone = zoner(self.BLOCKS).add("RESPAWN", 0, box=self.STRIP)
        feet = (32.0, 64.0, -5100.0)
        self.assertTrue(all(zone["min"][i] <= feet[i] < zone["max"][i] for i in range(3)))


class Functions(unittest.TestCase):
    def test_hull_span(self):
        self.assertEqual(bi.hull_span(8.0, MIN), 8.0 + HULL)
        self.assertEqual(bi.hull_span(180.0, MIN), MIN)

    def test_wide_sides_untouched(self):
        lo, hi, grown = bi.inflate([0, 0, 0], [512, 512, 1], MIN)
        self.assertEqual((lo[0], hi[0], lo[1], hi[1]), (0, 512, 0, 512))
        self.assertTrue(grown)

    def test_non_pit_vertical_stays_centred(self):
        # A start or finish volume drawn as a sheet is still grown about its centre.
        lo, hi, _ = bi.inflate([0, 0, 0], [512, 512, 16], MIN)
        self.assertAlmostEqual(lo[2], 8.0 - MIN / 2)
        self.assertAlmostEqual(hi[2], 8.0 + MIN / 2)

    def test_pit_under_open_air_hangs_too(self):
        lo, hi, grown, how = bi.inflate_pit([0, 0, 0], [512, 512, 16], MIN, [])
        self.assertEqual((hi[2], lo[2], how), (16, 16 - MIN, "hung"))

    def test_thick_pit_untouched(self):
        lo, hi, grown, how = bi.inflate_pit([0, 0, 0], [512, 512, 400], MIN, [])
        self.assertEqual((lo, hi, grown, how), ([0, 0, 0], [512, 512, 400], False, ""))

    def test_inflated_always_contains_the_original(self):
        for box in (([0, 0, 0], [8, 8, 8]), ([0, 0, 0], [1000, 4, 2]),
                    ([-5, -5, -5], [5, 300, 190])):
            lo, hi, _ = bi.inflate(*box, MIN)
            self.assertTrue(contains((lo, hi), box))
            lo, hi, _, _ = bi.inflate_pit(*box, MIN, [])
            self.assertTrue(contains((lo, hi), box))
            self.assertEqual(hi[2], box[1][2])


if __name__ == "__main__":
    unittest.main()
