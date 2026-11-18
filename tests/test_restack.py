"""dotbsp.restack: a floating prop is lowered onto the support below, within the allowed drop.
Run: python3 -P tests/test_restack.py
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import restack  # noqa: E402

FOOT = lambda q: (0.5, 0.5)  # noqa: E731
H = {"table": 0.6, "cup": 0.1}
REST = lambda under, dx, dz, q: H[under["id"]]  # noqa: E731


def doc(*props):
    return {"boxes": [{"at": [0, -0.05, 0], "size": [20, 0.1, 20], "solid": True}],
            "props": [{"id": i, "at": list(a)} for i, a in props]}


class Restack(unittest.TestCase):
    def test_lowers_onto_floor(self):
        d = doc(("cup", (0, 0.5, 0)))
        low, lost = restack.restack(d, FOOT, REST)
        self.assertEqual((len(low), lost), (1, []))
        self.assertAlmostEqual(d["props"][0]["at"][1], 0.0)

    def test_stack_follows_its_support(self):
        d = doc(("table", (0, 0.4, 0)), ("cup", (0, 1.0, 0)))
        restack.restack(d, FOOT, REST)
        self.assertAlmostEqual(d["props"][0]["at"][1], 0.0)
        self.assertAlmostEqual(d["props"][1]["at"][1], 0.6)

    def test_standing_prop_stays(self):
        d = doc(("cup", (0, 0.03, 0)))
        low, lost = restack.restack(d, FOOT, REST)
        self.assertEqual((low, lost), ([], []))

    def test_max_drop_and_strict(self):
        d = doc(("cup", (0, 0.5, 0)))
        low, lost = restack.restack(d, FOOT, REST, max_drop=0.3)
        self.assertEqual((low, len(lost)), ([], 1))
        self.assertEqual(d["props"][0]["at"][1], 0.5)
        with self.assertRaises(restack.RestackError):
            restack.restack(d, FOOT, REST, max_drop=0.3, strict=True)

    def test_no_support_is_lost(self):
        d = doc(("cup", (50, 0.5, 50)))
        low, lost = restack.restack(d, FOOT, REST)
        self.assertEqual((low, len(lost)), ([], 1))

    def test_skip(self):
        d = doc(("cup", (0, 0.5, 0)))
        low, lost = restack.restack(d, FOOT, REST, skip=lambda q: True)
        self.assertEqual((low, lost), ([], []))


if __name__ == "__main__":
    unittest.main()
