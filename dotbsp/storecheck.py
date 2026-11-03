"""`bsp.py storecheck`: does a world pack draw its art from what is published, and nothing it cannot find?

A converted world names library PBR sets and models; it never carries them. They arrive as dot-cloud slices
(`licence.store_pack`, see storepack.py). A pack with no stamp, a slice that is not published, or a slice that lacks a
set the manifest names does not fail: the client draws the 64 px fallback albedo or a stand-in box, so the map looks
plausible and wrong (a yellow street, a box for a car). This reads the signed slice manifests (a `--dist` folder or a
published `--origin`), follows `dependencies` the way the client does, and lists every gap.
"""
import base64
import json
import os
import urllib.error
import urllib.request

# Cloudflare in front of the CDN answers 403 to Python's default agent.
USER_AGENT = "dot-map-convert-storecheck/1 (+https://github.com/modcommunity/dot-map-convert)"


class FetchError(Exception):
    """The slice could not be read for a reason other than 'not published' (403, 5xx, network)."""


def _payload(raw):
    doc = json.loads(raw)
    if "payload" not in doc:    # an unsigned dist/ manifest, written before dot-cloud publish signs it
        return doc
    p = doc["payload"]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))


def fetch(sid, version, dist=None, origin=None):
    """The decoded manifest payload of one slice, None when it is not there (404 / no file); FetchError otherwise."""
    if dist:
        try:
            with open(os.path.join(dist, sid.replace("/", "_"), version, "manifest.json"), "rb") as f:
                return _payload(f.read())
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError) as e:
            raise FetchError("%s@%s: %s" % (sid, version, e))
    url = "%s/content/%s/%s/manifest.json" % (origin.rstrip("/"), sid, version)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            return _payload(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise FetchError("%s@%s: HTTP %d from %s" % (sid, version, e.code, url))
    except (OSError, ValueError, KeyError) as e:
        raise FetchError("%s@%s: %s (%s)" % (sid, version, e, url))


def closure(pack, dist=None, origin=None, cache=None):
    """(file paths, missing 'id@version' list, fetch error list) of a root slice and every dependency below it."""
    cache = {} if cache is None else cache
    files, missing, errors, todo, seen = set(), [], [], [(pack["id"], pack["version"])], set()
    for s in pack.get("shared", []):
        todo.append((s["id"], s["version"]))
    while todo:
        key = todo.pop()
        if key in seen:
            continue
        seen.add(key)
        if key not in cache:
            try:
                cache[key] = fetch(key[0], key[1], dist, origin)
            except FetchError as e:
                cache[key] = e
        m = cache[key]
        if isinstance(m, FetchError):
            errors.append(str(m))
            continue
        if m is None:
            missing.append("%s@%s" % key)
            continue
        files.update(f["path"] for f in m.get("files", []))
        todo += [(d["id"], d["version"]) for d in m.get("dependencies", [])]
    return files, missing, errors


def check(doc, pack_dir, dist=None, origin=None, cache=None):
    """Problems of one world manifest (a list of strings; empty means everything it draws resolves)."""
    lic = doc.get("licence", {})
    bad = []
    pbr = [t for t in lic.get("textures", []) if t.get("kind") == "pbr"]
    models = [r for r in lic.get("model_stand_ins", []) if r.get("store_file")]
    keys = {t.get("key") for t in lic.get("textures", [])}
    for t in lic.get("textures", []):
        for rel in ([t["file"]] if t.get("kind") == "generated" else []) + ([t["fallback_file"]] if t.get("fallback_file") else []):
            if not os.path.isfile(os.path.join(pack_dir, rel)):
                bad.append("pack file %s missing" % rel)
    unresolved = {s.get("free") for s in doc.get("surfaces", []) if s.get("free") and s["free"] not in keys}
    if unresolved:
        bad.append("%d surface keys name no licence.textures row (drawn flat): %s" % (len(unresolved), ", ".join(sorted(unresolved)[:3])))
    held = {r.get("stand_in") for r in lic.get("model_stand_ins", [])}
    lost = sorted({m["stand_in"] for m in lic.get("models", []) if str(m.get("stand_in", "")).startswith("lib/") and m["stand_in"] not in held})
    if lost:
        bad.append("%d lib/ models have no model_stand_ins row, so none is drawn: %s" % (len(lost), ", ".join(lost[:3])))
    if not pbr and not models:
        return bad
    pack = lic.get("store_pack")
    if not pack:
        return bad + ["no licence.store_pack: %d PBR sets and %d models draw as fallbacks (run ship_store.sh)" % (len(pbr), len(models))]
    files, missing, errors = closure(pack, dist, origin, cache)
    if errors:    # unknown is not 'not published': report it and skip the checks that would be guesses
        return bad + ["could not read slices (not the same as unpublished): %s" % "; ".join(sorted(errors))]
    if missing:
        bad.append("slices not published: %s" % ", ".join(sorted(missing)))
    if missing and pack["id"] + "@" + pack["version"] in missing:
        return bad
    no_set = sorted(t["file"] for t in pbr if "pbr/%s/%s/albedo.webp.import" % (os.path.basename(t["file"]), t.get("tier", "1k")) not in files
                    and "pbr/%s/%s/albedo.jpg.import" % (os.path.basename(t["file"]), t.get("tier", "1k")) not in files)
    if no_set:
        bad.append("%d PBR sets not in the slices (fallback albedo): %s" % (len(no_set), ", ".join(no_set[:4])))
    no_model = sorted(r["store_file"] for r in models if "models/%s.import" % r["store_file"] not in files)
    if no_model:
        bad.append("%d models not in the slices (stand-in box): %s" % (len(no_model), ", ".join(no_model[:4])))
    return bad


def cmd(args):
    cache, failed = {}, 0
    for p in args.manifests:
        try:
            with open(p) as f:
                doc = json.load(f)
        except OSError as e:    # a world mid-regeneration has no manifest yet
            print("%s: 1 problems\n  manifest unreadable: %s" % (p, e.strerror))
            failed += 1
            continue
        bad = check(doc, os.path.dirname(os.path.abspath(p)), args.dist, args.origin, cache)
        print("%s: %s" % (doc.get("name", p), "ok" if not bad else "%d problems" % len(bad)))
        for b in bad:
            print("  " + b)
        failed += bool(bad)
    print("storecheck: %d of %d worlds with problems" % (failed, len(args.manifests)))
    return 1 if failed else 0
