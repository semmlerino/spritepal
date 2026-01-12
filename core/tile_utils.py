"""
Shared tile decoding utilities for SNES sprite formats.

This module provides common tile decoding functions used by multiple
sprite extraction and rendering components.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

import numpy as np

from utils.constants import BYTES_PER_TILE, PIXEL_MASK_4BIT

logger = logging.getLogger(__name__)

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


def encode_4bpp_tile(tile_pixels: list[int] | np.ndarray) -> bytes:
    """
    Encode an 8x8 tile to SNES 4bpp format using NumPy vectorization.

    Args:
        tile_pixels: 64 pixel values (either list or numpy array)

    Returns:
        32 bytes of SNES 4bpp tile data
    """
    # Convert to numpy array if needed
    if isinstance(tile_pixels, list):
        pixels = np.array(tile_pixels, dtype=np.uint8)
    else:
        pixels = tile_pixels.astype(np.uint8)

    if len(pixels) != 64:
        logger.error(f"Invalid tile size: expected 64 pixels, got {len(pixels)}")
        raise ValueError(f"Expected 64 pixels, got {len(pixels)}")

    # Reshape to 8x8 and mask to 4-bit
    pixels = pixels.reshape(8, 8) & PIXEL_MASK_4BIT

    # Extract bitplanes (vectorized bit extraction)
    # Each bitplane is an 8x8 array of 0s and 1s
    bp0_bits = (pixels & 1).astype(np.uint8)
    bp1_bits = ((pixels >> 1) & 1).astype(np.uint8)
    bp2_bits = ((pixels >> 2) & 1).astype(np.uint8)
    bp3_bits = ((pixels >> 3) & 1).astype(np.uint8)

    # Pack each row of 8 bits into 1 byte using np.packbits
    # np.packbits packs bits in big-endian order (MSB first), which matches SNES format
    bp0 = np.packbits(bp0_bits, axis=1).flatten()  # 8 bytes
    bp1 = np.packbits(bp1_bits, axis=1).flatten()  # 8 bytes
    bp2 = np.packbits(bp2_bits, axis=1).flatten()  # 8 bytes
    bp3 = np.packbits(bp3_bits, axis=1).flatten()  # 8 bytes

    # Interleave bitplanes in SNES 4bpp format:
    # First 16 bytes: bp0[0], bp1[0], bp0[1], bp1[1], ...
    # Next 16 bytes: bp2[0], bp3[0], bp2[1], bp3[1], ...
    output = np.zeros(32, dtype=np.uint8)
    output[0:16:2] = bp0  # Even indices 0,2,4,6,8,10,12,14
    output[1:16:2] = bp1  # Odd indices 1,3,5,7,9,11,13,15
    output[16:32:2] = bp2  # Even indices 16,18,20,22,24,26,28,30
    output[17:32:2] = bp3  # Odd indices 17,19,21,23,25,27,29,31

    return bytes(output)


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


def align_tile_data(tile_data: bytes, bytes_per_tile: int = BYTES_PER_TILE) -> bytes:
    """
    Align tile data to tile boundaries by removing leading header bytes.

    Some HAL-compressed sprite assets in Kirby games include metadata/header bytes
    at the start of the decompressed data (e.g., asset ID, length prefix, palette hints).
    These extra bytes cause tile misalignment, corrupting the bitplane interpretation.

    This function detects and removes leading bytes to ensure the data starts at a
    valid tile boundary (multiple of bytes_per_tile, typically 32 for 4bpp).

    Args:
        tile_data: Raw decompressed tile data that may have leading header bytes
        bytes_per_tile: Bytes per tile (default 32 for 4bpp SNES tiles)

    Returns:
        Tile data aligned to tile boundaries. If already aligned, returns unchanged.
        If misaligned, strips leading bytes to achieve alignment.

    Example:
        >>> data = b'\\x02' + b'\\x00' * 64  # 1 header byte + 2 tiles
        >>> aligned = align_tile_data(data)
        >>> len(aligned) % 32
        0
    """
    if not tile_data:
        return tile_data

    remainder = len(tile_data) % bytes_per_tile

    if remainder == 0:
        # Already aligned
        return tile_data

    # Strip leading bytes to align
    # The assumption is that header bytes are at the START, not end
    # This is based on observed Kirby Super Star asset format
    header_size = remainder
    aligned_data = tile_data[header_size:]

    if len(aligned_data) >= bytes_per_tile:
        logger.debug(
            f"Aligned tile data: removed {header_size} header byte(s), "
            f"{len(tile_data)} -> {len(aligned_data)} bytes "
            f"({len(aligned_data) // bytes_per_tile} tiles)"
        )
        return aligned_data
    else:
        # Not enough data left after stripping - return original
        logger.warning(
            f"Cannot align tile data: only {len(aligned_data)} bytes remain after removing {header_size} header byte(s)"
        )
        return tile_data


def get_tile_alignment_info(tile_data: bytes, bytes_per_tile: int = BYTES_PER_TILE) -> dict[str, int | bool]:
    """
    Analyze tile data alignment and return diagnostic information.

    Args:
        tile_data: Raw tile data to analyze
        bytes_per_tile: Bytes per tile (default 32 for 4bpp SNES tiles)

    Returns:
        Dictionary with alignment info:
        - 'size': Total size in bytes
        - 'tile_count': Number of complete tiles
        - 'remainder': Extra bytes beyond tile boundary
        - 'is_aligned': True if perfectly aligned
        - 'header_bytes': Likely header size (same as remainder if not aligned)
    """
    if not tile_data:
        return {
            "size": 0,
            "tile_count": 0,
            "remainder": 0,
            "is_aligned": True,
            "header_bytes": 0,
        }

    size = len(tile_data)
    remainder = size % bytes_per_tile
    tile_count = size // bytes_per_tile

    return {
        "size": size,
        "tile_count": tile_count,
        "remainder": remainder,
        "is_aligned": remainder == 0,
        "header_bytes": max(0, remainder),
    }
