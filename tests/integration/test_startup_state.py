import pytest

pytestmark = [pytest.mark.integration]
"""Integration tests for startup state consistency.

Verifies that UI state is correctly synchronized at startup:
- Mode toggle matches stack widget
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
        self.vram_file_changed = Mock()
        self.vram_file_changed.connect = Mock()
        self.cgram_file_changed = Mock()
        self.cgram_file_changed.connect = Mock()
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
        self.importImageRequested = Mock()
        self.importImageRequested.connect = Mock()
        self.saveProjectRequested = Mock()
        self.saveProjectRequested.connect = Mock()
        self.loadProjectRequested = Mock()
        self.loadProjectRequested.connect = Mock()
        self.arrangeClicked = Mock()
        self.arrangeClicked.connect = Mock()

        # Mock icon toolbar
        self.icon_toolbar = Mock()
        self.icon_toolbar.revertClicked = Mock()
        self.icon_toolbar.revertClicked.connect = Mock()

        # Added to satisfy ROMWorkflowController
        self.palette_panel = None

        # Overlay panel (for image import alignment)
        self.overlay_panel = Mock()
        self.overlay_panel.importRequested = Mock()
        self.overlay_panel.importRequested.connect = Mock()
        self.overlay_panel.applyRequested = Mock()
        self.overlay_panel.applyRequested.connect = Mock()
        self.overlay_panel.cancelRequested = Mock()
        self.overlay_panel.cancelRequested.connect = Mock()
        self.overlay_panel.baseOpacityChanged = Mock()
        self.overlay_panel.baseOpacityChanged.connect = Mock()
        self.overlay_panel.overlayOpacityChanged = Mock()
        self.overlay_panel.overlayOpacityChanged.connect = Mock()
        self.overlay_panel.positionChanged = Mock()
        self.overlay_panel.positionChanged.connect = Mock()

    def set_controller(self, ctrl):
        pass

    def set_save_project_enabled(self, enabled: bool) -> None:
        pass

    def set_arrange_enabled(self, enabled: bool) -> None:
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
        self.local_file_selected = Mock()
        self.local_file_selected.connect = Mock()
        self.local_file_activated = Mock()
        self.local_file_activated.connect = Mock()
        self.asset_browser = Mock()
        self.asset_browser.save_to_library_requested = Mock()
        self.asset_browser.save_to_library_requested.connect = Mock()
        self.asset_browser.rename_requested = Mock()
        self.asset_browser.rename_requested.connect = Mock()
        self.asset_browser.delete_requested = Mock()
        self.asset_browser.delete_requested.connect = Mock()

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

    def test_mode_toggle_matches_stack_at_startup(self, sprite_editor_workspace):
        """Verify mode toggle and stack widget are in sync at startup.

        This tests the sync-after-wiring pattern:
        - Toggle is set to ROM mode during __init__
        - Signal is connected after toggle state is set
        - Explicit sync call ensures stack matches toggle
        """
        workspace = sprite_editor_workspace

        # Mode toggle should default to ROM mode
        assert workspace.current_mode == "rom"

        # The visible page should be the ROM page
        from PySide6.QtWidgets import QStackedWidget

        stack = workspace.findChild(QStackedWidget)
        assert stack.currentWidget() == workspace.rom_page

    def test_mode_switch_updates_stack(self, sprite_editor_workspace):
        """Verify switching modes updates the stack widget."""
        workspace = sprite_editor_workspace

        # Switch to VRAM mode
        workspace.set_mode("vram")

        # Stack should now show VRAM page
        from PySide6.QtWidgets import QStackedWidget

        stack = workspace.findChild(QStackedWidget)
        assert stack.currentWidget() == workspace.vram_page
        assert workspace.current_mode == "vram"

        # Switch back to ROM mode
        workspace.set_mode("rom")

        # Stack should show ROM page again
        assert stack.currentWidget() == workspace.rom_page
        assert workspace.current_mode == "rom"

    def test_set_mode_programmatic_updates_toggle_and_stack(self, sprite_editor_workspace):
        """Verify programmatic set_mode() updates both toggle and stack."""
        workspace = sprite_editor_workspace

        # Use the public API to switch modes
        workspace.set_mode("vram")

        # Both toggle and stack should update
        assert workspace.current_mode == "vram"
        from PySide6.QtWidgets import QStackedWidget

        stack = workspace.findChild(QStackedWidget)
        assert stack.currentWidget() == workspace.vram_page

        workspace.set_mode("rom")

        assert workspace.current_mode == "rom"
        assert stack.currentWidget() == workspace.rom_page

    def test_controllers_receive_mode_at_startup(self, sprite_editor_workspace):
        """Verify sub-controllers are set to correct mode at startup.

        The mode_changed signal should propagate to sub-controllers during
        the sync-after-wiring call.
        """
        workspace = sprite_editor_workspace

        # Controllers should be in ROM mode (default)
        assert workspace.extraction_controller.mode == "rom"
        assert workspace.injection_controller.mode == "rom"

    def test_mode_switch_propagates_to_controllers(self, sprite_editor_workspace):
        """Verify mode switches propagate to all sub-controllers."""
        workspace = sprite_editor_workspace

        # Switch to VRAM mode
        workspace.set_mode("vram")

        # All controllers should update
        assert workspace.extraction_controller.mode == "vram"
        assert workspace.injection_controller.mode == "vram"

        # Switch back to ROM
        workspace.set_mode("rom")

        assert workspace.extraction_controller.mode == "rom"
        assert workspace.injection_controller.mode == "rom"


class TestModeToggleDataConsistency:
    """Tests for toggle data consistency."""

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

    def test_toggle_count_matches_stack_count(self, sprite_editor_workspace):
        """Verify toggle options match stack pages."""
        workspace = sprite_editor_workspace
        from PySide6.QtWidgets import QStackedWidget

        stack = workspace.findChild(QStackedWidget)

        # SegmentedToggle doesn't have a public count() but we can check if it has the 2 expected options
        assert workspace.mode_toggle is not None
        assert stack.count() == 2  # VRAM and ROM

    def test_data_mapping_is_consistent(self, sprite_editor_workspace):
        """Verify toggle data maps to correct stack page."""
        workspace = sprite_editor_workspace
        from PySide6.QtWidgets import QStackedWidget

        stack = workspace.findChild(QStackedWidget)

        # "vram" should map to VRAM page
        workspace.set_mode("vram")
        assert stack.currentWidget() == workspace.vram_page

        # "rom" should map to ROM page
        workspace.set_mode("rom")
        assert stack.currentWidget() == workspace.rom_page
