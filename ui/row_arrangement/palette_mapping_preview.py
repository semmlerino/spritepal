"""Live preview panel for palette color mapping.

Shows side-by-side comparison of original overlay vs quantized preview,
with editable color mappings that update the preview in real-time.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.services.image_utils import pil_to_qpixmap_fast
from ui.dialogs.color_mapping_dialog import (
    ColorMappingRow,
    SimpleColorSwatch,
    _find_nearest_palette_index,
    extract_colors_from_sampled_overlay,
)

if TYPE_CHECKING:
    from ui.row_arrangement.grid_arrangement_manager import ArrangementType
    from ui.row_arrangement.overlay_layer import OverlayLayer


def render_sampled_composite(
    overlay_layer: OverlayLayer,
    grid_mapping: Mapping[tuple[int, int], tuple[ArrangementType, str]],
    tile_width: int,
    tile_height: int,
) -> Image.Image | None:
    """Render all sampled tile regions into a single composite image.

    Args:
        overlay_layer: The overlay to sample from
        grid_mapping: Canvas position -> (type, key) mapping
        tile_width: Width of each tile in pixels
        tile_height: Height of each tile in pixels

    Returns:
        Composite RGBA image of all sampled regions, or None if no tiles
    """
    from ui.row_arrangement.grid_arrangement_manager import ArrangementType as ArrType

    # Find grid bounds
    min_row = min_col = float("inf")
    max_row = max_col = float("-inf")

    tile_positions: list[tuple[int, int]] = []
    for (r, c), (arr_type, _key) in grid_mapping.items():
        if arr_type == ArrType.TILE:
            tile_positions.append((r, c))
            min_row = min(min_row, r)
            min_col = min(min_col, c)
            max_row = max(max_row, r)
            max_col = max(max_col, c)

    if not tile_positions:
        return None

    # Create composite image
    width = (int(max_col) - int(min_col) + 1) * tile_width
    height = (int(max_row) - int(min_row) + 1) * tile_height
    composite = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    # Sample each tile and paste into composite
    for r, c in tile_positions:
        tile_x = c * tile_width
        tile_y = r * tile_height

        region = overlay_layer.sample_region(tile_x, tile_y, tile_width, tile_height)
        if region is not None:
            paste_x = (c - int(min_col)) * tile_width
            paste_y = (r - int(min_row)) * tile_height
            composite.paste(region, (paste_x, paste_y))

    return composite


def render_quantized_preview(
    image: Image.Image,
    palette: list[tuple[int, int, int]],
    color_mappings: dict[tuple[int, int, int], int],
    alpha_threshold: int = 128,
) -> Image.Image:
    """Render a preview of the image with color mappings applied.

    Args:
        image: Source RGBA image
        palette: Target palette (16 RGB colors)
        color_mappings: Overlay RGB -> palette index mappings
        alpha_threshold: Alpha below which pixels are transparent

    Returns:
        RGBA image with colors mapped to palette
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    # Convert to numpy for fast processing
    pixels = np.array(image)

    # Create output array
    output = np.zeros_like(pixels)

    # Process each pixel
    for y in range(pixels.shape[0]):
        for x in range(pixels.shape[1]):
            r, g, b, a = pixels[y, x]

            if a < alpha_threshold:
                # Transparent pixel
                output[y, x] = [0, 0, 0, 0]
            else:
                rgb = (int(r), int(g), int(b))
                # Look up mapping or find nearest
                if rgb in color_mappings:
                    idx = color_mappings[rgb]
                else:
                    idx = _find_nearest_palette_index(rgb, palette, skip_zero=True)

                # Get palette color and set full alpha
                pr, pg, pb = palette[idx]
                output[y, x] = [pr, pg, pb, 255]

    return Image.fromarray(output, "RGBA")


class PreviewImageWidget(QLabel):
    """Widget displaying a preview image with checkerboard background for transparency."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(100, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._scale = 4  # Default display scale

    def set_image(self, image: Image.Image | None) -> None:
        """Set the preview image."""
        if image is None:
            self.clear()
            self.setText("No preview")
            return

        pixmap = pil_to_qpixmap_fast(image, self._scale)
        self.setPixmap(pixmap)

    def set_scale(self, scale: int) -> None:
        """Set the display scale factor."""
        self._scale = max(1, scale)


class PaletteMappingPreviewPanel(QWidget):
    """Live preview panel for palette color mapping.

    Shows side-by-side original vs quantized preview with editable mappings.

    Signals:
        mappings_changed: Emitted when any color mapping changes
        apply_requested: Emitted when user wants to apply with current mappings
    """

    mappings_changed = Signal(dict)  # dict[tuple[int,int,int], int]
    apply_requested = Signal(dict)  # dict[tuple[int,int,int], int]

    def __init__(
        self,
        overlay_layer: OverlayLayer,
        grid_mapping: Mapping[tuple[int, int], tuple[ArrangementType, str]],
        tile_width: int,
        tile_height: int,
        palette: list[tuple[int, int, int]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._overlay_layer = overlay_layer
        self._grid_mapping = grid_mapping
        self._tile_width = tile_width
        self._tile_height = tile_height
        self._palette = palette

        # Extract colors from sampled regions
        self._extract_colors()

        # Compute initial mappings
        self._color_mappings: dict[tuple[int, int, int], int] = {}
        for color in self._overlay_colors:
            self._color_mappings[color] = _find_nearest_palette_index(color, palette)

        # Render initial composite
        self._composite_image = render_sampled_composite(overlay_layer, grid_mapping, tile_width, tile_height)

        self._mapping_rows: list[ColorMappingRow] = []
        self._setup_ui()
        self._update_quantized_preview()

    def _extract_colors(self) -> None:
        """Extract unique colors from sampled overlay regions."""
        self._overlay_colors = extract_colors_from_sampled_overlay(
            self._overlay_layer,
            self._grid_mapping,
            self._tile_width,
            self._tile_height,
        )

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Preview area with splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Original preview
        original_group = QGroupBox("Original (Sampled)")
        original_layout = QVBoxLayout(original_group)
        self._original_preview = PreviewImageWidget()
        if self._composite_image:
            self._original_preview.set_image(self._composite_image)
        original_layout.addWidget(self._original_preview)
        splitter.addWidget(original_group)

        # Quantized preview
        quantized_group = QGroupBox("Quantized (Preview)")
        quantized_layout = QVBoxLayout(quantized_group)
        self._quantized_preview = PreviewImageWidget()
        quantized_layout.addWidget(self._quantized_preview)
        splitter.addWidget(quantized_group)

        layout.addWidget(splitter)

        # Palette display
        palette_row = QHBoxLayout()
        palette_row.addWidget(QLabel("Palette:"))
        for idx, color in enumerate(self._palette):
            swatch = SimpleColorSwatch(color, size=20)
            swatch.setToolTip(f"[{idx}] RGB({color[0]}, {color[1]}, {color[2]})")
            palette_row.addWidget(swatch)
        palette_row.addStretch()
        layout.addLayout(palette_row)

        # Color mappings in scrollable area
        mappings_group = QGroupBox(f"Color Mappings ({len(self._overlay_colors)} colors)")
        mappings_layout = QVBoxLayout(mappings_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(250)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(2)

        # Sort colors by pixel count
        sorted_colors = sorted(
            self._overlay_colors.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        # Show top colors (limit for performance)
        max_displayed = 30
        for color, pixel_count in sorted_colors[:max_displayed]:
            initial_idx = self._color_mappings[color]
            row = ColorMappingRow(color, pixel_count, self._palette, initial_idx)
            row.mapping_changed.connect(self._on_mapping_changed)
            self._mapping_rows.append(row)
            scroll_layout.addWidget(row)

        if len(sorted_colors) > max_displayed:
            hidden_label = QLabel(f"+ {len(sorted_colors) - max_displayed} more colors (using nearest-match)")
            hidden_label.setStyleSheet("color: gray; font-style: italic;")
            scroll_layout.addWidget(hidden_label)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        mappings_layout.addWidget(scroll)
        layout.addWidget(mappings_group)

    def _on_mapping_changed(self, overlay_color: tuple[int, int, int], palette_index: int) -> None:
        """Handle color mapping change."""
        self._color_mappings[overlay_color] = palette_index
        self._update_quantized_preview()
        self.mappings_changed.emit(self._color_mappings.copy())

    def _update_quantized_preview(self) -> None:
        """Update the quantized preview image."""
        if self._composite_image is None:
            return

        quantized = render_quantized_preview(
            self._composite_image,
            self._palette,
            self._color_mappings,
        )
        self._quantized_preview.set_image(quantized)

    def get_color_mappings(self) -> dict[tuple[int, int, int], int]:
        """Get the current color mappings."""
        return self._color_mappings.copy()

    def refresh(self) -> None:
        """Refresh the preview (e.g., after overlay position/scale changes)."""
        # Re-extract colors
        self._extract_colors()

        # Re-render composite
        self._composite_image = render_sampled_composite(
            self._overlay_layer,
            self._grid_mapping,
            self._tile_width,
            self._tile_height,
        )
        if self._composite_image:
            self._original_preview.set_image(self._composite_image)

        # Update quantized preview
        self._update_quantized_preview()
