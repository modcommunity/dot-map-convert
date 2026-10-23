"""A starter `<map_name>.yml` for a converted map, from the console commands its entities send.

The commands are only ever suggestions: every value is written commented out in the file, so it
changes nothing until an author or operator uncomments a line and the game whitelists the key
(docs/map-config.md). The same values are the manifest's `settings` (`defaults`), the weakest
layer of `DotMapConfig`, behind the same whitelist. Nothing here runs a command.

    python3 -m dotbsp.mapcfg OUT_DIR map1.bsp [map2.bsp ...]    (from tools/bsp)
"""

import os
import sys

from . import store


def parse(command):
    """`sv_airaccelerate 150; say hi` -> ([(key, value)], [text not shaped like `name value`])."""
    settings, other = [], []
    for part in command.split(";"):
        words = part.strip().split(None, 1)
        # A cvar name has an underscore; `say`, `bind` and `echo` are commands and are not settings.
        if len(words) == 2 and "_" in words[0] and words[0].replace("_", "").isalnum():
            settings.append((words[0].lower(), words[1].strip().strip('"')))
        elif part.strip():
            other.append(part.strip())
    return settings, other


def _scalar(value):
    try:
        float(value)
        return value
    except ValueError:
        return '"%s"' % value.replace('"', "'")


def defaults(cmds):
    """The `{cvar: value}` a map's own `point_servercommand` entities set, numbers as numbers.

    The manifest carries it as `settings` and `DotMapWorld` hands it to `DotMapConfig` as its
    weakest layer: a key the game does not whitelist is still refused, so this adds no command."""
    out = {}
    for c in cmds:
        if c.get("classname") == "point_servercommand":
            for key, value in parse(c.get("command", ""))[0]:
                try:
                    out[key] = int(value) if value.lstrip("-").isdigit() else float(value)
                except ValueError:
                    out[key] = value
    return out


def suggest(map_name, cmds):
    """The yml text for [map_name] from the rows of `store.commands`, or None when there is nothing to suggest."""
    chosen, skipped = {}, []
    for c in cmds:
        if c.get("classname") != "point_servercommand":
            skipped.append("%s: %s" % (c.get("classname"), c.get("command", "")))
            continue
        settings, other = parse(c.get("command", ""))
        for key, value in settings:
            chosen[key] = value
        skipped.extend("not a setting: " + o for o in other)
    if not chosen and not skipped:
        return None
    lines = ["# Suggested by the converter from commands in %s's entities." % map_name,
             "# Nothing here is applied. Uncomment a line to set it for this map; a key the game does",
             "# not whitelist is logged and ignored (docs/map-config.md)."]
    lines += ["# %s: %s" % (k, _scalar(v)) for k, v in sorted(chosen.items())]
    lines += ["# skipped, never run: " + s for s in skipped]
    return "\n".join(lines) + "\n"


def write_suggestion(out_dir, file_name, cmds, map_name=None):
    """Writes `<out_dir>/<file_name>.yml` unless one exists (an author's file is never overwritten). Returns the path or None."""
    text = suggest(map_name or file_name, cmds)
    path = os.path.join(out_dir, file_name + ".yml")
    if text is None or os.path.exists(path):
        return None
    os.makedirs(out_dir, exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    for bsp in argv[1:]:
        name = os.path.splitext(os.path.basename(bsp))[0].lower()
        with open(bsp, "rb") as f:
            cmds = store.document(f.read())["commands"]
        print(write_suggestion(argv[0], name, cmds) or "%s: nothing to suggest" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
