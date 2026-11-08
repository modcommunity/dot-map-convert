"""storecheck: a world's art resolves through published slices and their dependencies, or the gap is named.
Run: python3 -P tests/test_storecheck.py
"""
import base64
import json
import os
import sys
import tempfile
import http.server
import threading
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


class Origin(unittest.TestCase):
    """A local CDN stand-in: 403 for Python's default agent, 404 for unpublished, 500 for a broken slice."""

    @classmethod
    def setUpClass(cls):
        cls.dist = tempfile.mkdtemp()
        publish(cls.dist, "o/root", "h2", ["models/poly/m/m.glb.import"])

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get("User-Agent", "").startswith("Python-urllib"):
                    return self.send_error(403)
                if "/broken/" in self.path:
                    return self.send_error(500)
                parts = self.path.split("/")    # /content/<owner>/<name>/<ver>/manifest.json
                f = os.path.join(cls.dist, parts[2] + "_" + parts[3], parts[4], "manifest.json")
                if not os.path.isfile(f):
                    return self.send_error(404)
                with open(f, "rb") as fh:
                    body = fh.read()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.origin = "http://127.0.0.1:%d" % cls.srv.server_port

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_descriptive_agent_gets_through(self):
        self.assertEqual(storecheck.fetch("o/root", "h2", origin=self.origin)["version"], "h2")

    def test_404_is_not_there(self):
        self.assertIsNone(storecheck.fetch("o/root", "h9", origin=self.origin))

    def test_5xx_is_an_error_not_unpublished(self):
        with self.assertRaises(storecheck.FetchError):
            storecheck.fetch("o/broken", "h1", origin=self.origin)
        bad = storecheck.check(world({"id": "o/broken", "version": "h1"}), self.dist, origin=self.origin)
        self.assertTrue(any("could not read" in b for b in bad))
        self.assertFalse(any("not published" in b for b in bad))

    def test_unpublished_over_http(self):
        bad = storecheck.check(world({"id": "o/root", "version": "h9"}), self.dist, origin=self.origin)
        self.assertTrue(any("not published" in b for b in bad))

    def test_default_agent_is_refused_by_the_stand_in(self):
        import urllib.error
        import urllib.request
        with self.assertRaises(urllib.error.HTTPError) as c:
            urllib.request.urlopen(self.origin + "/content/o/root/h2/manifest.json")
        self.assertEqual(c.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
