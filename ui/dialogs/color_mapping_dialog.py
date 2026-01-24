"""Dialog for previewing and editing overlay-to-palette color mappings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.components.base.dialog_base import DialogBase
from utils.color_distance import perceptual_distance_sq

if TYPE_CHECKING:
    from PIL import Image

    from ui.row_arrangement.grid_arrangement_manager import ArrangementType
    from ui.row_arrangement.overlay_layer import OverlayLayer


def _color_distance_sq(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """Calculate squared perceptual distance between two RGB colors using CIELAB.

    This provides better matching for human perception than RGB Euclidean distance.
    """
    return perceptual_distance_sq(c1, c2)


def snap_to_snes_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Snap an RGB color to the nearest SNES-valid color.

    SNES uses BGR555 (5 bits per channel), so valid RGB888 values
    must be multiples of 8: 0, 8, 16, ..., 240, 248.

    Args:
        color: RGB tuple with 8-bit values (0-255)

    Returns:
        RGB tuple snapped to nearest SNES-valid values
    """

    def snap_component(val: int) -> int:
        # Round to nearest multiple of 8, clamped to 0-248
        snapped = round(val / 8) * 8
        return max(0, min(248, snapped))

    return (snap_component(color[0]), snap_component(color[1]), snap_component(color[2]))


def _find_nearest_palette_index(
    color: tuple[int, int, int],
    palette: list[tuple[int, int, int]],
    skip_zero: bool = True,
) -> int:
    """Find the palette index with the nearest color.

    Args:
        color: RGB color tuple to match
        palette: List of RGB palette colors
        skip_zero: If True, skip index 0 (transparency) for opaque colors

    Returns:
        Index of nearest palette color
    """
    min_dist = float("inf")
    best_idx = 1 if skip_zero else 0

    for idx, pal_color in enumerate(palette):
        if skip_zero and idx == 0:
            continue
        dist = _color_distance_sq(color, pal_color)
        if dist < min_dist:
            min_dist = dist
            best_idx = idx

    return best_idx


class ColorSwatchWidget(QWidget):
    """Small widget displaying a colored square."""

    def __init__(self, color: tuple[int, int, int], size: int = 24, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)

    def set_color(self, color: tuple[int, int, int]) -> None:
        """Update the displayed color."""
        self._color = color
        self.update()

    @override
    def paintEvent(self, event: object) -> None:
        """Draw the color swatch."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(*self._color))
        painter.setPen(Qt.GlobalColor.black)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        painter.end()


class ColorMappingRow(QWidget):
    """A single row showing: overlay color → palette color mapping."""

    mapping_changed = Signal(tuple, int)  # (overlay_color, new_palette_index)

    def __init__(
        self,
        overlay_color: tuple[int, int, int],
        pixel_count: int,
        palette: list[tuple[int, int, int]],
        initial_index: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._overlay_color = overlay_color
        self._palette = palette

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # Overlay color swatch
        self._overlay_swatch = ColorSwatchWidget(overlay_color, size=28)
        layout.addWidget(self._overlay_swatch)

        # Overlay color info
        info_label = QLabel(f"RGB({overlay_color[0]}, {overlay_color[1]}, {overlay_color[2]})  [{pixel_count} px]")
        info_label.setMinimumWidth(180)
        layout.addWidget(info_label)

        # Arrow
        arrow_label = QLabel("→")
        arrow_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(arrow_label)

        # Palette color dropdown
        self._palette_combo = QComboBox()
        self._palette_combo.setMinimumWidth(200)
        self._populate_palette_combo(initial_index)
        _ = self._palette_combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self._palette_combo)

        # Palette color swatch (shows current selection)
        self._palette_swatch = ColorSwatchWidget(palette[initial_index], size=28)
        layout.addWidget(self._palette_swatch)

        layout.addStretch()

    def _populate_palette_combo(self, selected_index: int) -> None:
        """Populate the palette dropdown."""
        for idx, color in enumerate(self._palette):
            # Create a small color icon for the dropdown
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(*color))
            label = f"[{idx}] RGB({color[0]}, {color[1]}, {color[2]})"
            if idx == 0:
                label += " (transparent)"
            self._palette_combo.addItem(label)
            # Set icon after adding
            self._palette_combo.setItemIcon(idx, pixmap)

        self._palette_combo.setCurrentIndex(selected_index)

    def _on_combo_changed(self, index: int) -> None:
        """Handle palette selection change."""
        if 0 <= index < len(self._palette):
            self._palette_swatch.set_color(self._palette[index])
            self.mapping_changed.emit(self._overlay_color, index)

    def get_mapping(self) -> tuple[tuple[int, int, int], int]:
        """Get the current mapping (overlay_color, palette_index)."""
        return (self._overlay_color, self._palette_combo.currentIndex())


class ColorMappingDialog(DialogBase):
    """Dialog for previewing and editing color mappings before overlay apply."""

    def __init__(
        self,
        overlay_colors: dict[tuple[int, int, int], int],  # color -> pixel count
        palette: list[tuple[int, int, int]],
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the color mapping dialog.

        Args:
            overlay_colors: Dict of unique overlay RGB colors to their pixel counts
            palette: The target palette (16 RGB colors)
            parent: Parent widget
        """
        # Store before super().__init__ (DialogBase pattern)
        self._overlay_colors = overlay_colors
        self._palette = palette

        # Will store final mappings: overlay_color -> palette_index
        self._color_mappings: dict[tuple[int, int, int], int] = {}

        # Compute initial mappings (nearest color)
        for color in overlay_colors:
            self._color_mappings[color] = _find_nearest_palette_index(color, palette)

        # UI components
        self._mapping_rows: list[ColorMappingRow] = []

        super().__init__(
            parent,
            title="Color Mapping Preview",
            min_size=(550, 400),
            with_button_box=True,
        )

        # Customize button box
        if self.button_box:
            ok_button = self.button_box.button(self.button_box.StandardButton.Ok)
            if ok_button:
                ok_button.setText("Apply with Mappings")

    @property
    def color_mappings(self) -> dict[tuple[int, int, int], int]:
        """Get the final color mappings (overlay RGB -> palette index)."""
        return self._color_mappings

    @override
    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        content_layout = QVBoxLayout()
        content_layout.setSpacing(8)

        # Header
        header = QLabel(
            "<b>Review Color Mappings</b><br>"
            "Each overlay color is shown with its target palette color.<br>"
            "Click the dropdown to change any incorrect mappings."
        )
        header.setWordWrap(True)
        content_layout.addWidget(header)

        # Palette preview
        palette_group = QWidget()
        palette_layout = QHBoxLayout(palette_group)
        palette_layout.setContentsMargins(0, 8, 0, 8)
        palette_label = QLabel("Palette: ")
        palette_layout.addWidget(palette_label)

        for idx, color in enumerate(self._palette):
            swatch = ColorSwatchWidget(color, size=20)
            swatch.setToolTip(f"[{idx}] RGB({color[0]}, {color[1]}, {color[2]})")
            palette_layout.addWidget(swatch)

        palette_layout.addStretch()
        content_layout.addWidget(palette_group)

        # Scrollable area for color mappings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(2)

        # Sort colors by pixel count (most common first)
        sorted_colors = sorted(
            self._overlay_colors.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        # Limit displayed colors to prevent UI slowdown
        max_displayed = 50
        displayed_colors = sorted_colors[:max_displayed]
        hidden_count = len(sorted_colors) - len(displayed_colors)

        for color, pixel_count in displayed_colors:
            initial_idx = self._color_mappings[color]
            row = ColorMappingRow(color, pixel_count, self._palette, initial_idx)
            _ = row.mapping_changed.connect(self._on_mapping_changed)
            self._mapping_rows.append(row)
            scroll_layout.addWidget(row)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        content_layout.addWidget(scroll)

        # Summary
        if hidden_count > 0:
            summary = QLabel(
                f"Showing top {max_displayed} of {len(self._overlay_colors)} unique colors "
                f"({sum(self._overlay_colors.values())} total pixels)\n"
                f"Note: {hidden_count} minor colors will use nearest-color matching."
            )
        else:
            summary = QLabel(
                f"Total: {len(self._overlay_colors)} unique colors, {sum(self._overlay_colors.values())} pixels"
            )
        content_layout.addWidget(summary)

        self.set_content_layout(content_layout)

    def _on_mapping_changed(self, overlay_color: tuple[int, int, int], palette_index: int) -> None:
        """Handle a mapping change from a row."""
        self._color_mappings[overlay_color] = palette_index


def extract_unique_colors(
    image: Image.Image,
    ignore_transparent: bool = True,
    alpha_threshold: int = 128,
) -> dict[tuple[int, int, int], int]:
    """Extract unique RGB colors from an image with their pixel counts.

    Args:
        image: PIL Image to analyze
        ignore_transparent: If True, skip pixels with alpha < threshold
        alpha_threshold: Alpha value below which pixels are considered transparent

    Returns:
        Dict mapping RGB tuples to pixel counts
    """
    import numpy as np

    if image.mode != "RGBA":
        image = image.convert("RGBA")

    # Convert to numpy array for fast processing
    pixels = np.array(image)

    # Flatten to (N, 4) where N is total pixels
    flat_pixels = pixels.reshape(-1, 4)

    # Filter out transparent pixels if requested
    if ignore_transparent:
        opaque_mask = flat_pixels[:, 3] >= alpha_threshold
        flat_pixels = flat_pixels[opaque_mask]

    if len(flat_pixels) == 0:
        return {}

    # Get RGB only (drop alpha)
    rgb_pixels = flat_pixels[:, :3]

    # Use numpy unique to count colors efficiently
    # Pack RGB into single integers for fast comparison
    packed = (
        rgb_pixels[:, 0].astype(np.uint32) << 16
        | rgb_pixels[:, 1].astype(np.uint32) << 8
        | rgb_pixels[:, 2].astype(np.uint32)
    )
    unique_packed, counts = np.unique(packed, return_counts=True)

    # Unpack back to RGB tuples
    color_counts: dict[tuple[int, int, int], int] = {}
    for packed_color, count in zip(unique_packed, counts, strict=False):
        r = int((packed_color >> 16) & 0xFF)
        g = int((packed_color >> 8) & 0xFF)
        b = int(packed_color & 0xFF)
        color_counts[(r, g, b)] = int(count)

    return color_counts


def extract_colors_from_sampled_overlay(
    overlay_layer: OverlayLayer,
    grid_mapping: Mapping[tuple[int, int], tuple[ArrangementType, str]],
    tile_width: int,
    tile_height: int,
    alpha_threshold: int = 128,
) -> dict[tuple[int, int, int], int]:
    """Extract unique colors from the actual sampled overlay regions.

    This extracts colors from exactly what will be applied - the sampled/resampled
    pixels, not the original overlay image. This ensures color mappings match
    the actual applied pixels even when the overlay is scaled.

    Args:
        overlay_layer: The OverlayLayer to sample from
        grid_mapping: Canvas position -> (type, key) mapping
        tile_width: Width of each tile in pixels
        tile_height: Height of each tile in pixels
        alpha_threshold: Alpha value below which pixels are considered transparent

    Returns:
        Dict mapping RGB tuples to pixel counts
    """
    import numpy as np

    # Import here to avoid issues at module load time
    from ui.row_arrangement.grid_arrangement_manager import ArrangementType as ArrType

    all_pixels: list[tuple[int, int, int]] = []

    # Sample each tile region and collect pixels
    for (r, c), (arr_type, _key) in grid_mapping.items():
        if arr_type != ArrType.TILE:
            continue

        # Calculate canvas position
        tile_x = c * tile_width
        tile_y = r * tile_height

        # Sample from overlay (this uses the same method as ApplyOperation)
        region = overlay_layer.sample_region(tile_x, tile_y, tile_width, tile_height)
        if region is None:
            continue

        # Convert to RGBA if needed
        if region.mode != "RGBA":
            region = region.convert("RGBA")

        # Extract opaque pixels
        pixels = np.array(region)
        flat = pixels.reshape(-1, 4)
        opaque_mask = flat[:, 3] >= alpha_threshold
        opaque_pixels = flat[opaque_mask]

        # Collect RGB tuples
        for pixel in opaque_pixels:
            all_pixels.append((int(pixel[0]), int(pixel[1]), int(pixel[2])))

    if not all_pixels:
        return {}

    # Count unique colors
    color_counts: dict[tuple[int, int, int], int] = {}
    for rgb in all_pixels:
        color_counts[rgb] = color_counts.get(rgb, 0) + 1

    return color_counts


def quantize_colors_to_palette(
    color_counts: dict[tuple[int, int, int], int],
    max_colors: int = 16,
    *,
    snap_to_snes: bool = True,
) -> list[tuple[int, int, int]]:
    """Quantize colors to a limited palette.

    Uses PIL's median-cut quantization to reduce colors.
    Index 0 is reserved for transparency (black).

    Args:
        color_counts: Dict mapping RGB tuples to pixel counts
        max_colors: Maximum colors in output palette (default 16 for SNES)
        snap_to_snes: If True, snap colors to SNES-valid values (multiples of 8)

    Returns:
        List of RGB tuples (max_colors entries, index 0 = transparency)
    """
    from PIL import Image

    if not color_counts:
        # Return empty palette with black at index 0
        return [(0, 0, 0)] * max_colors

    # Optionally snap input colors to SNES-valid values first
    # This merges similar colors that would map to the same SNES color
    if snap_to_snes:
        snapped_counts: dict[tuple[int, int, int], int] = {}
        for color, count in color_counts.items():
            snapped = snap_to_snes_color(color)
            snapped_counts[snapped] = snapped_counts.get(snapped, 0) + count
        color_counts = snapped_counts

    # Sort colors by frequency
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)

    # If we have few enough colors, use them directly
    if len(sorted_colors) <= max_colors - 1:  # -1 for transparency
        palette: list[tuple[int, int, int]] = [(0, 0, 0)]  # Index 0 = transparent/black
        for color, _count in sorted_colors:
            palette.append(color)
        # Pad with black if needed
        while len(palette) < max_colors:
            palette.append((0, 0, 0))
        return palette

    # Create a small image with all colors weighted by frequency
    # This gives better quantization results
    total_pixels = sum(color_counts.values())
    img_size = min(256, max(16, int(total_pixels**0.5)))  # Reasonable size

    # Build image data
    pixel_data: list[tuple[int, int, int]] = []
    for color, count in sorted_colors:
        # Add each color proportionally to its frequency
        weight = max(1, int(count * img_size * img_size / total_pixels))
        pixel_data.extend([color] * weight)

    # Ensure we have enough pixels
    while len(pixel_data) < img_size * img_size:
        pixel_data.append(sorted_colors[0][0])  # Pad with most common color

    # Create image and quantize
    img = Image.new("RGB", (img_size, img_size))
    img.putdata(pixel_data[: img_size * img_size])

    # Quantize to max_colors - 1 (reserve index 0 for transparency)
    quantized = img.quantize(colors=max_colors - 1, method=Image.Quantize.MEDIANCUT)
    raw_palette = quantized.getpalette()

    if raw_palette is None:
        # Fallback: use most frequent colors (already snapped if snap_to_snes)
        palette = [(0, 0, 0)]
        for color, _count in sorted_colors[: max_colors - 1]:
            palette.append(color)
        while len(palette) < max_colors:
            palette.append((0, 0, 0))
        return palette

    # Extract palette colors from quantization result
    palette = [(0, 0, 0)]  # Index 0 = transparent
    for i in range(max_colors - 1):
        r = raw_palette[i * 3]
        g = raw_palette[i * 3 + 1]
        b = raw_palette[i * 3 + 2]
        color = (r, g, b)
        # Snap quantized colors to SNES-valid values
        if snap_to_snes:
            color = snap_to_snes_color(color)
        palette.append(color)

    return palette
