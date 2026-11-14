"""build_provides refuses a document with a source that no licence.json entry covers.
Run: python3 -P tests/test_provides_licence.py
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

import build_provides  # noqa: E402


def _pack(docs, licence):
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "maps"))
    for name, doc in docs.items():
        json.dump(doc, open(os.path.join(root, "maps", name + ".json"), "w"))
    if licence is not None:
        json.dump(licence, open(os.path.join(root, "licence.json"), "w"))
    return root


def _run(root):
    return build_provides.run(root, ["g/x"], title="T", directory="maps", map_kind="k", argv=["--check"])


BASE = {"paths": [""], "licence": "MIT"}


class T(unittest.TestCase):
    def test_original_without_source_is_covered_by_base(self):
        root = _pack({"a": {"name": "A"}}, [BASE])
        self.assertIsNone(build_provides._unlicensed(root, "maps/a.json"))

    def test_source_with_only_base_fails(self):
        root = _pack({"a": {"name": "A", "source": "https://x"}}, [BASE])
        self.assertIn("no licence.json entry", build_provides._unlicensed(root, "maps/a.json"))
        self.assertEqual(_run(root), 1)

    def test_source_without_licence_file_fails(self):
        root = _pack({"a": {"source_url": "https://x"}}, None)
        self.assertIsNotNone(build_provides._unlicensed(root, "maps/a.json"))

    def test_exact_and_prefix_paths_cover(self):
        c = build_provides._covers
        self.assertTrue(c(["maps/a.json"], "maps/a.json"))
        self.assertTrue(c(["maps/b"], "maps/b/b.json"))
        self.assertTrue(c(["maps/b/"], "maps/b/b.json"))
        self.assertFalse(c(["maps/a"], "maps/ab.json"))
        self.assertFalse(c([""], "maps/a.json"))

    def _each_root(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "maps", "surf_a"))
        json.dump({"name": "A"}, open(os.path.join(root, "maps", "surf_a", "surf_a.json"), "w"))
        return root

    def test_each_names_its_collection(self):
        root = self._each_root()
        kind = lambda mid: "arena"  # noqa: E731
        self.assertEqual(build_provides.run(root, ["g/x"], pack="each", map_kind=kind, argv=[], collection="fc-surf-dm-maps"), 0)
        doc = json.load(open(os.path.join(root, "maps", "surf_a", "provides.json")))
        self.assertEqual(doc["collection"], "fc-surf-dm-maps")
        self.assertEqual(build_provides.run(root, ["g/x"], pack="each", map_kind=kind, argv=["--check"], collection="fc-surf-dm-maps"), 0)
        # Dropping the collection makes the written files stale, so a repo cannot lose it silently.
        self.assertEqual(build_provides.run(root, ["g/x"], pack="each", map_kind=kind, argv=["--check"]), 1)

    def test_each_refuses_a_bad_collection(self):
        root = self._each_root()
        self.assertEqual(build_provides.run(root, ["g/x"], pack="each", map_kind=lambda m: "k", argv=[], collection="Bad Name"), 1)

    def test_licence_uses_repo_name_not_folder(self):
        import subprocess
        root = self._each_root()
        subprocess.run(["git", "-C", root, "init", "-q"], check=True)
        subprocess.run(["git", "-C", root, "remote", "add", "origin", "git@github.com:zees-games/real-name.git"], check=True)
        json.dump([{"paths": ["maps/surf_a"], "licence": "none stated", "exception": "credited-community-map"}],
                  open(os.path.join(root, "licence.json"), "w"))
        self.assertEqual(build_provides.run(root, ["g/x"], pack="each", map_kind=lambda m: "k", argv=[]), 0)
        lic = json.load(open(os.path.join(root, "maps", "surf_a", "licence.json")))
        self.assertEqual(lic[0]["url"], "https://github.com/zees-games/real-name")
        self.assertEqual(lic[0]["title"], "real-name (original content)")


if __name__ == "__main__":
    unittest.main()
