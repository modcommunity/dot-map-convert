"""dotbsp.sourceframe and tools/audit_maps.py's use of it. Run: python3 -I tests/test_source_frame.py (needs numpy, as the audit runner does)"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                   # noqa: E402
from dotbsp import audit, sourceframe, units  # noqa: E402

BOXES = ((0, 0, 0, 256, 256, 16), (0, 0, 16, 64, 64, 48), (600, 0, 0, 856, 256, 16))
SHIFT = (3.5, 0.75, -2.25)      # what an importer subtracted, game metres


def box_of(b, shift=(0.0, 0.0, 0.0)):
    lo, hi = audit.to_game(b[:3], units.VISUAL), audit.to_game(b[3:], units.VISUAL)
    return {"at": [round((lo[k] + hi[k]) / 2 - shift[k], 3) for k in range(3)],
            "size": [round(abs(hi[k] - lo[k]), 3) for k in range(3)], "yaw": 0}


def tool():
    spec = importlib.util.spec_from_file_location("audit_maps", os.path.join(os.path.dirname(HERE), "tools", "audit_maps.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Frame(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.bsp = os.path.join(self.dir.name, "synth_map.bsp")
        with open(self.bsp, "wb") as f:
            f.write(synth.build(boxes=BOXES, materials=("concrete/concretefloor001", "metal/metalwall001"), faces=True, bevel=False))

    def doc(self, boxes=BOXES, bounds=None):
        d = {"boxes": [box_of(b, SHIFT) for b in boxes]}
        sourceframe.record(d, self.bsp, units.VISUAL, SHIFT, bounds)
        return d

    def audit(self, d):
        p = os.path.join(self.dir.name, "doc.json")
        with open(p, "w") as f:
            json.dump(d, f)
        return tool().run_doc(self.bsp, p, units.VISUAL, 0.002)

    def test_record_fields(self):
        sf = self.doc()["source_frame"]
        self.assertEqual(sf["map"], "synth_map.bsp")
        self.assertEqual(len(sf["sha256"]), 64)
        self.assertEqual(sf["offset"], list(SHIFT))
        self.assertIsNone(sf["crop"])
        # the extent, back in the source's frame, is the source's own: x 0..856 units, z (game) 0..-256 units
        k = units.VISUAL
        b = sf["bounds"]
        self.assertAlmostEqual(b[0], 0.0, 2)
        self.assertAlmostEqual(b[3], 856 * k, 2)
        self.assertAlmostEqual(b[1], 0.0, 2)
        self.assertAlmostEqual(b[4], 48 * k, 2)
        self.assertAlmostEqual(b[2], -256 * k, 2)
        self.assertAlmostEqual(b[5], 0.0, 2)

    def test_crop_is_a_within_rectangle(self):
        crop, band = sourceframe.crop_of([0, 0, -10, 300, 256, 100], units.VISUAL)
        self.assertEqual(crop, [0.0, round(-256 * units.VISUAL, 3), round(300 * units.VISUAL, 3), 0.0])
        self.assertEqual(band, [round(-10 * units.VISUAL, 3), round(100 * units.VISUAL, 3)])
        self.assertIsNone(sourceframe.crop_of(None, 1.0)[0])

    def test_recorded_frame_is_used_exactly(self):
        r = self.audit(self.doc())
        self.assertEqual(r["frame"], "recorded")
        self.assertEqual(r["offset"], list(SHIFT))
        self.assertTrue(r["ok"])
        self.assertEqual(r["fit"], 1.0)

    def test_no_registration_search_when_recorded(self):
        m = tool()
        m.register = lambda *a, **k: self.fail("register() ran although the frame is recorded")
        p = os.path.join(self.dir.name, "d.json")
        with open(p, "w") as f:
            json.dump(self.doc(), f)
        self.assertTrue(m.run_doc(self.bsp, p, units.VISUAL, 0.002)["ok"])

    def test_crop_audits_only_inside(self):
        # the output is cropped to the first 300 units (x): the far slab is out on purpose
        d = self.doc(BOXES[:2], bounds=[0, -10, -10, 300, 300, 100])
        self.assertFalse(self.audit(self.doc(BOXES[:2]))["ok"])      # uncropped, the far slab is a loss
        r = self.audit(d)
        self.assertTrue(r["cropped"])
        self.assertTrue(r["ok"], r)

    def test_other_map_falls_back_to_registration(self):
        d = self.doc()
        d["source_frame"]["sha256"] = "0" * 64
        r = self.audit(d)
        self.assertEqual(r["frame"], "registered")
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["offset"][0], SHIFT[0], delta=0.6)    # found by correlation, to its cell

    def test_old_document_is_unchanged(self):
        d = self.doc()
        del d["source_frame"]
        self.assertIsNone(sourceframe.read(d))
        r = self.audit(d)
        self.assertEqual(r["frame"], "registered")
        self.assertTrue(r["ok"])

    def test_malformed_field_is_ignored(self):
        for bad in (None, 3, {}, {"offset": [1, 2]}, {"offset": "abc"}):
            self.assertIsNone(sourceframe.read({"source_frame": bad}))

    def test_finds_source_by_recorded_name(self):
        m = tool()
        d = self.doc()
        os.makedirs(os.path.join(self.dir.name, "repo", "maps"))
        with open(os.path.join(self.dir.name, "repo", "maps", "x.json"), "w") as f:
            json.dump(d, f)
        idx = m.bsp_index([self.dir.name])
        t = m.targets(os.path.join(self.dir.name, "repo"), idx, set())
        self.assertEqual([(a, b) for a, b, *_ in t], [("x", self.bsp)])


if __name__ == "__main__":
    unittest.main()
