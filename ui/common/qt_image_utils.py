"""Qt-specific image conversion utilities."""

from __future__ import annotations

from io import BytesIO

from PIL import Image
from PySide6.QtGui import QImage, QPixmap


def pil_to_qpixmap(pil_image: Image.Image, format: str = "PNG") -> QPixmap:
    """Convert a PIL Image to a Qt QPixmap.

    Args:
        pil_image: PIL Image to convert
        format: Image format to use for serialization (default: PNG)

    Returns:
        QPixmap representation of the image
    """
    buffer = BytesIO()
    pil_image.save(buffer, format=format)
    buffer.seek(0)
    qimg = QImage()
    qimg.loadFromData(buffer.read())
    return QPixmap.fromImage(qimg)
