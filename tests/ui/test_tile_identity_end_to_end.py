"""
End-to-end tests for tile identity preservation through the overlay workflow.

These tests trace a single tile's identity from ROM offset through:
1. Temp PNG creation
2. Grid slicing (TilePosition established)
3. Canvas placement
4. Overlay sampling
5. Byte offset patching
6. Verification that ROM offset matches original

Also includes regression test for the "Apply + Rearrange = Silent Data Loss" bug.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from core.tile_utils import decode_4bpp_tile, encode_4bpp_tile
from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition

# --- Fixtures ---


@pytest.fixture
def sprite_4x2_tiles(tmp_path):
    """Create a 32x16 sprite (4x2 = 8 tiles).

    Each tile has a unique pixel pattern based on its linear index:
    - Tile at (row=0, col=0): all pixels = 0
    - Tile at (row=0, col=1): all pixels = 16
    - Tile at (row=0, col=2): all pixels = 32
    - Tile at (row=0, col=3): all pixels = 48
    - Tile at (row=1, col=0): all pixels = 64
    - Tile at (row=1, col=1): all pixels = 80
    - Tile at (row=1, col=2): all pixels = 96  <-- Our traced tile
    - Tile at (row=1, col=3): all pixels = 112

    This allows us to verify which tile was modified by checking pixel values.
    """
    img = Image.new("L", (32, 16), 0)
    tiles_per_row = 4

    for row in range(2):
        for col in range(4):
            tile_idx = row * tiles_per_row + col
            pixel_value = tile_idx * 16  # 0, 16, 32, 48, 64, 80, 96, 112
            # Fill the 8x8 tile region
            for y in range(8):
                for x in range(8):
                    img.putpixel((col * 8 + x, row * 8 + y), pixel_value)

    path = tmp_path / "sprite_4x2.png"
    img.save(path)
    return str(path)


@pytest.fixture
def distinctive_overlay(tmp_path):
    """Create a 32x32 overlay with distinctive per-pixel values.

    Pixel at (x, y) has value (x + y * 32) % 256.
    This lets us verify exactly which overlay region was sampled.
    """
    img = Image.new("RGBA", (32, 32))
    for y in range(32):
        for x in range(32):
            val = (x + y * 32) % 256
            img.putpixel((x, y), (val, val, val, 255))

    path = tmp_path / "distinctive_overlay.png"
    img.save(path)
    return str(path)


@pytest.fixture
def mock_4bpp_tile_data():
    """Create mock 4bpp tile data for 8 tiles (256 bytes total).

    Each tile is 32 bytes. Tile content mirrors the PNG fixture:
    - Tile 0: all indices = 0
    - Tile 1: all indices = 1
    - ...
    - Tile 6 (row=1, col=2): all indices = 6  <-- Our traced tile
    - Tile 7: all indices = 7
    """
    data = bytearray(8 * 32)  # 8 tiles, 32 bytes each

    for tile_idx in range(8):
        # Create 64 pixels all with the same index
        indices = np.full(64, tile_idx, dtype=np.uint8)
        tile_bytes = encode_4bpp_tile(indices)
        offset = tile_idx * 32
        data[offset : offset + 32] = tile_bytes

    return bytes(data)


# --- Happy Path Test ---


class TestTileIdentityEndToEnd:
    """Verify tile identity is preserved through the complete workflow."""

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_tile_identity_preserved_through_overlay_workflow(
        self, mock_info, mock_warning, qapp, qtbot, sprite_4x2_tiles, distinctive_overlay
    ):
        """
        Trace TilePosition(1, 2) through the entire workflow:

        1. Grid slicing creates TilePosition(1, 2) with original pixel value 96
        2. User places tile at canvas position (0, 0) - different from source
        3. Overlay is applied, sampling at canvas position (0, 0)
        4. Modified tile is stored with key TilePosition(1, 2)
        5. get_arrangement_result returns modified_tiles[TilePosition(1, 2)]
        6. Verify the tile at physical position (1, 2) was modified, not (0, 0)
        """
        tiles_per_row = 4
        traced_tile = TilePosition(1, 2)  # Linear index = 1*4 + 2 = 6

        # Create dialog
        dialog = GridArrangementDialog(sprite_4x2_tiles, tiles_per_row=tiles_per_row)
        dialog.show()

        # STAGE 3: Verify TilePosition established correctly from grid slicing
        assert traced_tile in dialog.tiles, "TilePosition(1, 2) should exist after grid slicing"
        original_tile = dialog.tiles[traced_tile]
        # Original pixel value should be 96 (tile_idx=6, pixel_value=6*16=96)
        assert original_tile.getpixel((0, 0)) == 96, (
            f"Original tile pixel should be 96, got {original_tile.getpixel((0, 0))}"
        )

        # STAGE 4: Place tile at canvas position (0, 0) - away from its source position
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "1,2")

        # Verify grid_mapping stores the physical identity correctly
        mapping = dialog.arrangement_manager.get_grid_mapping()
        assert (0, 0) in mapping, "Canvas position (0, 0) should be in mapping"
        arr_type, key = mapping[(0, 0)]
        assert arr_type == ArrangementType.TILE
        assert key == "1,2", f"Key should be '1,2' (physical identity), got '{key}'"

        # Import overlay at position (0, 0)
        dialog.overlay_layer.import_image(distinctive_overlay)
        dialog.overlay_layer.set_position(0, 0)

        # STAGE 5: Apply overlay - should sample at canvas (0, 0), store at TilePosition(1, 2)
        dialog._apply_overlay()
        # Process events to handle the deferred QMessageBox
        qtbot.wait(10)

        # Verify apply succeeded
        assert dialog._apply_result is not None, "Apply should have succeeded"
        assert dialog._apply_result.success, f"Apply failed: {dialog._apply_result.error_message}"

        # STAGE 6: Verify the correct tile was modified
        # The overlay samples at canvas pixel (0, 0), which is (0, 0) to (7, 7)
        # Pixel (0, 0) of overlay = (0 + 0*32) % 256 = 0 -> grayscale 0 -> index 0
        modified_tile = dialog.tiles[traced_tile]
        new_pixel_value = modified_tile.getpixel((0, 0))

        # ApplyOperation converts RGBA to L mode with quantization
        # The overlay pixel (0,0,0,255) should become index 0 -> value 0
        assert new_pixel_value != 96, (
            f"Tile should have been modified from original value 96, but still has {new_pixel_value}"
        )

        # STAGE 7: Call accept and verify result
        dialog.accept()

        result = dialog.arrangement_result
        assert result is not None, "arrangement_result should be set after accept()"
        assert result.modified_tiles is not None, "modified_tiles should not be None"

        # The critical check: TilePosition(1, 2) should be in modified_tiles
        # NOTE: modified_tiles is a copy of ALL tiles (by design), not just the ones
        # that were explicitly modified. This ensures complete state transfer.
        assert traced_tile in result.modified_tiles, (
            f"TilePosition(1, 2) should be in modified_tiles, but keys are: {list(result.modified_tiles.keys())}"
        )

        # Verify the traced tile has been modified (different from original)
        result_tile = result.modified_tiles[traced_tile]
        result_pixel = result_tile.getpixel((0, 0))
        assert result_pixel != 96, f"Traced tile should have modified pixels (not 96), but got {result_pixel}"

        # Verify that tiles NOT placed on canvas still have their original values
        # TilePosition(0, 1) was never placed, so it should have original value 16
        unplaced_tile = TilePosition(0, 1)
        if unplaced_tile in result.modified_tiles:
            unplaced_pixel = result.modified_tiles[unplaced_tile].getpixel((0, 0))
            assert unplaced_pixel == 16, (
                f"Unplaced tile (0,1) should have original value 16, but got {unplaced_pixel}. "
                "This would indicate the canvas position leaked into tile identity."
            )

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_byte_offset_calculation_matches_rom_layout(
        self, mock_info, mock_warning, qapp, qtbot, sprite_4x2_tiles, distinctive_overlay, mock_4bpp_tile_data
    ):
        """
        Verify that _update_tile_data_from_modified_tiles patches the correct byte offset.

        TilePosition(1, 2) with tiles_per_row=4:
        - tile_idx = 1 * 4 + 2 = 6
        - byte_offset = 6 * 32 = 192

        The patched bytes should be at data[192:224], not anywhere else.
        """
        tiles_per_row = 4
        expected_tile_idx = 6  # TilePosition(1, 2) -> 1 * 4 + 2 = 6

        dialog = GridArrangementDialog(sprite_4x2_tiles, tiles_per_row=tiles_per_row)
        dialog.show()

        # Place tile and apply overlay
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "1,2")
        dialog.overlay_layer.import_image(distinctive_overlay)
        dialog.overlay_layer.set_position(0, 0)
        dialog._apply_overlay()
        # Process events to handle the deferred QMessageBox
        qtbot.wait(10)
        dialog.accept()

        result = dialog.arrangement_result
        assert result is not None
        assert result.modified_tiles is not None

        # Now simulate what ROMWorkflowController does
        from core.tile_utils import encode_4bpp_tile

        data_before = bytearray(mock_4bpp_tile_data)
        data_after = bytearray(mock_4bpp_tile_data)

        # Apply the patch (mimicking _update_tile_data_from_modified_tiles)
        for pos, img in result.modified_tiles.items():
            tile_idx = pos.row * tiles_per_row + pos.col
            offset = tile_idx * 32

            img_l = img.convert("L")
            pixels = np.array(img_l, dtype=np.uint8)
            indices = (pixels // 16).flatten()
            tile_bytes = encode_4bpp_tile(indices)

            data_after[offset : offset + 32] = tile_bytes

        # Verify ONLY the expected offset was modified
        for i in range(8):  # 8 tiles
            offset = i * 32
            tile_before = data_before[offset : offset + 32]
            tile_after = data_after[offset : offset + 32]

            if i == expected_tile_idx:
                # This tile SHOULD be modified
                assert tile_before != tile_after, f"Tile {i} at offset {offset} should have been modified but wasn't"
            else:
                # Other tiles should NOT be modified
                assert tile_before == tile_after, (
                    f"Tile {i} at offset {offset} was modified but shouldn't have been! "
                    f"Only tile {expected_tile_idx} should change."
                )


# --- Bug Reproduction Test ---


class TestApplyThenRearrangeDataLoss:
    """Test that overlay changes survive arrangement changes (regression tests)."""

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_rearrange_after_apply_preserves_modified_tiles(
        self, mock_info, mock_warning, qapp, qtbot, sprite_4x2_tiles, distinctive_overlay
    ):
        """
        Verify that rearranging tiles after applying overlay does NOT lose the changes.

        Workflow: Apply overlay → Rearrange tiles → Accept dialog → modified_tiles present
        """
        tiles_per_row = 4
        dialog = GridArrangementDialog(sprite_4x2_tiles, tiles_per_row=tiles_per_row)
        dialog.show()

        # Place a tile
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")

        # Apply overlay
        dialog.overlay_layer.import_image(distinctive_overlay)
        dialog.overlay_layer.set_position(0, 0)
        dialog._apply_overlay()
        # Process events to handle the deferred QMessageBox
        qtbot.wait(10)

        # Verify apply worked
        assert dialog._apply_result is not None, "Apply should have succeeded"
        assert dialog._apply_result.success

        # Save the modified pixel value for verification
        modified_tile = dialog.tiles[TilePosition(0, 0)]
        modified_pixel = modified_tile.getpixel((0, 0))

        # NOW: Rearrange tiles (move the tile to a different position)
        # This triggers _on_arrangement_changed
        dialog.arrangement_manager.move_grid_item((0, 0), (0, 1))

        # Verify the pixels are still modified in self.tiles
        current_tile = dialog.tiles[TilePosition(0, 0)]
        current_pixel = current_tile.getpixel((0, 0))
        assert current_pixel == modified_pixel, "Tile pixels should still be modified even after rearrangement"

        # Close dialog and verify result - THIS IS THE CRITICAL CHECK
        dialog.accept()

        result = dialog.arrangement_result
        assert result is not None, "arrangement_result should exist"

        # modified_tiles MUST be present after Apply + Rearrange + Accept
        assert result.modified_tiles is not None, (
            "modified_tiles is None! The overlay changes would be silently discarded. "
            "User applied overlay, moved tiles, clicked OK - and lost all their work."
        )

        # Verify the modified tile is in the result
        assert TilePosition(0, 0) in result.modified_tiles, "The modified tile should be in the result"

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_add_tile_after_apply_preserves_modified_tiles(
        self, mock_info, mock_warning, qapp, qtbot, sprite_4x2_tiles, distinctive_overlay
    ):
        """
        Verify that adding a tile after applying overlay does NOT lose the changes.

        Workflow: Apply overlay → Add tile → Accept dialog → modified_tiles present
        """
        tiles_per_row = 4
        dialog = GridArrangementDialog(sprite_4x2_tiles, tiles_per_row=tiles_per_row)
        dialog.show()

        # Place initial tile and apply overlay
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
        dialog.overlay_layer.import_image(distinctive_overlay)
        dialog.overlay_layer.set_position(0, 0)
        dialog._apply_overlay()
        # Process events to handle the deferred QMessageBox
        qtbot.wait(10)

        assert dialog._apply_result is not None, "Apply should have succeeded"

        # Add another tile - this triggers arrangement_changed
        dialog.arrangement_manager.add_tile(TilePosition(0, 1))

        # Close dialog and verify result - THIS IS THE CRITICAL CHECK
        dialog.accept()

        result = dialog.arrangement_result
        assert result is not None, "arrangement_result should exist"

        # modified_tiles MUST be present after Apply + Add Tile + Accept
        assert result.modified_tiles is not None, "Adding a tile after apply caused modified_tiles to be lost!"

    @patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes)
    @patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok)
    def test_remove_tile_after_apply_preserves_modified_tiles(
        self, mock_info, mock_warning, qapp, qtbot, sprite_4x2_tiles, distinctive_overlay
    ):
        """
        Verify that removing a tile after applying overlay does NOT lose the changes.

        Workflow: Apply overlay → Remove tile → Accept dialog → modified_tiles present
        """
        tiles_per_row = 4
        dialog = GridArrangementDialog(sprite_4x2_tiles, tiles_per_row=tiles_per_row)
        dialog.show()

        # Place two tiles
        dialog.arrangement_manager.set_item_at(0, 0, ArrangementType.TILE, "0,0")
        dialog.arrangement_manager.set_item_at(0, 1, ArrangementType.TILE, "0,1")

        # Apply overlay (covers both tiles)
        dialog.overlay_layer.import_image(distinctive_overlay)
        dialog.overlay_layer.set_position(0, 0)
        dialog._apply_overlay()
        # Process events to handle the deferred QMessageBox
        qtbot.wait(10)

        assert dialog._apply_result is not None, "Apply should have succeeded"

        # Remove one tile - this triggers arrangement_changed
        dialog.arrangement_manager.remove_item_at(0, 1)

        # Close dialog and verify result - THIS IS THE CRITICAL CHECK
        dialog.accept()

        result = dialog.arrangement_result
        assert result is not None, "arrangement_result should exist"

        # modified_tiles MUST be present after Apply + Remove Tile + Accept
        assert result.modified_tiles is not None, "Removing a tile after apply caused modified_tiles to be lost!"
