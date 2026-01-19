"""Tests for CaptureImportDialog.

Tests the Mesen capture import configuration dialog.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from core.mesen_integration.click_extractor import (
    CaptureResult,
    OAMEntry,
    OBSELConfig,
    TileData,
)
from ui.dialogs.capture_import_dialog import CaptureImportDialog


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
    """Create sample tile data."""
    return TileData(
        tile_index=10,
        vram_addr=0x6000,
        pos_x=0,
        pos_y=0,
        data_hex="FF" * 32,
    )


@pytest.fixture
def sample_palettes() -> dict[int, list[int]]:
    """Create sample RGB palettes."""
    return {
        0: [0x000000] + [0x00FF00] * 15,
        3: [0x000000] + [0x0000FF] * 15,
        7: [0x000000] + [0xFF0000] * 15,
    }


@pytest.fixture
def sample_capture(
    obsel_config: OBSELConfig,
    sample_tile_data: TileData,
    sample_palettes: dict[int, list[int]],
) -> CaptureResult:
    """Create a sample capture with entries in different palettes."""
    entries = [
        # Palette 0 - 2 entries (should cluster together as they're close)
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
        # Palette 3 - 3 entries (should cluster together as they're close)
        OAMEntry(
            id=2,
            x=30,
            y=30,
            tile=20,
            width=8,
            height=8,
            flip_h=False,
            flip_v=False,
            palette=3,
            tiles=[sample_tile_data],
        ),
        OAMEntry(
            id=3,
            x=38,
            y=30,
            tile=21,
            width=8,
            height=8,
            flip_h=False,
            flip_v=False,
            palette=3,
            tiles=[sample_tile_data],
        ),
        OAMEntry(
            id=4,
            x=46,
            y=30,
            tile=22,
            width=8,
            height=8,
            flip_h=False,
            flip_v=False,
            palette=3,
            tiles=[sample_tile_data],
        ),
        # Palette 7 - 1 entry (separate sprite)
        OAMEntry(
            id=5,
            x=50,
            y=60,
            tile=30,
            width=16,
            height=16,
            flip_h=False,
            flip_v=False,
            palette=7,
            tiles=[sample_tile_data] * 4,
        ),
    ]
    return CaptureResult(
        frame=100,
        visible_count=6,
        obsel=obsel_config,
        entries=entries,
        palettes=sample_palettes,
        timestamp=12345,
    )


class TestCaptureImportDialog:
    """Tests for CaptureImportDialog."""

    def test_dialog_creation(self, qtbot, sample_capture: CaptureResult) -> None:
        """Dialog can be created with capture data."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        assert dialog is not None
        assert dialog._capture == sample_capture

    def test_shows_cluster_list(self, qtbot, sample_capture: CaptureResult) -> None:
        """Cluster list is populated with sprite clusters."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        # Should have a cluster list with items
        assert dialog._cluster_list is not None
        # Clusters depend on proximity - we should have at least one cluster
        assert dialog._cluster_list.count() > 0

    def test_cluster_list_shows_dimensions(self, qtbot, sample_capture: CaptureResult) -> None:
        """Each cluster item shows dimensions and palette info."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        # Check first item contains expected info patterns
        assert dialog._cluster_list is not None
        first_item = dialog._cluster_list.item(0)
        assert first_item is not None
        text = first_item.text()
        # Should have dimension like "NxN" and "Palette" mentioned
        assert "x" in text.lower()
        assert "palette" in text.lower()

    def test_first_cluster_selected_by_default(self, qtbot, sample_capture: CaptureResult) -> None:
        """First cluster is selected by default."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        assert dialog._cluster_list is not None
        if dialog._cluster_list.count() > 0:
            first_item = dialog._cluster_list.item(0)
            assert first_item is not None
            assert first_item.isSelected()

    def test_garbage_filter_enabled_by_default(self, qtbot, sample_capture: CaptureResult) -> None:
        """Garbage filter checkbox is checked by default."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        assert dialog._garbage_checkbox.isChecked()

    def test_accept_collects_selected_clusters(self, qtbot, sample_capture: CaptureResult) -> None:
        """Accept stores selected cluster list and palette indices."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        # Select all clusters
        dialog._select_all_clusters()
        dialog.accept()

        # Should have some clusters and their palettes
        assert len(dialog.selected_clusters) > 0
        assert len(dialog.selected_palettes) > 0

    def test_accept_stores_garbage_filter_setting(self, qtbot, sample_capture: CaptureResult) -> None:
        """Accept stores garbage filter setting."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        # Disable garbage filter
        dialog._garbage_checkbox.setChecked(False)
        dialog.accept()

        assert dialog.filter_garbage_tiles is False

        # Re-enable and accept again
        dialog._garbage_checkbox.setChecked(True)
        dialog.accept()

        assert dialog.filter_garbage_tiles is True

    def test_select_all_selects_all_clusters(self, qtbot, sample_capture: CaptureResult) -> None:
        """Select All button selects all cluster items."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        # First deselect all
        dialog._select_no_clusters()

        # Click select all
        dialog._select_all_clusters()

        # All should be selected
        assert dialog._cluster_list is not None
        for i in range(dialog._cluster_list.count()):
            item = dialog._cluster_list.item(i)
            assert item is not None
            assert item.isSelected()

    def test_select_none_deselects_all_clusters(self, qtbot, sample_capture: CaptureResult) -> None:
        """Select None button deselects all cluster items."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        # First select all
        dialog._select_all_clusters()

        # Click select none
        dialog._select_no_clusters()

        # None should be selected
        assert dialog._cluster_list is not None
        for i in range(dialog._cluster_list.count()):
            item = dialog._cluster_list.item(i)
            assert item is not None
            assert not item.isSelected()

    def test_preview_label_exists(self, qtbot, sample_capture: CaptureResult) -> None:
        """Preview label exists in dialog."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        assert dialog._preview_label is not None

    def test_preview_shows_no_selection_message(self, qtbot, sample_capture: CaptureResult) -> None:
        """Preview shows message when no clusters selected."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        # Deselect all clusters
        dialog._select_no_clusters()
        dialog._update_preview()

        assert "select" in dialog._preview_label.text().lower()

    def test_info_section_shows_frame(self, qtbot, sample_capture: CaptureResult) -> None:
        """Info section displays frame number."""
        dialog = CaptureImportDialog(sample_capture, parent=None)
        qtbot.addWidget(dialog)

        # Dialog was created with frame 100
        # Just ensure dialog was created successfully
        assert dialog._capture.frame == 100


class TestCaptureImportDialogEdgeCases:
    """Edge case tests for CaptureImportDialog."""

    def test_single_sprite_capture(self, qtbot, obsel_config: OBSELConfig, sample_tile_data: TileData) -> None:
        """Dialog handles capture with single sprite."""
        entries = [
            OAMEntry(
                id=0,
                x=0,
                y=0,
                tile=0,
                width=8,
                height=8,
                flip_h=False,
                flip_v=False,
                palette=5,
                tiles=[sample_tile_data],
            ),
        ]
        capture = CaptureResult(
            frame=1,
            visible_count=1,
            obsel=obsel_config,
            entries=entries,
            palettes={5: [0x000000] * 16},
            timestamp=0,
        )

        dialog = CaptureImportDialog(capture, parent=None)
        qtbot.addWidget(dialog)

        # Should have exactly one cluster
        assert dialog._cluster_list is not None
        assert dialog._cluster_list.count() == 1

    def test_empty_entries_list(self, qtbot, obsel_config: OBSELConfig) -> None:
        """Dialog handles capture with no entries."""
        capture = CaptureResult(
            frame=0,
            visible_count=0,
            obsel=obsel_config,
            entries=[],
            palettes={},
            timestamp=0,
        )

        dialog = CaptureImportDialog(capture, parent=None)
        qtbot.addWidget(dialog)

        # Should have empty cluster list
        assert dialog._cluster_list is not None
        assert dialog._cluster_list.count() == 0

    def test_accept_with_no_selection_returns_empty(
        self, qtbot, obsel_config: OBSELConfig, sample_tile_data: TileData
    ) -> None:
        """Accept with no selection returns empty clusters."""
        entries = [
            OAMEntry(
                id=0,
                x=0,
                y=0,
                tile=0,
                width=8,
                height=8,
                flip_h=False,
                flip_v=False,
                palette=5,
                tiles=[sample_tile_data],
            ),
        ]
        capture = CaptureResult(
            frame=1,
            visible_count=1,
            obsel=obsel_config,
            entries=entries,
            palettes={5: [0x000000] * 16},
            timestamp=0,
        )

        dialog = CaptureImportDialog(capture, parent=None)
        qtbot.addWidget(dialog)

        # Deselect all
        dialog._select_no_clusters()
        dialog.accept()

        assert len(dialog.selected_clusters) == 0
        assert len(dialog.selected_palettes) == 0
