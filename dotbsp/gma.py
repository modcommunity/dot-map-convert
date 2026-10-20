"""Garry's Mod workshop archives (.gma), read through fastgmad.

[b]No reader is written here, on purpose.[/b] A .gma is a header, a file table with CRCs and the
files; fastgmad (github.com/WilliamVenner/fastgmad, Apache-2.0) already reads it, checks the
CRCs and refuses what is malformed. dot-bootstrap installs it as `fastgmad` on the path; the
`DOTBSP_FASTGMAD` environment variable names another binary.

A .gma is an untrusted download: fastgmad extracts into a fresh temporary directory, only
files named `*.bsp` are read back into memory, a path that resolves outside that directory is
ignored, and the directory is deleted before this returns. Nothing from the archive is kept
on disk and no path inside it is used as a path anywhere else.
"""

import os
import shutil
import subprocess
import tempfile

TIMEOUT = 600


class GmaError(OSError):
    pass


def find_fastgmad():
    """The fastgmad binary, or None."""
    env = os.environ.get("DOTBSP_FASTGMAD")
    for c in (env, shutil.which("fastgmad"), os.path.expanduser("~/.local/bin/fastgmad")):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def read_bsps(path):
    """[(member path inside the archive, bytes)] for every .bsp in a .gma.

    Raises GmaError when fastgmad is missing or rejects the archive.
    """
    exe = find_fastgmad()
    if not exe:
        raise GmaError("fastgmad was not found; install it (dot-bootstrap does) or set DOTBSP_FASTGMAD")
    tmp = tempfile.mkdtemp(prefix="dotbsp-gma-")
    try:
        out = os.path.join(tmp, "x")
        r = subprocess.run([exe, "extract", "-file", os.path.abspath(path), "-out", out],
                           capture_output=True, text=True, errors="replace", timeout=TIMEOUT)
        if r.returncode != 0 or not os.path.isdir(out):
            raise GmaError("fastgmad could not read %s: %s" % (path, (r.stderr or r.stdout).strip()[-300:]))
        root = os.path.realpath(out)
        found = []
        for d, _dirs, files in os.walk(root):
            for f in sorted(files):
                full = os.path.realpath(os.path.join(d, f))
                if not f.lower().endswith(".bsp") or not full.startswith(root + os.sep) or os.path.islink(os.path.join(d, f)):
                    continue
                with open(full, "rb") as fh:
                    found.append((os.path.relpath(full, root).replace(os.sep, "/"), fh.read()))
        return sorted(found)
    except subprocess.TimeoutExpired:
        raise GmaError("fastgmad timed out on %s" % path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
