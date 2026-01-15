"""Integration tests for sprite project save/load workflow.

Tests the signal chain from SaveExportPanel through EditWorkspace to controller,
and verifies the SpriteProject persistence functionality integrates correctly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PySide6.QtCore import Qt

from core.sprite_project import SpriteProject
from core.types import CompressionType
from tests.fixtures.timeouts import ui_timeout


@pytest.fixture
def sample_tile_data() -> bytes:
    """Create sample 4bpp tile data (2 tiles = 64 bytes)."""
    return bytes(range(64))


@pytest.fixture
def sample_palette() -> list[tuple[int, int, int]]:
    """Create sample 16-color palette."""
    return [(i * 16, i * 16, i * 16) for i in range(16)]


class TestSaveExportPanelSignals:
    """Tests for SaveExportPanel signal emissions."""

    def test_save_project_button_emits_signal(self, qtbot) -> None:
        """Save Project button should emit saveProjectClicked signal."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        panel.save_project_btn.setEnabled(True)

        with qtbot.waitSignal(panel.saveProjectClicked, timeout=ui_timeout()):
            panel.save_project_btn.click()

    def test_load_project_button_emits_signal(self, qtbot) -> None:
        """Load Project button should emit loadProjectClicked signal."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()

        with qtbot.waitSignal(panel.loadProjectClicked, timeout=ui_timeout()):
            panel.load_project_btn.click()

    def test_save_project_button_initially_disabled(self) -> None:
        """Save Project button should be disabled by default."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        assert not panel.save_project_btn.isEnabled()

    def test_load_project_button_always_enabled(self) -> None:
        """Load Project button should be enabled by default (can load without ROM)."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        assert panel.load_project_btn.isEnabled()

    def test_set_save_project_enabled(self) -> None:
        """set_save_project_enabled should update button state."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        assert not panel.save_project_btn.isEnabled()

        panel.set_save_project_enabled(True)
        assert panel.save_project_btn.isEnabled()

        panel.set_save_project_enabled(False)
        assert not panel.save_project_btn.isEnabled()


class TestEditWorkspaceSignalForwarding:
    """Tests for signal forwarding through EditWorkspace."""

    def test_workspace_forwards_save_project_signal(self, qtbot) -> None:
        """EditWorkspace should forward saveProjectRequested signal."""
        from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace

        workspace = EditWorkspace()

        with qtbot.waitSignal(workspace.saveProjectRequested, timeout=ui_timeout()):
            workspace.save_export_panel.save_project_btn.setEnabled(True)
            workspace.save_export_panel.save_project_btn.click()

    def test_workspace_forwards_load_project_signal(self, qtbot) -> None:
        """EditWorkspace should forward loadProjectRequested signal."""
        from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace

        workspace = EditWorkspace()

        with qtbot.waitSignal(workspace.loadProjectRequested, timeout=ui_timeout()):
            workspace.save_export_panel.load_project_btn.click()

    def test_workspace_set_save_project_enabled(self) -> None:
        """set_save_project_enabled should propagate to panel."""
        from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace

        workspace = EditWorkspace()
        assert not workspace.save_export_panel.save_project_btn.isEnabled()

        workspace.set_save_project_enabled(True)
        assert workspace.save_export_panel.save_project_btn.isEnabled()


class TestSpriteProjectRoundTrip:
    """Tests for sprite project save/load round-trip through file system."""

    def test_save_and_load_preserves_sprite_data(
        self,
        tmp_path: Path,
        sample_tile_data: bytes,
        sample_palette: list[tuple[int, int, int]],
    ) -> None:
        """Saving and loading should preserve all sprite data."""
        # Create project
        project = SpriteProject(
            name="test_sprite",
            width=16,
            height=8,
            tile_data=sample_tile_data,
            tile_count=2,
            palette_colors=sample_palette,
            palette_name="Test Palette",
            palette_index=5,
            original_rom_offset=0x3C6EF1,
            original_compressed_size=100,
            header_bytes=b"\x00\x01",
            compression_type="hal",
            rom_title="Test ROM",
            rom_checksum="0x1234",
        )

        # Save
        file_path = tmp_path / "test.spritepal"
        project.save(file_path)
        assert file_path.exists()

        # Load
        loaded = SpriteProject.load(file_path)

        # Verify
        assert loaded.name == "test_sprite"
        assert loaded.width == 16
        assert loaded.height == 8
        assert loaded.tile_data == sample_tile_data
        assert loaded.palette_colors == sample_palette
        assert loaded.original_rom_offset == 0x3C6EF1
        assert loaded.compression_type == "hal"

    def test_project_file_is_valid_json(
        self,
        tmp_path: Path,
        sample_tile_data: bytes,
        sample_palette: list[tuple[int, int, int]],
    ) -> None:
        """Saved project file should be valid JSON."""
        import json

        project = SpriteProject(
            name="json_test",
            width=16,
            height=8,
            tile_data=sample_tile_data,
            tile_count=2,
            palette_colors=sample_palette,
        )

        file_path = tmp_path / "test.spritepal"
        project.save(file_path)

        # Should be valid JSON
        content = file_path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert data["format_version"] == "1.0"
        assert data["sprite"]["name"] == "json_test"


class TestControllerSaveProjectMethod:
    """Tests for ROMWorkflowController.save_sprite_project method."""

    def test_save_project_requires_tile_data(self, qtbot) -> None:
        """save_sprite_project should show message if no tile data."""
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )

        editing_controller = EditingController()
        controller = ROMWorkflowController(
            parent=None,
            editing_controller=editing_controller,
        )

        # No tile data set
        controller.current_tile_data = None
        mock_message = MagicMock()
        controller._message_service = mock_message

        # Mock file dialog to not actually show
        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName") as mock_dialog:
            mock_dialog.return_value = ("", "")
            controller.save_sprite_project()

        # Should show message about no sprite loaded
        mock_message.show_message.assert_called_once()
        assert "No sprite" in mock_message.show_message.call_args[0][0]


class TestControllerLoadProjectMethod:
    """Tests for ROMWorkflowController.load_sprite_project method."""

    def test_load_project_warns_on_rom_mismatch(
        self,
        tmp_path: Path,
        qtbot,
        sample_tile_data: bytes,
        sample_palette: list[tuple[int, int, int]],
    ) -> None:
        """load_sprite_project should warn if ROM checksum doesn't match."""
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )

        # Create a project with a specific ROM checksum
        project = SpriteProject(
            name="mismatch_test",
            width=16,
            height=8,
            tile_data=sample_tile_data,
            tile_count=2,
            palette_colors=sample_palette,
            original_rom_offset=0x8000,
            rom_checksum="0xABCD",
            rom_title="Original ROM",
        )
        file_path = tmp_path / "mismatch.spritepal"
        project.save(file_path)

        # Create controller with different ROM checksum
        editing_controller = EditingController()
        controller = ROMWorkflowController(
            parent=None,
            editing_controller=editing_controller,
        )

        # Set up mock view to avoid UI issues
        mock_view = MagicMock()
        mock_view.workspace = MagicMock()
        controller._view = mock_view

        # Mock file dialog to return our test file
        with (
            patch(
                "PySide6.QtWidgets.QFileDialog.getOpenFileName",
                return_value=(str(file_path), ""),
            ),
            patch("PySide6.QtWidgets.QMessageBox.warning"),
        ):
            # No ROM loaded, so no warning should appear
            controller.load_sprite_project()

            # Verify project was loaded
            assert controller.current_tile_data == sample_tile_data
            assert controller.current_width == 16
            assert controller.current_offset == 0x8000
