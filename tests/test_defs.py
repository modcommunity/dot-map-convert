"""The class catalogue's tests. Run: python3 -I tools/bsp/tests/test_defs.py

The committed rules/entity_defs.json is checked on its own; when the definition files and dumps
are on this machine (`$DOTBSP_DEFS`, default ~/mapsrc/defs) it is also rebuilt and compared.
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "defs"))

import build                                          # noqa: E402
from dotbsp import defs                               # noqa: E402

DEFS = os.environ.get("DOTBSP_DEFS", os.path.expanduser("~/mapsrc/defs"))
FGD = '''
@BaseClass = Targetname [ targetname(target_source) : "Name" : : "descr" ]
@PointClass base(Targetname) = env_demo : "A demo."
[
	spawnflags(flags) = [ 1: "A" : 0  2: "B" : 1 ]
	amp(float) : "Amp" : 4 : "long " + "text"
	mode(choices) : "Mode" : 1 = [ 0: "Off" 1: "On" ]
	input Go(void) : "go"
	output OnGo(void) : "went"
	@resources [ ]
]
'''
DUMP = '''// c
CDemo - env_demo
- m_x (Offset 4) (Save|Key)(4 Bytes) - extrakey
- InputKick (Offset 0) (Input)(0 Bytes) - Kick
- m_Out (Offset 8) (Save|Key|Output)(0 Bytes) - OnKick
'''


class Catalogue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = defs.load()

    def test_loads_and_is_marked_derived(self):
        self.assertIn("DERIVED", self.doc["_notice"])
        self.assertGreater(len(self.doc["classes"]), 1000)

    def test_only_derived_fields(self):
        allowed = {"bases", "solid", "keys", "inputs", "outputs", "extra", "in"}
        for name, rec in list(self.doc["classes"].items()) + list(self.doc["bases"].items()):
            self.assertLessEqual(set(rec), allowed, name)
            for k, v in rec.get("keys", {}).items():
                self.assertIn(len(v), (2, 3), name + "." + k)

    def test_every_map_class_catalogued_or_unknown(self):
        unknown = set(self.doc["unknown"])
        for c in self.doc["map_classes"]:
            self.assertTrue(defs.known(self.doc, c) or c in self.doc["bases"] or c in unknown, c)
        for c in unknown:
            self.assertIn(c, self.doc["map_classes"])
            self.assertFalse(defs.known(self.doc, c), c)

    def test_resolve_folds_bases(self):
        r = defs.resolve(self.doc, "env_shake")
        self.assertEqual(r["keys"]["amplitude"][:2], ("float", "4"))
        self.assertIn("startshake", r["inputs"])
        self.assertIn("targetname", r["keys"])
        self.assertIn("css", r["in"])
        self.assertIsNone(defs.resolve(self.doc, "no_such_class"))

    def test_dumps_only_class_listed(self):
        self.assertIn("l4d2", defs.resolve(self.doc, "ability_leap")["in"])
        self.assertNotIn("fgd", defs.resolve(self.doc, "ability_leap")["in"])


class Parsing(unittest.TestCase):
    def test_fgd(self):
        classes = {}
        build.parse_fgd(FGD, classes)
        c = classes["env_demo"]
        self.assertEqual(c["bases"], ["targetname"])
        self.assertEqual(c["keys"]["amp"], {"t": "float", "d": "4"})
        self.assertEqual(c["keys"]["mode"]["c"], ["0", "1"])
        self.assertEqual(c["keys"]["spawnflags"]["d"], "2")
        self.assertEqual(c["inputs"]["go"], ("Go", "void"))
        self.assertEqual(c["outputs"]["ongo"], ("OnGo", "void"))
        self.assertTrue(classes["targetname"]["base"])
        self.assertEqual(classes["targetname"]["keys"]["targetname"]["t"], "target_source")

    def test_dump_adds_only_what_definitions_lack(self):
        classes = {}
        build.parse_fgd(FGD, classes)
        with tempfile.NamedTemporaryFile("w", suffix=".txt") as fh:
            fh.write(DUMP)
            fh.flush()
            dm = build.read_datamaps(fh.name)
        build.merge_dumps(classes, {"x": {"maps": dm, "listed": {"gone"}}})
        c = classes["env_demo"]
        self.assertEqual(c["extra"], {"extrakey"})
        self.assertEqual(c["inputs"]["kick"], ("Kick", ""))
        self.assertEqual(c["in"], ["fgd", "x"])
        self.assertEqual(classes["gone"]["in"], ["x"])


@unittest.skipUnless(os.path.isdir(os.path.join(DEFS, "HammerAddons", "fgd")), "definition files not on this machine")
class Rebuild(unittest.TestCase):
    def test_deterministic_and_current(self):
        a = build.dumps_json(build.build(DEFS))
        b = build.dumps_json(build.build(DEFS))
        self.assertEqual(a, b)
        committed = build.dumps_json({k: v for k, v in defs.load().items()
                                      if k not in ("map_classes", "unknown", "maps_scanned", "maps_unreadable")})
        self.assertEqual(a, committed, "entity_defs.json is stale: python3 -I tools/bsp/defs/build.py")


if __name__ == "__main__":
    unittest.main()
