from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtWidgets import QComboBox, QWidget

from ui.workspaces import SpriteEditorWorkspace


class MockEditTab(QWidget):
    """Mock for EditTab which wraps EditWorkspace."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.detach_btn = Mock()
        self.detach_btn.hide = Mock()
        self.ready_for_inject = Mock()
        self.ready_for_inject.connect = Mock()
        self.workspace = MockEditWorkspace()

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
        self.browse_oam_requested = Mock()
        self.browse_oam_requested.connect = Mock()
        self.generate_preview_requested = Mock()
        self.generate_preview_requested.connect = Mock()

    def set_extraction_controller(self, ctrl):
        pass

    def get_preview_size(self):
        return 128

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
    def mock_deps(self):
        """Create mock dependencies for controllers."""
        deps = MagicMock()
        deps.rom_cache = MagicMock()
        deps.rom_extractor = MagicMock()
        deps.application_state_manager = MagicMock()
        deps.log_watcher = MagicMock()
        deps.sprite_library = MagicMock()
        return deps

    @pytest.fixture
    def sprite_editor_workspace(self, qt_app, mock_deps):
        # Patch the VRAMEditorPage and ROMWorkflowPage at the location they're imported
        # (workspace module imports from views.workspaces)
        with (
            patch("ui.workspaces.sprite_editor_workspace.VRAMEditorPage", MockVRAMEditorPage),
            patch("ui.workspaces.sprite_editor_workspace.ROMWorkflowPage", MockROMWorkflowPage),
        ):
            workspace = SpriteEditorWorkspace(
                settings_manager=mock_deps.application_state_manager,
                rom_cache=mock_deps.rom_cache,
                rom_extractor=mock_deps.rom_extractor,
                log_watcher=mock_deps.log_watcher,
                sprite_library=mock_deps.sprite_library,
            )
            return workspace

    def test_mode_switch(self, sprite_editor_workspace):
        # Verify mode combo exists
        assert hasattr(sprite_editor_workspace, "_mode_combo")
        combo = sprite_editor_workspace._mode_combo
        assert isinstance(combo, QComboBox)
        assert combo.count() == 2

        # Default is now ROM mode (index 1). Verify this.
        assert combo.currentIndex() == 1

        # Test mode switching between VRAM and ROM modes
        # The mode_changed signal triggers _on_mode_changed_internal which
        # propagates to extraction/injection controllers
        with patch.object(sprite_editor_workspace._extraction_controller, "set_mode") as mock_extract_mode:
            with patch.object(sprite_editor_workspace._injection_controller, "set_mode") as mock_inject_mode:
                # Switch to VRAM mode first (from default ROM mode)
                combo.setCurrentIndex(0)

                # Verify controllers received mode change to VRAM
                mock_extract_mode.assert_called_with("vram")
                mock_inject_mode.assert_called_with("vram")

                # Change back to ROM mode (index 1)
                combo.setCurrentIndex(1)
                mock_extract_mode.assert_called_with("rom")
                mock_inject_mode.assert_called_with("rom")

    def test_jump_to_offset_switches_mode(self, sprite_editor_workspace):
        # Verify jump_to_offset sets mode and offset

        # Mock the rom_workflow_controller.set_offset method
        sprite_editor_workspace._rom_workflow_controller = MagicMock()

        # Call jump_to_offset
        sprite_editor_workspace.jump_to_offset(0x123456)

        # Should have switched to ROM mode
        assert sprite_editor_workspace._mode_combo.currentData() == "rom"

        # Verify rom workflow controller offset set (auto_open=True is default behavior)
        sprite_editor_workspace._rom_workflow_controller.set_offset.assert_called_with(0x123456, auto_open=True)
