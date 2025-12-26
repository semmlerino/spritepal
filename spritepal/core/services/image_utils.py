"""
Image utility functions for SpritePal.

This module provides Qt-dependent image conversion utilities.
Moved from utils/image_utils.py to fix layer boundary violations
(utils should be stdlib-only per docs/architecture.md).
"""

from __future__ import annotations

import io

from PIL import Image
from PySide6.QtGui import QImage, QPixmap

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
        logger.debug(f"Converting PIL image: size={pil_image.size}, mode={pil_image.mode}, format={pil_image.format}")

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
            logger.error(f"Buffer data doesn't start with PNG header. First 16 bytes: {buffer_data[:16]}")
            return None

        logger.debug(f"Loading {len(buffer_data)} bytes into QPixmap")
        if pixmap.loadFromData(buffer_data):
            logger.debug(f"Successfully created QPixmap: {pixmap.size().width()}x{pixmap.size().height()}")
            return pixmap
        logger.error(f"QPixmap.loadFromData() failed. Data size: {len(buffer_data)} bytes")
        logger.error(f"PNG header check: {buffer_data[:16].hex() if len(buffer_data) >= 16 else 'too short'}")
        return None

    except Exception:
        logger.exception(
            "Failed to convert PIL to QPixmap. PIL image details: size=%s, mode=%s",
            getattr(pil_image, "size", "unknown"),
            getattr(pil_image, "mode", "unknown"),
        )
        return None


def pil_to_qimage(
    image: Image.Image,
    *,
    with_alpha: bool = False,
    thread_safe: bool = False,
) -> QImage:
    """
    Convert PIL Image to QImage with consistent mode handling.

    This is the canonical conversion function that should be used throughout
    the codebase to ensure consistent image display behavior.

    Args:
        image: PIL Image to convert
        with_alpha: If True, convert palette/RGB images to RGBA for transparency support.
                   Use this when the image may have transparency or needs alpha blending.
        thread_safe: If True, return a deep copy of the QImage. Required when calling
                    from worker threads since Qt images share underlying data.

    Returns:
        QImage ready for display or further Qt operations

    Note:
        - Palette (P) mode images are converted to RGB/RGBA, preserving palette colors
        - Grayscale (L) mode images remain grayscale
        - Already RGBA images are used as-is
    """
    width, height = image.size

    if image.mode == "RGBA":
        # Already in RGBA - most efficient path
        bytes_data = image.tobytes("raw", "RGBA")
        qimage = QImage(bytes_data, width, height, width * 4, QImage.Format.Format_RGBA8888)
    elif image.mode == "RGB":
        if with_alpha:
            # Convert to RGBA for alpha support
            image = image.convert("RGBA")
            bytes_data = image.tobytes("raw", "RGBA")
            qimage = QImage(bytes_data, width, height, width * 4, QImage.Format.Format_RGBA8888)
        else:
            # Keep as RGB
            bytes_data = image.tobytes("raw", "RGB")
            qimage = QImage(bytes_data, width, height, width * 3, QImage.Format.Format_RGB888)
    elif image.mode == "L":
        # Grayscale - use native grayscale format
        bytes_data = image.tobytes("raw", "L")
        qimage = QImage(bytes_data, width, height, width, QImage.Format.Format_Grayscale8)
    elif image.mode == "P":
        # Palette mode - convert to RGB/RGBA to preserve palette colors
        if with_alpha:
            image = image.convert("RGBA")
            bytes_data = image.tobytes("raw", "RGBA")
            qimage = QImage(bytes_data, width, height, width * 4, QImage.Format.Format_RGBA8888)
        else:
            image = image.convert("RGB")
            bytes_data = image.tobytes("raw", "RGB")
            qimage = QImage(bytes_data, width, height, width * 3, QImage.Format.Format_RGB888)
    else:  # noqa: PLR5501 - intentional nesting for fallback case
        # Fallback for other modes (LA, CMYK, etc.)
        if with_alpha:
            image = image.convert("RGBA")
            bytes_data = image.tobytes("raw", "RGBA")
            qimage = QImage(bytes_data, width, height, width * 4, QImage.Format.Format_RGBA8888)
        else:
            image = image.convert("RGB")
            bytes_data = image.tobytes("raw", "RGB")
            qimage = QImage(bytes_data, width, height, width * 3, QImage.Format.Format_RGB888)

    # For thread safety, return a copy since bytes_data may be garbage collected
    # and the QImage references that memory
    if thread_safe:
        return qimage.copy()
    return qimage.copy()  # Always copy since bytes_data is local


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
