"""tools/refresh_stores.sh: a library file the store lacks gets a link, what is there stays."""
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "tools", "refresh_stores.sh")


def touch(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def read(path):
    with open(path) as f:
        return f.read()


class RefreshStores(unittest.TestCase):
    def test_adds_missing_keeps_existing(self):
        with tempfile.TemporaryDirectory() as t:
            lib = os.path.join(t, "lib")
            repo = os.path.join(t, "maps")
            store = os.path.join(repo, ".stores", "model-library")
            touch(os.path.join(lib, "kenney", "mini-arcade", "wall.glb"), "lib")
            touch(os.path.join(lib, "kenney", "kit", "a.glb"), "lib")
            touch(os.path.join(lib, "kenney", "kit", "b.glb"), "lib")
            touch(os.path.join(store, "kenney", "kit", "a.glb"), "mine")
            os.symlink(os.path.join(t, "gone"), os.path.join(store, "kenney", "kit", "b.glb"))
            out = subprocess.run([SCRIPT, repo, lib], check=True, capture_output=True, text=True).stdout
            self.assertIn("2 links added", out)
            self.assertEqual(read(os.path.join(store, "kenney", "mini-arcade", "wall.glb")), "lib")
            self.assertEqual(read(os.path.join(store, "kenney", "kit", "a.glb")), "mine")
            self.assertEqual(read(os.path.join(store, "kenney", "kit", "b.glb")), "lib")
            out = subprocess.run([SCRIPT, repo, lib], check=True, capture_output=True, text=True).stdout
            self.assertIn("0 links added", out)

    def test_missing_store_fails(self):
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run([SCRIPT, t, t], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
