#!/usr/bin/env python3
"""Tests for unsaved changes indicator in ROM workflow.

These tests verify the [Modified] indicator in the SourceBar:
- Shows when sprite has unsaved edits (undo available)
- Hides when changes are saved or sprite is reloaded
"""

import numpy as np
import pytest

from tests.fixtures.timeouts import signal_timeout


class TestSourceBarModifiedIndicator:
    """Unit tests for SourceBar.set_modified() method."""

    def test_set_modified_adds_indicator(self, qtbot):
        """Verify set_modified(True) adds [Modified] to info label."""
        from ui.sprite_editor.views.widgets.source_bar import SourceBar

        source_bar = SourceBar()
        qtbot.addWidget(source_bar)

        # Set some initial info
        source_bar.set_info("Kirby Super Star")

        # Enable modified indicator
        source_bar.set_modified(True)

        # Verify indicator is present
        assert "[Modified]" in source_bar.info_label.text()
        assert "Kirby Super Star" in source_bar.info_label.text()

    def test_set_modified_removes_indicator(self, qtbot):
        """Verify set_modified(False) removes [Modified] from info label."""
        from ui.sprite_editor.views.widgets.source_bar import SourceBar

        source_bar = SourceBar()
        qtbot.addWidget(source_bar)

        # Set initial info and add indicator
        source_bar.set_info("Kirby Super Star")
        source_bar.set_modified(True)
        assert "[Modified]" in source_bar.info_label.text()

        # Remove indicator
        source_bar.set_modified(False)

        # Verify indicator is gone but info remains
        assert "[Modified]" not in source_bar.info_label.text()
        assert "Kirby Super Star" in source_bar.info_label.text()

    def test_set_modified_idempotent(self, qtbot):
        """Verify calling set_modified multiple times is safe."""
        from ui.sprite_editor.views.widgets.source_bar import SourceBar

        source_bar = SourceBar()
        qtbot.addWidget(source_bar)

        source_bar.set_info("Test ROM")

        # Call multiple times
        source_bar.set_modified(True)
        source_bar.set_modified(True)
        source_bar.set_modified(True)

        # Should only have one indicator
        text = source_bar.info_label.text()
        assert text.count("[Modified]") == 1

        # Remove multiple times
        source_bar.set_modified(False)
        source_bar.set_modified(False)

        # Should be gone
        assert "[Modified]" not in source_bar.info_label.text()


class TestROMWorkflowPageModifiedFacade:
    """Tests for ROMWorkflowPage.set_modified_indicator() facade."""

    def test_facade_delegates_to_source_bar(self, qtbot):
        """Verify facade method delegates to source bar."""
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        page = ROMWorkflowPage()
        qtbot.addWidget(page)

        # Set info first
        page.set_info("Test ROM")

        # Use facade to set modified
        page.set_modified_indicator(True)

        # Verify source bar was updated
        assert "[Modified]" in page.source_bar.info_label.text()

        # Clear via facade
        page.set_modified_indicator(False)
        assert "[Modified]" not in page.source_bar.info_label.text()


class TestUndoStateChangedConnection:
    """Integration tests for undoStateChanged signal connection."""

    def test_undo_state_changed_updates_indicator(self, qtbot, app_context):
        """Verify undoStateChanged signal updates modified indicator."""
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        # Create components
        editing_ctrl = EditingController()
        rom_ctrl = ROMWorkflowController(None, editing_ctrl)
        view = ROMWorkflowPage()
        qtbot.addWidget(view)

        # Connect controller to view
        rom_ctrl.set_view(view)

        # Set info and state
        view.set_info("Test ROM")
        rom_ctrl.state = "edit"

        # Simulate edit by triggering undoStateChanged with can_undo=True
        editing_ctrl.undoStateChanged.emit(True, False)
        qtbot.wait(10)

        # Verify indicator shows
        assert "[Modified]" in view.source_bar.info_label.text()

        # Simulate save/clear by triggering undoStateChanged with can_undo=False
        editing_ctrl.undoStateChanged.emit(False, False)
        qtbot.wait(10)

        # Verify indicator cleared
        assert "[Modified]" not in view.source_bar.info_label.text()

    def test_indicator_only_shows_in_edit_state(self, qtbot, app_context):
        """Verify indicator only shows when in 'edit' state."""
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        editing_ctrl = EditingController()
        rom_ctrl = ROMWorkflowController(None, editing_ctrl)
        view = ROMWorkflowPage()
        qtbot.addWidget(view)

        rom_ctrl.set_view(view)
        view.set_info("Test ROM")

        # In preview state, should not show indicator
        rom_ctrl.state = "preview"
        editing_ctrl.undoStateChanged.emit(True, False)
        qtbot.wait(10)

        assert "[Modified]" not in view.source_bar.info_label.text()

        # Switch to edit state, should show
        rom_ctrl.state = "edit"
        editing_ctrl.undoStateChanged.emit(True, False)
        qtbot.wait(10)

        assert "[Modified]" in view.source_bar.info_label.text()

    def test_indicator_clears_on_undo_manager_clear(self, qtbot, app_context):
        """Verify clearing undo manager clears the indicator."""
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )
        from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

        editing_ctrl = EditingController()
        rom_ctrl = ROMWorkflowController(None, editing_ctrl)
        view = ROMWorkflowPage()
        qtbot.addWidget(view)

        rom_ctrl.set_view(view)
        view.set_info("Test ROM")
        rom_ctrl.state = "edit"

        # Add some undo history by directly recording a command
        from ui.sprite_editor.commands import DrawPixelCommand

        test_data = np.zeros((16, 16), dtype=np.uint8)
        editing_ctrl.load_image(test_data)

        # Directly record a command to create undo history
        cmd = DrawPixelCommand(x=0, y=0, old_color=0, new_color=1)
        editing_ctrl.undo_manager.record_command(cmd)

        # Verify we have undo available
        assert editing_ctrl.undo_manager.can_undo(), "Expected undo to be available after command"

        # Wait for signal when clearing undo history via public API
        with qtbot.waitSignal(editing_ctrl.undoStateChanged, timeout=signal_timeout()):
            editing_ctrl.clear_undo_history()

        # Indicator should be cleared
        assert "[Modified]" not in view.source_bar.info_label.text()
