"""Weapon pickup stand-ins, CC0, for the `w_*` world models (`models/weapons/w_rif_ak47.mdl`, `w_pist_deagle`, ...) that map
authors place as props: assault rifle, pistol, submachine gun, sniper rifle, pump shotgun, machine gun, rocket launcher, knife
and a block of plastic explosive. They replace the cardboard box the old `w_\\w+` row drew.

blender -b --factory-startup --python weapons.py -- outdir
Writes dm_weaponrifle, dm_weaponpistol, dm_weaponsmg, dm_weaponsniper, dm_weaponshotgun, dm_weaponlmg, dm_weaponlauncher,
dm_weaponknife and dm_weaponc4 into outdir. Blender Z is up, X the length (muzzle toward +X), Y the depth; origin on the floor,
centred; each lies flat as a dropped weapon does. Plain colour materials.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402,F401
import modelkit as mk  # noqa: E402

outdir = sys.argv[sys.argv.index("--") + 1]
PI = math.pi


def out(name):
    return f"{outdir}/{name}.glb"


def gun(name, length, barrel_r, body_h, mag=None, stock=True, scope=False, pump=False, drum=False):
    """A long gun lying on its side: receiver, barrel, grip, optional stock, magazine, scope, forend."""
    p = mk.fresh()
    steel = mk.mat(name + "_steel", (0.12, 0.12, 0.13), 0.4, 0.7)
    wood = mk.mat(name + "_wood", (0.30, 0.2, 0.12), 0.8)
    z = 0.05 + body_h / 2
    x0 = -length / 2
    mk.box(p, (x0 + length * 0.52, 0, z), (length * 0.38, 0.04, body_h), steel)
    mk.cyl(p, (x0 + length * 0.82, 0, z + body_h * 0.2), barrel_r, length * 0.36, steel, verts=8, rot=(0, PI / 2, 0))
    mk.box(p, (x0 + length * 0.7, 0, z - body_h * 0.1), (length * 0.24, 0.05, body_h * 0.8), wood if pump else steel)
    mk.box(p, (x0 + length * 0.42, 0, z - body_h * 1.0), (0.05, 0.035, body_h * 1.4), wood, rot=(0, 0.25, 0))
    if stock:
        mk.box(p, (x0 + length * 0.17, 0, z - body_h * 0.2), (length * 0.3, 0.035, body_h * 1.2), wood, rot=(0, -0.08, 0))
    if mag:
        mk.box(p, (x0 + length * 0.56, 0, z - body_h * 1.0), (mag[0], 0.03, mag[1]), steel, rot=(0, 0.2, 0))
    if drum:
        mk.cyl(p, (x0 + length * 0.56, 0, z - body_h * 0.9), 0.1, 0.07, steel, verts=12, rot=(PI / 2, 0, 0))
    if scope:
        mk.cyl(p, (x0 + length * 0.5, 0, z + body_h * 0.9), 0.025, length * 0.3, steel, verts=10, rot=(0, PI / 2, 0))
    mk.finish(p, name, out(name))


gun("dm_weaponrifle", 0.95, 0.011, 0.07, mag=(0.05, 0.16))
gun("dm_weaponsmg", 0.6, 0.01, 0.07, mag=(0.035, 0.18), stock=False)
gun("dm_weaponsniper", 1.2, 0.014, 0.065, mag=(0.04, 0.08), scope=True)
gun("dm_weaponshotgun", 1.05, 0.016, 0.06, pump=True)
gun("dm_weaponlmg", 1.05, 0.013, 0.09, drum=True)

# Pistol 0.22 m: slide over a frame, angled grip, trigger guard.
p = mk.fresh()
steel = mk.mat("pi_steel", (0.1, 0.1, 0.11), 0.4, 0.7)
grip = mk.mat("pi_grip", (0.08, 0.08, 0.08), 0.9)
mk.box(p, (0.0, 0, 0.14), (0.22, 0.03, 0.035), steel)
mk.box(p, (-0.04, 0, 0.09), (0.12, 0.028, 0.05), steel)
mk.box(p, (-0.07, 0, 0.06), (0.032, 0.03, 0.11), grip, rot=(0, 0.25, 0))
mk.box(p, (-0.01, 0, 0.085), (0.04, 0.012, 0.012), steel)
mk.finish(p, "dm_weaponpistol", out("dm_weaponpistol"))

# Rocket launcher 1.1 m: tube with flared ends and a shoulder grip.
p = mk.fresh()
olive = mk.mat("rl_olive", (0.25, 0.28, 0.18), 0.6, 0.2)
blk = mk.mat("rl_black", (0.1, 0.1, 0.1), 0.6, 0.4)
mk.cyl(p, (0, 0, 0.1), 0.055, 1.0, olive, verts=14, rot=(0, PI / 2, 0))
mk.cyl(p, (0.52, 0, 0.1), 0.07, 0.1, blk, verts=14, rot=(0, PI / 2, 0))
mk.cyl(p, (-0.52, 0, 0.1), 0.07, 0.1, blk, verts=14, rot=(0, PI / 2, 0))
mk.box(p, (-0.05, 0, 0.04), (0.04, 0.03, 0.07), blk)
mk.finish(p, "dm_weaponlauncher", out("dm_weaponlauncher"))

# Knife 0.3 m: blade, guard, handle.
p = mk.fresh()
blade = mk.mat("kn_blade", (0.7, 0.7, 0.72), 0.3, 0.9)
hnd = mk.mat("kn_handle", (0.06, 0.06, 0.06), 0.8)
mk.box(p, (0.07, 0, 0.012), (0.17, 0.003, 0.03), blade)
mk.box(p, (-0.02, 0, 0.012), (0.012, 0.03, 0.035), hnd)
mk.box(p, (-0.09, 0, 0.012), (0.12, 0.025, 0.03), hnd)
mk.finish(p, "dm_weaponknife", out("dm_weaponknife"))

# Plastic explosive block 0.2 x 0.12 x 0.06 with a timer face and a wire.
p = mk.fresh()
tan = mk.mat("c4_tan", (0.55, 0.5, 0.38), 0.8)
dk = mk.mat("c4_dark", (0.06, 0.06, 0.06), 0.5)
mk.box(p, (0, 0, 0.03), (0.2, 0.12, 0.06), tan)
mk.box(p, (0.02, 0, 0.065), (0.08, 0.05, 0.012), dk)
mk.cyl(p, (-0.07, 0.03, 0.065), 0.006, 0.08, dk, verts=6, rot=(0, PI / 2, 0))
mk.finish(p, "dm_weaponc4", out("dm_weaponc4"))
