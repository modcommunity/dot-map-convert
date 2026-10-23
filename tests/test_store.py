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

    def test_set_credit_overwrites_and_recomputes_missing(self):
        with tempfile.TemporaryDirectory() as root:
            h, _ = store.put(root, "t", "fix", fixture(), {"author": "A"})
            c0 = json.load(open(os.path.join(root, h, "credit.json")))
            self.assertEqual(c0["missing"], ["page"])
            self.assertEqual(store.set_credit(root, "t/fix", {"author": "B", "page": "p", "removal": "r"}), h)
            c = json.load(open(os.path.join(root, h, "credit.json")))
            self.assertEqual((c["author"], c["page"], c["removal"], c["missing"]), ("B", "p", "r", []))
            with self.assertRaises(ValueError):
                store.set_credit(root, "t/none", {"author": "x"})

    def test_spawns_are_listed_with_a_place_and_a_team(self):
        bsp = reader.Bsp("t", data=synth.build(entities=[
            {"classname": "worldspawn"},
            {"classname": "info_player_terrorist", "origin": "100 200 300", "angles": "0 90 0"},
            {"classname": "info_player_custom", "origin": "0 0 0"},
            {"classname": "info_target", "origin": "1 1 1"}])).load()
        sp = movers.spawns(bsp)
        self.assertEqual([(s["classname"], s["team"]) for s in sp],
                         [("info_player_terrorist", "red"), ("info_player_custom", "any")])
        self.assertEqual(len(sp[0]["at"]), 3)

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


    def test_a_link_target_may_be_a_wildcard_or_a_class(self):
        from dotbsp import movers
        named = {"snow_p1": [3], "snow_p2": [4], "door": [5]}
        self.assertEqual(movers._resolve("snow_p*", named, {}), [3, 4])
        self.assertEqual(movers._resolve("door", named, {}), [5])
        self.assertEqual(movers._resolve("weapon_x", named, {"weapon_x": [7]}), [7])
        self.assertEqual(movers._resolve("nothing", named, {}), [])


class Audit(unittest.TestCase):
    def test_audit_lists_missing_fields_and_flags_restrictions(self):
        with tempfile.TemporaryDirectory() as root:
            for i, c in enumerate([{"author": "a", "page": "p", "licence": "CC BY-NC-ND", "no_share_check": "ok"}, {}]):
                os.makedirs(os.path.join(root, "h%d" % i))
                json.dump(c, open(os.path.join(root, "h%d" % i, "credit.json"), "w"))
            json.dump({"g/a": "h0", "g/b": "h1"}, open(os.path.join(root, "index.json"), "w"))
            rows = {k: (p, f) for k, p, f in store.audit(root)}
            self.assertEqual(rows["g/a"], ([], ["NC", "ND"]))
            self.assertEqual(rows["g/b"][0], ["author", "page", "licence", "no_share_check"])

    def test_share_status_and_exit(self):
        self.assertEqual(store.share_status("2026-10-23, forbidden: page says no"), "forbidden")
        self.assertEqual(store.share_status("2026-10-23, ask: NC-ND"), "ask")
        self.assertEqual(store.share_status("2026-10-19, none"), "none")
        self.assertEqual(store.share_status(""), "unchecked")
        with tempfile.TemporaryDirectory() as root:
            json.dump({"g/a": "h0"}, open(os.path.join(root, "index.json"), "w"))
            os.makedirs(os.path.join(root, "h0"))
            c = {"author": "a", "page": "p", "licence": "x", "no_share_check": "2026-10-23, forbidden: no"}
            json.dump(c, open(os.path.join(root, "h0", "credit.json"), "w"))
            self.assertIn("forbidden", store.audit(root)[0][2])
            args = type("A", (), {"root": root, "audit": True, "scripts": False})()
            self.assertEqual(store.cmd(args), 1)
            c["no_share_check"] = "2026-10-23, ask: NC-ND"
            json.dump(c, open(os.path.join(root, "h0", "credit.json"), "w"))
            self.assertEqual(store.cmd(args), 0)


if __name__ == "__main__":
    unittest.main()
