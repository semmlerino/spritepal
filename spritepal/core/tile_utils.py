"""
Shared tile decoding utilities for SNES sprite formats.

This module provides common tile decoding functions used by multiple
sprite extraction and rendering components.
"""
from __future__ import annotations

from utils.constants import BYTES_PER_TILE


def decode_4bpp_tile(tile_bytes: bytes) -> list[list[int]]:
    """
    Decode a single 4bpp SNES tile to pixel indices.

    SNES 4bpp format uses 32 bytes per 8x8 tile:
    - Bytes 0-15: Bitplanes 0 and 1 for rows 0-7
    - Bytes 16-31: Bitplanes 2 and 3 for rows 0-7

    For each row, 2 bytes encode bitplanes 0-1, another 2 bytes (offset by 16)
    encode bitplanes 2-3. Each pixel combines 4 bits to get a color index 0-15.

    Args:
        tile_bytes: 32 bytes of tile data (padded if shorter)

    Returns:
        8x8 array of color indices (0-15)
    """
    # Pad if needed
    if len(tile_bytes) < BYTES_PER_TILE:
        tile_bytes = tile_bytes + b'\x00' * (BYTES_PER_TILE - len(tile_bytes))

    pixels: list[list[int]] = []

    for row in range(8):
        row_pixels: list[int] = []

        # Get the 4 plane bytes for this row
        plane_01_offset = row * 2
        plane_23_offset = 16 + row * 2

        plane0 = tile_bytes[plane_01_offset]
        plane1 = tile_bytes[plane_01_offset + 1]
        plane2 = tile_bytes[plane_23_offset]
        plane3 = tile_bytes[plane_23_offset + 1]

        # Decode each pixel in the row
        for col in range(8):
            bit_mask = 1 << (7 - col)

            # Extract bit from each plane and combine
            pixel = 0
            if plane0 & bit_mask:
                pixel |= 1
            if plane1 & bit_mask:
                pixel |= 2
            if plane2 & bit_mask:
                pixel |= 4
            if plane3 & bit_mask:
                pixel |= 8

            row_pixels.append(pixel)

        pixels.append(row_pixels)

    return pixels
