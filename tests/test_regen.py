"""Rule tiers, the fallbacks, regen and the coverage ratchet. Run: python3 -I tools/bsp/tests/test_regen.py"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                          # noqa: E402
from dotbsp import coverage, regen, rules, store      # noqa: E402

MAT = ("TOOLS/TOOLSNODRAW", "ZZQ/NEWWALL", "ZZQ/OTHER")
ENTS = [{"classname": "worldspawn", "skyname": "sky_test"},
        {"classname": "info_player_start", "origin": "16 16 1"},
        {"classname": "zz_brand_new_class", "origin": "8 8 8", "targetname": "x", "weirdkey": "1",
         "OnTrigger": "nobody,Kill,,0,-1"},
        {"classname": "prop_physics", "origin": "10 10 10", "model": "models/zz/unlisted_thing.mdl"}]


def tmp_tier(files):
    d = tempfile.mkdtemp()
    for k, v in files.items():
        with open(os.path.join(d, k), "w") as f:
            f.write(v)
    return d


class TierTests(unittest.TestCase):
    def test_precedence_texture_higher_tier_wins(self):
        a = tmp_tier({"textures.tsv": "ZZQ/NEWWALL\twall_a\n"})
        g = tmp_tier({"textures.tsv": "ZZQ/NEWWALL\twall_g\n"})
        m = tmp_tier({"rules.json": json.dumps({"textures": {"ZZQ/NEWWALL": {"material": "wall_m"}}})})
        self.assertIsNone(rules.RuleSet.build().texture("ZZQ/NEWWALL"))
        self.assertEqual(rules.RuleSet.build(addon=[a]).texture("ZZQ/NEWWALL")[::2], ("wall_a", "addon"))
        self.assertEqual(rules.RuleSet.build(addon=[a], game=g).texture("ZZQ/NEWWALL")[::2], ("wall_g", "game"))
        self.assertEqual(rules.RuleSet.build(addon=[a], game=g, map_rules=os.path.join(m, "rules.json")).texture(
            "ZZQ/NEWWALL")[::2], ("wall_m", "map"))

    def test_lower_tier_still_answers_what_higher_does_not_name(self):
        g = tmp_tier({"textures.tsv": "ZZQ/NEWWALL\twall_g\n"})
        rs = rules.RuleSet.build(game=g)
        self.assertEqual(rs.texture("ZZQ/NEWWALL")[2], "game")
        hit = rs.texture("WOOD/WOODFLOOR001A")
        self.assertTrue(hit is None or hit[2] == "default")

    def test_a_game_glob_beats_a_default_exact_row(self):
        g = tmp_tier({"textures.tsv": "*\tcatch_all\n"})
        rs = rules.RuleSet.build(game=g)
        d = rules.default_tier().textures.rows[0].pattern
        self.assertEqual(rs.texture(d)[2], "game")

    def test_class_precedence_and_fallback(self):
        g = tmp_tier({"classes.tsv": "zz_brand_new_class\tpoint\tmine\tDotMapThing\nzz_fam_*\tdrawn\tfamily\n"})
        rs = rules.RuleSet.build(game=g)
        self.assertEqual(rs.klass("zz_brand_new_class")[::3], ("point", "game"))
        self.assertEqual(rs.klass("zz_fam_x")[::3], ("drawn", "game"))
        self.assertEqual(rs.klass("worldspawn")[3], "default")
        self.assertEqual(rules.RuleSet.build().klass("zz_brand_new_class")[2:], ("fallback", "fallback"))
        self.assertEqual(rules.RuleSet.build().treatment("zz_brand_new_class")[0], "data")

    def test_bad_rows_and_missing_paths_are_errors(self):
        with self.assertRaises(ValueError):
            rules.RuleSet.build(game="/nonexistent/rules")
        with self.assertRaises(ValueError):
            rules.RuleSet.build(game=tmp_tier({"classes.tsv": "a\tnotatreatment\n"}))

    def test_model_row_and_silent_sound_row_are_mapped(self):
        g = tmp_tier({"models.tsv": "unlisted_thing\tarmchair\tKenney\thttps://kenney.nl\tKenney\tCC0-1.0\n"})
        rs = rules.RuleSet.build(game=g)
        self.assertEqual(rs.models_view().get("zz/unlisted_thing.mdl")["stand_in"], "armchair")
        self.assertEqual(rs.used["models"]["zz/unlisted_thing.mdl"], "game")
        self.assertIsNone(rules.RuleSet.build().models_view().get("zz/unlisted_thing.mdl"))


class RegenTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.out = os.path.join(tempfile.mkdtemp(), "m")
        store.put(self.root, "t", "fix", synth.build(entities=ENTS, materials=MAT, faces=True),
                  {"author": "A", "page": "https://example.invalid/a"})

    def run_regen(self, **kw):
        a = dict(entry="t/fix", out=self.out, root=self.root, addon_rules=None, game_rules=None, map_rules=None,
                 ratchet=False, baseline=None, coverage=None, catalogue=None, name=None, scale="visual", y0=0.0)
        a.update(kw)
        import argparse
        return regen.cmd(argparse.Namespace(**a))

    def report(self):
        with open(self.out + ".coverage.json") as f:
            return json.load(f)

    def test_fallbacks_are_listed_not_dropped(self):
        self.assertIn(self.run_regen(), (0, 4))
        lists = self.report()["lists"]
        self.assertEqual(lists["classes_unmapped"], ["zz_brand_new_class"])
        self.assertIn("ZZQ/NEWWALL", lists["textures_unmapped"])
        self.assertEqual(lists["models_unmapped"], ["zz/unlisted_thing.mdl"])
        self.assertEqual(lists["links_unresolved"], ["zz_brand_new_class.OnTrigger->nobody"])
        doc = json.load(open(self.out + ".json"))
        self.assertTrue(any(e["classname"] == "zz_brand_new_class" and e["rule"] == "fallback" for e in doc["entities"]))
        self.assertTrue(any(m["stand_in"] == "placeholder_box" for m in doc["licence"]["models"]))

    def test_ratchet_passes_when_equal_and_fails_when_a_rule_is_dropped(self):
        g = tmp_tier({"classes.tsv": "zz_brand_new_class\tdata\tdecided\tDotMapEntity\n",
                      "models.tsv": "unlisted_thing\tarmchair\tKenney\thttps://kenney.nl\tKenney\tCC0-1.0\n",
                      "textures.tsv": "ZZQ/*\tplaster\n"})
        self.run_regen(game_rules=g)
        better = self.report()["lists"]
        self.assertEqual(better["classes_unmapped"], [])
        self.assertEqual(better["models_unmapped"], [])
        self.assertEqual(self.run_regen(game_rules=g, ratchet=True) & 5, 0)      # unchanged: passes
        self.assertEqual(self.run_regen(ratchet=True), 5)                        # a rule gone: fails
        self.assertEqual(self.report()["lists"], better)                         # and the baseline is not rewritten

    def test_ratchet_needs_a_baseline(self):
        self.assertEqual(self.run_regen(ratchet=True), 2)

    def test_unmapped_keys_against_a_catalogue(self):
        cat = os.path.join(tempfile.mkdtemp(), "defs.json")
        with open(cat, "w") as f:
            json.dump({"classes": {"zz_brand_new_class": {"keys": {"weirdkey2": {}}}, "worldspawn": {"keys": {"skyname": []}}}}, f)
        self.run_regen(catalogue=cat)
        self.assertEqual(self.report()["lists"]["keys_unmapped"], ["zz_brand_new_class.weirdkey"])

    def test_credit_is_required(self):
        store.put(self.root, "t", "nocredit", synth.build(entities=ENTS, materials=MAT + ("X/Y",)))
        self.assertEqual(self.run_regen(entry="t/nocredit"), 2)


if __name__ == "__main__":
    unittest.main()
