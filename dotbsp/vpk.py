"""Valve package archives (`<name>_dir.vpk` + `<name>_NNN.vpk`), read-only, and an internal texture cache.

The base-game archives (HL2, CS:S, HL2:DM dedicated-server installs) are Valve's assets. They are an
INTERNAL reference only: they are read to give an original (`_orig`) conversion its real surfaces, and
nothing taken from them is ever committed or published. So the archive root and the cache both live
outside every git checkout (default `~/mapsrc/basegame`), and `TextureCache` refuses a directory that
sits inside a repository. Published packs use the free swaps in `free_textures.tsv`, never these.
"""
import glob
import hashlib
import os
import struct
import zlib

from . import vtf

SIG = 0x55AA1234
IN_DIR = 0x7FFF                                  # archive index of data stored after the tree, in the _dir file
DEFAULT_ROOT = os.path.expanduser("~/mapsrc/basegame")


class VpkError(OSError):
    pass


def _cstr(buf, pos):
    end = buf.index(b"\0", pos)
    return buf[pos:end].decode("latin-1"), end + 1


class Vpk:
    """One archive set. `entries` maps the lower-cased path to (archive, offset, length, preload, crc)."""

    def __init__(self, dir_vpk):
        if not dir_vpk.endswith("_dir.vpk"):
            raise VpkError("not a *_dir.vpk: %s" % dir_vpk)
        self.dir_vpk, self.base = dir_vpk, dir_vpk[:-len("_dir.vpk")]
        self.entries = {}
        with open(dir_vpk, "rb") as f:
            head = f.read(12)
            if len(head) < 12:
                raise VpkError("short header: %s" % dir_vpk)
            sig, ver, tree = struct.unpack("<III", head)
            if sig != SIG or ver not in (1, 2):
                raise VpkError("not a vpk v1/v2: %s" % dir_vpk)
            if ver == 2:
                f.read(16)
            self.data_start = f.tell() + tree
            buf = f.read(tree)
        if len(buf) < tree:
            raise VpkError("truncated tree: %s" % dir_vpk)
        self._parse(buf)

    def _parse(self, buf):
        pos = 0
        try:
            while True:
                ext, pos = _cstr(buf, pos)
                if not ext:
                    return
                while True:
                    folder, pos = _cstr(buf, pos)
                    if not folder:
                        break
                    while True:
                        name, pos = _cstr(buf, pos)
                        if not name:
                            break
                        crc, pre, arc, off, ln, term = struct.unpack_from("<IHHIIH", buf, pos)
                        pos += 18
                        if term != 0xFFFF:
                            raise VpkError("bad entry terminator in %s" % self.dir_vpk)
                        pre_bytes = buf[pos:pos + pre]
                        pos += pre
                        leaf = name if ext == " " else name + "." + ext
                        path = leaf if folder == " " else "%s/%s" % (folder, leaf)
                        self.entries[path.lower().replace("\\", "/")] = (arc, off, ln, pre_bytes, crc)
        except (ValueError, struct.error):
            raise VpkError("malformed tree: %s" % self.dir_vpk)

    def __contains__(self, path):
        return path.lower() in self.entries

    def paths(self, prefix="", suffix=""):
        return [p for p in self.entries if p.startswith(prefix) and p.endswith(suffix)]

    def get(self, path):
        """The file's bytes (CRC-checked), or None when absent."""
        e = self.entries.get(path.lower())
        if e is None:
            return None
        arc, off, ln, pre, crc = e
        body = b""
        if ln:
            if arc == IN_DIR:
                src, at = self.dir_vpk, self.data_start + off
            else:
                src, at = "%s_%03d.vpk" % (self.base, arc), off
            with open(src, "rb") as f:
                f.seek(at)
                body = f.read(ln)
            if len(body) != ln:
                raise VpkError("short read of %s" % path)
        out = pre + body
        if zlib.crc32(out) & 0xFFFFFFFF != crc:
            raise VpkError("crc mismatch: %s" % path)
        return out


def find_dirs(root=None):
    """Every `*_dir.vpk` under the base-game root, sorted (a stable first-wins order)."""
    return sorted(glob.glob(os.path.join(root or DEFAULT_ROOT, "**", "*_dir.vpk"), recursive=True))


class BaseGame:
    """All installed archives as one file system; the first archive holding a path wins."""

    def __init__(self, root=None):
        self.root = root or DEFAULT_ROOT
        self.sets = [Vpk(p) for p in find_dirs(self.root)]

    def __bool__(self):
        return bool(self.sets)

    def get(self, path):
        for s in self.sets:
            try:
                d = s.get(path)
            except FileNotFoundError:        # a dedicated-server install lists archives it does not ship
                continue
            if d is not None:
                return d
        return None

    def material(self, name):
        """(vmt keys, vtf bytes) of a base-game material, or (None, None)."""
        from . import reader
        path = reader.clean_material(name).lower().replace("\\", "/")
        raw = self.get("materials/%s.vmt" % path)
        if raw is None:
            return None, None
        keys = vtf.vmt_keys(raw.decode("latin-1"))
        base = keys.get("$basetexture")
        if not base:
            return keys, None
        return keys, self.get("materials/%s.vtf" % vtf.base_texture('"$basetexture" "%s"' % base))


def _inside_repo(path):
    d = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return True
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent


class TextureCache:
    """Decoded base-game textures as PNGs under `<root>/cache`, keyed by material name and size.
    INTERNAL ONLY: the directory must be outside every git checkout, and what is in it is never
    published (the `_orig` packs stay on the internal store)."""

    def __init__(self, game=None, cache_dir=None, max_side=512):
        self.game = game if game is not None else BaseGame()
        self.dir = cache_dir or os.path.join(self.game.root, "cache")
        if _inside_repo(self.dir):
            raise VpkError("texture cache must be outside git: %s" % self.dir)
        self.max_side = max_side

    def _path(self, name):
        key = name.lower().replace("\\", "/")
        return os.path.join(self.dir, "%s_%d_%s.png" % (os.path.basename(key)[:40], self.max_side,
                                                         hashlib.sha1(key.encode()).hexdigest()[:10]))

    def png(self, name):
        """PNG bytes of the material's base texture, or None when the archives lack it or it will not decode."""
        p = self._path(name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                return f.read()
        _, data = self.game.material(name)
        if data is None:
            return None
        try:
            w, h, px = vtf.read(data, self.max_side)
        except Exception:
            return None
        out = vtf.png(w, h, px)
        os.makedirs(self.dir, exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "wb") as f:
            f.write(out)
        os.replace(tmp, p)
        return out
