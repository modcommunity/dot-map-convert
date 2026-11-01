"""A light_environment nobody set, and what the sky says instead.

A mapper who never opened the light_environment compiles with the editor's defaults: white 255
255 255 at 200, angles 0 0 0 (a sun on the horizon), ambient white. The lightmap carries the real
light, but a renderer that reads the entity draws a white noon sun over a dusk map. When the entity
is exactly that default, the sky's name is the only statement the author made, so it picks a mood.
"""

# Sky-name patterns, first match wins. sun: colour, brightness, pitch, yaw; amb: ambient colour;
# top: sky zenith; fog: horizon haze colour, start, end (map units), max density.
MOODS = (
    (("night", "dark", "space", "star", "borealis"), {
        "sun": ([0.45, 0.55, 0.85], 40.0, -35.0, 35.0), "amb": [0.14, 0.17, 0.28],
        "top": [0.03, 0.05, 0.12], "fog": ([0.08, 0.1, 0.18], 4000.0, 30000.0, 0.5)}),
    (("hav", "dusk", "sunset", "day03", "day01_09", "day02_09", "twilight"), {
        "sun": ([1.0, 0.58, 0.32], 90.0, -14.0, 215.0), "amb": [0.34, 0.31, 0.42],
        "top": [0.2, 0.2, 0.38], "fog": ([0.78, 0.52, 0.42], 3000.0, 26000.0, 0.55)}),
)


def is_editor_default(sun):
    """True when `sun` (the manifest's sun block) is the unedited light_environment."""
    if not sun:
        return False
    col, amb = sun.get("colour"), sun.get("ambient_colour")
    return (col is not None and all(c > 0.99 for c in col) and abs(sun.get("brightness", 0) - 200.0) < 1.0
            and amb is not None and all(c > 0.99 for c in amb)
            and not sun.get("yaw_src") and not sun.get("pitch_src"))


def mood_for(sky_name):
    n = (sky_name or "").lower()
    for keys, mood in MOODS:
        if any(k in n for k in keys):
            return mood
    return None


def resolve(lighting):
    """Rewrites `lighting` in place when its sun is the editor default and the sky names a mood;
    the original numbers stay under sun["editor_default"] so nothing is hidden. Returns it."""
    sun = lighting.get("sun")
    mood = mood_for(lighting.get("sky_name", ""))
    if mood is None or not is_editor_default(sun):
        return lighting
    col, bright, pitch, yaw = mood["sun"]
    sun.update({"editor_default": True, "colour": list(col), "brightness": bright,
                "pitch_src": pitch, "yaw_src": yaw, "ambient_colour": list(mood["amb"])})
    lighting["sky_top"] = list(mood["top"])
    if "fog" not in lighting:
        colour, start, end, density = mood["fog"]
        lighting["fog"] = {"enabled": True, "colour": list(colour), "start": start, "end": end,
                           "max_density": density}
    return lighting
