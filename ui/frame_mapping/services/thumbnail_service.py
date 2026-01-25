"""Thumbnail generation service for frame mapping UI.

This service provides consistent thumbnail generation for AI frames and game frames,
ensuring WYSIWYG behavior by using the same quantization logic as injection.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from core.palette_utils import (
    QUANTIZATION_TRANSPARENCY_THRESHOLD,
    quantize_to_palette,
    quantize_with_mappings,
)
from core.services.image_utils import pil_to_qpixmap
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette

logger = get_logger(__name__)

# Default thumbnail size for list items and table cells
DEFAULT_THUMBNAIL_SIZE = 64


def create_quantized_thumbnail(
    frame_path: Path,
    sheet_palette: SheetPalette | None,
    size: int = DEFAULT_THUMBNAIL_SIZE,
) -> QPixmap | None:
    """Create a palette-quantized thumbnail for an AI frame.

    If a sheet palette is defined, quantizes the frame image to show
    WYSIWYG colors matching the injection result. Otherwise loads
    the raw PNG.

    Args:
        frame_path: Path to the AI frame PNG file
        sheet_palette: SheetPalette for quantization, or None for raw colors
        size: Thumbnail size in pixels (square)

    Returns:
        Scaled QPixmap ready for list item icon, or None on failure
    """
    if not frame_path.exists():
        return None

    # Load original image with PIL
    try:
        pil_image = Image.open(frame_path)
    except Exception:
        logger.warning("Failed to load image: %s", frame_path)
        return None

    # Apply palette quantization if palette is defined
    if sheet_palette is not None:
        try:
            pil_image = quantize_pil_image(pil_image, sheet_palette)
        except Exception:
            logger.warning("Failed to quantize image: %s", frame_path, exc_info=True)
            # Fall through to use original image

    # Convert to QPixmap
    pixmap = pil_to_qpixmap(pil_image)
    if pixmap is None or pixmap.isNull():
        return None

    # Scale to thumbnail size
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def quantize_pil_image(
    pil_image: Image.Image,
    sheet_palette: SheetPalette,
) -> Image.Image:
    """Quantize a PIL image to the sheet palette.

    Args:
        pil_image: Source image (any mode, will be converted to RGBA)
        sheet_palette: SheetPalette with colors and optional color_mappings

    Returns:
        Quantized RGBA image
    """
    # Ensure RGBA for quantization
    if pil_image.mode != "RGBA":
        pil_image = pil_image.convert("RGBA")

    # Use color_mappings if defined, otherwise simple quantization
    if sheet_palette.color_mappings:
        indexed = quantize_with_mappings(
            pil_image,
            sheet_palette.colors,
            sheet_palette.color_mappings,
            transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
        )
    else:
        indexed = quantize_to_palette(
            pil_image,
            sheet_palette.colors,
            transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
        )

    # Convert indexed back to RGBA for display (preserves palette colors)
    return indexed.convert("RGBA")


def quantize_qpixmap(
    pixmap: QPixmap,
    sheet_palette: SheetPalette | None,
) -> QPixmap:
    """Quantize a QPixmap to match the sheet palette.

    When a sheet palette is set, the pixmap will be quantized to show
    how the sprite will look when injected. This ensures WYSIWYG behavior
    between preview thumbnails and actual injection results.

    Args:
        pixmap: The raw QPixmap to quantize
        sheet_palette: SheetPalette for quantization, or None to return original

    Returns:
        Quantized QPixmap if sheet palette is set, otherwise the original
    """
    if sheet_palette is None:
        return pixmap

    try:
        # Convert QPixmap to PIL Image via QImage
        qimage = pixmap.toImage()
        if qimage.isNull():
            return pixmap

        width = qimage.width()
        height = qimage.height()

        # Ensure ARGB32 format for consistent byte layout
        qimage = qimage.convertToFormat(qimage.Format.Format_ARGB32)

        # Get raw bytes and convert to PIL
        img_data = bytes(qimage.bits())
        pil_image = Image.frombytes("RGBA", (width, height), img_data, "raw", "BGRA")

        # Quantize to sheet palette
        pil_image = quantize_pil_image(pil_image, sheet_palette)

        # Convert back to QPixmap
        result = pil_to_qpixmap(pil_image)
        if result is None or result.isNull():
            return pixmap
        return result

    except Exception:
        logger.debug("QPixmap quantization failed, using original")
        return pixmap
