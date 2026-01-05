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
    return (b5 << BGR555_BLUE_SHIFT) | (g5 << BGR555_GREEN_SHIFT) | (r5 << BGR555_RED_SHIFT)


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
            color_bytes = palette_data[i * BYTES_PER_COLOR : i * BYTES_PER_COLOR + BYTES_PER_COLOR]
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
