"""A map's precomputed visibility, kept for the renderer: clusters, the PVS, areas and portals, occluders.

The compiler splits a map's empty space into leaves, groups leaves into clusters and stores, per
cluster, the set of clusters anything could be seen from it (the potentially visible set, run-length
compressed). Areas are regions the mapper sealed with area portals; a closed portal (a shut door)
hides every area only reachable through it. Discarding this costs every frame: the renderer draws
every chunk in the view cone, through every wall.

`attach(bsp, mesh)` (called by `mesh.build`) gives every surface the sorted clusters its triangles
touch (a box query through the BSP tree per triangle, so a face on a leaf boundary counts on both
sides and the set is never short), and `mesh.vis` the data the runtime (`DotMapVisibility`) needs:

- `planes` (nx, ny, nz, d in metres and Godot axes, n.p - d >= 0 is the front), `nodes` (plane,
  front child, back child; a child below 0 is leaf -1 - child), `leaf_cluster`, `leaf_area`;
- `pvs`: the file's own compressed rows, `pvs_offsets` into them (-1: none), `cluster_area`;
- `portals`: (key, area a, area b) and `portal_entities` (key, targetname of the door it follows,
  start open, window), so a game closes a portal when its door shuts;
- `occluders`: triangles of the large opaque world brushes, shrunk a little inside the brush, for
  an `OccluderInstance3D` on maps with no PVS or between clusters that do see each other.

A map compiled without visibility has no rows (`clusters` 0) and the runtime draws everything.
"""

import math
import struct

from . import reader

LUMP_VISIBILITY, LUMP_AREAS, LUMP_AREAPORTALS = 4, 20, 21
CONTENTS_TRANSLUCENT = 0x10000000
SURF_TRANS = 0x10
# Faces of these kinds are not drawn opaque (or at all), so a brush carrying one is never an occluder.
SEE_THROUGH_FLAGS = SURF_TRANS | reader.SURF_SKY | reader.SURF_SKY2D | reader.SURF_TRIGGER
SEE_THROUGH_GENERIC = ("glass", "foliage_card", "water", "fence", "grate", "chainlink", "bars", "ladder", "shield", "invisible")
# An occluder is a brush whose two larger extents are at least this (metres), and is pulled this far inside.
OCCLUDER_MIN_SIDE = 1.5
OCCLUDER_MIN_AREA = 6.0
OCCLUDER_SHRINK = 0.04
BOX_EPSILON = 1.0          # map units added round each triangle's box: the format's plane tolerance


class Vis:
    """The visibility lumps of a loaded `reader.Bsp`, in the file's units."""

    def __init__(self, bsp):
        self.bsp = bsp
        raw = bsp._lump(LUMP_VISIBILITY)
        self.clusters = struct.unpack_from("<i", raw, 0)[0] if len(raw) >= 4 else 0
        if self.clusters < 0 or 4 + 8 * self.clusters > len(raw):
            self.clusters = 0
        self.raw = raw
        self.offsets = [struct.unpack_from("<i", raw, 4 + 8 * c)[0] for c in range(self.clusters)]
        self.head = bsp.models[0][9] if bsp.models else -1
        self.areas = bsp._array(LUMP_AREAS, "<2i")
        self.areaportals = bsp._array(LUMP_AREAPORTALS, "<4Hi")

    def row(self, cluster):
        """The decompressed PVS of one cluster as a bytearray bitset."""
        n = (self.clusters + 7) // 8
        out = bytearray(n)
        off = self.offsets[cluster] if 0 <= cluster < self.clusters else -1
        if off < 0 or off >= len(self.raw):
            return bytearray(b"\xff" * n)
        p, o = off, 0
        while o < n and p < len(self.raw):
            b = self.raw[p]
            if b:
                out[o] = b
                o += 1
                p += 1
            else:
                o += self.raw[p + 1] if p + 1 < len(self.raw) else n
                p += 2
        return out

    def compact_rows(self):
        """(bytes, offsets): the PVS rows alone, still compressed; the lump's audible sets are dropped."""
        n = (self.clusters + 7) // 8
        out, offs, seen = bytearray(), [], {}
        for c in range(self.clusters):
            p = self.offsets[c]
            if p < 0 or p >= len(self.raw):
                offs.append(-1)
                continue
            if p in seen:
                offs.append(seen[p])
                continue
            start, o = p, 0
            while o < n and p < len(self.raw):
                if self.raw[p]:
                    o += 1
                    p += 1
                else:
                    o += self.raw[p + 1] if p + 1 < len(self.raw) else n
                    p += 2
            seen[start] = len(out)
            offs.append(len(out))
            out += self.raw[start:p]
        return bytes(out), offs

    def leaf_at(self, point):
        node = self.head
        while node >= 0:
            n = self.bsp.nodes[node]
            pl = self.bsp.planes[n[0]]
            node = n[1] if pl[0] * point[0] + pl[1] * point[1] + pl[2] * point[2] - pl[3] >= 0 else n[2]
        return -1 - node

    def leaves_in_box(self, lo, hi):
        c = [(lo[i] + hi[i]) * 0.5 for i in range(3)]
        h = [(hi[i] - lo[i]) * 0.5 for i in range(3)]
        out, stack = [], [self.head]
        nodes, planes = self.bsp.nodes, self.bsp.planes
        while stack:
            node = stack.pop()
            if node < 0:
                out.append(-1 - node)
                continue
            n = nodes[node]
            pl = planes[n[0]]
            d = pl[0] * c[0] + pl[1] * c[1] + pl[2] * c[2] - pl[3]
            r = abs(pl[0]) * h[0] + abs(pl[1]) * h[1] + abs(pl[2]) * h[2]
            if d > -r:
                stack.append(n[1])
            if d < r:
                stack.append(n[2])
        return out

    def clusters_in_box(self, lo, hi):
        leafs = self.bsp.leafs
        return {leafs[i][1] for i in self.leaves_in_box(lo, hi) if 0 <= i < len(leafs) and leafs[i][1] >= 0}


def _to_map(p, scale, y0):
    return (p[0] / scale, -p[2] / scale, (p[1] + y0) / scale)


def surface_clusters(v, s, scale, y0):
    """Sorted clusters a surface's triangles touch, or None for one drawn everywhere (the 3D sky)."""
    if s.sky3d:
        return None
    seen, out = set(), set()
    for t in range(0, len(s.index), 3):
        pts = [_to_map(s.verts[s.index[t + k]][0], scale, y0) for k in range(3)]
        lo = tuple(min(q[i] for q in pts) - BOX_EPSILON for i in range(3))
        hi = tuple(max(q[i] for q in pts) + BOX_EPSILON for i in range(3))
        key = (round(lo[0]), round(lo[1]), round(lo[2]), round(hi[0]), round(hi[1]), round(hi[2]))
        if key in seen:
            continue
        seen.add(key)
        out |= v.clusters_in_box(lo, hi)
    return sorted(out)


def _brush_occludes(bsp, bi, tmap, classify):
    first, count, contents = bsp.brushes[bi]
    if not contents & reader.CONTENTS_SOLID or contents & (reader.CONTENTS_WINDOW | reader.CONTENTS_GRATE | CONTENTS_TRANSLUCENT):
        return False
    drawn = False
    for side in bsp.brushsides[first:first + count]:
        if side[3]:
            continue
        name, flags = bsp.side_material(side)
        if flags & SEE_THROUGH_FLAGS:
            return False
        if name.upper().startswith("TOOLS/"):
            continue
        drawn = True
        if tmap is not None:
            hit = tmap.lookup(classify(name))
            if hit is not None and any(k in hit[0] for k in SEE_THROUGH_GENERIC):
                return False
    return drawn


def _hull_points(planes):
    pts = []
    n = len(planes)
    for i in range(n - 2):
        a = planes[i]
        for j in range(i + 1, n - 1):
            b = planes[j]
            for k in range(j + 1, n):
                c = planes[k]
                cx, cy, cz = a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]
                det = c[0] * cx + c[1] * cy + c[2] * cz
                if abs(det) < 1e-9:
                    continue
                bx, by, bz = b[1] * c[2] - b[2] * c[1], b[2] * c[0] - b[0] * c[2], b[0] * c[1] - b[1] * c[0]
                ax, ay, az = c[1] * a[2] - c[2] * a[1], c[2] * a[0] - c[0] * a[2], c[0] * a[1] - c[1] * a[0]
                p = ((a[3] * bx + b[3] * ax + c[3] * cx) / det, (a[3] * by + b[3] * ay + c[3] * cy) / det,
                     (a[3] * bz + b[3] * az + c[3] * cz) / det)
                if all(q[0] * p[0] + q[1] * p[1] + q[2] * p[2] - q[3] <= 1e-3 for q in planes):
                    pts.append(p)
    return pts


def _hull_triangles(planes, pts):
    """Triangles of a convex hull, wound so the plane normal faces out, from its planes and corners."""
    tris = []
    for (nx, ny, nz, d) in planes:
        face = [p for p in pts if abs(nx * p[0] + ny * p[1] + nz * p[2] - d) < 2e-3]
        uniq = list(dict.fromkeys((round(p[0], 4), round(p[1], 4), round(p[2], 4)) for p in face))
        if len(uniq) < 3:
            continue
        c = [sum(p[i] for p in uniq) / len(uniq) for i in range(3)]
        # an in-plane basis: u any vector perpendicular to n, w = n x u
        u = (ny, -nx, 0.0) if abs(nz) < 0.9 else (0.0, nz, -ny)
        ln = math.sqrt(sum(x * x for x in u)) or 1.0
        u = [x / ln for x in u]
        w = (ny * u[2] - nz * u[1], nz * u[0] - nx * u[2], nx * u[1] - ny * u[0])
        uniq.sort(key=lambda p: math.atan2(sum((p[i] - c[i]) * w[i] for i in range(3)),
                                           sum((p[i] - c[i]) * u[i] for i in range(3))))
        for k in range(1, len(uniq) - 1):
            # counter-clockwise about n when seen from outside; Godot's front face is clockwise
            tris.append((uniq[0], uniq[k + 1], uniq[k]))
    return tris


def occluders(bsp, mesh, tmap=None, classify=None):
    """(vertices, indices) of the large opaque world brushes, in metres and Godot axes."""
    verts, index, lookup = [], [], {}
    for h in mesh.hulls:
        if h["model"] != 0 or h["kind"] != "solid":
            continue
        xs = [p[0] for p in h["points"]]
        ys = [p[1] for p in h["points"]]
        zs = [p[2] for p in h["points"]]
        ext = sorted((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))
        if ext[1] < OCCLUDER_MIN_SIDE or ext[1] * ext[2] < OCCLUDER_MIN_AREA:
            continue
        if not _brush_occludes(bsp, h["brush"], tmap, classify):
            continue
        shrink = min(OCCLUDER_SHRINK, ext[0] * 0.25)
        planes = [(nx, ny, nz, d - shrink) for (nx, ny, nz, d) in h["planes"]]
        pts = _hull_points(planes)
        for tri in _hull_triangles(planes, pts):
            for p in tri:
                k = lookup.get(p)
                if k is None:
                    k = lookup[p] = len(verts)
                    verts.append(p)
                index.append(k)
    return verts, index


def attach(bsp, mesh, tmap=None, classify=None):
    """Fill `surface.clusters` and `mesh.vis` from the map's visibility lumps; a map with none gets
    clusters 0, no per-surface sets, and its occluders all the same."""
    v = Vis(bsp)
    scale, y0 = mesh.scale, mesh.y0
    data = {"clusters": v.clusters}
    if v.clusters > 0 and v.head >= 0:
        for s in mesh.surfaces:
            s.clusters = surface_clusters(v, s, scale, y0)
        # n.p >= d in map units; with p = (x/s, -z/s, (y+y0)/s): (nx, nz, -ny).p' >= d*s - nz*y0
        data["planes"] = [(pl[0], pl[2], -pl[1], pl[3] * scale - pl[2] * y0) for pl in bsp.planes]
        data["nodes"] = [(n[0], n[1], n[2]) for n in bsp.nodes]
        data["leaf_cluster"] = [l[1] for l in bsp.leafs]
        data["leaf_area"] = [l[2] & 0x1FF for l in bsp.leafs]
        data["head"] = v.head
        area = [0] * v.clusters
        for l in bsp.leafs:
            if 0 <= l[1] < v.clusters:
                area[l[1]] = l[2] & 0x1FF
        data["cluster_area"] = area
        data["pvs"], data["pvs_offsets"] = v.compact_rows()
        pairs = {}
        for a, (count, first) in enumerate(v.areas):
            for ap in v.areaportals[first:first + count]:
                key, other = ap[0], ap[1]
                pairs[(key, min(a, other), max(a, other))] = True
        data["portals"] = sorted(pairs)
        ents = []
        for e in bsp.entities:
            cls = e.get("classname", "")
            if cls in ("func_areaportal", "func_areaportalwindow") and str(e.get("portalnumber", "")).strip().isdigit():
                ents.append({"key": int(e["portalnumber"]), "target": e.get("target", ""),
                             "start_open": str(e.get("StartOpen", "1")).strip() != "0",
                             "window": cls == "func_areaportalwindow"})
        data["portal_entities"] = ents
    data["occluder_vertices"], data["occluder_indices"] = occluders(bsp, mesh, tmap, classify)
    mesh.vis = data
    return data


def pack(data, blob):
    """Append `data`'s arrays to `blob`; returns the manifest's `vis` record (offsets into the blob)."""
    rec = {"clusters": data.get("clusters", 0)}

    def put(key, fmt, rows, width):
        flat = [x for r in rows for x in r] if width > 1 else list(rows)
        rec[key] = {"offset": len(blob), "count": len(rows)}
        blob.extend(struct.pack("<%d%s" % (len(flat), fmt), *flat))

    if rec["clusters"] > 0:
        rec["head"] = data["head"]
        put("planes", "f", data["planes"], 4)
        put("nodes", "i", data["nodes"], 3)
        put("leaf_cluster", "i", data["leaf_cluster"], 1)
        put("leaf_area", "i", data["leaf_area"], 1)
        put("cluster_area", "i", data["cluster_area"], 1)
        put("pvs_offsets", "i", data["pvs_offsets"], 1)
        rec["pvs"] = {"offset": len(blob), "count": len(data["pvs"])}
        blob.extend(data["pvs"])
        rec["portals"] = [list(p) for p in data["portals"]]
        rec["portal_entities"] = data["portal_entities"]
    if data.get("occluder_indices"):
        put("occluder_vertices", "f", data["occluder_vertices"], 3)
        put("occluder_indices", "I", data["occluder_indices"], 1)
    return rec
