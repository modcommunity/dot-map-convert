"""Ship the library models a world draws inside its own pack.

`licence.model_store` points at a shared folder (`../../model-library`) that exists on a developer's disk and in no
delivered pack, so a client drew those props as boxes or not at all. `bundle_world` copies a world folder and exactly the
model files its manifest names into `<out>/models/`, and points `model_store` there; `DotMapBspMesh` finds it beside the mesh.
`bsp.py bundle` runs it for many worlds; a world with no model rows is copied unchanged.
"""
import json
import os
import shutil


def _manifest(folder):
    name = os.path.basename(os.path.normpath(folder))
    return os.path.join(folder, name + ".json"), name


def bundle_world(folder, out, store=None):
    """Copy world `folder` to `out` with its models. Returns (copied, missing) lists of store_file paths."""
    path, name = _manifest(folder)
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    lic = doc.get("licence", {})
    root = store or os.path.normpath(os.path.join(folder, lic.get("model_store", "model-library")))
    files = sorted({r["store_file"] for r in lic.get("model_stand_ins", []) if r.get("store_file")})
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(folder, out, ignore=shutil.ignore_patterns("models"))
    copied, missing = [], []
    for rel in files:
        src = os.path.join(root, rel)
        if not os.path.isfile(src):
            missing.append(rel)
            continue
        dst = os.path.join(out, "models", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if rel.lower().endswith(".gltf"):
            # A .gltf names its .bin and textures beside it; copy the model's folder, not the one file.
            shutil.copytree(os.path.dirname(src), os.path.dirname(dst), dirs_exist_ok=True)
        else:
            shutil.copyfile(src, dst)
        copied.append(rel)
    if files:
        lic["model_store"] = "models"
        with open(os.path.join(out, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
    return copied, missing


def cmd(args):
    bad = 0
    for folder in args.worlds:
        name = os.path.basename(os.path.normpath(folder))
        copied, missing = bundle_world(folder, os.path.join(args.out, name), args.store)
        size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(os.path.join(args.out, name, "models")) for f in fs)
        print("%s: %d models, %.1f MB%s" % (name, len(copied), size / 1e6, ", MISSING %d: %s" % (len(missing), ", ".join(missing[:3])) if missing else ""))
        bad += len(missing)
    return 1 if bad and args.strict else 0
