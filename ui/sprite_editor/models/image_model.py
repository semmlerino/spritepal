#!/usr/bin/env python3
"""
Image data model for the pixel editor.
Handles indexed images with 4bpp format using numpy arrays.
"""

from dataclasses import dataclass, field

import numpy as np


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
        Uses visited set to prevent revisiting pixels (robust algorithm).
        """
        if not (0 <= x < self.width and 0 <= y < self.height and 0 <= new_value <= 15):
            return []

        target_value = self.data[y, x]
        if target_value == new_value:
            return []

        changed_pixels: list[tuple[int, int]] = []
        stack = [(x, y)]
        visited: set[tuple[int, int]] = set()

        while stack:
            cx, cy = stack.pop()

            if (cx, cy) in visited:
                continue

            if not (0 <= cx < self.width and 0 <= cy < self.height):
                continue

            if self.data[cy, cx] != target_value:
                continue

            visited.add((cx, cy))
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
