"""The pass ledger: what each box pass removes, by pass. Run: python3 -P tests/test_passledger.py"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import docboxes, passledger  # noqa: E402


def box(x, size, mat="wall", **kw):
    b = {"at": [x, size[1] / 2, 0.0], "size": list(size), "mat": mat}
    b.update(kw)
    return b


class Ledger(unittest.TestCase):
    def setUp(self):
        passledger.reset()

    def row(self, name):
        return passledger.LEDGER.passes[name]

    def test_a_pass_is_counted_by_boxes_and_volume(self):
        boxes = [box(0, (4, 3, 0.2)), box(9, (0.1, 0.1, 0.1)), box(11, (0.1, 0.1, 0.12), mat="trim")]
        self.assertEqual(docboxes.drop_small(boxes, 0.5), 2)
        r = self.row("drop_small")
        self.assertEqual((r["removed"], r["added"]), (2, 0))
        self.assertAlmostEqual(r["removed_m3"], 0.001 + 0.0012)
        self.assertEqual([b["mat"] for b in r["boxes"]], ["wall", "trim"])
        self.assertEqual(len(boxes), 1)

    def test_a_pass_that_removes_nothing_leaves_no_row(self):
        docboxes.drop_small([box(0, (4, 3, 0.2))], 0.5)
        self.assertNotIn("drop_small", passledger.LEDGER.passes)

    def test_trim_and_cap_are_named_for_the_pass(self):
        boxes = [box(0, (4, 3, 0.2)), box(5, (0.1, 0.1, 0.1))]
        docboxes.drop_trim(boxes, min_volume=0.01)
        self.assertEqual(self.row("drop_trim")["removed"], 1)
        far = [box(0, (2, 2, 2)), box(500, (2, 2, 2))]
        docboxes.prune_far_scenery(far, [(0.0, 0.0, 0.0)], log=None)
        self.assertEqual(self.row("prune_far_scenery")["removed"], 1)
        self.assertEqual(self.row("prune_far_scenery")["boxes"][0]["at"][0], 500)

    def test_merging_is_net_zero_volume(self):
        boxes = [box(0, (1, 1, 1)), box(1, (1, 1, 1))]
        docboxes.merge_touching(boxes)
        r = self.row("merge_touching")
        self.assertEqual((r["removed"], r["added"]), (2, 1))
        self.assertAlmostEqual(r["removed_m3"] - r["added_m3"], 0.0)

    def test_rebase_moves_what_was_kept_before_the_shift(self):
        docboxes.drop_small([box(10, (0.1, 0.1, 0.1))], 0.5)
        passledger.rebase(-4.0, 0.0, 2.0)
        b = self.row("drop_small")["boxes"][0]
        self.assertEqual((b["at"][0], b["at"][2]), (6.0, 2.0))
        self.assertEqual(self.row("drop_small")["largest"][0]["at"][0], 6.0)

    def test_the_table_and_the_sidecar(self):
        docboxes.drop_small([box(0, (0.1, 0.1, 0.1))], 0.5)
        passledger.note("tool_only_brush", 3, "triggers")
        text = "\n".join(passledger.LEDGER.table())
        self.assertIn("drop_small", text)
        self.assertIn("tool_only_brush", text)
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.json")
            os.environ["DOTBSP_PASS_LEDGER"] = "1"
            try:
                passledger.finish(log=lambda s: None, out_path=p)
            finally:
                del os.environ["DOTBSP_PASS_LEDGER"]
            with open(p + ".passes.json") as f:
                side = json.load(f)
        self.assertEqual(side["order"], ["drop_small"])
        self.assertEqual(side["notes"]["tool_only_brush"][0], 3)


class PruneFarScenery(unittest.TestCase):
    START = [(0.0, 0.0, 0.0)]

    def setUp(self):
        passledger.reset()

    def test_a_room_two_metres_from_the_play_space_stays_but_scenery_goes(self):
        play = box(0, (10, 1, 10))                          # -5..5, the start's floor
        room = box(9, (4, 1, 4), mat="parquet")             # 7..11: 2 m beyond the floor's edge, a gap a missing wall left
        far = box(60, (10, 1, 10))                          # 49 m from anything kept
        boxes = [play, room, far]
        self.assertEqual(docboxes.prune_far_scenery(boxes, self.START, reach=3.0, log=None), 1)
        self.assertEqual(boxes, [play, room])
        # the old rule dropped the room, and a second room another 2 m on
        old = [dict(play), dict(room), box(15, (4, 1, 4))]
        self.assertEqual(docboxes.prune_far_scenery(old, self.START, reach=3.0, log=None, join=0), 2)
        chained = [dict(play), dict(room), box(15, (4, 1, 4))]
        self.assertEqual(docboxes.prune_far_scenery(chained, self.START, reach=3.0, log=None), 0)

    def test_a_void_wider_than_a_body_crosses_separates_scenery(self):
        boxes = [box(0, (10, 1, 10)), box(25.5, (10, 1, 10)), box(31.0, (10, 1, 10))]    # 15 m of void, then two overlapping blocks
        self.assertEqual(docboxes.prune_far_scenery(boxes, self.START, reach=3.0, log=None), 2)


if __name__ == "__main__":
    unittest.main()
