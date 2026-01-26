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
        """Injected controller is not deleted when workspace is deleted."""
        controller = FrameMappingController(parent=None)

        workspace = FrameMappingWorkspace(controller=controller)
        qtbot.addWidget(workspace)

        # Delete workspace
        workspace.deleteLater()
        qtbot.wait(50)

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
        workspace._palette_editors["frame1.png"] = mock_editor1
        workspace._palette_editors["frame2.png"] = mock_editor2

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
        assert len(workspace._palette_editors) == 0

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

        workspace._palette_editors["frame1.png"] = mock_editor

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

        # Track save calls
        save_count = [0]
        original_save = workspace._controller.save_project

        def counting_save(path):
            save_count[0] += 1
            return original_save(path)

        workspace._controller.save_project = counting_save

        # Trigger multiple save requests (simulating rapid nudges)
        for _ in range(10):
            workspace._auto_save_after_injection()

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

        save_count = [0]
        original_save = workspace._controller.save_project

        def counting_save(path):
            save_count[0] += 1
            return original_save(path)

        workspace._controller.save_project = counting_save

        # First request
        workspace._auto_save_after_injection()

        # Wait 300ms (less than debounce)
        qtbot.wait(300)
        assert save_count[0] == 0  # Not saved yet

        # Second request restarts timer
        workspace._auto_save_after_injection()

        # Wait another 300ms - total 600ms from first but only 300ms from second
        qtbot.wait(300)
        assert save_count[0] == 0  # Still not saved (timer restarted)

        # Wait final 300ms - now 600ms from second request
        qtbot.wait(300)
        assert save_count[0] == 1  # Now saved
