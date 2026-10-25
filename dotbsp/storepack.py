"""The shared PBR and model stores of converted maps as dot-cloud content.

A map's manifest names the texture sets (`licence.textures`, kind pbr, with `tier`) and library models
(`licence.model_stand_ins`, `store_file`) it draws. `slice_for` copies exactly those out of the stores into a Godot
project folder, writes the import settings (VRAM-compressed textures: S3TC and ETC2 are both produced, so a web build
has both and a desktop or phone client fetches its own), and `version_of` names the slice by a hash of what it holds.
`bsp.py storepack` imports the project with the engine, publishes each slice with dot-cloud (`--depends` on a map's pack
names it) and stamps the slice into the map manifests (`licence.store_pack`).

Sharing: an item (a PBR set or a model) used by the same group of maps travels together, so `plan` cuts the items by
the set of maps that draw them. A group that is among the `shared` biggest of any of its maps becomes its own slice
(`store-shared-<hash of the maps>`), which every map in the group depends on; the rest stays in each map's own slice.
A map's slice (`store_pack`, the root) declares its shared slices as manifest `dependencies`; dot-cloud takes at most
eight per manifest, so more go through empty group nodes (`<map>-g<level>-<n>`). A client that has downloaded map A
then fetches only the shared slices of map B it lacks.
"""
import hashlib
import json
import os
import shutil

from . import licence

MODEL_EXT = (".glb", ".gltf", ".bin", ".png", ".jpg", ".jpeg", ".webp", ".ktx2")
TEXTURE_EXT = (".webp", ".jpg", ".jpeg", ".png")
MAPS = ("albedo", "normal", "roughness", "ao")
SLICE_DIR = "slices"

PROJECT = """config_version=5

[application]
config/name="dot-map store"

[rendering]
renderer/rendering_method="gl_compatibility"
textures/vram_compression/import_s3tc_bptc=true
textures/vram_compression/import_etc2_astc=true
"""

IMPORT_TEXTURE = """[remap]

importer="texture"
type="CompressedTexture2D"

[params]

compress/mode=%(mode)d
compress/high_quality=false
compress/lossy_quality=0.7
compress/uastc_level=0
compress/rdo_quality_loss=0.0
compress/hdr_compression=1
compress/normal_map=%(normal)d
compress/channel_pack=0
mipmaps/generate=true
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/channel_remap/red=0
process/channel_remap/green=1
process/channel_remap/blue=2
process/channel_remap/alpha=3
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=0
"""


def needs(doc):
    """(pbr, models) a manifest draws: pbr is {(set id, tier)}, models {store_file: row}."""
    block = doc.get("licence", {})
    pbr = {(os.path.basename(t["file"]), t.get("tier", "1k")) for t in block.get("textures", []) if t["kind"] == "pbr"}
    models = {r["store_file"]: r for r in block.get("model_stand_ins", []) if r.get("store_file")}
    return pbr, models


def write_import(path, vram=True, normal=False):
    """The `.import` marker for a texture, so the engine's import makes it VRAM-compressed (or lossless when asked)."""
    with open(path + ".import", "w") as f:
        f.write(IMPORT_TEXTURE % {"mode": 2 if vram else 0, "normal": 1 if normal else 0})


def _model_files(store, rel):
    """Every file a library model needs, relative to the store: a glTF goes with its folder, a glb with its textures."""
    src = os.path.join(store, rel)
    if rel.endswith(".gltf"):
        base = os.path.dirname(src)
        return [os.path.relpath(os.path.join(d, f), store) for d, _, fs in os.walk(base) for f in fs if f.lower().endswith(MODEL_EXT)]
    out = [rel]
    tex = os.path.join(os.path.dirname(src), "Textures")
    if os.path.isdir(tex):
        out += [os.path.relpath(os.path.join(d, f), store) for d, _, fs in os.walk(tex) for f in fs if f.lower().endswith(MODEL_EXT)]
    return out


def slice_for(docs, pbr_store, model_store, dest, vram=True, only=None, credits=True):
    """Copies what `docs` (manifests) draw into the folder `dest`, with import markers. Returns the file list
    (slice-relative, sorted). Existing files are kept, so building another slice into the same project is cheap.
    [param only] limits it to those items (`("p", set id, tier)` and `("m", store_file)`); `credits=False` leaves out credits.json."""
    pbr, models = set(), {}
    for doc in docs:
        p, m = needs(doc)
        pbr |= p
        models.update(m)
    if only is not None:
        pbr = {(sid, tier) for sid, tier in pbr if ("p", sid, tier) in only}
        models = {k: v for k, v in models.items() if ("m", k) in only}
    files = []
    os.makedirs(dest, exist_ok=True)    # a map that draws no stored art (Raven Street) still gets its credits.json

    def put(src, rel, normal=False, marker=True):
        out = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if not os.path.isfile(out) or _digest(out) != _digest(src):
            shutil.copyfile(src, out)
        files.append(rel)
        if marker and rel.lower().endswith(TEXTURE_EXT):
            write_import(out, vram, normal)

    for sid, tier in sorted(pbr):
        for name in MAPS:
            for ext in (".webp", ".jpg"):
                src = os.path.join(pbr_store, sid, tier, name + ext)
                if os.path.isfile(src):
                    put(src, "pbr/%s/%s/%s%s" % (sid, tier, name, ext), normal=(name == "normal"))
                    break
    for rel in sorted(models):
        for f in _model_files(model_store, rel):
            put(os.path.join(model_store, f), "models/" + f, marker=False)
    if credits:
        works = []
        for doc in docs:
            works += licence.credits_list(doc)
        merged = {}
        for w in works:
            k = (w["kind"], w["url"] or w["name"])
            merged.setdefault(k, w)
        with open(os.path.join(dest, "credits.json"), "w") as f:
            json.dump({"works": list(merged.values())}, f, indent=1)
            f.write("\n")
        files.append("credits.json")
    _prune(dest, files)
    return sorted(files)


def _digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _prune(dest, files):
    """Deletes what a previous build left in `dest` that this one does not draw, so the folder is exactly
    `files` (plus their `.import` markers) and the version hash covers everything that gets published."""
    keep = set(files) | {f + ".import" for f in files}
    for d, _, fs in os.walk(dest, topdown=False):
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), dest).replace(os.sep, "/")
            if rel not in keep:
                os.remove(os.path.join(d, f))
        if d != dest and not os.listdir(d):
            os.rmdir(d)


def version_of(dest, files, vram=True, deps=()):
    """`h` plus eight hex digits of the sha256 over every file's name, size and content hash (and the `id@version`
    of each dependency): the same slice always has the same version, so republishing it is a no-op and a pack's
    dependency never moves."""
    h = hashlib.sha256(b"vram" if vram else b"lossless")
    for d in deps:
        h.update(("dep %s@%s\n" % (d["id"], d["version"])).encode())
    for rel in files:
        if rel.endswith(".import"):
            continue
        with open(os.path.join(dest, rel), "rb") as f:
            h.update(("%s %s\n" % (rel, hashlib.sha256(f.read()).hexdigest())).encode())
    return "h" + h.hexdigest()[:8]


def item_bytes(pbr_store, model_store, item):
    """Source size of one item, to rank slices (the imported size follows it closely)."""
    def du(path):
        return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(path) for f in fs)
    if item[0] == "p":
        return du(os.path.join(pbr_store, item[1], item[2]))
    return sum(os.path.getsize(os.path.join(model_store, f)) for f in _model_files(model_store, item[1]))


def items_of(doc):
    """The items a manifest draws: `("p", set id, tier)` and `("m", store_file)`."""
    pbr, models = needs(doc)
    return {("p", sid, tier) for sid, tier in pbr} | {("m", k) for k in models}


def plan(wants, sizes, shared=8):
    """Cuts the items of every map by the group of maps that draw them. [param wants] is {map: items}, [param sizes]
    {item: bytes}. Returns (shared, private): shared is {frozenset(maps): items} for each group that is among the
    [param shared] biggest groups of any of its maps (a group of one map is never shared), private {map: items} the rest."""
    users = {}
    for m, items in wants.items():
        for it in items:
            users.setdefault(it, set()).add(m)
    groups = {}
    for it, ms in users.items():
        groups.setdefault(frozenset(ms), []).append(it)
    weight = {g: sum(sizes[i] for i in its) for g, its in groups.items()}
    chosen = set()
    for m in wants:
        mine = sorted((g for g in groups if m in g and len(g) > 1), key=lambda g: (-weight[g], sorted(g)))
        chosen.update(mine[:shared])
    shared_out = {g: sorted(groups[g]) for g in chosen}
    private = {m: sorted(it for g, its in groups.items() if m in g and g not in chosen for it in its) for m in wants}
    return shared_out, private


def shared_name(maps):
    return "shared-" + hashlib.sha1(",".join(sorted(maps)).encode()).hexdigest()[:8]


MAX_DEPENDENCIES = 8    # dot-cloud's per-manifest cap; a chain may be four deep


def chunk_tree(leaves, fan=MAX_DEPENDENCIES):
    """Levels of group nodes above [param leaves] until the top fits one manifest: [] when it already does, else
    [[(node index, its children)...] bottom level first]. Children are indexes into the level below ('l' = leaves)."""
    levels = []
    count = len(leaves)
    while count > fan:
        nodes = [list(range(i, min(i + fan, count))) for i in range(0, count, fan)]
        levels.append(nodes)
        count = len(nodes)
    return levels


def publish_slice(args, godot, cli, sid, version, dest, deps):
    """Publishes one slice into `args.dist` unless that version already is there."""
    import subprocess
    dist = os.path.join(args.dist, sid.replace("/", "_"), version)
    if os.path.isfile(os.path.join(dist, "manifest.json")):
        return
    cmd = [godot, "--headless", "--path", args.cloud, "--script", cli, "--", "publish", "--source", dest, "--out", dist,
           "--id", sid, "--version", version]
    for d in deps:
        cmd += ["--depends", "%s@%s" % (d["id"], d["version"])]
    if args.key:
        cmd += ["--key", args.key]
    subprocess.run(cmd, check=True, timeout=1800, stdout=subprocess.DEVNULL)


def run_cmd(args):
    """`bsp.py storepack`: shared slices for what several maps draw plus one root slice per map (or `--combined`, or
    `--shared 0` for one self-contained slice per map), imported by the engine once, published, stamped."""
    import subprocess
    out = os.path.abspath(args.out)
    packs = [os.path.abspath(p) for p in args.packs]
    docs = []
    for p in packs:
        mp = os.path.join(p, "manifest.json") if os.path.isdir(p) else p
        with open(mp) as f:
            docs.append((mp, json.load(f)))
    groups = {"combined": docs} if args.combined else {os.path.basename(os.path.dirname(mp)): [(mp, d)] for mp, d in docs}
    first = docs[0][1]["licence"]
    base = os.path.dirname(docs[0][0])
    pbr_store = os.path.normpath(os.path.join(base, first.get("pbr_store", "../pbr-library")))
    model_store = os.path.normpath(os.path.join(base, first.get("model_store", "../model-library")))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "project.godot"), "w") as f:
        f.write(PROJECT)
    vram = not args.lossless
    wants = {name: set().union(*(items_of(d) for _, d in items)) for name, items in groups.items()}
    sizes = {it: item_bytes(pbr_store, model_store, it) for its in wants.values() for it in its}
    shared, private = plan(wants, sizes, args.shared)
    # (slice dir name, docs it draws for, items or None, credits, who it is for)
    built = []
    for g, its in sorted(shared.items(), key=lambda kv: shared_name(kv[0])):
        name = shared_name(g)
        dest = os.path.join(out, SLICE_DIR, name)
        every = [d for n in g for _, d in groups[n]]
        files = slice_for(every, pbr_store, model_store, dest, vram=vram, only=set(its), credits=False)
        built.append(("shared", name, dest, files, g))
        print("storepack: %s: %d files, %d maps, %.1f MiB source" % (name, len(files), len(g), sum(sizes[i] for i in its) / 1048576.0))
    for name, items in groups.items():
        dest = os.path.join(out, SLICE_DIR, name)
        files = slice_for([d for _, d in items], pbr_store, model_store, dest, vram=vram, only=set(private[name]))
        built.append(("root", name, dest, files, frozenset([name])))
        print("storepack: %s: %d files (own)" % (name, len(files)))
    if args.dry_run:
        return 0
    godot = args.godot or "godot"
    subprocess.run([godot, "--headless", "--path", out, "--import"], check=True, timeout=3600, stdout=subprocess.DEVNULL)
    if not os.path.isfile(os.path.join(args.cloud, ".godot", "global_script_class_cache.cfg")):
        subprocess.run([godot, "--headless", "--path", args.cloud, "--import"], check=True, timeout=1800, stdout=subprocess.DEVNULL)
    cli = os.path.join(args.cloud, "addons/dot_cloud/publish/dot_cloud_cli.gd")
    version_of_shared = {}
    for kind, name, dest, files, g in built:
        if kind != "shared":
            continue
        sid = slice_id(args.owner, args.prefix + name)
        version = version_of(dest, files, vram=vram)
        publish_slice(args, godot, cli, sid, version, dest, [])
        version_of_shared[g] = {"id": sid, "version": version}
    for kind, name, dest, files, g in built:
        if kind != "root":
            continue
        leaves = [version_of_shared[x] for x in sorted(version_of_shared, key=shared_name) if name in x]
        top = list(leaves)
        for li, level in enumerate(chunk_tree(leaves, MAX_DEPENDENCIES)):
            nxt = []
            for ni, kids in enumerate(level):
                ndeps = [top[k] for k in kids]
                ndest = os.path.join(out, SLICE_DIR, "%s-g%d-%d" % (name, li + 1, ni))
                os.makedirs(ndest, exist_ok=True)
                with open(os.path.join(ndest, "group.json"), "w") as f:
                    json.dump({"dependencies": ndeps}, f, indent=1)
                    f.write("\n")
                nid = slice_id(args.owner, "%s%s-g%d-%d" % (args.prefix, name, li + 1, ni))
                nver = version_of(ndest, ["group.json"], vram=vram, deps=ndeps)
                publish_slice(args, godot, cli, nid, nver, ndest, ndeps)
                nxt.append({"id": nid, "version": nver})
            top = nxt
        sid = slice_id(args.owner, args.prefix + name)
        version = version_of(dest, files, vram=vram, deps=top)
        publish_slice(args, godot, cli, sid, version, dest, top)
        for mp, _ in groups[name]:
            if stamp(mp, sid, version, leaves):
                print("storepack: stamped %s -> %s@%s (+%d shared)" % (mp, sid, version, len(leaves)))
    saved = link_objects(args.dist)
    print("storepack: hardlinked %.1f MiB of objects shared between slices" % (saved / 1048576.0))
    return 0


def link_objects(dist):
    """Hardlink identical content-addressed objects across every published slice under `dist`, so a set two maps draw is stored once."""
    seen = {}
    saved = 0
    for root, _, names in os.walk(dist):
        if os.sep + "objects" + os.sep not in root + os.sep:
            continue
        for n in names:
            p = os.path.join(root, n)
            first = seen.setdefault(n, p)
            if first == p or os.path.samefile(first, p):
                continue
            size = os.path.getsize(p)
            tmp = p + ".lnk"
            os.link(first, tmp)
            os.replace(tmp, p)
            saved += size
    return saved


def slice_id(owner, name):
    """The dot-cloud content id of a slice: `<owner>/<name>`, each part lowercase letters, digits, - and _."""
    def slug(s):
        return "".join(c if (c.isalnum() or c == "_") else "-" for c in s.lower()).strip("-")
    return "%s/%s" % (slug(owner), slug(name))


def stamp(manifest_path, store_id, version, shared=()):
    """Writes `licence.store_pack` ({id, version, shared: [{id, version}]}) into a map manifest; returns whether it changed.
    `shared` lists every shared slice the root pulls in, flat, for `DotMapStore.apply`."""
    with open(manifest_path) as f:
        doc = json.load(f)
    pack = {"id": store_id, "version": version}
    if shared:
        pack["shared"] = [{"id": d["id"], "version": d["version"]} for d in shared]
    if doc["licence"].get("store_pack") == pack:
        return False
    doc["licence"]["store_pack"] = pack
    with open(manifest_path, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    return True
