"""
Image utility functions for SpritePal.

This module provides Qt-dependent image conversion utilities.
Moved from utils/image_utils.py to fix layer boundary violations
(utils should be stdlib-only per docs/architecture.md).
"""
from __future__ import annotations

import io

from PIL import Image
from PySide6.QtGui import QPixmap

from utils.logging_config import get_logger

logger = get_logger(__name__)


def pil_to_qpixmap(pil_image: Image.Image | None) -> QPixmap | None:
    """
    Convert PIL image to QPixmap with proper error handling.

    Args:
        pil_image: PIL Image object to convert

    Returns:
        QPixmap object or None if conversion fails
    """
    if not pil_image:
        logger.debug("pil_to_qpixmap called with None image")
        return None

    try:
        # Log image details for debugging
        logger.debug(
            f"Converting PIL image: size={pil_image.size}, mode={pil_image.mode}, format={pil_image.format}"
        )

        # Convert PIL image to QPixmap through bytes buffer
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        buffer_size = buffer.tell()
        _ = buffer.seek(0)

        logger.debug(f"PIL image saved to buffer: {buffer_size} bytes")

        pixmap = QPixmap()
        buffer_data = buffer.read()

        # Check if buffer data looks valid
        if len(buffer_data) < 8:
            logger.error(f"Buffer data too small: {len(buffer_data)} bytes")
            return None

        # Check PNG header
        if not buffer_data.startswith(b"\x89PNG\r\n\x1a\n"):
            logger.error(
                f"Buffer data doesn't start with PNG header. First 16 bytes: {buffer_data[:16]}"
            )
            return None

        logger.debug(f"Loading {len(buffer_data)} bytes into QPixmap")
        if pixmap.loadFromData(buffer_data):
            logger.debug(
                f"Successfully created QPixmap: {pixmap.size().width()}x{pixmap.size().height()}"
            )
            return pixmap
        logger.error(f"QPixmap.loadFromData() failed. Data size: {len(buffer_data)} bytes")
        logger.error(
            f"PNG header check: {buffer_data[:16].hex() if len(buffer_data) >= 16 else 'too short'}"
        )
        return None

    except Exception:
        logger.exception(
            "Failed to convert PIL to QPixmap. PIL image details: size=%s, mode=%s",
            getattr(pil_image, "size", "unknown"),
            getattr(pil_image, "mode", "unknown"),
        )
        return None


def create_checkerboard_pattern(
    width: int,
    height: int,
    tile_size: int = 8,
    color1: tuple[int, int, int] = (200, 200, 200),
    color2: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """
    Create a checkerboard pattern image.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        tile_size: Size of each checkerboard tile
        color1: RGB tuple for first color
        color2: RGB tuple for second color

    Returns:
        PIL Image with checkerboard pattern
    """
    img = Image.new("RGB", (width, height))

    # Create checkerboard using efficient array operations
    for y in range(0, height, tile_size):
        for x in range(0, width, tile_size):
            # Determine color based on position
            is_even = ((x // tile_size) + (y // tile_size)) % 2 == 0
            color = color1 if is_even else color2

            # Fill tile area
            for dy in range(min(tile_size, height - y)):
                for dx in range(min(tile_size, width - x)):
                    img.putpixel((x + dx, y + dy), color)

    return img
