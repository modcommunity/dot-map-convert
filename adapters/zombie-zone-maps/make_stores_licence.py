#!/usr/bin/env python3
"""Write .stores/licence.json: the licence block dot-cloud's publisher signs into the stores pack, so the site can refuse
anything that is not CC0, MIT, public domain or CC-BY. Poly Haven and ambientCG are told apart by name (ambientCG ids end in
digits: Bricks024); every one of the 760 textures any world credits matched that rule. Sketchfab models come from
tools/stores_sketchfab_licences.tsv (uid, author, licence, url), re-checked against the worlds' credits.json and the model picks;
a model missing from that table is refused here, not shipped.
Usage: tools/make_stores_licence.py [.stores dir]"""
import json, os, re, sys
root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", ".stores")
out = []
pbr = sorted(os.listdir(os.path.join(root, "pbr-library")))
amb = [n for n in pbr if re.match(r"^[A-Z][A-Za-z]*\d+", n)]
ph = [n for n in pbr if n not in amb]
out.append({"paths": ["pbr-library/%s/" % n for n in amb], "licence": "CC0-1.0", "author": "Lennart Demes and contributors (ambientCG)", "url": "https://ambientcg.com"})
out.append({"paths": ["pbr-library/%s/" % n for n in ph], "licence": "CC0-1.0", "author": "Poly Haven contributors", "url": "https://polyhaven.com/textures"})
out.append({"paths": ["model-library/kenney/"], "licence": "CC0-1.0", "author": "Kenney", "url": "https://kenney.nl/assets"})
out.append({"paths": ["model-library/own/"], "licence": "CC0-1.0", "author": "TMC (generated for dot-map)", "url": "https://github.com/modcommunity/dot-map"})
out.append({"paths": ["model-library/polyhaven/"], "licence": "CC0-1.0", "author": "Poly Haven contributors", "url": "https://polyhaven.com/models"})
out.append({"paths": ["licence.json"], "licence": "CC0-1.0", "author": "TMC (this list)", "url": "https://github.com/zees-games/zombie-zone-maps"})
table = {}
for line in open(os.path.join(os.path.dirname(__file__), "stores_sketchfab_licences.tsv")):
    if line.startswith("#") or not line.strip():
        continue
    uid, author, lic, url = line.rstrip("\n").split("\t")
    table[uid] = (author, lic, url)
for uid in sorted(os.listdir(os.path.join(root, "model-library", "sketchfab"))):
    if uid not in table or table[uid][1] not in ("CC0-1.0", "CC-BY-4.0"):
        sys.exit("sketchfab/%s has no recorded CC0 or CC-BY-4.0 licence: not publishing it" % uid)
    a, l, u = table[uid]
    out.append({"paths": ["model-library/sketchfab/%s/" % uid], "licence": l, "author": a, "url": u})
json.dump({"licences": out}, open(os.path.join(root, "licence.json"), "w"), indent=1)
print("wrote", os.path.join(root, "licence.json"), len(out), "entries")
