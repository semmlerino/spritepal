"""Tests for the Apply operation component."""

from __future__ import annotations

import pytest
from PIL import Image

from core.apply_operation import ApplyOperation, ApplyResult, WarningType
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition
from ui.row_arrangement.overlay_layer import OverlayLayer

pytestmark = [
    pytest.mark.headless,
    pytest.mark.unit,
]


def create_test_overlay(tmp_path, size=(32, 32), color=(255, 0, 0, 255)):
    """Create a test overlay image."""
    img_path = tmp_path / "overlay.png"
    img = Image.new("RGBA", size, color=color)
    img.save(img_path)

    overlay = OverlayLayer()
    overlay.import_image(str(img_path))
    return overlay


def create_test_tiles():
    """Create test tiles dictionary."""
    tiles = {}
    for r in range(2):
        for c in range(2):
            pos = TilePosition(r, c)
            tiles[pos] = Image.new("L", (8, 8))
    return tiles


class TestApplyOperationValidation:
    """Test Apply operation validation."""

    def test_validate_uncovered_tiles(self, tmp_path):
        """Test validation detects uncovered tiles."""
        overlay = create_test_overlay(tmp_path, size=(8, 8))  # Only covers 1 tile
        tiles = create_test_tiles()

        # Place 4 tiles on 2x2 grid
        grid_mapping = {
            (0, 0): (ArrangementType.TILE, "0,0"),
            (0, 1): (ArrangementType.TILE, "0,1"),  # Not covered
            (1, 0): (ArrangementType.TILE, "1,0"),  # Not covered
            (1, 1): (ArrangementType.TILE, "1,1"),  # Not covered
        }

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
        )

        warnings = operation.validate()

        assert len(warnings) == 1
        assert warnings[0].type == WarningType.UNCOVERED
        assert len(warnings[0].tile_ids) == 3  # 3 tiles not covered

    def test_validate_unplaced_tiles(self, tmp_path):
        """Test validation detects unplaced tiles."""
        overlay = create_test_overlay(tmp_path, size=(32, 32))
        tiles = create_test_tiles()  # 4 tiles

        # Only place 2 tiles
        grid_mapping = {
            (0, 0): (ArrangementType.TILE, "0,0"),
            (0, 1): (ArrangementType.TILE, "0,1"),
        }

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
        )

        warnings = operation.validate()

        assert len(warnings) == 1
        assert warnings[0].type == WarningType.UNPLACED
        assert len(warnings[0].tile_ids) == 2  # 2 tiles not placed

    def test_validate_no_warnings(self, tmp_path):
        """Test validation passes when all tiles covered and placed."""
        overlay = create_test_overlay(tmp_path, size=(32, 32))
        tiles = {}
        for r in range(2):
            for c in range(2):
                tiles[TilePosition(r, c)] = Image.new("L", (8, 8))

        # Place all 4 tiles in 2x2 grid
        grid_mapping = {
            (0, 0): (ArrangementType.TILE, "0,0"),
            (0, 1): (ArrangementType.TILE, "0,1"),
            (1, 0): (ArrangementType.TILE, "1,0"),
            (1, 1): (ArrangementType.TILE, "1,1"),
        }

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
        )

        warnings = operation.validate()
        assert len(warnings) == 0


class TestApplyOperationExecution:
    """Test Apply operation execution."""

    def test_execute_no_overlay(self, tmp_path):
        """Test execute fails gracefully when no overlay."""
        overlay = OverlayLayer()  # No image
        tiles = create_test_tiles()
        grid_mapping = {(0, 0): (ArrangementType.TILE, "0,0")}

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
        )

        result = operation.execute()

        assert result.success is False
        assert result.error_message is not None
        assert "No overlay" in result.error_message

    def test_execute_with_warnings_requires_force(self, tmp_path):
        """Test execute requires force=True when warnings exist."""
        overlay = create_test_overlay(tmp_path, size=(8, 8))  # Only covers 1 tile
        tiles = create_test_tiles()

        # Place 2 tiles but overlay only covers 1
        grid_mapping = {
            (0, 0): (ArrangementType.TILE, "0,0"),
            (0, 1): (ArrangementType.TILE, "0,1"),  # Not covered
        }

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
        )

        # Without force
        result = operation.execute(force=False)
        assert result.success is False
        assert len(result.warnings) > 0

        # With force - should succeed for the covered tile
        result = operation.execute(force=True)
        assert result.success is True
        # Only 1 tile should be modified (the covered one)
        assert TilePosition(0, 0) in result.modified_tiles
        assert TilePosition(0, 1) not in result.modified_tiles

    def test_execute_produces_modified_tiles(self, tmp_path):
        """Test execute produces modified tile images."""
        overlay = create_test_overlay(tmp_path, size=(16, 16), color=(255, 128, 64, 255))
        tiles = {}
        for r in range(2):
            for c in range(2):
                tiles[TilePosition(r, c)] = Image.new("L", (8, 8))

        grid_mapping = {
            (0, 0): (ArrangementType.TILE, "0,0"),
            (0, 1): (ArrangementType.TILE, "0,1"),
            (1, 0): (ArrangementType.TILE, "1,0"),
            (1, 1): (ArrangementType.TILE, "1,1"),
        }

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
        )

        result = operation.execute()

        assert result.success is True
        assert len(result.modified_tiles) == 4
        for img in result.modified_tiles.values():
            assert img.size == (8, 8)
            # Should be converted to grayscale
            assert img.mode == "L"


class TestApplyOperationPaletteQuantization:
    """Test Apply operation palette quantization."""

    def test_quantize_to_palette(self, tmp_path):
        """Test that pixels are quantized to nearest palette color."""
        # Create overlay with specific colors
        overlay = create_test_overlay(tmp_path, size=(8, 8), color=(255, 0, 0, 255))
        tiles = {TilePosition(0, 0): Image.new("L", (8, 8))}
        grid_mapping = {(0, 0): (ArrangementType.TILE, "0,0")}

        # Palette with red at index 1
        palette = [
            (0, 0, 0),  # Black
            (255, 0, 0),  # Red
            (0, 255, 0),  # Green
        ] + [(128, 128, 128)] * 13

        operation = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
            palette=palette,
        )

        result = operation.execute()

        assert result.success is True
        assert TilePosition(0, 0) in result.modified_tiles

        # Check that pixels are quantized (index 1 * 16 = 16 for red)
        modified = result.modified_tiles[TilePosition(0, 0)]
        pixels = modified.load()
        if pixels is not None:
            # Should be index 1 (red), which maps to grayscale value 16
            assert pixels[0, 0] == 16
