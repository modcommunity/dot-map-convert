"""Finding maps: loose .bsp files, and .bsp files inside the archives maps are downloaded as.

A downloaded archive is untrusted. Nothing here extracts to disk: a zip member is read with
`zipfile`, a rar or 7z member is streamed out of `7z e -so` into memory, and the path inside
the archive is never used as a path here.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

from . import gma

ARCHIVES = (".zip", ".rar", ".7z", ".gma")


class Source:
    """One map: where it is and how to get its bytes."""

    def __init__(self, name, origin, member, nbytes, loader):
        self.name, self.origin, self.member, self.bytes = name, origin, member, nbytes
        self._loader = loader

    def read(self):
        return self._loader()

    def label(self):
        return self.origin if not self.member else "%s!%s" % (self.origin, self.member)


def _stem(path):
    return os.path.splitext(os.path.basename(path.replace("\\", "/")))[0].lower()


def _seven(path):
    exe = shutil.which("7z") or shutil.which("7za")
    if not exe:
        return None, []
    try:
        out = subprocess.run([exe, "l", "-slt", "-ba", path], capture_output=True, text=True,
                             errors="replace", timeout=120).stdout
    except (OSError, subprocess.TimeoutExpired):
        return exe, []
    members, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line.strip():
            if cur.get("Path", "").lower().endswith(".bsp") and cur.get("Folder", "-") != "+":
                members.append((cur["Path"], int(cur.get("Size", "0") or 0)))
            cur = {}
            continue
        k, _, v = line.partition(" = ")
        cur[k.strip()] = v
    return exe, members


def in_archive(path):
    """Every .bsp inside one archive, as Sources."""
    out = []
    low = path.lower()
    if low.endswith(".gma"):
        # fastgmad extracts to a temporary directory that is gone before this returns, so the
        # bytes are read once here (a workshop addon holds one or a few maps).
        try:
            for member, data in gma.read_bsps(path):
                out.append(Source(_stem(member), path, member, len(data), lambda d=data: d))
        except gma.GmaMissing:
            raise
        except gma.GmaError as e:
            raise OSError(str(e))
        return out
    if low.endswith(".zip"):
        try:
            z = zipfile.ZipFile(path)
            for info in z.infolist():
                if info.filename.lower().endswith(".bsp") and not info.is_dir():
                    out.append(Source(_stem(info.filename), path, info.filename, info.file_size,
                                      lambda i=info: zipfile.ZipFile(path).read(i)))
            return out
        except zipfile.BadZipFile:
            pass                      # some ".zip" downloads are other formats; 7z knows
    exe, members = _seven(path)
    for m, size in members:
        out.append(Source(_stem(m), path, m, size, lambda m=m: _extract(exe, path, m)))
    return out


def _extract(exe, path, member):
    """One member's bytes, streamed to memory.

    [b]A packaged 7z often has no RAR codec[/b] (Debian's lists a RAR fine and then says
    "Unsupported Method" for every member), so a .rar is read with unrar when there is one.
    """
    cmds = []
    if path.lower().endswith(".rar") and shutil.which("unrar"):
        cmds.append([shutil.which("unrar"), "p", "-inul", path, member])
    cmds.append([exe, "e", "-so", path, member])
    for cmd in cmds:
        try:
            data = subprocess.run(cmd, capture_output=True, timeout=600).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        if data:
            return data
    raise OSError("%s could not be read out of %s (no extractor handled it)" % (member, path))


def find(paths):
    """Sources under each path (a .bsp, an archive, or a directory searched one level deep)."""
    out = []
    for p in paths:
        if os.path.isdir(p):
            names = sorted(os.listdir(p))
            files = [os.path.join(p, n) for n in names if os.path.isfile(os.path.join(p, n))]
        else:
            files = [p]
        for f in files:
            low = f.lower()
            if low.endswith(".bsp"):
                out.append(Source(_stem(f), f, None, os.path.getsize(f), lambda f=f: open(f, "rb").read()))
            elif low.endswith(ARCHIVES):
                out.append(("archive", f))
    res = []
    for s in out:
        if isinstance(s, tuple):
            try:
                res.extend(in_archive(s[1]))
            except gma.GmaMissing:
                raise                  # not this archive's fault: say so, do not list 0 maps
            except OSError as e:       # one unreadable archive does not end a listing
                print("unreadable: %s: %s" % (s[1], e), file=sys.stderr)
        else:
            res.append(s)
    return res


BSP_NAME = re.compile(r"([A-Za-z0-9_\-.]+)\.bsp\b", re.I)


def converted(root):
    """{map stem: where it is converted} across the family's map repositories under `root`.

    A map counts as converted when a map repository has a document or directory with its id,
    or names its .bsp in a document or a converter spec (a converted map is often renamed:
    a hide-and-seek document from a prop-hunt original).
    """
    seen = {}
    for repo in sorted(glob.glob(os.path.join(root, "*-maps"))):
        rn = os.path.basename(repo)
        idx = os.path.join(repo, "maps.json")
        if os.path.isfile(idx):
            try:
                for m in json.load(open(idx)).get("maps", []):
                    seen.setdefault(str(m.get("id", "")).lower(), rn)
            except (ValueError, AttributeError):
                pass
        for p in glob.glob(os.path.join(repo, "maps", "*")):
            seen.setdefault(_stem(p), rn)
        for p in glob.glob(os.path.join(repo, "maps", "*.json")) + glob.glob(os.path.join(repo, "tools", "**", "*.json"), recursive=True):
            try:
                text = open(p, errors="replace").read(400000)
            except OSError:
                continue
            for m in BSP_NAME.finditer(text):
                seen.setdefault(m.group(1).lower(), rn)
    seen.pop("", None)
    return seen


# A map's prefix is the genre it was built for, which is the game in this family that plays it.
TARGETS = (
    (("surf_", "bhop_", "kz_", "bunnyhop_", "xc_", "climb_"), "game-g2gfast"),
    (("ze_", "zs_", "zm_", "zps_", "zr_"), "game-zombie-zone"),
    (("ph_",), "mg-prop-hunt"),
    (("hns_", "hs_"), "game-hide-n-seek"),
    (("deathrun_", "dr_"), "mg-deathrun"),
    (("ttt_", "mm_", "md_"), "game-murder-mystery"),
    (("gm_", "sb_", "rp_"), "game-playground"),
    (("mg_",), "game-playground"),
    (("dm_", "aim_", "awp_", "fy_", "de_", "cs_", "ctf_", "tdm_", "jb_", "ba_"), "game-arena"),
)

# Which of those games has a working converter today (tools/ in the game or its map repo).
CONVERTER = {
    "game-g2gfast": "game-g2gfast/tools/bsp_import.py (mesh)",
    "game-zombie-zone": "zombie-zone-maps/tools/import_bsp.py (dotbsp)",
    "mg-prop-hunt": "mg-prop-hunt-maps/tools/import_bsp.py",
    "game-hide-n-seek": "hide-n-seek-maps/tools/import_bsp.py",
    "mg-deathrun": "mg-deathrun-maps/tools/bsp_to_course.py",
    "game-playground": "game-playground-maps/tools/import_bsp.py",
}


def target(name):
    n = name.lower()
    for prefixes, game in TARGETS:
        if n.startswith(prefixes):
            return game
    return None
