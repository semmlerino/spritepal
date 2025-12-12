"""
Palette colorization for sprite images with caching
"""
from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QObject, Signal

from utils.logging_config import get_logger

logger = get_logger(__name__)


class PaletteColorizer(QObject):
    """Manages palette application to grayscale images with caching"""

    # Signals
    palette_mode_changed = Signal(bool)  # Emitted when palette mode is toggled
    palette_index_changed = Signal(int)  # Emitted when palette index changes

    def __init__(self) -> None:
        super().__init__()
        self._current_palettes: dict[int, list[tuple[int, int, int]]] = {}
        self._palette_applied: bool = False
        self._selected_palette_index: int = 8  # Default to palette 8
        self._colorized_cache: dict[tuple[int, int], Image.Image] = (
            {}
        )  # (row_index, palette_index) -> Image
        self._max_cache_size: int = 100  # Limit cache size to prevent memory issues

    def set_palettes(
        self, palettes_dict: dict[int, list[tuple[int, int, int]]]
    ) -> None:
        """Set the available palettes for colorization

        Args:
            palettes_dict: Dictionary mapping palette index to RGB color lists
        """
        self._current_palettes = palettes_dict
        if self._colorized_cache:
            self._colorized_cache.clear()  # Clear cache when palettes change

    def get_palettes(self) -> dict[int, list[tuple[int, int, int]]]:
        """Get the current palette data

        Returns:
            Dictionary mapping palette index to RGB color lists
        """
        return self._current_palettes.copy()

    def set_selected_palette(self, palette_index: int) -> None:
        """Set the selected palette index

        Args:
            palette_index: The palette index to select (8-15)
        """
        if palette_index != self._selected_palette_index:
            self._selected_palette_index = palette_index
            if self._colorized_cache:
                self._colorized_cache.clear()  # Clear cache when selection changes
            self.palette_index_changed.emit(palette_index)

    def toggle_palette_mode(self) -> bool:
        """Toggle between grayscale and colorized display

        Returns:
            True if palette mode is now enabled, False otherwise
        """
        self._palette_applied = not self._palette_applied
        if self._colorized_cache:
            self._colorized_cache.clear()  # Clear cache when mode changes
        self.palette_mode_changed.emit(self._palette_applied)
        return self._palette_applied

    def cycle_palette(self) -> int:
        """Cycle through available palettes (8-15)

        Returns:
            The newly selected palette index
        """
        if not self._current_palettes:
            return self._selected_palette_index

        # Find next available palette index
        available_indices = [i for i in range(8, 16) if i in self._current_palettes]
        if not available_indices:
            return self._selected_palette_index

        # Find current index in available list
        try:
            current_idx = available_indices.index(self._selected_palette_index)
            next_idx = (current_idx + 1) % len(available_indices)
            self._selected_palette_index = available_indices[next_idx]
        except ValueError:
            # Current palette not found, use first available
            self._selected_palette_index = available_indices[0]

        # Clear cache when palette changes
        if self._colorized_cache:
            self._colorized_cache.clear()
        self.palette_index_changed.emit(self._selected_palette_index)

        return self._selected_palette_index

    def apply_palette_to_image(
        self, grayscale_image: Image.Image, palette_colors: list[tuple[int, int, int]]
    ) -> Image.Image | None:
        """Apply a palette to a grayscale image with transparency support

        Args:
            grayscale_image: Input grayscale image
            palette_colors: List of RGB tuples for the palette

        Returns:
            RGBA image with palette applied, or None on error
        """
        if not grayscale_image or not palette_colors:
            return None

        try:
            # Convert grayscale to RGBA for transparency support
            rgba_image = grayscale_image.convert("RGBA")

            # Get image data
            pixels = rgba_image.load()
            if pixels is None:
                logger.warning("Failed to load image pixels")
                return None
            width, height = rgba_image.size

            # Apply palette
            for y in range(height):
                for x in range(width):
                    # Get pixel value
                    pixel_value = grayscale_image.getpixel((x, y))

                    # Ensure pixel_value is an integer for indexing operations
                    if not isinstance(pixel_value, int):
                        # If it's a tuple or other type, convert to int (take first value)
                        if isinstance(pixel_value, tuple):
                            first_val = pixel_value[0]
                            pixel_value = int(first_val)
                        else:
                            # For non-tuple, non-int values, convert directly
                            pixel_value = int(pixel_value) if pixel_value is not None else 0

                    # For palette mode images, pixel value is already the palette index
                    if grayscale_image.mode == "P":
                        palette_index = pixel_value
                    else:
                        # For grayscale images, map to palette index
                        palette_index = min(15, pixel_value // 16)

                    # Handle transparency for palette index 0
                    if palette_index == 0:
                        # Set transparent pixel
                        pixels[x, y] = (0, 0, 0, 0)
                    elif palette_index < len(palette_colors):
                        # Get RGB color from palette
                        color_tuple = palette_colors[palette_index]
                        r, g, b = color_tuple
                        pixels[x, y] = (r, g, b, 255)
                    else:
                        # Use black for out of range indices
                        pixels[x, y] = (0, 0, 0, 255)

        except Exception as e:
            logger.exception("Error applying palette: %s", e)
            return None
        else:
            return rgba_image

    def get_display_image(
        self, row_index: int, grayscale_image: Image.Image
    ) -> Image.Image:
        """Get the appropriate display image for a row (grayscale or colorized)

        Args:
            row_index: Index of the row for caching
            grayscale_image: The original grayscale image

        Returns:
            Either the original grayscale or colorized image
        """
        # If palette is not applied, return grayscale
        if not self._palette_applied or not self._current_palettes:
            return grayscale_image

        # Check if we have a cached colorized version
        cache_key = (row_index, self._selected_palette_index)
        if cache_key in self._colorized_cache:
            return self._colorized_cache[cache_key]

        # Apply palette and cache the result
        if self._selected_palette_index in self._current_palettes:
            colorized_image = self.apply_palette_to_image(
                grayscale_image, self._current_palettes[self._selected_palette_index]
            )

            if colorized_image:
                self._colorized_cache[cache_key] = colorized_image
                self._enforce_cache_limit()
                return colorized_image

        # Fallback to grayscale if palette application fails
        return grayscale_image

    def is_palette_mode(self) -> bool:
        """Check if palette mode is currently enabled

        Returns:
            True if palette mode is active, False otherwise
        """
        return self._palette_applied

    def get_selected_palette_index(self) -> int:
        """Get the currently selected palette index

        Returns:
            The palette index (8-15)
        """
        return self._selected_palette_index

    def has_palettes(self) -> bool:
        """Check if any palettes are available

        Returns:
            True if palettes are loaded, False otherwise
        """
        return bool(self._current_palettes)

    def clear_cache(self) -> None:
        """Clear the colorized image cache"""
        if self._colorized_cache:
            self._colorized_cache.clear()

    def _enforce_cache_limit(self) -> None:
        """Enforce maximum cache size to prevent memory issues"""
        if len(self._colorized_cache) > self._max_cache_size:
            # Remove oldest entries (simple LRU-like behavior)
            # Convert to list and remove first items
            items = list(self._colorized_cache.items())
            for key, _ in items[: len(items) - self._max_cache_size]:
                del self._colorized_cache[key]
