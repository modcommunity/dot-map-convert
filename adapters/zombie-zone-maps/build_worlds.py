"""Draw a converted map with its own geometry: one world pack per map, for the client alone.

    python3 -I tools/build_worlds.py tools/bsp/<id>.json path/to/<map>.bsp [out_root]

Writes `<out_root>/zz_world_<id>/<id>.{json,bin}` (out_root defaults to `world/`), the drawn
mesh of the source map in dot-map's `dot-bsp-mesh` format (dot-map-convert/dotbsp/mesh.py;
the game reads it with dot-map's DotMapBspMesh), and names it in the map document (`"world"`).

WHY A SECOND FILE AND NOT MORE BOXES. The document's boxes are what collides and what the horde's
ground is cut from, and they stay that; drawn, a curved tunnel, an arch or a sloped roof was a
staircase of boxes and a whole map was a few thousand cubes. The mesh is the original's faces, so
it looks like the map, but it is far larger than the document (180 KB to 1.3 MB against 60 KB), so
it is not sent in MAP: each map's world is its own pack, published by this repository's release
(dot-ci's release-maps), which a client fetches when the server it joins is on that map.

WHAT IS DRAWN IS WHAT THE DOCUMENT COLLIDES WITH, as far as a face can say:
- the world and the spec's `solid_classes`; never a `gate_classes` model (the document draws its
  gates from their boxes, so an opened gate is gone) or anything that moves (a door the game does
  not have would stand drawn and shut in an open doorway);
- a spec's `cut` and `crop` drop the faces they would drop boxes for, by triangle centroid;
- the water's faces are left out (the game draws water itself, from the document's volumes);
- the spec's `add_boxes` (stand-ins for what the game has no mover for) are not in the source, so
  the manifest lists them under `zz.keep_boxes` and the game keeps drawing those as boxes;
- no hulls, except those of the models the game moves (below): nothing else here collides.

WHAT MOVES IS THE GAME'S TO ANIMATE, FROM THE MANIFEST. `movers`, `volumes`, `links`, `entities` and
`destinations` are dot-map's (`bsp.py mesh` writes the same records; DotMapEntities reads them).
A brush entity is left to them only when the document does not already stand it up: a class in
the spec's `solid_classes` or `gate_classes` is boxes (a static wall, or a gate an objective
opens), and a second, moving copy would collide twice. Every other mover keeps its faces in the
mesh (a model of its own, drawn at rest) and, when solid, its hulls, so the game can move the
collider with the picture.

Textures are never the author's: each face carries its source material NAME only, and
`zz.materials` turns it into this game's material id through the importer's own table.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import import_bsp  # noqa: E402  (puts dot-map-convert on the path, and owns the material table)
from dotbsp import environment, importer, licence, mesh, models, movers, reader, standins, units  # noqa: E402

# Metres of world one batch covers: the game's own (ZzMap.CHUNK), because the compatibility renderer
# lights a mesh with at most eight lamps and a chunk is about a room, which is about a lamp.
CHUNK = 12.0

# Brush entities that move in the source. Drawn still they would be shut doors in open doorways.
MOVING = {"func_door", "func_door_rotating", "func_movelinear", "func_button", "func_rot_button",
          "func_rotating", "func_tracktrain", "func_train", "func_plat", "func_platrot",
          "func_physbox", "func_physbox_multiplayer", "func_breakable", "func_breakable_surf",
          "func_pushable", "momentary_rot_button", "func_water_analog"}


# Mover kinds whose model the game carries a collider with.
CARRIED = {"slide", "rotate", "plat", "path"}


def keep_surface(s, spec, live=frozenset()):
    if s.water:
        return False
    if s.model == 0:
        return True
    if s.classname in spec.get("gate_classes", []):
        return False
    if s.classname in spec.get("solid_classes", []):
        return True
    if s.model in live:
        return True
    return s.classname not in MOVING


def live_movers(records, spec):
    """The mover records the game animates: those the document does not already stand up as boxes."""
    boxed = set(spec.get("solid_classes", [])) | set(spec.get("gate_classes", []))
    return [r for r in records if r["classname"] not in boxed and r.get("model") is not None]


def _dropped(c, spec):
    for cut in spec.get("cut", []):
        x0, y0, z0, x1, y1, z1 = cut[:6]
        if len(cut) < 7 and x0 <= c[0] <= x1 and y0 <= c[1] <= y1 and z0 <= c[2] <= z1:
            return True
    wc = spec.get("world_crop")    # drawn faces only: the boxes keep what they have (distant scenery the street never reaches)
    if wc and not (wc[0] <= c[0] <= wc[2] and wc[1] <= c[2] <= wc[3]):
        return True
    crop = spec.get("crop")
    if crop:
        cx0, cz0, cx1, cz1 = crop
        if not (cx0 <= c[0] <= cx1 and cz0 <= c[2] <= cz1):
            return True
    return False


def trim(s, spec):
    """Drops the triangles a `cut` or `crop` would have removed boxes for. A `cut` naming a material
    is about the document's boxes only (it picks one box out of a stack), so it is not applied."""
    if s.sky3d or not (spec.get("cut") or spec.get("crop") or spec.get("world_crop")):
        return s
    return s.retain(lambda c: not _dropped(c, spec))    # Surface.retain keeps uv2 and alpha with the vertices


def _centre(rec):
    lo, hi = rec.get("mins"), rec.get("maxs")
    return [(lo[k] + hi[k]) / 2.0 for k in range(3)] if lo and hi else rec["origin"]


def build(spec, bsp_path):
    bsp = reader.Bsp(bsp_path).load()
    y0 = float(spec.get("y0", 0.0))
    m = mesh.build(bsp, y0=y0, chunk=CHUNK)
    before = len(m.surfaces)
    records = [r for r in live_movers(movers.movers(bsp, units.VISUAL, y0), spec) if not _dropped(_centre(r), spec)]
    live = frozenset(r["model"] for r in records)
    m.surfaces = [s for s in (trim(s, spec) for s in m.surfaces if keep_surface(s, spec, live)) if s.index]
    solid = frozenset(r["model"] for r in records if r["kind"] in CARRIED and r.get("solid", True))
    m.hulls = [h for h in m.hulls if h["model"] in solid]
    # A mover whose faces are all tool textures or hidden has nothing to move.
    has = {s.model for s in m.surfaces} | {h["model"] for h in m.hulls}
    records = [r for r in records if r["model"] in has]
    mats = {s.material: import_bsp.material_for(s.material.lower()) for s in m.surfaces}
    keep = [dict(b) for b in spec.get("add_boxes", [])]
    extra = {"zz": {"materials": dict(sorted(mats.items())), "keep_boxes": keep},
             "movers": records, "volumes": movers.volumes(bsp, units.VISUAL, y0),
             "destinations": movers.destinations(bsp, units.VISUAL, y0),
             "links": movers.links(bsp), "entities": movers.generic(bsp),
             "environment": environment.environment(bsp, units.VISUAL, y0),
             "sounds": environment.sounds(bsp, units.VISUAL, y0)}
    return m, before, extra, bsp, y0


def _kinds(records):
    out = {}
    for r in records:
        out[r["kind"]] = out.get(r["kind"], 0) + 1
    return out


def name_in_document(doc_path):
    """Names the world in the map document (`import_bsp.name_world`), leaving the rest as it was."""
    with open(doc_path) as f:
        doc = json.load(f)
    named = import_bsp.name_world(doc, os.path.join(HERE, ".."))
    if named == doc:
        return False
    with open(doc_path, "w") as f:
        json.dump(named, f, indent=1)
        f.write("\n")
    return True


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    spec = json.load(open(argv[1]))
    map_id = spec["id"]
    root = argv[3] if len(argv) > 3 else os.path.join(HERE, "..", "world")
    out_dir = os.path.join(root, import_bsp.world_pack(map_id))
    os.makedirs(out_dir, exist_ok=True)
    m, before, extra, bsp, y0 = build(spec, argv[2])
    credit = {k: spec[k] for k in ("author", "page", "licence") if k in spec}
    credit["note"] = "Geometry converted from the original map with credit; its textures and models are not used. Removed on the author's request."
    doc = mesh.write(m, os.path.join(out_dir, map_id), credit=credit, name=map_id, extra=extra)
    # The licence pass: every texture a free one, the models and sounds stand-ins (dot-map's tables), props placed.
    # The sizes come from the raw import's models.json when the map has one (no second read of the pakfile).
    raw = importer.raw_dir("zz", map_id)
    packed = models.measure(bsp, raw=raw if os.path.isdir(raw) else None)
    shaped = standins.shape_matches(bsp, packed=packed)
    licence.annotate(doc, out_dir, models=importer.placed_models(bsp), shaped=shaped)
    doc["props"] = standins.placements(bsp, y0=y0, shaped=shaped, packed=packed)
    problems = licence.check(doc)
    with open(os.path.join(out_dir, map_id + ".json"), "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(out_dir, "CREDITS.md"), "w") as f:
        f.write(licence.credits_markdown(doc))
    if problems:
        print("LICENCE CHECK FAILED: " + "; ".join(problems))
        return 4
    c = doc["counts"]
    print("%s: %d of %d surfaces drawn, %d triangles, %d hulls, bin %d bytes (%d gzip'd) -> %s" % (
        map_id, c["surfaces"], before, c["triangles"], c["hulls"], doc["bin"]["bytes"], doc["bin"]["stored_bytes"], out_dir))
    print("  %d movers (%s), %d volumes, %d links, %d entities" % (
        len(extra["movers"]), ", ".join("%s %d" % kv for kv in sorted(_kinds(extra["movers"]).items())),
        len(extra["volumes"]), len(extra["links"]), len(extra["entities"])))
    doc_path = os.path.join(HERE, "..", "maps", map_id + ".json")
    if os.path.isfile(doc_path) and name_in_document(doc_path):
        print("  named it in maps/%s.json" % map_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
