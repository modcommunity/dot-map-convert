#!/usr/bin/env python3
"""Add the gameplay-fidelity section (`gameplay`, `lists.gameplay_lost`) to shipped coverage reports.

    python3 -P tools/coverage_gameplay.py [--store DIR] [--check] REPORT.coverage.json [...]

Each report names its source by `sha256`, a store entry (`dotbsp/store.py`). The rest of the report
is kept as it was, so a world's binaries need not be rebuilt for its report to say what the
converted map does not do as the original did. `--check` writes nothing and exits 5 when a report
would gain a `gameplay_lost` entry (the ratchet) or does not have the section yet. A report whose
source is not in the store fails loudly (exit 2).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotbsp import coverage, reader, store  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--store", default=store.default_root())
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    rc = 0
    for p in a.reports:
        with open(p, encoding="utf-8") as f:
            rep = json.load(f)
        src = os.path.join(a.store, rep.get("sha256", ""), "source.bsp")
        if not rep.get("sha256") or not os.path.isfile(src):
            print("%s: source %s is not in the store %s" % (p, rep.get("sha256") or "(no sha256)", a.store), file=sys.stderr)
            rc = max(rc, 2)
            continue
        with open(src, "rb") as f:
            bsp = reader.Bsp(src, data=f.read()).load()
        old = list(rep.get("lists", {}).get("gameplay_lost", ())) if "gameplay_lost" in rep.get("lists", {}) else None
        coverage.add_gameplay(rep, bsp)
        new = rep["lists"]["gameplay_lost"]
        print("%s: gameplay_lost %d%s" % (p, len(new), "" if old is None else " (was %d)" % len(old)))
        if a.check:
            if old is None:
                print("  RATCHET: no gameplay section yet", file=sys.stderr)
                rc = max(rc, 5)
            elif set(new) - set(old):
                print("  RATCHET: %d new: %s" % (len(set(new) - set(old)), ", ".join(sorted(set(new) - set(old))[:6])), file=sys.stderr)
                rc = max(rc, 5)
            continue
        with open(p, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=1)
            f.write("\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
