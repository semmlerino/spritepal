"""
Core utilities for the Unified Sprite Editor.
Tile encoding/decoding, palette conversion, and shared helpers.
"""

from .palette_utils import (
    apply_palette_with_transparency,
    bgr555_to_rgb888,
    get_grayscale_palette,
    read_all_palettes,
    read_cgram_palette,
    rgb888_to_bgr555,
    write_cgram_palette,
)
from .tile_utils import (
    calculate_dimensions_from_tile_data,
    calculate_tile_grid_exact,
    calculate_tile_grid_padded,
    decode_4bpp_tile,
    decode_tiles,
    encode_4bpp_tile,
    encode_tiles,
)

__all__ = [
    "apply_palette_with_transparency",
    # Palette utilities
    "bgr555_to_rgb888",
    "calculate_dimensions_from_tile_data",
    "calculate_tile_grid_exact",
    "calculate_tile_grid_padded",
    # Tile utilities
    "decode_4bpp_tile",
    "decode_tiles",
    "encode_4bpp_tile",
    "encode_tiles",
    "get_grayscale_palette",
    "read_all_palettes",
    "read_cgram_palette",
    "rgb888_to_bgr555",
    "write_cgram_palette",
]
