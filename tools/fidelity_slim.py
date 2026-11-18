#!/usr/bin/env python3
"""Cut every map down to what the gameplay-fidelity audit reads, so the audit runs on a build box.

    python3 -P tools/fidelity_slim.py OUT_DIR ROOT [ROOT ...] [--jobs N]

The audit (`dotbsp/fidelity.py`) reads the entity lump and the brush tree (planes, nodes, leafs,
models, leaf brushes, brushes, brush sides): a few MB of a map that is often hundreds of MB of
faces, lighting and packed files. This writes one slim map per distinct source (`<key>.bsp`, a
valid map holding only those lumps, read through mmap so the rest of the file is never paged
in) and `<key>.json` beside it: every path that carried it, its size, the lump sizes of what
was cut (displacements, overlays, cubemaps, static props, the packed files' names and the small
text files a level ships for sound scripts and soundscapes), which the audit counts for its
other-categories table. Two copies of a map (a store copy and a working copy) share one key.
"""

import argparse
import hashlib
import json
import mmap
import os
import struct
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotbsp import reader  # noqa: E402

KEEP = (reader.LUMP_ENTITIES, reader.LUMP_PLANES, reader.LUMP_NODES, reader.LUMP_LEAFS, reader.LUMP_MODELS,
        reader.LUMP_LEAFBRUSHES, reader.LUMP_BRUSHES, reader.LUMP_BRUSHSIDES)
# Lumps whose size alone says a category is present (counted, not kept).
COUNTED = {"dispinfo": reader.LUMP_DISPINFO, "overlays": reader.LUMP_OVERLAYS, "cubemaps": 42,
           "worldlights": 15, "game": reader.LUMP_GAME, "pakfile": reader.LUMP_PAKFILE}
# Packed text files worth carrying whole (sound scripts, soundscapes, map configs, particles manifests).
TEXT_SUFFIXES = (".txt", ".cfg", ".vmt")
TEXT_HINTS = ("soundscape", "level_sounds", "game_sounds", "particles", "maps/", "cfg/")
TEXT_MAX = 256 * 1024


def slim(path):
    with open(path, "rb") as f:
        size = os.fstat(f.fileno()).st_size
        if size < reader.HEADER_BYTES:
            return {"path": path, "error": "too short"}
        d = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            b = reader.Bsp(path, data=d)
            cut = b.truncated()
            if cut:
                return {"path": path, "error": "cut off: lumps %s" % cut[:8]}
            h = hashlib.sha256()
            raw = {}
            for i in KEEP:
                off, ln, ver = b.dir[i]
                raw[i] = (bytes(d[off:off + ln]), ver, struct.unpack_from("<4s", d, 8 + i * 16 + 12)[0])
                h.update(struct.pack("<ii", i, ln))
                h.update(raw[i][0])
            key = h.hexdigest()[:24]
            info = {"key": key, "path": path, "size": size, "version": b.version, "revision": b.revision,
                    "lumps": {n: b.dir[i][1] for n, i in COUNTED.items()}}
            info["pak"], info["texts"] = [], {}
            if b.dir[reader.LUMP_PAKFILE][1]:
                try:
                    off, ln, _ = b.dir[reader.LUMP_PAKFILE]
                    z = zipfile.ZipFile(reader._View(d, off, ln))
                    for zi in z.infolist():
                        n = zi.filename.replace("\\", "/").lower()
                        info["pak"].append(n)
                        if n.endswith(TEXT_SUFFIXES) and any(t in n for t in TEXT_HINTS) and zi.file_size <= TEXT_MAX \
                                and not n.endswith(".vmt"):
                            info["texts"][n] = z.read(zi).decode("latin-1")
                except (zipfile.BadZipFile, ValueError, OSError, NotImplementedError) as ex:
                    info["pak_error"] = str(ex)[:200]
            return info, raw, b.version, b.revision
        finally:
            try:
                d.close()
            except BufferError:      # a zip view still holds it; the collector closes it
                pass


def write(out, info, raw, version, revision):
    blob = bytearray(reader.HEADER_BYTES)
    struct.pack_into("<4si", blob, 0, b"VBSP", version)
    for i, (data, ver, four) in sorted(raw.items()):
        off = len(blob)
        blob += data
        blob += b"\0" * (-len(blob) % 4)
        struct.pack_into("<iii4s", blob, 8 + i * 16, off if data else 0, len(data), ver, four)
    struct.pack_into("<i", blob, 8 + 64 * 16, revision)
    tmp = os.path.join(out, info["key"] + ".bsp.part")
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, os.path.join(out, info["key"] + ".bsp"))


def one(args):
    path, out = args
    try:
        r = slim(path)
    except (ValueError, OSError, struct.error) as ex:
        return {"path": path, "error": str(ex)[:300]}
    if isinstance(r, dict):
        return r
    info, raw, version, revision = r
    if not os.path.exists(os.path.join(out, info["key"] + ".bsp")):
        write(out, info, raw, version, revision)
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--jobs", type=int, default=2, help="processes (0 = one per core)")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    paths = []
    for root in a.roots:
        for dp, _dn, fn in os.walk(root, followlinks=False):
            paths += [os.path.join(dp, n) for n in fn if n.lower().endswith(".bsp")]
    paths.sort()
    byk, errors = {}, []
    with ProcessPoolExecutor(max_workers=a.jobs or os.cpu_count()) as ex:
        for r in ex.map(one, [(p, a.out) for p in paths], chunksize=4):
            if "error" in r:
                errors.append(r)
                continue
            cur = byk.get(r["key"])
            if cur is None:
                r["paths"] = [r.pop("path")]
                byk[r["key"]] = r
            else:
                cur["paths"].append(r["path"])
    for k, info in byk.items():
        with open(os.path.join(a.out, k + ".json"), "w", encoding="utf-8") as f:
            json.dump(info, f, indent=1, sort_keys=True)
    with open(os.path.join(a.out, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"files": len(paths), "maps": len(byk), "errors": errors,
                   "keys": {k: v["paths"] for k, v in sorted(byk.items())}}, f, indent=1, sort_keys=True)
    print("%d files, %d distinct maps, %d unreadable" % (len(paths), len(byk), len(errors)))


if __name__ == "__main__":
    main()
