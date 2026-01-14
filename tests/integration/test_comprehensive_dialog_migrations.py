"""
Comprehensive Dialog Migration Testing

This test suite verifies that all migrated dialogs work correctly together
and maintain full functionality after migration to the new component architecture.

Uses app_context fixture from core_fixtures.py.
"""

from __future__ import annotations

import contextlib
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from PIL import Image

from core.app_context import get_app_context
from ui.components import DialogBase, SplitterDialog, TabbedDialog
from ui.dialogs.user_error_dialog import UserErrorDialog
from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.injection_dialog import InjectionDialog


def _create_injection_dialog(**kwargs) -> InjectionDialog:
    """Create InjectionDialog with injected dependencies."""
    context = get_app_context()
    return InjectionDialog(
        injection_manager=context.core_operations_manager,
        settings_manager=context.application_state_manager,
        **kwargs,
    )


# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]


class TestComprehensiveDialogMigrations:
    """Test all migrated dialogs work together correctly.

    Uses app_context fixture.
    """

    @pytest.fixture
    def test_sprite_image(self) -> Generator[str, None, None]:
        """Create a test sprite image for dialog testing"""
        test_image = Image.new("L", (128, 128), 0)
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        test_image.save(temp_file.name)
        temp_file.close()

        yield temp_file.name

        with contextlib.suppress(Exception):
            Path(temp_file.name).unlink()

    def test_all_dialogs_inherit_from_correct_base_classes(
        self, qtbot: Any, test_sprite_image: str, app_context: Any
    ) -> None:
        """Test that all migrated dialogs inherit from the correct component base classes"""
        # Test UserErrorDialog inherits from BaseDialog
        error_dialog = UserErrorDialog("Test error")
        qtbot.addWidget(error_dialog)
        assert isinstance(error_dialog, DialogBase)

        # Test InjectionDialog inherits from TabbedDialog
        injection_dialog = _create_injection_dialog()
        qtbot.addWidget(injection_dialog)
        assert isinstance(injection_dialog, TabbedDialog)
        assert isinstance(injection_dialog, DialogBase)  # TabbedDialog inherits from DialogBase

        # Test GridArrangementDialog inherits from SplitterDialog
        with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
            grid_dialog = GridArrangementDialog(test_sprite_image)
        qtbot.addWidget(grid_dialog)
        assert isinstance(grid_dialog, SplitterDialog)
        assert isinstance(grid_dialog, DialogBase)  # SplitterDialog inherits from DialogBase

        # Clean up
        for dialog in [error_dialog, injection_dialog, grid_dialog]:
            try:
                dialog.close()
            except Exception:
                pass

    def test_all_dialogs_have_consistent_component_features(
        self, qtbot: Any, test_sprite_image: str, app_context: Any
    ) -> None:
        """Test that all migrated dialogs have consistent component features"""
        dialogs = [
            UserErrorDialog("Test error"),
            _create_injection_dialog(),
        ]

        # Handle grid dialog with error patching
        with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
            dialogs.append(GridArrangementDialog(test_sprite_image))

        for dialog in dialogs:
            qtbot.addWidget(dialog)

            # All should inherit from BaseDialog and have these features
            assert hasattr(dialog, "main_layout")
            assert hasattr(dialog, "content_widget")
            assert hasattr(dialog, "button_box")

            # All should be modal
            assert dialog.isModal() is True

            # All should have proper titles
            assert dialog.windowTitle() != ""

        # Clean up
        for dialog in dialogs:
            try:
                dialog.close()
            except Exception:
                pass

    def test_dialog_button_integration_consistency(self, qtbot, test_sprite_image, app_context):
        """Test that all dialogs have consistent button integration"""
        # UserErrorDialog has custom OK button (creates button box manually)
        error_dialog = UserErrorDialog("Test error")
        qtbot.addWidget(error_dialog)
        # UserErrorDialog creates button box manually, doesn't expose it as attribute
        assert error_dialog.button_box is None  # BaseDialog was created with with_button_box=False

        # InjectionDialog has custom buttons
        injection_dialog = _create_injection_dialog()
        qtbot.addWidget(injection_dialog)
        assert injection_dialog.button_box is not None

        # GridArrangementDialog has Export button
        with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
            grid_dialog = GridArrangementDialog(test_sprite_image)
        qtbot.addWidget(grid_dialog)
        assert grid_dialog.button_box is not None
        assert hasattr(grid_dialog, "export_btn")

        # Clean up
        for dialog in [error_dialog, injection_dialog, grid_dialog]:
            try:
                dialog.close()
            except Exception:
                pass

    def test_dialog_status_bar_integration_consistency(self, qtbot, test_sprite_image, app_context):
        """Test that status bar integration is consistent across dialogs"""
        # Dialogs with status bars
        status_dialogs = []

        # Handle grid dialog with error patching
        with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
            status_dialogs.append(GridArrangementDialog(test_sprite_image))

        for dialog in status_dialogs:
            qtbot.addWidget(dialog)
            assert hasattr(dialog, "status_bar")
            assert dialog.status_bar is not None

            # Test status update functionality
            dialog.update_status("Test message")
            assert dialog.status_bar.currentMessage() == "Test message"

        # Clean up
        for dialog in status_dialogs:
            try:
                dialog.close()
            except Exception:
                pass

    def test_dialog_component_api_consistency(self, qtbot, app_context):
        """Test that component APIs are consistent across dialogs"""
        # Test InjectionDialog component usage
        injection_dialog = _create_injection_dialog()
        qtbot.addWidget(injection_dialog)

        # Should have HexOffsetInput components
        assert hasattr(injection_dialog, "vram_offset_input")
        assert hasattr(injection_dialog, "rom_offset_input")

        # Should have FileSelector components
        assert hasattr(injection_dialog, "sprite_file_selector")
        assert hasattr(injection_dialog, "input_vram_selector")

        # Test component API methods exist
        assert hasattr(injection_dialog.vram_offset_input, "get_value")
        assert hasattr(injection_dialog.vram_offset_input, "set_text")
        assert hasattr(injection_dialog.sprite_file_selector, "get_path")
        assert hasattr(injection_dialog.sprite_file_selector, "set_path")

        # Clean up
        injection_dialog.close()

    def test_dialog_layout_architecture_consistency(self, qtbot, test_sprite_image, app_context):
        """Test that layout architecture is consistent after migrations"""
        # Test TabbedDialog structure
        injection_dialog = _create_injection_dialog()
        qtbot.addWidget(injection_dialog)
        assert hasattr(injection_dialog, "tab_widget")
        assert injection_dialog.tab_widget.count() == 2  # VRAM and ROM tabs

        # Patch QMessageBox to prevent blocking dialogs during GridArrangementDialog initialization
        with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
            grid_dialog = GridArrangementDialog(test_sprite_image)
        qtbot.addWidget(grid_dialog)
        assert hasattr(grid_dialog, "main_splitter")
        assert grid_dialog.main_splitter.count() == 2  # Left and right panels

        # Clean up
        for dialog in [injection_dialog, grid_dialog]:
            try:
                dialog.close()
            except Exception:
                pass

    def test_dialog_signal_integration_preservation(self, qtbot, test_sprite_image, app_context):
        """Test that signal integration is preserved after migrations"""
        # Test GridArrangementDialog signals
        with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
            grid_dialog = GridArrangementDialog(test_sprite_image)
        qtbot.addWidget(grid_dialog)

        # Should have arrangement manager and grid view with signals
        assert hasattr(grid_dialog, "arrangement_manager")
        assert hasattr(grid_dialog, "grid_view")
        assert hasattr(grid_dialog.grid_view, "tile_clicked")

        # Clean up
        for dialog in [grid_dialog]:
            try:
                dialog.close()
            except Exception:
                pass

    def test_dialog_error_handling_consistency(self, qtbot, app_context):
        """Test that error handling is consistent across migrated dialogs"""
        # Test error dialog functionality
        error_dialog = UserErrorDialog("Test error", "Test details")
        qtbot.addWidget(error_dialog)

        # Should have proper error mapping
        memory_error_dialog = UserErrorDialog("memory error occurred")
        qtbot.addWidget(memory_error_dialog)
        assert memory_error_dialog.windowTitle() == "Memory Error"

        # Test error state handling in other dialogs
        # Patch QMessageBox to prevent blocking dialogs during GridArrangementDialog initialization
        with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
            grid_dialog = GridArrangementDialog("/non/existent/file.png")
        qtbot.addWidget(grid_dialog)

        # Should handle error gracefully and maintain structure
        assert isinstance(grid_dialog, SplitterDialog)
        assert grid_dialog.status_bar is not None

        # Clean up
        for dialog in [error_dialog, memory_error_dialog, grid_dialog]:
            try:
                dialog.close()
            except Exception:
                pass

    def test_dialog_memory_management_consistency(self, qtbot, test_sprite_image, app_context):
        """Test that memory management is consistent across dialogs"""
        # Only GridArrangementDialog has _cleanup_resources method
        with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
            grid_dialog = GridArrangementDialog(test_sprite_image)
        qtbot.addWidget(grid_dialog)

        # GridArrangementDialog should have cleanup method
        assert hasattr(grid_dialog, "_cleanup_resources")

        # Test cleanup doesn't crash
        try:
            grid_dialog._cleanup_resources()
        except Exception as e:
            pytest.fail(f"Cleanup failed for GridArrangementDialog: {e}")

        # Clean up
        for dialog in [grid_dialog]:
            try:
                dialog.close()
            except Exception:
                pass

    def test_dialog_component_isolation(self, qtbot, test_sprite_image, app_context):
        """Test that component changes don't affect other dialogs"""
        # Create multiple dialogs
        injection_dialog = _create_injection_dialog()

        with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
            grid_dialog = GridArrangementDialog(test_sprite_image)

        for dialog in [injection_dialog, grid_dialog]:
            qtbot.addWidget(dialog)

        # Modify one dialog's settings
        injection_dialog.vram_offset_input.set_text("0x8000")

        # Other dialogs should be unaffected
        assert grid_dialog.status_bar.currentMessage() != "Test message"

        # Each dialog should maintain its own component state
        assert injection_dialog.vram_offset_input.get_value() == 0x8000

        # Clean up
        for dialog in [injection_dialog, grid_dialog]:
            try:
                dialog.close()
            except Exception:
                pass


# App Context Integration Tests
class TestAppContextIntegration:
    """Test app context integration with dialog migrations.

    Uses app_context fixture.
    """

    @pytest.fixture
    def test_sprite_image_shared(self) -> Generator[str, None, None]:
        """Create a test sprite image for dialog testing"""
        test_image = Image.new("L", (128, 128), 0)
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        test_image.save(temp_file.name)
        temp_file.close()

        yield temp_file.name

        with contextlib.suppress(Exception):
            Path(temp_file.name).unlink()

    def test_injection_dialog_manager_access(self, qtbot, app_context):
        """Test that InjectionDialog can access managers through context."""
        injection_dialog = _create_injection_dialog()
        qtbot.addWidget(injection_dialog)

        # Verify dialog can access required managers
        operations_manager = app_context.core_operations_manager
        assert operations_manager is not None

        state_manager = app_context.application_state_manager
        assert state_manager is not None

        # Clean up
        injection_dialog.close()

    def test_dialog_context_isolation(self, qtbot, test_sprite_image_shared, app_context):
        """Test that dialogs can access managers through app context.

        AppContext provides access to the core operations and state managers.
        """
        # First dialog
        dialog1 = _create_injection_dialog()
        qtbot.addWidget(dialog1)

        # Verify dialog1 can access managers
        operations_manager1 = app_context.core_operations_manager
        assert operations_manager1 is not None

        dialog1.close()

        # Second dialog - uses same app_context
        dialog2 = _create_injection_dialog()
        qtbot.addWidget(dialog2)

        # Verify dialog2 can access managers
        operations_manager2 = app_context.core_operations_manager
        assert operations_manager2 is not None
        # Same instance as dialog1 used
        assert operations_manager2 is operations_manager1

        dialog2.close()

    def test_dialog_manager_state_persistence(self, qtbot, app_context):
        """Test that manager state persists within app context."""
        # Create first dialog and modify manager state
        dialog1 = _create_injection_dialog()
        qtbot.addWidget(dialog1)

        operations_manager = app_context.core_operations_manager
        operations_manager.test_value = "test_state"  # type: ignore[attr-defined]

        dialog1.close()

        # Create second dialog in same context
        dialog2 = _create_injection_dialog()
        qtbot.addWidget(dialog2)

        # Manager state should persist
        same_manager = app_context.core_operations_manager
        assert same_manager is operations_manager
        assert hasattr(same_manager, "test_value")
        assert same_manager.test_value == "test_state"  # type: ignore[attr-defined]

        dialog2.close()
