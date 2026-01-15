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

    position_changed = Signal(float, float)
    opacity_changed = Signal(float)
    scale_changed = Signal(float)
    visibility_changed = Signal(bool)
    image_changed = Signal()
    resampling_mode_changed = Signal(int)  # Image.Resampling enum value

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._image: Image.Image | None = None
        self._image_path: str | None = None
        self._x: float = 0.0
        self._y: float = 0.0
        self._opacity: float = 0.5
        self._scale: float = 1.0
        self._visible: bool = True
        # Default to NEAREST for pixel art - preserves sharp edges
        self._resampling_mode: Image.Resampling = Image.Resampling.NEAREST

    @property
    def image(self) -> Image.Image | None:
        """The current overlay image."""
        return self._image

    @property
    def image_path(self) -> str | None:
        """Path to the loaded overlay image."""
        return self._image_path

    @property
    def x(self) -> float:
        """X position of overlay (pixels from left)."""
        return self._x

    @property
    def y(self) -> float:
        """Y position of overlay (pixels from top)."""
        return self._y

    @property
    def position(self) -> tuple[float, float]:
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

    @property
    def resampling_mode(self) -> Image.Resampling:
        """Resampling mode for image scaling (NEAREST, BOX, LANCZOS)."""
        return self._resampling_mode

    def import_image(self, path: str, target_width: int | None = None, target_height: int | None = None) -> bool:
        """Import an image from the given path.

        Args:
            path: Path to image file.
            target_width: Optional target width to auto-scale to.
            target_height: Optional target height to auto-scale to.

        Returns:
            True if import succeeded, False otherwise.
        """
        try:
            image = Image.open(path)
            # Convert to RGBA for consistent handling, preserving alpha channel
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            self._image = image
            self._image_path = str(Path(path).resolve())
            self._visible = True  # Auto-show when importing new image

            # Auto-scale if target dimensions provided
            if target_width and target_height:
                # Calculate scale to fit within target (preserving aspect ratio)
                scale_w = target_width / image.width
                scale_h = target_height / image.height
                # Usually users want it to roughly match the size of the sprite.
                initial_scale = min(scale_w, scale_h)
                # Ensure it's not too tiny or too huge initially (0.1% to 100%)
                # Removed the 30% cap which was causing unexpected tiny overlays.
                self._scale = max(0.001, min(1.0, initial_scale))

                # Center it at (0,0)
                self._x = 0.0
                self._y = 0.0

            self.image_changed.emit()
            self.scale_changed.emit(self._scale)
            self.position_changed.emit(self._x, self._y)
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

    def set_position(self, x: float, y: float) -> None:
        """Set the overlay position.

        Args:
            x: X position in pixels.
            y: Y position in pixels.
        """
        if self._x != x or self._y != y:
            self._x = x
            self._y = y
            self.position_changed.emit(x, y)

    def nudge(self, dx: float, dy: float) -> None:
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
            scale: Scale factor (0.001 to 5.0).
        """
        # Increased max scale to 5.0 to allow zooming in on overlays
        scale = max(0.001, min(5.0, scale))
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
            self._x = center_x - new_width / 2
            self._y = center_y - new_height / 2

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

    def set_resampling_mode(self, mode: Image.Resampling) -> None:
        """Set the resampling mode for image scaling.

        Args:
            mode: Resampling mode (NEAREST for pixel art, BOX for smoothed, LANCZOS for high-quality).
        """
        if self._resampling_mode != mode:
            self._resampling_mode = mode
            self.resampling_mode_changed.emit(mode.value)

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
            "resampling_mode": self._resampling_mode.value,
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

            # Restore scale BEFORE position - set_scale adjusts position to maintain
            # visual center, so position must be set after scale
            scale = state.get("scale", 1.0)
            if isinstance(scale, (int, float)):
                self.set_scale(float(scale))

            # Restore position AFTER scale to avoid it being overwritten
            x = state.get("x", 0.0)
            y = state.get("y", 0.0)
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                self.set_position(float(x), float(y))

            # Restore opacity
            opacity = state.get("opacity", 0.5)
            if isinstance(opacity, (int, float)):
                self.set_opacity(float(opacity))

            # Restore visibility
            visible = state.get("visible", True)
            if isinstance(visible, bool):
                self.set_visible(visible)

            # Restore resampling mode
            resampling_mode = state.get("resampling_mode")
            if isinstance(resampling_mode, int):
                self.set_resampling_mode(Image.Resampling(resampling_mode))

            return True
        except (TypeError, ValueError):
            return False

    def sample_region(self, tile_x: int, tile_y: int, tile_width: int, tile_height: int) -> Image.Image | None:
        """Sample a tile-sized region from the overlay at the given canvas position.

        Supports partial overlap: returns a tile-sized RGBA image where
        parts not covered by the overlay are transparent.

        Args:
            tile_x: X position of tile on canvas (pixels).
            tile_y: Y position of tile on canvas (pixels).
            tile_width: Width of tile (pixels).
            tile_height: Height of tile (pixels).

        Returns:
            RGBA image of the sampled region, or None if no overlap.
        """
        if self._image is None:
            return None

        # 1. Define rects in Canvas Space
        tile_rect = (tile_x, tile_y, tile_x + tile_width, tile_y + tile_height)

        # Calculate visual overlay rect
        overlay_w = self._image.width * self._scale
        overlay_h = self._image.height * self._scale
        overlay_rect = (self._x, self._y, self._x + overlay_w, self._y + overlay_h)

        # 2. Calculate Intersection
        ix1 = max(tile_rect[0], overlay_rect[0])
        iy1 = max(tile_rect[1], overlay_rect[1])
        ix2 = min(tile_rect[2], overlay_rect[2])
        iy2 = min(tile_rect[3], overlay_rect[3])

        # Check for non-positive area (no overlap) with epsilon for float precision
        if ix2 <= ix1 + 1e-6 or iy2 <= iy1 + 1e-6:
            return None

        # 3. Calculate Source (Image) Rect
        # Map (ix1, iy1) relative to overlay top-left, then divide by scale
        src_x = (ix1 - self._x) / self._scale
        src_y = (iy1 - self._y) / self._scale
        src_w = (ix2 - ix1) / self._scale
        src_h = (iy2 - iy1) / self._scale

        # 4. Calculate Dest (Tile) Rect
        # Map (ix1, iy1) relative to tile top-left
        dst_x = int(ix1 - tile_x)
        dst_y = int(iy1 - tile_y)
        dst_w = int(ix2 - ix1)
        dst_h = int(iy2 - iy1)

        # Ensure destination dimensions are at least 1x1
        if dst_w <= 0 or dst_h <= 0:
            return None

        # 5. Extract and Scale
        # Use precise sampling box
        sampling_box = (src_x, src_y, src_x + src_w, src_y + src_h)

        try:
            # Resize the cropped region to the destination size
            # Use configured resampling mode (default NEAREST for pixel art)
            sampled_part = self._image.resize((dst_w, dst_h), self._resampling_mode, box=sampling_box)
        except Exception:
            # Fallback for extreme edge cases
            return None

        # 6. Compose into full tile
        # Start with fully transparent image
        result = Image.new("RGBA", (tile_width, tile_height), (0, 0, 0, 0))
        result.paste(sampled_part, (dst_x, dst_y))

        return result

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
