"""Low-poly vehicles, CC0, for `rules/models/categories.tsv`: a box truck, a flatbed truck, a box trailer, a forklift, a fuel tanker, a generator trailer, a hand truck, a panel van, an armoured carrier a wooden hand cart, four sedans and hatchbacks (one police), a minibus and a refuse truck.

blender -b --factory-startup --python vehicles.py -- outdir
Writes dm_boxtruck, dm_flatbedtruck, dm_boxtrailer, dm_forkliftmachine, dm_fueltanker, dm_generatortrailer, dm_handtruck, dm_panelvan, dm_armouredcarrier, dm_woodcart, dm_carsedan, dm_carsedanblack, dm_carsedanred, dm_carhatch, dm_carpolice, dm_minibus and dm_refusetruck (.glb) into outdir. Length along X, front at +X, origin on the floor, centred.
Plain colour materials only, under 700 triangles each, real-world scale (the picker rescales).
"""
import math
import sys

import bpy

outdir = sys.argv[sys.argv.index("--") + 1]
M = {}


def mat(name, rgb, rough=0.7, metal=0.0):
    if name not in M:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Base Color"].default_value = (*rgb, 1.0)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        M[name] = m
    return M[name]


def paint(): return mat("paint", (0.72, 0.18, 0.14))
def cargo(): return mat("cargo", (0.82, 0.82, 0.8))
def dark(): return mat("dark", (0.1, 0.1, 0.11), 0.9)
def glass(): return mat("glass", (0.35, 0.5, 0.6), 0.2)
def steel(): return mat("steel", (0.4, 0.42, 0.45), 0.5, 0.6)
def wood(): return mat("deck", (0.5, 0.36, 0.2), 0.9)


def box(parts, x0, x1, y0, y1, z0, z1, m):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    o = bpy.context.object
    o.scale = (x1 - x0, y1 - y0, z1 - z0)
    o.data.materials.append(m)
    parts.append(o)


def wheel(parts, x, y, r, w, m=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=r, depth=w, location=(x, y, r), rotation=(math.pi / 2, 0, 0))
    o = bpy.context.object
    o.data.materials.append(m or dark())
    parts.append(o)
    # hub
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=r * 0.5, depth=w * 1.05, location=(x, y, r), rotation=(math.pi / 2, 0, 0))
    h = bpy.context.object
    h.data.materials.append(steel())
    parts.append(h)


def cab(parts, x0, x1, hw, z0=0.9, top=2.6):
    """Truck cab: lower body plus a glazed upper part, a bonnet is not needed (cab-over)."""
    box(parts, x0, x1, -hw, hw, z0, z0 + 0.7, paint())
    box(parts, x0 + 0.05, x1, -hw + 0.02, hw - 0.02, z0 + 0.7, top, paint())
    box(parts, x1 - 0.01, x1 + 0.02, -hw + 0.12, hw - 0.12, z0 + 0.95, top - 0.35, glass())
    for s in (-1, 1):
        box(parts, x0 + 0.4, x1 - 0.5, s * (hw - 0.01), s * (hw + 0.015), z0 + 0.95, top - 0.35, glass())
    box(parts, x1 - 0.02, x1 + 0.06, -hw, hw, z0, z0 + 0.25, steel())


def finish(parts, name, path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    o = bpy.context.object
    o.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.quads_convert_to_tris()
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True, export_yup=True)


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    M.clear()
    return []


def axle_wheels(parts, xs, hw, r=0.5, w=0.3):
    for x in xs:
        for s in (-1, 1):
            wheel(parts, x, s * (hw - 0.05), r, w)


# Box truck, 6.2 x 2.4 x 3.0 m.
p = fresh()
box(p, -3.1, 1.3, -1.15, 1.15, 0.45, 0.85, steel())      # chassis
box(p, -3.1, 1.2, -1.2, 1.2, 0.85, 3.0, cargo())          # cargo box
box(p, -3.12, -3.08, -1.0, 1.0, 1.0, 2.8, steel())        # rear door frame
cab(p, 1.25, 3.1, 1.1, 0.7, 2.6)
axle_wheels(p, (2.2, -1.9, -0.6), 1.2)
finish(p, "TruckBox", f"{outdir}/dm_boxtruck.glb")

# Flatbed truck, 5.6 x 2.3 x 2.6 m.
p = fresh()
box(p, -2.8, 1.0, -1.1, 1.1, 0.5, 0.8, steel())
box(p, -2.8, 1.0, -1.15, 1.15, 0.8, 0.95, wood())         # deck
for s in (-1, 1):
    box(p, -2.8, 1.0, s * 1.1, s * 1.15, 0.95, 1.3, wood())   # side boards
box(p, 0.95, 1.0, -1.15, 1.15, 0.95, 1.9, wood())            # headboard behind the cab
cab(p, 1.05, 2.8, 1.05, 0.7, 2.5)
axle_wheels(p, (1.95, -1.6, -0.5), 1.15, 0.42, 0.3)
finish(p, "TruckFlatbed", f"{outdir}/dm_flatbedtruck.glb")

# Box trailer on a tandem axle with a landing gear and a front kingpin plate, 8 x 2.5 x 3.6 m (deck at 1.1 m).
p = fresh()
box(p, -4.0, 4.0, -1.2, 1.2, 1.0, 1.15, steel())
box(p, -4.0, 4.0, -1.25, 1.25, 1.15, 3.6, cargo())
box(p, -4.02, -3.98, -1.0, 1.0, 1.3, 3.4, steel())
for z in (1.8, 2.6):
    box(p, -4.0, 4.0, -1.255, 1.255, z, z + 0.05, steel())   # ribs
for s in (-1, 1):
    box(p, 3.0, 3.1, s * 1.0, s * 1.1, 0.35, 1.0, steel())    # landing legs
axle_wheels(p, (-2.5, -1.2), 1.25, 0.5, 0.3)
finish(p, "Trailer", f"{outdir}/dm_boxtrailer.glb")

# Forklift, 1.2 x 2.1 x 3.0 m (mast to +X): counterweight rear, seat and overhead guard, mast with two tines.
p = fresh()
box(p, -1.3, 0.5, -0.55, 0.55, 0.3, 0.85, paint())          # body
box(p, -1.45, -0.9, -0.55, 0.55, 0.3, 1.1, steel())         # counterweight
box(p, -0.7, -0.2, -0.3, 0.3, 0.85, 1.15, dark())           # seat
for sx in (-0.85, 0.2):
    for sy in (-0.45, 0.45):
        box(p, sx, sx + 0.05, sy, sy + 0.05, 1.1, 2.05, steel())    # guard posts
box(p, -0.9, 0.3, -0.5, 0.5, 2.05, 2.1, steel())             # guard roof
for s in (-1, 1):
    box(p, 0.55, 0.65, s * 0.4, s * 0.3, 0.2, 2.1, steel())   # mast uprights (two)
box(p, 0.55, 0.65, -0.4, 0.4, 1.5, 1.6, steel())
box(p, 0.65, 0.72, -0.45, 0.45, 0.15, 1.0, steel())          # carriage
for s in (-1, 1):
    box(p, 0.72, 1.7, s * 0.35 - 0.06, s * 0.35 + 0.06, 0.1, 0.18, steel())  # tines
for x, y in ((0.15, -0.55), (0.15, 0.55)):
    wheel(p, x, y, 0.32, 0.22)
for y in (-0.5, 0.5):
    wheel(p, -1.0, y, 0.27, 0.2)
finish(p, "Forklift", f"{outdir}/dm_forkliftmachine.glb")


def drum(parts, x0, x1, y, z, r, m, n=16):
    """Cylinder lying along X."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=n, radius=r, depth=x1 - x0, location=((x0 + x1) / 2, y, z), rotation=(0, math.pi / 2, 0))
    o = bpy.context.object
    o.data.materials.append(m)
    parts.append(o)


# Fuel tanker, 8.5 x 2.5 x 2.8 m: cab-over tractor, round tank on a frame.
p = fresh()
box(p, -4.2, 3.0, -0.9, 0.9, 0.55, 0.85, steel())
drum(p, -4.25, 2.0, 0, 1.75, 1.0, cargo(), 20)
for x in (-4.25, 1.9):
    drum(p, x, x + 0.1, 0, 1.75, 1.03, steel(), 20)         # end bands
box(p, -3.0, 1.0, -0.2, 0.2, 2.7, 2.8, steel())             # walkway
cab(p, 2.15, 4.2, 1.2, 0.8, 2.5)
axle_wheels(p, (3.3, -1.8, -3.2), 1.3, 0.5, 0.3)
finish(p, "Tanker", f"{outdir}/dm_fueltanker.glb")

# Generator trailer, 4.5 x 2.0 x 2.3 m: ribbed sound-proof enclosure on a one-axle chassis with a draw bar.
p = fresh()
box(p, -2.0, 1.8, -0.85, 0.85, 0.5, 0.65, steel())
box(p, -2.0, 1.8, -0.95, 0.95, 0.65, 2.3, paint())
for x in (-1.5, -0.5, 0.5):
    box(p, x, x + 0.05, -0.96, 0.96, 0.9, 2.1, dark())      # louvre bands
box(p, 1.8, 2.25, -0.06, 0.06, 0.55, 0.62, steel())          # draw bar
box(p, 2.2, 2.3, -0.12, 0.12, 0.45, 0.7, dark())             # coupling
for s in (-1, 1):
    box(p, -1.8, -1.6, s * 0.7, s * 0.8, 0.0, 0.5, steel())  # stands
axle_wheels(p, (-0.2,), 1.1, 0.45, 0.28)
finish(p, "GeneratorTrailer", f"{outdir}/dm_generatortrailer.glb")

# Hand truck, 0.5 x 0.5 x 1.2 m: two rails, cross bars, a toe plate and two wheels.
p = fresh()
for s in (-1, 1):
    box(p, -0.03, 0.03, s * 0.22 - 0.015, s * 0.22 + 0.015, 0.12, 1.2, steel())
box(p, -0.04, 0.02, -0.23, 0.23, 1.15, 1.2, steel())
for z in (0.4, 0.7, 0.95):
    box(p, -0.04, 0.02, -0.22, 0.22, z, z + 0.02, steel())
box(p, 0.0, 0.3, -0.2, 0.2, 0.1, 0.13, steel())              # toe plate
for s in (-1, 1):
    wheel(p, -0.08, s * 0.27, 0.13, 0.06)
finish(p, "HandTruck", f"{outdir}/dm_handtruck.glb")

# Panel van, 4.4 x 1.8 x 1.7 m.
p = fresh()
box(p, -2.2, 2.2, -0.9, 0.9, 0.3, 0.55, steel())
box(p, -2.2, 0.9, -0.9, 0.9, 0.55, 1.7, cargo())             # load area
box(p, 0.9, 2.2, -0.9, 0.9, 0.55, 1.0, paint())              # bonnet
box(p, 0.4, 1.4, -0.88, 0.88, 1.0, 1.7, paint())             # cab roof and body
box(p, 1.38, 1.46, -0.8, 0.8, 1.05, 1.55, glass())           # windscreen
for s in (-1, 1):
    box(p, 0.5, 1.2, s * 0.9, s * 0.915, 1.05, 1.55, glass())
box(p, 2.2, 2.3, -0.9, 0.9, 0.3, 0.5, steel())
axle_wheels(p, (1.4, -1.3), 0.9, 0.34, 0.22)
finish(p, "Van", f"{outdir}/dm_panelvan.glb")

# Armoured personnel carrier, 4.2 x 1.84 x 1.9 m: sloped hull, turret, four big wheels.
p = fresh()
box(p, -2.1, 2.1, -0.9, 0.9, 0.5, 1.3, mat("armour", (0.36, 0.4, 0.3), 0.8))
box(p, -2.1, 2.1, -0.75, 0.75, 1.3, 1.45, mat("armour", (0.36, 0.4, 0.3), 0.8))
box(p, 1.6, 2.15, -0.8, 0.8, 0.8, 1.2, mat("armour", (0.36, 0.4, 0.3), 0.8))   # nose
box(p, 1.0, 1.4, -0.5, 0.5, 1.4, 1.5, glass())               # driver slit
drum(p, -0.4, -0.4 + 0.9, 0, 1.6, 0.4, mat("armour", (0.36, 0.4, 0.3), 0.8), 12)   # turret ring
box(p, 0.5, 1.8, -0.04, 0.04, 1.55, 1.65, dark())            # gun
for s in (-1, 1):
    box(p, -1.6, 1.0, s * 0.9, s * 0.92, 0.9, 1.1, dark())    # hatches/side ports
for x in (1.3, 0.45, -0.7, -1.55):
    for s in (-1, 1):
        wheel(p, x, s * 0.85, 0.5, 0.3)
finish(p, "Apc", f"{outdir}/dm_armouredcarrier.glb")

# Wooden hand cart, 2.2 x 0.9 x 1.0 m: open bed, two big spoked-look wheels, two shafts.
p = fresh()
box(p, -0.7, 0.7, -0.45, 0.45, 0.6, 0.68, wood())            # bed floor
for s in (-1, 1):
    box(p, -0.7, 0.7, s * 0.43, s * 0.45, 0.68, 1.0, wood())  # sides
box(p, -0.72, -0.68, -0.45, 0.45, 0.68, 1.0, wood())          # back
box(p, 0.68, 0.72, -0.45, 0.45, 0.68, 1.0, wood())            # front
for s in (-1, 1):
    box(p, 0.0, 2.2, s * 0.3 - 0.03, s * 0.3 + 0.03, 0.55, 0.62, wood())  # shafts
    wheel(p, 0.0, s * 0.55, 0.55, 0.08, wood())
box(p, 0.0, 0.0 + 0.04, -0.6, 0.6, 0.53, 0.57, steel())      # axle
finish(p, "Cart", f"{outdir}/dm_woodcart.glb")


def car(name, rgb, length=4.5, width=1.8, hatch=False, police=False):
    """Passenger car: body, cabin with glass band, bumpers, lights and four wheels; hatch ends the roof square."""
    p = fresh()
    body = mat("body" + name, rgb, 0.35, 0.3)
    l0, l1 = -length / 2, length / 2
    hw = width / 2
    box(p, l0, l1, -hw, hw, 0.32, 0.88, body)
    cl0, cl1 = (l0 + 0.15, l1 - 1.15) if hatch else (l0 + 0.95, l1 - 1.2)
    box(p, cl0, cl1, -hw + 0.08, hw - 0.08, 0.88, 1.42, body)
    box(p, cl0 + 0.1, cl1 - 0.1, -hw + 0.06, hw - 0.06, 0.95, 1.36, glass())
    box(p, cl0 + 0.25, cl1 - 0.25, -hw + 0.1, hw - 0.1, 1.36, 1.44, body)
    for x in (l0 - 0.04, l1 - 0.01):
        box(p, x, x + 0.05, -hw, hw, 0.28, 0.5, dark())
    box(p, l1 - 0.02, l1 + 0.02, -hw + 0.1, -hw + 0.42, 0.62, 0.74, mat("headlight", (1.0, 0.95, 0.75), 0.3))
    box(p, l1 - 0.02, l1 + 0.02, hw - 0.42, hw - 0.1, 0.62, 0.74, mat("headlight", (1.0, 0.95, 0.75), 0.3))
    for s in (-1, 1):
        box(p, l0 - 0.02, l0 + 0.02, min(s * (hw - 0.1), s * (hw - 0.4)), max(s * (hw - 0.1), s * (hw - 0.4)), 0.62, 0.74, mat("taillight", (0.8, 0.05, 0.05), 0.4))
    if police:
        box(p, (cl0 + cl1) / 2 - 0.12, (cl0 + cl1) / 2 + 0.12, -0.55, 0.0, 1.44, 1.52, mat("sirenr", (0.9, 0.1, 0.1), 0.3))
        box(p, (cl0 + cl1) / 2 - 0.12, (cl0 + cl1) / 2 + 0.12, 0.0, 0.55, 1.44, 1.52, mat("sirenb", (0.1, 0.2, 0.9), 0.3))
        box(p, l0 + 0.9, l1 - 0.9, -hw - 0.005, hw + 0.005, 0.5, 0.62, mat("stripe", (0.95, 0.95, 0.95), 0.5))
    axle_wheels(p, (l1 - 0.95, l0 + 0.85), hw + 0.05, 0.32, 0.22)
    finish(p, name, f"{outdir}/dm_{name}.glb")


car("carsedan", (0.25, 0.35, 0.55))
car("carsedanblack", (0.07, 0.07, 0.08))
car("carsedanred", (0.65, 0.1, 0.1))
car("carhatch", (0.75, 0.72, 0.6), 3.9, 1.7, hatch=True)
car("carpolice", (0.12, 0.14, 0.2), 4.9, 1.9, police=True)

# Minibus, 5.7 x 2.2 x 3.2 m, front at +X: window band, door, destination sign.
p = fresh()
bus = mat("busbody", (0.9, 0.7, 0.1), 0.4, 0.2)
box(p, -2.85, 2.85, -1.1, 1.1, 0.4, 3.0, bus)
box(p, -2.8, 2.8, -1.105, 1.105, 1.5, 2.55, glass())
for x in (-1.6, -0.5, 0.6, 1.7):
    box(p, x - 0.04, x + 0.04, -1.11, 1.11, 1.5, 2.55, bus)
box(p, 2.84, 2.88, -1.0, 1.0, 1.1, 2.6, glass())
box(p, 2.84, 2.88, -0.7, 0.7, 2.65, 2.9, mat("sign", (1.0, 0.6, 0.1), 0.4))
box(p, 2.84, 2.9, -1.1, 1.1, 0.25, 0.5, dark())
for s in (-1, 1):
    box(p, 2.8, 2.88, s * 0.65 - 0.2, s * 0.65 + 0.2, 0.6, 0.78, mat("headlight", (1.0, 0.95, 0.75), 0.3))
box(p, 1.4, 2.2, 1.105, 1.12, 0.5, 2.4, dark())
box(p, -2.4, -0.6, -0.6, 0.6, 3.0, 3.2, steel())
axle_wheels(p, (1.85, -1.8), 1.1, 0.42, 0.28)
finish(p, "BusMini", f"{outdir}/dm_minibus.glb")

# Refuse truck, 7.5 x 2.5 x 3.3 m, front at +X: cab, compactor body with a rear hopper and a bin lift.
p = fresh()
box(p, -3.75, 1.7, -1.1, 1.1, 0.5, 0.9, steel())
box(p, -3.75, 1.6, -1.2, 1.2, 0.9, 3.0, mat("refuse", (0.2, 0.45, 0.25), 0.5))
box(p, -3.75, -2.9, -1.2, 1.2, 0.9, 1.6, dark())
box(p, -3.9, -3.75, -0.9, 0.9, 0.6, 2.6, steel())
cab(p, 1.65, 3.75, 1.1, 0.7, 2.7)
for z in (1.6, 2.2, 2.8):
    box(p, -2.9, 1.6, -1.205, 1.205, z, z + 0.05, steel())
axle_wheels(p, (2.6, -0.4, -2.5), 1.2, 0.5, 0.32)
finish(p, "TruckRefuse", f"{outdir}/dm_refusetruck.glb")
