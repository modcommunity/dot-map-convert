"""A map's sky, light, fog, reflection probes and sound as data, in metres and Godot axes.

`environment` and `sounds` read the point entities `classes.py` calls `point` that the mesh
leaves out of the manifest: nothing here runs, it only says what the map asked for, so a game
draws its own sky and plays its own sound. Sound files are the author's and are never shipped:
a record names the original (`message`) so an adapter can map it to a free sound, and
`stand_in` stays empty until it does.
"""

from . import reader
from . import units as _units


def _get(e, key, default=""):
    key = key.lower()
    for k, v in e.items():
        if k.lower() == key:
            return v
    return default


def _num(text, default=0.0):
    try:
        return float(str(text).split()[0])
    except (ValueError, IndexError):
        return default


def _colour(text):
    """'r g b [intensity]' (0..255) to [r, g, b] in 0..1, plus the fourth value when given."""
    t = str(text).split()
    try:
        v = [float(x) for x in t[:4]]
    except ValueError:
        return None
    if len(v) < 3:
        return None
    return [round(c / 255.0, 4) for c in v[:3]] + ([v[3]] if len(v) > 3 else [])


def _at(e, k, y0):
    p = reader.entity_vec(e)
    return [round(p[0] * k, 4), round(p[2] * k - y0, 4), round(-p[1] * k, 4)]


def _angles(e):
    """(pitch, yaw) of an entity; a `pitch` key beats the angles' first value, as the engine does."""
    a = str(_get(e, "angles", "0 0 0")).split()
    try:
        pitch, yaw = float(a[0]), float(a[1])
    except (ValueError, IndexError):
        pitch, yaw = 0.0, 0.0
    if _get(e, "pitch") != "":
        pitch = _num(_get(e, "pitch"), pitch)
    return pitch, yaw


def environment(bsp, scale=_units.VISUAL, y0=0.0):
    """{sky, sun, fog, shadows, tonemap, cubemaps, wind, sky_camera}: every key a game needs to
    rebuild the outdoors, with lengths in metres. Absent things are absent keys, not nulls."""
    ents = bsp.entities
    world = ents[0] if ents else {}
    out = {"sky": {"name": _get(world, "skyname"), "keys": {k: str(v) for k, v in world.items()
                   if k.lower() in ("skyname", "maxpropscreenwidth", "detailmaterial", "detailvbsp",
                                    "maxrange", "minrange", "chaptertitle", "gametitle")}}}
    suns, cubes = [], []
    for i, e in enumerate(ents):
        cls = e.get("classname", "")
        if cls == "light_environment":
            pitch, yaw = _angles(e)
            rec = {"entity": i, "class": cls, "pitch": pitch, "yaw": yaw, "colour": _colour(_get(e, "_light")),
                   "ambient": _colour(_get(e, "_ambient")), "colour_hdr": _colour(_get(e, "_lighthdr")),
                   "ambient_hdr": _colour(_get(e, "_ambienthdr")), "spread": _num(_get(e, "SunSpreadAngle"))}
            out.setdefault("sun", rec)
            suns.append(rec)
        elif cls == "env_sun":
            pitch, yaw = _angles(e)
            out.setdefault("env_sun", {"entity": i, "pitch": pitch, "yaw": yaw,
                                       "colour": _colour(_get(e, "rendercolor")), "size": _num(_get(e, "size")),
                                       "material": _get(e, "material")})
        elif cls == "env_fog_controller":
            out.setdefault("fog", []).append({
                "entity": i, "targetname": _get(e, "targetname"), "enabled": _get(e, "fogenable", "0") == "1",
                "colour": _colour(_get(e, "fogcolor")), "colour2": _colour(_get(e, "fogcolor2")),
                "start": round(_num(_get(e, "fogstart")) * scale, 3), "end": round(_num(_get(e, "fogend")) * scale, 3),
                "max_density": _num(_get(e, "fogmaxdensity"), 1.0), "far_z": round(_num(_get(e, "farz"), -1) * scale, 3)
                if _num(_get(e, "farz"), -1) > 0 else -1, "blend": _get(e, "fogblend", "0") == "1"})
        elif cls == "shadow_control":
            pitch, yaw = _angles(e)
            out.setdefault("shadows", {"entity": i, "pitch": pitch, "yaw": yaw, "colour": _colour(_get(e, "color")),
                                       "distance": round(_num(_get(e, "distance")) * scale, 3),
                                       "disabled": _get(e, "disableallshadows", "0") == "1"})
        elif cls == "env_tonemap_controller":
            out.setdefault("tonemap", {"entity": i, "targetname": _get(e, "targetname"),
                                       "keys": {k: str(v) for k, v in e.items() if not k.startswith("On") and k not in ("classname", "origin")}})
        elif cls == "env_cubemap":
            cubes.append({"entity": i, "at": _at(e, scale, y0), "size": int(_num(_get(e, "cubemapsize"))) or 0})
        elif cls == "env_wind":
            out.setdefault("wind", {"entity": i, "min": _num(_get(e, "minwind")), "max": _num(_get(e, "maxwind")),
                                    "gust_min": _num(_get(e, "mingust")), "gust_max": _num(_get(e, "maxgust"))})
        elif cls == "sky_camera":
            out.setdefault("sky_camera", {"entity": i, "at": _at(e, scale, y0), "scale": _num(_get(e, "scale"), 16.0),
                                          "fog": _get(e, "fogenable", "0") == "1",
                                          "fog_colour": _colour(_get(e, "fogcolor")),
                                          "fog_start": round(_num(_get(e, "fogstart")) * scale, 3),
                                          "fog_end": round(_num(_get(e, "fogend")) * scale, 3)})
    if len(suns) > 1:
        out["suns"] = suns
    if cubes:
        out["cubemaps"] = cubes
    return out


def sounds(bsp, scale=_units.VISUAL, y0=0.0):
    """{ambient, soundscapes, triggers, files}. `ambient` is each ambient_generic (looped by
    default unless spawnflag 32 is set; 16 starts silent, 1 plays everywhere); `files` is every
    sound the map names, with what names it, so a game can map each to a free sound."""
    out = {"ambient": [], "soundscapes": [], "triggers": [], "files": {}}
    for i, e in enumerate(bsp.entities):
        cls = e.get("classname", "")
        if cls == "ambient_generic":
            flags = int(_num(_get(e, "spawnflags")))
            msg = str(_get(e, "message")).replace("\\", "/")
            out["ambient"].append({
                "entity": i, "targetname": _get(e, "targetname"), "at": _at(e, scale, y0), "message": msg,
                "volume": _num(_get(e, "health"), 10.0) / 10.0, "radius": round(_num(_get(e, "radius"), 1250) * scale, 3),
                "pitch": _num(_get(e, "pitch"), 100.0), "pitch_start": _num(_get(e, "pitchstart"), 100.0),
                "everywhere": bool(flags & 1), "start_silent": bool(flags & 16), "looped": not flags & 32,
                "source_entity": _get(e, "sourceentityname"), "stand_in": ""})
            if msg:
                out["files"].setdefault(msg.lower(), []).append("ambient_generic:%d" % i)
        elif cls in ("env_soundscape", "env_soundscape_triggerable", "env_soundscape_proxy"):
            name = _get(e, "soundscape") or _get(e, "MainSoundscapeName")
            out["soundscapes"].append({
                "entity": i, "class": cls, "targetname": _get(e, "targetname"), "soundscape": name,
                "at": _at(e, scale, y0), "radius": round(_num(_get(e, "radius")) * scale, 3),
                "positions": [_get(e, "position%d" % n) for n in range(8) if _get(e, "position%d" % n)]})
        elif cls == "trigger_soundscape":
            out["triggers"].append({"entity": i, "soundscape": _get(e, "soundscape"), "model": _get(e, "model"),
                                    "start_disabled": _get(e, "startdisabled", "0") == "1"})
    return out
