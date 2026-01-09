"""Integration tests for startup state consistency.

Verifies that UI state is correctly synchronized at startup:
- Mode combo matches stack widget
- Tab selections are consistent
- Session restore maintains state consistency
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtWidgets import QWidget


# --- Mock Classes (reused from test_mode_switch_repro.py) ---


class MockEditTab(QWidget):
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
    def __init__(self, *args, **kwargs):
        super().__init__()
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

    def set_mode(self, mode):
        pass


class MockVRAMEditorPage(QWidget):
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
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.saveToRomRequested = Mock()
        self.saveToRomRequested.connect = Mock()
        self.exportPngRequested = Mock()
        self.exportPngRequested.connect = Mock()

    def set_controller(self, ctrl):
        pass


class MockROMWorkflowPage(QWidget):
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
        self.sprite_selected = Mock()
        self.sprite_selected.connect = Mock()
        self.sprite_activated = Mock()
        self.sprite_activated.connect = Mock()
        self.asset_browser = Mock()
        self.asset_browser.save_to_library_requested = Mock()
        self.asset_browser.save_to_library_requested.connect = Mock()
        self.asset_browser.rename_requested = Mock()
        self.asset_browser.rename_requested.connect = Mock()
        self.asset_browser.delete_requested = Mock()
        self.asset_browser.delete_requested.connect = Mock()


# --- Test Class ---


class TestStartupState:
    """Tests for verifying UI state consistency at startup."""

    @pytest.fixture
    def mock_deps(self):
        deps = MagicMock()
        deps.rom_cache = MagicMock()
        deps.rom_extractor = MagicMock()
        deps.application_state_manager = MagicMock()
        deps.log_watcher = MagicMock()
        deps.sprite_library = MagicMock()
        return deps

    @pytest.fixture
    def sprite_editor_workspace(self, qtbot, mock_deps):
        from ui.workspaces.sprite_editor_workspace import SpriteEditorWorkspace

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
            qtbot.addWidget(workspace)
            return workspace

    def test_mode_combo_matches_stack_at_startup(self, sprite_editor_workspace):
        """Verify mode combo and stack widget are in sync at startup.

        This tests the sync-after-wiring pattern:
        - Combo is set to ROM mode (index 1) during __init__
        - Signal is connected after combo state is set
        - Explicit sync call ensures stack matches combo
        """
        workspace = sprite_editor_workspace

        # Mode combo should default to ROM mode (index 1)
        assert workspace._mode_combo.currentIndex() == 1
        assert workspace._mode_combo.currentData() == "rom"

        # Stack should show ROM page (index 1)
        assert workspace._mode_stack.currentIndex() == 1

        # The visible page should be the ROM page
        assert workspace._mode_stack.currentWidget() == workspace._rom_page

    def test_mode_switch_updates_stack(self, sprite_editor_workspace):
        """Verify switching modes updates the stack widget."""
        workspace = sprite_editor_workspace

        # Switch to VRAM mode
        workspace._mode_combo.setCurrentIndex(0)

        # Stack should now show VRAM page
        assert workspace._mode_stack.currentIndex() == 0
        assert workspace._mode_stack.currentWidget() == workspace._vram_page
        assert workspace._mode_combo.currentData() == "vram"

        # Switch back to ROM mode
        workspace._mode_combo.setCurrentIndex(1)

        # Stack should show ROM page again
        assert workspace._mode_stack.currentIndex() == 1
        assert workspace._mode_stack.currentWidget() == workspace._rom_page
        assert workspace._mode_combo.currentData() == "rom"

    def test_set_mode_programmatic_updates_combo_and_stack(self, sprite_editor_workspace):
        """Verify programmatic set_mode() updates both combo and stack."""
        workspace = sprite_editor_workspace

        # Use the public API to switch modes
        workspace.set_mode("vram")

        # Both combo and stack should update
        assert workspace._mode_combo.currentData() == "vram"
        assert workspace._mode_stack.currentWidget() == workspace._vram_page

        workspace.set_mode("rom")

        assert workspace._mode_combo.currentData() == "rom"
        assert workspace._mode_stack.currentWidget() == workspace._rom_page

    def test_controllers_receive_mode_at_startup(self, sprite_editor_workspace):
        """Verify sub-controllers are set to correct mode at startup.

        The mode_changed signal should propagate to sub-controllers during
        the sync-after-wiring call.
        """
        workspace = sprite_editor_workspace

        # Controllers should be in ROM mode (default)
        assert workspace._extraction_controller._mode == "rom"
        assert workspace._injection_controller._mode == "rom"

    def test_mode_switch_propagates_to_controllers(self, sprite_editor_workspace):
        """Verify mode switches propagate to all sub-controllers."""
        workspace = sprite_editor_workspace

        # Switch to VRAM mode
        workspace.set_mode("vram")

        # All controllers should update
        assert workspace._extraction_controller._mode == "vram"
        assert workspace._injection_controller._mode == "vram"

        # Switch back to ROM
        workspace.set_mode("rom")

        assert workspace._extraction_controller._mode == "rom"
        assert workspace._injection_controller._mode == "rom"


class TestModeComboDataConsistency:
    """Tests for combo box data consistency."""

    @pytest.fixture
    def mock_deps(self):
        deps = MagicMock()
        deps.rom_cache = MagicMock()
        deps.rom_extractor = MagicMock()
        deps.application_state_manager = MagicMock()
        deps.log_watcher = MagicMock()
        deps.sprite_library = MagicMock()
        return deps

    @pytest.fixture
    def sprite_editor_workspace(self, qtbot, mock_deps):
        from ui.workspaces.sprite_editor_workspace import SpriteEditorWorkspace

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
            qtbot.addWidget(workspace)
            return workspace

    def test_combo_data_values_are_strings(self, sprite_editor_workspace):
        """Verify combo items have string data values for mode identification."""
        combo = sprite_editor_workspace._mode_combo

        # Check each item has the expected data
        assert combo.itemData(0) == "vram"
        assert combo.itemData(1) == "rom"

    def test_combo_count_matches_stack_count(self, sprite_editor_workspace):
        """Verify combo items match stack pages."""
        workspace = sprite_editor_workspace

        assert workspace._mode_combo.count() == workspace._mode_stack.count()
        assert workspace._mode_combo.count() == 2  # VRAM and ROM

    def test_index_mapping_is_consistent(self, sprite_editor_workspace):
        """Verify combo index maps to correct stack page."""
        workspace = sprite_editor_workspace

        # Index 0 should be VRAM
        workspace._mode_combo.setCurrentIndex(0)
        assert workspace._mode_stack.currentWidget() == workspace._vram_page

        # Index 1 should be ROM
        workspace._mode_combo.setCurrentIndex(1)
        assert workspace._mode_stack.currentWidget() == workspace._rom_page
