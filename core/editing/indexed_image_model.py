#!/usr/bin/env python3
"""
Indexed image data model for palette-based editing.
Handles indexed images with configurable bit depth using numpy arrays.

Includes checksum functionality for data integrity verification:
- Checksum is computed when data is loaded via set_data()
- verify_integrity() can be called to detect external modifications
- Useful for round-trip verification (extract -> edit -> save -> extract)
"""

import hashlib
from dataclasses import dataclass, field

import numpy as np


@dataclass
class IndexedImageModel:
    """
    Model for managing indexed image data and operations.
    Supports images with configurable color count (default 16 colors for 4bpp).

    Includes checksum tracking for data integrity verification.
    """

    width: int = 8
    height: int = 8
    data: np.ndarray = field(default_factory=lambda: np.zeros((8, 8), dtype=np.uint8))
    modified: bool = False
    file_path: str | None = None
    max_color_index: int = 15  # Maximum valid color index (default 4bpp = 16 colors)

    # Checksum of data at load time (for integrity verification)
    _initial_checksum: str = field(default="", init=False)

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
        if (
            0 <= x < self.width
            and 0 <= y < self.height
            and 0 <= value <= self.max_color_index
            and self.data[y, x] != value
        ):
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
        if not (0 <= x < self.width and 0 <= y < self.height and 0 <= new_value <= self.max_color_index):
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

            # Add neighbors (4-way connectivity)
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])

        return changed_pixels

    def get_color_at(self, x: int, y: int) -> int:
        """Color picker - get color at coordinates."""
        return self.get_pixel(x, y)

    def set_data(self, data: np.ndarray, *, store_checksum: bool = True) -> None:
        """Set image data from numpy array.

        Args:
            data: The image data as a 2D numpy array of palette indices
            store_checksum: If True, compute and store checksum for integrity tracking
        """
        self.data = data
        self.height, self.width = data.shape
        self.modified = True

        if store_checksum:
            self._initial_checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        """Compute SHA256 checksum of current data.

        Returns:
            Hex string of SHA256 hash (first 32 chars for efficiency)
        """
        return hashlib.sha256(self.data.tobytes()).hexdigest()[:32]

    def get_initial_checksum(self) -> str:
        """Get the checksum computed when data was loaded.

        Returns:
            Empty string if no checksum was stored, otherwise the hex checksum
        """
        return self._initial_checksum

    def get_current_checksum(self) -> str:
        """Compute checksum of current data state.

        Returns:
            Hex string of current data's SHA256 hash
        """
        return self._compute_checksum()

    def verify_integrity(self) -> bool:
        """Verify that data hasn't been corrupted since load.

        Compares current data checksum against the checksum stored at load time.
        This is useful for detecting external modifications or data corruption.

        Returns:
            True if data is intact (or no initial checksum was stored),
            False if data appears corrupted
        """
        if not self._initial_checksum:
            # No checksum stored, can't verify
            return True
        return self._compute_checksum() == self._initial_checksum

    def has_been_modified_since_load(self) -> bool:
        """Check if data has been modified since load (using checksum comparison).

        Different from `modified` flag which tracks any edit. This compares
        actual data content against the initial load state.

        Returns:
            True if data differs from initial load state,
            False if unchanged or no checksum stored
        """
        if not self._initial_checksum:
            return self.modified
        return self._compute_checksum() != self._initial_checksum

    def get_contiguous_region(self, x: int, y: int) -> set[tuple[int, int]]:
        """Get all pixels connected to (x, y) with the same color index.

        Uses 4-way connectivity (up, down, left, right).

        Args:
            x: Starting x coordinate
            y: Starting y coordinate

        Returns:
            Set of (x, y) tuples for all connected pixels with the same index
        """
        if not (0 <= x < self.width and 0 <= y < self.height):
            return set()

        target_value = self.data[y, x]
        region: set[tuple[int, int]] = set()
        stack = [(x, y)]

        while stack:
            cx, cy = stack.pop()

            if (cx, cy) in region:
                continue

            if not (0 <= cx < self.width and 0 <= cy < self.height):
                continue

            if self.data[cy, cx] != target_value:
                continue

            region.add((cx, cy))
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])

        return region

    def get_global_index_pixels(self, index: int) -> set[tuple[int, int]]:
        """Get all pixels with the specified color index in the entire image.

        Args:
            index: The color index to search for

        Returns:
            Set of (x, y) tuples for all pixels with that index
        """
        if not (0 <= index <= self.max_color_index):
            return set()

        # Find all positions where data equals the index
        positions = np.where(self.data == index)
        return {(int(x), int(y)) for y, x in zip(positions[0], positions[1], strict=True)}

    def copy_data(self) -> np.ndarray:
        """Return a copy of the image data array.

        Returns:
            A deep copy of the data array
        """
        return self.data.copy()
