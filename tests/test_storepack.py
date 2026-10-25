"""credits_list and the store slice: what a map draws is copied, imported VRAM-compressed, named by content, stamped.
Run: python3 -I tools/bsp/tests/test_storepack.py
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from dotbsp import licence, storepack  # noqa: E402

DOC = {"licence": {
    "textures": [
        {"kind": "pbr", "key": "a", "file": "pbr/set_a", "tier": "1k", "generic": "A", "author": "x", "licence": "CC0-1.0", "url": "u/a", "surfaces": 3},
        {"kind": "generated", "key": "g", "generic": "G", "file": "g.png"}],
    "model_stand_ins": [
        {"stand_in": "lib/m", "store_file": "poly/m/m.glb", "author": "y", "licence": "CC-BY-4.0", "url": "u/m", "count": 2},
        {"stand_in": "kenney/k", "author": "z", "licence": "CC0-1.0", "url": "u/k", "count": 1}],
    "sounds": []}}


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class Credits(unittest.TestCase):
    def test_rows(self):
        rows = licence.credits_list(DOC)
        self.assertEqual([r["name"] for r in rows], ["A", "lib/m", "kenney/k"])
        self.assertEqual([r["attribution"] for r in rows], [False, True, False])
        self.assertEqual(rows[0]["uses"], 3)


class Slice(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.pbr = os.path.join(self.t, "pbr-library")
        self.mod = os.path.join(self.t, "model-library")
        touch(os.path.join(self.pbr, "set_a", "1k", "albedo.webp"), b"A")
        touch(os.path.join(self.pbr, "set_a", "1k", "normal.jpg"), b"N")
        touch(os.path.join(self.pbr, "set_a", "2k", "albedo.webp"), b"BIG")
        touch(os.path.join(self.mod, "poly", "m", "m.glb"), b"G")
        touch(os.path.join(self.mod, "poly", "m", "Textures", "t.png"), b"T")
        touch(os.path.join(self.mod, "poly", "other", "o.glb"), b"O")

    def test_slice_has_only_what_is_drawn(self):
        dest = os.path.join(self.t, "s")
        files = storepack.slice_for([DOC], self.pbr, self.mod, dest)
        self.assertEqual(files, sorted(["pbr/set_a/1k/albedo.webp", "pbr/set_a/1k/normal.jpg", "models/poly/m/m.glb",
                                        "models/poly/m/Textures/t.png", "credits.json"]))
        self.assertTrue(os.path.isfile(os.path.join(dest, "pbr/set_a/1k/albedo.webp.import")))
        with open(os.path.join(dest, "pbr/set_a/1k/normal.jpg.import")) as f:
            self.assertIn("compress/normal_map=1", f.read())
        with open(os.path.join(dest, "credits.json")) as f:
            self.assertEqual(len(json.load(f)["works"]), 3)

    def test_version_ignores_import_markers_and_follows_content(self):
        a, b = os.path.join(self.t, "a"), os.path.join(self.t, "b")
        fa = storepack.slice_for([DOC], self.pbr, self.mod, a)
        fb = storepack.slice_for([DOC], self.pbr, self.mod, b)
        va = storepack.version_of(a, fa)
        self.assertEqual(va, storepack.version_of(b, fb))
        with open(os.path.join(a, "pbr/set_a/1k/albedo.webp.import"), "a") as f:
            f.write("uid=\"uid://x\"\n")
        self.assertEqual(va, storepack.version_of(a, fa))
        touch(os.path.join(a, "pbr/set_a/1k/albedo.webp"), b"CHANGED")
        self.assertNotEqual(va, storepack.version_of(a, fa))
        self.assertNotEqual(va, storepack.version_of(a, fa, vram=False))

    def test_equal_size_regenerated_file_is_recopied(self):
        dest = os.path.join(self.t, "s")
        files = storepack.slice_for([DOC], self.pbr, self.mod, dest)
        v1 = storepack.version_of(dest, files)
        touch(os.path.join(self.pbr, "set_a", "1k", "albedo.webp"), b"Z")    # same size, new content
        files = storepack.slice_for([DOC], self.pbr, self.mod, dest)
        with open(os.path.join(dest, "pbr/set_a/1k/albedo.webp"), "rb") as f:
            self.assertEqual(f.read(), b"Z")
        self.assertNotEqual(storepack.version_of(dest, files), v1)

    def test_stale_files_are_removed(self):
        dest = os.path.join(self.t, "s")
        storepack.slice_for([DOC], self.pbr, self.mod, dest)
        touch(os.path.join(dest, "pbr/old/1k/albedo.webp"), b"old")
        touch(os.path.join(dest, "pbr/old/1k/albedo.webp.import"), b"old")
        touch(os.path.join(dest, "stray.txt"), b"s")
        files = storepack.slice_for([DOC], self.pbr, self.mod, dest)
        on_disk = sorted(os.path.relpath(os.path.join(d, f), dest).replace(os.sep, "/")
                         for d, _, fs in os.walk(dest) for f in fs if not f.endswith(".import"))
        self.assertEqual(on_disk, files)
        self.assertFalse(os.path.exists(os.path.join(dest, "pbr/old")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "pbr/set_a/1k/albedo.webp.import")))

    def test_stamp_is_idempotent(self):
        mp = os.path.join(self.t, "manifest.json")
        with open(mp, "w") as f:
            json.dump(DOC, f)
        self.assertTrue(storepack.stamp(mp, "o/n", "h1"))
        self.assertFalse(storepack.stamp(mp, "o/n", "h1"))
        self.assertTrue(storepack.stamp(mp, "o/n", "h2"))

    def test_only_limits_the_slice_and_credits_can_be_left_out(self):
        dest = os.path.join(self.t, "s")
        files = storepack.slice_for([DOC], self.pbr, self.mod, dest, only={("p", "set_a", "1k")}, credits=False)
        self.assertEqual(files, ["pbr/set_a/1k/albedo.webp", "pbr/set_a/1k/normal.jpg"])
        self.assertFalse(os.path.exists(os.path.join(dest, "credits.json")))

    def test_version_follows_dependencies(self):
        dest = os.path.join(self.t, "s")
        files = storepack.slice_for([DOC], self.pbr, self.mod, dest)
        a = storepack.version_of(dest, files, deps=[{"id": "o/x", "version": "h1"}])
        self.assertNotEqual(a, storepack.version_of(dest, files))
        self.assertNotEqual(a, storepack.version_of(dest, files, deps=[{"id": "o/x", "version": "h2"}]))

    def test_stamp_lists_shared_slices(self):
        mp = os.path.join(self.t, "manifest.json")
        with open(mp, "w") as f:
            json.dump(DOC, f)
        sh = [{"id": "o/s", "version": "h9"}]
        self.assertTrue(storepack.stamp(mp, "o/n", "h1", sh))
        self.assertFalse(storepack.stamp(mp, "o/n", "h1", sh))
        with open(mp) as f:
            self.assertEqual(json.load(f)["licence"]["store_pack"]["shared"], sh)

    def test_ids(self):
        self.assertEqual(storepack.slice_id("GameMann", "Store ZE_x.1"), "gamemann/store-ze_x-1")


class Plan(unittest.TestCase):
    def test_groups_by_the_maps_that_draw_them(self):
        wants = {"a": {1, 2, 3}, "b": {2, 3, 4}, "c": {3, 5}}
        sizes = {i: 10 * i for i in range(1, 6)}
        shared, private = storepack.plan(wants, sizes, shared=8)
        self.assertEqual(shared, {frozenset("ab"): [2], frozenset("abc"): [3]})
        self.assertEqual(private, {"a": [1], "b": [4], "c": [5]})

    def test_only_the_biggest_groups_are_cut_and_every_member_depends_on_them(self):
        wants = {"a": {1, 2}, "b": {1, 3}, "c": {2, 3}}
        sizes = {1: 5, 2: 50, 3: 500}
        shared, private = storepack.plan(wants, sizes, shared=1)
        # a's biggest is {a,c} (2), b's and c's is {b,c} (3); {a,b} (1) is in nobody's top and stays private to both
        self.assertEqual(set(shared), {frozenset("ac"), frozenset("bc")})
        self.assertEqual(private, {"a": [1], "b": [1], "c": []})

    def test_zero_is_the_old_one_slice_per_map(self):
        shared, private = storepack.plan({"a": {1}, "b": {1, 2}}, {1: 1, 2: 1}, shared=0)
        self.assertEqual(shared, {})
        self.assertEqual(private, {"a": [1], "b": [1, 2]})

    def test_every_item_is_in_exactly_one_slice_of_each_map(self):
        wants = {"a": {1, 2, 3, 4}, "b": {2, 3, 5}, "c": {3, 4, 5}}
        shared, private = storepack.plan(wants, {i: i for i in range(1, 6)}, shared=1)
        for m, its in wants.items():
            got = sorted(i for g, v in shared.items() if m in g for i in v) + private[m]
            self.assertEqual(sorted(got), sorted(its))

    def test_tree_keeps_each_manifest_at_eight(self):
        self.assertEqual(storepack.chunk_tree(list(range(8))), [])
        lv = storepack.chunk_tree(list(range(20)))
        self.assertEqual([len(n) for n in lv[0]], [8, 8, 4])
        self.assertEqual(len(lv), 1)
        self.assertEqual(len(storepack.chunk_tree(list(range(70)))), 2)

    def test_shared_name_is_stable(self):
        self.assertEqual(storepack.shared_name({"a", "b"}), storepack.shared_name(["b", "a"]))


if __name__ == "__main__":
    unittest.main()
