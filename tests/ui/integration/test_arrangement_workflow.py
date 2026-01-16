"""
Consolidated Arrangement Workflow Tests.

This file consolidates all arrangement-related regression tests from:
- test_arrangement_canvas_preservation.py (4 tests)
- test_arrangement_defaults.py (2 tests)
- test_arrangement_overlay_fixes.py (10 tests)
- test_arrangement_persistence_integration.py (2 tests)
- test_arrangement_workflow_audit.py (3 tests)

Total: 21 tests

The tests are organized by functional area rather than by source file.
Each class contains source attribution in its docstring.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QMessageBox

from core.apply_operation import ApplyOperation
from core.arrangement_persistence import ArrangementConfig
from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition
from ui.row_arrangement.overlay_layer import OverlayLayer
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController
from ui.sprite_editor.services.arrangement_bridge import ArrangementBridge

# =============================================================================
# SHARED FIXTURES
# =============================================================================


@pytest.fixture
def wide_sprite(tmp_path):
    """Create a 24-tile wide sprite (192x8 px).

    Source: test_arrangement_canvas_preservation.py::wide_sprite
    """
    img = Image.new("L", (192, 8), 0)
    for tile_idx in range(24):
        x = tile_idx * 8
        for px in range(8):
            for py in range(8):
                img.putpixel((x + px, py), min(tile_idx * 10, 240))
    path = tmp_path / "wide_sprite.png"
    img.save(path)
    return str(path)


@pytest.fixture
def small_overlay(tmp_path):
    """Create a small overlay covering only 4 tiles (32x8 px).

    Source: test_arrangement_canvas_preservation.py::small_overlay
    """
    img = Image.new("RGBA", (32, 8), (255, 0, 0, 255))
    path = tmp_path / "small_overlay.png"
    img.save(path)
    return str(path)


@pytest.fixture
def test_sprite(tmp_path):
    """Create a 16x8 sprite (2 tiles). Tile 0 is black, Tile 1 is dark gray.

    Source: test_arrangement_workflow_audit.py::test_sprite
    """
    img = Image.new("L", (16, 8), 0)
    img.putpixel((8, 0), 64)
    path = tmp_path / "test_sprite.png"
    img.save(path)
    return str(path)


@pytest.fixture
def gradient_overlay(tmp_path):
    """Create a 16x8 gradient overlay.

    Source: test_arrangement_workflow_audit.py::gradient_overlay
    """
    img = Image.new("RGBA", (16, 8), (0, 0, 0, 255))
    for x in range(16):
        for y in range(8):
            img.putpixel((x, y), (x * 10, y * 10, 0, 255))
    path = tmp_path / "gradient_overlay.png"
    img.save(path)
    return str(path)


@pytest.fixture
def mock_sprite_image(tmp_path):
    """Create a simple test sprite image.

    Source: test_arrangement_persistence_integration.py::mock_sprite_image
    """
    path = tmp_path / "test_sprite.png"
    Image.new("RGBA", (32, 16)).save(path)
    return str(path)


@pytest.fixture
def sample_config():
    """Create a mock ArrangementConfig with some data.

    Source: test_arrangement_persistence_integration.py::sample_config
    """
    config = MagicMock(spec=ArrangementConfig)
    config.arrangement_order = [{"type": "tile", "key": "0,0"}, {"type": "tile", "key": "0,1"}]
    config.groups = []
    config.grid_dimensions = {"rows": 2, "cols": 4}
    config.logical_width = 16
    config.overlay_path = None
    config.overlay_visible = True
    config.overlay_opacity = 0.5
    config.overlay_x = 0
    config.overlay_y = 0
    config.grid_mapping = {"0,0": {"type": "tile", "key": "0,0"}, "0,1": {"type": "tile", "key": "0,1"}}
    return config


# =============================================================================
# CANVAS PRESERVATION TESTS
# Source: test_arrangement_canvas_preservation.py
# =============================================================================


class TestCanvasPreservation:
    """Tests for preserving canvas dimensions after overlay application.

    Source: test_arrangement_canvas_preservation.py::TestCanvasPreservation

    REGRESSION: When overlay is applied to only some tiles, canvas size
    must remain unchanged to prevent non-arranged tiles from becoming invisible.
    """

    def test_canvas_size_preserved_after_overlay_partial_coverage(self, qtbot, wide_sprite, small_overlay):
        """
        REGRESSION TEST: When overlay is applied to only some tiles, canvas size
        must remain unchanged in the sprite editor.

        Bug: Canvas size changes from 192x8 to 32x8 after applying overlay.
        """
        dialog = GridArrangementDialog(wide_sprite, tiles_per_row=24)
        qtbot.addWidget(dialog)
        dialog.show()

        original_width = dialog.processor.grid_cols * 8
        original_height = dialog.processor.grid_rows * 8
        assert original_width == 192
        assert original_height == 8

        for col in range(4):
            dialog.arrangement_manager.set_item_at(0, col, ArrangementType.TILE, f"0,{col}")

        dialog.overlay_layer.import_image(small_overlay)
        dialog.overlay_layer.set_position(0, 0)

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                dialog._apply_overlay()

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        logical_width_px, logical_height_px = bridge.logical_size
        assert logical_width_px == original_width, (
            f"Canvas width changed from {original_width}px to {logical_width_px}px. "
            "Non-arranged tiles would become invisible!"
        )
        assert logical_height_px == original_height, (
            f"Canvas height changed from {original_height}px to {logical_height_px}px."
        )

    def test_physical_to_logical_preserves_all_tiles(self, wide_sprite):
        """
        Verify that physical_to_logical transformation preserves ALL tiles,
        not just the arranged ones.
        """
        dialog = GridArrangementDialog(wide_sprite, tiles_per_row=24)

        for col in range(4):
            dialog.arrangement_manager.set_item_at(0, col, ArrangementType.TILE, f"0,{col}")

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        input_array = np.zeros((8, 192), dtype=np.uint8)
        for tile_idx in range(24):
            x = tile_idx * 8
            input_array[:, x : x + 8] = min(tile_idx * 10, 240)

        output_array = bridge.physical_to_logical(input_array)

        assert output_array.shape == input_array.shape, (
            f"physical_to_logical changed shape from {input_array.shape} to {output_array.shape}. "
            "Non-arranged tiles are lost!"
        )

        for tile_idx in range(4, 24):
            x = tile_idx * 8
            expected_value = min(tile_idx * 10, 240)
            actual_value = output_array[0, x]
            assert actual_value == expected_value, (
                f"Tile {tile_idx} at x={x} was not preserved. Expected {expected_value}, got {actual_value}"
            )

    def test_logical_to_physical_preserves_non_arranged_tiles(self, wide_sprite):
        """
        Verify that logical_to_physical transformation preserves tiles that
        were not explicitly arranged (identity mapping for non-arranged tiles).
        """
        dialog = GridArrangementDialog(wide_sprite, tiles_per_row=24)

        for col in range(4):
            dialog.arrangement_manager.set_item_at(0, col, ArrangementType.TILE, f"0,{col}")

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        logical_w, logical_h = bridge.logical_size
        logical_array = np.zeros((logical_h, logical_w), dtype=np.uint8)

        for tile_idx in range(24):
            x = tile_idx * 8
            if x + 8 <= logical_w:
                logical_array[:, x : x + 8] = min(tile_idx * 10, 240)

        physical_array = bridge.logical_to_physical(logical_array)

        phys_w, phys_h = bridge.physical_size
        assert physical_array.shape == (phys_h, phys_w), (
            f"logical_to_physical output shape {physical_array.shape} doesn't match physical size ({phys_h}, {phys_w})"
        )

        for col in range(4):
            expected_value = min(col * 10, 240)
            actual_value = physical_array[0, col * 8]
            assert actual_value == expected_value, (
                f"Arranged tile {col} was not correctly transformed. Expected {expected_value}, got {actual_value}"
            )


class TestArrangementBridgeDimensions:
    """Unit tests for ArrangementBridge dimension calculations.

    Source: test_arrangement_canvas_preservation.py::TestArrangementBridgeDimensions
    """

    def test_logical_size_minimum_physical(self, wide_sprite):
        """
        Logical size should be at least as large as physical size
        to prevent losing tiles.
        """
        dialog = GridArrangementDialog(wide_sprite, tiles_per_row=24)

        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
        dialog.arrangement_manager.set_item_at(0, 1, ArrangementType.TILE, "0,1")

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        logical_w, logical_h = bridge.logical_size
        physical_w, physical_h = bridge.physical_size

        assert logical_w >= physical_w, f"Logical width {logical_w}px is smaller than physical {physical_w}px"
        assert logical_h >= physical_h, f"Logical height {logical_h}px is smaller than physical {physical_h}px"


# =============================================================================
# ARRANGEMENT DEFAULTS TESTS
# Source: test_arrangement_defaults.py
# =============================================================================


class TestArrangementDefaults:
    """Verify defaults for arrangement dialog preserve layout.

    Source: test_arrangement_defaults.py::TestArrangementDefaults

    Regression check: tiles_per_row should NOT be clamped to 16 for wide sprites.
    """

    @pytest.fixture
    def controller(self):
        """Create a mocked ROMWorkflowController."""
        mock_editing = MagicMock()
        mock_editing.validationChanged.connect = MagicMock()
        mock_editing.paletteSourceSelected.connect = MagicMock()
        mock_editing.paletteChanged.connect = MagicMock()

        ctrl = ROMWorkflowController(None, mock_editing)
        ctrl._view = MagicMock()
        return ctrl

    def test_rom_workflow_tiles_per_row_calculation(self, controller):
        """
        Verify ROMWorkflowController passes correct tiles_per_row for wide sprites.
        Regression check: Should NOT be clamped to 16.
        """
        # Case 1: Standard sprite (128px = 16 tiles)
        controller.current_width = 128

        with patch("ui.grid_arrangement_dialog.GridArrangementDialog") as MockDialog:
            with patch("PIL.Image.Image.save"):
                controller.current_tile_data = b"\x00" * 32
                controller.show_arrangement_dialog()
                args, _ = MockDialog.call_args
                tiles_per_row = args[1]
                assert tiles_per_row == 16, f"Expected 16 tiles_per_row for 128px width, got {tiles_per_row}"

        # Case 2: Wide sprite (256px = 32 tiles)
        controller.current_width = 256
        with patch("ui.grid_arrangement_dialog.GridArrangementDialog") as MockDialog:
            with patch("PIL.Image.Image.save"):
                controller.current_tile_data = b"\x00" * 32
                controller.show_arrangement_dialog()
                args, _ = MockDialog.call_args
                tiles_per_row = args[1]
                assert tiles_per_row == 32, (
                    f"Expected 32 tiles_per_row for 256px width, got {tiles_per_row} (Was it clamped?)"
                )

    def test_dialog_width_spin_default(self, qtbot):
        """
        Verify GridArrangementDialog defaults width_spin to full grid width.
        Regression check: Should NOT be clamped to 16.
        """
        mock_processor = MagicMock()
        mock_processor.grid_cols = 32
        mock_processor.grid_rows = 1
        mock_processor.tile_width = 8
        mock_processor.tile_height = 8

        with patch("ui.grid_arrangement_dialog.GridImageProcessor", return_value=mock_processor):
            real_img = Image.new("L", (256, 8))
            mock_processor.process_sprite_sheet_as_grid.return_value = (real_img, {})

            dialog = GridArrangementDialog("dummy.png", tiles_per_row=32)
            qtbot.addWidget(dialog)

            assert dialog.width_spin.value() == 32, (
                f"Expected width_spin default 32, got {dialog.width_spin.value()} (Was it clamped?)"
            )


# =============================================================================
# OVERLAY APPLICATION TESTS
# Source: test_arrangement_overlay_fixes.py
# =============================================================================


class TestOverlayConfiguration:
    """Tests for overlay configuration persistence.

    Source: test_arrangement_overlay_fixes.py
    """

    def test_arrangement_config_persists_overlay_scale(self, tmp_path):
        """Regression test: ArrangementConfig must persist overlay_scale."""
        config_path = tmp_path / "test.json"

        config = ArrangementConfig(
            rom_hash="hash",
            rom_offset=0,
            sprite_name="test",
            grid_dimensions={},
            arrangement_order=[],
            groups=[],
            total_tiles=0,
            logical_width=16,
            overlay_path="img.png",
            overlay_x=10,
            overlay_y=20,
            overlay_opacity=0.8,
            overlay_visible=True,
            overlay_scale=2.5,
        )

        config.save(config_path)

        loaded = ArrangementConfig.load(config_path)
        assert hasattr(loaded, "overlay_scale"), "Loaded config missing overlay_scale"
        assert loaded.overlay_scale == 2.5, f"Scale not persisted. Got {getattr(loaded, 'overlay_scale', 'MISSING')}"


class TestApplyOperation:
    """Tests for overlay apply operation behavior.

    Source: test_arrangement_overlay_fixes.py
    """

    def test_apply_operation_replaces_partially_covered_tiles(self):
        """Regression test: ApplyOperation must completely REPLACE partially covered tiles (no composition)."""
        overlay = OverlayLayer()
        img = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
        overlay._image = img
        overlay.set_scale(1.0)
        overlay.set_position(4.0, 4.0)

        grid_mapping = {(0, 0): (ArrangementType.TILE, "0,0")}
        tile_pos = TilePosition(0, 0)

        original_tile = Image.new("L", (8, 8), 1)
        tiles = {tile_pos: original_tile}

        op = ApplyOperation(overlay=overlay, grid_mapping=grid_mapping, tiles=tiles, tile_width=8, tile_height=8)

        result = op.execute(force=True)

        assert result.success
        assert tile_pos in result.modified_tiles, "Partially covered tile was skipped"

        modified = result.modified_tiles[tile_pos]

        val_0_0 = modified.getpixel((0, 0))
        assert val_0_0 == 0, f"Untouched pixel was not cleared! Expected 0, got {val_0_0}"

        val_6_6 = modified.getpixel((6, 6))
        assert val_6_6 != 0, f"Covered pixel was not modified! Got {val_6_6}"

    def test_opaque_black_not_quantized_to_transparent_index(self):
        """Regression test: Opaque black pixels should NOT become transparent.

        BUG: When an overlay has opaque black pixels (0,0,0,255), they get quantized
        to palette index 0 (which is typically black in SNES palettes). But index 0
        is reserved for transparency in SNES sprites, so these pixels appear transparent.

        FIX: When quantizing opaque pixels, skip index 0 entirely.
        """
        overlay = OverlayLayer()
        img = Image.new("RGBA", (8, 8), (0, 0, 0, 255))
        overlay._image = img
        overlay.set_scale(1.0)
        overlay.set_position(0.0, 0.0)

        grid_mapping = {(0, 0): (ArrangementType.TILE, "0,0")}
        tile_pos = TilePosition(0, 0)
        original_tile = Image.new("L", (8, 8), 128)
        tiles = {tile_pos: original_tile}

        palette = [
            (0, 0, 0),
            (16, 16, 16),
            (32, 32, 32),
            (48, 48, 48),
        ] + [(i * 16, i * 16, i * 16) for i in range(4, 16)]

        op = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
            palette=palette,
        )

        result = op.execute(force=True)
        assert result.success
        assert tile_pos in result.modified_tiles

        modified = result.modified_tiles[tile_pos]

        pixel_value = modified.getpixel((0, 0))
        index = pixel_value // 16

        assert index != 0, (
            f"Opaque black pixel was quantized to index 0 (transparent)! "
            f"Got pixel value {pixel_value} (index {index}). "
            f"Opaque pixels should never be assigned to index 0."
        )

    def test_transparent_pixels_remain_transparent(self):
        """Regression test: Transparent pixels in overlay should become transparent in output."""
        overlay = OverlayLayer()
        img = Image.new("RGBA", (8, 8), (255, 0, 0, 0))
        overlay._image = img
        overlay.set_scale(1.0)
        overlay.set_position(0.0, 0.0)

        grid_mapping = {(0, 0): (ArrangementType.TILE, "0,0")}
        tile_pos = TilePosition(0, 0)
        original_tile = Image.new("L", (8, 8), 128)
        tiles = {tile_pos: original_tile}

        palette = [(i * 16, i * 16, i * 16) for i in range(16)]

        op = ApplyOperation(
            overlay=overlay,
            grid_mapping=grid_mapping,
            tiles=tiles,
            tile_width=8,
            tile_height=8,
            palette=palette,
        )

        result = op.execute(force=True)
        assert result.success
        assert tile_pos in result.modified_tiles

        modified = result.modified_tiles[tile_pos]

        pixel_value = modified.getpixel((0, 0))
        index = pixel_value // 16

        assert index == 0, (
            f"Transparent pixel was NOT quantized to index 0! "
            f"Got pixel value {pixel_value} (index {index}). "
            f"Transparent pixels (alpha < 128) should always be index 0."
        )


class TestDuplicateTilePrevention:
    """Tests for duplicate tile placement prevention.

    Source: test_arrangement_overlay_fixes.py - Risk 1 tests

    When the same tile key is already placed on the canvas,
    attempting to place it at a different position should fail.
    """

    def test_duplicate_tile_placement_rejected(self):
        """Risk 1: Same physical tile placed at multiple canvas positions should be rejected."""
        from ui.row_arrangement.grid_arrangement_manager import GridArrangementManager

        manager = GridArrangementManager(total_rows=4, total_cols=4)

        result1 = manager.set_item_at(0, 0, ArrangementType.TILE, "1,2")
        assert result1 is True, "First placement should succeed"

        mapping = manager.get_grid_mapping()
        assert (0, 0) in mapping
        assert mapping[(0, 0)] == (ArrangementType.TILE, "1,2")

        result2 = manager.set_item_at(1, 1, ArrangementType.TILE, "1,2")

        assert result2 is False, (
            "Duplicate tile placement should be rejected! "
            "Tile '1,2' already placed at (0,0), cannot place at (1,1). "
            "This would cause ambiguous 'last write wins' during overlay apply."
        )

        mapping_after = manager.get_grid_mapping()
        tile_count = sum(1 for v in mapping_after.values() if v == (ArrangementType.TILE, "1,2"))
        assert tile_count == 1, f"Expected exactly 1 instance of tile '1,2', found {tile_count}"

    def test_move_tile_allows_same_key(self):
        """Moving a tile (remove + place) should work even though key is 'duplicate'."""
        from ui.row_arrangement.grid_arrangement_manager import GridArrangementManager

        manager = GridArrangementManager(total_rows=4, total_cols=4)

        manager.set_item_at(0, 0, ArrangementType.TILE, "1,2")

        manager.move_grid_item((0, 0), (1, 1))

        mapping = manager.get_grid_mapping()
        assert (0, 0) not in mapping, "Tile should no longer be at old position"
        assert (1, 1) in mapping, "Tile should be at new position"
        assert mapping[(1, 1)] == (ArrangementType.TILE, "1,2")

    def test_replace_tile_at_same_position_allowed(self):
        """Placing a different tile at an occupied position should replace the existing one."""
        from ui.row_arrangement.grid_arrangement_manager import GridArrangementManager

        manager = GridArrangementManager(total_rows=4, total_cols=4)

        manager.set_item_at(0, 0, ArrangementType.TILE, "1,2")

        result = manager.set_item_at(0, 0, ArrangementType.TILE, "2,3")
        assert result is True, "Replacing tile at same position should succeed"

        mapping = manager.get_grid_mapping()
        assert mapping[(0, 0)] == (ArrangementType.TILE, "2,3")


class TestApplyButtonState:
    """Tests for Apply button enable/disable state.

    Source: test_arrangement_overlay_fixes.py - Risk 3 tests
    """

    def test_apply_disabled_when_no_tiles_placed(self, qapp, tmp_path):
        """Risk 3: Apply button should be disabled when no tiles are placed on canvas."""
        sprite_img = Image.new("L", (16, 16), 128)
        sprite_path = tmp_path / "sprite.png"
        sprite_img.save(sprite_path)

        overlay_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        overlay_path = tmp_path / "overlay.png"
        overlay_img.save(overlay_path)

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                dialog = GridArrangementDialog(str(sprite_path), tiles_per_row=2)
                dialog.show()

                dialog.arrangement_manager.clear()

                dialog.overlay_layer.import_image(str(overlay_path))
                dialog.overlay_layer.set_visible(True)

                dialog._on_overlay_changed()

                assert hasattr(dialog, "apply_overlay_btn"), "Dialog should have apply button"
                is_enabled = dialog.apply_overlay_btn.isEnabled()

                assert is_enabled is False, (
                    "Apply button should be disabled when no tiles are placed on canvas! "
                    "Currently enabled, which would result in 'Applied overlay to 0 tile(s)' no-op."
                )

    def test_apply_enabled_when_tiles_placed(self, qapp, tmp_path):
        """Apply button should be enabled when tiles ARE placed and overlay is valid."""
        sprite_img = Image.new("L", (16, 16), 128)
        sprite_path = tmp_path / "sprite.png"
        sprite_img.save(sprite_path)

        overlay_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        overlay_path = tmp_path / "overlay.png"
        overlay_img.save(overlay_path)

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                dialog = GridArrangementDialog(str(sprite_path), tiles_per_row=2)
                dialog.show()

                dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

                dialog.overlay_layer.import_image(str(overlay_path))
                dialog.overlay_layer.set_visible(True)

                dialog._on_overlay_changed()

                assert dialog.apply_overlay_btn.isEnabled() is True, (
                    "Apply button should be enabled when tiles are placed and overlay is valid"
                )

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_tiles_per_row_preserved_in_result(self, mock_info, mock_warning, qapp, tmp_path, qtbot):
        """Risk 2: tiles_per_row must be preserved in ArrangementResult for correct byte offset calculation."""
        sprite_img = Image.new("L", (32, 16), 128)
        sprite_path = tmp_path / "sprite.png"
        sprite_img.save(sprite_path)

        overlay_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        overlay_path = tmp_path / "overlay.png"
        overlay_img.save(overlay_path)

        dialog = GridArrangementDialog(str(sprite_path), tiles_per_row=4)
        dialog.show()

        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
        dialog.overlay_layer.import_image(str(overlay_path))
        dialog.overlay_layer.set_position(0, 0)
        dialog._apply_overlay()
        qtbot.wait(10)

        dialog.accept()

        result = dialog.arrangement_result
        assert result is not None, "Result should exist after accept"

        assert hasattr(result, "tiles_per_row"), (
            "ArrangementResult must have tiles_per_row field! "
            "Without it, byte offset calculation may use wrong value if current_width changes."
        )
        assert result.tiles_per_row == 4, f"tiles_per_row should be 4 (from dialog init), got {result.tiles_per_row}"


# =============================================================================
# ARRANGEMENT PERSISTENCE TESTS
# Source: test_arrangement_persistence_integration.py
# =============================================================================


class TestArrangementPersistence:
    """Tests for arrangement config persistence and restoration.

    Source: test_arrangement_persistence_integration.py
    """

    def test_dialog_accepts_config(self, qtbot, mock_sprite_image, sample_config):
        """Test that GridArrangementDialog accepts an arrangement_config parameter."""
        try:
            dialog = GridArrangementDialog(mock_sprite_image, arrangement_config=sample_config)
        except TypeError:
            pytest.fail("GridArrangementDialog does not accept arrangement_config")

        qtbot.addWidget(dialog)

        assert hasattr(dialog, "arrangement_config")
        assert dialog.arrangement_config == sample_config

    def test_dialog_restores_state(self, qtbot, mock_sprite_image, sample_config):
        """Test that dialog restores manager state from config."""
        dialog = GridArrangementDialog(mock_sprite_image, arrangement_config=sample_config)
        qtbot.addWidget(dialog)

        assert dialog.arrangement_manager.is_tile_arranged(TilePosition(0, 0))
        assert dialog.arrangement_manager.is_tile_arranged(TilePosition(0, 1))
        assert dialog.arrangement_manager.get_arranged_count() == 2


# =============================================================================
# WORKFLOW AUDIT TESTS
# Source: test_arrangement_workflow_audit.py
# =============================================================================


class TestArrangementWorkflowAudit:
    """Audit tests for Sprite Editor -> Arrangement -> Apply Overlay workflow.

    Source: test_arrangement_workflow_audit.py

    Reproduces:
    1. Overlay position truncation (float vs int)
    2. ArrangementBridge compaction (ignoring gaps)
    """

    def test_overlay_position_precision_loss(self, qtbot, test_sprite, gradient_overlay):
        """
        Reproduce Bug 1: OverlayGraphicsItem truncates position to int,
        causing misalignment between what the user sees and what is sampled.
        """
        dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.arrangement_manager.add_tile(TilePosition(0, 0))

        dialog.overlay_layer.import_image(gradient_overlay)

        dialog._update_arrangement_canvas()
        assert dialog.overlay_item is not None

        float_pos = QPointF(5.7, 3.2)
        dialog.overlay_item.setPos(float_pos)

        dialog.overlay_item.itemChange(dialog.overlay_item.GraphicsItemChange.ItemPositionChange, float_pos)

        assert dialog.overlay_layer.x == 5.7, f"Layer X should be 5.7, but got {dialog.overlay_layer.x}"
        assert dialog.overlay_layer.y == 3.2, f"Layer Y should be 3.2, but got {dialog.overlay_layer.y}"

    def test_arrangement_bridge_compaction_with_gaps(self, test_sprite):
        """
        Reproduce Bug 2: ArrangementBridge compacts tiles, ignoring gaps
        placed by the user on the arrangement canvas.
        """
        dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)

        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
        dialog.arrangement_manager.set_item_at(0, 2, ArrangementType.TILE, "0,1")

        mapping = dialog.arrangement_manager.get_grid_mapping()
        assert (0, 0) in mapping
        assert (0, 2) in mapping
        assert (0, 1) not in mapping

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        width_px, height_px = bridge.logical_size

        assert width_px >= 24, f"Bridge logical width should be at least 24px to accommodate gap, but got {width_px}px"

    def test_apply_overlay_samples_canvas_pos(self, qtbot, test_sprite, gradient_overlay):
        """
        Verify that ApplyOverlay correctly samples based on CANVAS positions,
        not original source positions.
        """
        dialog = GridArrangementDialog(test_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.arrangement_manager.set_item_at(0, 2, ArrangementType.TILE, "0,0")

        dialog.overlay_layer.import_image(gradient_overlay)
        dialog.overlay_layer.set_position(0, 0)

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                dialog._apply_overlay()

        assert TilePosition(0, 0) not in dialog.apply_result.modified_tiles

        dialog.arrangement_manager.clear()
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                dialog._apply_overlay()

        assert TilePosition(0, 0) in dialog.apply_result.modified_tiles

        dialog.arrangement_manager.clear()
        dialog.arrangement_manager.set_item_at(0, 2, ArrangementType.TILE, "0,0")
        dialog.overlay_layer.set_position(16, 0)

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
                dialog._apply_overlay()

        assert TilePosition(0, 0) in dialog.apply_result.modified_tiles
        modified_img = dialog.apply_result.modified_tiles[TilePosition(0, 0)]
        assert modified_img.getpixel((0, 0)) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
