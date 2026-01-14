"""
Tests for overlay sampling coordinate system.

Verifies that overlay sampling uses source tile positions, not canvas positions,
to correctly apply overlays that match the source sprite layout.
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


class TestOverlaySourceSampling:
    """Tests for overlay sampling coordinate system."""

    def test_all_tiles_modified_when_using_source_positions(
        self, overlay_layer: OverlayLayer, source_layout_overlay: str
    ):
        """All tiles should be modified when overlay covers source area.

        Bug: When tiles are rearranged on canvas (e.g., 4x2 → 1x8),
        tiles beyond the overlay's canvas coverage are skipped because
        sampling uses canvas positions instead of source positions.

        This test verifies that:
        - With canvas sampling (bug): Only tiles in first 4 canvas columns get modified
        - With source sampling (fix): All 8 tiles get modified
        """
        # 128x64 overlay at 25% scale = 32x16 visual (matches 4x2 source)
        overlay_layer.import_image(source_layout_overlay, 32, 16)
        overlay_layer.set_scale(0.25)
        overlay_layer.set_position(0, 0)

        # Source: 4 columns x 2 rows
        source_tiles: dict[TilePosition, Image.Image] = {}
        for row in range(2):
            for col in range(4):
                source_tiles[TilePosition(row, col)] = Image.new("L", (8, 8), 128)

        # Canvas: tiles rearranged into single row (8 columns x 1 row)
        # This mimics _find_next_empty_slot behavior with wide target_width
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
        assert result.success, f"Apply failed: {result.error_message}"
        assert result.modified_tiles is not None

        # ALL 8 tiles should be modified
        # With the bug (canvas sampling): only tiles 0-3 get modified
        # (canvas positions 0-3 → pixels 0-24 which are within 32px overlay)
        # Tiles 4-7 are at canvas positions 32-56, outside the overlay
        #
        # With the fix (source sampling): all 8 tiles get modified
        # because source positions (row 0: 0-24, row 1: 0-24 in Y) are all within overlay
        expected_tiles = [
            TilePosition(0, 0),
            TilePosition(0, 1),
            TilePosition(0, 2),
            TilePosition(0, 3),
            TilePosition(1, 0),
            TilePosition(1, 1),
            TilePosition(1, 2),
            TilePosition(1, 3),
        ]

        missing_tiles = [t for t in expected_tiles if t not in result.modified_tiles]
        assert not missing_tiles, (
            f"Tiles {missing_tiles} not modified. "
            f"This happens because overlay sampling uses CANVAS positions "
            f"instead of SOURCE positions. "
            f"Modified tiles: {list(result.modified_tiles.keys())}"
        )

    def test_tile_content_matches_source_position_in_overlay(
        self, overlay_layer: OverlayLayer, source_layout_overlay: str
    ):
        """Tile content should come from source position in overlay.

        Tile (1,0) should get DARK content from overlay row 1,
        NOT bright content from where it's placed on canvas.
        """
        overlay_layer.import_image(source_layout_overlay, 32, 16)
        overlay_layer.set_scale(0.25)
        overlay_layer.set_position(0, 0)

        source_tiles: dict[TilePosition, Image.Image] = {}
        for row in range(2):
            for col in range(4):
                source_tiles[TilePosition(row, col)] = Image.new("L", (8, 8), 128)

        # Single row canvas arrangement
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

        # Skip this test if tile not modified (separate test handles that)
        tile_1_0 = result.modified_tiles.get(TilePosition(1, 0))
        if tile_1_0 is None:
            pytest.skip(
                "Tile (1,0) not modified - bug where canvas positions are used. "
                "See test_all_tiles_modified_when_using_source_positions."
            )

        # Get brightness value
        pixels = tile_1_0.load()
        brightness = pixels[4, 4]

        # Tile (1,0) should have DARK content (~40-88 range from row 1)
        # NOT bright content (~200-248 from row 0)
        #
        # With bug: tile (1,0) at canvas (0,4) samples from canvas position
        # which would sample from a completely different area
        #
        # With fix: tile (1,0) samples from source position (row=1, col=0)
        # which is the dark bottom-left area of the overlay
        assert brightness < 100, (
            f"Tile (1,0) has brightness {brightness}, expected < 100 (dark). "
            f"Source position (1,0) should sample from overlay row 1 (dark area), "
            f"but it appears to be sampling from the wrong position."
        )

    def test_row_0_tiles_are_bright_row_1_tiles_are_dark(self, overlay_layer: OverlayLayer, source_layout_overlay: str):
        """Row 0 tiles should be bright, row 1 tiles should be dark.

        This verifies the full structure is preserved when tiles are rearranged.
        """
        overlay_layer.import_image(source_layout_overlay, 32, 16)
        overlay_layer.set_scale(0.25)
        overlay_layer.set_position(0, 0)

        source_tiles: dict[TilePosition, Image.Image] = {}
        for row in range(2):
            for col in range(4):
                source_tiles[TilePosition(row, col)] = Image.new("L", (8, 8), 128)

        # Single row canvas
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
        assert result.modified_tiles is not None

        # Verify row 0 tiles are bright (>150)
        for col in range(4):
            tile = result.modified_tiles.get(TilePosition(0, col))
            if tile is None:
                pytest.skip(f"Tile (0,{col}) not modified")
            brightness = tile.load()[4, 4]
            assert brightness > 150, (
                f"Tile (0,{col}) has brightness {brightness}, expected > 150. "
                f"Row 0 tiles should be bright (from overlay top half)."
            )

        # Verify row 1 tiles are dark (<100)
        for col in range(4):
            tile = result.modified_tiles.get(TilePosition(1, col))
            if tile is None:
                pytest.skip(f"Tile (1,{col}) not modified")
            brightness = tile.load()[4, 4]
            assert brightness < 100, (
                f"Tile (1,{col}) has brightness {brightness}, expected < 100. "
                f"Row 1 tiles should be dark (from overlay bottom half)."
            )
