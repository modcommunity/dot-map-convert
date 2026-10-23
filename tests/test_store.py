"""The lossless store and the two parser losses it fixes. Run: python3 -I tools/bsp/tests/test_store.py"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                          # noqa: E402
from dotbsp import movers, reader, store              # noqa: E402


class Pairs:
    """An entity for synth.build that keeps repeated keys (a dict cannot)."""

    def __init__(self, *pairs):
        self._p = list(pairs)

    def items(self):
        return list(self._p)


def fixture():
    return synth.build(entities=[
        Pairs(("classname", "worldspawn"), ("skyname", "sky_test")),
        Pairs(("classname", "trigger_multiple"), ("targetname", "t1"), ("spawnflags", "1"),
              ("OnTrigger", "door,Open,,0,-1"), ("OnTrigger", "door,Close,,2.5,1"),
              ("filtername", "a"), ("filtername", "b")),
        Pairs(("classname", "math_counter"), ("targetname", "cnt"), ("max", "3"),
              ("OutValue", "door,SetValue,,0,-1"), ("OutValue", "relay,Trigger,,1,-1"),
              ("message", "a,b,c"), ("note", "x,y,z,notanumber,2")),
        Pairs(("classname", "point_servercommand"), ("targetname", "cmd")),
        Pairs(("classname", "logic_auto"), ("OnMapSpawn", "cmd,Command,sv_airaccelerate 150,0,-1")),
        Pairs(("classname", "game_ui"), ("PressedAttack", "door,Open,,0,-1"), ("PlayerOn", "relay,Enable\x1b\x1b0\x1b-1")),
    ])


class RepeatedKeys(unittest.TestCase):
    def setUp(self):
        self.bsp = reader.Bsp("t", data=fixture()).load()

    def test_pairs_keep_every_repeat_in_order(self):
        trig = self.bsp.entities[1]
        self.assertEqual([k for k, _ in trig.pairs],
                         ["classname", "targetname", "spawnflags", "OnTrigger", "OnTrigger", "filtername", "filtername"])
        self.assertEqual([v for k, v in trig.pairs if k == "filtername"], ["a", "b"])

    def test_dict_view_unchanged(self):
        trig = self.bsp.entities[1]
        self.assertEqual(trig["filtername"], "a")
        self.assertEqual(trig["OnTrigger"], "door,Open,,0,-1\ndoor,Close,,2.5,1")

    def test_on_outputs_come_first_and_unchanged(self):
        outs = movers.outputs(self.bsp.entities[1])
        self.assertEqual([(o["output"], o["input"], o["delay"], o["times"]) for o in outs],
                         [("OnTrigger", "Open", 0.0, -1), ("OnTrigger", "Close", 2.5, 1)])


class NonOnOutputs(unittest.TestCase):
    def setUp(self):
        self.bsp = reader.Bsp("t", data=fixture()).load()

    def test_counter_repeats_and_shape(self):
        outs = movers.outputs(self.bsp.entities[2])
        self.assertEqual([(o["output"], o["target"], o["input"]) for o in outs],
                         [("OutValue", "door", "SetValue"), ("OutValue", "relay", "Trigger")])

    def test_plain_comma_values_are_not_outputs(self):
        keys = [o["output"] for o in movers.outputs(self.bsp.entities[2])]
        self.assertNotIn("message", keys)
        self.assertNotIn("note", keys)

    def test_escape_separator_and_input_capture(self):
        outs = movers.outputs(self.bsp.entities[5])
        self.assertEqual([(o["output"], o["target"], o["input"]) for o in outs],
                         [("PressedAttack", "door", "Open"), ("PlayerOn", "relay", "Enable")])

    def test_links_include_them(self):
        self.assertEqual(len(movers.links(self.bsp)), 2 + 2 + 2 + 1)


class RoundTrip(unittest.TestCase):
    def test_store_reload_identical_document(self):
        data = fixture()
        with tempfile.TemporaryDirectory() as root:
            h, new = store.put(root, "t", "fix", data, {"author": "A", "page": "http://x"})
            self.assertTrue(new)
            d = os.path.join(root, h)
            self.assertEqual(open(os.path.join(d, "source.bsp"), "rb").read(), data)
            stored = json.load(open(os.path.join(d, "doc.json")))
            again = store.document(open(os.path.join(d, "source.bsp"), "rb").read())
            self.assertEqual(stored, again)
            self.assertEqual(json.load(open(os.path.join(root, "index.json"))), {"t/fix": h})
            self.assertEqual(json.load(open(os.path.join(d, "credit.json")))["missing"], [])
            self.assertEqual(store.check(root), [])

    def test_document_keeps_repeats_and_rebuilds_the_lump(self):
        doc = store.document(fixture())
        trig = doc["entities"][1]
        self.assertEqual(sum(1 for k, _ in trig["pairs"] if k == "filtername"), 2)
        self.assertEqual(len(doc["entities"][2]["outputs"]), 2)
        again = reader.parse_entities(store.entity_text(doc))
        self.assertEqual([[list(p) for p in e.pairs] for e in again], [e["pairs"] for e in doc["entities"]])

    def test_commands_are_recorded_not_run(self):
        cmds = store.document(fixture())["commands"]
        self.assertEqual([(c["classname"], c["command"]) for c in cmds],
                         [("point_servercommand", "sv_airaccelerate 150")])

    def test_second_put_is_not_new_and_keeps_credit(self):
        data = fixture()
        with tempfile.TemporaryDirectory() as root:
            h, _ = store.put(root, "t", "fix", data, {"author": "A"})
            _, new = store.put(root, "t", "fix", data, {"author": "B", "page": "p"})
            self.assertFalse(new)
            c = json.load(open(os.path.join(root, h, "credit.json")))
            self.assertEqual((c["author"], c["page"]), ("A", "p"))

    def test_check_finds_a_changed_source(self):
        with tempfile.TemporaryDirectory() as root:
            h, _ = store.put(root, "t", "fix", fixture())
            with open(os.path.join(root, h, "source.bsp"), "ab") as f:
                f.write(b"x")
            self.assertEqual(len(store.check(root)), 1)

    def test_cut_off_file_is_refused_not_stored(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                store.put(root, "t", "cut", fixture()[:200])
            self.assertEqual(os.listdir(root), [])


if __name__ == "__main__":
    unittest.main()
