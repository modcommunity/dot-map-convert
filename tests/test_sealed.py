"""A zombie start behind a door closed at map start is not reachable from the player start.
Run: python3 -I tests/test_sealed.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import flood, movers  # noqa: E402


def floor(x0, z0, x1, z1):
    return {"at": [(x0 + x1) / 2, -0.1, (z0 + z1) / 2], "size": [x1 - x0, 0.2, z1 - z0]}


def door(x, z0, z1):
    return {"at": [x, 1.1, (z0 + z1) / 2], "size": [0.2, 2.2, z1 - z0]}


class Hurt(unittest.TestCase):
    def test_points_inside_a_volume_are_returned(self):
        vol = [[24, 0, -5, 31, 3, 0]]
        inside, outside = (26.0, 0.1, -2.0), (20.0, 0.1, -2.0)
        self.assertEqual(flood.inside_volumes([inside, outside], vol), [inside])

    def test_no_volumes_returns_nothing(self):
        self.assertEqual(flood.inside_volumes([(1.0, 0.0, 1.0)], []), [])

    def test_above_the_volume_is_outside(self):
        self.assertEqual(flood.inside_volumes([(26.0, 5.0, -2.0)], [[24, 0, -5, 31, 3, 0]]), [])


class Sealed(unittest.TestCase):
    def test_closed_door_seals_the_room_behind_it(self):
        boxes = [floor(0, 0, 10, 4), floor(10, 0, 16, 4)]
        shut = [door(10, 0, 4)]
        inside, outside = (13, 0.0, 2), (3, 0.0, 2)
        self.assertEqual(flood.sealed_by(boxes, shut, [(1, 0.0, 2)], [inside, outside]), [inside])

    def test_no_door_seals_nothing(self):
        self.assertEqual(flood.sealed_by([floor(0, 0, 10, 4)], [], [(1, 0.0, 2)], [(3, 0.0, 2)]), [])

    def test_an_island_is_not_blamed_on_a_door(self):
        boxes = [floor(0, 0, 10, 4), floor(30, 0, 36, 4)]
        self.assertEqual(flood.sealed_by(boxes, [door(10, 0, 4)], [(1, 0.0, 2)], [(33, 0.0, 2)]), [])

    def test_a_second_way_round_keeps_the_room_reachable(self):
        boxes = [floor(0, 0, 10, 4), floor(10, 0, 16, 4), floor(0, 4, 16, 8)]
        self.assertEqual(flood.sealed_by(boxes, [door(10, 0, 4)], [(1, 0.0, 2)], [(13, 0.0, 2)]), [])

    def test_which_doors_start_shut(self):
        self.assertTrue(movers.closed_door({"classname": "func_door", "spawnflags": "0"}))
        self.assertTrue(movers.closed_door({"classname": "func_door_rotating"}))
        self.assertFalse(movers.closed_door({"classname": "func_door", "spawnflags": "1"}))
        self.assertFalse(movers.closed_door({"classname": "func_door", "spawnflags": "8"}))
        self.assertFalse(movers.closed_door({"classname": "func_wall"}))


if __name__ == "__main__":
    unittest.main()
