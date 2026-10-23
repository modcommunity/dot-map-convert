"""Source models (mdl + vvd + vtx) as triangles, and their materials: the map's own props.

A map packs the models it places in its pakfile, so the geometry is in the source and nothing
has to be guessed from the file name. Reads studio format v44 to v49, LOD 0, body group 0
(the default of each body part) and the dx90 strip list; skinning is ignored (a prop is
static). Output is in game metres and Godot axes like `mesh.py`; `write_glb` stores one.
Standard library only. Models are the author's work: they go to the raw store, never into a
shipped map repository.
"""

import json
import struct

from . import units

VERTEX_BYTES = 48


def _cstr(d, off):
    end = d.find(b"\0", off)
    return d[off:end if end >= 0 else len(d)].decode("latin-1")


class ModelError(ValueError):
    pass


class Model:
    """`name`, `hull` (min, max in source units), `materials` [vmt path stems with cdmaterials
    applied, lower case] and `meshes` [(material index, [(x, y, z, nx, ny, nz, u, v)] , [i, i, i...])]."""

    def __init__(self, name, hull, materials, meshes, cdmaterials=()):
        self.name, self.hull, self.materials, self.meshes = name, hull, materials, meshes
        self.cdmaterials = list(cdmaterials)

    def material_paths(self, pak):
        """Each material's vmt path inside the pakfile (`pak` any container of lower-case names),
        trying every cdmaterials directory; the bare name when none of them holds it."""
        out = []
        for m in self.materials:
            hit = next((d + "/" + m for d in self.cdmaterials if "materials/%s/%s.vmt" % (d, m) in pak), None)
            out.append(hit or m)
        return out

    def triangles(self):
        return sum(len(i) // 3 for _, _, i in self.meshes)

    def bounds(self, scale=units.VISUAL):
        """(min, max) in metres and Godot axes over the drawn vertices."""
        pts = [v for _, vs, _ in self.meshes for v in vs]
        if not pts:
            return None
        lo = [min(p[k] for p in pts) for k in range(3)]
        hi = [max(p[k] for p in pts) for k in range(3)]
        return ([lo[0] * scale, lo[2] * scale, -hi[1] * scale], [hi[0] * scale, hi[2] * scale, -lo[1] * scale])


def parse(mdl, vvd, vtx):
    """A `Model` from the three files' bytes; raises `ModelError` on anything it does not read."""
    if len(mdl) < 240 or mdl[:4] != b"IDST":
        raise ModelError("not a studio model")
    ver = struct.unpack_from("<i", mdl, 4)[0]
    if not 44 <= ver <= 49:
        raise ModelError("studio version %d" % ver)
    name = _cstr(mdl, 12)
    hull = (list(struct.unpack_from("<3f", mdl, 104)), list(struct.unpack_from("<3f", mdl, 116)))
    ntex, texi, ncd, cdi, nskinref, nfam, skini, nbody, bodyi = (struct.unpack_from("<i", mdl, o)[0] for o in (204, 208, 212, 216, 220, 224, 228, 232, 236))
    cds = []
    for i in range(ncd):
        o = struct.unpack_from("<i", mdl, cdi + 4 * i)[0]
        cds.append(_cstr(mdl, o).lower().replace("\\", "/").strip("/"))
    texnames = []
    for i in range(ntex):
        base = texi + 64 * i
        texnames.append(_cstr(mdl, base + struct.unpack_from("<i", mdl, base)[0]).lower().replace("\\", "/"))
    skin0 = list(struct.unpack_from("<%dh" % nskinref, mdl, skini)) if nskinref and nfam else list(range(ntex))

    def material(skin_slot):
        t = skin0[skin_slot] if skin_slot < len(skin0) else skin_slot
        n = texnames[t] if t < len(texnames) else ""
        return n  # resolved against cdmaterials below

    # vvd
    if len(vvd) < 64 or vvd[:4] != b"IDSV":
        raise ModelError("not a vertex file")
    nfix, fixi, vdata = (struct.unpack_from("<i", vvd, o)[0] for o in (48, 52, 56))
    nlod0 = struct.unpack_from("<i", vvd, 16)[0]
    if nfix:
        verts = []
        for i in range(nfix):
            lod, src, n = struct.unpack_from("<3i", vvd, fixi + 12 * i)
            verts.append((src, n))
        order = [s for src, n in verts for s in range(src, src + n)]
    else:
        order = list(range(nlod0))
    raw = [struct.unpack_from("<8f", vvd, vdata + VERTEX_BYTES * s + 16) for s in order]  # pos, normal, uv

    # vtx
    if len(vtx) < 36:
        raise ModelError("not a strip file")
    vver, _, _, _, _, _, nlods, _, nbp, bpo = struct.unpack_from("<iihhiiiiii", vtx, 0)
    if vver != 7:
        raise ModelError("strip version %d" % vver)
    meshes = []
    for bp in range(nbody):
        bo = bodyi + 16 * bp
        nmodels = struct.unpack_from("<i", mdl, bo + 4)[0]
        modelidx = struct.unpack_from("<i", mdl, bo + 12)[0]
        if nmodels < 1:
            continue
        mo = bo + modelidx  # model 0
        nmesh, meshidx = struct.unpack_from("<ii", mdl, mo + 72)
        vidx = struct.unpack_from("<i", mdl, mo + 84)[0]
        mstart = vidx // VERTEX_BYTES
        vbp = bpo + 8 * bp
        vnm, vmo = struct.unpack_from("<ii", vtx, vbp)
        if vnm < 1:
            continue
        vm = vbp + vmo
        _, lodo = struct.unpack_from("<ii", vtx, vm)
        nvmesh, vmeshoff = struct.unpack_from("<ii", vtx, vm + lodo)
        for mi in range(min(nmesh, nvmesh)):
            mm = mo + meshidx + 116 * mi
            mat, = struct.unpack_from("<i", mdl, mm)
            moffset = struct.unpack_from("<i", mdl, mm + 12)[0]
            vmm = vm + lodo + vmeshoff + 9 * mi
            nsg, sgo = struct.unpack_from("<ii", vtx, vmm)
            verts_out, idx_out, remap = [], [], {}
            for si in range(nsg):
                sg = vmm + sgo + 25 * si
                nv, vo, ni, io, nstrip, stripo = struct.unpack_from("<6i", vtx, sg)
                gv = [struct.unpack_from("<H", vtx, sg + vo + 9 * k + 4)[0] for k in range(nv)]
                gi = struct.unpack_from("<%dH" % ni, vtx, sg + io)
                for st in range(nstrip):
                    sp = sg + stripo + 27 * st
                    sni, sio, _, _, _, flags = struct.unpack_from("<iiiihB", vtx, sp)
                    ids = gi[sio:sio + sni]
                    if flags & 2:   # a strip, not a list: alternate winding
                        tri = []
                        for k in range(len(ids) - 2):
                            a, b, c = ids[k], ids[k + 1], ids[k + 2]
                            tri += [a, b, c] if k % 2 == 0 else [b, a, c]
                        ids = tri
                    for a in ids:
                        g = mstart + moffset + gv[a]
                        if g not in remap:
                            if g >= len(raw):
                                raise ModelError("vertex %d beyond %d" % (g, len(raw)))
                            remap[g] = len(verts_out)
                            verts_out.append(raw[g])
                        idx_out.append(remap[g])
            if idx_out:
                meshes.append((mat, verts_out, idx_out))
    mats = [material(s) for s in range(max([m for m, _, _ in meshes] + [-1]) + 1)]
    return Model(name, hull, mats, meshes, cds)


def _norm_tri(vs, idx):
    """Flip winding when the stored normals say the triangles face the wrong way."""
    agree = 0
    for k in range(0, len(idx) - 2, 3):
        a, b, c = (vs[idx[k + j]] for j in range(3))
        e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        agree += n[0] * (a[3] + b[3] + c[3]) + n[1] * (a[4] + b[4] + c[4]) + n[2] * (a[5] + b[5] + c[5]) > 0
    return agree * 2 < len(idx) // 3


def to_glb(model, textures=None, scale=units.VISUAL):
    """The model as one binary glTF in metres and Godot axes. `textures` {material index: png bytes}."""
    textures = textures or {}
    buf = bytearray()
    views, accs, prims, images, mats = [], [], [], [], []
    mat_of = {}

    def view(data, target=None):
        while len(buf) % 4:
            buf.append(0)
        views.append({"buffer": 0, "byteOffset": len(buf), "byteLength": len(data), **({"target": target} if target else {})})
        buf.extend(data)
        return len(views) - 1

    for mat, vs, idx in model.meshes:
        flip = _norm_tri(vs, idx)
        pos, nor, uv = bytearray(), bytearray(), bytearray()
        lo, hi = [1e9] * 3, [-1e9] * 3
        for x, y, z, nx, ny, nz, u, v in vs:
            p = (x * scale, z * scale, -y * scale)
            for k in range(3):
                lo[k], hi[k] = min(lo[k], p[k]), max(hi[k], p[k])
            pos += struct.pack("<3f", *p)
            nor += struct.pack("<3f", nx, nz, -ny)
            uv += struct.pack("<2f", u, v)
        ind = list(idx)
        if flip:
            for k in range(0, len(ind) - 2, 3):
                ind[k + 1], ind[k + 2] = ind[k + 2], ind[k + 1]
        iv = view(struct.pack("<%dI" % len(ind), *ind), 34963)
        a = {}
        for key, data, n, typ in (("POSITION", pos, len(vs), "VEC3"), ("NORMAL", nor, len(vs), "VEC3"), ("TEXCOORD_0", uv, len(vs), "VEC2")):
            vi = view(bytes(data), 34962)
            accs.append({"bufferView": vi, "componentType": 5126, "count": n, "type": typ,
                         **({"min": lo, "max": hi} if key == "POSITION" else {})})
            a[key] = len(accs) - 1
        accs.append({"bufferView": iv, "componentType": 5125, "count": len(ind), "type": "SCALAR"})
        if mat not in mat_of:
            m = {"name": model.materials[mat] if mat < len(model.materials) else "material%d" % mat,
                 "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.9}, "doubleSided": True}
            if mat in textures:
                images.append({"bufferView": view(textures[mat]), "mimeType": "image/png"})
                m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(images) - 1}
            mats.append(m)
            mat_of[mat] = len(mats) - 1
        prims.append({"attributes": a, "indices": len(accs) - 1, "material": mat_of[mat]})
    doc = {"asset": {"version": "2.0", "generator": "dotbsp.mdl"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"mesh": 0, "name": model.name}], "meshes": [{"primitives": prims}],
           "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": len(buf)}], "materials": mats}
    if images:
        doc["images"] = images
        doc["textures"] = [{"source": i} for i in range(len(images))]
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    while len(buf) % 4:
        buf.append(0)
    total = 12 + 8 + len(js) + 8 + len(buf)
    return (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON") + js
            + struct.pack("<I4s", len(buf), b"BIN\0") + bytes(buf))
