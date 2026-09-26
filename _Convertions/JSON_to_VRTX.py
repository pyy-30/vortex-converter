import io
import json
import math
import struct
import sys
from pathlib import Path
import zstandard as zstd

_CONVERTER_DIR = Path(__file__).resolve().parent

# Look for settings.py in the main project folder first, then fall back
# to the same folder as this converter.
for _candidate in (_CONVERTER_DIR.parent, _CONVERTER_DIR):
    if (_candidate / "settings.py").exists():
        sys.path.insert(0, str(_candidate))
        break
import settings


# =========================================================
#  VERSIONING
# =========================================================
SUPPORTED_JSON_VERSION     = 1
CONTAINER_VERSION_TO_WRITE = 4
DOWNLOAD_URL = "https://github.com/pyy-30/vortex-converter/releases/latest"


def _check_json_version(data):
    v = int(data.get("version", 1))
    if v < SUPPORTED_JSON_VERSION:
        raise SystemExit(
            f"[JSON] File version {v} is older than this converter supports "
            f"({SUPPORTED_JSON_VERSION}).\n"
            f"  This JSON was produced by an older plugin or converter.\n"
            f"  Regenerate it with the current plugin."
        )
    if v > SUPPORTED_JSON_VERSION:
        raise SystemExit(
            f"[JSON] File version {v} is newer than this converter supports "
            f"({SUPPORTED_JSON_VERSION}).\n"
            f"  Download a newer converter: {DOWNLOAD_URL}"
        )


# =========================================================
#  CONSTANTS
# =========================================================
MATERIAL_NAMES = {
    "Smooth": 0, "Plastic": 1, "Wood": 2, "Metal": 3,
    "Grass": 4, "Ice": 5, "Paint": 6,
}
DEFAULT_SCRIPT_TRAILING = {
    7:  "01 00 00 00 00 00 00 00 00 00",
    8:  "01 00 00 00 00 00 00 00 00 00",
    9:  "01 00 00 00 00 00 00 00 00 00",   # ModuleScript
    13: "00",
    14: "00",
    15: "00",
}

DEFAULT_CHILD_BLOB = "00 " * 24
SCRIPT_MARKER_BYTES_SCRIPT = 0x01000000
SCRIPT_MARKER_BYTES_REMOTE = 0


def normalize_marker(marker, type_id):
    default = SCRIPT_MARKER_BYTES_SCRIPT if type_id in (7, 8, 9) else SCRIPT_MARKER_BYTES_REMOTE
    if marker is None:
        return default
    marker = int(marker)
    if marker == 1:
        return SCRIPT_MARKER_BYTES_SCRIPT
    if marker == 0:
        return SCRIPT_MARKER_BYTES_REMOTE
    return marker


# =========================================================
#  SHAPE RASTERIZATION
# =========================================================
def rasterize_shape(obj):
    shape = obj.get("shape", "Block")
    if shape in ("Block", None):
        return [obj]

    pos  = obj.get("position", [0, 0, 0])
    rot  = obj.get("rotation", [0, 0, 0, 1])
    size = obj.get("size", [1, 1, 1])

    acc = max(1, int(settings.CUSTOM_SHAPES_ACCURACY))
    longest = max(size)
    if longest <= 0:
        return [obj]

    nx = max(1, int(round(acc * size[0] / longest)))
    ny = max(1, int(round(acc * size[1] / longest)))
    nz = max(1, int(round(acc * size[2] / longest)))

    while nx * ny * nz > settings.MAX_BLOCKS_PER_SHAPE:
        if nx >= ny and nx >= nz and nx > 1:    nx -= 1
        elif ny >= nz and ny > 1:               ny -= 1
        elif nz > 1:                            nz -= 1
        else:                                   break

    bsx, bsy, bsz = size[0] / nx, size[1] / ny, size[2] / nz

    qx, qy, qz, qw = rot
    m = [
        [1 - 2*qy*qy - 2*qz*qz, 2*qx*qy - 2*qz*qw, 2*qx*qz + 2*qy*qw],
        [2*qx*qy + 2*qz*qw,     1 - 2*qx*qx - 2*qz*qz, 2*qy*qz - 2*qx*qw],
        [2*qx*qz - 2*qy*qw,     2*qy*qz + 2*qx*qw,     1 - 2*qx*qx - 2*qy*qy],
    ]

    def rotate(vx, vy, vz):
        return (
            m[0][0]*vx + m[0][1]*vy + m[0][2]*vz,
            m[1][0]*vx + m[1][1]*vy + m[1][2]*vz,
            m[2][0]*vx + m[2][1]*vy + m[2][2]*vz,
        )

    base_name = obj.get("name", "Part")
    blocks = []
    for ix in range(nx):
        lx = -size[0]/2 + (ix + 0.5) * bsx
        for iy in range(ny):
            ly = -size[1]/2 + (iy + 0.5) * bsy
            for iz in range(nz):
                lz = -size[2]/2 + (iz + 0.5) * bsz

                if shape == "Cylinder":
                    r = min(size[1], size[2]) / 2
                    if (ly*ly + lz*lz) > r*r: continue
                elif shape == "Ball":
                    r = min(size) / 2
                    if (lx*lx + ly*ly + lz*lz) > r*r: continue
                elif shape == "Wedge":
                    if (size[2]*ly + size[1]*lz) > 0: continue
                # Union / CornerWedge: keep all blocks (bounding box fill)

                wx, wy, wz = rotate(lx, ly, lz)

                block = {
                    "type_id":       2,
                    "class":         "Part",
                    "name":          base_name,
                    "kind":          "part",
                    "enabled":       True,
                    "parent_id":     obj.get("parent_id"),
                    "flag2":         1,
                    "inner_name":    base_name,
                    "position":      [
                        settings.round_value(pos[0] + wx),
                        settings.round_value(pos[1] + wy),
                        settings.round_value(pos[2] + wz),
                    ],
                    "rotation":      rot,
                    "size":          [
                        settings.round_value(bsx),
                        settings.round_value(bsy),
                        settings.round_value(bsz),
                    ],
                    "color":         obj.get("color", {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1}),
                    "transparency":  obj.get("transparency", 0),
                    "material_id":   obj.get("material_id", 1),
                    "material":      obj.get("material", "Plastic"),
                    "shape":         "Block",
                    "flags":         obj.get("flags", [0, 1, 1, 1, 0, 0]),
                    "truss":         False,
                    "group":         obj.get("group"),
                    "textures":       [],
                    "point_lights":   [],
                    "spot_lights":    [],
                    "surface_lights": [],
                    "child_blob_hex": DEFAULT_CHILD_BLOB,
                }
                blocks.append(block)

    return blocks if blocks else [obj]

def flatten_parents(objects):
    """
    Vortex can't have a part as a parent. Any part or group whose parent_id
    points at a part gets walked up to the nearest non-part ancestor
    (a service or a group).
    """
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

# =========================================================
#  FILTERS
# =========================================================
def apply_filters(objects):
    flatten_parents(objects)
    # 1. Drop group objects entirely if IGNORE_MODELS is set.
    if settings.IGNORE_MODELS:
        remap = {}
        for i, o in enumerate(objects):
            if o.get("kind") == "group":
                remap[i] = o.get("parent_id", 0)
        # Resolve chains
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

    # 2. Drop scripts if IGNORE_SCRIPTS
    if settings.IGNORE_SCRIPTS:
        objects = [o for o in objects if o.get("kind") != "script"]

    # 3. Rasterize shapes
    if settings.SAVE_CUSTOM_SHAPES:
        expanded = []
        for o in objects:
            if o.get("kind") == "part":
                expanded.extend(rasterize_shape(o))
            else:
                expanded.append(o)
        objects = expanded

    return objects


# =========================================================
#  BUILD
# =========================================================
def build_vrtx(data):
    _check_json_version(data)

    version = int(data.get("version", 1))

    # UUID: prefer settings, then file, then generated
    uuid = settings.PROJECT_ID or data.get("uuid")
    if not uuid:
        import uuid as _uuid
        uuid = _uuid.uuid4().hex

    lighting = data.get("lighting") if settings.SAVE_LIGHTING else None
    objects = apply_filters(list(data.get("objects", [])))

    out = bytearray()
    out.append(version)
    uuid_bytes = uuid.encode("utf-8")
    out += struct.pack("<Q", len(uuid_bytes))
    out += uuid_bytes
    out += struct.pack("<Q", len(objects))

    for obj in objects:
        kind = obj.get("kind")
        type_id = int(obj["type_id"])
        name = obj.get("name", "").encode("utf-8")

        out += struct.pack("<I", type_id)
        out += struct.pack("<Q", len(name))
        out += name

        # ---------- SERVICES ----------
        if kind == "service":
            ph = obj.get("payload_hex", "00 " * 14).replace(" ", "")
            if len(ph) != 28:
                ph = "00" * 14
            out += bytes.fromhex(ph)

        # ---------- PARTS ----------
        elif kind == "part":
            out.append(1 if obj.get("enabled", True) else 0)
            out += struct.pack("<Q", int(obj.get("parent_id", 0)))
            out.append(int(obj.get("flag2", 1)) & 0xFF)

            inner_name = obj.get("inner_name", obj.get("name", "")).encode("utf-8")
            out += struct.pack("<Q", len(inner_name))
            out += inner_name

            pos   = obj.get("position", [0.0, 0.0, 0.0])
            rot   = obj.get("rotation", [0.0, 0.0, 0.0, 1.0])
            size  = obj.get("size", [1.0, 1.0, 1.0])
            color = obj.get("color", {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0})

            out += struct.pack("<3f", float(pos[0]), float(pos[1]), float(pos[2]))
            out += struct.pack("<4f", float(rot[0]), float(rot[1]), float(rot[2]), float(rot[3]))
            out += struct.pack("<3f", float(size[0]), float(size[1]), float(size[2]))
            out += struct.pack("<4f",
                float(color.get("r", 1)), float(color.get("g", 1)),
                float(color.get("b", 1)), float(color.get("a", 1)))

            mat_name = obj.get("material", "Plastic")
            mat_id = int(obj.get("material_id", MATERIAL_NAMES.get(mat_name, 1)))
            out += struct.pack("<I", mat_id)

            flags = obj.get("flags", [0, 1, 1, 1, 0, 0])
            for i in range(6):
                out.append((flags[i] if i < len(flags) else 0) & 0xFF)

            cb_hex = obj.get("child_blob_hex", "").replace(" ", "")
            if cb_hex:
                out += bytes.fromhex(cb_hex)
            else:
                out += bytes.fromhex(DEFAULT_CHILD_BLOB.replace(" ", ""))
        # ---------- GROUPS ----------
        elif kind == "group":
            out.append(1)  # enabled flag
            out += struct.pack("<Q", int(obj.get("parent_id", 0)))
            padding = obj.get("padding_hex", "").replace(" ", "")
            padding_bytes = bytes.fromhex(padding) if padding else b"\x00" * 13
            if len(padding_bytes) != 13:
                padding_bytes = b"\x00" * 13
            out += padding_bytes
        # ---------- SCRIPTS / REMOTES ----------
        elif kind == "script":
            out.append(1 if obj.get("enabled", True) else 0)
            out += struct.pack("<Q", int(obj.get("parent_id", 5)))

            marker_val = normalize_marker(obj.get("marker", None), type_id)
            out += struct.pack("<I", marker_val)

            source = (obj.get("source") or "").encode("utf-8")
            out += struct.pack("<Q", len(source))
            out += source

            th = obj.get("trailing_hex", "").replace(" ", "")
            if th:
                out += bytes.fromhex(th)
            else:
                default = DEFAULT_SCRIPT_TRAILING.get(type_id, "00")
                out += bytes.fromhex(default.replace(" ", ""))

        else:
            raise ValueError(f"Unknown object kind: {kind!r} (type_id={type_id})")

    # ---------- LIGHTING ----------
    if lighting:
        amb = lighting.get("ambient_color", {"r": 1, "g": 1, "b": 1})
        sun = lighting.get("sun_color", {"r": 1, "g": 1, "b": 1})
        sr  = lighting.get("sun_rotation", {"x": 0, "y": 0, "z": 0, "w": 1})
        out += struct.pack("<4f",
            float(amb.get("r", 1)), float(amb.get("g", 1)), float(amb.get("b", 1)),
            float(lighting.get("ambient_alpha", 1)))
        out += struct.pack("<f", float(lighting.get("ambient_brightness", 0)))
        out += struct.pack("<4f",
            float(sun.get("r", 1)), float(sun.get("g", 1)), float(sun.get("b", 1)),
            float(lighting.get("sun_alpha", 1)))
        out += struct.pack("<f", float(lighting.get("sun_brightness", 0)))
        out.append(1 if lighting.get("sun_shadows", True) else 0)
        out += struct.pack("<4f",
            float(sr.get("x", 0)), float(sr.get("y", 0)),
            float(sr.get("z", 0)), float(sr.get("w", 1)))
    else:
        out += struct.pack("<4f", 1.0, 1.0, 1.0, 1.0)
        out += struct.pack("<f", 0.0)
        out += struct.pack("<4f", 1.0, 1.0, 1.0, 1.0)
        out += struct.pack("<f", 0.0)
        out.append(1)
        out += struct.pack("<4f", 0.0, 0.0, 0.0, 1.0)

    # ---------- COMPRESSION ----------
    cctx = zstd.ZstdCompressor(write_content_size=False)
    raw = cctx.compress(bytes(out))

    fhd = raw[4]
    single_segment = (fhd >> 5) & 1
    header_len = 5 + (0 if single_segment else 1)

    tail = raw[header_len:]
    compressed = b"\x28\xB5\x2F\xFD" + b"\x00\x68" + tail

    return b"VRTX" + bytes([CONTAINER_VERSION_TO_WRITE]) + compressed


# =========================================================
#  ENTRY
# =========================================================
if __name__ == "__main__":
    import traceback

    args  = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    verbose = any(f in ("-v", "--verbose") for f in flags)

    if not args:
        print("Usage: py JSON_to_VRTX.py input.json [output.vrtx] [--verbose]")
        sys.exit(1)

    input_path  = Path(args[0])
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    output_path = Path(args[1]) if len(args) > 1 else input_path.with_suffix(".vrtx")

    try:
        file_bytes = build_vrtx(data)
    except SystemExit:
        raise
    except Exception:
        print("=== BUILD FAILED ===")
        traceback.print_exc()
        sys.exit(1)

    with open(output_path, "wb") as f:
        f.write(file_bytes)

    # Summary based on the *filtered* objects the writer actually saw
    filtered = apply_filters(list(data.get("objects", [])))
    services = sum(1 for o in filtered if o.get("kind") == "service")
    parts    = sum(1 for o in filtered if o.get("kind") == "part")
    scripts  = sum(1 for o in filtered if o.get("kind") == "script")
    groups   = sum(1 for o in filtered if o.get("kind") == "group")

    print(f"Saved: {output_path}  ({len(file_bytes)} bytes)")
    print(f"  services : {services}")
    print(f"  parts    : {parts}")
    print(f"  groups   : {groups}")
    print(f"  scripts  : {scripts}")
    print(f"  total    : {len(filtered)}")

    if verbose:
        print("\n" + "=" * 60)
        print(file_bytes.decode("utf-8", errors="replace"))
        print("=" * 60)
