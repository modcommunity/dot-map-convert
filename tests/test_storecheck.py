"""storecheck: a world's art resolves through published slices and their dependencies, or the gap is named.
Run: python3 -I tools/bsp/tests/test_storecheck.py
"""
import base64
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import storecheck  # noqa: E402


def publish(dist, sid, version, files, deps=()):
    body = {"content_id": sid, "version": version, "files": [{"path": f} for f in files], "dependencies": [{"id": d[0], "version": d[1]} for d in deps]}
    out = os.path.join(dist, sid.replace("/", "_"), version)
    os.makedirs(out)
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump({"payload": base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")}, f)


def world(pack=None):
    lic = {"textures": [{"kind": "pbr", "key": "pbr:a", "file": "pbr/Brick01", "tier": "1k"}],
           "model_stand_ins": [{"stand_in": "lib/m", "store_file": "poly/m/m.glb"}],
           "models": [{"stand_in": "lib/m"}]}
    if pack:
        lic["store_pack"] = pack
    return {"licence": lic, "surfaces": [{"free": "pbr:a"}]}


class Check(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        publish(self.d, "o/shared", "h1", ["pbr/Brick01/1k/albedo.webp.import"])
        publish(self.d, "o/root", "h2", ["models/poly/m/m.glb.import"], deps=[("o/shared", "h1")])

    def test_resolves_through_dependency(self):
        self.assertEqual(storecheck.check(world({"id": "o/root", "version": "h2"}), self.d, dist=self.d), [])

    def test_unstamped_world_is_a_problem(self):
        self.assertIn("no licence.store_pack", storecheck.check(world(), self.d, dist=self.d)[0])

    def test_unpublished_slice_and_missing_items(self):
        bad = storecheck.check(world({"id": "o/root", "version": "h9"}), self.d, dist=self.d)
        self.assertEqual(len(bad), 1)
        self.assertIn("o/root@h9", bad[0])
        publish(self.d, "o/thin", "h1", [])
        bad = storecheck.check(world({"id": "o/thin", "version": "h1"}), self.d, dist=self.d)
        self.assertTrue(any("PBR sets" in b and "Brick01" in b for b in bad))
        self.assertTrue(any("models" in b and "m.glb" in b for b in bad))

    def test_model_without_a_stand_in_row(self):
        w = world({"id": "o/root", "version": "h2"})
        w["licence"]["models"].append({"stand_in": "lib/other"})
        self.assertTrue(any("lib/other" in b for b in storecheck.check(w, self.d, dist=self.d)))


if __name__ == "__main__":
    unittest.main()
