"""The importer detector: a map or game repository ships no BSP geometry, entity or texture logic of its own.
Run: python3 -P tests/test_detector.py [REPO_DIR ...]

Scans the `tools/*.py` of the sibling map repositories (`*-maps`, plus the games that convert maps) for
  1. code that reads the VBSP format (the magic, a lump table, lump index constants), and
  2. an importer-named file (`import*`, `reimport*`, `bsp*`) over MAX_LINES lines.
Both belong in dot-map-convert (`dotbsp/`, `adapters/<repo>/`); a repository keeps a launcher and data.
A file that must stay is listed in ALLOW with the reason, so a new one fails. Repositories that are not
checked out beside this one are skipped (CI has only dot-map-convert and dot-map).
"""
import glob
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAX_LINES = 200
EXTRA_REPOS = ("game-g2gfast", "mg-look-at-me")

# Code that parses the format: the magic, a lump table or a lump constant. A docstring that names VBSP is fine.
READS_BSP = re.compile(r"""b['"]VBSP|\bLUMP_[A-Z_]+\b|\blump_(?:table|dir|index|ofs|offset)\b|\blumps\s*\[""")
IMPORTER_NAME = re.compile(r"(^|_)(import|reimport|bsp)", re.I)

# path under the repository -> why it may stay. Shrink this list, never grow it without a reason.
ALLOW = {}


def repos():
    godot = os.environ.get("DOT_GODOT_DIR") or os.path.dirname(ROOT)
    found = sorted(glob.glob(os.path.join(godot, "*-maps")))
    found += [os.path.join(godot, n) for n in EXTRA_REPOS if os.path.isdir(os.path.join(godot, n))]
    return found


def scan(repo):
    """Findings for one repository as (relative path, reason)."""
    out = []
    name = os.path.basename(repo.rstrip("/"))
    for path in sorted(glob.glob(os.path.join(repo, "tools", "*.py"))):
        base = os.path.basename(path)
        rel = "%s/tools/%s" % (name, base)
        if base.startswith("test_") or rel in ALLOW:
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        code = [ln for ln in lines if not ln.lstrip().startswith("#")]
        if any(READS_BSP.search(ln) for ln in code):
            out.append((rel, "reads the VBSP format; use dotbsp.reader"))
        if IMPORTER_NAME.search(base[:-3]) and len(lines) > MAX_LINES:
            out.append((rel, "importer of %d lines (limit %d); make it an adapter in dot-map-convert" % (len(lines), MAX_LINES)))
    return out


class Detector(unittest.TestCase):
    def test_pattern_catches_a_reader(self):
        self.assertTrue(READS_BSP.search('if data[:4] != b"VBSP":'))
        self.assertTrue(READS_BSP.search("x = lumps[10]"))
        self.assertFalse(READS_BSP.search('"""Reads a VBSP map via the shared reader."""'))

    def test_long_importer_is_flagged(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "x-maps", "tools"))
            with open(os.path.join(d, "x-maps", "tools", "import_bsp.py"), "w") as f:
                f.write("x = 1\n" * (MAX_LINES + 1))
            with open(os.path.join(d, "x-maps", "tools", "build_maps.py"), "w") as f:
                f.write("x = 1\n" * (MAX_LINES + 1))
            self.assertEqual([r for r, _ in scan(os.path.join(d, "x-maps"))], ["x-maps/tools/import_bsp.py"])

    def test_no_repository_ships_its_own_importer(self):
        given = [a for a in sys.argv[1:] if os.path.isdir(a)]
        found = []
        for repo in given or repos():
            found += scan(repo)
        self.assertEqual(found, [], "\n" + "\n".join("  %s: %s" % f for f in found))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
