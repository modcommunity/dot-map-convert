"""A tiny VBSP file written from scratch, so the tests need no downloaded map.

It holds what a converter reads: a worldspawn, two spawns and a light; one brush per box
given (six sides, one material each, plus an optional bevel); the world model, whose BSP tree
is a single leaf reaching every brush; and, when asked, a brush entity of its own. The lump
records can be written in the swapped v21 order, and the leaves in the v19 size.
"""

import struct

LUMPS = 64


def _ents(entities):
    out = []
    for e in entities:
        out.append("{\n" + "".join('"%s" "%s"\n' % kv for kv in e.items()) + "}\n")
    return ("".join(out) + "\0").encode("ascii")


def build(boxes=((0, 0, 0, 64, 64, 64),), version=20, swapped=False, entities=None,
          materials=("TOOLS/TOOLSNODRAW", "dev/dev_measuregeneric01"), contents=1, bevel=True,
          entity_box=None, entity_origin=(0, 0, 0), game_lump=None, static_props=None, faces=False,
          entity_class="func_door", entity_keys=None):
    """The bytes of a map whose world is `boxes` (x0, y0, z0, x1, y1, z1 in map units).

    `entity_box` adds a brush entity (model *1, a func_door) with that box relative to
    `entity_origin`, which is how the format stores one. `faces` also writes every box's six
    sides as drawn faces (vertexes, edges, surfedges, faces, and texinfo whose s and t axes are
    map x and -y), wound as the compiler winds them: clockwise seen from outside.
    """
    if entities is None:
        entities = [{"classname": "worldspawn", "skyname": "sky_test"},
                    {"classname": "info_player_terrorist", "origin": "16 16 1", "angles": "0 90 0"},
                    {"classname": "info_player_counterterrorist", "origin": "48 48 1", "angles": "0 180 0"},
                    {"classname": "light", "origin": "32 32 60", "_light": "255 200 100 300"}]
    entities = list(entities)
    all_boxes = list(boxes) + ([entity_box] if entity_box else [])
    if entity_box:
        ent = {"classname": entity_class, "model": "*1", "origin": "%g %g %g" % tuple(entity_origin)}
        ent.update(entity_keys or {})
        entities.append(ent)
    planes, sides, brushes = [], [], []
    for b in all_boxes:
        x0, y0, z0, x1, y1, z1 = b
        first = len(sides)
        for n, d in (((1, 0, 0), x1), ((-1, 0, 0), -x0), ((0, 1, 0), y1),
                     ((0, -1, 0), -y0), ((0, 0, 1), z1), ((0, 0, -1), -z0)):
            sides.append((len(planes), len(sides) % len(materials), -1, 0))
            planes.append(n + (d, 0))
        if bevel:      # a bevel duplicates a real side; the reader must drop it
            sides.append((first + 4, 0, -1, 1))
        brushes.append((first, len(sides) - first, contents))
    strings = b""
    table = []
    for m in materials:
        table.append(len(strings))
        strings += m.encode("latin-1") + b"\0"
    nworld = len(boxes)
    texinfo = [(0.0,) * 16 + (0, i) for i in range(len(materials))]
    if faces:
        texinfo = [(1.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0) + (0.0,) * 8 + (0, i) for i in range(len(materials))]
    verts, edges, surfedges, dfaces, model_range = [], [(0, 0)], [], [], []
    if faces:
        for bi, b in enumerate(all_boxes):
            x0, y0, z0, x1, y1, z1 = b
            first_face = len(dfaces)
            for k in range(6):
                pi = bi * 6 + k
                n = planes[pi][:3]
                axis = [i for i in range(3) if n[i]][0]
                lo, hi = (x0, y0, z0), (x1, y1, z1)
                c = (hi if n[axis] > 0 else lo)[axis]
                u, v = [i for i in range(3) if i != axis]
                ring = []
                for a, bb in ((lo[u], lo[v]), (hi[u], lo[v]), (hi[u], hi[v]), (lo[u], hi[v])):
                    p = [0.0, 0.0, 0.0]
                    p[axis], p[u], p[v] = c, a, bb
                    ring.append(tuple(p))
                e1 = [ring[1][i] - ring[0][i] for i in range(3)]
                e2 = [ring[2][i] - ring[0][i] for i in range(3)]
                cr = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                if sum(cr[i] * n[i] for i in range(3)) > 0:
                    ring.reverse()
                fe = len(surfedges)
                for j in range(4):
                    verts.append(ring[j])
                base = len(verts) - 4
                for j in range(4):
                    edges.append((base + j, base + (j + 1) % 4))
                    surfedges.append(len(edges) - 1)
                ti = sides[bi * (7 if bevel else 6) + k][1]
                dfaces.append((pi, 0, 0, fe, 4, ti, -1, -1, b"\0" * 4, -1, 0.0, 0, 0, 0, 0, -1, 0, 0, 0))
            model_range.append((first_face, len(dfaces) - first_face))
    texdata = [(0.5, 0.5, 0.5, i, 64, 64, 64, 64) for i in range(len(materials))]
    leaf_fmt = "<ihh6h4Hh24x2x" if version <= 19 else "<ihh6h4Hh2x"
    # leaf 0: the world's brushes; leaf 1: the entity's
    leafs = [(1, 0, 0, -16384, -16384, -16384, 16384, 16384, 16384, 0, 0, 0, nworld, -1)]
    leafbrushes = list(range(nworld))
    nwf = sum(n for _f, n in model_range[:nworld]) if faces else 0
    models = [(-16384, -16384, -16384, 16384, 16384, 16384, 0, 0, 0, -1, 0, nwf)]
    if entity_box:
        leafs.append((1, 0, 0, -1, -1, -1, 1, 1, 1, 0, 0, nworld, 1, -1))
        leafbrushes.append(nworld)
        x0, y0, z0, x1, y1, z1 = entity_box
        models.append((x0, y0, z0, x1, y1, z1, 0, 0, 0, -2, nwf, len(dfaces) - nwf))
    lumps = {
        0: _ents(entities),
        1: b"".join(struct.pack("<4fi", *p) for p in planes),
        2: b"".join(struct.pack("<3f5i", *t) for t in texdata),
        3: b"".join(struct.pack("<3f", *v) for v in verts) if faces else b"",
        7: b"".join(struct.pack("<HBBihhhh4sifiiiiiHHI", *f) for f in dfaces),
        12: b"".join(struct.pack("<2H", *e) for e in edges) if faces else b"",
        13: b"".join(struct.pack("<i", e) for e in surfedges),
        6: b"".join(struct.pack("<16f2i", *t) for t in texinfo),
        10: b"".join(struct.pack(leaf_fmt, *l) for l in leafs),
        14: b"".join(struct.pack("<9f3i", *m) for m in models),
        17: b"".join(struct.pack("<H", i) for i in leafbrushes),
        18: b"".join(struct.pack("<3i", *b) for b in brushes),
        19: b"".join(struct.pack("<H3h", *s) for s in sides),
        35: game_lump or b"",
        43: strings,
        44: b"".join(struct.pack("<i", o) for o in table),
    }
    header = 8 + LUMPS * 16 + 4
    if static_props is not None:
        # a `sprp` game lump (v4, 60-byte records) whose directory points at its own data,
        # which sits right after the 20-byte directory inside lump 35
        names = sorted({p[0] for p in static_props})
        data = struct.pack("<i", len(names)) + b"".join(n.encode().ljust(128, b"\0") for n in names)
        data += struct.pack("<i", 0) + struct.pack("<i", len(static_props))
        for model, org, ang in static_props:
            data += struct.pack("<3f3fHHHBBi", *org, *ang, names.index(model), 0, 0, 6, 0, 0).ljust(60, b"\0")
        before = sum(len(v) + (-len(v) % 4) for k, v in sorted(lumps.items()) if k < 35 and v)
        ofs = header + before + 20
        game_lump = struct.pack("<i", 1) + struct.pack("<4sHHii", b"prps", 0, 4, ofs, len(data)) + data
        lumps[35] = game_lump
    body, recs = b"", []
    for i in range(LUMPS):
        data = lumps.get(i, b"")
        off = header + len(body) if data else 0
        recs.append((off, len(data), 0))
        body += data + b"\0" * (-len(data) % 4)
    out = struct.pack("<4si", b"VBSP", version)
    for off, ln, v in recs:
        out += struct.pack("<iii4s", v, off, ln, b"\0" * 4) if swapped else struct.pack("<iii4s", off, ln, v, b"\0" * 4)
    out += struct.pack("<i", 7)
    return out + body
