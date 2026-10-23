"""A starter `<map_name>.yml` for a converted map, from the console commands its entities send.

The commands are only ever suggestions: every value is written commented out, so a file the
converter emits changes nothing until an author or operator uncomments a line and the game
whitelists the key (docs/map-config.md). Nothing here runs a command.

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


def write_suggestion(out_dir, map_name, cmds):
    """Writes `<out_dir>/<map_name>.yml` unless one exists (an author's file is never overwritten). Returns the path or None."""
    text = suggest(map_name, cmds)
    path = os.path.join(out_dir, map_name + ".yml")
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
