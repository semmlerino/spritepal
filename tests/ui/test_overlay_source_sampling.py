"""
Tests for overlay sampling coordinate system.

Verifies that overlay sampling uses canvas positions, to correctly
apply overlays that are positioned on the arrangement canvas.
"""

import pytest
from PIL import Image

from core.apply_operation import ApplyOperation
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition
from ui.row_arrangement.overlay_layer import OverlayLayer


@pytest.fixture
def overlay_layer() -> OverlayLayer:
    """Create an overlay layer for testing."""
    return OverlayLayer()


@pytest.fixture
def source_layout_overlay(tmp_path) -> str:
    """Create a large overlay representing a 4x2 tile layout.

    At 25% scale, 128x64 displays as 32x16 (matching 4x2 tiles at 8x8 each).

    The image has distinct brightness per tile region for grayscale verification:
    - Row 0 (top half): Bright values (200-248 based on column)
    - Row 1 (bottom half): Dark values (40-88 based on column)
    """
    overlay_width, overlay_height = 128, 64
    img = Image.new("RGBA", (overlay_width, overlay_height), (0, 0, 0, 255))
    pixels = img.load()

    # Each "tile" region in overlay coordinates
    tile_w_overlay = overlay_width // 4  # 32
    tile_h_overlay = overlay_height // 2  # 32

    # Row 0 (top half): BRIGHT gray (high luminance)
    for col in range(4):
        brightness = 200 + col * 16  # 200, 216, 232, 248
        for x in range(col * tile_w_overlay, (col + 1) * tile_w_overlay):
            for y in range(tile_h_overlay):
                pixels[x, y] = (brightness, brightness, brightness, 255)

    # Row 1 (bottom half): DARK gray (low luminance)
    for col in range(4):
        brightness = 40 + col * 16  # 40, 56, 72, 88
        for x in range(col * tile_w_overlay, (col + 1) * tile_w_overlay):
            for y in range(tile_h_overlay, overlay_height):
                pixels[x, y] = (brightness, brightness, brightness, 255)

    path = tmp_path / "source_layout_overlay.png"
    img.save(path)
    return str(path)


class TestOverlayCanvasSampling:
    """Tests for overlay sampling coordinate system (Canvas-based)."""

    def test_only_tiles_covered_on_canvas_are_modified(self, overlay_layer: OverlayLayer, source_layout_overlay: str):
        """Only tiles covered by the overlay on the canvas should be modified.

        If tiles are rearranged into a wide row (8x1), and the overlay only
        covers the first 4 columns (32px), then only tiles in those 4 columns
        should be modified.
        """
        # 128x64 overlay at 25% scale = 32x16 visual (covers 4x2 area)
        overlay_layer.import_image(source_layout_overlay, 32, 16)
        overlay_layer.set_scale(0.25)
        overlay_layer.set_position(0, 0)

        # Source: 4 columns x 2 rows (8 tiles total)
        source_tiles: dict[TilePosition, Image.Image] = {}
        for row in range(2):
            for col in range(4):
                source_tiles[TilePosition(row, col)] = Image.new("L", (8, 8), 128)

        # Canvas: tiles rearranged into single row (8 columns x 1 row)
        grid_mapping: dict[tuple[int, int], tuple[ArrangementType, str]] = {}
        canvas_col = 0
        for src_row in range(2):
            for src_col in range(4):
                grid_mapping[(0, canvas_col)] = (
                    ArrangementType.TILE,
                    f"{src_row},{src_col}",
                )
                canvas_col += 1

        operation = ApplyOperation(
            overlay=overlay_layer,
            grid_mapping=grid_mapping,
            tiles=source_tiles,
            tile_width=8,
            tile_height=8,
        )

        result = operation.execute(force=True)
        assert result.success

        # Tiles at canvas columns 0, 1, 2, 3 should be modified (covered by 32px overlay)
        # Tiles at canvas columns 4, 5, 6, 7 should NOT be modified

        modified_keys = set(result.modified_tiles.keys())

        # (0,0) -> (src 0,0) is at canvas (0,0) -> SHOULD BE MODIFIED
        assert TilePosition(0, 0) in modified_keys
        # (1,0) -> (src 1,0) is at canvas (0,4) -> SHOULD NOT BE MODIFIED
        assert TilePosition(1, 0) not in modified_keys

    def test_tile_content_matches_canvas_position_in_overlay(
        self, overlay_layer: OverlayLayer, source_layout_overlay: str
    ):
        """Tile content should come from its canvas position in the overlay."""
        # 128x64 overlay at 25% scale = 32x16 visual
        overlay_layer.import_image(source_layout_overlay, 32, 16)

        # Set scale FIRST
        overlay_layer.set_scale(0.25)
        # Then set position to ensure it's exactly where we want it
        # Move overlay so it covers canvas columns 2-5 (pixels 16-48)
        # Visual top-left of overlay will be at (-16, 0) on canvas
        overlay_layer.set_position(0, 0)

        source_tiles: dict[TilePosition, Image.Image] = {}
        source_tiles[TilePosition(0, 0)] = Image.new("L", (8, 8), 128)

        # Place Tile (0,0) at canvas (0, 2) -> pixel 16 on canvas.
        # Overlay is at 0, so relative X = 16 - 0 = 16.
        # Original overlay width is 128. Scale is 0.25.
        # Sample X = 16 / 0.25 = 64.
        # Pixel 64 in overlay is the start of Column 2 (if 128px wide / 4 = 32px per col).
        # Column 2 in Row 0 of overlay has brightness 232.
        grid_mapping = {
            (0, 2): (ArrangementType.TILE, "0,0"),
        }

        operation = ApplyOperation(
            overlay=overlay_layer,
            grid_mapping=grid_mapping,
            tiles=source_tiles,
            tile_width=8,
            tile_height=8,
        )

        result = operation.execute(force=True)
        assert result.success
        assert TilePosition(0, 0) in result.modified_tiles

        pixels = result.modified_tiles[TilePosition(0, 0)].load()
        brightness = pixels[0, 0]
        assert brightness == 232  # Column 2 brightness
