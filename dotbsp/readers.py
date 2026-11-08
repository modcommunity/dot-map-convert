"""The reader plugin interface: how a format other than a BSP map is added to the converter.

A reader turns one input file into a plain dict (its `asset`) and says what it is (`kind`:
map, model, texture, heightmap, sound). Every result leaves with a licence record attached;
`read` refuses an input without a complete one, so no converted asset is ever without
author, source URL and an accepted licence (`licence.ALLOWED`).

    from dotbsp import readers

    def read_wav(path, **opts):
        return {"samples": ..., "lufs": ...}

    readers.register(readers.Reader("wav-sound", "sound", (".wav",), read_wav))
    out = readers.read("steps.wav", licence={"author": "A", "url": "https://...", "licence": "CC0-1.0"})
    out["asset"], out["licence"], out["reader"], out["kind"]

Plugins outside this repository: every `*.py` in a directory named by `$DOTBSP_READERS` (path
list) that defines `register(registry)` is loaded by `load_plugins`, and a map repository
may ship its own. Built in: `bsp-map` (`.bsp`, the intermediate document).

Not done here: the model, texture, heightmap and sound readers themselves, and loudness
normalisation for sounds; they are added as plugins against this interface.
"""

import os

from . import licence as _licence

KINDS = ("map", "model", "texture", "heightmap", "sound")
LICENCE_KEYS = ("author", "url", "licence")


class ReaderError(Exception):
    pass


class Reader:
    """`name` (unique), `kind` (one of KINDS), `extensions` (with dot), `read(path, **opts)`."""

    def __init__(self, name, kind, extensions, read):
        if kind not in KINDS:
            raise ReaderError("reader %r: kind %r is not one of %s" % (name, kind, ", ".join(KINDS)))
        exts = tuple(e.lower() for e in extensions)
        if not exts or any(not e.startswith(".") for e in exts):
            raise ReaderError("reader %r: extensions must be non-empty and start with a dot" % name)
        self.name, self.kind, self.extensions, self.read = name, kind, exts, read


class Registry:
    def __init__(self):
        self._by_name = {}

    def register(self, reader, replace=False):
        if reader.name in self._by_name and not replace:
            raise ReaderError("reader %r is already registered" % reader.name)
        self._by_name[reader.name] = reader
        return reader

    def names(self):
        return sorted(self._by_name)

    def get(self, name):
        try:
            return self._by_name[name]
        except KeyError:
            raise ReaderError("no reader named %r (have: %s)" % (name, ", ".join(self.names()) or "none"))

    def for_path(self, path, kind=None):
        """The reader for a file by extension (the most recently registered wins); None when no reader takes it."""
        ext = os.path.splitext(str(path))[1].lower()
        found = [r for r in self._by_name.values() if ext in r.extensions and (kind is None or r.kind == kind)]
        return found[-1] if found else None


def check_licence(record):
    """Problems with a licence record: [] when it is complete and the licence is accepted."""
    if not isinstance(record, dict):
        return ["licence record is missing"]
    probs = []
    for k in LICENCE_KEYS:
        if not str(record.get(k, "")).strip():
            probs.append("licence record has no %s" % k)
    lic = str(record.get("licence", "")).strip()
    if lic and lic not in _licence.ALLOWED:
        probs.append("licence %r is not one of %s" % (lic, ", ".join(sorted(_licence.ALLOWED))))
    return probs


REGISTRY = Registry()
register = REGISTRY.register


def read(path, licence=None, reader=None, registry=None, **opts):
    """Read `path` with the named reader or the one its extension picks.

    Returns {"reader", "kind", "source", "asset", "licence"}. Raises ReaderError when no
    reader takes the file or the licence record is incomplete (checked before the file is read).
    """
    reg = registry or REGISTRY
    r = reg.get(reader) if reader else reg.for_path(path)
    if r is None:
        raise ReaderError("no reader takes %s (extension %r)" % (path, os.path.splitext(str(path))[1]))
    probs = check_licence(licence)
    if probs:
        raise ReaderError("%s: %s" % (path, "; ".join(probs)))
    return {"reader": r.name, "kind": r.kind, "source": str(path), "asset": r.read(path, **opts),
            "licence": {k: licence[k] for k in LICENCE_KEYS}}


def load_plugins(paths=None, registry=None):
    """Load `register(registry)` from every .py in `paths` (default `$DOTBSP_READERS`, os.pathsep list). Returns the files loaded."""
    reg = registry or REGISTRY
    if paths is None:
        paths = [p for p in os.environ.get("DOTBSP_READERS", "").split(os.pathsep) if p]
    loaded = []
    for d in paths:
        if not os.path.isdir(d):
            raise ReaderError("reader plugin path %s is not a directory" % d)
        for f in sorted(os.listdir(d)):
            if not f.endswith(".py") or f.startswith("_"):
                continue
            full = os.path.join(d, f)
            ns = {"__file__": full, "__name__": "dotbsp_plugin_" + f[:-3]}
            with open(full, encoding="utf-8") as fh:
                exec(compile(fh.read(), full, "exec"), ns)
            if not callable(ns.get("register")):
                raise ReaderError("%s defines no register(registry)" % full)
            ns["register"](reg)
            loaded.append(full)
    return loaded


def _read_bsp(path, credit=None, **opts):
    from . import intermediate, reader
    return intermediate.build(reader.Bsp(path).load(), credit, **opts)


REGISTRY.register(Reader("bsp-map", "map", (".bsp",), _read_bsp))
