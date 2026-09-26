#!/usr/bin/env python3
"""
JSON_to_RBXLX.py
Convert a Vortex/plugin JSON file back into a Roblox .rbxlx XML place file.

Handles textures, lights, and all script types. Works with any version
of settings.py.

Usage:
    py JSON_to_RBXLX.py input.json [output.rbxlx] [--verbose]
"""

import sys
import json
import random
import struct
from pathlib import Path
import xml.etree.ElementTree as ET

# =========================================================
#  IMPORT SETTINGS (any folder layout)
# =========================================================
_HERE = Path(__file__).resolve().parent
for _cand in (_HERE.parent, _HERE):
    if (_cand / "settings.py").exists():
        sys.path.insert(0, str(_cand))
        break
import settings


def _get(name, default):
    return getattr(settings, name, default)


def map_to_roblox(mat):
    """Return the Roblox material name for a Vortex material name."""
    for fn_name in ("map_to_roblox", "map_material_to_roblox"):
        fn = getattr(settings, fn_name, None)
        if callable(fn):
            try:
                return fn(mat)
            except Exception:
                pass
    for d_name in ("VORTEX_MATERIALS_CONVERTION", "VORTEX_TO_ROBLOX_MATERIALS"):
        d = getattr(settings, d_name, None)
        if isinstance(d, dict):
            return d.get(mat, "Plastic")
    return "Plastic"


SAVE_LIGHTING = _get("SAVE_LIGHTING", True)
IGNORE_MODELS = _get("IGNORE_MODELS", False)
IGNORE_SCRIPTS = _get("IGNORE_SCRIPTS", False)


# =========================================================
#  CONSTANTS
# =========================================================
ROBLOX_MATERIAL_TOKENS = {
    "Plastic":        256,
    "Wood":           512,
    "Slate":          288,
    "Concrete":       304,
    "CorrodedMetal":  320,
    "DiamondPlate":   336,
    "Foil":          1072,
    "Grass":         1280,
    "Ice":           1536,
    "Marble":         400,
    "Granite":        416,
    "Brick":          432,
    "Pebble":         448,
    "Sand":           464,
    "Fabric":         480,
    "SmoothPlastic":  272,
    "Metal":         1088,
    "WoodPlanks":     528,
    "Cobblestone":    544,
    "Rock":           592,
    "Glacier":        608,
    "Snow":           624,
    "Sandstone":      640,
    "Mud":            656,
    "Basalt":         672,
    "Ground":         688,
    "CrackedLava":    704,
    "Asphalt":        720,
    "LeafyGrass":     736,
    "Salt":           752,
    "Limestone":      768,
    "Pavement":       784,
    "ForceField":     800,
    "Neon":           816,
    "Glass":          832,
    "Plaster":        848,
    "Carpet":         864,
    "CeramicTiles":   880,
    "ClayRoofTiles":  896,
    "RoofShingles":   912,
    "Cardboard":      928,
}

FACE_TO_NORMAL = {
    "Front": 4, "Back": 2, "Top": 1,
    "Bottom": 5, "Left": 3, "Right": 0,
}

TEXTURE_TO_SURFACE = {"Studs": 3, "Inlets": 4}

SURFACE_PROPS = {
    "Front":  "FrontSurface",
    "Back":   "BackSurface",
    "Top":    "TopSurface",
    "Bottom": "BottomSurface",
    "Left":   "LeftSurface",
    "Right":  "RightSurface",
}

SHAPE_TO_ROBLOX_TOKEN = {
    "Ball":     0,
    "Block":    1,
    "Cylinder": 2,
}

ROBLOX_ROOT_ATTRS = {
    "xmlns:xmime": "http://www.w3.org/2005/05/xmlmime",
    "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "xsi:noNamespaceSchemaLocation": "http://www.roblox.com/roblox.xsd",
    "version": "4",
}

VORTEX_FACE_NAMES  = ["Right", "Top", "Back", "Left", "Front", "Bottom"]
VORTEX_KIND_NAMES  = {0: "Studs", 1: "Inlets"}


# =========================================================
#  CHILD BLOB DECODER
# =========================================================
def parse_child_blob(hex_str):
    """Decode a part's child_blob_hex into textures + lights + truss."""
    if not hex_str or not isinstance(hex_str, str):
        return [], [], [], [], False

    try:
        b = [int(tok, 16) for tok in hex_str.split()]
    except ValueError:
        return [], [], [], [], False

    if len(b) < 10:
        return [], [], [], [], False

    truss     = bool(b[1])
    tex_count = b[2]

    textures = []
    pos = 10
    for _ in range(tex_count):
        if pos + 8 > len(b):
            break
        face_idx = b[pos]
        kind_idx = b[pos + 4]
        face_name = VORTEX_FACE_NAMES[face_idx] if 0 <= face_idx < 6 else "Front"
        kind_name = VORTEX_KIND_NAMES.get(kind_idx, "Studs")
        textures.append({"face": face_name, "kind": kind_name})
        pos += 8

    def rf(off):
        if off + 4 > len(b):
            return 0.0
        return struct.unpack("<f", bytes(b[off:off + 4]))[0]

    def ru(off):
        if off + 4 > len(b):
            return 0
        return struct.unpack("<I", bytes(b[off:off + 4]))[0]

    points, spots, surfaces = [], [], []

    while pos < len(b):
        b1 = b[pos]
        b2 = b[pos + 1] if pos + 1 < len(b) else 0

        if b1 == 1 and pos + 25 <= len(b):
            points.append({
                "color":      {"r": round(rf(pos + 1), 3),
                               "g": round(rf(pos + 5), 3),
                               "b": round(rf(pos + 9), 3)},
                "brightness": round(rf(pos + 17) / 1500000.0, 3),
                "range":      round(rf(pos + 21), 3),
                "enabled":    True,
            })
            pos += 25

        elif b1 == 0 and b2 == 1 and pos + 34 <= len(b):
            face_id   = ru(pos + 30)
            face_name = VORTEX_FACE_NAMES[face_id] if 0 <= face_id < 6 else "Front"
            surfaces.append({
                "color":      {"r": round(rf(pos + 2), 3),
                               "g": round(rf(pos + 6), 3),
                               "b": round(rf(pos + 10), 3)},
                "brightness": round(rf(pos + 18) / 1500000.0, 3),
                "range":      round(rf(pos + 22), 3),
                "angle":      round(rf(pos + 26), 3),
                "face":       face_name,
                "enabled":    True,
            })
            pos += 34

        else:
            pos += 1

    return textures, points, spots, surfaces, truss


def enrich_part_from_blob(obj):
    """Populate structured fields from child_blob_hex if missing."""
    has_tex = bool(obj.get("textures"))
    has_pts = bool(obj.get("point_lights"))
    has_sps = bool(obj.get("spot_lights"))
    has_sur = bool(obj.get("surface_lights"))

    if has_tex and has_pts and has_sps and has_sur:
        return

    blob = obj.get("child_blob_hex")
    if not blob:
        return

    textures, points, spots, surfaces, truss = parse_child_blob(blob)

    if not has_tex and textures:   obj["textures"]       = textures
    if not has_pts and points:     obj["point_lights"]   = points
    if not has_sps and spots:      obj["spot_lights"]    = spots
    if not has_sur and surfaces:   obj["surface_lights"] = surfaces
    if truss:                      obj["truss"]          = True


# =========================================================
#  XML HELPERS
# =========================================================
def new_referent():
    return "RBX" + "".join(random.choice("0123456789ABCDEF") for _ in range(32))


def quat_to_matrix(qx, qy, qz, qw):
    return [
        [1 - 2*qy*qy - 2*qz*qz, 2*qx*qy - 2*qz*qw, 2*qx*qz + 2*qy*qw],
        [2*qx*qy + 2*qz*qw,     1 - 2*qx*qx - 2*qz*qz, 2*qy*qz - 2*qx*qw],
        [2*qx*qz - 2*qy*qw,     2*qy*qz + 2*qx*qw,     1 - 2*qx*qx - 2*qy*qy],
    ]


def encode_color3uint8(r, g, b):
    ri = int(round(max(0.0, min(1.0, r)) * 255))
    gi = int(round(max(0.0, min(1.0, g)) * 255))
    bi = int(round(max(0.0, min(1.0, b)) * 255))
    return (0xFF << 24) | (ri << 16) | (gi << 8) | bi


def add_string(parent, name, value):
    ET.SubElement(parent, "string", {"name": name}).text = str(value)


def add_bool(parent, name, value):
    ET.SubElement(parent, "bool", {"name": name}).text = "true" if value else "false"


def add_float(parent, name, value):
    ET.SubElement(parent, "float", {"name": name}).text = str(float(value))


def add_token(parent, name, value):
    ET.SubElement(parent, "token", {"name": name}).text = str(int(value))


def add_vector3(parent, name, x, y, z):
    el = ET.SubElement(parent, "Vector3", {"name": name})
    ET.SubElement(el, "X").text = str(float(x))
    ET.SubElement(el, "Y").text = str(float(y))
    ET.SubElement(el, "Z").text = str(float(z))


def add_cframe(parent, name, pos, quat):
    el = ET.SubElement(parent, "CoordinateFrame", {"name": name})
    ET.SubElement(el, "X").text = str(float(pos[0]))
    ET.SubElement(el, "Y").text = str(float(pos[1]))
    ET.SubElement(el, "Z").text = str(float(pos[2]))
    m = quat_to_matrix(quat[0], quat[1], quat[2], quat[3])
    for i in range(3):
        for j in range(3):
            ET.SubElement(el, f"R{i}{j}").text = str(float(m[i][j]))


def add_color3uint8(parent, name, r, g, b):
    ET.SubElement(parent, "Color3uint8", {"name": name}).text = str(encode_color3uint8(r, g, b))


def add_color3(parent, name, r, g, b):
    el = ET.SubElement(parent, "Color3", {"name": name})
    ET.SubElement(el, "R").text = str(float(r))
    ET.SubElement(el, "G").text = str(float(g))
    ET.SubElement(el, "B").text = str(float(b))


def add_protected_string(parent, name, value):
    ET.SubElement(parent, "ProtectedString", {"name": name}).text = str(value)


# =========================================================
#  PART / SCRIPT PROPERTIES
# =========================================================
def build_part_props(props, obj):
    add_string(props, "Name", obj.get("name", "Part"))

    pos   = obj.get("position", [0, 0, 0])
    quat  = obj.get("rotation", [0, 0, 0, 1])
    size  = obj.get("size", [1, 1, 1])
    col   = obj.get("color", {"r": 0.5, "g": 0.5, "b": 0.5})
    flags = obj.get("flags", [0, 1, 1, 1, 0, 0])

    add_cframe(props, "CFrame", pos, quat)
    add_vector3(props, "size", size[0], size[1], size[2])
    add_color3uint8(props, "Color3uint8",
                    col.get("r", 0.5), col.get("g", 0.5), col.get("b", 0.5))

    transparency = obj.get("transparency")
    if transparency is None:
        transparency = 1.0 - col.get("a", 1.0)
    add_float(props, "Transparency", transparency)

    mat_name   = obj.get("material", "Plastic")
    roblox_mat = map_to_roblox(mat_name)
    add_token(props, "Material", ROBLOX_MATERIAL_TOKENS.get(roblox_mat, 256))

    add_bool(props, "CastShadow", flags[1] == 1)
    add_bool(props, "Anchored",   flags[2] == 1)
    add_bool(props, "CanCollide", flags[3] == 1)
    add_bool(props, "Locked",     flags[5] == 1)

    # Surfaces — default Smooth, override from textures
    surfaces = {face: 0 for face in SURFACE_PROPS}
    for t in obj.get("textures") or []:
        face = t.get("face")
        kind = t.get("kind")
        if face in SURFACE_PROPS and kind in TEXTURE_TO_SURFACE:
            surfaces[face] = TEXTURE_TO_SURFACE[kind]
    for face, token in surfaces.items():
        add_token(props, SURFACE_PROPS[face], token)

    add_bool(props,  "CanQuery",      True)
    add_bool(props,  "CanTouch",      True)
    add_float(props, "Reflectance",   0.0)

    shape = obj.get("shape", "Block")
    add_token(props, "shape",         SHAPE_TO_ROBLOX_TOKEN.get(shape, 1))
    add_token(props, "formFactorRaw", 1)


def build_script_props(props, obj):
    add_string(props, "Name", obj.get("name", "Script"))
    add_protected_string(props, "Source", obj.get("source", ""))
    add_bool(props, "Disabled", not obj.get("enabled", True))
    add_token(props, "RunContext", 0)


# =========================================================
#  LIGHT ITEMS
# =========================================================
def build_point_light_item(data):
    item = ET.Element("Item", {"class": "PointLight", "referent": new_referent()})
    props = ET.SubElement(item, "Properties")
    c = data.get("color", {"r": 1, "g": 1, "b": 1})
    add_color3(props, "Color",      c.get("r", 1.0), c.get("g", 1.0), c.get("b", 1.0))
    add_float(props,  "Brightness", data.get("brightness", 1.0))
    add_float(props,  "Range",      data.get("range", 8.0))
    add_bool(props,   "Enabled",    data.get("enabled", True))
    add_bool(props,   "Shadows",    False)
    add_string(props, "Name",       "PointLight")
    return item


def build_spot_light_item(data, class_name="SpotLight"):
    item = ET.Element("Item", {"class": class_name, "referent": new_referent()})
    props = ET.SubElement(item, "Properties")
    c = data.get("color", {"r": 1, "g": 1, "b": 1})
    add_color3(props, "Color",      c.get("r", 1.0), c.get("g", 1.0), c.get("b", 1.0))
    add_float(props,  "Brightness", data.get("brightness", 1.0))
    add_float(props,  "Range",      data.get("range", 8.0))
    add_float(props,  "Angle",      data.get("angle", 90.0))
    add_token(props,  "Face",       FACE_TO_NORMAL.get(data.get("face", "Front"), 4))
    add_bool(props,   "Enabled",    data.get("enabled", True))
    add_bool(props,   "Shadows",    False)
    add_string(props, "Name",       class_name)
    return item


def add_lights_to_part(item, obj):
    for light in obj.get("point_lights") or []:
        item.append(build_point_light_item(light))
    for light in obj.get("spot_lights") or []:
        item.append(build_spot_light_item(light, "SpotLight"))
    for light in obj.get("surface_lights") or []:
        item.append(build_spot_light_item(light, "SurfaceLight"))


# =========================================================
#  ITEM BUILDERS
# =========================================================
def build_service_item(cls, name):
    item = ET.Element("Item", {"class": cls, "referent": new_referent()})
    props = ET.SubElement(item, "Properties")
    add_string(props, "Name", name)
    return item


def build_item(obj):
    kind = obj.get("kind")

    if kind == "group":
        item = ET.Element("Item", {"class": "Model", "referent": new_referent()})
        props = ET.SubElement(item, "Properties")
        add_string(props, "Name", obj.get("name", "Model"))
        return item

    if kind == "part":
        cls = "Part"
        flags = obj.get("flags", [0] * 6)
        if len(flags) > 4 and flags[4] == 1:
            cls = "SpawnLocation"
        elif obj.get("truss"):
            cls = "TrussPart"
        item = ET.Element("Item", {"class": cls, "referent": new_referent()})
        props = ET.SubElement(item, "Properties")
        build_part_props(props, obj)
        add_lights_to_part(item, obj)
        return item

    if kind == "script":
        cls = obj.get("class", "Script")
        item = ET.Element("Item", {"class": cls, "referent": new_referent()})
        props = ET.SubElement(item, "Properties")
        build_script_props(props, obj)
        return item

    return None


# =========================================================
#  TREE WALK
# =========================================================
def build_children_map(objects):
    children = {}
    for idx, obj in enumerate(objects):
        if obj.get("kind") == "service":
            continue
        pid = obj.get("parent_id")
        if pid is None:
            pid = 0
        children.setdefault(int(pid), []).append(idx)
    return children


def emit_children(parent_idx, parent_xml, objects, children):
    for child_idx in children.get(parent_idx, []):
        obj = objects[child_idx]
        item = build_item(obj)
        if item is None:
            continue
        parent_xml.append(item)
        emit_children(child_idx, item, objects, children)


# =========================================================
#  FILTERS
# =========================================================
def flatten_parents(objects):
    """No part or group may have a part as its parent."""
    for o in objects:
        kind = o.get("kind")
        if kind not in ("part", "group"):
            continue
        pid = o.get("parent_id")
        seen = set()
        while pid is not None and pid not in seen and 0 <= pid < len(objects):
            seen.add(pid)
            parent_obj = objects[pid]
            if parent_obj.get("kind") != "part":
                break
            pid = parent_obj.get("parent_id")
        o["parent_id"] = pid if pid is not None else 0


def apply_filters(objects):
    objects = list(objects)

    # Safety pass: nothing may have a part as parent
    flatten_parents(objects)

    if IGNORE_MODELS:
        remap = {}
        for i, o in enumerate(objects):
            if o.get("kind") == "group":
                remap[i] = o.get("parent_id", 0)
        for i in list(remap.keys()):
            p = remap[i]
            seen = set()
            while p in remap and p not in seen:
                seen.add(p)
                p = remap[p]
            remap[i] = p
        for o in objects:
            pid = o.get("parent_id")
            if pid in remap:
                o["parent_id"] = remap[pid]
        objects = [o for o in objects if o.get("kind") != "group"]

    if IGNORE_SCRIPTS:
        objects = [o for o in objects if o.get("kind") != "script"]

    return objects


# =========================================================
#  MAIN
# =========================================================
def run(json_data):
    # Merge scripts array into objects if they aren't there already
    objects_in = list(json_data.get("objects", []))
    scripts_arr = json_data.get("scripts", []) or []

    def looks_like_script(o):
        return o.get("kind") == "script" or o.get("class") in (
            "Script", "LocalScript", "ModuleScript",
            "RemoteEvent", "RemoteFunction", "BindableEvent"
        )

    for s in scripts_arr:
        if looks_like_script(s) and s not in objects_in:
            objects_in.append(s)

    objects = apply_filters(objects_in)

    # Decode textures & lights from child_blob_hex for every part
    for o in objects:
        if o.get("kind") == "part":
            enrich_part_from_blob(o)

    root = ET.Element("roblox", ROBLOX_ROOT_ATTRS)
    ET.SubElement(root, "External").text = "null"
    ET.SubElement(root, "External").text = "nil"

    ws      = build_service_item("Workspace",               "Workspace")
    lt      = build_service_item("Lighting",                "Lighting")
    rs      = build_service_item("ReplicatedStorage",       "ReplicatedStorage")
    sss     = build_service_item("ServerScriptService",     "ServerScriptService")
    sp      = build_service_item("StarterPlayer",           "StarterPlayer")
    sps     = build_service_item("StarterPlayerScripts",    "StarterPlayerScripts")
    spc     = build_service_item("StarterCharacterScripts", "StarterCharacterScripts")
    players = build_service_item("Players",                 "Players")

    sp.append(sps)
    sp.append(spc)
    root.extend([ws, lt, rs, sss, sp, players])

    service_xml = {0: ws, 1: lt, 2: rs, 3: sss, 4: sps}

    # Lighting
    if SAVE_LIGHTING:
        lighting = json_data.get("lighting") or {}
        lt_props = lt.find("Properties")
        amb = lighting.get("ambient_color", {"r": 0.5, "g": 0.5, "b": 0.5})
        sun = lighting.get("sun_color",     {"r": 1.0, "g": 1.0, "b": 1.0})
        add_color3(lt_props, "Ambient",        amb.get("r", 0.5), amb.get("g", 0.5), amb.get("b", 0.5))
        add_color3(lt_props, "OutdoorAmbient", sun.get("r", 1.0), sun.get("g", 1.0), sun.get("b", 1.0))
        raw_br = float(lighting.get("sun_brightness", 2000))
        brightness = max(0.0, min(10.0, (raw_br / 1000.0 - 1) / 2))
        add_float(lt_props, "Brightness",    brightness)
        add_bool(lt_props,  "GlobalShadows", lighting.get("sun_shadows", True))
        add_token(lt_props, "Technology",    3)

    children = build_children_map(objects)
    for svc_idx, svc_xml in service_xml.items():
        emit_children(svc_idx, svc_xml, objects, children)

    return root, objects


# =========================================================
#  ENTRY
# =========================================================
if __name__ == "__main__":
    args  = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    verbose = any(f in ("-v", "--verbose") for f in flags)

    if not args:
        print("Usage: py JSON_to_RBXLX.py input.json [output.rbxlx] [--verbose]")
        sys.exit(1)

    in_path  = Path(args[0])
    out_path = Path(args[1]) if len(args) > 1 else in_path.with_suffix(".rbxlx")

    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    root, objects = run(data)

    try:
        ET.indent(root, space="\t")
    except AttributeError:
        pass

    ET.ElementTree(root).write(out_path, encoding="utf-8", xml_declaration=False)

    parts   = sum(1 for o in objects if o.get("kind") == "part")
    scripts = sum(1 for o in objects if o.get("kind") == "script")
    groups  = sum(1 for o in objects if o.get("kind") == "group")
    lights  = 0
    texs    = 0
    trusses = 0
    for o in objects:
        if o.get("kind") == "part":
            lights  += len(o.get("point_lights") or [])
            lights  += len(o.get("spot_lights") or [])
            lights  += len(o.get("surface_lights") or [])
            texs    += len(o.get("textures") or [])
            if o.get("truss"):
                trusses += 1

    print(f"Saved: {out_path}")
    print(f"  services : 5")
    print(f"  parts    : {parts}")
    print(f"  groups   : {groups}")
    print(f"  scripts  : {scripts}")
    print(f"  lights   : {lights}")
    print(f"  textures : {texs}")
    print(f"  trusses  : {trusses}")

    if verbose:
        print("\n" + "=" * 60)
        with open(out_path, "r", encoding="utf-8") as f:
            print(f.read())
        print("=" * 60)
