"""Tests for the shared source texture list (dotbsp/source_textures.tsv, dotbsp/texturemap.py) and the
`unmapped` report. Run: python3 -I tools/bsp/tests/test_texturemap.py"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import bsp as cli                                          # noqa: E402
from dotbsp import docboxes, licence, texturemap                    # noqa: E402

# The ids a game may be asked to draw: the generic list the replacements table (free_textures.tsv)
# defines, so a row naming anything else is a typo and a new generic is added in exactly one place.
GENERIC = set(licence.load())


def table(text):
    with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as f:
        f.write(text)
    try:
        return texturemap.load(f.name)
    finally:
        os.unlink(f.name)


class FakeBsp:
    """Just the lumps `face_counts` reads: three textures, faces 0,0,1,2,2,2."""
    texnames = ["PLASTER/OFFWLLB", "CARPET/OFFFLRA", "TOOLS/TOOLSNODRAW", "NOWHERE/ZZ"]
    texdata = [(0, 0, 0, i) for i in range(4)]
    texinfo = [[0] * 17 + [i] for i in range(4)]
    faces = [(0, 0, 0, 0, 4, ti, -1, 0) for ti in (0, 0, 1, 3, 3, 3, 2, 99)]


class TextureMapTests(unittest.TestCase):
    def test_exact_beats_glob_and_longer_glob_beats_shorter_wherever_they_sit(self):
        t = table("*WALL*\tc\nPLASTER/*\tb\nPLASTER/OFFWLL*\ta\nPLASTER/OFFWLLB\texact\n")
        self.assertEqual(t.lookup("plaster/offwllb")[0], "exact")
        self.assertEqual(t.lookup("PLASTER/OFFWLLC")[0], "a")
        self.assertEqual(t.lookup("PLASTER/INFDOOR")[0], "b")
        self.assertEqual(t.lookup("BRICK/WALL01")[0], "c")
        self.assertIsNone(t.lookup("BRICK/FLOOR"))

    def test_equal_specificity_goes_to_the_earlier_line(self):
        self.assertEqual(table("A/*\tfirst\nB/*\tsecond\nA/*\tthird\n").lookup("A/X")[0], "first")

    def test_tint_forms(self):
        t = table("A\ta\t0.5,0.25,1\nB\tb\t#ff8000\nC\tc\n")
        self.assertEqual(t.lookup("A")[1], (0.5, 0.25, 1.0))
        self.assertEqual(t.lookup("B")[1], (1.0, 0.502, 0.0))
        self.assertIsNone(t.lookup("C")[1])

    def test_a_bad_row_names_its_line(self):
        for bad in ("onlyone\n", "A\ta\t1,2\n", "A\ta\t#12\n"):
            with self.assertRaises(ValueError) as cm:
                table("# fine\n\n" + bad)
            self.assertIn(":3", str(cm.exception))

    def test_majority_material_takes_the_shared_list(self):
        t = table("WOOD/*\twood_planks\nDEV/*\tflat\n")
        self.assertEqual(docboxes.majority_material(["WOOD/A"], t, ("flat", None)), ("wood_planks", None))
        self.assertEqual(docboxes.majority_material(["MAPS/x/WOOD/A_1_2_3"], t), ("wood_planks", None))
        self.assertIsNone(docboxes.majority_material(["TOOLS/NODRAW"], t))
        self.assertEqual(docboxes.majority_material(["NOPE/A"], t, ("flat", None)), ("flat", None))

    def test_unmapped_counts_faces_and_leaves_tools_out(self):
        t = table("PLASTER/*\tplaster_painted\n")
        got = texturemap.unmapped(FakeBsp, t, docboxes.classify_material)
        self.assertEqual(dict(got), {"CARPET/OFFFLRA": 1, "NOWHERE/ZZ": 3})

    def test_the_shipped_list_is_sound(self):
        t = texturemap.load()
        self.assertGreater(len(t.rows), 100)
        self.assertEqual(set(t.materials()) - GENERIC, set())
        seen = {}
        for r in t.rows:
            self.assertNotIn(r.pattern, seen, "%s is on lines %s and %d twice" % (r.pattern, seen.get(r.pattern), r.line))
            seen[r.pattern] = r.line

    def test_drawn_in_code_generics_credit_the_script_that_draws_them(self):
        free = licence.load()
        for name in ("fence", "grate", "bars", "ladder", "shield", "invisible"):
            self.assertIn("dot_map_bsp_mesh.gd", free[name]["url"], name)
            self.assertNotIn("textures.py", free[name]["url"], name)

    def test_a_decal_inside_a_folder_is_not_drawn_as_a_wall(self):
        # '*WARS/*' (five literal characters) used to outrank '*DECAL*' by line order, so a decal drew as a cut-out card
        tm = texturemap.load()
        self.assertEqual(tm.lookup("STARWARS/DECALS/MP_IMPERIAL_SYMBOL")[0], "invisible")
        self.assertEqual(tm.lookup("RNDECALS/X")[0], "flat")

    def test_carpet_and_snow_names_reach_a_photo_set(self):
        t, free = texturemap.load(), licence.load()
        want = {
            "carpet/offflra": "carpet", "carpet/offflrb": "carpet", "cs_italy/carpet-sn03": "carpet_red",
            "customtext/gc textures/carpet/blue_carpet08_darker": "carpet_blue",
            "customtext/gc textures/carpet/gray_carpet02": "carpet_grey",
            "customtext/gc textures/carpet/red_carpet01": "carpet_red",
            "de_piranesi/pi_rug1": "carpet_pattern", "de_piranesi/pi_rug4": "carpet_pattern",
            "nippertextures/clue/clue_redcarp": "carpet_red", "props/carpetfloor001a": "carpet",
            "props/carpetfloor004a": "carpet", "props/carpetfloor006a": "carpet",
            "props/carpetfloor007a": "carpet", "props/carpetfloor008a": "carpet",
            "custom/snowboard": "snow", "custom/snowboard2": "snow",
        }
        for name, material in want.items():
            hit = t.lookup(name)
            self.assertIsNotNone(hit, name)
            self.assertEqual(hit[0], material, name)
            self.assertNotEqual(free[material]["kind"], "generated", name)
            self.assertEqual(free[material]["licence"], "CC0-1.0", name)
        self.assertEqual(len({free[m]["kind"] for m in want.values()} - {"snow"}), 4)

    def test_cli_unmapped_reads_a_map(self):
        import synth
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.bsp")
            with open(p, "wb") as f:
                f.write(synth.build())
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = cli.main(["bsp.py", "unmapped", p])
            self.assertEqual(rc, 0)
            self.assertIn("1 maps", err.getvalue())


if __name__ == "__main__":
    unittest.main()
