"""Procedural asset factory for BUNKER-0, run with Blender's Python module (bpy >= 5.0).

    python build_assets.py <output-dir>

Every model is built from code (no source .blend files) and exported as GLB.
Conventions: Blender is Z-up with the model's front facing -Y; the glTF
exporter turns that into three.js Y-up with the front facing +Z.
Materials carry semantic names (Paint, Neon, Screen, ...) so the game can
recolour or retexture them at runtime.
"""

import math
import os
import random
import sys

import bpy  # bpy must come first: it registers bmesh and mathutils
import bmesh
from mathutils import Vector

OUT = sys.argv[-1] if len(sys.argv) > 1 and not sys.argv[-1].endswith(".py") else "assets"
os.makedirs(OUT, exist_ok=True)
random.seed(7)
MATS = {}


# --------------------------------------------------------------------------- basics
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    MATS.clear()


def mat(name, color=(0.8, 0.8, 0.8), metal=0.0, rough=0.5, emit=None, strength=1.0, alpha=1.0, coat=0.0):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = strength
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    MATS[name] = m
    return m


def sel(objs, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]


def finish(o, m=None, smooth=True, angle=None):
    """Apply transforms and modifiers, assign material, shade."""
    sel([o])
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    for mod in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    if m is not None:
        o.data.materials.clear()
        o.data.materials.append(m)
    if smooth:
        if angle is not None:
            try:
                bpy.ops.object.shade_smooth_by_angle(angle=angle)
            except Exception:
                bpy.ops.object.shade_smooth()
        else:
            bpy.ops.object.shade_smooth()
    return o


def bevel(o, width, segs=2, limit=True):
    md = o.modifiers.new("bevel", "BEVEL")
    md.width = width
    md.segments = segs
    if limit:
        md.limit_method = "ANGLE"
    return o


def subsurf(o, lvl=2):
    md = o.modifiers.new("sub", "SUBSURF")
    md.levels = lvl
    md.render_levels = lvl
    return o


def cube(name, loc, size, m=None, bev=0.0, segs=2, sub=0, rot=(0, 0, 0), angle=0.7):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    if bev:
        sel([o])
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bevel(o, bev, segs)
    if sub:
        subsurf(o, sub)
    return finish(o, m, angle=None if sub else angle)


def cyl(name, loc, r, depth, m=None, verts=24, rot=(0, 0, 0), bev=0.0, sub=0, r2=None, angle=0.7):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    if bev:
        bevel(o, bev, 2)
    if sub:
        subsurf(o, sub)
    return finish(o, m, angle=None if sub else angle)


def sphere(name, loc, r, m=None, scale=(1, 1, 1), seg=24, rings=14, rot=(0, 0, 0), sub=0):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=r, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    if sub:
        subsurf(o, sub)
    return finish(o, m)


def torus(name, loc, R, r, m=None, rot=(0, 0, 0), maj=48, mino=12, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=maj, minor_segments=mino, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    return finish(o, m)


def lathe(name, profile, m=None, steps=48, loc=(0, 0, 0), rot=(0, 0, 0), sub=0, axis="Z"):
    """Spin a list of (radius, height) points around Z."""
    me = bpy.data.meshes.new(name)
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0, z)) for r, z in profile]
    edges = [bm.edges.new((vs[i], vs[i + 1])) for i in range(len(vs) - 1)]
    bmesh.ops.spin(bm, geom=vs + edges, angle=math.tau, steps=steps, axis=(0, 0, 1), cent=(0, 0, 0))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.to_mesh(me)
    bm.free()
    o.location = loc
    o.rotation_euler = rot
    if sub:
        subsurf(o, sub)
    sel([o])
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return finish(o, m)


def deform(o, fn):
    """Move vertices with fn(Vector) -> Vector (object-space)."""
    me = o.data
    for v in me.vertices:
        v.co = fn(v.co.copy())
    me.update()
    return o


def empty(name, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    o.location = loc
    bpy.context.collection.objects.link(o)
    return o


def parent(children, p):
    for c in children:
        c.parent = p
        c.matrix_parent_inverse = p.matrix_world.inverted()


def join(objs, name):
    objs = [o for o in objs if o is not None]
    if len(objs) == 1:
        objs[0].name = name
        return objs[0]
    sel(objs, objs[0])
    bpy.ops.object.join()
    o = bpy.context.active_object
    o.name = name
    return o


def join_by_material(objs, prefix):
    """Merge objects that share a single material to keep draw calls low."""
    groups = {}
    for o in objs:
        key = o.data.materials[0].name if o.data.materials else "none"
        groups.setdefault(key, []).append(o)
    return [join(g, f"{prefix}_{k}") for k, g in groups.items()]


def uv_project(objs):
    for o in objs:
        if o.type != "MESH":
            continue
        sel([o])
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        try:
            bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.02)
        except Exception:
            bpy.ops.uv.cube_project(cube_size=4.0)
        bpy.ops.object.mode_set(mode="OBJECT")


def export(path):
    objs = list(bpy.context.scene.objects)
    uv_project([o for o in objs if o.type == "MESH"])
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, path), export_format="GLB", use_selection=True, export_apply=True, export_yup=True)
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs if o.type == "MESH")
    size = os.path.getsize(os.path.join(OUT, path))
    print(f"[asset] {path}: {tris} tris, {size / 1024:.0f} KB")


# --------------------------------------------------------------------------- shared materials
def common_mats():
    return dict(
        paint=mat("Paint", (0.9, 0.9, 0.9), 0.55, 0.28, coat=1.0),
        carbon=mat("Carbon", (0.04, 0.045, 0.05), 0.3, 0.42),
        chrome=mat("Chrome", (0.92, 0.93, 0.95), 1.0, 0.12),
        steel=mat("Steel", (0.55, 0.58, 0.62), 0.9, 0.35),
        rubber=mat("Rubber", (0.025, 0.025, 0.03), 0.0, 0.85),
        neon=mat("Neon", (1, 1, 1), 0.0, 0.3, emit=(1, 1, 1), strength=4.0),
        exhaust=mat("Exhaust", (1, 0.5, 0.2), 0.0, 0.4, emit=(1.0, 0.45, 0.15), strength=6.0),
        light=mat("Headlight", (1, 1, 1), 0.0, 0.2, emit=(0.85, 0.95, 1.0), strength=8.0),
    )


# --------------------------------------------------------------------------- kart
def build_kart():
    reset()
    M = common_mats()
    suit = mat("Suit", (0.92, 0.93, 0.95), 0.1, 0.55)
    visor = mat("Visor", (0.02, 0.03, 0.05), 0.9, 0.05, emit=(0.15, 0.5, 0.9), strength=0.6)
    bci = mat("BCI", (1, 0.3, 0.85), 0.0, 0.3, emit=(1.0, 0.25, 0.85), strength=6.0)
    gun = mat("Gunmetal", (0.12, 0.13, 0.15), 0.85, 0.3)
    root = empty("Kart")
    parts = []
    # monocoque: tapered towards the nose, smooth
    body = cube("Body", (0, 0, 0.55), (1.15, 3.6, 0.42), M["paint"], sub=0)
    sel([body])
    deform(body, lambda v: Vector((v.x * (0.42 if v.y < -0.2 else 1.0), v.y, v.z * (0.55 if v.y < -0.2 else 1.0) + (-0.06 if v.y < -0.2 else 0))))
    bevel(body, 0.12, 3, limit=False)
    subsurf(body, 2)
    finish(body)
    parts.append(body)
    # cockpit tub
    tub = cube("Tub", (0, 0.35, 0.8), (0.95, 1.3, 0.35), M["carbon"], bev=0.1, segs=3)
    parts.append(tub)
    # side pods with neon intakes
    for sx in (-1, 1):
        pod = cube(f"Pod{sx}", (sx * 1.05, 0.35, 0.55), (0.55, 1.9, 0.48), M["paint"], sub=2)
        deform(pod, lambda v: Vector((v.x, v.y, v.z * (0.7 if v.y > 0.2 else 1.0))))
        parts.append(pod)
        parts.append(cube(f"Intake{sx}", (sx * 1.05, -0.62, 0.6), (0.4, 0.05, 0.22), M["neon"]))
        parts.append(cube(f"Stripe{sx}", (sx * 1.32, 0.35, 0.62), (0.02, 1.5, 0.06), M["neon"]))
    # front wing
    parts.append(cube("FrontWing", (0, -2.05, 0.22), (2.5, 0.42, 0.06), M["carbon"], bev=0.02))
    for sx in (-1, 1):
        parts.append(cube(f"FWEnd{sx}", (sx * 1.25, -2.05, 0.32), (0.05, 0.5, 0.26), M["paint"], bev=0.02))
    parts.append(cube("NoseLight", (0, -1.98, 0.42), (0.5, 0.04, 0.05), M["light"]))
    # rear wing
    parts.append(cube("RearWing", (0, 1.85, 1.38), (2.7, 0.55, 0.08), M["paint"], bev=0.03))
    parts.append(cube("RearWing2", (0, 1.95, 1.22), (2.5, 0.3, 0.05), M["carbon"], bev=0.02))
    for sx in (-1, 1):
        parts.append(cube(f"RWEnd{sx}", (sx * 1.36, 1.85, 1.25), (0.05, 0.7, 0.55), M["carbon"], bev=0.02))
        parts.append(cube(f"Strut{sx}", (sx * 0.45, 1.75, 1.0), (0.08, 0.18, 0.75), M["carbon"], bev=0.02))
    parts.append(cube("WingNeon", (0, 1.58, 1.42), (2.5, 0.03, 0.03), M["neon"]))
    # engine and exhausts
    parts.append(cyl("Engine", (0, 1.45, 0.85), 0.42, 0.9, M["steel"], rot=(math.pi / 2, 0, 0), bev=0.04))
    for sx in (-0.32, 0.32):
        parts.append(cyl(f"Pipe{sx}", (sx, 2.05, 0.82), 0.16, 0.5, M["chrome"], rot=(math.pi / 2, 0, 0), r2=0.2))
        parts.append(cyl(f"Flame{sx}", (sx, 2.31, 0.82), 0.13, 0.04, M["exhaust"], rot=(math.pi / 2, 0, 0)))
    # steering wheel
    parts.append(torus("Wheel", (0, -0.3, 1.18), 0.22, 0.035, M["carbon"], rot=(math.radians(60), 0, 0)))
    # driver
    drv = []
    drv.append(cyl("Torso", (0, 0.35, 1.2), 0.36, 0.7, suit, sub=1, r2=0.3))
    drv.append(sphere("Helmet", (0, 0.28, 1.78), 0.43, M["paint"], scale=(1, 1.08, 1)))
    vz = sphere("Visor", (0, 0.2, 1.8), 0.44, visor, scale=(0.95, 1.08, 0.75))
    deform(vz, lambda v: Vector((v.x, min(v.y, -0.05), v.z)))
    drv.append(vz)
    drv.append(cube("BCIChip", (0, 0.73, 1.86), (0.22, 0.08, 0.14), bci, bev=0.02))
    drv.append(cube("BCIWire", (0, 0.66, 2.05), (0.04, 0.04, 0.28), bci))
    for sx in (-1, 1):
        arm = cyl(f"Arm{sx}", (sx * 0.3, -0.02, 1.22), 0.09, 0.6, suit, rot=(math.radians(-70), sx * 0.25, 0))
        drv.append(arm)
    parts.extend(drv)
    # wheels (separate nodes, origin at hub so they can spin)
    wheels = []
    for name, x, y in (("Wheel_FL", -1.32, -1.3), ("Wheel_FR", 1.32, -1.3), ("Wheel_RL", -1.36, 1.25), ("Wheel_RR", 1.36, 1.25)):
        tire = cyl(name + "_tire", (0, 0, 0), 0.52, 0.48, M["rubber"], verts=32, rot=(0, math.pi / 2, 0), bev=0.12)
        rim = cyl(name + "_rim", (0, 0, 0), 0.33, 0.5, M["chrome"], verts=24, rot=(0, math.pi / 2, 0))
        hub = torus(name + "_hub", (math.copysign(0.26, x), 0, 0), 0.22, 0.035, M["neon"], rot=(0, math.pi / 2, 0), maj=24, mino=6)
        w = join([tire, rim, hub], name)
        w.location = (x, y, 0.52)
        wheels.append(w)
    # weapon turret (hidden until McAfee drops a gun)
    t_parts = [cyl("TBase", (0, 0, 0), 0.42, 0.25, gun, bev=0.04)]
    for sx in (-0.2, 0.2):
        t_parts.append(cyl(f"Barrel{sx}", (sx, -0.8, 0.12), 0.08, 1.5, gun, rot=(math.pi / 2, 0, 0)))
        t_parts.append(cyl(f"Muzzle{sx}", (sx, -1.56, 0.12), 0.1, 0.06, M["neon"], rot=(math.pi / 2, 0, 0)))
    t_parts.append(cube("TBox", (0, 0.05, 0.18), (0.55, 0.6, 0.25), gun, bev=0.05))
    turret = join(t_parts, "Turret")
    turret.location = (0, -1.0, 1.0)
    body_mesh = join_by_material(parts, "Kart")
    parent(body_mesh + wheels + [turret], root)
    export("kart.glb")


# --------------------------------------------------------------------------- saucers
def build_saucers():
    reset()
    M = common_mats()
    for species in ("Zeta", "Nibiru"):
        hull = mat(f"{species}_Hull", (0.62, 0.65, 0.72) if species == "Zeta" else (0.42, 0.47, 0.38), 0.85, 0.25)
        glass = mat("Glass", (0.6, 0.85, 1.0), 0.0, 0.05, alpha=0.35)
        engine = mat("Engine", (1, 1, 1), 0.0, 0.3, emit=(1, 1, 1), strength=5.0)
        root = empty(f"Saucer{species}")
        parts = []
        prof = [(0.001, -0.5), (0.9, -0.47), (1.7, -0.3), (2.3, -0.08), (2.45, 0.02), (2.3, 0.14), (1.7, 0.3), (1.05, 0.42), (0.9, 0.45)]
        parts.append(lathe(f"{species}Disc", prof, hull, steps=48, loc=(0, 0, 1.1), sub=1))
        parts.append(torus(f"{species}Rim", (0, 0, 1.12), 2.42, 0.07, M["neon"], maj=64, mino=8))
        parts.append(torus(f"{species}Belly", (0, 0, 0.62), 0.9, 0.12, engine, maj=40, mino=8))
        parts.append(lathe(f"{species}Pod", [(0.001, 0.45), (0.5, 0.48), (0.7, 0.62), (0.001, 0.62)], hull, steps=24, loc=(0, 0, 0.0)))
        # panel ridges and lights
        for i in range(12):
            a = i / 12 * math.tau
            parts.append(cube(f"{species}Fin{i}", (math.cos(a) * 1.75, math.sin(a) * 1.75, 1.36), (0.6, 0.08, 0.06), hull, rot=(0, 0, a), bev=0.02))
            parts.append(sphere(f"{species}Light{i}", (math.cos(a + 0.26) * 2.2, math.sin(a + 0.26) * 2.2, 1.18), 0.07, M["neon"], seg=8, rings=6))
        dome = sphere(f"{species}Dome", (0, 0.05, 1.5), 0.95, glass, seg=32, rings=16)
        deform(dome, lambda v: Vector((v.x, v.y, max(v.z, 0.0))))
        parts.append(dome)
        if species == "Zeta":
            skin = mat("Zeta_Skin", (0.58, 0.66, 0.56), 0.0, 0.55)
            eye = mat("Zeta_Eye", (0.01, 0.01, 0.015), 0.4, 0.05)
            head = sphere("ZHead", (0, 0.05, 1.98), 0.36, skin, scale=(1, 0.95, 1.3), sub=1)
            deform(head, lambda v: Vector((v.x * (1 + 0.25 * max(0, v.z)), v.y, v.z)))
            parts.append(head)
            for sx in (-1, 1):
                parts.append(sphere(f"ZEye{sx}", (sx * 0.15, -0.27, 2.0), 0.12, eye, scale=(0.9, 0.55, 1.4), rot=(0, sx * 0.5, 0)))
            parts.append(cyl("ZNeck", (0, 0.05, 1.6), 0.1, 0.3, skin))
        else:
            skin = mat("Nibiru_Skin", (0.25, 0.45, 0.2), 0.1, 0.45)
            eye = mat("Nibiru_Eye", (1, 0.8, 0), 0.0, 0.2, emit=(1, 0.75, 0), strength=4.0)
            parts.append(sphere("NHead", (0, 0.1, 1.95), 0.33, skin, scale=(1, 1.15, 0.95), sub=1))
            snout = sphere("NSnout", (0, -0.25, 1.88), 0.22, skin, scale=(0.8, 1.4, 0.65), sub=1)
            parts.append(snout)
            for sx in (-1, 1):
                parts.append(sphere(f"NEye{sx}", (sx * 0.16, -0.12, 2.04), 0.07, eye, scale=(1.2, 0.6, 0.6)))
            for i in range(4):
                parts.append(cyl(f"NSpike{i}", (0, 0.05 + i * 0.12, 2.25 - i * 0.05), 0.05, 0.16, skin, r2=0.0, rot=(-0.4, 0, 0)))
            parts.append(cyl("NNeck", (0, 0.1, 1.6), 0.12, 0.3, skin))
        parts.append(cyl(f"{species}Antenna", (0.9, 0.9, 1.7), 0.02, 0.7, M["steel"]))
        parts.append(sphere(f"{species}AntennaTip", (0.9, 0.9, 2.05), 0.06, M["neon"], seg=8, rings=6))
        merged = join_by_material(parts, f"Saucer{species}")
        parent(merged, root)
    export("saucers.glb")


# --------------------------------------------------------------------------- characters
def person(name, spec):
    S = lambda n, c, met=0.0, r=0.55: mat(f"{name}_{n}", c, met, r)
    skin = S("Skin", spec["skin"], 0.0, 0.6)
    suit = S("Suit", spec["suit"], 0.05, 0.6)
    pants = S("Pants", spec.get("pants", spec["suit"]), 0.05, 0.65)
    shirt = S("Shirt", spec.get("shirt", (0.95, 0.95, 0.95)), 0.0, 0.5)
    hair = S("Hair", spec["hair"], 0.05, 0.55)
    shoe = S("Shoe", (0.03, 0.03, 0.035), 0.3, 0.25)
    dark = S("Dark", (0.02, 0.02, 0.02), 0.0, 0.4)
    white = S("EyeWhite", (0.95, 0.95, 0.95), 0.0, 0.3)
    lip = S("Lip", (0.55, 0.25, 0.25), 0.0, 0.5)
    root = empty(name)
    p = []
    for sx in (-1, 1):
        p.append(cube(f"{name}Shoe{sx}", (sx * 0.15, -0.05, 0.06), (0.17, 0.32, 0.12), shoe, sub=2))
        p.append(cyl(f"{name}Leg{sx}", (sx * 0.15, 0, 0.53), 0.12, 0.86, pants, verts=16, r2=0.135))
    torso = cube(f"{name}Torso", (0, 0, 1.36), (0.78, 0.42, 0.84), None)
    deform(torso, lambda v: Vector((v.x * (0.84 if v.z < 0 else 1.0), v.y * (0.92 if v.z < 0 else 1.0), v.z)))
    bevel(torso, 0.14, 4, limit=False)
    finish(torso, suit)
    p.append(torso)
    tshirt = spec.get("tshirt", False)
    if not tshirt:
        p.append(cube(f"{name}ShirtV", (0, -0.2, 1.58), (0.2, 0.06, 0.32), shirt, rot=(0.15, 0, 0)))
        for sx in (-1, 1):
            p.append(
                cube(f"{name}Lapel{sx}", (sx * 0.12, -0.225, 1.55), (0.1, 0.03, 0.38), S("Lapel", [c * 0.7 for c in spec["suit"]]), rot=(0.12, sx * 0.35, 0))
            )
        if spec.get("tie"):
            tie = S("Tie", spec["tie"], 0.1, 0.4)
            tlen = spec.get("tie_len", 0.42)
            p.append(cube(f"{name}TieKnot", (0, -0.24, 1.69), (0.08, 0.05, 0.07), tie))
            p.append(cube(f"{name}Tie", (0, -0.245, 1.66 - tlen / 2), (0.09, 0.03, tlen), tie, rot=(0.1, 0, 0)))
        else:
            p.append(cube(f"{name}Collar", (0, -0.2, 1.72), (0.3, 0.05, 0.08), shirt))
    else:
        p.append(torus(f"{name}Crew", (0, 0, 1.76), 0.14, 0.03, suit, maj=20, mino=6))
    if spec.get("chain"):
        p.append(torus(f"{name}Chain", (0, -0.08, 1.7), 0.15, 0.015, S("Gold", (1, 0.75, 0.3), 1.0, 0.2), rot=(0.5, 0, 0), maj=20, mino=5))
    for sx in (-1, 1):
        p.append(sphere(f"{name}Shoulder{sx}", (sx * 0.38, 0, 1.66), 0.15, suit, scale=(1.0, 1.25, 0.9)))
    p.append(cyl(f"{name}Neck", (0, 0, 1.82), 0.085, 0.16, skin, verts=16))
    head = sphere(f"{name}Head", (0, 0, 2.06), 0.27, skin, scale=spec.get("face", (0.93, 0.96, 1.06)), sub=1)
    p.append(head)
    p.append(sphere(f"{name}Nose", (0, -0.265, 2.03), 0.05, skin, scale=(0.8, 1.1, 1.2)))
    for sx in (-1, 1):
        p.append(sphere(f"{name}Ear{sx}", (sx * 0.255, 0.0, 2.05), 0.065, skin, scale=(0.45, 0.8, 1.1)))
        if not spec.get("glasses"):
            p.append(sphere(f"{name}Eye{sx}", (sx * 0.09, -0.23, 2.1), 0.045, white, seg=12, rings=8))
            p.append(sphere(f"{name}Pupil{sx}", (sx * 0.09, -0.27, 2.1), 0.024, dark, seg=8, rings=6))
        p.append(cube(f"{name}Brow{sx}", (sx * 0.09, -0.25, 2.17), (0.08, 0.02, 0.022), hair, rot=(0, -sx * 0.12, 0)))
    p.append(cube(f"{name}Mouth", (0, -0.255, 1.95), (0.1, 0.02, 0.018), lip))
    st = spec["style"]
    # hair: a shell slightly larger than the head, pushed inside the face below the hairline
    vol = {"swoop": 1.13, "white": 1.07, "short": 1.06, "neat": 1.09, "slick": 1.08}[st]
    line = {"swoop": 0.1, "white": 0.17, "short": 0.11, "neat": 0.1, "slick": 0.12}[st]
    shell = sphere(f"{name}Hair", (0, 0.025, 2.07), 0.27 * vol, hair, scale=(0.95, 1.0, 1.06), seg=32, rings=18, sub=1)

    def hairline(v, line=line):
        front = v.y < 0.02
        if v.z < -0.14 or (front and v.z < line - 0.25 * max(0.0, -v.y) + 0.0) and v.y < -0.12:
            return v * 0.8
        if v.z < -0.02 and abs(v.x) > 0.16 and v.y < 0.0:
            return v * 0.86
        return v

    deform(shell, hairline)
    p.append(shell)
    if st == "swoop":
        p.append(sphere(f"{name}Swoop", (0.04, -0.15, 2.29), 0.21, hair, scale=(1.5, 0.95, 0.42), rot=(-0.4, 0, 0.12), sub=1))
    if spec.get("beard"):
        beard = sphere(f"{name}Beard", (0, -0.01, 2.02), 0.275, S("Beard", spec["beard"], 0.0, 0.8), scale=(0.97, 0.98, 1.0), sub=1)
        deform(beard, lambda v: Vector((v.x, v.y, min(v.z, -0.02))))
        p.append(beard)
    if spec.get("goatee"):
        p.append(sphere(f"{name}Goatee", (0, -0.21, 1.88), 0.09, S("Goatee", spec["goatee"]), scale=(0.7, 0.6, 1.0)))
    if spec.get("glasses") == "aviator":
        lens = S("Lens", (0.05, 0.06, 0.08), 0.9, 0.05)
        gold = S("Frame", (1, 0.78, 0.35), 1.0, 0.2)
        for sx in (-1, 1):
            p.append(cyl(f"{name}Lens{sx}", (sx * 0.095, -0.265, 2.09), 0.075, 0.015, lens, verts=20, rot=(math.pi / 2, 0, 0)))
        p.append(cyl(f"{name}Bridge", (0, -0.27, 2.12), 0.008, 0.06, gold, rot=(0, math.pi / 2, 0)))
    elif spec.get("glasses") == "wrap":
        p.append(cube(f"{name}Shades", (0, -0.262, 2.1), (0.4, 0.05, 0.08), S("Lens", (0.02, 0.02, 0.03), 0.9, 0.05), bev=0.02))
    if spec.get("smile"):
        p.append(cube(f"{name}Teeth", (0, -0.262, 1.955), (0.08, 0.01, 0.012), white))
    body = join_by_material(p, name + "Body")
    # arms with the pivot at the shoulder so the game can wave them
    arms = []
    for side, sx in (("ArmL", -1), ("ArmR", 1)):
        pivot = empty(f"{name}_{side}", (sx * 0.45, 0, 1.68))
        sleeve = cyl(f"{name}{side}Sleeve", (sx * 0.45, 0, 1.3), 0.1, 0.76, suit if not tshirt else skin, verts=16, r2=0.09)
        cuff = cyl(f"{name}{side}Cuff", (sx * 0.45, 0, 1.6), 0.105, 0.26, suit, verts=16) if tshirt else None
        hand = sphere(f"{name}{side}Hand", (sx * 0.45, -0.02, 0.88), 0.1, skin, scale=(0.9, 1.0, 1.2))
        arm = join_by_material([o for o in (sleeve, cuff, hand) if o], f"{name}{side}")
        parent(arm, pivot)
        arms.append(pivot)
    parent(body + arms, root)
    return root


LEADERS = {
    "Trump": dict(
        skin=(0.95, 0.64, 0.45), suit=(0.09, 0.11, 0.22), tie=(0.8, 0.05, 0.06), tie_len=0.6, hair=(0.93, 0.72, 0.35), style="swoop", face=(0.97, 0.96, 1.04)
    ),
    "Biden": dict(
        skin=(0.95, 0.78, 0.67), suit=(0.11, 0.15, 0.27), tie=(0.15, 0.3, 0.75), hair=(0.95, 0.95, 0.95), style="white", glasses="aviator", smile=True
    ),
    "Zelensky": dict(
        skin=(0.92, 0.74, 0.62), suit=(0.28, 0.32, 0.17), pants=(0.2, 0.22, 0.15), tshirt=True, hair=(0.2, 0.15, 0.11), style="short", beard=(0.2, 0.15, 0.11)
    ),
    "Xi": dict(skin=(0.93, 0.77, 0.6), suit=(0.08, 0.08, 0.1), tie=(0.5, 0.06, 0.1), hair=(0.03, 0.03, 0.03), style="neat", face=(0.98, 0.97, 1.02)),
    "Musk": dict(skin=(0.95, 0.78, 0.68), suit=(0.05, 0.05, 0.06), pants=(0.1, 0.13, 0.2), tshirt=True, hair=(0.12, 0.09, 0.07), style="slick"),
    "McAfee": dict(
        skin=(0.9, 0.7, 0.56),
        suit=(0.08, 0.08, 0.09),
        shirt=(0.95, 0.95, 0.95),
        hair=(0.62, 0.62, 0.62),
        style="slick",
        goatee=(0.75, 0.75, 0.75),
        glasses="wrap",
        chain=True,
    ),
}


def build_characters():
    reset()
    for i, (name, spec) in enumerate(LEADERS.items()):
        r = person(name, spec)
        r.location.x = i * 2.0  # spread out for previews; the game re-positions them
    export("characters.glb")


# --------------------------------------------------------------------------- props
def build_props():
    reset()
    M = common_mats()
    red = mat("OmegaRed", (1, 0.05, 0.1), 0.0, 0.3, emit=(1.0, 0.05, 0.1), strength=8.0)
    dark = mat("DroneShell", (0.06, 0.05, 0.06), 0.8, 0.3)
    # OMEGA drone
    root = empty("Drone")
    p = [sphere("DCore", (0, 0, 0), 0.8, dark, sub=1)]
    eye = sphere("DEye", (0, -0.62, 0), 0.38, red, scale=(1, 0.5, 1))
    p.append(eye)
    p.append(torus("DEyeRing", (0, -0.6, 0), 0.42, 0.06, M["chrome"], rot=(math.pi / 2, 0, 0), maj=24, mino=6))
    for i in range(4):
        a = i / 4 * math.tau + math.pi / 4
        x, y = math.cos(a), math.sin(a)
        p.append(cube(f"DArm{i}", (x * 1.1, y * 1.1, 0), (1.3, 0.16, 0.12), dark, rot=(0, 0, a), bev=0.03))
        p.append(torus(f"DRotor{i}", (x * 1.9, y * 1.9, 0.12), 0.5, 0.05, red, maj=24, mino=6))
        p.append(cyl(f"DMotor{i}", (x * 1.9, y * 1.9, 0.05), 0.14, 0.3, M["steel"], verts=12))
    p.append(cyl("DAntenna", (0, 0.3, 0.9), 0.02, 0.6, M["steel"]))
    parent(join_by_material(p, "Drone"), root)

    # Starship-style rocket, nose towards -Y
    steel = mat("Stainless", (0.82, 0.84, 0.88), 1.0, 0.22)
    root = empty("Rocket")
    prof = [(0.001, -4.7), (0.35, -4.4), (0.7, -3.7), (0.95, -2.6), (1.0, -1.6), (1.0, 3.6), (0.92, 3.8), (0.001, 3.8)]
    body = lathe("RBody", prof, steel, steps=32)
    sel([body])
    body.rotation_euler = (math.pi / 2, 0, 0)
    body.location = (0, 0, 0)
    finish(body)
    p = [body]
    for i, (yy, w) in enumerate(((-2.4, 0.9), (2.6, 1.3))):
        for sx in (-1, 1):
            p.append(cube(f"RFlap{i}{sx}", (sx * 1.25, yy, 0), (0.7 * w, 1.4 * w, 0.06), M["carbon"], bev=0.02))
    for i in range(3):
        a = i / 3 * math.tau
        p.append(cyl(f"RBell{i}", (math.cos(a) * 0.45, 3.95, math.sin(a) * 0.45), 0.25, 0.45, M["steel"], r2=0.15, rot=(math.pi / 2, 0, 0)))
        p.append(cyl(f"RFire{i}", (math.cos(a) * 0.45, 4.2, math.sin(a) * 0.45), 0.22, 0.05, M["exhaust"], rot=(math.pi / 2, 0, 0)))
    parent(join_by_material(p, "Rocket"), root)

    # BCI brain chip
    brain_m = mat("Brain", (1.0, 0.45, 0.75), 0.0, 0.35, emit=(1.0, 0.2, 0.7), strength=1.5)
    root = empty("Brain")
    br = sphere("BrainMesh", (0, 0, 0.15), 0.8, None, scale=(0.9, 1.15, 0.78), seg=48, rings=24)
    tex = bpy.data.textures.new("folds", "VORONOI")
    tex.noise_scale = 0.18
    md = br.modifiers.new("disp", "DISPLACE")
    md.texture = tex
    md.strength = 0.09
    subsurf(br, 1)
    finish(br, brain_m)
    # central fissure
    deform(br, lambda v: Vector((v.x + (0.05 if v.x > 0 else -0.05), v.y, v.z - (0.12 * math.exp(-((v.x * 14) ** 2)) if v.z > 0 else 0))))
    p = [br]
    p.append(cube("BrainChip", (0, 0, -0.55), (1.2, 1.2, 0.12), M["carbon"], bev=0.03))
    for i in range(6):
        p.append(cube(f"BrainTrace{i}", (-0.45 + i * 0.18, 0, -0.48), (0.04, 1.0, 0.02), M["neon"]))
    for sx in (-1, 1):
        for k in range(5):
            p.append(cube(f"Pin{sx}{k}", (sx * 0.66, -0.4 + k * 0.2, -0.58), (0.14, 0.05, 0.04), M["chrome"]))
    parent(join_by_material(p, "Brain"), root)

    # McAfee supply crate with parachute
    olive = mat("CrateOlive", (0.22, 0.27, 0.15), 0.2, 0.6)
    stencil = mat("Stencil", (0.9, 0.85, 0.2), 0.0, 0.5)
    root = empty("Crate")
    p = [cube("CrateBox", (0, 0, 0), (2.3, 2.3, 2.3), olive, bev=0.08, segs=2)]
    for ax in range(3):
        for s in (-1, 1):
            loc = [0, 0, 0]
            loc[ax] = s * 1.16
            size = [2.36, 2.36, 2.36]
            size[ax] = 0.04
            p.append(cube(f"Edge{ax}{s}", tuple(loc), tuple(size), M["steel"], bev=0.0))
    p.append(cube("CratePlate", (0, -1.19, 0.2), (1.6, 0.03, 0.6), stencil))
    p.append(sphere("CrateBeacon", (0, 0, 1.25), 0.15, M["neon"], seg=10, rings=6))
    parent(join_by_material(p, "Crate"), root)
    chute_m = mat("Chute", (1.0, 0.45, 0.1), 0.0, 0.7)
    canopy = sphere("ChuteCanopy", (0, 0, 4.2), 2.6, chute_m, scale=(1, 1, 0.55), seg=16, rings=8)
    deform(canopy, lambda v: Vector((v.x, v.y, max(v.z, 0.0))))
    lines = [
        cyl(
            f"Line{i}",
            (math.cos(i / 6 * math.tau) * 1.3, math.sin(i / 6 * math.tau) * 1.3, 2.6),
            0.015,
            2.9,
            M["steel"],
            verts=4,
            rot=(math.sin(i / 6 * math.tau) * 0.45, -math.cos(i / 6 * math.tau) * 0.45, 0),
        )
        for i in range(6)
    ]
    chute = join([canopy] + lines, "Chute")
    parent([chute], root)

    # McAfee's hover skiff
    hullm = mat("SkiffHull", (0.18, 0.2, 0.25), 0.8, 0.3)
    gold = mat("SkiffGold", (1.0, 0.75, 0.2), 1.0, 0.25)
    root = empty("Skiff")
    hullo = cube("SkiffBody", (0, 0, 0), (4.4, 7.0, 0.5), hullm, sub=2)
    deform(hullo, lambda v: Vector((v.x * (0.6 if v.y < -0.2 else 1.0), v.y, v.z)))
    p = [hullo, cube("SkiffRail", (0, 0.2, 0.55), (4.2, 6.0, 0.08), gold, bev=0.03)]
    for sx in (-1, 1):
        p.append(cyl(f"SkiffJet{sx}", (sx * 1.6, 3.2, -0.1), 0.45, 1.0, M["steel"], rot=(math.pi / 2, 0, 0), r2=0.35))
        p.append(cyl(f"SkiffFire{sx}", (sx * 1.6, 3.72, -0.1), 0.36, 0.04, M["exhaust"], rot=(math.pi / 2, 0, 0)))
    p.append(cube("SkiffNeon", (0, -3.3, 0.1), (1.8, 0.05, 0.1), M["neon"]))
    p.append(cyl("SkiffPost", (0, -1.8, 0.9), 0.06, 1.4, M["steel"]))
    p.append(cube("SkiffConsole", (0, -1.8, 1.6), (0.7, 0.2, 0.35), hullm, bev=0.03, rot=(0.5, 0, 0)))
    parent(join_by_material(p, "Skiff"), root)

    # chrono-portal ring (in the XZ plane, facing -Y)
    frame = mat("PortalFrame", (0.2, 0.23, 0.3), 0.9, 0.3)
    root = empty("Portal")
    p = [torus("PRing", (0, 0, 0), 17, 1.5, frame, rot=(math.pi / 2, 0, 0), maj=96, mino=16)]
    p.append(torus("PInner", (0, 0, 0), 15.6, 0.25, M["neon"], rot=(math.pi / 2, 0, 0), maj=96, mino=8))
    for i in range(24):
        a = i / 24 * math.tau
        p.append(cube(f"PRib{i}", (math.cos(a) * 17, 0, math.sin(a) * 17), (1.2, 3.6, 3.6), frame, rot=(0, -a, 0), bev=0.15))
    emitters = []
    for i in range(12):
        a = i / 12 * math.tau
        e = cube(
            f"Emitter_{i}",
            (math.cos(a) * 18.7, 0, math.sin(a) * 18.7),
            (1.6, 2.2, 0.8),
            mat(f"Emit{i}", (1, 1, 1), 0, 0.3, emit=(1, 1, 1), strength=5),
            rot=(0, -a, 0),
            bev=0.1,
        )
        emitters.append(e)
    for sx in (-1, 1):
        p.append(cube(f"PClamp{sx}", (sx * 9, 0, -16.5), (5, 5, 4), frame, bev=0.4))
    parent(join_by_material(p, "Portal") + emitters, root)

    # asteroids
    rock = mat("Rock", (0.33, 0.31, 0.3), 0.0, 0.9)
    for i in range(4):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1.0, location=(i * 3, 20, 0))
        o = bpy.context.active_object
        o.name = f"Rock_{i}"
        t = bpy.data.textures.new(f"rock{i}", "CLOUDS")
        t.noise_scale = 0.6 + i * 0.15
        md = o.modifiers.new("d", "DISPLACE")
        md.texture = t
        md.strength = 0.45
        o.scale = (1, 0.8 + 0.1 * i, 0.9)
        finish(o, rock, angle=0.6)
    export("props.glb")


# --------------------------------------------------------------------------- the giant printer
def build_printer():
    reset()
    M = common_mats()
    shell = mat("PrinterShell", (0.86, 0.88, 0.92), 0.1, 0.35, coat=0.6)
    trim = mat("PrinterTrim", (0.35, 0.38, 0.45), 0.6, 0.35)
    black = mat("PrinterBlack", (0.03, 0.035, 0.04), 0.3, 0.4)
    paper = mat("Paper", (0.97, 0.96, 0.93), 0.0, 0.8)
    screen = mat("Screen", (0.02, 0.1, 0.05), 0.0, 0.3, emit=(0.2, 1.0, 0.5), strength=1.0)
    plate = mat("Plate", (0.9, 0.9, 0.9), 0.2, 0.4)
    root = empty("Printer")
    p = [cube("PBody", (0, 0, 12.5), (64, 36, 23), shell, bev=1.2, segs=3)]
    p.append(cube("PBase", (0, 0, 0.8), (66, 38, 1.6), trim, bev=0.5))
    p.append(cube("PLid", (0, 1, 26), (65, 36.5, 4), shell, bev=0.8, segs=3))
    p.append(cube("PLidGroove", (0, -17.3, 25.4), (40, 0.6, 0.8), black))
    p.append(cube("PSlot", (0, -18.1, 17), (50, 1.0, 2.6), black, bev=0.3))
    tray = cube("POutTray", (0, -26, 10.5), (48, 18, 0.8), trim, bev=0.3, rot=(-0.15, 0, 0))
    p.append(tray)
    for sx in (-1, 1):
        p.append(cube(f"PTrayArm{sx}", (sx * 23, -21, 11.6), (1.2, 8, 1.4), trim, bev=0.2, rot=(-0.15, 0, 0)))
    # input tray with paper stack at the back
    p.append(cube("PInTray", (0, 21, 33), (54, 1.2, 22), trim, bev=0.4, rot=(-0.55, 0, 0)))
    for k in range(10):
        p.append(
            cube(f"PSheet{k}", (random.uniform(-0.6, 0.6), 19.6 - k * 0.12, 33 + k * 0.08), (48, 0.12, 19), paper, rot=(-0.55, 0, random.uniform(-0.02, 0.02)))
        )
    # control panel
    p.append(cube("PPanel", (22, -19.5, 21), (18, 4, 7), trim, bev=0.6, rot=(0.6, 0, 0)))
    scr = cube("PScreen", (20.5, -21.0, 21.9), (12, 0.4, 5.2), screen, rot=(0.6, 0, 0))
    p.append(scr)
    for k, c in enumerate(((0.2, 1, 0.4), (1, 0.8, 0.1), (1, 0.15, 0.2))):
        p.append(
            cyl(
                f"PBtn{k}",
                (28.5, -21.2 + k * 0.0, 22.8 - k * 1.6),
                0.6,
                0.6,
                mat(f"Btn{k}", c, 0, 0.3, emit=c, strength=4),
                rot=(0.6 + math.pi / 2, 0, 0),
                verts=16,
            )
        )
    # ink tanks (glass + glowing ink)
    glass = mat("InkGlass", (0.8, 0.9, 1.0), 0.0, 0.05, alpha=0.3)
    inks = [("Ink_C", (0.0, 0.75, 1.0)), ("Ink_M", (1.0, 0.1, 0.6)), ("Ink_Y", (1.0, 0.85, 0.0)), ("Ink_K", (0.05, 0.05, 0.07))]
    for k, (nm, c) in enumerate(inks):
        y = -10 + k * 6.5
        p.append(cyl(f"Tank{k}", (-33.5, y, 11), 2.5, 16, glass, verts=24))
        p.append(cyl(f"Liquid{k}", (-33.5, y, 9), 2.2, 11, mat(nm, c, 0, 0.2, emit=c, strength=2.5 if nm != "Ink_K" else 0.2), verts=24))
        p.append(cyl(f"TankCap{k}", (-33.5, y, 19.3), 2.7, 1.2, trim, verts=24, bev=0.2))
        p.append(cyl(f"TankHose{k}", (-32.4, y, 21), 0.35, 4, black, rot=(0, math.pi / 2.4, 0)))
    # vents
    for sx in (-1, 1):
        for k in range(8):
            p.append(cube(f"Vent{sx}{k}", (sx * 32.1, 2 + k * 1.6, 15), (0.4, 0.7, 7), black))
    p.append(cube("PPlate", (-8, -18.15, 6.5), (40, 0.3, 5), plate))
    for k in range(5):
        p.append(sphere(f"PLed{k}", (12 + k * 2.4, -18.4, 13.5), 0.5, M["neon"], seg=10, rings=6))
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(cyl(f"PFoot{sx}{sy}", (sx * 30, sy * 16, -0.6), 1.8, 1.2, M["rubber"], verts=16))
    parent(join_by_material(p, "Printer"), root)
    export("printer.glb")


# --------------------------------------------------------------------------- Bunker-0 (world coordinates)
def B(x, y, z):
    """three.js world coords -> Blender coords."""
    return (x, -z, y)


def bbox(name, x0, x1, y0, y1, z0, z1, m, bev=0.0):
    return cube(name, B((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, z1 - z0, y1 - y0), m, bev=bev)


def build_bunker():
    reset()
    hull = mat("BunkerHull", (0.2, 0.23, 0.29), 0.75, 0.42)
    plate = mat("BunkerPlate", (0.28, 0.31, 0.37), 0.6, 0.5)
    dark = mat("BunkerDark", (0.07, 0.08, 0.1), 0.5, 0.55)
    amber = mat("Hazard", (1.0, 0.62, 0.0), 0.0, 0.4, emit=(1.0, 0.55, 0.0), strength=2.5)
    window = mat("Window", (1, 0.85, 0.6), 0, 0.3, emit=(1.0, 0.78, 0.5), strength=5.0)
    lamp = mat("Lamp", (1, 0.9, 0.75), 0, 0.3, emit=(1.0, 0.85, 0.65), strength=10.0)
    thr = mat("Thruster", (0.5, 0.8, 1), 0, 0.3, emit=(0.35, 0.7, 1.0), strength=12.0)
    red = mat("Beacon", (1, 0.1, 0.1), 0, 0.3, emit=(1, 0.08, 0.1), strength=10.0)
    steel = mat("Steel", (0.55, 0.58, 0.62), 0.9, 0.35)
    X0, X1, Y0, Y1, Z0, Z1 = -165, 145, -54, 26, 222, 350
    p = []
    p.append(bbox("Floor", X0, X1, Y0 - 5, Y0, Z0, Z1, dark, 0.6))
    p.append(bbox("Roof", X0 - 2, X1 + 2, Y1, Y1 + 6, Z0 - 2, Z1 + 2, hull, 1.2))
    p.append(bbox("North", X0, X1, Y0, Y1, Z0 - 5, Z0, hull, 0.8))
    p.append(bbox("South", X0, X1, Y0, Y1, Z1, Z1 + 5, hull, 0.8))
    for x, zA, zB in ((X0, 280, 318), (X1, 276, 316)):
        xa, xb = x - 2.5, x + 2.5
        p.append(bbox("WLow", xa, xb, Y0, -46, Z0, Z1, hull, 0.4))
        p.append(bbox("WHigh", xa, xb, -1, Y1, Z0, Z1, hull, 0.4))
        p.append(bbox("WA", xa, xb, -46, -1, Z0, zA, hull, 0.4))
        p.append(bbox("WB", xa, xb, -46, -1, zB, Z1, hull, 0.4))
        # hangar frame
        for a0, a1, b0, b1 in ((-48, -45, zA - 3, zB + 3), (-2, 1, zA - 3, zB + 3)):
            p.append(bbox("FrameH", xa - 1.5, xb + 1.5, a0, a1, b0, b1, plate, 0.3))
        for zz in (zA - 1.5, zB + 1.5):
            p.append(bbox("FrameV", xa - 1.5, xb + 1.5, -48, 1, zz - 1.5, zz + 1.5, plate, 0.3))
        p.append(bbox("FrameGlow", xa - 1.7, xb + 1.7, -1.2, -0.4, zA, zB, amber))
        p.append(bbox("FrameGlow2", xa - 1.7, xb + 1.7, -46, -45.2, zA, zB, amber))
    # exterior armour plates and greebles
    for side, zf in ((-1, Z0 - 5), (1, Z1 + 5)):
        for k in range(14):
            x = X0 + 12 + k * 21.5
            p.append(bbox("Armor", x - 9.5, x + 9.5, -50, 22, zf - (1.2 if side < 0 else 0), zf + (1.2 if side > 0 else 0), plate, 0.5))
        for k in range(60):
            x = random.uniform(X0 + 6, X1 - 6)
            y = random.uniform(-48, 20)
            w, h, d = random.uniform(2, 9), random.uniform(1, 5), random.uniform(0.8, 2.5)
            zz = zf + side * (1.2 + d / 2)
            p.append(bbox("Greeble", x - w / 2, x + w / 2, y - h / 2, y + h / 2, zz - d / 2, zz + d / 2, random.choice((hull, dark, plate)), 0.15))
        for k in range(36):
            x = random.uniform(X0 + 8, X1 - 8)
            y = random.choice((-38, -22, -6, 10))
            zz = zf + side * 1.4
            p.append(bbox("Window", x - random.uniform(2, 6), x + random.uniform(2, 6), y, y + 1.4, zz - 0.3, zz + 0.3, window))
        # horizontal pipes
        for y in (-44, 16):
            p.append(cyl("Pipe", B((X0 + X1) / 2, y, zf + side * 1.8), 0.9, X1 - X0 - 10, steel, verts=12, rot=(0, math.pi / 2, 0)))
    # roof greebles, vents, antenna masts, beacons
    for k in range(70):
        x = random.uniform(X0 + 8, X1 - 8)
        z = random.uniform(Z0 + 6, Z1 - 6)
        w, h, d = random.uniform(3, 14), random.uniform(1, 6), random.uniform(3, 14)
        p.append(bbox("RoofG", x - w / 2, x + w / 2, Y1 + 6, Y1 + 6 + h, z - d / 2, z + d / 2, random.choice((hull, dark, plate)), 0.3))
    for x, z, hgt in ((-120, 240, 60), (80, 330, 45), (10, 236, 80), (-30, 340, 35)):
        p.append(cyl("Mast", B(x, Y1 + 6 + hgt / 2, z), 1.0, hgt, steel, verts=8, r2=0.4))
        for k in range(3):
            p.append(cube("Cross", B(x, Y1 + 12 + k * hgt / 4, z), (10 - k * 2.5, 0.4, 0.4), steel))
        p.append(sphere("BeaconTip", B(x, Y1 + 7 + hgt, z), 1.0, red, seg=10, rings=6))
    # thrusters underneath (the bunker floats)
    for x in (-120, -40, 40, 110):
        for z in (250, 325):
            prof = [(5.5, 0), (6.5, -2), (8.5, -9), (9.5, -12), (9.0, -12.4), (7.5, -9.5), (5.0, -2.5), (4.5, -0.3)]
            p.append(lathe("Nozzle", prof, steel, steps=32, loc=B(x, Y0 - 5, z)))
            p.append(cyl("Glow", B(x, Y0 - 13, z), 7.2, 0.5, thr, verts=32))
            p.append(cyl("Mount", B(x, Y0 - 5.5, z), 6.5, 2, dark, verts=16))
    # interior: lamps, ceiling trusses, columns, wall pipes
    for x in range(X0 + 20, X1 - 5, 30):
        p.append(bbox("Lamp", x - 7, x + 7, Y1 - 1.5, Y1 - 0.8, 297, 303, lamp))
        p.append(bbox("Lamp", x - 7, x + 7, Y1 - 1.5, Y1 - 0.8, 247, 253, lamp))
        p.append(bbox("Truss", x - 1, x + 1, Y1 - 4, Y1, Z0, Z1, plate, 0.2))
    for z in (229, 343):
        for x in range(X0 + 25, X1 - 10, 45):
            if -125 < x < -45 and z < 280:
                continue
            p.append(bbox("Column", x - 2, x + 2, Y0, Y1, z - 2, z + 2, plate, 0.3))
            p.append(bbox("ColLight", x - 2.2, x + 2.2, -40, -38.5, z - 2.2, z + 2.2, amber))
    for z, side in ((Z0 + 1.5, 1), (Z1 - 1.5, -1)):
        for y in (-36, -30, 8):
            p.append(cyl("WallPipe", B((X0 + X1) / 2, y, z), 0.7, X1 - X0 - 6, steel, verts=10, rot=(0, math.pi / 2, 0)))
    # floor grating stripes
    for x in range(X0 + 10, X1, 12):
        p.append(bbox("Grate", x - 0.3, x + 0.3, Y0 + 0.05, Y0 + 0.25, Z0 + 2, Z1 - 2, plate))
    # hologram projector pad for Musk
    p.append(cyl("HoloPad", B(45, -42.6, 334), 6.5, 1.2, plate, verts=32, bev=0.3))
    p.append(torus("HoloRing", B(45, -41.9, 334), 6.0, 0.18, thr, maj=48, mino=6))
    merged = join_by_material(p, "Bunker")
    root = empty("Bunker")
    parent(merged, root)
    # radar dish on its own node so it can rotate
    dish_root = empty("Dish", B(-60, Y1 + 6, 330))
    d = []
    bowl = sphere("Bowl", B(-60, Y1 + 20, 330), 15, steel, seg=32, rings=16)
    deform(bowl, lambda v: Vector((v.x, v.y, min(v.z, -9.0))))
    sel([bowl])
    bowl.rotation_euler = (1.0, 0, 0)
    finish(bowl)
    d.append(bowl)
    d.append(cyl("DishMast", B(-60, Y1 + 12, 330), 1.2, 12, dark, verts=12))
    d.append(cyl("Feed", B(-60, Y1 + 22, 324), 0.4, 10, steel, verts=8, rot=(0.6, 0, 0)))
    dm = join_by_material(d, "Dish")
    parent(dm, dish_root)
    parent([dish_root], root)
    export("bunker.glb")


if __name__ == "__main__":
    build_kart()
    build_saucers()
    build_characters()
    build_props()
    build_printer()
    build_bunker()
