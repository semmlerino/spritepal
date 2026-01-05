"""
Core utilities for the Unified Sprite Editor.
Tile encoding/decoding, palette conversion, and shared helpers.
"""

from .palette_utils import (
    bgr555_to_rgb888,
    get_grayscale_palette,
    read_cgram_palette,
    rgb888_to_bgr555,
)
from .tile_utils import (
    calculate_dimensions_from_tile_data,
    calculate_tile_grid_padded,
    decode_4bpp_tile,
    encode_4bpp_tile,
)

__all__ = [
    "bgr555_to_rgb888",
    "calculate_dimensions_from_tile_data",
    "calculate_tile_grid_padded",
    "decode_4bpp_tile",
    "encode_4bpp_tile",
    "get_grayscale_palette",
    "read_cgram_palette",
    "rgb888_to_bgr555",
]
