#!/usr/bin/env python3
"""check_zone_fidelity -- every converted teleport catches a player only where Source's did.

Source touches a trigger with the player's hull (32 wide, 72 tall); dot-timer tests one point,
the feet, once a tick. So the importer thickens a thin trigger, and this checks that the
thickening never reaches anywhere Source's trigger could not have touched a player from:

    no_audit          the manifest predates the importer's teleport audit (regenerate the map)
    unaccounted       a trigger_teleport became neither a pit nor anything another rule claimed
    audit_broken      the importer's `teleport_audit.broken` lists a teleport (wrong destination,
                      shadowed, looping, gone: see bsp_import.teleport_audit)
    no_original       a respawn volume does not carry the trigger it was made from
    overreach         a respawn volume reaches further sideways past its trigger than the hull,
                      PLAYER_HALF_WIDTH (bhop_arcane_v2's 8-unit Restart doors caught players 90
                      units from the frame)
    above_sheet       a respawn volume reaches above the top of its trigger, where Source never
                      catches anyone's feet (bhop_arcane_v2's gap strips reached 64 units over its
                      red blocks and reset every hop across a gap); a pit trimmed back off an
                      arrival under it may keep one tick of depth above its plane
    over_landing      the air a player stands or hops in over a block top is inside a respawn
                      volume whose trigger was drawn below that top
    zone_buried       every sample of a START, STAGE, CHECKPOINT or END zone is inside a respawn
                      volume on its track: that part of the route cannot be reached

Reads only maps/<id>/<id>.json, so it checks the converted map, not the importer's opinion of it.
The destinations themselves (in a solid, in a pit, off the map) are check_playable's job.

    tools/check_zone_fidelity.py                  every map (what CI runs)
    tools/check_zone_fidelity.py bhop_arcane_v2   these maps
    tools/check_zone_fidelity.py -v               list every problem, not the first few per map

This is the shared copy; a map repository runs it through its own launcher of the same name,
which calls main(root=<repo>), as tools/check_playable.py is run. A map listed in
tools/zone_fidelity_known.json with exactly the failure counts it records is reported as
`known` and does not fail the run; a known map that now passes, or fails differently, fails
the run until the entry is removed or updated, so the list can only shrink by a fix.
"""
import argparse
import json
import sys
from pathlib import Path

# dot-map-convert adapters/game-airdrift/bsp_import.py
PLAYER_HALF_WIDTH = 16.0
HOP_REACH = 76.0
MIN_ZONE_THICKNESS = 192.0
TICK_DEPTH = 32.0
SLACK = 0.5                 # float noise in the manifest
ROUTE = ("START", "STAGE", "CHECKPOINT", "END")
LANDING = (1.0, 36.0, HOP_REACH - 4.0)   # over a block top: the feet standing, mid-hop, top of a hop


def source_box(lo, hi):
    """A Godot-axes manifest box (x, up, -y) in Source axes (x, y, z up)."""
    a = (lo[0], -lo[2], lo[1])
    b = (hi[0], -hi[2], hi[1])
    return [min(a[i], b[i]) for i in range(3)], [max(a[i], b[i]) for i in range(3)]


def inside(box, p):
    return all(box[0][k] <= p[k] < box[1][k] for k in range(3))


def check_volumes(doc):
    """Respawn volumes against the triggers they were made from (Source axes, z up)."""
    problems = []
    thickness = float(doc.get("min_zone_thickness") or MIN_ZONE_THICKNESS)
    for v in doc.get("respawn_volumes") or []:
        lo, hi = v["min"], v["max"]
        olo, ohi = v.get("original_min"), v.get("original_max")
        if olo is None or ohi is None:
            problems.append(("no_original", "respawn volume", lo))
            continue
        for k in (0, 1):
            allowed = SLACK + (PLAYER_HALF_WIDTH if ohi[k] - olo[k] < thickness else 0.0)
            reach = max(olo[k] - lo[k], hi[k] - ohi[k])
            if reach > allowed:
                problems.append(("overreach", "%.0f units on %s past the trigger %s..%s"
                                 % (reach, "xy"[k], _fmt(olo), _fmt(ohi)), lo))
                break
        # clear_arrivals: a pit trimmed back off an arrival under it takes its tick of depth
        # back above the plane (bhop_badges2), so it is never thinner than one tick's fall.
        above = TICK_DEPTH if v.get("cleared") and hi[2] - lo[2] <= TICK_DEPTH + SLACK else 0.0
        if hi[2] > ohi[2] + above + SLACK:
            problems.append(("above_sheet", "%.0f units over the trigger's top %.0f"
                             % (hi[2] - ohi[2], ohi[2]), lo))
    return problems


def check_landings(doc):
    """The air over every block top, against the respawn volumes drawn under it."""
    problems = []
    vols = [v for v in doc.get("respawn_volumes") or [] if v.get("original_max")]
    if not vols:
        return problems
    for blk in (doc.get("mechanics") or {}).get("blocks") or []:
        if blk.get("class") == "trap":
            # A trap block (bsp_mechanics.trap_blocks) is a teleport lying on a block, not a
            # surface: its own volume is meant to catch whoever stands there. bhop_arcane_v2's
            # strips between them are caught by above_sheet and overreach instead.
            continue
        lo, hi = source_box(blk["min"], blk["max"])
        top = hi[2]
        # The middle and the edges, a unit in: a hop between two blocks lands at the lip.
        spots = [(x, y) for x in _across(lo[0], hi[0]) for y in _across(lo[1], hi[1])]
        hit = None
        for rise in LANDING:
            for at in spots:
                p = (at[0], at[1], top + rise)
                v = next((v for v in vols if v["original_max"][2] < top
                          and inside((v["min"], v["max"]), p)), None)
                if v is not None:
                    hit = (rise, v, p)
                    break
            if hit:
                break
        if hit:
            problems.append(("over_landing", "block top %.0f, %.0f above it, under a trigger drawn at %.0f"
                             % (top, hit[0], hit[1]["original_max"][2]), hit[2]))
    return problems


def _across(a, b):
    """Three feet positions across one side of a block top: a unit in from each lip, and the middle."""
    if b - a <= 2.0:
        return [(a + b) * 0.5]
    return [a + 1.0, (a + b) * 0.5, b - 1.0]


def check_route(doc):
    """Each route zone keeps somewhere a player can be that is not a pit on its track."""
    problems = []
    pits = {}
    for z in doc.get("zones") or []:
        if z.get("kind") == "RESPAWN" and "min" in z:
            pits.setdefault(z.get("track", 0), []).append((z["min"], z["max"]))
    for z in doc.get("zones") or []:
        if z.get("kind") not in ROUTE or "min" not in z:
            continue
        mine = pits.get(z.get("track", 0), [])
        if not mine:
            continue
        lo, hi = z["min"], z["max"]
        samples = [[lo[k] + (hi[k] - lo[k]) * f for k, f in enumerate(fs)]
                   for fs in [(a, b, c) for a in (0.1, 0.5, 0.9) for b in (0.05, 0.3, 0.6)
                              for c in (0.1, 0.5, 0.9)]]
        if all(any(inside(p, s) for p in mine) for s in samples):
            problems.append(("zone_buried", "%s %s" % (z["kind"], z.get("number", "")), lo))
    return problems


def check(doc):
    problems = []
    audit = doc.get("teleport_audit")
    if not isinstance(audit, dict):
        return [("no_audit", "regenerate the map", None)]
    for entry in audit.get("broken") or []:
        problems.append(("audit_broken", json.dumps(entry)[:160], None))
    if audit.get("no_volume"):
        problems.append(("unaccounted", "%d trigger_teleports" % audit["no_volume"], None))
    problems += check_volumes(doc)
    problems += check_landings(doc)
    problems += check_route(doc)
    return problems


def _fmt(p):
    return "(%s)" % ", ".join("%.0f" % x for x in p)


def map_ids(maps_dir):
    return sorted(d.name for d in maps_dir.iterdir() if (d / (d.name + ".json")).is_file())


def main(argv=None, root=None):
    """root is the map repository (maps/ and tools/zone_fidelity_known.json); default the current directory."""
    root = Path(root or ".").resolve()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("maps", nargs="*")
    ap.add_argument("--maps-dir", default=str(root / "maps"))
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--known", default=str(root / "tools" / "zone_fidelity_known.json"))
    ap.add_argument("--json", action="store_true", help="print the failure counts per map as JSON")
    a = ap.parse_args(argv)
    maps_dir = Path(a.maps_dir)
    ids = a.maps or map_ids(maps_dir)
    known = json.loads(Path(a.known).read_text()) if Path(a.known).is_file() else {}
    failed = held = 0
    counts = {}
    for mid in ids:
        try:
            doc = json.loads((maps_dir / mid / (mid + ".json")).read_text())
        except (OSError, ValueError) as e:
            print("FAIL %s: unreadable: %s" % (mid, e))
            failed += 1
            continue
        problems = check(doc)
        kinds = {}
        for p in problems:
            kinds[p[0]] = kinds.get(p[0], 0) + 1
        if kinds:
            counts[mid] = kinds
        want = known.get(mid, {}).get("fails")
        if not problems and want is None:
            print("ok   %s: %d respawn volumes" % (mid, len(doc.get("respawn_volumes") or [])))
            continue
        if want is not None and want == kinds:
            held += 1
            print("known %s: %s (%s)" % (mid, ", ".join("%s %d" % kv for kv in sorted(kinds.items())),
                                        known[mid].get("reason", "")))
            continue
        failed += 1
        if want is not None:
            print("FAIL %s: zone_fidelity_known.json expects %s, got %s: update or remove the entry"
                  % (mid, want, kinds or "no failures"))
            continue
        print("FAIL %s: %s" % (mid, ", ".join("%s %d" % kv for kv in sorted(kinds.items()))))
        for kind, what, at in problems if a.verbose else problems[:5]:
            print("       %s %s%s" % (kind, what, "" if at is None else " at (%.0f, %.0f, %.0f)" % tuple(at)))
    if a.json:
        print(json.dumps(counts, indent=1, sort_keys=True))
    print("check_zone_fidelity: %d maps, %d ok, %d known, %d failed"
          % (len(ids), len(ids) - failed - held, held, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
