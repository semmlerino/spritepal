from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtWidgets import QComboBox, QWidget

from ui.workspaces.sprite_editor_workspace import SpriteEditorWorkspace

# --- Mock Classes (simplified from test_rom_mode_workflow.py) ---


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

    # --- Test Class ---

    # Delegation methods from source_bar
    def set_rom_available(self, available: bool, rom_size: int = 0) -> None:
        """Mock: Update ROM availability state in source bar."""
        pass

    def set_rom_path(self, path: str) -> None:
        """Mock: Set ROM file path in source bar."""
        pass

    def set_info(self, text: str) -> None:
        """Mock: Set info text in source bar."""
        pass

    def set_offset(self, offset: int) -> None:
        """Mock: Update displayed ROM offset in source bar."""
        pass

    def set_action_text(self, text: str) -> None:
        """Mock: Set action button text in source bar."""
        pass

    def set_action_loading(self, loading: bool) -> None:
        """Mock: Set action button loading state in source bar."""
        pass

    # Delegation methods from asset_browser
    def set_thumbnail(self, offset: int, pixmap) -> None:
        """Mock: Set thumbnail for a sprite in asset browser."""
        pass

    def add_rom_sprite(self, name: str, offset: int) -> None:
        """Mock: Add a ROM sprite to the asset browser."""
        pass

    def add_mesen_capture(self, name: str, offset: int) -> None:
        """Mock: Add a Mesen capture to the asset browser."""
        pass

    def add_library_sprite(self, name: str, offset: int, thumbnail=None) -> None:
        """Mock: Add a library sprite to the asset browser."""
        pass

    def clear_asset_browser(self) -> None:
        """Mock: Clear all items from asset browser."""
        pass


class TestModeSwitchRepro:
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

    def test_load_rom_switches_mode(self, sprite_editor_workspace):
        """Verify that loading a ROM automatically switches to ROM mode."""
        # Ensure we start in VRAM mode (default)
        sprite_editor_workspace.set_mode("vram")
        assert sprite_editor_workspace.current_mode == "vram"

        # Mock the controller's load_rom to do nothing (we just want to check the mode switch)
        # Note: We are testing the workspace's load_rom method, not the controller's.
        sprite_editor_workspace._rom_workflow_controller = MagicMock()

        # Action: Load a ROM
        sprite_editor_workspace.load_rom("test.sfc")

        # Assertion: Should have switched to ROM mode
        assert sprite_editor_workspace.current_mode == "rom", "Failed to switch to ROM mode after loading a ROM"
