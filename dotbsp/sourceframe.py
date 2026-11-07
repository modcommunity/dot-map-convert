"""The frame a box document was drawn in, recorded in the document so an audit need not recover it.

The box importers shift a map so its origin stands on open ground (and may crop it with --bounds). That shift is
what `tools/audit_maps.py` used to find by correlating footprints. `record()` writes it into the document as the
optional top-level field `source_frame`; a reader that does not know the field ignores it:

    "source_frame": {
      "map": "ph_house.bsp",          # the source map's file name
      "sha256": "...",                # of its bytes, so an audit can tell it is the same map
      "scale": 0.01905,               # metres per source unit
      "offset": [x, y, z],            # game metres to ADD to a document coordinate to land on the source's
      "crop": [x0, z0, x1, z1],       # --bounds as an audit --within rectangle (source game metres), or null
      "crop_band": [y0, y1],          # --bounds' height range (source game metres), or null
      "bounds": [x0, y0, z0, x1, y1, z1]   # the finished world's extent, in the source's game metres
    }

"Source game metres" are `audit.to_game(p, scale)` of a source point: (x, z, -y) times the scale.
"""
import hashlib
import math
import os

FIELD = "source_frame"


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def crop_of(bounds, scale):
    """(crop rectangle, band) in source game metres from --bounds `x0,y0,z0,x1,y1,z1` (source units, z up)."""
    if not bounds:
        return None, None
    x0, y0, z0, x1, y1, z1 = bounds
    return ([round(x0 * scale, 3), round(-y1 * scale, 3), round(x1 * scale, 3), round(-y0 * scale, 3)],
            [round(z0 * scale, 3), round(z1 * scale, 3)])


def extent(doc):
    """[x0, y0, z0, x1, y1, z1] of the solid boxes in the document's own frame, or None."""
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for b in doc.get("boxes") or []:
        if b.get("solid") is False:
            continue
        yaw = math.radians(b.get("yaw", 0) or 0)
        sx, sy, sz = b["size"]
        hx = (abs(math.cos(yaw)) * sx + abs(math.sin(yaw)) * sz) / 2
        hz = (abs(math.sin(yaw)) * sx + abs(math.cos(yaw)) * sz) / 2
        for k, h in enumerate((hx, sy / 2, hz)):
            lo[k] = min(lo[k], b["at"][k] - h)
            hi[k] = max(hi[k], b["at"][k] + h)
    return None if lo[0] == math.inf else lo + hi


def record(doc, bsp_path, scale, shift, bounds=None):
    """Set doc["source_frame"]. `shift` is what the importer SUBTRACTED from the source's game metres (x, y, z);
    call it after the last move of the boxes. Returns the field."""
    off = [round(float(v), 5) for v in shift]
    ext = extent(doc)
    crop, band = crop_of(bounds, scale)
    doc[FIELD] = {
        "map": os.path.basename(bsp_path),
        "sha256": file_sha256(bsp_path),
        "scale": round(scale, 6),
        "offset": off,
        "crop": crop,
        "crop_band": band,
        "bounds": None if ext is None else [round(ext[k] + off[k % 3], 3) for k in range(6)],
    }
    return doc[FIELD]


def read(doc):
    """The recorded frame, or None when the document has none or it is malformed."""
    f = doc.get(FIELD) if isinstance(doc, dict) else None
    if not isinstance(f, dict):
        return None
    off = f.get("offset")
    if not (isinstance(off, list) and len(off) == 3 and all(isinstance(v, (int, float)) for v in off)):
        return None
    return f
