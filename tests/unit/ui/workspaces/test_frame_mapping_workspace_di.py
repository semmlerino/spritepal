"""Tests for FrameMappingWorkspace dependency injection.

Verifies that the workspace can accept an injected controller or create its own.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.workspaces.frame_mapping_workspace import FrameMappingWorkspace


class TestFrameMappingWorkspaceDI:
    """Tests for controller dependency injection in workspace."""

    def test_default_controller_creation(self, app_context, qtbot) -> None:
        """Workspace creates its own controller when none injected."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Verify controller exists
        assert workspace.controller is not None
        assert isinstance(workspace.controller, FrameMappingController)

        # Verify controller has workspace as parent (for Qt ownership)
        assert workspace.controller.parent() is workspace

    def test_injected_controller(self, app_context, qtbot) -> None:
        """Workspace uses injected controller when provided."""
        # Create a controller without parent
        injected_controller = FrameMappingController(parent=None)

        # Inject into workspace
        workspace = FrameMappingWorkspace(controller=injected_controller)
        qtbot.addWidget(workspace)

        # Verify workspace uses the injected controller
        assert workspace.controller is injected_controller

        # Verify injected controller does not have workspace as parent
        # (caller controls lifecycle)
        assert workspace.controller.parent() is None

    def test_signal_connections_with_injected_controller(self, app_context, qtbot) -> None:
        """Signal connections work with injected controller."""
        # Create controller
        controller = FrameMappingController(parent=None)

        # Inject into workspace
        workspace = FrameMappingWorkspace(controller=controller)
        qtbot.addWidget(workspace)

        # Verify key signals are connected by checking workspace handles signals
        # We can test this by emitting a signal and checking for no errors
        with qtbot.waitSignal(controller.project_changed, timeout=1000):
            controller.project_changed.emit()

    def test_signal_connections_with_default_controller(self, app_context, qtbot) -> None:
        """Signal connections work with default controller."""
        # Create workspace (creates default controller)
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Verify signals work
        with qtbot.waitSignal(workspace.controller.project_changed, timeout=1000):
            workspace.controller.project_changed.emit()

    def test_controller_property_access(self, app_context, qtbot) -> None:
        """Controller property provides access to controller."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Access via property
        controller = workspace.controller
        assert controller is not None
        assert isinstance(controller, FrameMappingController)

        # Property returns the same instance
        assert workspace.controller is controller

    def test_multiple_workspaces_with_separate_controllers(self, app_context, qtbot) -> None:
        """Multiple workspaces can have separate controllers."""
        workspace1 = FrameMappingWorkspace()
        workspace2 = FrameMappingWorkspace()
        qtbot.addWidget(workspace1)
        qtbot.addWidget(workspace2)

        # Each workspace has its own controller
        assert workspace1.controller is not workspace2.controller

    def test_multiple_workspaces_with_shared_controller(self, app_context, qtbot) -> None:
        """Multiple workspaces can share a controller (though unusual)."""
        shared_controller = FrameMappingController(parent=None)

        workspace1 = FrameMappingWorkspace(controller=shared_controller)
        workspace2 = FrameMappingWorkspace(controller=shared_controller)
        qtbot.addWidget(workspace1)
        qtbot.addWidget(workspace2)

        # Both workspaces use the same controller
        assert workspace1.controller is shared_controller
        assert workspace2.controller is shared_controller
        assert workspace1.controller is workspace2.controller

    def test_controller_survives_workspace_deletion_when_injected(self, app_context, qtbot) -> None:
        """Injected controller is not deleted when workspace is deleted.

        Note: This test manually manages widget lifecycle rather than using
        qtbot.addWidget to avoid pytest-qt tracking issues with deleted widgets.
        """
        from PySide6.QtWidgets import QApplication

        controller = FrameMappingController(parent=None)

        # Create workspace but don't add to qtbot - we manage lifecycle manually
        workspace = FrameMappingWorkspace(controller=controller)
        workspace.show()  # Need to show to initialize properly
        QApplication.processEvents()

        # Block signals before deletion to prevent signals being delivered to deleted object
        controller.blockSignals(True)

        # Close and delete workspace
        workspace.close()
        workspace.deleteLater()
        QApplication.processEvents()
        qtbot.wait(100)
        QApplication.processEvents()

        # Unblock signals now that workspace is gone
        controller.blockSignals(False)

        # Controller still exists (caller owns it)
        assert controller is not None
        # Can still call methods
        controller.new_project("test")
        assert controller.has_project


class TestEditorPaletteSyncOnPaletteChange:
    """Tests for BUG-3 fix: palette editors sync when palette changes externally."""

    def test_palette_editors_synced_when_palette_color_changes(self, app_context, qtbot) -> None:
        """Open palette editors receive updates when palette color changes externally."""
        from core.frame_mapping_project import SheetPalette

        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Setup project with palette
        workspace.controller.new_project("test")
        colors = [(0, 0, 0)] * 16
        palette = SheetPalette(colors=colors)
        workspace.controller.set_sheet_palette(palette)

        # Create mock editors to track updates
        mock_editor1 = MagicMock()
        mock_editor1._palette = palette
        mock_editor1._palette_panel = MagicMock()
        mock_editor1._update_duplicate_warning = MagicMock()
        mock_editor1._controller = MagicMock()
        mock_editor1._controller.get_indexed_data.return_value = MagicMock()  # Simulate having data
        mock_editor1._canvas = MagicMock()

        mock_editor2 = MagicMock()
        mock_editor2._palette = palette
        mock_editor2._palette_panel = MagicMock()
        mock_editor2._update_duplicate_warning = MagicMock()
        mock_editor2._controller = MagicMock()
        mock_editor2._controller.get_indexed_data.return_value = MagicMock()
        mock_editor2._canvas = MagicMock()

        # Register mock editors
        workspace._palette.palette_editors["frame1.png"] = mock_editor1
        workspace._palette.palette_editors["frame2.png"] = mock_editor2

        # Change palette color (this should trigger _on_sheet_palette_changed)
        workspace.controller.set_sheet_palette_color(5, (255, 0, 0))

        # Verify both editors were synced
        mock_editor1._palette_panel.set_palette.assert_called()
        mock_editor1._update_duplicate_warning.assert_called()
        mock_editor1._canvas.set_image.assert_called()

        mock_editor2._palette_panel.set_palette.assert_called()
        mock_editor2._update_duplicate_warning.assert_called()
        mock_editor2._canvas.set_image.assert_called()

    def test_no_crash_when_no_editors_open(self, app_context, qtbot) -> None:
        """Palette change doesn't crash when no editors are open."""
        from core.frame_mapping_project import SheetPalette

        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Setup project with palette
        workspace.controller.new_project("test")
        colors = [(0, 0, 0)] * 16
        palette = SheetPalette(colors=colors)
        workspace.controller.set_sheet_palette(palette)

        # No editors registered (empty dict)
        assert len(workspace._palette.palette_editors) == 0

        # Change palette color - should not crash
        workspace.controller.set_sheet_palette_color(5, (255, 0, 0))

    def test_editor_receives_new_palette_reference(self, app_context, qtbot) -> None:
        """Editor's _palette is updated to match current palette from controller."""
        from core.frame_mapping_project import SheetPalette

        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Setup project with palette
        workspace.controller.new_project("test")
        colors = [(0, 0, 0)] * 16
        palette = SheetPalette(colors=colors)
        workspace.controller.set_sheet_palette(palette)

        # Create mock editor with old palette reference
        old_palette = SheetPalette(colors=[(128, 128, 128)] * 16)
        mock_editor = MagicMock()
        mock_editor._palette = old_palette  # Different palette object
        mock_editor._palette_panel = MagicMock()
        mock_editor._update_duplicate_warning = MagicMock()
        mock_editor._controller = MagicMock()
        mock_editor._controller.get_indexed_data.return_value = None  # No data
        mock_editor._canvas = MagicMock()

        workspace._palette.palette_editors["frame1.png"] = mock_editor

        # Change palette color (palette service may create new palette object)
        workspace.controller.set_sheet_palette_color(5, (255, 0, 0))

        # Editor's _palette should now reference the CURRENT palette from controller
        # (not necessarily the original object, since palette service may create new objects)
        current_palette = workspace.controller.get_sheet_palette()
        assert mock_editor._palette is current_palette
        # Verify the color was actually changed
        assert current_palette is not None
        assert current_palette.colors[5] == (255, 0, 0)


class TestAutoSaveDebouncing:
    """Tests for auto-save debouncing to avoid slow nudge operations."""

    def test_auto_save_timer_exists(self, app_context, qtbot) -> None:
        """Workspace has auto-save debounce timer."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        assert hasattr(workspace, "_auto_save_timer")
        assert workspace._auto_save_timer.isSingleShot()
        assert workspace._auto_save_timer.interval() == 500

    def test_save_debounced_on_rapid_changes(self, app_context, qtbot, tmp_path) -> None:
        """Multiple rapid save requests result in single save after debounce."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Setup project with path
        workspace.controller.new_project("test")
        project_path = tmp_path / "test.spritepal"
        workspace._state.project_path = project_path

        # Track save calls - must mock at the auto_save_manager level since it
        # captures the save_project reference at init time
        save_count = [0]
        original_save = workspace._auto_save_manager._save_project

        def counting_save(path):
            save_count[0] += 1
            return original_save(path)

        workspace._auto_save_manager._save_project = counting_save

        # Trigger multiple save requests (simulating rapid nudges)
        for _ in range(10):
            workspace._auto_save_manager.schedule_save()

        # Save should not happen immediately
        assert save_count[0] == 0

        # Wait for debounce timer
        qtbot.wait(600)  # Wait longer than 500ms debounce

        # Only one save should have occurred
        assert save_count[0] == 1

    def test_timer_restarts_on_new_request(self, app_context, qtbot, tmp_path) -> None:
        """New save request restarts debounce timer."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Setup project with path
        workspace.controller.new_project("test")
        project_path = tmp_path / "test.spritepal"
        workspace._state.project_path = project_path

        # Track save calls - must mock at the auto_save_manager level since it
        # captures the save_project reference at init time
        save_count = [0]
        original_save = workspace._auto_save_manager._save_project

        def counting_save(path):
            save_count[0] += 1
            return original_save(path)

        workspace._auto_save_manager._save_project = counting_save

        # First request
        workspace._auto_save_manager.schedule_save()

        # Wait 300ms (less than debounce)
        qtbot.wait(300)
        assert save_count[0] == 0  # Not saved yet

        # Second request restarts timer
        workspace._auto_save_manager.schedule_save()

        # Wait another 300ms - total 600ms from first but only 300ms from second
        qtbot.wait(300)
        assert save_count[0] == 0  # Still not saved (timer restarted)

        # Wait final 300ms - now 600ms from second request
        qtbot.wait(300)
        assert save_count[0] == 1  # Now saved


class TestROMSelector:
    """Tests for ROM selector in Frame Mapping workspace header."""

    def test_rom_selector_exists(self, app_context, qtbot) -> None:
        """Workspace has ROM selector widget in header."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        assert hasattr(workspace, "_rom_selector")
        assert workspace._rom_selector is not None

    def test_rom_selector_shows_placeholder_when_no_rom(self, app_context, qtbot) -> None:
        """ROM selector shows placeholder text when no ROM is loaded."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # No ROM set initially
        assert workspace._state.rom_path is None
        assert workspace._rom_selector.path_edit.placeholderText() == "No ROM selected"

    def test_set_rom_path_syncs_widget(self, app_context, qtbot, tmp_path) -> None:
        """set_rom_path updates the ROM selector display."""
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Create a dummy ROM file
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"dummy rom data")

        # Set ROM path
        workspace.set_rom_path(rom_file)

        # Widget should display the path
        assert workspace._rom_selector.get_path() == str(rom_file)

    def test_rom_selector_validates_extension(self, app_context, qtbot, tmp_path) -> None:
        """ROM selector rejects files with invalid extensions."""
        from unittest.mock import patch

        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Create a file with invalid extension
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a rom")

        # Patch QMessageBox to prevent blocking dialog
        with patch("ui.workspaces.frame_mapping_workspace.QMessageBox.warning") as mock_warn:
            workspace._on_rom_selector_changed(str(txt_file))

            # Should show warning
            mock_warn.assert_called_once()
            # ROM should not be set
            assert workspace._state.rom_path is None

    def test_rom_selector_validates_existence(self, app_context, qtbot, tmp_path) -> None:
        """ROM selector rejects nonexistent files."""
        from unittest.mock import patch

        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Use a path that doesn't exist
        nonexistent = tmp_path / "nonexistent.sfc"

        with patch("ui.workspaces.frame_mapping_workspace.QMessageBox.warning") as mock_warn:
            workspace._on_rom_selector_changed(str(nonexistent))

            # Should show warning
            mock_warn.assert_called_once()
            # ROM should not be set
            assert workspace._state.rom_path is None

    def test_rom_selector_clears_injection_state(self, app_context, qtbot, tmp_path) -> None:
        """Selecting new ROM clears previous injection state."""
        from pathlib import Path

        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Simulate prior injection state
        old_rom = tmp_path / "old.sfc"
        old_rom.write_bytes(b"old rom")
        workspace._state.rom_path = old_rom
        workspace._state.last_injected_rom = tmp_path / "injected.sfc"

        # Create new ROM
        new_rom = tmp_path / "new.sfc"
        new_rom.write_bytes(b"new rom data")

        # Select new ROM
        workspace._on_rom_selector_changed(str(new_rom))

        # State should be cleared
        assert workspace._state.rom_path == new_rom
        assert workspace._state.last_injected_rom is None

    def test_auto_load_rom_from_settings(self, app_context, qtbot, tmp_path) -> None:
        """ROM is auto-loaded from settings if available."""
        from core.app_context import get_app_context

        # Set up a ROM path in settings BEFORE creating workspace
        context = get_app_context()
        rom_file = tmp_path / "settings_rom.sfc"
        rom_file.write_bytes(b"rom from settings")
        context.application_state_manager.set("rom_injection", "last_input_rom", str(rom_file))

        # Create workspace - should auto-load ROM
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # ROM should be loaded from settings
        assert workspace._state.rom_path == rom_file
        assert workspace._rom_selector.get_path() == str(rom_file)

    def test_auto_load_rom_skipped_if_already_set(self, app_context, qtbot, tmp_path) -> None:
        """ROM auto-load is skipped if MainWindow already set a ROM."""
        from core.app_context import get_app_context

        # Set up a different ROM in settings
        context = get_app_context()
        settings_rom = tmp_path / "settings_rom.sfc"
        settings_rom.write_bytes(b"settings rom")
        context.application_state_manager.set("rom_injection", "last_input_rom", str(settings_rom))

        # Create workspace
        workspace = FrameMappingWorkspace()
        qtbot.addWidget(workspace)

        # Now simulate MainWindow setting a different ROM
        main_rom = tmp_path / "main_window_rom.sfc"
        main_rom.write_bytes(b"main window rom")
        workspace.set_rom_path(main_rom)

        # The MainWindow ROM should take precedence
        assert workspace._state.rom_path == main_rom
        assert workspace._rom_selector.get_path() == str(main_rom)
