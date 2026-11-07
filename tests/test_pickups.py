"""movers.pickups' tests: a source's weapon_*, item_* and ammo_* entities as the dictionaries
dot-weapon's DotWeaponSpawner.add_entities takes. Run: python3 -I tests/test_pickups.py"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                  # noqa: E402
from dotbsp import movers, reader, units      # noqa: E402


def load(*extra):
    ents = [{"classname": "worldspawn"}, {"classname": "info_player_start", "origin": "0 0 0"}] + list(extra)
    return reader.Bsp("synth.bsp", data=synth.build(entities=ents)).load()


class Pickups(unittest.TestCase):
    def test_weapon_ammo_item_become_spawner_entities(self):
        bsp = load({"classname": "weapon_ak47", "origin": "100 200 30", "angles": "0 90 0", "targetname": "gun1"},
                   {"classname": "ammo_9mm", "origin": "0 0 0"},
                   {"classname": "item_healthkit", "origin": "16 0 0"})
        out = movers.pickups(bsp)
        self.assertEqual([p["classname"] for p in out], ["weapon_ak47", "ammo_9mm", "item_healthkit"])
        w = out[0]
        s = units.VISUAL
        # map (x, y, z) -> Godot (x, z, -y), scaled; map yaw 90 -> Godot yaw 0
        self.assertEqual(w["origin"], [round(100 * s, 4), round(30 * s, 4), round(-200 * s, 4)])
        self.assertEqual(w["angle"], 0.0)
        self.assertEqual(w["props"], {"targetname": "gun1"})
        self.assertEqual(out[1]["props"], {})

    def test_dropped_and_other_classes_are_skipped(self):
        bsp = load({"classname": "item_defuser", "origin": "0 0 0"},      # dropped: a CS bomb kit
                   {"classname": "prop_physics", "origin": "0 0 0"},
                   {"classname": "weapon_awp", "origin": "0 0 0"})
        self.assertEqual([p["classname"] for p in movers.pickups(bsp)], ["weapon_awp"])

    def test_y0_lowers_the_height(self):
        bsp = load({"classname": "weapon_m4a1", "origin": "0 0 100"})
        self.assertAlmostEqual(movers.pickups(bsp, y0=1.0)[0]["origin"][1], round(100 * units.VISUAL - 1.0, 4), places=3)


if __name__ == "__main__":
    unittest.main()
