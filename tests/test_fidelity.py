"""The gameplay-fidelity audit and the converter fixes it drove. Run: python3 -P tests/test_fidelity.py"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                          # noqa: E402
from dotbsp import fidelity, movers, reader           # noqa: E402


class Pairs:
    """An entity for synth.build that keeps repeated keys and their case."""

    def __init__(self, *pairs):
        self._p = list(pairs)

    def items(self):
        return list(self._p)


WORLD = Pairs(("classname", "worldspawn"))


def teleport_map(target, dest_class="info_teleport_destination", dest_name="Orange", extra=(), keys=None):
    ents = [WORLD, Pairs(("classname", dest_class), ("targetname", dest_name), ("origin", "100 200 300"),
                         ("angles", "0 90 0"))] + list(extra)
    k = {"target": target, "spawnflags": "1"}
    k.update(keys or {})
    data = synth.build(entities=ents, entity_box=(0, 0, 0, 32, 32, 32), entity_origin=(500, 0, 0),
                       entity_class="trigger_teleport", entity_keys=k)
    return reader.Bsp("t", data=data).load()


class EngineReading(unittest.TestCase):
    def test_keys_are_case_insensitive_and_the_last_value_wins(self):
        e = reader.parse_entities('{ "classname" "trigger_hurt" "Damage" "5" "damage" "20" "StartDisabled" "1" }')[0]
        self.assertEqual(e["damage"], "20")
        self.assertEqual(e.get("DAMAGE"), "20")
        self.assertEqual(e.get("startdisabled"), "1")
        self.assertIn("startDisabled", e)
        self.assertEqual(list(e), ["classname", "Damage", "StartDisabled"])     # the first spelling stays

    def test_a_brace_inside_a_quoted_value_does_not_split_the_entity(self):
        ents = reader.parse_entities('{ "classname" "game_text" "message" "{hi}" "targetname" "t" }\n{ "classname" "info_target" }')
        self.assertEqual([e["classname"] for e in ents], ["game_text", "info_target"])
        self.assertEqual(ents[0]["targetname"], "t")

    def test_an_escape_separated_output_keeps_commas_in_its_parameter(self):
        e = reader.parse_entities('{ "classname" "trigger_once" "OnStartTouch" "s\x1bRunScriptCode\x1bf(a,b)\x1b0\x1b-1" }')[0]
        (o,) = movers.outputs(e)
        self.assertEqual((o["target"], o["input"], o["param"]), ("s", "RunScriptCode", "f(a,b)"))

    def test_an_output_key_in_another_case_is_one_output_list(self):
        e = reader.parse_entities('{ "classname" "logic_relay" "OnTrigger" "a,Open,,0,-1" "ontrigger" "b,Open,,0,-1" }')[0]
        self.assertEqual([o["target"] for o in movers.outputs(e)], ["a", "b"])


class Teleports(unittest.TestCase):
    def test_a_target_in_another_case_finds_its_destination(self):
        bsp = teleport_map("orange")
        (v,) = [v for v in movers.volumes(bsp) if v["kind"] == "teleport"]
        self.assertEqual(v["target"], "Orange")
        self.assertIn("Orange", movers.destinations(bsp))
        self.assertEqual(fidelity.findings(bsp)["counts"].get("teleport_dest_lost", 0), 0)

    def test_any_named_entity_a_teleport_names_is_a_destination(self):
        bsp = teleport_map("redspawn", dest_class="info_player_teamspawn", dest_name="redspawn")
        d = movers.destinations(bsp)["redspawn"]
        self.assertEqual(d["at"], [round(100 * 0.01905, 4), round(300 * 0.01905, 4), round(-200 * 0.01905, 4)])
        self.assertEqual(fidelity.findings(bsp)["counts"].get("teleport_dest_lost", 0), 0)

    def test_an_unnamed_spot_is_not_a_destination(self):
        bsp = teleport_map("nowhere", dest_class="prop_static", dest_name="Orange")
        self.assertNotIn("Orange", movers.destinations(bsp))

    def test_set_remote_destination_names_a_destination(self):
        relay = Pairs(("classname", "logic_relay"), ("OnTrigger", "tp,SetRemoteDestination,spot,0,-1"))
        spot = Pairs(("classname", "info_player_start"), ("targetname", "spot"), ("origin", "0 0 0"))
        bsp = teleport_map("orange", extra=(relay, spot))
        self.assertIn("spot", movers.destinations(bsp))

    def test_landmark_and_its_angles_are_recorded(self):
        lm = Pairs(("classname", "info_landmark"), ("targetname", "LM"), ("origin", "0 0 0"))
        bsp = teleport_map("orange", extra=(lm,), keys={"landmark": "lm", "UseLandmarkAngles": "1"})
        (v,) = [v for v in movers.volumes(bsp) if v["kind"] == "teleport"]
        self.assertEqual((v["landmark"], v["landmark_angles"]), ("LM", True))

    def test_teleports_are_not_retargeted_unless_asked(self):
        bsp = teleport_map("orange")
        self.assertFalse(any(v.get("retargeted_from") for v in movers.volumes(bsp)))


class Filters(unittest.TestCase):
    def test_every_trigger_kind_records_its_filter(self):
        for cls in ("trigger_push", "trigger_hurt", "trigger_gravity", "trigger_teleport", "trigger_multiple"):
            data = synth.build(entities=[WORLD, Pairs(("classname", "filter_activator_name"), ("targetname", "f"))],
                               entity_box=(0, 0, 0, 32, 32, 32), entity_class=cls, entity_keys={"filtername": "f"})
            bsp = reader.Bsp("t", data=data).load()
            (v,) = [v for v in movers.volumes(bsp) if v.get("entity") is not None]
            self.assertEqual(v["filter"], "f", cls)
            self.assertEqual(fidelity.findings(bsp)["counts"].get("filter_dropped", 0), 0, cls)


class Audit(unittest.TestCase):
    def test_a_gameplay_class_nothing_implements_is_listed(self):
        data = synth.build(entities=[WORLD, Pairs(("classname", "logic_frobnicator"), ("targetname", "x")),
                                     Pairs(("classname", "logic_auto"), ("OnMapSpawn", "x,Frob,,0,-1"))])
        rep = fidelity.findings(reader.Bsp("t", data=data).load())
        self.assertNotEqual(rep["classes"]["logic_frobnicator"], "implemented")
        self.assertIn("input_unimplemented", rep["counts"])
        self.assertTrue(fidelity.gameplay_lost(rep))

    def test_hurt_keys_the_runtime_reads_are_not_unread(self):
        k = {"damage": "50", "damagecap": "100", "damagemodel": "1", "nodmgforce": "1", "hurtrate": "0.2"}
        data = synth.build(entities=[WORLD], entity_box=(0, 0, 0, 32, 32, 32), entity_origin=(0, 0, 0),
                           entity_class="trigger_hurt", entity_keys=k)
        rep = fidelity.findings(reader.Bsp("t", data=data).load())
        self.assertEqual([f for f in rep["findings"].get("volume_key_unread", []) if "trigger_hurt" in f], [])
        self.assertIn("damagecap", fidelity.volume_keys_read("trigger_hurt"))
        self.assertNotIn("damagecap", fidelity.volume_keys_read("trigger_push"))

    def test_the_converter_reads_the_lump_as_the_engine_does(self):
        bsp = teleport_map("orange", keys={"Target": "orange"})
        rep = fidelity.findings(bsp)
        self.assertTrue(rep["aligned"])
        self.assertEqual(rep["counts"].get("key_case", 0), 0)


class ShippedReports(unittest.TestCase):
    def test_a_shipped_report_gains_the_gameplay_section_and_check_ratchets_it(self):
        import json
        import tempfile
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
        import coverage_gameplay
        from dotbsp import store
        root = tempfile.mkdtemp()
        data = synth.build(entities=[{"classname": "worldspawn"},
                                     {"classname": "zz_unheard_of", "targetname": "z", "OnTrigger": "z,Kill,,0,-1"}])
        h, _new = store.put(root, "t", "m", data, {"author": "A", "page": "https://example.invalid"})
        rp = os.path.join(tempfile.mkdtemp(), "m.coverage.json")
        with open(rp, "w") as f:
            json.dump({"map": "m", "sha256": h, "lists": {"classes_unmapped": ["zz_unheard_of"]}, "counts": {}}, f)
        self.assertEqual(coverage_gameplay.main(["--store", root, "--check", rp]), 5)      # no section yet
        self.assertEqual(coverage_gameplay.main(["--store", root, rp]), 0)
        rep = json.load(open(rp))
        self.assertIn("class_unknown:zz_unheard_of", rep["lists"]["gameplay_lost"])
        self.assertEqual(rep["counts"]["gameplay_lost"], len(rep["lists"]["gameplay_lost"]))
        self.assertEqual(coverage_gameplay.main(["--store", root, "--check", rp]), 0)
        rep["lists"]["gameplay_lost"] = []
        with open(rp, "w") as f:
            json.dump(rep, f)
        self.assertEqual(coverage_gameplay.main(["--store", root, "--check", rp]), 5)      # a new loss fails
        rep["sha256"] = "0" * 64
        with open(rp, "w") as f:
            json.dump(rep, f)
        self.assertEqual(coverage_gameplay.main(["--store", root, rp]), 2)                 # missing source: loud

    def test_runtime_handled_teleport_constructs_are_not_losses(self):
        self.assertNotIn(fidelity.FINDINGS["teleport_target_dynamic"][0], fidelity.SEVERE)
        self.assertNotIn(fidelity.FINDINGS["teleport_landmark_angles"][0], fidelity.SEVERE)


if __name__ == "__main__":
    unittest.main()
