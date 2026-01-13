"""
Overlay layer for sprite rearrangement.

Provides an overlay image layer that can be positioned over the arranged tiles
to serve as a reference for sprite reconstruction.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, Signal


class OverlayLayer(QObject):
    """Manages an overlay image layer for sprite reference/replacement.

    The overlay can be imported, positioned, and its opacity controlled.
    Used during the Apply operation to sample pixels and write to tiles.

    Signals:
        position_changed: Emitted when overlay position changes (x, y).
        opacity_changed: Emitted when opacity changes (0.0-1.0).
        visibility_changed: Emitted when visibility toggles (bool).
        image_changed: Emitted when overlay image is loaded or cleared.
    """

    position_changed = Signal(int, int)
    opacity_changed = Signal(float)
    visibility_changed = Signal(bool)
    image_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._image: Image.Image | None = None
        self._image_path: str | None = None
        self._x: int = 0
        self._y: int = 0
        self._opacity: float = 0.5
        self._visible: bool = True

    @property
    def image(self) -> Image.Image | None:
        """The current overlay image."""
        return self._image

    @property
    def image_path(self) -> str | None:
        """Path to the loaded overlay image."""
        return self._image_path

    @property
    def x(self) -> int:
        """X position of overlay (pixels from left)."""
        return self._x

    @property
    def y(self) -> int:
        """Y position of overlay (pixels from top)."""
        return self._y

    @property
    def position(self) -> tuple[int, int]:
        """Current overlay position as (x, y)."""
        return (self._x, self._y)

    @property
    def opacity(self) -> float:
        """Opacity of overlay (0.0 = transparent, 1.0 = opaque)."""
        return self._opacity

    @property
    def visible(self) -> bool:
        """Whether the overlay is visible."""
        return self._visible

    def import_image(self, path: str) -> bool:
        """Import an image from the given path.

        Args:
            path: Path to image file.

        Returns:
            True if import succeeded, False otherwise.
        """
        try:
            image = Image.open(path)
            # Convert to RGBA for consistent handling
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            self._image = image
            self._image_path = str(Path(path).resolve())
            self.image_changed.emit()
            return True
        except (OSError, ValueError) as e:
            # Log error but don't crash
            import logging

            logging.getLogger(__name__).warning(f"Failed to import overlay: {e}")
            return False

    def clear_image(self) -> None:
        """Clear the current overlay image."""
        self._image = None
        self._image_path = None
        self.image_changed.emit()

    def set_position(self, x: int, y: int) -> None:
        """Set the overlay position.

        Args:
            x: X position in pixels.
            y: Y position in pixels.
        """
        if self._x != x or self._y != y:
            self._x = x
            self._y = y
            self.position_changed.emit(x, y)

    def nudge(self, dx: int, dy: int) -> None:
        """Nudge the overlay position by delta.

        Args:
            dx: Horizontal delta (positive = right).
            dy: Vertical delta (positive = down).
        """
        self.set_position(self._x + dx, self._y + dy)

    def set_opacity(self, opacity: float) -> None:
        """Set the overlay opacity.

        Args:
            opacity: Opacity value between 0.0 and 1.0.
        """
        opacity = max(0.0, min(1.0, opacity))
        if self._opacity != opacity:
            self._opacity = opacity
            self.opacity_changed.emit(opacity)

    def toggle_visibility(self) -> bool:
        """Toggle overlay visibility.

        Returns:
            The new visibility state.
        """
        self._visible = not self._visible
        self.visibility_changed.emit(self._visible)
        return self._visible

    def set_visible(self, visible: bool) -> None:
        """Set overlay visibility.

        Args:
            visible: True to show, False to hide.
        """
        if self._visible != visible:
            self._visible = visible
            self.visibility_changed.emit(visible)

    def has_image(self) -> bool:
        """Check if an overlay image is loaded."""
        return self._image is not None

    def get_state(self) -> dict[str, object]:
        """Get the current overlay state for persistence.

        Returns:
            Dictionary containing overlay state.
        """
        return {
            "image_path": self._image_path,
            "x": self._x,
            "y": self._y,
            "opacity": self._opacity,
            "visible": self._visible,
        }

    def restore_state(self, state: dict[str, object]) -> bool:
        """Restore overlay state from a dictionary.

        Args:
            state: State dictionary from get_state().

        Returns:
            True if state was restored successfully.
        """
        try:
            # Restore image if path is provided
            image_path = state.get("image_path")
            if isinstance(image_path, str) and image_path:
                if not self.import_image(image_path):
                    return False

            # Restore position
            x = state.get("x", 0)
            y = state.get("y", 0)
            if isinstance(x, int) and isinstance(y, int):
                self.set_position(x, y)

            # Restore opacity
            opacity = state.get("opacity", 0.5)
            if isinstance(opacity, (int, float)):
                self.set_opacity(float(opacity))

            # Restore visibility
            visible = state.get("visible", True)
            if isinstance(visible, bool):
                self.set_visible(visible)

            return True
        except (TypeError, ValueError):
            return False

    def sample_region(self, tile_x: int, tile_y: int, tile_width: int, tile_height: int) -> Image.Image | None:
        """Sample a tile-sized region from the overlay at the given canvas position.

        Used during Apply operation to extract pixels for a tile.

        Args:
            tile_x: X position of tile on canvas (pixels).
            tile_y: Y position of tile on canvas (pixels).
            tile_width: Width of tile (pixels).
            tile_height: Height of tile (pixels).

        Returns:
            RGBA image of the sampled region, or None if no overlay or region out of bounds.
        """
        if self._image is None:
            return None

        # Calculate the region to sample from overlay coordinates
        # The tile is at (tile_x, tile_y) on the canvas
        # The overlay is at (self._x, self._y) on the canvas
        # So the corresponding overlay coordinates are:
        sample_x = tile_x - self._x
        sample_y = tile_y - self._y

        # Check if the region is within bounds
        if sample_x < 0 or sample_y < 0:
            return None
        if sample_x + tile_width > self._image.width:
            return None
        if sample_y + tile_height > self._image.height:
            return None

        # Crop the region from the overlay
        return self._image.crop((sample_x, sample_y, sample_x + tile_width, sample_y + tile_height))

    def covers_tile(self, tile_x: int, tile_y: int, tile_width: int, tile_height: int) -> bool:
        """Check if the overlay fully covers a tile region.

        Args:
            tile_x: X position of tile on canvas (pixels).
            tile_y: Y position of tile on canvas (pixels).
            tile_width: Width of tile (pixels).
            tile_height: Height of tile (pixels).

        Returns:
            True if overlay fully covers the tile, False otherwise.
        """
        if self._image is None:
            return False

        sample_x = tile_x - self._x
        sample_y = tile_y - self._y

        # Check all four corners are within overlay bounds
        if sample_x < 0 or sample_y < 0:
            return False
        if sample_x + tile_width > self._image.width:
            return False
        if sample_y + tile_height > self._image.height:
            return False

        return True
