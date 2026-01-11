"""
Shared tile decoding utilities for SNES sprite formats.

This module provides common tile decoding functions used by multiple
sprite extraction and rendering components.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from utils.constants import BYTES_PER_TILE

if TYPE_CHECKING:
    from collections.abc import Iterator


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
        tile_bytes = tile_bytes + b"\x00" * (BYTES_PER_TILE - len(tile_bytes))

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


def hash_tile(tile_data: bytes) -> str:
    """Generate MD5 hash for a tile."""
    return hashlib.md5(tile_data).hexdigest()


def reverse_byte(value: int) -> int:
    """Reverse bits in a byte."""
    value = ((value & 0xF0) >> 4) | ((value & 0x0F) << 4)
    value = ((value & 0xCC) >> 2) | ((value & 0x33) << 2)
    value = ((value & 0xAA) >> 1) | ((value & 0x55) << 1)
    return value


def flip_tile(tile_data: bytes, flip_h: bool, flip_v: bool) -> bytes:
    """
    Flip 4bpp tile data horizontally and/or vertically.
    
    Args:
        tile_data: 32 bytes of 4bpp tile data
        flip_h: Horizontal flip
        flip_v: Vertical flip
        
    Returns:
        Flipped tile data
    """
    if not flip_h and not flip_v:
        return tile_data
    if len(tile_data) != BYTES_PER_TILE:
        return tile_data
    
    out = bytearray(BYTES_PER_TILE)
    for row in range(8):
        src_row = 7 - row if flip_v else row
        for plane_offset in (0, 16):
            b0 = tile_data[plane_offset + (src_row * 2)]
            b1 = tile_data[plane_offset + (src_row * 2) + 1]
            if flip_h:
                b0 = reverse_byte(b0)
                b1 = reverse_byte(b1)
            out[plane_offset + (row * 2)] = b0
            out[plane_offset + (row * 2) + 1] = b1
    return bytes(out)


def iter_flip_variants(tile_data: bytes) -> Iterator[bytes]:
    """Yield all flipped variants of a tile (H, V, HV)."""
    yield flip_tile(tile_data, flip_h=True, flip_v=False)
    yield flip_tile(tile_data, flip_h=False, flip_v=True)
    yield flip_tile(tile_data, flip_h=True, flip_v=True)