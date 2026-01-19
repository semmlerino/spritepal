"""
Consolidated Overlay Workflow Tests.

This file consolidates all overlay-related regression tests from:
- test_overlay_apply_bugs.py (4 tests)
- test_overlay_canvas_no_expand.py (8 tests)
- test_overlay_import_autoscale.py (6 tests)
- test_overlay_movement.py (3 tests)
- test_overlay_scaling_editor.py (3 tests)
- test_overlay_source_sampling.py (2 tests)

Total: 26 tests

The tests are organized by functional area rather than by source file.
Each class contains source attribution in its docstring.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGraphicsPixmapItem, QMessageBox

from core.apply_operation import ApplyOperation
from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition
from ui.row_arrangement.overlay_layer import OverlayLayer
from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController

# =============================================================================
# SHARED FIXTURES
# =============================================================================


@pytest.fixture
def simple_sprite(tmp_path):
    """Create a simple 16x16 sprite sheet (4 tiles of 8x8, all black).

    Source: test_overlay_apply_bugs.py::simple_sprite
    """
    img = Image.new("L", (16, 16), 0)
    path = tmp_path / "simple_sprite.png"
    img.save(path)
    return str(path)


@pytest.fixture
def white_overlay(tmp_path):
    """Create a 16x16 white overlay image.

    Source: test_overlay_apply_bugs.py::white_overlay
    """
    img = Image.new("RGBA", (16, 16), (255, 255, 255, 255))
    path = tmp_path / "white_overlay.png"
    img.save(path)
    return str(path)


@pytest.fixture
def sample_palette():
    """Create a simple 16-color palette for testing.

    Source: test_overlay_apply_bugs.py::sample_palette
    """
    return [(i * 16, i * 16, i * 16) for i in range(16)]


@pytest.fixture
def test_sprite_canvas(tmp_path):
    """Create a 16x16 sprite (4 tiles: 0,0; 0,1; 1,0; 1,1).

    Source: test_overlay_canvas_no_expand.py::test_sprite
    """
    img = Image.new("L", (16, 16), 0)
    data = np.array(img)
    data[0:8, 0:8] = 10
    data[0:8, 8:16] = 20
    data[8:16, 0:8] = 30
    data[8:16, 8:16] = 40
    img = Image.fromarray(data, mode="L")
    path = tmp_path / "test_sprite_canvas.png"
    img.save(path)
    return str(path)


@pytest.fixture
def test_overlay_canvas(tmp_path):
    """Create a 16x16 red overlay.

    Source: test_overlay_canvas_no_expand.py::test_overlay
    """
    img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
    path = tmp_path / "test_overlay_canvas.png"
    img.save(path)
    return str(path)


@pytest.fixture
def small_sprite(tmp_path):
    """Create a small 64x64 sprite sheet (8x8 tiles, 8 per row).

    Source: test_overlay_import_autoscale.py::small_sprite
    """
    img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
    path = tmp_path / "small_sprite.png"
    img.save(path)
    return str(path)


@pytest.fixture
def large_overlay(tmp_path):
    """Create a large 1000x1000 overlay image.

    Source: test_overlay_import_autoscale.py::large_overlay
    """
    img = Image.new("RGBA", (1000, 1000), (0, 255, 0, 128))
    path = tmp_path / "large_overlay.png"
    img.save(path)
    return str(path)


@pytest.fixture
def dummy_sprite(tmp_path):
    """Create a dummy sprite sheet for testing.

    Source: test_overlay_movement.py::dummy_sprite
    """
    img = Image.new("RGBA", (128, 128), (255, 0, 0, 255))
    path = tmp_path / "dummy_sprite.png"
    img.save(path)
    return str(path)


@pytest.fixture
def dummy_overlay(tmp_path):
    """Create a dummy overlay image.

    Source: test_overlay_movement.py::dummy_overlay
    """
    img = Image.new("RGBA", (32, 32), (0, 255, 0, 128))
    path = tmp_path / "dummy_overlay.png"
    img.save(path)
    return str(path)


@pytest.fixture
def overlay_layer() -> OverlayLayer:
    """Create an overlay layer for testing.

    Source: test_overlay_source_sampling.py::overlay_layer
    """
    return OverlayLayer()


@pytest.fixture
def source_layout_overlay(tmp_path) -> str:
    """Create a large overlay representing a 4x2 tile layout.

    Source: test_overlay_source_sampling.py::source_layout_overlay

    At 25% scale, 128x64 displays as 32x16 (matching 4x2 tiles at 8x8 each).
    The image has distinct brightness per tile region for grayscale verification.
    """
    overlay_width, overlay_height = 128, 64
    img = Image.new("RGBA", (overlay_width, overlay_height), (0, 0, 0, 255))
    pixels = img.load()

    tile_w_overlay = overlay_width // 4
    tile_h_overlay = overlay_height // 2

    for col in range(4):
        brightness = 200 + col * 16
        for x in range(col * tile_w_overlay, (col + 1) * tile_w_overlay):
            for y in range(tile_h_overlay):
                pixels[x, y] = (brightness, brightness, brightness, 255)

    for col in range(4):
        brightness = 40 + col * 16
        for x in range(col * tile_w_overlay, (col + 1) * tile_w_overlay):
            for y in range(tile_h_overlay, overlay_height):
                pixels[x, y] = (brightness, brightness, brightness, 255)

    path = tmp_path / "source_layout_overlay.png"
    img.save(path)
    return str(path)


# =============================================================================
# ACCEPT PATH BUG TESTS
# Source: test_overlay_apply_bugs.py::TestAcceptPathBug
# =============================================================================


class TestAcceptPathBug:
    """Tests for Bug 1: Dialog accept() not setting _arrangement_result.

    Source: test_overlay_apply_bugs.py::TestAcceptPathBug
    """

    def test_arrangement_result_none_before_accept(self, qtbot, simple_sprite):
        """arrangement_result should be None before accept is called."""
        dialog = GridArrangementDialog(simple_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        assert dialog.arrangement_result is None

        dialog.close()

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_arrangement_result_set_after_direct_accept(
        self, mock_info, mock_warning, qapp, simple_sprite, white_overlay
    ):
        """arrangement_result should be set when accept() is called directly.

        This simulates clicking the OK button (which calls accept() directly).
        """
        dialog = GridArrangementDialog(simple_sprite, tiles_per_row=2)
        dialog.show()

        pos = TilePosition(0, 0)
        dialog.arrangement_manager.add_tile(pos)

        dialog.overlay_layer.import_image(white_overlay, 16, 16)
        dialog._apply_overlay()

        assert dialog.apply_result is not None
        assert dialog.apply_result.success

        dialog.accept()

        assert dialog.arrangement_result is not None, (
            "arrangement_result is None after accept()! "
            "This means changes will be discarded when dialog closes via OK button."
        )
        assert dialog.arrangement_result.modified_tiles is not None

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_modified_tiles_preserved_through_accept(self, mock_info, mock_warning, qapp, simple_sprite, white_overlay):
        """Modified tiles should be accessible after accept()."""
        dialog = GridArrangementDialog(simple_sprite, tiles_per_row=2)
        dialog.show()

        pos = TilePosition(0, 0)
        dialog.arrangement_manager.add_tile(pos)
        dialog.overlay_layer.import_image(white_overlay, 16, 16)
        dialog._apply_overlay()

        pre_accept_tiles = dialog.tiles.copy()
        assert pos in pre_accept_tiles

        dialog.accept()

        result = dialog.arrangement_result
        assert result is not None
        assert result.modified_tiles is not None
        assert pos in result.modified_tiles


# =============================================================================
# PALETTE CACHE BUG TESTS
# Source: test_overlay_apply_bugs.py::TestPaletteCacheBug
# =============================================================================


class TestPaletteCacheBug:
    """Tests for Bug 2: PaletteColorizer cache not invalidated after Apply.

    Source: test_overlay_apply_bugs.py::TestPaletteCacheBug
    """

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_colorizer_cache_cleared_during_apply(
        self, mock_info, mock_warning, qtbot, simple_sprite, white_overlay, sample_palette
    ):
        """Colorizer cache should be cleared when overlay is applied.

        Otherwise the display shows old tile images even after Apply modifies them.
        """
        dialog = GridArrangementDialog(simple_sprite, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.colorizer.set_palettes({8: sample_palette})
        dialog.colorizer.toggle_palette_mode()
        assert dialog.colorizer.is_palette_mode()

        pos = TilePosition(0, 0)
        dialog.arrangement_manager.add_tile(pos)

        original_tile = dialog.tiles.get(pos)
        assert original_tile is not None

        tile_index = pos.row * dialog.processor.grid_cols + pos.col + 1000
        _ = dialog.colorizer.get_display_image(tile_index, original_tile)

        cache_stats_before = dialog.colorizer.get_cache_stats()
        assert cache_stats_before["size"] > 0, "Cache should be populated after get_display_image"

        original_clear_cache = dialog.colorizer.clear_cache
        clear_cache_called = []

        def tracked_clear_cache() -> None:
            clear_cache_called.append(True)
            original_clear_cache()

        dialog.colorizer.clear_cache = tracked_clear_cache  # type: ignore[method-assign]

        dialog.overlay_layer.import_image(white_overlay, 16, 16)
        # Pre-set color mappings to skip the ColorMappingDialog (which would block)
        # White (255,255,255) maps to palette index 15 (brightest in our grayscale palette)
        dialog._saved_color_mappings = {(255, 255, 255): 15}
        dialog._apply_overlay()

        assert len(clear_cache_called) > 0, (
            "clear_cache() was not called during _apply_overlay()! "
            "This causes the display to show old tiles instead of modified ones."
        )


# =============================================================================
# CANVAS EXPANSION TESTS
# Source: test_overlay_canvas_no_expand.py::TestOverlayCanvasFixes
# =============================================================================


class TestOverlayCanvasFixes:
    """Tests for overlay canvas fixes and tile duplication prevention.

    Source: test_overlay_canvas_no_expand.py::TestOverlayCanvasFixes
    """

    def test_no_duplication_when_moving_tiles(self, qtbot, test_sprite_canvas):
        """Verify that physical_to_logical does NOT duplicate tiles.

        If tile (0,0) is moved to (0,2), its original spot (0,0) should be EMPTY (0).
        """
        dialog = GridArrangementDialog(test_sprite_canvas, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.arrangement_manager.set_item_at(0, 2, ArrangementType.TILE, "0,0")

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        w, h = bridge.logical_size
        assert w == 24
        assert h == 16

        input_array = np.zeros((16, 16), dtype=np.uint8)
        input_array[0:8, 0:8] = 10

        output_array = bridge.physical_to_logical(input_array)

        assert np.all(output_array[0:8, 0:8] == 0), "Tile (0,0) was duplicated at its original position!"
        assert np.all(output_array[0:8, 16:24] == 10), "Tile (0,0) was not moved to (0,2)!"

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_keep_layout_false_preserves_physical_canvas(
        self, mock_info, mock_warning, qtbot, test_sprite_canvas, test_overlay_canvas
    ):
        """Test the workflow where keep_arrangement=False means we should revert to physical layout."""
        dialog = GridArrangementDialog(test_sprite_canvas, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.arrangement_manager.set_item_at(5, 5, ArrangementType.TILE, "0,0")

        dialog.keep_layout_check.setChecked(False)

        dialog.overlay_layer.import_image(test_overlay_canvas)
        dialog._apply_overlay()
        qtbot.wait(10)

        result = dialog.get_arrangement_result()
        assert result is not None
        assert result.keep_arrangement is False

        bridge = result.bridge
        input_data = np.zeros((48, 48), dtype=np.uint8)
        input_data[40:48, 40:48] = 255

        phys = bridge.logical_to_physical(input_data)
        assert phys.shape == (16, 16)
        assert np.all(phys[0:8, 0:8] == 255), "Mapping back to physical failed"

    def test_canvas_not_shrinking_if_arrangement_is_small(self, qtbot, test_sprite_canvas):
        """Verify that if we arrange only 1 tile at (0,0), the canvas remains 16x16."""
        dialog = GridArrangementDialog(test_sprite_canvas, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        w, h = bridge.logical_size
        assert w == 16
        assert h == 16

    def test_intentional_expansion_works(self, qtbot, test_sprite_canvas):
        """Verify that we can still expand the canvas if we want to."""
        dialog = GridArrangementDialog(test_sprite_canvas, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.arrangement_manager.set_item_at(10, 10, ArrangementType.TILE, "0,0")

        result = dialog.get_arrangement_result()
        assert result is not None
        bridge = result.bridge

        w, h = bridge.logical_size
        assert w == 88
        assert h == 88


# =============================================================================
# CHECKBOX DEFAULTS TESTS
# Source: test_overlay_canvas_no_expand.py::TestCheckboxDefaults
# =============================================================================


class TestCheckboxDefaults:
    """Tests for Bug 1: Canvas Expansion due to checkbox default.

    Source: test_overlay_canvas_no_expand.py::TestCheckboxDefaults
    """

    def test_keep_layout_checkbox_defaults_to_unchecked(self, qtbot, test_sprite_canvas):
        """Verify keep_layout_check is unchecked by default."""
        dialog = GridArrangementDialog(test_sprite_canvas, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        assert hasattr(dialog, "keep_layout_check"), "Dialog should have keep_layout_check"
        assert dialog.keep_layout_check.isChecked() is False, (
            "keep_layout_check should default to unchecked. "
            "When checked, arrangement grid dimensions leak to sprite editor canvas."
        )

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_overlay_apply_without_keep_layout_returns_false(
        self, mock_info, mock_warning, qtbot, test_sprite_canvas, test_overlay_canvas
    ):
        """Result should have keep_arrangement=False when checkbox is unchecked (default)."""
        dialog = GridArrangementDialog(test_sprite_canvas, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

        dialog.overlay_layer.import_image(test_overlay_canvas)
        dialog._apply_overlay()
        qtbot.wait(10)

        result = dialog.get_arrangement_result()
        assert result is not None

        assert result.keep_arrangement is False, "keep_arrangement should be False when checkbox is unchecked"
        assert result.modified_tiles is not None, "modified_tiles should be present even when keep_arrangement=False"


# =============================================================================
# DELAYED VISUAL FEEDBACK TESTS
# Source: test_overlay_canvas_no_expand.py::TestDelayedVisualFeedback
# =============================================================================


class TestDelayedVisualFeedback:
    """Tests for Bug 2: Overlay not immediately applied.

    Source: test_overlay_canvas_no_expand.py::TestDelayedVisualFeedback
    """

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_apply_overlay_modifies_tiles_immediately(
        self, mock_info, mock_warning, qtbot, test_sprite_canvas, test_overlay_canvas
    ):
        """Tiles should be updated before success message is shown."""
        dialog = GridArrangementDialog(test_sprite_canvas, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
        dialog.overlay_layer.import_image(test_overlay_canvas)
        dialog.overlay_layer.set_position(0, 0)

        original_tile = dialog.tiles[TilePosition(0, 0)]
        original_pixel = original_tile.getpixel((0, 0))

        dialog._apply_overlay()

        modified_tile = dialog.tiles[TilePosition(0, 0)]
        modified_pixel = modified_tile.getpixel((0, 0))

        assert modified_pixel != original_pixel, (
            f"Tile pixel should have changed after apply. Original={original_pixel}, After={modified_pixel}"
        )

        qtbot.wait(10)

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_arrangement_canvas_shows_modified_tiles_after_apply(
        self, mock_info, mock_warning, qtbot, test_sprite_canvas, test_overlay_canvas
    ):
        """Arrangement canvas should display the modified tiles after overlay apply.

        BUG: When applying overlay with palette mode enabled, the colorizer cache
        was cleared AFTER _update_displays() ran, causing stale (cached) tile
        images to be shown.
        """
        dialog = GridArrangementDialog(test_sprite_canvas, tiles_per_row=2)
        qtbot.addWidget(dialog)
        dialog.show()

        palette = [(i, i, i) for i in range(0, 256, 16)]
        dialog.colorizer.set_palettes({0: palette})
        dialog.colorizer.set_selected_palette(0)
        dialog.colorizer.toggle_palette_mode()

        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

        dialog.overlay_layer.import_image(test_overlay_canvas)
        dialog.overlay_layer.set_position(0, 0)
        # Pre-set color mappings to skip ColorMappingDialog (red overlay -> bright palette)
        dialog._saved_color_mappings = {(255, 0, 0): 15}  # Red to brightest
        dialog._apply_overlay()
        qtbot.wait(10)

        scene_items = [item for item in dialog.arrangement_scene.items() if isinstance(item, QGraphicsPixmapItem)]

        assert len(scene_items) >= 1, "Expected at least one pixmap item in scene"

        tile_pixmap = None
        for item in scene_items:
            if item.pos().x() == 0 and item.pos().y() == 0:
                tile_pixmap = item.pixmap()
                break

        assert tile_pixmap is not None, "Could not find tile pixmap at (0,0)"

        qimage = tile_pixmap.toImage()
        pixel_color = qimage.pixelColor(0, 0)

        assert pixel_color.red() > 50, (
            f"Tile in arrangement canvas should show modified pixels. "
            f"Got color ({pixel_color.red()}, {pixel_color.green()}, {pixel_color.blue()}), "
            f"expected brighter value after red overlay was applied."
        )


# =============================================================================
# OVERLAY IMPORT AUTOSCALE TESTS
# Source: test_overlay_import_autoscale.py::TestOverlayImportAutoScale
# =============================================================================


class TestOverlayImportAutoScale:
    """Test overlay auto-scaling on import.

    Source: test_overlay_import_autoscale.py::TestOverlayImportAutoScale
    """

    def test_overlay_layer_autoscales_with_target_dimensions(self, tmp_path):
        """OverlayLayer.import_image should auto-scale when target dimensions provided."""
        img = Image.new("RGBA", (1000, 1000), (0, 255, 0, 128))
        overlay_path = tmp_path / "large_overlay.png"
        img.save(overlay_path)

        layer = OverlayLayer()

        target_w, target_h = 128, 128
        layer.import_image(str(overlay_path), target_w, target_h)

        expected_scale = min(target_w / 1000, target_h / 1000)
        assert layer.scale == pytest.approx(expected_scale, rel=0.01)
        assert layer.scale < 0.2

    def test_overlay_layer_no_autoscale_without_target_dimensions(self, tmp_path):
        """OverlayLayer.import_image should NOT auto-scale when no target dimensions."""
        img = Image.new("RGBA", (1000, 1000), (0, 255, 0, 128))
        overlay_path = tmp_path / "large_overlay.png"
        img.save(overlay_path)

        layer = OverlayLayer()

        layer.import_image(str(overlay_path))

        assert layer.scale == 1.0

    def test_dialog_provides_target_dimensions_for_autoscale(self, qtbot, small_sprite, large_overlay):
        """GridArrangementDialog should provide target dimensions for overlay auto-scaling."""
        dialog = GridArrangementDialog(small_sprite, tiles_per_row=8)
        qtbot.addWidget(dialog)
        dialog.show()

        assert dialog.processor.tile_width == 8
        assert dialog.processor.tile_height == 8
        assert dialog.processor.grid_cols == 8
        assert dialog.processor.grid_rows == 8

        expected_target_w = dialog.arrangement_grid.grid_cols * dialog.processor.tile_width
        expected_target_h = dialog.arrangement_grid.grid_rows * dialog.processor.tile_height
        assert expected_target_w > 0
        assert expected_target_h > 0

        dialog.overlay_layer.import_image(large_overlay, expected_target_w, expected_target_h)

        assert dialog.overlay_layer.scale < 0.3
        assert dialog.overlay_layer.scale > 0.001

        expected_scale = min(expected_target_w / 1000, expected_target_h / 1000)
        assert dialog.overlay_layer.scale == pytest.approx(expected_scale, rel=0.01)

        dialog.close()

    def test_dialog_overlay_controls_autoscale_on_import(self, qtbot, small_sprite, large_overlay, monkeypatch):
        """Test that OverlayControls._on_import_clicked correctly provides target dimensions."""
        dialog = GridArrangementDialog(small_sprite, tiles_per_row=8)
        qtbot.addWidget(dialog)
        dialog.show()

        def mock_getOpenFileName(*args, **kwargs):
            return (large_overlay, "Images (*.png)")

        monkeypatch.setattr(
            "ui.row_arrangement.overlay_controls.QFileDialog.getOpenFileName",
            mock_getOpenFileName,
        )

        dialog.overlay_controls._on_import_clicked()

        assert dialog.overlay_layer.has_image()

        assert dialog.overlay_layer.scale < 0.5, (
            f"Overlay should auto-scale but got scale={dialog.overlay_layer.scale}. "
            "This indicates the parent chain lookup for target dimensions failed."
        )

        dialog.close()

    def test_large_mpng_dimensions(self, qtbot, tmp_path):
        """Test with m.png dimensions (1696x2528) to debug actual user scenario."""
        sprite_img = Image.new("RGBA", (128, 128), (255, 0, 0, 255))
        sprite_path = tmp_path / "sprite.png"
        sprite_img.save(sprite_path)

        overlay_img = Image.new("RGBA", (1696, 2528), (0, 255, 0, 128))
        overlay_path = tmp_path / "mpng_overlay.png"
        overlay_img.save(overlay_path)

        dialog = GridArrangementDialog(str(sprite_path), tiles_per_row=16)
        qtbot.addWidget(dialog)
        dialog.show()

        target_w = dialog.arrangement_grid.grid_cols * dialog.processor.tile_width
        target_h = dialog.arrangement_grid.grid_rows * dialog.processor.tile_height

        dialog.overlay_layer.import_image(str(overlay_path), target_w, target_h)

        expected_scale = min(target_w / 1696, target_h / 2528)
        assert dialog.overlay_layer.scale == pytest.approx(expected_scale, rel=0.01)

        dialog.close()


# =============================================================================
# OVERLAY RENDERING REGRESSION TESTS
# Source: test_overlay_import_autoscale.py::TestOverlayRegression
# =============================================================================


class TestOverlayRegression:
    """Regression tests for overlay rendering and visibility.

    Source: test_overlay_import_autoscale.py::TestOverlayRegression
    """

    @pytest.mark.skipif(os.environ.get("QT_QPA_PLATFORM") == "offscreen", reason="Requires GUI")
    def test_overlay_import_renders_on_scene(self, qtbot, small_sprite, tmp_path, isolated_managers):
        """Verify overlay image is actually rendered as a pixmap item in the scene."""
        overlay_img_path = tmp_path / "repro_overlay.png"
        Image.new("RGBA", (32, 32), color=(255, 0, 0, 128)).save(overlay_img_path)

        dialog = GridArrangementDialog(small_sprite)
        qtbot.addWidget(dialog)
        dialog.show()

        assert not dialog.overlay_layer.has_image()

        success = dialog.overlay_layer.import_image(str(overlay_img_path))
        assert success

        qtbot.wait_until(
            lambda: any(isinstance(item, QGraphicsPixmapItem) for item in dialog.arrangement_scene.items()),
            timeout=1000,
        )

        items = dialog.arrangement_scene.items()
        pixmap_items = [item for item in items if isinstance(item, QGraphicsPixmapItem)]
        assert len(pixmap_items) >= 1

        overlay_items = [item for item in pixmap_items if item.pixmap().width() == 32 and item.pixmap().height() == 32]
        assert len(overlay_items) == 1

        dialog.overlay_layer.set_visible(False)
        qtbot.wait_until(
            lambda: len(
                [
                    item
                    for item in dialog.arrangement_scene.items()
                    if isinstance(item, QGraphicsPixmapItem) and item.pixmap().width() == 32
                ]
            )
            == 0,
            timeout=1000,
        )

        dialog.close()


# =============================================================================
# OVERLAY MOVEMENT TESTS
# Source: test_overlay_movement.py
# =============================================================================


class TestOverlayMovement:
    """Tests for overlay movement in GridArrangementDialog.

    Source: test_overlay_movement.py
    """

    def test_overlay_drag_interaction(self, qtbot, dummy_sprite, dummy_overlay):
        """Test that dragging the overlay item updates the layer position."""
        dialog = GridArrangementDialog(dummy_sprite)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.overlay_layer.import_image(dummy_overlay)
        dialog._update_arrangement_canvas()

        overlay_item = dialog.overlay_item
        assert overlay_item is not None
        assert overlay_item.isVisible()

        initial_pos = dialog.overlay_layer.position
        assert initial_pos == (0, 0)

        viewport = dialog.arrangement_grid.viewport()
        center_scene = QPoint(16, 16)
        center_view = dialog.arrangement_grid.mapFromScene(center_scene)

        qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=center_view)
        assert overlay_item.is_dragging

        target_view = center_view + QPoint(50, 30)
        QTest.mouseMove(viewport, target_view)
        qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=target_view)

        assert not overlay_item.is_dragging

        new_pos = dialog.overlay_layer.position
        assert new_pos[0] > 0
        assert new_pos[1] > 0

    def test_overlay_keyboard_nudge(self, qtbot, dummy_sprite, dummy_overlay):
        """Test that keyboard arrow keys nudge the overlay."""
        dialog = GridArrangementDialog(dummy_sprite)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.overlay_layer.import_image(dummy_overlay)
        dialog._update_arrangement_canvas()

        initial_pos = dialog.overlay_layer.position
        assert initial_pos == (0, 0)

        qtbot.keyClick(dialog, Qt.Key.Key_Right)
        assert dialog.overlay_layer.position == (1, 0)

        qtbot.keyClick(dialog, Qt.Key.Key_Down, modifier=Qt.KeyboardModifier.ShiftModifier)
        assert dialog.overlay_layer.position == (1, 10)

    def test_overlay_scaling(self, qtbot, dummy_sprite, dummy_overlay):
        """Test that changing overlay scale updates the graphics item and keeps center fixed."""
        dialog = GridArrangementDialog(dummy_sprite)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.overlay_layer.import_image(dummy_overlay)
        dialog._update_arrangement_canvas()

        dialog.overlay_layer.set_scale(0.05)
        dialog.overlay_layer.set_position(0.0, 0.0)

        assert dialog.overlay_layer.scale == 0.05
        assert dialog.overlay_layer.position == (0.0, 0.0)
        initial_center = (0.8, 0.8)

        dialog.overlay_controls.scale_spin.setValue(2.0)
        assert dialog.overlay_layer.scale == 0.02
        assert dialog.overlay_layer.x == pytest.approx(0.48)

        new_width = 32 * 0.02
        new_center_x = dialog.overlay_layer.x + new_width / 2
        assert new_center_x == pytest.approx(initial_center[0])

        dialog.overlay_controls.scale_slider.setValue(70)
        assert dialog.overlay_layer.scale == 0.07
        assert dialog.overlay_layer.x == pytest.approx(-0.32)

        dialog.close()


# =============================================================================
# OVERLAY SCALING EDITOR TESTS
# Source: test_overlay_scaling_editor.py::TestOverlayScalingEditor
# =============================================================================


class TestOverlayScalingEditor:
    """Tests for overlay scaling in sprite editor.

    Source: test_overlay_scaling_editor.py::TestOverlayScalingEditor
    """

    @pytest.fixture
    def controller(self):
        """Setup real controllers with mocks for dependencies."""
        edit_ctrl = EditingController()
        edit_ctrl.load_image(np.zeros((32, 32), dtype=np.uint8), [(0, 0, 0)] * 16)

        workflow = ROMWorkflowController(None, edit_ctrl)
        workflow._view = MagicMock()
        workflow._view.workspace = MagicMock()
        workflow.current_width = 32
        workflow.current_height = 32
        return workflow

    def test_merge_overlay_with_scaling(self, controller):
        """Test merging overlay with scaling applied."""
        palette = [(0, 0, 0)] * 16
        palette[1] = (255, 0, 0)
        controller._editing_controller.set_palette(palette)

        overlay = QImage(64, 64, QImage.Format.Format_ARGB32)
        overlay.fill(QColor(255, 0, 0))

        position = QPoint(0, 0)
        scale = 0.5

        sprite_data = controller._editing_controller.get_image_data()
        merged = controller._merge_overlay_to_indexed(sprite_data, palette, overlay, position, scale)

        assert merged.shape == (32, 32)
        assert np.all(merged == 1)

    def test_merge_overlay_with_scaling_and_offset(self, controller):
        """Test merging overlay with scaling and position offset."""
        palette = [(0, 0, 0)] * 16
        palette[1] = (255, 0, 0)

        overlay = QImage(32, 32, QImage.Format.Format_ARGB32)
        overlay.fill(QColor(255, 0, 0))

        sprite_data = np.zeros((32, 32), dtype=np.uint8)
        merged = controller._merge_overlay_to_indexed(sprite_data, palette, overlay, QPoint(8, 8), 0.5)

        assert merged[8, 8] == 1
        assert merged[23, 23] == 1
        assert merged[7, 7] == 0
        assert merged[24, 24] == 0

    def test_auto_scale_on_import(self, controller, tmp_path):
        """Test auto-scaling is applied when importing large overlay."""
        img_path = tmp_path / "large.png"
        QImage(128, 128, QImage.Format.Format_ARGB32).save(str(img_path))

        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(img_path), "Images")):
            canvas = MagicMock()
            controller._view.workspace.get_canvas.return_value = canvas

            controller.state = "edit"
            controller._on_overlay_import_requested()

            canvas.set_overlay_scale.assert_called_with(0.25)
            controller._view.workspace.overlay_panel._scale_slider.setValue.assert_called_with(25)


# =============================================================================
# OVERLAY SOURCE SAMPLING TESTS
# Source: test_overlay_source_sampling.py::TestOverlayCanvasSampling
# =============================================================================


class TestOverlayCanvasSampling:
    """Tests for overlay sampling coordinate system (Canvas-based).

    Source: test_overlay_source_sampling.py::TestOverlayCanvasSampling

    Verifies that overlay sampling uses canvas positions, to correctly
    apply overlays that are positioned on the arrangement canvas.
    """

    def test_only_tiles_covered_on_canvas_are_modified(self, overlay_layer: OverlayLayer, source_layout_overlay: str):
        """Only tiles covered by the overlay on the canvas should be modified.

        If tiles are rearranged into a wide row (8x1), and the overlay only
        covers the first 4 columns (32px), then only tiles in those 4 columns
        should be modified.
        """
        overlay_layer.import_image(source_layout_overlay, 32, 16)
        overlay_layer.set_scale(0.25)
        overlay_layer.set_position(0, 0)

        source_tiles: dict[TilePosition, Image.Image] = {}
        for row in range(2):
            for col in range(4):
                source_tiles[TilePosition(row, col)] = Image.new("L", (8, 8), 128)

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

        modified_keys = set(result.modified_tiles.keys())

        assert TilePosition(0, 0) in modified_keys
        assert TilePosition(1, 0) not in modified_keys

    def test_tile_content_matches_canvas_position_in_overlay(
        self, overlay_layer: OverlayLayer, source_layout_overlay: str
    ):
        """Tile content should come from its canvas position in the overlay."""
        overlay_layer.import_image(source_layout_overlay, 32, 16)

        overlay_layer.set_scale(0.25)
        overlay_layer.set_position(0, 0)

        source_tiles: dict[TilePosition, Image.Image] = {}
        source_tiles[TilePosition(0, 0)] = Image.new("L", (8, 8), 128)

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
        assert brightness == 232


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
