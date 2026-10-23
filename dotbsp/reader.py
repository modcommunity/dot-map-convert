"""Read a compiled BSP map (the VBSP format, versions 19 to 21) far enough to convert it.

This is the one reader every game's map converter uses. It started as game-g2gfast's
`tools/bsp_read.py`, which six repositories carried as byte-identical copies, and it keeps
that file's names (`Bsp`, `to_godot`, `clean_material`, the `CONTENTS_*` and `SURF_*`
constants) so a converter written against the old copy imports this unchanged.

Coordinates stay as the file stores them: Z-up, in map units (0.75 inch, so 1 unit is
0.01905 m). Converting is the caller's choice, because the games disagree on purpose: the
surf game is authored in map units, the box games in metres, the course game at an inch a
unit. `to_godot` only swaps the axes; `to_metres` swaps and scales.

Everything here is a fact about the file. Decisions (which brush is a ramp, which spawn is
which team, what a material looks like) belong to `boxes.py`, `intermediate.py` or the game.
"""

import io
import lzma
import math
import re
import struct
import zipfile

# Surface flags worth skipping when drawing. Tool textures are the compiler's own
# annotations, not geometry a player sees.
SURF_SKY2D, SURF_SKY, SURF_TRIGGER, SURF_NODRAW = 0x2, 0x4, 0x40, 0x80
SURF_HINT, SURF_SKIP = 0x100, 0x200
SKIP_MASK = SURF_SKY2D | SURF_SKY | SURF_TRIGGER | SURF_NODRAW | SURF_HINT | SURF_SKIP

LUMP_ENTITIES, LUMP_PLANES, LUMP_TEXDATA, LUMP_VERTEXES = 0, 1, 2, 3
LUMP_NODES, LUMP_TEXINFO, LUMP_FACES, LUMP_LIGHTING = 5, 6, 7, 8
LUMP_LEAFS, LUMP_EDGES, LUMP_SURFEDGES, LUMP_MODELS = 10, 12, 13, 14
LUMP_LEAFBRUSHES, LUMP_BRUSHES, LUMP_BRUSHSIDES = 17, 18, 19
LUMP_DISPINFO, LUMP_DISP_VERTS, LUMP_GAME, LUMP_PAKFILE = 26, 33, 35, 40
LUMP_TEXDATA_STRING_DATA, LUMP_TEXDATA_STRING_TABLE = 43, 44

HEADER_BYTES = 8 + 64 * 16 + 4      # ident, version, 64 lump records, map revision
METRES_PER_UNIT = 0.01905

# What a player collides with, which is not what a player can see.
#
# [b]A map's solid volume is its brushes; its drawn faces are only the ones that happened
# to stay visible.[/b] The compiler deletes every face it can prove nobody can look at, and
# a mapper paints the rest invisible on purpose (player clips are invisible by definition
# and are the whole reason a ramp is smooth to ride). Measured over eight maps, between 31%
# and 77% of the sides of a solid brush are not drawn, so collision built from drawn faces
# is a shell with most of itself missing.
#
# The mask is the format's player-solid mask. GRATE and WINDOW are in it because a player
# cannot walk through a grille or a pane; WATER, AREAPORTAL and a MONSTERCLIP that is not
# also PLAYERCLIP are not, because a player walks through all three.
CONTENTS_SOLID, CONTENTS_WINDOW, CONTENTS_GRATE = 0x1, 0x2, 0x8
CONTENTS_SLIME, CONTENTS_WATER = 0x10, 0x20
CONTENTS_MOVEABLE, CONTENTS_PLAYERCLIP, CONTENTS_MONSTERCLIP = 0x4000, 0x10000, 0x20000
CONTENTS_MONSTER, CONTENTS_DETAIL, CONTENTS_LADDER = 0x2000000, 0x8000000, 0x20000000
MASK_PLAYERSOLID = (CONTENTS_SOLID | CONTENTS_WINDOW | CONTENTS_GRATE
                    | CONTENTS_MOVEABLE | CONTENTS_PLAYERCLIP | CONTENTS_MONSTER)

# Which brush entities are solid, by classname, because their contents cannot say.
#
# [b]A trigger_teleport's brushes carry CONTENTS_SOLID.[/b] Hundreds of them do in a surf
# map (the pits, the one volume that must not be solid), and so do func_illusionary and
# func_dustcloud. The engine never asks the contents alone: it asks the entity what it is.
# So does this. A classname in neither list is the caller's to report, because the
# alternative to a note is an invisible wall nobody can explain.
SOLID_BRUSH_ENTITIES = frozenset("""
    func_brush func_wall func_wall_toggle func_detail func_breakable
    func_breakable_surf func_button func_rot_button func_door func_door_rotating
    func_movelinear func_water_analog func_conveyor func_train func_tracktrain
    func_tanktrain func_rotating func_platrot func_plat func_lod func_physbox
    func_physbox_multiplayer func_pushable func_monitor func_reflective_glass
    func_clip_vphysics
""".split())

NONSOLID_BRUSH_ENTITIES = frozenset("""
    func_illusionary func_dustcloud func_dustmotes func_smokevolume
    func_precipitation func_areaportal func_areaportalwindow func_occluder
    func_viscluster func_ladder func_bomb_target func_buyzone func_hostage_rescue
    func_nav_blocker func_instance_io_proxy func_fish_pool func_vehicleclip
    trigger_vphysics_motion env_bubbles env_wind func_wall_illusionary
""".split())

# dnode_t and dleaf_t, both 32 bytes from v20 on; v19 carried a light cube inline and
# measured 56, which is why the leaf format is chosen by version (see `load`).
FMT_NODE = "<i2i6h2Hh2x"        # planenum, children[2], mins[3], maxs[3], face range, area
FMT_LEAF = "<ihh6h4Hh2x"        # contents, cluster, area/flags, mins/maxs, face and brush ranges
FMT_LEAF_V19 = "<ihh6h4Hh24x2x" # the same plus the 24-byte light cube and the 2-byte pad: 56
FMT_BRUSH = "<3i"               # firstside, numsides, contents
FMT_BRUSHSIDE = "<H3h"          # planenum, texinfo, dispinfo, bevel

# dmodel_t is 48 bytes. Read as 9f4i (52) model 0 still comes out right (every field
# before the overrun is in place) and every model after it is garbage, so the world draws
# perfectly while every trigger volume is wrong. The sizes came out negative, which is the
# only reason it showed.
FMT_MODEL = "<9f3i"
FMT_FACE = "<HBBihhhh4sifiiiiiHHI"   # 56 bytes
FMT_TEXINFO = "<16f2i"               # 72
FMT_TEXDATA = "<3f5i"                # 32
FMT_DISPVERT = "<3fff"               # 20

# Spawn classes the family's games read, and the team each means. A converter that wants
# a different reading takes `Bsp.entities` itself; this is only the common case.
SPAWN_CLASSES = {
    "info_player_start": "any", "info_player_deathmatch": "any",
    "info_player_terrorist": "red", "info_player_counterterrorist": "blue",
    "info_player_teamspawn": "any", "info_player_combine": "blue", "info_player_rebel": "red",
    "info_player_human": "survivors", "info_player_zombie": "zombies",
    "info_player_zombie_boss": "zombies",
}
LIGHT_CLASSES = frozenset(("light", "light_spot", "light_environment", "light_dynamic"))


class Bsp:
    def __init__(self, path=None, data=None):
        """Open a map from a path, or from bytes already read (an archive member)."""
        self.path = path or "<bytes>"
        self.d = data if data is not None else open(path, "rb").read()
        if len(self.d) < HEADER_BYTES:
            raise ValueError("%s is too short to be a BSP file" % self.path)
        ident, self.version = struct.unpack_from("<4si", self.d, 0)
        if ident != b"VBSP":
            raise ValueError("%s is not a VBSP file (magic %r)" % (self.path, ident))
        if not 17 <= self.version <= 21:
            raise ValueError("%s is VBSP v%d; this reader knows v19 to v21" % (self.path, self.version))
        self.revision = struct.unpack_from("<i", self.d, 8 + 64 * 16)[0]
        self.dir = self._directory()
        self._cache = {}

    def _directory(self):
        """The 64 lump records as (offset, length, version).

        [b]One v21 family stores a record as version, offset, length; the other keeps the
        v20 order.[/b] Nothing in the header says which, so both readings are tried and the
        one whose every lump lies inside the file, past the header, wins. Reading the wrong
        one does not fail: it slices plausible bytes from the wrong place.
        """
        raw = [struct.unpack_from("<iii4s", self.d, 8 + i * 16)[:3] for i in range(64)]
        plain = [(a, b, c) for a, b, c in raw]
        swapped = [(b, c, a) for a, b, c in raw]

        def fits(recs):
            for off, ln, _v in recs:
                if ln == 0:
                    continue
                if ln < 0 or off < HEADER_BYTES or off + ln > len(self.d):
                    return False
            return True

        if self.version >= 21 and not fits(plain) and fits(swapped):
            return swapped
        # Anything else reads as v20 always has: a truncated download still yields the lumps
        # that are whole, and the one that is not fails where it is used, by name.
        return plain

    def _lump(self, i):
        if i in self._cache:
            return self._cache[i]
        off, ln, _ = self.dir[i]
        out = decompress_lump(self.d[off:off + ln])
        self._cache[i] = out
        return out

    def _array(self, i, fmt):
        b, sz = self._lump(i), struct.calcsize(fmt)
        return [struct.unpack_from(fmt, b, o) for o in range(0, len(b) - sz + 1, sz)]

    def truncated(self):
        """Lump numbers whose record points past the end of the file (a cut-off download)."""
        return [i for i, (off, ln, _v) in enumerate(self.dir) if ln > 0 and off + ln > len(self.d)]

    def load(self):
        # [b]A cut-off file converts to an empty map without this[/b]: every lump past the cut
        # reads as zero bytes, so 0 brushes and 0 entities came back with no error. Helix's
        # deathrun map arrived as a 4 MB piece of a 23 MB file and looked like a reader crash.
        cut = self.truncated()
        if cut:
            raise ValueError("%s is cut off: lumps %s run past the end of its %d bytes (an incomplete download or extraction)"
                             % (self.path or "bsp", cut[:8], len(self.d)))
        # normal(3f), dist(f), type(i). Kept for exact face normals: a brush face lies on
        # its plane by construction, so a normal from the winding is strictly worse.
        self.planes = self._array(LUMP_PLANES, "<4fi")
        self.verts = self._array(LUMP_VERTEXES, "<3f")
        self.edges = self._array(LUMP_EDGES, "<2H")
        self.surfedges = [x[0] for x in self._array(LUMP_SURFEDGES, "<i")]
        self.texinfo = self._array(LUMP_TEXINFO, FMT_TEXINFO)
        self.texdata = self._array(LUMP_TEXDATA, FMT_TEXDATA)
        self.faces = self._array(LUMP_FACES, FMT_FACE)
        self.models = self._array(LUMP_MODELS, FMT_MODEL)
        self.dispinfo = self._lump(LUMP_DISPINFO)
        self.dispverts = self._array(LUMP_DISP_VERTS, FMT_DISPVERT)
        table = [x[0] for x in self._array(LUMP_TEXDATA_STRING_TABLE, "<i")]
        data = self._lump(LUMP_TEXDATA_STRING_DATA)
        # [b]Latin-1, not ASCII.[/b] The string table is the mapper's Windows codepage, and a
        # map naming its textures `customs/Früchte/...` decoded as ASCII got U+FFFD for the ü,
        # matched no pakfile entry, and drew 15% of itself in the prototype grid. Latin-1 maps
        # every byte and agrees with cp1252 on every letter a material name uses.
        self.texnames = [data[o:data.index(b"\0", o)].decode("latin-1") for o in table]
        self.entities = parse_entities(self._lump(LUMP_ENTITIES).decode("ascii", "replace"))
        self.brushes = self._array(LUMP_BRUSHES, FMT_BRUSH)
        self.brushsides = self._array(LUMP_BRUSHSIDES, FMT_BRUSHSIDE)
        self.leafbrushes = [x[0] for x in self._array(LUMP_LEAFBRUSHES, "<H")]
        self.nodes = self._array(LUMP_NODES, FMT_NODE)
        # [b]Leaf size by the file's version, not by which size the lump divides by.[/b] A
        # v19 lump whose leaf count is a multiple of four divides by 32 too; read as v20,
        # every leaf after the first was garbage and so were the brushes reached through
        # them. And the first v19 format was 54 bytes, two short, which is how a v19 lump
        # that did NOT divide by 32 failed to import at all.
        raw = len(self._lump(LUMP_LEAFS))
        fmt = FMT_LEAF_V19 if self.version <= 19 else FMT_LEAF
        if raw % struct.calcsize(fmt):
            raise ValueError("leaf lump of %d bytes is neither v19 nor v20 shaped" % raw)
        self.leafs = self._array(LUMP_LEAFS, fmt)
        return self

    # -- faces -----------------------------------------------------------
    def face_material(self, f):
        ti = f[5]
        if ti < 0:
            return "?", 0
        flags, td = int(self.texinfo[ti][16]), int(self.texinfo[ti][17])
        if not 0 <= td < len(self.texdata):
            return "?", flags
        return self.texnames[self.texdata[td][3]], flags

    def side_material(self, side):
        """(material name, surface flags) of one brushside, ('?', 0) when it has none."""
        ti = side[1]
        if ti < 0 or ti >= len(self.texinfo):
            return "?", 0
        flags, td = int(self.texinfo[ti][16]), int(self.texinfo[ti][17])
        if not 0 <= td < len(self.texdata):
            return "?", flags
        return self.texnames[self.texdata[td][3]], flags

    def face_points(self, f):
        first, n = f[3], f[4]
        pts = []
        for k in range(n):
            se = self.surfedges[first + k]
            e = self.edges[abs(se)]
            pts.append(self.verts[e[0] if se >= 0 else e[1]])
        return pts

    def model_faces(self, model=0):
        m = self.models[model]
        return self.faces[m[10]:m[10] + m[11]]

    def model_bounds(self, model):
        m = self.models[model]
        return (m[0], m[1], m[2]), (m[3], m[4], m[5])

    # -- brushes: the solid volume, as opposed to the visible surface -----
    def model_brushes(self, model=0):
        """Every brush index belonging to one model, by walking its BSP tree.

        [b]There is no per-model brush range to slice.[/b] dmodel_t carries a headnode and
        nothing else about brushes; a brush belongs to a model because a leaf under that
        model's node reaches it through the leafbrush table. Model 0 is the world, including
        every func_detail the compiler merged into it; models 1..n are one brush entity each.
        """
        out, stack, seen = set(), [self.models[model][9]], set()
        while stack:
            n = stack.pop()
            if n < 0:
                i = -1 - n
                if 0 <= i < len(self.leafs):
                    leaf = self.leafs[i]
                    first, count = leaf[11], leaf[12]
                    out.update(self.leafbrushes[first:first + count])
                continue
            if n >= len(self.nodes) or n in seen:
                continue
            seen.add(n)
            stack.extend(self.nodes[n][1:3])
        return out

    def brush_planes(self, index, offset=(0.0, 0.0, 0.0)):
        """The brush's real (non-bevel) sides as (nx, ny, nz, d), moved by `offset`.

        A brush entity's planes are relative to its origin; moving a plane by o adds n.o to
        its distance, which is how a converter places a func_door where the map put it.
        """
        first, count, _ = self.brushes[index]
        out = []
        for s in self.brushsides[first:first + count]:
            if s[3]:
                continue
            pl = self.planes[s[0]]
            out.append((pl[0], pl[1], pl[2],
                        pl[3] + pl[0] * offset[0] + pl[1] * offset[1] + pl[2] * offset[2]))
        return out

    def brush_hull(self, index, epsilon=0.1):
        """One brush as the corner points of its convex hull, in map coordinates.

        A brush is stored as the intersection of the half-spaces its sides lie on, with no
        vertices anywhere. The corners are the points where three planes meet that no fourth
        excludes: Cramer's rule over every triple of sides, kept when inside all the rest.

        [b]Bevel sides are skipped, and must be.[/b] The compiler adds axis-aligned bevel
        planes for its own box sweep; they are tangent to the hull and change no corner, and
        there can be more of them than real sides (16.5 sides a brush against about 6 real).
        Feeding them in costs the cube of that for nothing.

        `epsilon` is the format's own plane tolerance. The planes are float32 and the
        coordinates reach +/-16384, so an exact test drops corners on the hull by
        construction, and a hull missing a corner is a solid with a bite out of it.
        """
        first, count, _ = self.brushes[index]
        planes = []
        for s in self.brushsides[first:first + count]:
            if s[3]:                                    # bevel
                continue
            pl = self.planes[s[0]]
            planes.append((pl[0], pl[1], pl[2], pl[3]))
        n = len(planes)
        if n < 4:
            return []
        pts = []
        for i in range(n - 2):
            a = planes[i]
            for j in range(i + 1, n - 1):
                b = planes[j]
                cx = a[1] * b[2] - a[2] * b[1]
                cy = a[2] * b[0] - a[0] * b[2]
                cz = a[0] * b[1] - a[1] * b[0]
                for k in range(j + 1, n):
                    c = planes[k]
                    det = c[0] * cx + c[1] * cy + c[2] * cz
                    if -1e-6 < det < 1e-6:              # the three planes share a line
                        continue
                    bx = b[1] * c[2] - b[2] * c[1]
                    by = b[2] * c[0] - b[0] * c[2]
                    bz = b[0] * c[1] - b[1] * c[0]
                    ax = c[1] * a[2] - c[2] * a[1]
                    ay = c[2] * a[0] - c[0] * a[2]
                    az = c[0] * a[1] - c[1] * a[0]
                    x = (a[3] * bx + b[3] * ax + c[3] * cx) / det
                    y = (a[3] * by + b[3] * ay + c[3] * cy) / det
                    z = (a[3] * bz + b[3] * az + c[3] * cz) / det
                    for p in planes:
                        if p[0] * x + p[1] * y + p[2] * z - p[3] > epsilon:
                            break
                    else:
                        pts.append((round(x, 3), round(y, 3), round(z, 3)))
        # A corner where four planes meet (every bevelled edge, every wedge tip) comes out
        # once per triple. Duplicates are only waste, but a surf map has 2500 brushes.
        return list(dict.fromkeys(pts))

    def point_in_brush(self, index, point, epsilon=0.1):
        """True when a point is behind every side of a brush: the definition, not an estimate."""
        first, count, _ = self.brushes[index]
        for side in self.brushsides[first:first + count]:
            pl = self.planes[side[0]]
            if pl[0] * point[0] + pl[1] * point[1] + pl[2] * point[2] - pl[3] > epsilon:
                return False
        return True

    # -- displacements ---------------------------------------------------
    def displacement_tris(self, f, with_base=False, with_alpha=False):
        """A displacement's subdivided surface.

        The face is the flat quad the mapper drew; the real surface is a (2^power + 1)
        square grid of offsets from it. Drawing the quad instead deletes every piece of
        terrain in the map, including ramps players ride.

        `with_base` returns each point as (displaced, flat). The flat one is where a
        displacement's LIGHTING lives: its lightmap is parameterised over the drawn quad,
        so a lightmap coordinate projected from the displaced point runs off the face's
        luxel range by as much as the terrain bulges. `with_alpha` adds the vertex's blend
        alpha as 0..1 (0..255 on disk); it needs `with_base`.
        """
        o = f[6] * 176
        start = struct.unpack_from("<3f", self.dispinfo, o)
        vstart, _tstart, power = struct.unpack_from("<3i", self.dispinfo, o + 12)
        c = self.face_points(f)
        if len(c) != 4:
            return []
        # The grid is laid out from the corner nearest startPosition, which is not
        # necessarily the first vertex of the face winding.
        best = min(range(4), key=lambda k: sum((c[k][a] - start[a]) ** 2 for a in range(3)))
        c = c[best:] + c[:best]
        size = (1 << power) + 1
        grid = []
        for row in range(size):
            t = row / (size - 1)
            lft = [c[0][a] + (c[1][a] - c[0][a]) * t for a in range(3)]
            rgt = [c[3][a] + (c[2][a] - c[3][a]) * t for a in range(3)]
            for col in range(size):
                s = col / (size - 1)
                base = [lft[a] + (rgt[a] - lft[a]) * s for a in range(3)]
                dv = self.dispverts[vstart + row * size + col]
                point = tuple(base[a] + dv[a] * dv[3] for a in range(3))
                if with_alpha:
                    grid.append((point, tuple(base), min(max(dv[4] / 255.0, 0.0), 1.0)))
                else:
                    grid.append((point, tuple(base)) if with_base else point)
        tris = []
        for row in range(size - 1):
            for col in range(size - 1):
                a = row * size + col
                tris.append((grid[a], grid[a + size], grid[a + 1]))
                tris.append((grid[a + 1], grid[a + size], grid[a + size + 1]))
        return tris

    # -- game lumps, static props, the embedded zip ------------------------
    def game_lumps(self):
        """{four-character id: (version, bytes)} for every game lump the map has.

        [b]A map can carry an empty or cut-off game lump[/b] (compiled with no static props, or a
        file whose directory points past its end: Helix's deathrun map). Reading the count from
        zero bytes raised struct.error out of the whole conversion, and zombie-zone-maps worked
        round it by catching everything. Here a lump too short for its own directory, or an entry
        that points outside the file, costs that lump, never the map.
        """
        off, ln, _ = self.dir[LUMP_GAME]
        raw = self.d[off:off + ln] if ln > 0 and 0 <= off < len(self.d) else b""
        if len(raw) < 4:
            return {}
        count = struct.unpack_from("<i", raw, 0)[0]
        out = {}
        for i in range(max(0, min(count, (len(raw) - 4) // 16))):
            gid, _flags, version, fileofs, filelen = struct.unpack_from("<4sHHii", raw, 4 + 16 * i)
            if fileofs < 0 or filelen <= 0 or fileofs + filelen > len(self.d):
                continue
            data = self.d[fileofs:fileofs + filelen]
            if data[:4] == b"LZMA":
                try:
                    data = decompress_lump(data)
                except Exception:      # a bad LZMA stream costs this lump only
                    continue
            out[gid[::-1].decode("ascii", "replace")] = (version, data)
        return out

    def static_props(self):
        """Every static prop: {model, origin, angles, solid, skin, flags, lighting_origin, scale}.

        [b]Static props are not entities.[/b] They are compiled out of the entity lump into
        the `sprp` game lump, so a converter that reads only `entities` finds no prop_static
        at all, which in some maps is most of the furniture. The record grows with the lump
        version and every field read here is in the first 32 bytes of all of them, so the
        stride is taken from the lump (what is left over, divided by the count) rather than
        from a table of versions the next map would be missing.
        """
        lump = self.game_lumps().get("sprp")
        if lump is None:
            return []
        version, d = lump
        names_n = struct.unpack_from("<i", d, 0)[0]
        names = [d[4 + 128 * i:4 + 128 * (i + 1)].split(b"\0")[0].decode("ascii", "replace")
                 .replace("\\", "/").lower() for i in range(names_n)]
        o = 4 + 128 * names_n
        leaves = struct.unpack_from("<i", d, o)[0]
        o += 4 + 2 * leaves
        count = struct.unpack_from("<i", d, o)[0]
        o += 4
        if count <= 0:
            return []
        stride = (len(d) - o) // count
        props = []
        for i in range(count):
            q = o + i * stride
            origin = struct.unpack_from("<3f", d, q)
            angles = struct.unpack_from("<3f", d, q + 12)
            model, _first_leaf, _leaf_count, solid, flags = struct.unpack_from("<HHHBB", d, q + 24)
            skin = struct.unpack_from("<i", d, q + 32)[0]
            lighting = origin
            if version >= 4 and stride >= 60:
                lighting = struct.unpack_from("<3f", d, q + 44)
            scale = 1.0
            if version >= 11 and stride >= 76:
                scale = struct.unpack_from("<f", d, q + stride - 4)[0] or 1.0
            props.append({
                "model": names[model] if model < len(names) else "",
                "origin": origin, "angles": angles, "solid": solid, "skin": skin,
                "flags": flags,
                # STATIC_PROP_USE_LIGHTING_ORIGIN; a lighting origin that is not a number is
                # a field this version lays out differently, so the prop's own origin is used.
                "lighting_origin": lighting if flags & 0x2 and all(
                    math.isfinite(c) and abs(c) < 65536 for c in lighting) else origin,
                "scale": scale,
            })
        return props

    def pak_names(self):
        """The names of the files in the embedded zip, lowercased; [] when there is none."""
        off, ln, _ = self.dir[LUMP_PAKFILE]
        if not ln:
            return []
        try:
            z = zipfile.ZipFile(_View(self.d, off, ln))
        except zipfile.BadZipFile:
            return []
        return sorted(_pak_key(i).lower() for i in z.infolist())

    def read_pak(self, notes, only=None):
        """Every file in the embedded zip, by lowercased name; `only` is a tuple of suffixes to keep (a 1.7 GB pakfile fits in memory only when asked for what is used).

        [b]One entry at a time, and a broken one is missing rather than fatal.[/b] A map
        whose zip has a bad CRC on one soundscape nobody reads must not import as a
        traceback. A skipped entry goes in `notes`, because if it was a texture the map
        draws a stand-in and the note is the only thing that says why.
        """
        off, ln, _ = self.dir[LUMP_PAKFILE]
        if not ln:
            return {}
        try:
            z = zipfile.ZipFile(_View(self.d, off, ln))
        except zipfile.BadZipFile as e:
            notes.append("pakfile is unreadable (%s); every surface falls back to the "
                         "prototype grid" % e)
            return {}
        pak, bad = {}, []
        for info in z.infolist():
            if only and not _pak_key(info).lower().endswith(only):
                continue
            try:
                pak[_pak_key(info).lower()] = z.read(info)
            except (zipfile.BadZipFile, EOFError, OSError) as e:
                bad.append("%s (%s)" % (info.filename, e.__class__.__name__))
        if bad:
            notes.append("%d of %d pakfile entries could not be read and were skipped: %s"
                         % (len(bad), len(z.namelist()), ", ".join(sorted(bad)[:5])
                            + (" ..." if len(bad) > 5 else "")))
        return pak


class _View(io.RawIOBase):
    """A read-only file over a slice of a bytes object without copying it (a zip of a gigabyte pakfile)."""

    def __init__(self, data, off, ln):
        self._m, self._o, self._n, self._p = memoryview(data), off, ln, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self._p

    def seek(self, pos, whence=0):
        self._p = max(0, pos if whence == 0 else self._p + pos if whence == 1 else self._n + pos)
        return self._p

    def readinto(self, b):
        k = max(0, min(len(b), self._n - self._p))
        b[:k] = self._m[self._o + self._p:self._o + self._p + k]
        self._p += k
        return k


def _pak_key(info):
    # [b]A name the zip did not flag as UTF-8 is decoded by Python as cp437[/b], which turns
    # the mapper's codepage byte for ü into `ⁿ`, so it never matched the material name.
    # Re-read those bytes as Latin-1, as Bsp.texnames is.
    n = info.filename
    return n if info.flag_bits & 0x800 else n.encode("cp437").decode("latin-1")


def decompress_lump(raw):
    """A lump's bytes, decompressed if the map was compressed.

    [b]Many maps in circulation are LZMA-compressed and nothing in the header says so.[/b]
    Map hosts repack every lump as an `lzma_header_t` and a raw LZMA1 stream and leave the
    version alone, so a reader that does not check gets plausible garbage: three of eight
    maps parsed their planes happily and died in the texture string table, the first lump
    whose contents are checked against anything.

    The header is `LZMA`, the uncompressed size, the compressed size, and the five property
    bytes, so this is a raw LZMA1 stream with no end marker: FORMAT_RAW plus `max_length`.
    """
    if len(raw) < 17 or raw[:4] != b"LZMA":
        return raw
    actual, _packed = struct.unpack_from("<II", raw, 4)
    props = raw[12]
    dict_size = struct.unpack_from("<I", raw, 13)[0]
    pb, r = divmod(props, 45)
    lp, lc = divmod(r, 9)
    filters = [{"id": lzma.FILTER_LZMA1, "dict_size": max(4096, dict_size),
                "lc": lc, "lp": lp, "pb": pb}]
    dec = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=filters)
    # No end marker: the stream stops when `actual` bytes have come out, and asking for
    # more raises rather than returning what there was.
    return dec.decompress(raw[17:], max_length=actual)


def yaw_to_godot(yaw):
    """A map yaw as the yaw dot-player-controller builds a forward vector from.

    The map measures yaw anticlockwise about +Z from +X; DotFpsMotor.forward is
    (-sin y, 0, -cos y), and the axis swap has turned the map's +Y into Godot's -Z. Solving
    the two gives exactly `yaw - 90`. Getting it wrong shows in no number: the player
    stands in the right place facing the wrong way.
    """
    return float(yaw) - 90.0


def to_godot(p):
    """Map Z-up to Godot Y-up, in map units: (x, z, -y)."""
    return (p[0], p[2], -p[1])


def to_metres(p, scale=METRES_PER_UNIT):
    """Map Z-up to Godot Y-up, in metres (or whatever `scale` says a unit is)."""
    return (p[0] * scale, p[2] * scale, -p[1] * scale)


class Entity(dict):
    """One entity as the dict every reader uses, plus `pairs`: every key and value in file order."""

    pairs = ()


def parse_entities(text):
    """The entity lump as one `Entity` per entity.

    [b]An output key repeats, and every repeat is kept.[/b] A trigger that does two things
    on touch carries two OnTrigger keys, and a dict that kept only the first lost the second
    (32 traps imported as nothing). Repeats of an On* key are joined with newlines, which
    every reader of outputs already scans with a regex that stops at whitespace. Any other
    key keeps its first value in the dict; `pairs` keeps all of them, for outputs that are
    not named On* and for the lossless store.
    """
    out = []
    for blk in re.findall(r"\{([^{}]*)\}", text):
        kv = Entity()
        pairs = re.findall(r'"([^"]*)"\s*"([^"]*)"', blk)
        for k, v in pairs:
            if k in kv and k.startswith("On"):
                kv[k] += "\n" + v
            else:
                kv.setdefault(k, v)
        if kv:
            kv.pairs = pairs
            out.append(kv)
    return out


def entity_vec(e, key="origin", default=(0.0, 0.0, 0.0)):
    """A three-number key as floats; `default` when missing or unreadable."""
    try:
        v = [float(x) for x in e.get(key, "").split()][:3]
    except ValueError:
        return list(default)
    return v if len(v) == 3 else list(default)


DOOR_HINGE_REACH = 64.0     # source units (1.2 m): a hinge farther from the origin than a door is wide is a stale editor helper


def door_hinge(e):
    """Where a prop_door_rotating swings from, in source units: ([x, y, z], offset).

    The entity's origin is the model's, which for most models is the hinge. A door authored with a
    hinge axis (`axis`: two points) away from it has its model origin elsewhere on the panel (a
    stall door's origin is its middle), so the swing is about the axis. Only a vertical axis (or
    one point) counts; a horizontal axis, or a hinge farther away than a door is wide, is left
    on the origin. `offset` is the hinge-to-origin vector (x, y) when they differ by over a unit, else None."""
    o = entity_vec(e)
    try:
        pts = [[float(x) for x in part.split()][:3] for part in e.get("axis", "").split(",")]
    except ValueError:
        return o, None
    if not pts or any(len(p) != 3 for p in pts) or len(pts) > 2:
        return o, None
    if any(abs(p[0] - pts[0][0]) > 0.5 or abs(p[1] - pts[0][1]) > 0.5 for p in pts):
        return o, None
    dx, dy = o[0] - pts[0][0], o[1] - pts[0][1]
    d = math.hypot(dx, dy)
    if d <= 1.0 or d > DOOR_HINGE_REACH:
        return o, None
    return [pts[0][0], pts[0][1], o[2]], (dx, dy)


def entity_yaw(e):
    try:
        return float(e["angles"].split()[1])
    except (KeyError, ValueError, IndexError):
        return 0.0


def clean_material(m):
    """The base material name, lowercased.

    The compiler renames any material a cubemap patched to `maps/<mapname>/<path>_<x>_<y>_<z>`,
    so one texture appears under a dozen names; grouping by the raw string scatters a surface
    across the map. And the folder carries the map's own name, which must not decide a
    surface (a map called ph_school would match `school` in everything).

    [b]A leading `/` is dropped.[/b] A mapper who typed a root material with a slash gets
    `/SURFACE`, which the engine resolves; kept, the lookup missed and 97% of one map drew
    the prototype grid with its own textures in the pakfile the whole time.
    """
    m = m.lower().replace("\\", "/").lstrip("/")
    # The `_x_y_z` suffix is only the compiler's when it moved the material under `maps/`:
    # a mapper's own `corals_1_5_8_9` ends in three numbers too.
    patched = re.sub(r"^maps/[^/]+/", "", m)
    if patched == m:
        return m
    return re.sub(r"_-?\d+_-?\d+_-?\d+$", "", patched)
