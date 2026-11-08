"""bundle: a world's pack carries the library models it draws and points model_store at them.
Run: python3 -P tests/test_bundle.py
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import bundle  # noqa: E402


def make(root, rows):
    store = os.path.join(root, "store")
    for r in rows:
        os.makedirs(os.path.dirname(os.path.join(store, r)), exist_ok=True)
        if not r.startswith("gone"):
            open(os.path.join(store, r), "wb").write(b"glb")
    os.makedirs(os.path.join(root, "worlds", "w"))
    doc = {"licence": {"model_store": "../../store", "model_stand_ins": [{"stand_in": "lib/x", "store_file": r} for r in rows]}}
    json.dump(doc, open(os.path.join(root, "worlds", "w", "w.json"), "w"))
    return os.path.join(root, "worlds", "w")


class BundleTest(unittest.TestCase):
    def test_copies_used_models_and_repoints(self):
        with tempfile.TemporaryDirectory() as t:
            w = make(t, ["a/m.glb", "b/n.glb"])
            copied, missing = bundle.bundle_world(w, os.path.join(t, "out", "w"))
            self.assertEqual(copied, ["a/m.glb", "b/n.glb"])
            self.assertEqual(missing, [])
            self.assertTrue(os.path.isfile(os.path.join(t, "out", "w", "models", "a", "m.glb")))
            doc = json.load(open(os.path.join(t, "out", "w", "w.json")))
            self.assertEqual(doc["licence"]["model_store"], "models")

    def test_gltf_brings_its_bin_and_textures(self):
        with tempfile.TemporaryDirectory() as t:
            w = make(t, ["p/car/car.gltf"])
            os.makedirs(os.path.join(t, "store", "p", "car", "textures"))
            open(os.path.join(t, "store", "p", "car", "car.bin"), "wb").write(b"b")
            open(os.path.join(t, "store", "p", "car", "textures", "d.jpg"), "wb").write(b"j")
            bundle.bundle_world(w, os.path.join(t, "out", "w"))
            self.assertTrue(os.path.isfile(os.path.join(t, "out", "w", "models", "p", "car", "car.bin")))
            self.assertTrue(os.path.isfile(os.path.join(t, "out", "w", "models", "p", "car", "textures", "d.jpg")))

    def test_missing_file_is_reported_not_hidden(self):
        with tempfile.TemporaryDirectory() as t:
            w = make(t, ["a/m.glb", "gone/n.glb"])
            copied, missing = bundle.bundle_world(w, os.path.join(t, "out", "w"))
            self.assertEqual(missing, ["gone/n.glb"])


if __name__ == "__main__":
    unittest.main()
