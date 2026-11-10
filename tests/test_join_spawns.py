"""join_spawns: a start on floor cut off from the others is moved onto the component holding most of them."""
import copy
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DOTBSP_PATH", ROOT)

from dotbsp import docboxes  # noqa: E402


def deck_and_pit():
    """A 10 m deck with its top at 3 m and, 20 m off, a 2 m pad at 0 m no step joins to it."""
    return {"boxes": [{"at": [0, 2.85, 0], "size": [10, 0.3, 10]},
                      {"at": [20, -0.15, 0], "size": [2, 0.3, 2]}],
            "props": [],
            "spawns": {"seekers": [{"at": [20.0, 0.05, 0.0]}, {"at": [0.0, 3.05, 0.0]}],
                       "hiders": [{"at": [2.0, 3.05, 2.0]}, {"at": [-2.0, 3.05, -2.0]}]}}


class JoinSpawns(unittest.TestCase):
    def test_stranded_seeker_moves_onto_the_deck(self):
        d = deck_and_pit()
        self.assertEqual(docboxes.reach_report(d)[0], 1)
        self.assertEqual(docboxes.join_spawns(d, log=lambda *_: None), 1)
        x, y, z = d["spawns"]["seekers"][0]["at"]
        self.assertAlmostEqual(y, 3.05)
        self.assertTrue(abs(x) <= 4.75 and abs(z) <= 4.75, "inside the deck, about a half metre from its edge (cells at the edge count)")
        for o in d["spawns"]["seekers"][1:] + d["spawns"]["hiders"]:
            self.assertGreaterEqual((x - o["at"][0]) ** 2 + (z - o["at"][2]) ** 2, 1.2 ** 2)
        self.assertEqual(docboxes.reach_report(d), (4, 4, []))

    def test_joined_document_is_not_touched(self):
        d = deck_and_pit()
        d["spawns"]["seekers"][0]["at"] = [1.5, 3.05, -1.5]
        self.assertEqual(docboxes.join_spawns(d, log=lambda *_: None), 0)
        self.assertEqual(d["spawns"]["seekers"][0]["at"], [1.5, 3.05, -1.5])

    def test_start_on_nothing_moves_and_props_are_kept_clear(self):
        d = deck_and_pit()
        d["spawns"]["seekers"][0]["at"] = [60.0, 0.0, 60.0]
        d["props"] = [{"id": "crate", "at": [4.0, 3.0, 4.0], "yaw": 0}]
        self.assertEqual(docboxes.join_spawns(d, log=lambda *_: None), 1)
        x, _, z = d["spawns"]["seekers"][0]["at"]
        self.assertGreaterEqual((x - 4) ** 2 + (z - 4) ** 2, 1.0)

    def test_footprint_keeps_the_start_off_a_bed(self):
        d = deck_and_pit()
        d["spawns"]["hiders"] = [{"at": [-4.0, 3.05, -4.0]}]
        d["spawns"]["seekers"][1]["at"] = [-4.0, 3.05, 4.0]
        d["props"] = [{"id": "bed", "at": [3.5, 3.0, 0.0], "yaw": 30}]
        bare = copy.deepcopy(d)
        docboxes.join_spawns(bare, log=lambda *_: None)
        self.assertLess(abs(bare["spawns"]["seekers"][0]["at"][2]), 1.0, "by origin distance alone it lands beside the bed's middle, inside the bed")
        self.assertEqual(docboxes.join_spawns(d, footprint=lambda pid, yaw: (2.0, 3.0), log=lambda *_: None), 1)
        x, _, z = d["spawns"]["seekers"][0]["at"]
        half_x = (2.0 * math.cos(math.radians(30)) + 3.0 * math.sin(math.radians(30))) / 2 + 0.5
        half_z = (2.0 * math.sin(math.radians(30)) + 3.0 * math.cos(math.radians(30))) / 2 + 0.5
        self.assertTrue(abs(x - 3.5) >= half_x or abs(z) >= half_z, "outside the turned bed and a person's room around it: %s" % [x, z])

    def test_terrain_counts_as_floor(self):
        from dotbsp import terrain
        d = deck_and_pit()
        d["boxes"] = d["boxes"][1:]
        hf = terrain.Heightfield(-10.0, -10.0, 1.0, 21, 21, [3.0] * (21 * 21))
        d["terrain"] = hf.encode()
        self.assertEqual(docboxes.join_spawns(d, log=lambda *_: None), 1)
        self.assertEqual(docboxes.reach_report(d)[2], [])


if __name__ == "__main__":
    unittest.main()
