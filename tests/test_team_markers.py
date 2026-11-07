"""Team spawns, control points, resupply and flag spawns in the g2gfast importer.
Run: python3 -I tests/test_team_markers.py   (needs numpy, like the importer)
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "adapters", "game-g2gfast"))
sys.path.insert(0, ROOT)

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
    raise unittest.SkipTest("bsp_read or numpy not found (set G2G_TOOLS): %s" % err)


def spawn(team, origin="0 0 0"):
    return {"classname": "info_player_teamspawn", "origin": origin, "angles": "0 90 0", "TeamNum": team}


class TeamMarkers(unittest.TestCase):
    def test_team_numbers_become_red_and_blue_and_the_rest_stay_untagged(self):
        z = types.SimpleNamespace(entities=[spawn("2"), spawn("3"), spawn("0"),
                                            {"classname": "info_player_deathmatch", "origin": "5 5 5"}])
        sides = [bsp_import.SPAWN_TEAMS.get((e["classname"], str(e.get("TeamNum", "")))) for e in z.entities]
        self.assertEqual(sides, ["red", "blue", None, None])

    def test_control_points_and_flag_spawns(self):
        bsp = types.SimpleNamespace(entities=[
            {"classname": "team_control_point", "origin": "10 20 30", "point_index": "2",
             "point_printname": "B", "point_default_owner": "3"},
            {"classname": "team_control_point", "origin": "0 0 0", "point_index": "1",
             "point_printname": "A", "point_default_owner": "2"}])
        doc = {"flag_spawns": [{"team": "red", "origin_src": [100, 200, 30], "yaw_src": 90}]}
        points, resupply, flags = bsp_import.objective_markers(bsp, doc)
        self.assertEqual([(p["index"], p["owner"]) for p in points], [(1, "red"), (2, "blue")])
        self.assertEqual(resupply, [])
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["team"], "red")
        self.assertEqual(flags[0]["origin"], list(bsp_import.to_godot([100.0, 200.0, 30.0])))


if __name__ == "__main__":
    unittest.main()
