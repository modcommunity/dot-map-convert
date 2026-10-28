extends SceneTree
## Bakes a PBR store's textures so a client loads them without decoding: see DotMapTextureBake.
##   heavy -- godot --headless --path dot-map --script tools/bake_textures.gd -- <store dir> [--out=<dir>] [--max=2048]
## Without --out the baked files sit beside the sources, where DotMapSurfaces looks. Publishes nothing.


func _initialize() -> void:
	var store := ""
	var out := ""
	var cap := 2048
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--out="):
			out = a.get_slice("=", 1)
		elif a.begins_with("--max="):
			cap = int(a.get_slice("=", 1))
		else:
			store = a
	if store.is_empty():
		print("usage: bake_textures.gd -- <store dir> [--out=<dir>] [--max=2048]")
		quit(2)
		return
	var stats := DotMapTextureBake.bake_store(store, out, cap)
	print("bake_textures: ", stats)
	quit(1 if stats["failed"] > 0 else 0)
