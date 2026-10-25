"""The shared PBR and model stores of converted maps as dot-cloud content.

A map's manifest names the texture sets (`licence.textures`, kind pbr, with `tier`) and library models
(`licence.model_stand_ins`, `store_file`) it draws. `slice_for` copies exactly those out of the stores into a Godot
project folder, writes the import settings (VRAM-compressed textures: S3TC and ETC2 are both produced, so a web build
has both and a desktop or phone client fetches its own), and `version_of` names the slice by a hash of what it holds.
`bsp.py storepack` imports the project with the engine, publishes each slice with dot-cloud (`--depends` on a map's pack
names it) and stamps the slice into the map manifests (`licence.store_pack`). Files are content addressed by dot-cloud,
so two slices that share a texture download it once on one client: the "shared store" is the object cache, not a
second copy per map.
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


def slice_for(docs, pbr_store, model_store, dest, vram=True):
    """Copies what `docs` (manifests) draw into the folder `dest`, with import markers. Returns the file list
    (slice-relative, sorted). Existing files are kept, so building another slice into the same project is cheap."""
    pbr, models = set(), {}
    for doc in docs:
        p, m = needs(doc)
        pbr |= p
        models.update(m)
    files = []
    os.makedirs(dest, exist_ok=True)    # a map that draws no stored art (Raven Street) still gets its credits.json

    def put(src, rel, normal=False, marker=True):
        out = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if not os.path.isfile(out) or os.path.getsize(out) != os.path.getsize(src):
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
    return sorted(files)


def version_of(dest, files, vram=True):
    """`h` plus eight hex digits of the sha256 over every file's name, size and content hash: the same slice
    always has the same version, so republishing it is a no-op and a pack's dependency never moves."""
    h = hashlib.sha256(b"vram" if vram else b"lossless")
    for rel in files:
        if rel.endswith(".import"):
            continue
        with open(os.path.join(dest, rel), "rb") as f:
            h.update(("%s %s\n" % (rel, hashlib.sha256(f.read()).hexdigest())).encode())
    return "h" + h.hexdigest()[:8]


def run_cmd(args):
    """`bsp.py storepack`: one slice per map (or `--combined`), imported by the engine once, published, stamped."""
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.abspath(args.out)
    packs = [os.path.abspath(p) for p in args.packs]
    docs = []
    for p in packs:
        mp = os.path.join(p, "manifest.json") if os.path.isdir(p) else p
        with open(mp) as f:
            docs.append((mp, json.load(f)))
    groups = [("combined", docs)] if args.combined else [(os.path.basename(os.path.dirname(mp)), [(mp, d)]) for mp, d in docs]
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "project.godot"), "w") as f:
        f.write(PROJECT)
    built = []
    for name, items in groups:
        first = items[0][1]["licence"]
        base = os.path.dirname(items[0][0])
        pbr_store = os.path.normpath(os.path.join(base, first.get("pbr_store", "../pbr-library")))
        model_store = os.path.normpath(os.path.join(base, first.get("model_store", "../model-library")))
        dest = os.path.join(out, SLICE_DIR, name)
        files = slice_for([d for _, d in items], pbr_store, model_store, dest, vram=not args.lossless)
        built.append((name, items, dest, files))
        print("storepack: %s: %d files" % (name, len(files)))
    if args.dry_run:
        return 0
    godot = args.godot or "godot"
    subprocess.run([godot, "--headless", "--path", out, "--import"], check=True, timeout=1800, stdout=subprocess.DEVNULL)
    if not os.path.isfile(os.path.join(args.cloud, ".godot", "global_script_class_cache.cfg")):
        subprocess.run([godot, "--headless", "--path", args.cloud, "--import"], check=True, timeout=1800, stdout=subprocess.DEVNULL)
    cli = os.path.join(args.cloud, "addons/dot_cloud/publish/dot_cloud_cli.gd")
    for name, items, dest, files in built:
        version = version_of(dest, files, vram=not args.lossless)
        sid = slice_id(args.owner, args.prefix + name)
        dist = os.path.join(args.dist, sid.replace("/", "_"), version)
        cmd = [godot, "--headless", "--path", args.cloud, "--script", cli, "--", "publish", "--source", dest, "--out", dist,
               "--id", sid, "--version", version]
        if args.key:
            cmd += ["--key", args.key]
        subprocess.run(cmd, check=True, timeout=1800)
        for mp, _ in items:
            if stamp(mp, sid, version):
                print("storepack: stamped %s -> %s@%s" % (mp, sid, version))
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


def stamp(manifest_path, store_id, version):
    """Writes `licence.store_pack` ({id, version}) into a map manifest; returns whether it changed."""
    with open(manifest_path) as f:
        doc = json.load(f)
    pack = {"id": store_id, "version": version}
    if doc["licence"].get("store_pack") == pack:
        return False
    doc["licence"]["store_pack"] = pack
    with open(manifest_path, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    return True
