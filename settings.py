"""
settings.py

Central configuration for all converters.
Edit this file to customise behaviour. Nothing else needs changing.
"""


# Include the lighting block when writing a file?
# When False, the target engine uses its default lighting.
SAVE_LIGHTING = True


# Set to a string (32-char hex) to reuse the same project UUID every time.
# Set to None to generate a fresh random UUID on every export.
PROJECT_ID = None


# Vortex doesn't support Cylinders, Balls, Wedges, or Unions natively.
# When True, those shapes are approximated with a grid of small blocks.
# When False, they export as bounding boxes.
SAVE_CUSTOM_SHAPES = True

# How many samples along the longest axis.
# Higher = finer detail = more parts.
#   4  = chunky
#   8  = default, good balance
#   16 = fine, many parts
CUSTOM_SHAPES_ACCURACY = 8

# Hard cap on blocks per shape. If the grid exceeds this, resolution
# is automatically reduced until it fits.
MAX_BLOCKS_PER_SHAPE = 512


# When True, Model instances are ignored entirely during conversion.
# Parts inside models end up parented directly to their service.
IGNORE_MODELS =  False

# When True, scripts, LocalScripts, RemoteEvents, RemoteFunctions, and
# BindableEvents are all skipped.
IGNORE_SCRIPTS = False


# Decimal places used when rounding positions, sizes, colours, rotation.
#   3 = millimetre precision (safe default)
#   6 = near full float precision (larger files)
DECIMAL_PLACES = 3


# =========================================================
#  MATERIAL CONVERSION  (Vortex -> Roblox)
# =========================================================
VORTEX_TO_ROBLOX_MATERIALS = {
    "Smooth":  "SmoothPlastic",
    "Plastic": "Plastic",
    "Wood":    "Wood",
    "Metal":   "Metal",
    "Grass":   "Grass",
    "Ice":     "Ice",
    "Paint":   "Foil",
}


# =========================================================
#  MATERIAL CONVERSION  (Roblox -> Vortex)
# =========================================================
# Anything not listed here falls back to "Plastic".
ROBLOX_TO_VORTEX_MATERIALS = {
    "Asphalt":       "Paint",
    "Basalt":        "Plastic",
    "Brick":         "Plastic",
    "Cardboard":     "Plastic",
    "Carpet":        "Grass",
    "CeramicTiles":  "Plastic",
    "ClayRoofTiles": "Wood",
    "Cobblestone":   "Plastic",
    "Concrete":      "Plastic",
    "CorrodedMetal": "Metal",
    "CrackedLava":   "Paint",
    "DiamondPlate":  "Metal",
    "Fabric":        "Grass",
    "Foil":          "Paint",
    "ForceField":    "Ice",
    "Glacier":       "Ice",
    "Glass":         "Ice",
    "Granite":       "Paint",
    "Grass":         "Grass",
    "Ground":        "Grass",
    "Ice":           "Ice",
    "LeafyGrass":    "Grass",
    "Leather":       "Paint",
    "Limestone":     "Paint",
    "Marble":        "Plastic",
    "Metal":         "Metal",
    "Mud":           "Grass",
    "Neon":          "Smooth",
    "Pavement":      "Plastic",
    "Pebble":        "Plastic",
    "Plaster":       "Plastic",
    "Plastic":       "Plastic",
    "Rock":          "Paint",
    "RoofShingles":  "Wood",
    "Rubber":        "Paint",
    "Salt":          "Paint",
    "Sand":          "Paint",
    "Sandstone":     "Paint",
    "Slate":         "Paint",
    "SmoothPlastic": "Smooth",
    "Snow":          "Paint",
    "Wood":          "Wood",
    "WoodPlanks":    "Wood",
}


# =========================================================
#  HELPERS (dont change)
# =========================================================

# Support both naming conventions for the dicts
_VORTEX_TO_ROBLOX = globals().get("VORTEX_MATERIALS_CONVERTION") \
                 or globals().get("VORTEX_TO_ROBLOX_MATERIALS") \
                 or {}

_ROBLOX_TO_VORTEX = globals().get("ROBLOX_MATERIALS_CONVERTION") \
                 or globals().get("ROBLOX_TO_VORTEX_MATERIALS") \
                 or {}


def map_to_roblox(vortex_material):
    return _VORTEX_TO_ROBLOX.get(vortex_material, "Plastic")


def map_to_vortex(roblox_material):
    return _ROBLOX_TO_VORTEX.get(roblox_material, "Plastic")


# Aliases so any converter version works
map_material_to_roblox = map_to_roblox
map_material_to_vortex = map_to_vortex


def round_value(n, places=None):
    if not isinstance(n, (int, float)):
        return n
    places = places if places is not None else DECIMAL_PLACES
    return round(n, places)