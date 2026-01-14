"""
Tests for overlay import auto-scaling in GridArrangementDialog.
"""

import pytest
from PIL import Image

from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.overlay_layer import OverlayLayer


@pytest.fixture
def small_sprite(tmp_path):
    """Create a small 64x64 sprite sheet (8x8 tiles, 8 per row)."""
    img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
    path = tmp_path / "small_sprite.png"
    img.save(path)
    return str(path)


@pytest.fixture
def large_overlay(tmp_path):
    """Create a large 1000x1000 overlay image."""
    img = Image.new("RGBA", (1000, 1000), (0, 255, 0, 128))
    path = tmp_path / "large_overlay.png"
    img.save(path)
    return str(path)


class TestOverlayImportAutoScale:
    """Test overlay auto-scaling on import."""

    def test_overlay_layer_autoscales_with_target_dimensions(self, tmp_path):
        """OverlayLayer.import_image should auto-scale when target dimensions provided."""
        # Create a large image
        img = Image.new("RGBA", (1000, 1000), (0, 255, 0, 128))
        overlay_path = tmp_path / "large_overlay.png"
        img.save(overlay_path)

        layer = OverlayLayer()

        # Import with target dimensions (e.g., 128x128 grid)
        target_w, target_h = 128, 128
        layer.import_image(str(overlay_path), target_w, target_h)

        # Scale should be calculated as min(128/1000, 128/1000) = 0.128
        # Clamped to [0.001, 0.3] = 0.128
        expected_scale = min(target_w / 1000, target_h / 1000)
        assert layer.scale == pytest.approx(expected_scale, rel=0.01)
        assert layer.scale < 0.2  # Should be significantly scaled down

    def test_overlay_layer_no_autoscale_without_target_dimensions(self, tmp_path):
        """OverlayLayer.import_image should NOT auto-scale when no target dimensions."""
        img = Image.new("RGBA", (1000, 1000), (0, 255, 0, 128))
        overlay_path = tmp_path / "large_overlay.png"
        img.save(overlay_path)

        layer = OverlayLayer()

        # Import WITHOUT target dimensions
        layer.import_image(str(overlay_path))

        # Scale should stay at default 1.0
        assert layer.scale == 1.0

    def test_dialog_provides_target_dimensions_for_autoscale(
        self, qtbot, small_sprite, large_overlay
    ):
        """GridArrangementDialog should provide target dimensions for overlay auto-scaling.

        This is the key integration test - when importing via the dialog,
        the overlay should auto-scale to fit the grid dimensions.
        """
        # Create dialog with small sprite (64x64, tiles_per_row=8 -> 8x8 tiles)
        dialog = GridArrangementDialog(small_sprite, tiles_per_row=8)
        qtbot.addWidget(dialog)
        dialog.show()

        # Verify grid dimensions (64/8 = 8 tiles wide, 8 tiles tall, each 8x8)
        assert dialog.processor.tile_width == 8
        assert dialog.processor.tile_height == 8
        assert dialog.processor.grid_cols == 8
        assert dialog.processor.grid_rows == 8

        # Target dimensions for overlay should be based on arrangement grid
        # arrangement_grid uses width_spin (default 16) and fixed height 32
        # So target_w = 16 * 8 = 128, target_h = 32 * 8 = 256
        expected_target_w = dialog.arrangement_grid.grid_cols * dialog.processor.tile_width
        expected_target_h = dialog.arrangement_grid.grid_rows * dialog.processor.tile_height
        assert expected_target_w > 0
        assert expected_target_h > 0

        # Now import a large overlay - it SHOULD auto-scale
        # We'll call import_image directly with the dimensions the dialog SHOULD provide
        dialog.overlay_layer.import_image(
            large_overlay, expected_target_w, expected_target_h
        )

        # The overlay scale should be much less than 1.0
        # For 1000x1000 image -> target ~128x256, scale = min(128/1000, 256/1000) = 0.128
        assert dialog.overlay_layer.scale < 0.3
        assert dialog.overlay_layer.scale > 0.001

        # The scale should roughly equal the expected ratio
        expected_scale = min(
            expected_target_w / 1000, expected_target_h / 1000
        )
        assert dialog.overlay_layer.scale == pytest.approx(expected_scale, rel=0.01)

        dialog.close()

    def test_dialog_overlay_controls_autoscale_on_import(
        self, qtbot, small_sprite, large_overlay, monkeypatch
    ):
        """Test that OverlayControls._on_import_clicked correctly provides target dimensions.

        This test verifies the parent chain lookup works correctly.
        """
        dialog = GridArrangementDialog(small_sprite, tiles_per_row=8)
        qtbot.addWidget(dialog)
        dialog.show()

        # Mock the file dialog to return our large overlay
        def mock_getOpenFileName(*args, **kwargs):
            return (large_overlay, "Images (*.png)")

        monkeypatch.setattr(
            "ui.row_arrangement.overlay_controls.QFileDialog.getOpenFileName",
            mock_getOpenFileName,
        )

        # Trigger the import via the controls (this should use the parent chain lookup)
        dialog.overlay_controls._on_import_clicked()

        # The overlay should be auto-scaled
        # If the parent chain lookup FAILS, scale would be 1.0 (this is the bug)
        # If it WORKS, scale should be << 1.0
        assert dialog.overlay_layer.has_image()

        # Print debug info
        print(f"\n[DEBUG] Overlay scale after import: {dialog.overlay_layer.scale}")
        print(f"[DEBUG] Grid cols: {dialog.arrangement_grid.grid_cols}")
        print(f"[DEBUG] Grid rows: {dialog.arrangement_grid.grid_rows}")
        print(f"[DEBUG] Tile width: {dialog.processor.tile_width}")
        print(f"[DEBUG] Tile height: {dialog.processor.tile_height}")
        target_w = dialog.arrangement_grid.grid_cols * dialog.processor.tile_width
        target_h = dialog.arrangement_grid.grid_rows * dialog.processor.tile_height
        print(f"[DEBUG] Expected target: {target_w}x{target_h}")
        expected_scale = min(target_w / 1000, target_h / 1000)
        print(f"[DEBUG] Expected scale: {expected_scale}")

        # THIS ASSERTION SHOULD FAIL before the fix (scale = 1.0 due to failed lookup)
        # After the fix, scale should be properly calculated
        assert dialog.overlay_layer.scale < 0.5, (
            f"Overlay should auto-scale but got scale={dialog.overlay_layer.scale}. "
            "This indicates the parent chain lookup for target dimensions failed."
        )

        dialog.close()

    def test_large_mpng_dimensions(self, qtbot, tmp_path):
        """Test with m.png dimensions (1696x2528) to debug actual user scenario."""
        # Create sprite sheet matching typical SNES sprite (e.g., 128x128)
        sprite_img = Image.new("RGBA", (128, 128), (255, 0, 0, 255))
        sprite_path = tmp_path / "sprite.png"
        sprite_img.save(sprite_path)

        # Create overlay with m.png dimensions
        overlay_img = Image.new("RGBA", (1696, 2528), (0, 255, 0, 128))
        overlay_path = tmp_path / "mpng_overlay.png"
        overlay_img.save(overlay_path)

        # Create dialog with typical settings (16 tiles wide, 8x8 tiles)
        dialog = GridArrangementDialog(str(sprite_path), tiles_per_row=16)
        qtbot.addWidget(dialog)
        dialog.show()

        print("\n[M.PNG TEST]")
        print("Sprite: 128x128, tiles_per_row=16")
        print(f"processor.tile_width={dialog.processor.tile_width}")
        print(f"processor.tile_height={dialog.processor.tile_height}")
        print(f"processor.grid_cols={dialog.processor.grid_cols}")
        print(f"processor.grid_rows={dialog.processor.grid_rows}")
        print(f"arrangement_grid.grid_cols={dialog.arrangement_grid.grid_cols}")
        print(f"arrangement_grid.grid_rows={dialog.arrangement_grid.grid_rows}")

        # Calculate what the target dimensions SHOULD be
        target_w = dialog.arrangement_grid.grid_cols * dialog.processor.tile_width
        target_h = dialog.arrangement_grid.grid_rows * dialog.processor.tile_height
        print(f"Target dimensions: {target_w}x{target_h}")

        # Import overlay
        dialog.overlay_layer.import_image(str(overlay_path), target_w, target_h)

        expected_scale = min(target_w / 1696, target_h / 2528)
        print(f"Expected scale: {expected_scale}")
        print(f"Actual scale: {dialog.overlay_layer.scale}")

        # With scale, overlay visual size would be:
        visual_w = 1696 * dialog.overlay_layer.scale
        visual_h = 2528 * dialog.overlay_layer.scale
        print(f"Visual overlay size: {visual_w}x{visual_h}")

        assert dialog.overlay_layer.scale == pytest.approx(expected_scale, rel=0.01)

        dialog.close()
