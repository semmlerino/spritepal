#!/usr/bin/env python3
"""
Selection mask for indexed image editing.

Provides a boolean mask for tracking selected pixels during editing operations.
"""

from __future__ import annotations

import numpy as np


class SelectionMask:
    """Boolean mask for tracking pixel selection state.

    Provides operations for manipulating selections including add, remove,
    intersect, invert, and get/set pixels.
    """

    def __init__(self, width: int, height: int) -> None:
        """Initialize an empty selection mask.

        Args:
            width: Image width in pixels
            height: Image height in pixels
        """
        self.width = width
        self.height = height
        self._mask = np.zeros((height, width), dtype=bool)

    @property
    def mask(self) -> np.ndarray:
        """Get the underlying boolean numpy array."""
        return self._mask

    def clear(self) -> None:
        """Clear all selection (deselect all pixels)."""
        self._mask.fill(False)

    def select_all(self) -> None:
        """Select all pixels."""
        self._mask.fill(True)

    def invert(self) -> None:
        """Invert the selection."""
        self._mask = np.logical_not(self._mask)

    def is_selected(self, x: int, y: int) -> bool:
        """Check if a pixel is selected.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            True if the pixel is selected, False otherwise
        """
        if 0 <= x < self.width and 0 <= y < self.height:
            return bool(self._mask[y, x])
        return False

    def set_selected(self, x: int, y: int, selected: bool = True) -> None:
        """Set selection state for a single pixel.

        Args:
            x: X coordinate
            y: Y coordinate
            selected: Selection state to set
        """
        if 0 <= x < self.width and 0 <= y < self.height:
            self._mask[y, x] = selected

    def add_pixels(self, pixels: set[tuple[int, int]]) -> None:
        """Add pixels to the selection.

        Args:
            pixels: Set of (x, y) coordinates to add
        """
        for x, y in pixels:
            if 0 <= x < self.width and 0 <= y < self.height:
                self._mask[y, x] = True

    def remove_pixels(self, pixels: set[tuple[int, int]]) -> None:
        """Remove pixels from the selection.

        Args:
            pixels: Set of (x, y) coordinates to remove
        """
        for x, y in pixels:
            if 0 <= x < self.width and 0 <= y < self.height:
                self._mask[y, x] = False

    def set_pixels(self, pixels: set[tuple[int, int]]) -> None:
        """Replace selection with exactly these pixels.

        Clears existing selection and selects only the given pixels.

        Args:
            pixels: Set of (x, y) coordinates to select
        """
        self.clear()
        self.add_pixels(pixels)

    def get_selected_pixels(self) -> set[tuple[int, int]]:
        """Get all currently selected pixels.

        Returns:
            Set of (x, y) coordinates for all selected pixels
        """
        positions = np.where(self._mask)
        return {(int(x), int(y)) for y, x in zip(positions[0], positions[1], strict=True)}

    def get_selection_count(self) -> int:
        """Get the number of selected pixels.

        Returns:
            Count of selected pixels
        """
        return int(np.sum(self._mask))

    def has_selection(self) -> bool:
        """Check if any pixels are selected.

        Returns:
            True if at least one pixel is selected
        """
        return bool(np.any(self._mask))

    def get_bounding_box(self) -> tuple[int, int, int, int] | None:
        """Get the bounding box of the selection.

        Returns:
            Tuple of (x, y, width, height) or None if no selection
        """
        if not self.has_selection():
            return None

        rows = np.any(self._mask, axis=1)
        cols = np.any(self._mask, axis=0)
        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]

        return (int(x_min), int(y_min), int(x_max - x_min + 1), int(y_max - y_min + 1))

    def intersect_with(self, other: SelectionMask) -> None:
        """Intersect this selection with another (in-place).

        Args:
            other: Selection mask to intersect with
        """
        if self.width == other.width and self.height == other.height:
            self._mask = np.logical_and(self._mask, other._mask)

    def union_with(self, other: SelectionMask) -> None:
        """Union this selection with another (in-place).

        Args:
            other: Selection mask to union with
        """
        if self.width == other.width and self.height == other.height:
            self._mask = np.logical_or(self._mask, other._mask)

    def subtract(self, other: SelectionMask) -> None:
        """Subtract another selection from this one (in-place).

        Args:
            other: Selection mask to subtract
        """
        if self.width == other.width and self.height == other.height:
            self._mask = np.logical_and(self._mask, np.logical_not(other._mask))

    def copy(self) -> SelectionMask:
        """Create a copy of this selection mask.

        Returns:
            New SelectionMask with the same selection state
        """
        new_mask = SelectionMask(self.width, self.height)
        new_mask._mask = self._mask.copy()
        return new_mask

    def resize(self, new_width: int, new_height: int) -> None:
        """Resize the mask, clearing all selection.

        Args:
            new_width: New width
            new_height: New height
        """
        self.width = new_width
        self.height = new_height
        self._mask = np.zeros((new_height, new_width), dtype=bool)

    def from_index_mask(self, image_data: np.ndarray, index: int) -> None:
        """Set selection to all pixels with a specific index value.

        Args:
            image_data: 2D array of palette indices
            index: The index value to select
        """
        if image_data.shape == (self.height, self.width):
            self._mask = image_data == index

    def expand(self, pixels: int = 1) -> None:
        """Expand the selection by N pixels (simple dilation).

        Args:
            pixels: Number of pixels to expand by
        """
        from scipy import ndimage

        for _ in range(pixels):
            self._mask = ndimage.binary_dilation(self._mask)

    def contract(self, pixels: int = 1) -> None:
        """Contract the selection by N pixels (simple erosion).

        Args:
            pixels: Number of pixels to contract by
        """
        from scipy import ndimage

        for _ in range(pixels):
            self._mask = ndimage.binary_erosion(self._mask)
