"""Tests for Import Mesen Capture feature in GridArrangementDialog.

Integration tests verifying the import button, handler, and grid population.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from PySide6.QtCore import Qt

from core.mesen_integration.capture_to_arrangement import CaptureArrangementData, PaletteGroup
from core.mesen_integration.click_extractor import CaptureResult, OAMEntry, OBSELConfig, TileData
from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.row_arrangement.grid_arrangement_manager import TilePosition

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = [pytest.mark.gui]


@pytest.fixture
def obsel_config() -> OBSELConfig:
    """Create a default OBSEL configuration."""
    return OBSELConfig(
        raw=0x63,
        name_base=3,
        name_select=0,
        size_select=3,
        tile_base_addr=0x6000,
        oam_base_addr=0x0000,
        oam_addr_offset=0x0100,
    )


@pytest.fixture
def sample_tile_data() -> TileData:
    """Create sample tile data with a non-white pattern."""
    # SNES 2bpp tile format: 32 bytes (4 bytes per row, 8 rows)
    # Create a simple pattern: alternating pixels to avoid all-white tile
    # Row format: 2 bytes for bitplane 0, 2 bytes for bitplane 1
    # This creates a checkerboard-like pattern
    tile_data = "55AA" * 16  # Alternating pattern across all 8 rows
    return TileData(
        tile_index=10,
        vram_addr=0x6000,
        pos_x=0,
        pos_y=0,
        data_hex=tile_data,
    )


@pytest.fixture
def sample_capture(obsel_config: OBSELConfig, sample_tile_data: TileData) -> CaptureResult:
    """Create a sample capture result."""
    entries = [
        OAMEntry(
            id=0,
            x=10,
            y=20,
            tile=10,
            width=8,
            height=8,
            flip_h=False,
            flip_v=False,
            palette=0,
            tiles=[sample_tile_data],
        ),
        OAMEntry(
            id=1,
            x=18,
            y=20,
            tile=11,
            width=8,
            height=8,
            flip_h=False,
            flip_v=False,
            palette=0,
            tiles=[sample_tile_data],
        ),
    ]
    return CaptureResult(
        frame=100,
        visible_count=2,
        obsel=obsel_config,
        entries=entries,
        palettes={0: [0x000000] + [0x00FF00] * 15},
        timestamp=12345,
    )


@pytest.fixture
def sample_arrangement_data(obsel_config: OBSELConfig) -> CaptureArrangementData:
    """Create sample arrangement data with tiles."""
    # Create 8x8 test tiles
    tile1 = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    tile2 = Image.new("RGBA", (8, 8), (0, 255, 0, 255))

    group = PaletteGroup(
        palette_index=0,
        entries=[],  # Entries not needed for this test
        tiles={(0, 0): tile1, (0, 1): tile2},
        width_tiles=2,
        height_tiles=1,
    )

    return CaptureArrangementData(
        source_path="/test/capture.json",
        frame=100,
        groups=[group],
        palettes={0: [(0, 0, 0)] + [(0, 255, 0)] * 15},
        obsel=obsel_config,
        total_tiles=2,
    )


@pytest.fixture
def dialog(qtbot: QtBot, tmp_path: Path) -> GridArrangementDialog:
    """Create a GridArrangementDialog with a test image."""
    test_image_path = tmp_path / "test_sprite.png"
    # Create a 16x16 image (2x2 8x8 tiles)
    test_image = Image.new("RGB", (16, 16), color="white")
    test_image.save(test_image_path)

    dialog = GridArrangementDialog(str(test_image_path), tiles_per_row=16)
    qtbot.addWidget(dialog)
    return dialog


@pytest.fixture
def capture_json_file(tmp_path: Path, sample_capture: CaptureResult) -> Path:
    """Create a valid capture JSON file."""
    capture_path = tmp_path / "sprite_capture_test.json"

    # Convert CaptureResult to JSON-serializable dict
    capture_dict = {
        "frame": sample_capture.frame,
        "visible_count": sample_capture.visible_count,
        "timestamp": sample_capture.timestamp,
        "obsel": {
            "raw": sample_capture.obsel.raw,
            "name_base": sample_capture.obsel.name_base,
            "name_select": sample_capture.obsel.name_select,
            "size_select": sample_capture.obsel.size_select,
            "tile_base_addr": sample_capture.obsel.tile_base_addr,
            "oam_base_addr": sample_capture.obsel.oam_base_addr,
            "oam_addr_offset": sample_capture.obsel.oam_addr_offset,
        },
        "entries": [
            {
                "id": e.id,
                "x": e.x,
                "y": e.y,
                "tile": e.tile,
                "width": e.width,
                "height": e.height,
                "flip_h": e.flip_h,
                "flip_v": e.flip_v,
                "palette": e.palette,
                "priority": e.priority,
                "name_table": e.name_table,
                "size_large": e.size_large,
                "tiles": [
                    {
                        "tile_index": t.tile_index,
                        "vram_addr": t.vram_addr,
                        "pos_x": t.pos_x,
                        "pos_y": t.pos_y,
                        "data_hex": t.data_hex,
                    }
                    for t in e.tiles
                ],
            }
            for e in sample_capture.entries
        ],
        "palettes": {str(k): v for k, v in sample_capture.palettes.items()},
    }

    with open(capture_path, "w") as f:
        json.dump(capture_dict, f)

    return capture_path


class TestImportMesenCapture:
    """Tests for Import Mesen Capture feature."""

    def test_import_button_exists(self, dialog: GridArrangementDialog, qtbot: QtBot) -> None:
        """Import Capture button is present."""
        with qtbot.waitExposed(dialog):
            dialog.show()

        assert hasattr(dialog, "import_capture_btn")
        assert dialog.import_capture_btn is not None
        assert dialog.import_capture_btn.isVisible()
        assert "Import Capture" in dialog.import_capture_btn.text()

    def test_import_button_tooltip(self, dialog: GridArrangementDialog, qtbot: QtBot) -> None:
        """Import Capture button has descriptive tooltip."""
        assert "Mesen" in dialog.import_capture_btn.toolTip()

    def test_import_no_file_selected(self, dialog: GridArrangementDialog, qtbot: QtBot) -> None:
        """Import handler returns early when no file selected."""
        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName") as mock_file_dialog:
            mock_file_dialog.return_value = ("", "")  # No file selected

            # Trigger import via button click
            qtbot.mouseClick(dialog.import_capture_btn, Qt.MouseButton.LeftButton)

            # No changes to arrangement
            assert dialog.arrangement_manager.get_arranged_count() == 0

    def test_import_invalid_file_shows_warning(
        self, dialog: GridArrangementDialog, qtbot: QtBot, tmp_path: Path
    ) -> None:
        """Import handler shows warning for invalid JSON."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not valid json {{{")

        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName") as mock_file_dialog:
            mock_file_dialog.return_value = (str(invalid_file), "")

            with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
                # Trigger import via button click
                qtbot.mouseClick(dialog.import_capture_btn, Qt.MouseButton.LeftButton)

                mock_warning.assert_called_once()
                assert "Failed to parse" in str(mock_warning.call_args)

    def test_populate_from_capture_adds_tiles(
        self,
        dialog: GridArrangementDialog,
        sample_arrangement_data: CaptureArrangementData,
        qtbot: QtBot,
    ) -> None:
        """Populate method adds tiles to dialog."""
        initial_count = dialog.arrangement_manager.get_arranged_count()
        assert initial_count == 0

        # Use public API
        dialog.populate_from_capture_data(sample_arrangement_data)

        # Should have added 2 tiles
        assert len(dialog.tiles) == 2
        # Tiles should be at positions (0,0) and (0,1)
        assert TilePosition(0, 0) in dialog.tiles
        assert TilePosition(0, 1) in dialog.tiles

    def test_populate_clears_existing_tiles(
        self,
        dialog: GridArrangementDialog,
        sample_arrangement_data: CaptureArrangementData,
        qtbot: QtBot,
    ) -> None:
        """Populate method clears existing tiles before adding new ones."""
        # Add some existing tiles
        dialog.tiles[TilePosition(5, 5)] = Image.new("RGBA", (8, 8))

        # Use public API
        dialog.populate_from_capture_data(sample_arrangement_data)

        # Old tile should be gone
        assert TilePosition(5, 5) not in dialog.tiles
        # New tiles should exist
        assert TilePosition(0, 0) in dialog.tiles

    def test_populate_creates_composite_image(
        self,
        dialog: GridArrangementDialog,
        sample_arrangement_data: CaptureArrangementData,
        qtbot: QtBot,
    ) -> None:
        """Populate method creates composite original_image."""
        # Use public API
        dialog.populate_from_capture_data(sample_arrangement_data)

        assert dialog.original_image is not None
        # With 2 tiles side by side: 16x8
        assert dialog.original_image.size == (16, 8)

    def test_populate_updates_processor_dimensions(
        self,
        dialog: GridArrangementDialog,
        sample_arrangement_data: CaptureArrangementData,
        qtbot: QtBot,
    ) -> None:
        """Populate method updates processor grid dimensions."""
        # Use public API
        dialog.populate_from_capture_data(sample_arrangement_data)

        # With 1 group of height 1 + 1 spacing = 2 rows
        assert dialog.processor.grid_rows >= 1
        assert dialog.processor.grid_cols >= 2

    def test_import_status_message(
        self,
        dialog: GridArrangementDialog,
        capture_json_file: Path,
        sample_capture: CaptureResult,
        qtbot: QtBot,
    ) -> None:
        """Import updates status bar with tile count."""
        from PySide6.QtWidgets import QMessageBox

        from core.mesen_integration.capture_to_arrangement import SpriteCluster

        # Create a mock cluster with real entries from the capture
        mock_cluster = SpriteCluster(
            id=0,
            entries=sample_capture.entries,
            palette_index=0,
            min_x=0,
            min_y=0,
            width=16,
            height=8,
        )

        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName") as mock_file_dialog:
            mock_file_dialog.return_value = (str(capture_json_file), "")

            with patch("ui.dialogs.capture_import_dialog.CaptureImportDialog") as mock_dialog_cls:
                mock_dialog_instance = MagicMock()
                mock_dialog_instance.exec.return_value = mock_dialog_cls.DialogCode.Accepted
                mock_dialog_instance.selected_clusters = [mock_cluster]
                mock_dialog_instance.filter_garbage_tiles = False
                mock_dialog_cls.return_value = mock_dialog_instance

                with (
                    patch("PySide6.QtWidgets.QMessageBox.question") as mock_question,
                    patch("PySide6.QtWidgets.QMessageBox.warning"),
                ):
                    mock_question.return_value = QMessageBox.StandardButton.No

                    # Trigger import via button click
                    qtbot.mouseClick(dialog.import_capture_btn, Qt.MouseButton.LeftButton)

        # Assert on actual status bar content instead of mocking _update_status
        status_text = dialog.status_bar.currentMessage()
        assert "Imported" in status_text or "tile" in status_text.lower()


class TestImportMesenCaptureEdgeCases:
    """Edge case tests for Import Mesen Capture."""

    def test_confirm_replace_existing_arrangement(
        self,
        dialog: GridArrangementDialog,
        sample_arrangement_data: CaptureArrangementData,
        qtbot: QtBot,
    ) -> None:
        """Import confirms before replacing existing arrangement."""
        # Add an existing arrangement
        dialog.arrangement_manager.add_tile(TilePosition(0, 0))
        assert dialog.arrangement_manager.get_arranged_count() == 1

        # Mock the import flow with confirmation rejected
        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName") as mock_file_dialog:
            mock_file_dialog.return_value = ("/test/capture.json", "")

            with patch("core.mesen_integration.click_extractor.MesenCaptureParser") as mock_parser:
                mock_parser_instance = MagicMock()
                mock_parser_instance.parse_file.return_value = MagicMock(
                    entries=[MagicMock(palette=0)],
                )
                mock_parser.return_value = mock_parser_instance

                with patch("ui.dialogs.capture_import_dialog.CaptureImportDialog") as mock_dialog:
                    mock_dialog_instance = MagicMock()
                    mock_dialog_instance.exec.return_value = mock_dialog.DialogCode.Accepted
                    # Use selected_clusters (new API) instead of selected_palettes
                    mock_dialog_instance.selected_clusters = [MagicMock(id=0, palette_index=0)]
                    mock_dialog_instance.filter_garbage_tiles = False
                    mock_dialog.return_value = mock_dialog_instance

                    with patch(
                        "core.mesen_integration.capture_to_arrangement.CaptureToArrangementConverter"
                    ) as mock_converter:
                        mock_converter_instance = MagicMock()
                        # Use convert_clusters (new API) instead of convert
                        mock_converter_instance.convert_clusters.return_value = sample_arrangement_data
                        mock_converter.return_value = mock_converter_instance

                        # Reject the confirmation
                        with patch("PySide6.QtWidgets.QMessageBox.question") as mock_question:
                            from PySide6.QtWidgets import QMessageBox

                            mock_question.return_value = QMessageBox.StandardButton.No

                            # Trigger import via button click
                            qtbot.mouseClick(dialog.import_capture_btn, Qt.MouseButton.LeftButton)

                            # Original arrangement should still exist
                            assert dialog.arrangement_manager.get_arranged_count() == 1

    def test_import_empty_capture_shows_warning(
        self,
        dialog: GridArrangementDialog,
        obsel_config: OBSELConfig,
        qtbot: QtBot,
    ) -> None:
        """Import shows warning for capture with no tiles."""
        empty_data = CaptureArrangementData(
            source_path="/test/empty.json",
            frame=0,
            groups=[],
            palettes={},
            obsel=obsel_config,
            total_tiles=0,
        )

        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName") as mock_file_dialog:
            mock_file_dialog.return_value = ("/test/capture.json", "")

            with patch("core.mesen_integration.click_extractor.MesenCaptureParser") as mock_parser:
                mock_parser_instance = MagicMock()
                mock_parser_instance.parse_file.return_value = MagicMock(
                    entries=[MagicMock(palette=0)],
                )
                mock_parser.return_value = mock_parser_instance

                with patch("ui.dialogs.capture_import_dialog.CaptureImportDialog") as mock_dialog:
                    mock_dialog_instance = MagicMock()
                    mock_dialog_instance.exec.return_value = mock_dialog.DialogCode.Accepted
                    # Use selected_clusters (new API) instead of selected_palettes
                    mock_dialog_instance.selected_clusters = [MagicMock(id=0, palette_index=0)]
                    mock_dialog_instance.filter_garbage_tiles = True
                    mock_dialog.return_value = mock_dialog_instance

                    with patch(
                        "core.mesen_integration.capture_to_arrangement.CaptureToArrangementConverter"
                    ) as mock_converter:
                        mock_converter_instance = MagicMock()
                        # Use convert_clusters (new API) instead of convert
                        mock_converter_instance.convert_clusters.return_value = empty_data
                        mock_converter.return_value = mock_converter_instance

                        with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
                            with patch("PySide6.QtWidgets.QMessageBox.question") as mock_question:
                                from PySide6.QtWidgets import QMessageBox

                                mock_question.return_value = QMessageBox.StandardButton.No
                                # Trigger import via button click
                                qtbot.mouseClick(dialog.import_capture_btn, Qt.MouseButton.LeftButton)

                            # Should warn about no tiles
                            mock_warning.assert_called_once()
                            assert "No tiles" in str(mock_warning.call_args)
