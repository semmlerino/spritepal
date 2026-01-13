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
    scale_changed = Signal(float)
    visibility_changed = Signal(bool)
    image_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._image: Image.Image | None = None
        self._image_path: str | None = None
        self._x: int = 0
        self._y: int = 0
        self._opacity: float = 0.5
        self._scale: float = 1.0
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
    def scale(self) -> float:
        """Scale factor of overlay (1.0 = original size)."""
        return self._scale

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

    def set_scale(self, scale: float) -> None:
        """Set the overlay scale, keeping the center fixed.

        Args:
            scale: Scale factor (0.1 to 10.0).
        """
        scale = max(0.1, min(10.0, scale))
        if self._scale != scale and self._image is not None:
            # Calculate current visual center relative to canvas
            # Visual width/height = original * scale
            old_width = self._image.width * self._scale
            old_height = self._image.height * self._scale
            center_x = self._x + old_width / 2
            center_y = self._y + old_height / 2
            
            # Update scale
            self._scale = scale
            
            # Calculate new top-left to maintain visual center
            new_width = self._image.width * self._scale
            new_height = self._image.height * self._scale
            self._x = int(center_x - new_width / 2)
            self._y = int(center_y - new_height / 2)
            
            self.scale_changed.emit(self._scale)
            self.position_changed.emit(self._x, self._y)
        elif self._scale != scale:
            self._scale = scale
            self.scale_changed.emit(self._scale)

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
            "scale": self._scale,
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

            # Restore scale
            scale = state.get("scale", 1.0)
            if isinstance(scale, (int, float)):
                self.set_scale(float(scale))

            # Restore visibility
            visible = state.get("visible", True)
            if isinstance(visible, bool):
                self.set_visible(visible)

            return True
        except (TypeError, ValueError):
            return False

    def sample_region(self, tile_x: int, tile_y: int, tile_width: int, tile_height: int) -> Image.Image | None:
        """Sample a tile-sized region from the overlay at the given canvas position.

        Accounts for overlay scale.

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

        # When the overlay is scaled, we need to find the corresponding region 
        # in the original full-resolution overlay image.
        
        # Coordinates relative to overlay top-left on canvas
        rel_x = tile_x - self._x
        rel_y = tile_y - self._y
        
        # Scale these relative coordinates to original image space
        # If scale=0.5, then rel_x=10 means sample_x=20 in the original image
        sample_x = rel_x / self._scale
        sample_y = rel_y / self._scale
        
        # Also scale the tile dimensions to original image space
        sample_w = tile_width / self._scale
        sample_h = tile_height / self._scale

        # Check if the region is within bounds (with small epsilon for float precision)
        eps = 1e-6
        if sample_x < -eps or sample_y < -eps:
            return None
        if sample_x + sample_w > self._image.width + eps:
            return None
        if sample_y + sample_h > self._image.height + eps:
            return None

        # Crop the region from the original overlay
        crop_box = (int(sample_x), int(sample_y), int(sample_x + sample_w), int(sample_y + sample_h))
        region = self._image.crop(crop_box)
        
        # Resize the cropped region back to the tile size (8x8)
        # using Lanczos (high quality) or nearest if indices matter
        # Since this is an overlay (RGB/RGBA), we use high quality scaling.
        return region.resize((tile_width, tile_height), Image.Resampling.LANCZOS)

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

        # Same logic as sample_region: check if the mapped region is within bounds
        rel_x = tile_x - self._x
        rel_y = tile_y - self._y
        
        sample_x = rel_x / self._scale
        sample_y = rel_y / self._scale
        sample_w = tile_width / self._scale
        sample_h = tile_height / self._scale

        eps = 1e-6
        if sample_x < -eps or sample_y < -eps:
            return False
        if sample_x + sample_w > self._image.width + eps:
            return False
        if sample_y + sample_h > self._image.height + eps:
            return False

        return True
