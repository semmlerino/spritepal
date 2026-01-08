from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtWidgets import QComboBox, QWidget

from ui.sprite_editor.controllers.main_controller import MainController
from ui.workspaces import SpriteEditorWorkspace


class MockEditTab(QWidget):
    """Mock for EditTab which wraps EditWorkspace."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.detach_btn = Mock()
        self.detach_btn.hide = Mock()
        self.ready_for_inject = Mock()
        self.ready_for_inject.connect = Mock()

    def set_controller(self, ctrl):
        pass


class MockTab(QWidget):
    """Mock for other tabs (Extract, Inject, etc.)."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.set_mode = Mock()
        self.set_offset = Mock()
        # Signals
        self.ready_for_inject = Mock()
        self.ready_for_inject.connect = Mock()

        self.extract_requested = Mock()
        self.extract_requested.connect = Mock()
        self.load_rom_requested = Mock()
        self.load_rom_requested.connect = Mock()
        self.browse_vram_requested = Mock()
        self.browse_vram_requested.connect = Mock()
        self.browse_cgram_requested = Mock()
        self.browse_cgram_requested.connect = Mock()
        self.browse_rom_requested = Mock()
        self.browse_rom_requested.connect = Mock()

        self.inject_requested = Mock()
        self.inject_requested.connect = Mock()
        self.save_rom_requested = Mock()
        self.save_rom_requested.connect = Mock()
        self.browse_png_requested = Mock()
        self.browse_png_requested.connect = Mock()

    def set_extraction_controller(self, ctrl):
        pass

    def set_controller(self, ctrl):
        pass


class MockVRAMEditorPage(QWidget):
    """Mock for VRAMEditorPage."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.extract_tab = MockTab()
        self.edit_tab = MockEditTab()
        self.inject_tab = MockTab()
        self.multi_palette_tab = MockTab()
        self.ready_for_inject = Mock()
        self.ready_for_inject.connect = Mock()

    def switch_to_inject_tab(self):
        pass


class MockEditWorkspace(QWidget):
    """Mock for EditWorkspace."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        # Signals required by ROMWorkflowController
        self.saveToRomRequested = Mock()
        self.saveToRomRequested.connect = Mock()
        self.exportPngRequested = Mock()
        self.exportPngRequested.connect = Mock()

    def set_controller(self, ctrl):
        pass


class MockROMWorkflowPage(QWidget):
    """Mock for ROMWorkflowPage."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.offset_changed = Mock()
        self.offset_changed.connect = Mock()
        self.workspace = MockEditWorkspace()
        self.source_bar = Mock()
        self.source_bar.offset_changed = Mock()
        self.source_bar.offset_changed.connect = Mock()
        self.source_bar.action_clicked = Mock()
        self.source_bar.action_clicked.connect = Mock()
        self.source_bar.browse_rom_requested = Mock()
        self.source_bar.browse_rom_requested.connect = Mock()

        # Asset browser signals (required by ROMWorkflowController)
        self.sprite_selected = Mock()
        self.sprite_selected.connect = Mock()
        self.sprite_activated = Mock()
        self.sprite_activated.connect = Mock()

        # Asset browser with context menu signals
        self.asset_browser = Mock()
        self.asset_browser.save_to_library_requested = Mock()
        self.asset_browser.save_to_library_requested.connect = Mock()
        self.asset_browser.rename_requested = Mock()
        self.asset_browser.rename_requested.connect = Mock()
        self.asset_browser.delete_requested = Mock()
        self.asset_browser.delete_requested.connect = Mock()

        self.recent_captures_widget = Mock()
        self.recent_captures_widget.offset_selected = Mock()
        self.recent_captures_widget.offset_selected.connect = Mock()
        self.recent_captures_widget.offset_activated = Mock()
        self.recent_captures_widget.offset_activated.connect = Mock()

        self.prev_btn = Mock()
        self.prev_btn.clicked = Mock()
        self.prev_btn.clicked.connect = Mock()

        self.next_btn = Mock()
        self.next_btn.clicked = Mock()
        self.next_btn.clicked.connect = Mock()

        self.offset_slider = Mock()
        self.offset_slider.valueChanged = Mock()
        self.offset_slider.valueChanged.connect = Mock()

        self.step_spin = Mock()
        self.step_spin.value = Mock(return_value=1)

    def set_rom_size(self, size: int) -> None:
        pass


class TestRomModeWorkflow:
    @pytest.fixture
    def mock_app_context(self):
        # Patch get_app_context in all controllers that use it
        with (
            patch("ui.sprite_editor.controllers.extraction_controller.get_app_context") as mock_extract,
            patch("ui.sprite_editor.controllers.rom_workflow_controller.get_app_context") as mock_rom,
            patch("core.app_context.get_app_context") as mock_core,
        ):
            context = MagicMock()
            context.rom_cache = MagicMock()
            context.application_state_manager = MagicMock()
            context.log_watcher = MagicMock()  # Needed for ROMWorkflowController

            mock_extract.return_value = context
            mock_rom.return_value = context
            mock_core.return_value = context

            yield context

    @pytest.fixture
    def sprite_editor_workspace(self, qt_app, mock_app_context):
        # Patch the VRAMEditorPage and ROMWorkflowPage at the location they're imported
        # (workspace module imports from views.workspaces)
        with (
            patch("ui.workspaces.sprite_editor_workspace.VRAMEditorPage", MockVRAMEditorPage),
            patch("ui.workspaces.sprite_editor_workspace.ROMWorkflowPage", MockROMWorkflowPage),
        ):
            workspace = SpriteEditorWorkspace(settings_manager=mock_app_context.application_state_manager)
            return workspace

    def test_mode_switch(self, sprite_editor_workspace):
        # Verify mode combo exists
        assert hasattr(sprite_editor_workspace, "_mode_combo")
        combo = sprite_editor_workspace._mode_combo
        assert isinstance(combo, QComboBox)
        assert combo.count() == 2

        # Test switching to ROM mode
        with patch.object(sprite_editor_workspace._controller, "set_mode") as mock_set_mode:
            # Change index to ROM (index 1)
            combo.setCurrentIndex(1)

            # Verify controller was called
            mock_set_mode.assert_called_with("rom")

            # Change back to VRAM (index 0)
            combo.setCurrentIndex(0)
            mock_set_mode.assert_called_with("vram")

    def test_jump_to_offset_switches_mode(self, sprite_editor_workspace):
        # Verify jump_to_offset sets mode and offset

        # Mock the controller methods we expect to be called
        sprite_editor_workspace._controller.rom_workflow_controller = MagicMock()

        # Call jump_to_offset
        sprite_editor_workspace.jump_to_offset(0x123456)

        # Should have switched to ROM mode
        assert sprite_editor_workspace._mode_combo.currentData() == "rom"

        # Verify rom workflow controller offset set (auto_open=True is default behavior)
        sprite_editor_workspace._controller.rom_workflow_controller.set_offset.assert_called_with(
            0x123456, auto_open=True
        )

    def test_controller_propagates_mode(self, mock_app_context):
        # Test MainController propagation logic
        with patch("ui.sprite_editor.controllers.main_controller.ROMWorkflowController", MagicMock()):
            controller = MainController()
            controller.extraction_controller = MagicMock()
            controller.injection_controller = MagicMock()

            controller.set_mode("rom")

            controller.extraction_controller.set_mode.assert_called_with("rom")
            controller.injection_controller.set_mode.assert_called_with("rom")
