#!/usr/bin/env python3
"""
SNES palette utilities
Consolidated palette operations for CGRAM handling
"""

import struct
from pathlib import Path

from ..constants import (
    BGR555_BLUE_MASK,
    BGR555_BLUE_SHIFT,
    BGR555_GREEN_MASK,
    BGR555_GREEN_SHIFT,
    BGR555_MAX_VALUE,
    BGR555_RED_MASK,
    BGR555_RED_SHIFT,
    BYTES_PER_COLOR,
    BYTES_PER_PALETTE,
    COLORS_PER_PALETTE,
    MAX_PALETTES,
    PALETTE_ENTRIES,
    PALETTE_SIZE_BYTES,
    RGB888_MAX_VALUE,
)


def bgr555_to_rgb888(bgr555: int) -> tuple[int, int, int]:
    """
    Convert BGR555 color to RGB888.

    Args:
        bgr555: 16-bit BGR555 color value

    Returns:
        Tuple of (r, g, b) values in 0-255 range
    """
    # Extract 5-bit components
    b = (bgr555 & BGR555_BLUE_MASK) >> BGR555_BLUE_SHIFT
    g = (bgr555 & BGR555_GREEN_MASK) >> BGR555_GREEN_SHIFT
    r = (bgr555 & BGR555_RED_MASK) >> BGR555_RED_SHIFT

    # Convert to 8-bit values
    r = (r * RGB888_MAX_VALUE) // BGR555_MAX_VALUE
    g = (g * RGB888_MAX_VALUE) // BGR555_MAX_VALUE
    b = (b * RGB888_MAX_VALUE) // BGR555_MAX_VALUE

    return r, g, b


def rgb888_to_bgr555(r: int, g: int, b: int) -> int:
    """
    Convert RGB888 color to BGR555.

    Args:
        r: Red component (0-255)
        g: Green component (0-255)
        b: Blue component (0-255)

    Returns:
        16-bit BGR555 color value
    """
    # Convert to 5-bit values
    r5 = (r * BGR555_MAX_VALUE) // RGB888_MAX_VALUE
    g5 = (g * BGR555_MAX_VALUE) // RGB888_MAX_VALUE
    b5 = (b * BGR555_MAX_VALUE) // RGB888_MAX_VALUE

    # Pack into BGR555
    return (
        (b5 << BGR555_BLUE_SHIFT)
        | (g5 << BGR555_GREEN_SHIFT)
        | (r5 << BGR555_RED_SHIFT)
    )


def read_cgram_palette(cgram_file: str, palette_num: int) -> list[int] | None:
    """
    Read a specific palette from CGRAM dump.

    Args:
        cgram_file: Path to CGRAM dump file
        palette_num: Palette number (0-15)

    Returns:
        List of 768 RGB values (256 colors * 3 components) or None on error
        Only the first 16 colors contain actual data from the SNES palette
    """
    try:
        # Validate palette number
        if palette_num < 0 or palette_num >= MAX_PALETTES:
            return None

        with Path(cgram_file).open("rb") as f:
            # Each palette is BYTES_PER_PALETTE
            offset = palette_num * BYTES_PER_PALETTE
            # Check if offset is within file
            f.seek(0, 2)  # Seek to end
            file_size = f.tell()
            if offset + BYTES_PER_PALETTE > file_size:
                return None

            f.seek(offset)
            palette_data = f.read(BYTES_PER_PALETTE)

        palette = []
        for i in range(COLORS_PER_PALETTE):
            # Read BGR555 color
            color_bytes = palette_data[
                i * BYTES_PER_COLOR : i * BYTES_PER_COLOR + BYTES_PER_COLOR
            ]
            if len(color_bytes) == BYTES_PER_COLOR:
                bgr555 = struct.unpack("<H", color_bytes)[0]
                r, g, b = bgr555_to_rgb888(bgr555)
                palette.extend([r, g, b])
            else:
                palette.extend([0, 0, 0])

        # Fill rest with black (for 256-color palette compatibility)
        while len(palette) < PALETTE_SIZE_BYTES:
            palette.extend([0, 0, 0])

        return palette

    except (OSError, struct.error, ValueError, IndexError):
        # Expected errors from file operations and data parsing
        return None


def get_grayscale_palette() -> list[int]:
    """
    Get default grayscale palette for preview.

    Returns:
        List of 768 RGB values forming a grayscale palette
    """
    palette = []
    for i in range(PALETTE_ENTRIES):
        # For 4bpp sprites, map 0-15 to 0-255
        gray = (i * RGB888_MAX_VALUE) // 15 if i < COLORS_PER_PALETTE else 0
        palette.extend([gray, gray, gray])
    return palette


def read_all_palettes(cgram_file: str) -> list[list[int] | None]:
    """
    Read all 16 palettes from CGRAM dump.

    Args:
        cgram_file: Path to CGRAM dump file

    Returns:
        List of 16 palettes (each palette is a list of RGB values or None)
    """
    palettes = []
    for i in range(MAX_PALETTES):
        palette = read_cgram_palette(cgram_file, i)
        palettes.append(palette)
    return palettes


def apply_palette_with_transparency(palette: list[int]) -> list[int]:
    """
    Apply a palette but handle index 0 as transparent.

    Args:
        palette: Original palette (768 RGB values)

    Returns:
        Modified palette with index 0 set to a neutral color for transparency
    """
    modified_palette = palette.copy()

    # Option 1: Set index 0 to a neutral gray for better visualization
    # This helps distinguish transparent areas from actual sprite pixels
    modified_palette[0] = 240  # R
    modified_palette[1] = 240  # G
    modified_palette[2] = 240  # B

    return modified_palette


def write_cgram_palette(palette: list[int], palette_num: int) -> bytes:
    """
    Convert RGB palette to CGRAM format for a specific palette slot.

    Args:
        palette: List of RGB values (at least 48 values for 16 colors)
        palette_num: Palette number (0-15)

    Returns:
        32 bytes of CGRAM data

    Raises:
        ValueError: If palette doesn't have enough colors
    """
    if len(palette) < COLORS_PER_PALETTE * 3:
        raise ValueError(
            f"Palette must have at least {
                COLORS_PER_PALETTE *
                3} values"
        )

    cgram_data = bytearray()

    for i in range(COLORS_PER_PALETTE):
        r = palette[i * 3]
        g = palette[i * 3 + 1]
        b = palette[i * 3 + 2]

        bgr555 = rgb888_to_bgr555(r, g, b)
        cgram_data.extend(struct.pack("<H", bgr555))

    return bytes(cgram_data)
