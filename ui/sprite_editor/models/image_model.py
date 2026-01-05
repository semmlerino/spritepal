#!/usr/bin/env python3
"""
Image data model for the pixel editor.
Handles indexed images with 4bpp format using numpy arrays.
"""

from dataclasses import dataclass, field
from pathlib import Path, PosixPath, WindowsPath
from typing import Any

import numpy as np
from PIL import Image


def _sanitize_for_json(obj: Any) -> Any:  # type: ignore[reportExplicitAny]
    """Convert non-JSON-serializable objects to JSON-safe types."""
    if isinstance(obj, str | int | float | bool | type(None)):
        return obj
    if isinstance(obj, Path | WindowsPath | PosixPath):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="ignore")
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_sanitize_for_json(item) for item in obj]
    # Fallback: convert to string
    return str(obj)


@dataclass
class ImageModel:
    """
    Model for managing image data and operations.
    Handles indexed images with 4bpp format (16 colors).
    """

    width: int = 8
    height: int = 8
    data: np.ndarray = field(default_factory=lambda: np.zeros((8, 8), dtype=np.uint8))
    modified: bool = False
    file_path: str | None = None

    def __post_init__(self) -> None:
        """Ensure data array matches dimensions."""
        if self.data.shape != (self.height, self.width):
            self.data = np.zeros((self.height, self.width), dtype=np.uint8)

    def new_image(self, width: int, height: int) -> None:
        """Create a new blank image."""
        self.width = width
        self.height = height
        self.data = np.zeros((height, width), dtype=np.uint8)
        self.modified = True
        self.file_path = None

    def load_from_pil(self, pil_image: Image.Image) -> dict[str, Any]:  # type: ignore[reportExplicitAny]
        """
        Load image data from a PIL Image.
        Returns metadata including palette information.
        """
        if pil_image.mode != "P":
            raise ValueError(f"Expected indexed image (mode 'P'), got mode '{pil_image.mode}'")

        self.width = pil_image.width
        self.height = pil_image.height
        self.data = np.array(pil_image, dtype=np.uint8)
        self.modified = False

        # Extract metadata
        metadata: dict[str, Any] = {  # type: ignore[reportExplicitAny]
            "width": self.width,
            "height": self.height,
            "mode": pil_image.mode,
        }

        # Get palette if available
        palette_data = pil_image.getpalette()
        if palette_data:
            metadata["palette"] = palette_data

        # Get any custom info
        if hasattr(pil_image, "info"):
            metadata["info"] = _sanitize_for_json(pil_image.info)

        return metadata

    def to_pil_image(self, palette: list[int] | None = None) -> Image.Image:
        """Convert to PIL Image with optional palette."""
        img = Image.fromarray(self.data, mode="P")

        if palette:
            img.putpalette(palette)

        return img

    def get_pixel(self, x: int, y: int) -> int:
        """Get pixel value at coordinates."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return int(self.data[y, x])
        return 0

    def set_pixel(self, x: int, y: int, value: int) -> bool:
        """
        Set pixel value at coordinates.
        Returns True if pixel was changed.
        """
        if 0 <= x < self.width and 0 <= y < self.height and 0 <= value <= 15 and self.data[y, x] != value:
            self.data[y, x] = value
            self.modified = True
            return True
        return False

    def fill(self, x: int, y: int, new_value: int) -> list[tuple[int, int]]:
        """
        Flood fill from coordinates.
        Returns list of changed pixels.
        """
        if not (0 <= x < self.width and 0 <= y < self.height and 0 <= new_value <= 15):
            return []

        target_value = self.data[y, x]
        if target_value == new_value:
            return []

        changed_pixels: list[tuple[int, int]] = []
        stack = [(x, y)]

        while stack:
            cx, cy = stack.pop()
            if 0 <= cx < self.width and 0 <= cy < self.height and self.data[cy, cx] == target_value:
                self.data[cy, cx] = new_value
                changed_pixels.append((cx, cy))
                self.modified = True

                # Add neighbors
                stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])

        return changed_pixels

    def get_color_at(self, x: int, y: int) -> int:
        """Color picker - get color at coordinates."""
        return self.get_pixel(x, y)

    def set_data(self, data: np.ndarray) -> None:
        """Set image data from numpy array."""
        self.data = data
        self.height, self.width = data.shape
        self.modified = True
