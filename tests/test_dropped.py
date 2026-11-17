"""The reviewed drop table (rules/models/dropped.tsv) and the final-pass props kept out of DETAIL.
Run: python3 -P tests/test_dropped.py
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import standins  # noqa: E402


class Dropped(unittest.TestCase):
    def test_dropped_models_are_left_out(self):
        for m in ("models/characters/hostage_02.mdl", "models/humans/group01/female_01.mdl", "models/zombie/fast.mdl",
                  "models/headcrabclassic.mdl", "models/player/items/demo/demo_halloween.mdl", "models/effects/combineball.mdl",
                  "models/effects/vol_light.mdl", "models/laboratory/wormhole.mdl", "models/extras/info_speech.mdl",
                  "models/props_combine/combine_citadel001.mdl", "models/props_buildings/row_res_1.mdl"):
            self.assertIsNotNone(standins.dropped(m), m)
            self.assertTrue(standins.is_detail(m), m)

    def test_final_pass_props_are_kept(self):
        for m in ("models/cranes/crane_frame.mdl", "models/cranes/crane_body_lod.mdl", "models/props/de_nuke/powerwires.mdl",
                  "models/props/de_prodigy/prodcables128.mdl", "models/props/cs_assault/wirepipe.mdl",
                  "models/props/de_inferno/ceiling_fan.mdl", "models/props/de_inferno/ceiling_fan_blade.mdl",
                  "models/props/de_prodigy/fanoff.mdl", "models/props_c17/pulleywheels_small01.mdl",
                  "models/combine_turrets/floor_turret.mdl", "models/props_lab/tpplugholder_single.mdl",
                  "models/props_buildings/collapsedbuilding01awall.mdl", "models/props/cs_assault/billboard.mdl",
                  "models/props_idbs/go/kitchen_vent1.mdl"):
            self.assertIsNone(standins.dropped(m), m)
            self.assertFalse(standins.is_detail(m), m)

    def test_no_omit_keeps_everything(self):
        standins.set_no_omit(True)
        try:
            self.assertIsNone(standins.dropped("models/zombie/fast.mdl"))
            self.assertFalse(standins.is_detail("models/zombie/fast.mdl"))
        finally:
            standins.set_no_omit(False)

    def test_bad_row_fails_loudly(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "dropped.tsv")
            with open(p, "w", encoding="utf-8") as f:
                f.write("zombie/fast\tnpc\n")
            with self.assertRaises(ValueError):
                standins.dropped_rows(p)


if __name__ == "__main__":
    unittest.main()
