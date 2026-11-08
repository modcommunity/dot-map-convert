"""Headless batch migration of g2gfast maps: re-import (hull kinds) and optionally regen into dot-map worlds.

    python3 -I migrate_batch.py --repo ../game-g2gfast --src ../inspirations/g2gfast --out DIR [--regen WORLDS] [--jobs 4] [ids... | --all]

Per map: runs the game's `tools/bsp_import.py` (this directory's bsp_import.py through the launcher) into DIR, reads the manifest it wrote
and records the hull count and the hull kinds (`collision.hull_kinds`: clip / glass / fence / sky; absent = all solid). With `--regen`,
also runs `bsp.py regen g2g/<id> --out WORLDS/<id>/<id> --name <id>` for ids that have a lossless store entry. Rows go to DIR/migrate.tsv:
id, status (ok, nosource, importfail, regenfail, nostore), hulls, kinds, seconds. Exit 1 when any map failed. Re-running skips a map whose
manifest is newer than its bsp and already carries `hull_kinds` unless `--force`. Output is for local use: converted third-party map data is
never committed.
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import time

# -I would drop the user site where numpy lives on the fleet boxes; -E -P keeps what -I is for (no PYTHON* variables, no cwd or script dir on the path).
PYFLAGS = ("-E", "-P")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def find_bsp(src, mid):
    """The source file for an id, case-insensitive, in `src` or one level down (the extracted/ and pending/ folders)."""
    want = mid.lower() + ".bsp"
    for base, dirs, files in os.walk(src):
        if base[len(src):].count(os.sep) > 3:
            dirs[:] = []
        for f in files:
            if f.lower() == want:
                return os.path.join(base, f)
    return None


def kinds_of(manifest):
    col = json.load(open(manifest)).get("collision", {})
    return col.get("hull_count", 0), {k: len(v) for k, v in sorted(col.get("hull_kinds", {}).items())}, "hull_kinds" in col


def one(a, mid, bsp_index):
    t0 = time.time()
    bsp = bsp_index.get(mid)
    if not bsp:
        return [mid, "nosource", 0, "", 0]
    manifest = os.path.join(a.out, mid, mid + ".json")
    if not a.force and os.path.exists(manifest) and os.path.getmtime(manifest) > os.path.getmtime(bsp) and kinds_of(manifest)[2]:
        h, k, _ = kinds_of(manifest)
        status = "ok"
    else:
        cmd = [sys.executable, *PYFLAGS, os.path.join(a.repo, "tools", "bsp_import.py"), bsp, a.out, "--id", mid]
        env = dict(os.environ, DOTBSP_PATH=ROOT)
        r = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        open(os.path.join(a.logs, mid + ".import.log"), "w").write(r.stdout + r.stderr)
        if r.returncode != 0 or not os.path.exists(manifest):
            return [mid, "importfail", 0, "exit %d" % r.returncode, round(time.time() - t0)]
        h, k, _ = kinds_of(manifest)
        status = "ok"
    if a.regen:
        out = os.path.join(a.regen, mid)
        os.makedirs(out, exist_ok=True)
        cmd = [sys.executable, *PYFLAGS, os.path.join(ROOT, "bsp.py"), "regen", "g2g/" + mid, "--out", os.path.join(out, mid), "--name", mid]
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        open(os.path.join(a.logs, mid + ".regen.log"), "w").write(r.stdout + r.stderr)
        if r.returncode != 0:
            status = "nostore" if "no store entry" in (r.stdout + r.stderr).lower() or "not in the store" in (r.stdout + r.stderr).lower() else "regenfail"
    return [mid, status, h, " ".join("%s=%d" % kv for kv in k.items()) or "all-solid", round(time.time() - t0)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--repo", default=os.path.join(ROOT, "..", "game-g2gfast"))
    ap.add_argument("--src", default=os.path.join(ROOT, "..", "inspirations", "g2gfast"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--regen", default=None, help="worlds dir: also regen each id from the store into <dir>/<id>/")
    ap.add_argument("--all", action="store_true", help="every .bsp under --src")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    a.logs = os.path.join(a.out, "_logs")
    os.makedirs(a.logs, exist_ok=True)
    bsp_index = {}
    for base, dirs, files in os.walk(a.src):
        for f in sorted(files):
            if f.lower().endswith(".bsp"):
                bsp_index.setdefault(f[:-4].lower(), os.path.join(base, f))
    ids = sorted(bsp_index) if a.all else [i.lower() for i in a.ids]
    if not ids:
        ap.error("give ids or --all")
    with concurrent.futures.ThreadPoolExecutor(max(1, a.jobs)) as ex:
        rows = list(ex.map(lambda m: one(a, m, bsp_index), ids))
    with open(os.path.join(a.out, "migrate.tsv"), "w") as fh:
        for r in rows:
            fh.write("\t".join(str(x) for x in r) + "\n")
            print("\t".join(str(x) for x in r))
    return 0 if all(r[1] in ("ok", "nostore") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
