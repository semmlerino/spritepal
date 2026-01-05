"""
SA-1 Character Conversion Algorithm.

Implements the bitmap ↔ SNES bitplane conversion that the SA-1 coprocessor
performs via hardware DMA. This enables matching captured VRAM tiles back
to decompressed ROM graphics.

The SA-1 character conversion transforms:
- Bitmap format (linear pixels) → SNES 4bpp bitplane format

SNES 4bpp Tile Format (32 bytes):
    Bytes 0-15:  Bitplanes 0,1 (low bits) - 2 bytes per row x 8 rows
    Bytes 16-31: Bitplanes 2,3 (high bits) - 2 bytes per row x 8 rows

    For each row:
        byte[row*2+0]  = bitplane 0 (8 pixels, bit 0 of each)
        byte[row*2+1]  = bitplane 1 (8 pixels, bit 1 of each)
        byte[16+row*2] = bitplane 2 (8 pixels, bit 2 of each)
        byte[17+row*2] = bitplane 3 (8 pixels, bit 3 of each)

Bitmap Format (32 bytes for 8x8 4bpp):
    4 bytes per row x 8 rows
    Each byte contains 2 pixels (high nibble = left, low nibble = right)
    Row-major, left-to-right

Usage:
    from core.mesen_integration.sa1_character_conversion import (
        bitmap_to_snes_4bpp,
        snes_4bpp_to_bitmap,
    )

    # Convert HAL-decompressed bitmap to SNES format for matching
    snes_tile = bitmap_to_snes_4bpp(decompressed_bitmap)

    # Convert captured VRAM tile back to bitmap for ROM search
    bitmap = snes_4bpp_to_bitmap(vram_tile)
"""

from __future__ import annotations


def bitmap_to_snes_4bpp(bitmap: bytes) -> bytes:
    """
    Convert 8x8 4bpp bitmap to SNES 4bpp bitplane format.

    This is the forward conversion - transforms linear bitmap pixels
    into the interleaved bitplane format the SNES PPU expects.

    Args:
        bitmap: 32 bytes in bitmap format (4 bytes/row x 8 rows).
                Each byte contains 2 pixels as nibbles (high=left, low=right).

    Returns:
        32 bytes in SNES 4bpp bitplane format.

    Raises:
        ValueError: If bitmap is not exactly 32 bytes.
    """
    if len(bitmap) != 32:
        raise ValueError(f"Bitmap must be 32 bytes, got {len(bitmap)}")

    result = bytearray(32)

    for row in range(8):
        # Extract 8 pixels from this row (4 bytes, 2 pixels per byte)
        row_offset = row * 4
        pixels = []
        for col_byte in range(4):
            byte_val = bitmap[row_offset + col_byte]
            # High nibble = left pixel, low nibble = right pixel
            pixels.append((byte_val >> 4) & 0x0F)
            pixels.append(byte_val & 0x0F)

        # Now we have 8 pixels, each 0-15 (4 bits)
        # Separate into 4 bitplanes
        bp0 = 0  # Bit 0 of each pixel
        bp1 = 0  # Bit 1 of each pixel
        bp2 = 0  # Bit 2 of each pixel
        bp3 = 0  # Bit 3 of each pixel

        for i, pixel in enumerate(pixels):
            bit_pos = 7 - i  # Leftmost pixel → MSB
            if pixel & 0x01:
                bp0 |= 1 << bit_pos
            if pixel & 0x02:
                bp1 |= 1 << bit_pos
            if pixel & 0x04:
                bp2 |= 1 << bit_pos
            if pixel & 0x08:
                bp3 |= 1 << bit_pos

        # Store in SNES format
        result[row * 2] = bp0
        result[row * 2 + 1] = bp1
        result[16 + row * 2] = bp2
        result[16 + row * 2 + 1] = bp3

    return bytes(result)


def snes_4bpp_to_bitmap(snes_tile: bytes) -> bytes:
    """
    Convert SNES 4bpp bitplane format to 8x8 4bpp bitmap.

    This is the inverse conversion - transforms interleaved bitplanes
    back into linear bitmap pixels for comparison with ROM data.

    Args:
        snes_tile: 32 bytes in SNES 4bpp bitplane format.

    Returns:
        32 bytes in bitmap format (4 bytes/row x 8 rows).
        Each byte contains 2 pixels as nibbles (high=left, low=right).

    Raises:
        ValueError: If snes_tile is not exactly 32 bytes.
    """
    if len(snes_tile) != 32:
        raise ValueError(f"SNES tile must be 32 bytes, got {len(snes_tile)}")

    result = bytearray(32)

    for row in range(8):
        # Extract bitplanes for this row
        bp0 = snes_tile[row * 2]
        bp1 = snes_tile[row * 2 + 1]
        bp2 = snes_tile[16 + row * 2]
        bp3 = snes_tile[16 + row * 2 + 1]

        # Reconstruct 8 pixels
        pixels = []
        for i in range(8):
            bit_pos = 7 - i  # MSB → leftmost pixel
            pixel = 0
            if bp0 & (1 << bit_pos):
                pixel |= 0x01
            if bp1 & (1 << bit_pos):
                pixel |= 0x02
            if bp2 & (1 << bit_pos):
                pixel |= 0x04
            if bp3 & (1 << bit_pos):
                pixel |= 0x08
            pixels.append(pixel)

        # Pack 8 pixels into 4 bytes (2 pixels per byte)
        row_offset = row * 4
        for col_byte in range(4):
            left_pixel = pixels[col_byte * 2]
            right_pixel = pixels[col_byte * 2 + 1]
            result[row_offset + col_byte] = (left_pixel << 4) | right_pixel

    return bytes(result)


def verify_roundtrip(data: bytes, is_bitmap: bool = True) -> bool:
    """
    Verify that conversion is lossless by round-tripping.

    Args:
        data: 32-byte tile data.
        is_bitmap: True if data is in bitmap format, False if SNES format.

    Returns:
        True if round-trip produces identical data.
    """
    if is_bitmap:
        converted = bitmap_to_snes_4bpp(data)
        back = snes_4bpp_to_bitmap(converted)
    else:
        converted = snes_4bpp_to_bitmap(data)
        back = bitmap_to_snes_4bpp(converted)

    return data == back


def hash_snes_tile(snes_tile: bytes) -> str:
    """
    Generate a hash for a SNES 4bpp tile.

    Uses SHA-256 truncated to 16 hex chars for compact storage.
    This matches the hash format used in tile_hash_database.py.

    Args:
        snes_tile: 32 bytes in SNES 4bpp format.

    Returns:
        16-character hex string.
    """
    import hashlib

    return hashlib.sha256(snes_tile).hexdigest()[:16]


def hash_bitmap_as_snes(bitmap: bytes) -> str:
    """
    Hash bitmap data as if it were converted to SNES format.

    Useful for matching decompressed ROM data against VRAM captures.

    Args:
        bitmap: 32 bytes in bitmap format.

    Returns:
        16-character hex string matching what VRAM capture would produce.
    """
    snes_tile = bitmap_to_snes_4bpp(bitmap)
    return hash_snes_tile(snes_tile)


# =============================================================================
# Batch conversion utilities
# =============================================================================


def convert_tileset_to_snes(bitmap_data: bytes, tiles_per_row: int = 16) -> bytes:
    """
    Convert a tileset from bitmap format to SNES format.

    Args:
        bitmap_data: Bitmap tileset (must be multiple of 32 bytes).
        tiles_per_row: Tiles per row (for potential row-major reordering).

    Returns:
        Converted tileset in SNES 4bpp format.
    """
    if len(bitmap_data) % 32 != 0:
        raise ValueError(f"Bitmap data must be multiple of 32 bytes, got {len(bitmap_data)}")

    num_tiles = len(bitmap_data) // 32
    result = bytearray()

    for i in range(num_tiles):
        tile_bitmap = bitmap_data[i * 32 : (i + 1) * 32]
        tile_snes = bitmap_to_snes_4bpp(tile_bitmap)
        result.extend(tile_snes)

    return bytes(result)


def convert_tileset_to_bitmap(snes_data: bytes) -> bytes:
    """
    Convert a tileset from SNES format to bitmap format.

    Args:
        snes_data: SNES tileset (must be multiple of 32 bytes).

    Returns:
        Converted tileset in bitmap format.
    """
    if len(snes_data) % 32 != 0:
        raise ValueError(f"SNES data must be multiple of 32 bytes, got {len(snes_data)}")

    num_tiles = len(snes_data) // 32
    result = bytearray()

    for i in range(num_tiles):
        tile_snes = snes_data[i * 32 : (i + 1) * 32]
        tile_bitmap = snes_4bpp_to_bitmap(tile_snes)
        result.extend(tile_bitmap)

    return bytes(result)


# =============================================================================
# Packed 2bpp format conversion (Planes 0+2)
# =============================================================================
#
# Kirby Super Star sprite graphics use a 4-color subset palette where only
# bitplanes 0 and 2 contain data. The ROM stores these 16 bytes directly.
#
# VERIFIED: Analysis of captured VRAM tiles shows:
# - Bitplanes 0 and 2 contain data (even byte positions in SNES 4bpp)
# - Bitplanes 1 and 3 are all-zero (odd byte positions)
# - 98.3% of non-empty sprite tiles follow this pattern
#
# This corresponds to palette indices 0, 1, 4, 5 (where bits 1 and 3 are zero).


def packed_2bpp_to_snes_4bpp(packed: bytes) -> bytes:
    """
    Expand packed 2bpp tile (planes 0+2) to full SNES 4bpp format.

    Packed format (16 bytes):
        Bytes 0-7:  Bitplane 0 for rows 0-7 (1 byte per row)
        Bytes 8-15: Bitplane 2 for rows 0-7 (1 byte per row)

    SNES 4bpp format (32 bytes):
        Bytes 0-15:  Rows 0-7, [bp0, bp1] pairs (bp1 = 0x00)
        Bytes 16-31: Rows 0-7, [bp2, bp3] pairs (bp3 = 0x00)

    Args:
        packed: 16 bytes in packed 2bpp format.

    Returns:
        32 bytes in SNES 4bpp format.

    Raises:
        ValueError: If packed is not exactly 16 bytes.
    """
    if len(packed) != 16:
        raise ValueError(f"Packed 2bpp must be 16 bytes, got {len(packed)}")

    result = bytearray(32)

    for row in range(8):
        bp0 = packed[row]  # Bitplane 0 from first half
        bp2 = packed[8 + row]  # Bitplane 2 from second half

        # Low bitplanes (0-15): bp0=actual, bp1=0x00
        result[row * 2] = bp0
        result[row * 2 + 1] = 0x00

        # High bitplanes (16-31): bp2=actual, bp3=0x00
        result[16 + row * 2] = bp2
        result[16 + row * 2 + 1] = 0x00

    return bytes(result)


def snes_4bpp_to_packed_2bpp(snes_tile: bytes) -> bytes:
    """
    Compress SNES 4bpp tile to packed 2bpp format (planes 0+2).

    Extracts only bitplanes 0 and 2 (the even bytes).
    Bitplanes 1 and 3 (odd bytes) are discarded.

    Useful for searching ROM for VRAM tile patterns.

    Args:
        snes_tile: 32 bytes in SNES 4bpp format.

    Returns:
        16 bytes in packed 2bpp format.

    Raises:
        ValueError: If snes_tile is not exactly 32 bytes.
    """
    if len(snes_tile) != 32:
        raise ValueError(f"SNES tile must be 32 bytes, got {len(snes_tile)}")

    result = bytearray(16)

    for row in range(8):
        # Extract bitplane 0 (even byte from first half)
        result[row] = snes_tile[row * 2]
        # Extract bitplane 2 (even byte from second half)
        result[8 + row] = snes_tile[16 + row * 2]

    return bytes(result)


def is_packed_2bpp_candidate(snes_tile: bytes) -> bool:
    """
    Check if a SNES 4bpp tile could have originated from packed 2bpp.

    A tile is a packed 2bpp candidate if:
    - All odd bytes (bitplanes 1, 3) are 0x00
    - At least some even bytes (bitplanes 0, 2) are non-zero

    Args:
        snes_tile: 32 bytes in SNES 4bpp format.

    Returns:
        True if tile matches packed 2bpp pattern (planes 0+2 only).
    """
    if len(snes_tile) != 32:
        return False

    # Check that all odd bytes (bp1, bp3) are zero
    for row in range(8):
        if snes_tile[row * 2 + 1] != 0:  # bp1
            return False
        if snes_tile[16 + row * 2 + 1] != 0:  # bp3
            return False

    # Check that at least some data exists in even bytes
    has_data = any(snes_tile[i] != 0 for i in range(0, 32, 2))
    return has_data


def hash_packed_as_snes(packed: bytes) -> str:
    """
    Hash packed 2bpp data as if expanded to SNES format.

    Useful for building database from packed ROM data.

    Args:
        packed: 16 bytes in packed 2bpp format.

    Returns:
        16-character hex string matching expanded VRAM capture.
    """
    snes_tile = packed_2bpp_to_snes_4bpp(packed)
    return hash_snes_tile(snes_tile)


# =============================================================================
# Flexible two-plane extraction
# =============================================================================
#
# SNES 4bpp tiles have 4 bitplanes. Some tiles may use only 2 of the 4,
# with the other 2 being all-zero. This can happen due to:
# - Packed storage format in ROM (only non-zero planes stored)
# - Palette design that only uses 4 colors (specific bit positions)
#
# There are 6 possible combinations of choosing 2 planes from 4:
# (0,1), (0,2), (0,3), (1,2), (1,3), (2,3)
#
# The byte layout in SNES 4bpp format (32 bytes):
#   Bytes 0-15:  rows 0-7, [bp0, bp1] pairs (2 bytes per row)
#   Bytes 16-31: rows 0-7, [bp2, bp3] pairs (2 bytes per row)
#
# For row r:
#   bp0 = tile[r*2]      bp1 = tile[r*2+1]
#   bp2 = tile[16+r*2]   bp3 = tile[16+r*2+1]

# All 6 combinations of 2 planes from 4
TWO_PLANE_COMBOS: list[tuple[int, int]] = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]


def _get_plane_byte_indices(plane: int) -> list[int]:
    """
    Get the 8 byte indices for a given bitplane (0-3).

    Args:
        plane: Bitplane number (0-3).

    Returns:
        List of 8 byte indices within a 32-byte SNES tile.
    """
    if plane == 0:
        return [r * 2 for r in range(8)]  # even bytes in first half
    elif plane == 1:
        return [r * 2 + 1 for r in range(8)]  # odd bytes in first half
    elif plane == 2:
        return [16 + r * 2 for r in range(8)]  # even bytes in second half
    elif plane == 3:
        return [16 + r * 2 + 1 for r in range(8)]  # odd bytes in second half
    else:
        raise ValueError(f"Plane must be 0-3, got {plane}")


def extract_two_planes(snes_tile: bytes, planes: tuple[int, int]) -> bytes:
    """
    Extract 16 bytes from two specified bitplanes.

    Args:
        snes_tile: 32 bytes in SNES 4bpp format.
        planes: Tuple of two plane numbers (0-3) to extract.

    Returns:
        16 bytes: 8 bytes from first plane, then 8 bytes from second plane.

    Raises:
        ValueError: If tile is not 32 bytes or planes invalid.
    """
    if len(snes_tile) != 32:
        raise ValueError(f"SNES tile must be 32 bytes, got {len(snes_tile)}")

    p1, p2 = planes
    if not (0 <= p1 <= 3 and 0 <= p2 <= 3 and p1 != p2):
        raise ValueError(f"Invalid planes: {planes}")

    result = bytearray(16)

    # Extract first plane (8 bytes)
    for i, idx in enumerate(_get_plane_byte_indices(p1)):
        result[i] = snes_tile[idx]

    # Extract second plane (8 bytes)
    for i, idx in enumerate(_get_plane_byte_indices(p2)):
        result[8 + i] = snes_tile[idx]

    return bytes(result)


def get_zero_planes(snes_tile: bytes) -> set[int]:
    """
    Identify which bitplanes are all-zero in a SNES 4bpp tile.

    Args:
        snes_tile: 32 bytes in SNES 4bpp format.

    Returns:
        Set of plane numbers (0-3) that are all-zero.
    """
    if len(snes_tile) != 32:
        return set()

    zero_planes: set[int] = set()
    for plane in range(4):
        indices = _get_plane_byte_indices(plane)
        if all(snes_tile[idx] == 0 for idx in indices):
            zero_planes.add(plane)

    return zero_planes


def get_two_plane_candidates(snes_tile: bytes) -> list[tuple[int, int]]:
    """
    Find all valid two-plane combinations for a tile.

    A valid combination has exactly two planes all-zero (the other two non-zero).

    Args:
        snes_tile: 32 bytes in SNES 4bpp format.

    Returns:
        List of (plane1, plane2) tuples representing the non-zero planes.
        Empty if tile doesn't have exactly 2 zero planes.
    """
    if len(snes_tile) != 32:
        return []

    zero_planes = get_zero_planes(snes_tile)

    # We want exactly 2 zero planes (meaning 2 non-zero planes)
    if len(zero_planes) != 2:
        return []

    # The non-zero planes are the candidates
    non_zero = sorted(set(range(4)) - zero_planes)
    if len(non_zero) != 2:
        return []

    # Verify the non-zero planes actually have data
    for plane in non_zero:
        indices = _get_plane_byte_indices(plane)
        if all(snes_tile[idx] == 0 for idx in indices):
            return []  # Shouldn't happen but be safe

    return [tuple(non_zero)]  # type: ignore[list-item]


def hash_two_planes(snes_tile: bytes, planes: tuple[int, int]) -> str:
    """
    Hash 16 bytes extracted from two specific planes.

    Args:
        snes_tile: 32 bytes in SNES 4bpp format.
        planes: Tuple of two plane numbers to extract.

    Returns:
        16-character hex hash of the 16 extracted bytes.
    """
    import hashlib

    extracted = extract_two_planes(snes_tile, planes)
    return hashlib.sha256(extracted).hexdigest()[:16]


def analyze_tile_planes(snes_tile: bytes) -> dict[str, object]:
    """
    Analyze a tile's bitplane usage for diagnostics.

    Args:
        snes_tile: 32 bytes in SNES 4bpp format.

    Returns:
        Dictionary with plane analysis info.
    """
    if len(snes_tile) != 32:
        return {"error": f"Invalid tile size: {len(snes_tile)}"}

    zero_planes = get_zero_planes(snes_tile)
    non_zero_planes = sorted(set(range(4)) - zero_planes)

    # Count non-zero bytes per plane
    plane_byte_counts = {}
    for plane in range(4):
        indices = _get_plane_byte_indices(plane)
        non_zero_count = sum(1 for idx in indices if snes_tile[idx] != 0)
        plane_byte_counts[plane] = non_zero_count

    return {
        "zero_planes": sorted(zero_planes),
        "non_zero_planes": non_zero_planes,
        "plane_byte_counts": plane_byte_counts,
        "is_two_plane_tile": len(zero_planes) == 2,
        "non_zero_plane_combo": tuple(non_zero_planes) if len(non_zero_planes) == 2 else None,
    }
