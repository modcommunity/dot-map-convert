"""The look-at-me house converter on a two-room map written in the test.
Run: python3 -P tests/test_bsp_house.py
"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("bsp_house", os.path.join(HERE, "..", "adapters", "mg-look-at-me", "bsp_house.py"))
bsp_house = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bsp_house)


def doc(door=40):
    """Two 10 m rooms side by side under one roof, a wall between them with a doorway `door` units wide."""
    boxes = [(0, 0, -16, 800, 400, 0),       # floor
             (0, 0, 128, 800, 400, 144),     # roof
             (-16, 0, 0, 0, 400, 128), (800, 0, 0, 816, 400, 128),
             (0, -16, 0, 800, 0, 128), (0, 400, 0, 800, 416, 128),
             (392, 0, 0, 408, 200 - door / 2, 128), (392, 200 + door / 2, 0, 408, 400, 128)]
    return {"entities": [{"index": 0, "classname": "worldspawn"},
                         {"index": 1, "classname": "info_player_start", "origin": [100, 200, 1]},
                         {"index": 2, "classname": "prop_physics", "origin": [600, 200, 1], "keys": {"model": "models/props/bed01.mdl"}}],
            "models": [{"index": 0, "entity": 0}],
            "brushes": [{"model": 0, "player_solid": True, "mins": list(b[:3]), "maxs": list(b[3:])} for b in boxes],
            "static_props": []}


SPEC = {"name": "Test", "title": "Test", "scale": 0.0254, "grow": 1.0, "storeys": [{"floor": 0, "z": [-40, 60]}],
        "start_name": "Hall", "erode": 0.5, "min_area": 3.0, "fill": 0.4, "min_cells": 2}


class TestBspHouse(unittest.TestCase):
    def test_wall_classes_lets_a_func_brush_pane_stay_open(self):
        d = doc()
        d["entities"].append({"index": 3, "classname": "func_brush"})
        d["models"].append({"index": 5, "entity": 3})
        d["brushes"].append({"model": 5, "player_solid": True, "mins": [392, 190, 0], "maxs": [408, 210, 128]})
        shut = bsp_house.Raster(d, SPEC).walls
        open_ = bsp_house.Raster(d, dict(SPEC, wall_classes=["func_wall"])).walls
        self.assertEqual(len(shut) - len(open_), 1)

    def test_two_rooms_through_the_doorway(self):
        rooms, lost = bsp_house.convert(doc(), SPEC)
        self.assertEqual([r["name"] for r in rooms][:1], ["Hall"])
        self.assertEqual(len(rooms), 2, rooms)
        self.assertEqual(rooms[1].get("from"), "Hall")
        self.assertLess(rooms[0]["x"] + rooms[0]["w"], rooms[1]["x"] + 1)  # the start room is the west one

    def test_same_input_same_layout(self):
        self.assertEqual(bsp_house.convert(doc(), SPEC), bsp_house.convert(doc(), SPEC))

    def test_growth_doubles_the_plan(self):
        one, _ = bsp_house.convert(doc(), SPEC)
        two, _ = bsp_house.convert(doc(), dict(SPEC, grow=2.0))
        area = lambda rooms: sum(r["w"] * r["d"] for r in rooms)
        self.assertGreater(area(two), 3 * area(one))

    def test_mesh_mode_keeps_the_doorway(self):
        # The door is the source's own doorway (x 400, y 200, 40 units), where the pack's origin puts it.
        spec = dict(SPEC, mode="mesh", cell=2.0, pack="test", pack_metres_per_unit=0.01905)
        rooms, lost, world = bsp_house.convert_mesh(doc(), spec)
        self.assertEqual([r["name"] for r in rooms], ["Hall", "Ward"])
        door = rooms[1]["door"]
        self.assertEqual(door["side"], "e")
        self.assertAlmostEqual(door["w"], 40 * 0.0254, delta=0.3)
        self.assertAlmostEqual(door["c"][0], 400 * 0.0254 + world["origin"][0], delta=0.5)
        self.assertAlmostEqual(door["c"][1], world["origin"][2] - 200 * 0.0254, delta=0.5)
        self.assertAlmostEqual(world["scale"], 0.0254 / 0.01905, places=4)
        self.assertEqual(bsp_house.convert_mesh(doc(), spec), (rooms, lost, world))

if __name__ == "__main__":
    unittest.main()
