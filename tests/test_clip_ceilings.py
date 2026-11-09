"""The clip ceilings drop_lids removes from the document are kept in the server's nav extra, and the sky lids are not."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, os.path.join(ROOT, "adapters", "zombie-zone-maps")]
os.environ.setdefault("DOTBSP_PATH", ROOT)

sys.path.append(os.path.join(os.path.dirname(ROOT), "zombie-zone-maps", "tools"))
try:
    import import_bsp as I  # noqa: E402
except ImportError:
    I = None

CLIP = {"at": [0.6, 3.62, 57.9], "size": [67.0, 0.076, 67.0], "mat": "concrete", "visible": False, "kind": "clip", "_rise": 1.0}
SKY = {"at": [0.6, 33.5, 57.9], "size": [67.0, 1.2, 67.0], "mat": "sky", "visible": False, "kind": "sky"}


@unittest.skipIf(I is None, "the zombie-zone-maps adapter is not importable here")
class ClipCeilings(unittest.TestCase):
    def setUp(self):
        I.DROPS.clear()
        I.DROPS.extend([("drop_lids", CLIP), ("drop_lids", SKY), ("drop_buried", dict(CLIP))])

    def tearDown(self):
        I.DROPS.clear()

    def test_only_the_dropped_clip_lid_is_kept(self):
        got = I.clip_ceilings()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["kind"], "clip")
        self.assertNotIn("_rise", got[0])

    def test_an_unbudgeted_map_still_gets_them(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "m.json")
            with open(path, "w") as f:
                json.dump({"id": "m", "boxes": [], "world_collision": {"hulls": "x"}}, f)
            I.write_nav_extra(path, {})
            extra = json.load(open(os.path.join(d, "hulls", "m.nav.json")))
        self.assertEqual([b["kind"] for b in extra["boxes"]], ["clip"])


if __name__ == "__main__":
    unittest.main()
