"""The reader plugin interface. Run: python3 -P tests/test_readers.py"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import synth                                          # noqa: E402
from dotbsp import intermediate, readers              # noqa: E402

LIC = {"author": "A", "url": "https://example.org/a", "licence": "CC0-1.0"}


def fresh():
    reg = readers.Registry()
    reg.register(readers.Reader("wav", "sound", (".WAV",), lambda p, **o: {"path": p, **o}))
    return reg


class Readers(unittest.TestCase):
    def test_read_attaches_the_licence_record(self):
        out = readers.read("a.wav", licence=dict(LIC, extra="dropped"), registry=fresh(), gain=2)
        self.assertEqual(out["kind"], "sound")
        self.assertEqual(out["asset"], {"path": "a.wav", "gain": 2})
        self.assertEqual(out["licence"], LIC)

    def test_refuses_missing_incomplete_or_unaccepted_licence(self):
        for rec in (None, {}, {"author": "A", "url": "u"}, dict(LIC, licence="CC-BY-NC-4.0"), dict(LIC, author=" ")):
            with self.assertRaises(readers.ReaderError, msg=rec):
                readers.read("a.wav", licence=rec, registry=fresh())

    def test_unknown_extension_and_bad_registration(self):
        with self.assertRaises(readers.ReaderError):
            readers.read("a.xyz", licence=LIC, registry=fresh())
        with self.assertRaises(readers.ReaderError):
            fresh().register(readers.Reader("wav", "sound", (".wav",), None))
        with self.assertRaises(readers.ReaderError):
            readers.Reader("x", "video", (".x",), None)
        with self.assertRaises(readers.ReaderError):
            readers.Reader("x", "sound", ("x",), None)

    def test_plugin_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "ogg.py"), "w") as f:
                f.write("from dotbsp import readers\n"
                        "def register(r):\n"
                        "    r.register(readers.Reader('ogg', 'sound', ('.ogg',), lambda p, **o: {'ok': 1}))\n")
            reg = readers.Registry()
            self.assertEqual(len(readers.load_plugins([d], reg)), 1)
            self.assertEqual(readers.read("x.ogg", licence=LIC, registry=reg)["asset"], {"ok": 1})
            with open(os.path.join(d, "bad.py"), "w") as f:
                f.write("x = 1\n")
            with self.assertRaises(readers.ReaderError):
                readers.load_plugins([d], readers.Registry())

    def test_builtin_bsp_reader_writes_the_intermediate(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.bsp")
            with open(p, "wb") as f:
                f.write(synth.build())
            out = readers.read(p, licence=LIC, credit={"author": "A", "page": "https://example.org/a", "licence": "CC0-1.0"})
        self.assertEqual(out["reader"], "bsp-map")
        self.assertEqual(out["asset"]["format"], intermediate.FORMAT)
        self.assertEqual(intermediate.check(out["asset"]), [])


if __name__ == "__main__":
    unittest.main()
