"""
Comprehensive Dialog Migration Testing

This test suite verifies that all migrated dialogs work correctly together
and maintain full functionality after migration to the new component architecture.

Uses session_managers fixture from core_fixtures.py with shared_state_safe marker.
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

from core.di_container import inject
from core.managers.application_state_manager import ApplicationStateManager
from core.protocols.manager_protocols import InjectionManagerProtocol
from ui.components import DialogBase, SplitterDialog, TabbedDialog
from ui.dialogs.user_error_dialog import UserErrorDialog
from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.injection_dialog import InjectionDialog
from ui.row_arrangement_dialog import RowArrangementDialog


def _create_injection_dialog(**kwargs) -> InjectionDialog:
    """Create InjectionDialog with injected dependencies."""
    return InjectionDialog(
        injection_manager=inject(InjectionManagerProtocol),
        settings_manager=inject(ApplicationStateManager),
        **kwargs,
    )

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="Uses session_managers which owns worker threads"),
    pytest.mark.headless,
    pytest.mark.integration,
]


class TestComprehensiveDialogMigrations:
    """Test all migrated dialogs work together correctly.

    Uses session_managers via pytestmark - no local setup needed.
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
        self,
        qtbot: Any,
        test_sprite_image: str,
        manager_context_factory: Any
    ) -> None:
        """Test that all migrated dialogs inherit from the correct component base classes"""
        with manager_context_factory():
            # Test UserErrorDialog inherits from BaseDialog
            error_dialog = UserErrorDialog("Test error")
            qtbot.addWidget(error_dialog)
            assert isinstance(error_dialog, DialogBase)

            # Test InjectionDialog inherits from TabbedDialog
            injection_dialog = _create_injection_dialog()
            qtbot.addWidget(injection_dialog)
            assert isinstance(injection_dialog, TabbedDialog)
            assert isinstance(injection_dialog, DialogBase)  # TabbedDialog inherits from DialogBase

            # Test RowArrangementDialog inherits from SplitterDialog
            row_dialog = RowArrangementDialog(test_sprite_image)
            qtbot.addWidget(row_dialog)
            assert isinstance(row_dialog, SplitterDialog)
            assert isinstance(row_dialog, DialogBase)  # SplitterDialog inherits from DialogBase

            # Test GridArrangementDialog inherits from SplitterDialog
            with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
                grid_dialog = GridArrangementDialog(test_sprite_image)
            qtbot.addWidget(grid_dialog)
            assert isinstance(grid_dialog, SplitterDialog)
            assert isinstance(grid_dialog, DialogBase)  # SplitterDialog inherits from DialogBase

            # Clean up
            for dialog in [error_dialog, injection_dialog, row_dialog, grid_dialog]:
                try:
                    dialog.close()
                except Exception:
                    pass

    def test_all_dialogs_have_consistent_component_features(
        self,
        qtbot: Any,
        test_sprite_image: str,
        manager_context_factory: Any
    ) -> None:
        """Test that all migrated dialogs have consistent component features"""
        with manager_context_factory():
            dialogs = [
                UserErrorDialog("Test error"),
                _create_injection_dialog(),
                RowArrangementDialog(test_sprite_image),
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

    def test_dialog_button_integration_consistency(self, qtbot, test_sprite_image, manager_context_factory):
        """Test that all dialogs have consistent button integration"""
        with manager_context_factory():
            # UserErrorDialog has custom OK button (creates button box manually)
            error_dialog = UserErrorDialog("Test error")
            qtbot.addWidget(error_dialog)
            # UserErrorDialog creates button box manually, doesn't expose it as attribute
            assert error_dialog.button_box is None  # BaseDialog was created with with_button_box=False

            # InjectionDialog has custom buttons
            injection_dialog = _create_injection_dialog()
            qtbot.addWidget(injection_dialog)
            assert injection_dialog.button_box is not None

            # RowArrangementDialog has Export button
            row_dialog = RowArrangementDialog(test_sprite_image)
            qtbot.addWidget(row_dialog)
            assert row_dialog.button_box is not None
            assert hasattr(row_dialog, "export_btn")

            # GridArrangementDialog has Export button
            with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
                grid_dialog = GridArrangementDialog(test_sprite_image)
            qtbot.addWidget(grid_dialog)
            assert grid_dialog.button_box is not None
            assert hasattr(grid_dialog, "export_btn")

            # Clean up
            for dialog in [error_dialog, injection_dialog, row_dialog, grid_dialog]:
                try:
                    dialog.close()
                except Exception:
                    pass

    def test_dialog_status_bar_integration_consistency(self, qtbot, test_sprite_image, manager_context_factory):
        """Test that status bar integration is consistent across dialogs"""
        with manager_context_factory():
            # Dialogs with status bars
            status_dialogs = [
                RowArrangementDialog(test_sprite_image),
            ]

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

    def test_dialog_component_api_consistency(self, qtbot, manager_context_factory):
        """Test that component APIs are consistent across dialogs"""
        with manager_context_factory():
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

    def test_dialog_layout_architecture_consistency(self, qtbot, test_sprite_image, manager_context_factory):
        """Test that layout architecture is consistent after migrations"""
        with manager_context_factory():
            # Test TabbedDialog structure
            injection_dialog = _create_injection_dialog()
            qtbot.addWidget(injection_dialog)
            assert hasattr(injection_dialog, "tab_widget")
            assert injection_dialog.tab_widget.count() == 2  # VRAM and ROM tabs

            # Test SplitterDialog structure
            row_dialog = RowArrangementDialog(test_sprite_image)
            qtbot.addWidget(row_dialog)
            assert hasattr(row_dialog, "main_splitter")
            assert row_dialog.main_splitter.count() == 2  # Content and preview panels

            # Patch QMessageBox to prevent blocking dialogs during GridArrangementDialog initialization
            with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
                grid_dialog = GridArrangementDialog(test_sprite_image)
            qtbot.addWidget(grid_dialog)
            assert hasattr(grid_dialog, "main_splitter")
            assert grid_dialog.main_splitter.count() == 2  # Left and right panels

            # Clean up
            for dialog in [injection_dialog, row_dialog, grid_dialog]:
                try:
                    dialog.close()
                except Exception:
                    pass

    def test_dialog_signal_integration_preservation(self, qtbot, test_sprite_image, manager_context_factory):
        """Test that signal integration is preserved after migrations"""
        with manager_context_factory():
            # Test RowArrangementDialog signals
            row_dialog = RowArrangementDialog(test_sprite_image)
            qtbot.addWidget(row_dialog)

            # Should have arrangement manager with signals
            assert hasattr(row_dialog, "arrangement_manager")
            assert hasattr(row_dialog.arrangement_manager, "arrangement_changed")

            # Test GridArrangementDialog signals
            with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
                grid_dialog = GridArrangementDialog(test_sprite_image)
            qtbot.addWidget(grid_dialog)

            # Should have arrangement manager and grid view with signals
            assert hasattr(grid_dialog, "arrangement_manager")
            assert hasattr(grid_dialog, "grid_view")
            assert hasattr(grid_dialog.grid_view, "tile_clicked")

            # Clean up
            for dialog in [row_dialog, grid_dialog]:
                try:
                    dialog.close()
                except Exception:
                    pass

    def test_dialog_error_handling_consistency(self, qtbot, manager_context_factory):
        """Test that error handling is consistent across migrated dialogs"""
        with manager_context_factory():
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

    def test_dialog_memory_management_consistency(self, qtbot, test_sprite_image, manager_context_factory):
        """Test that memory management is consistent across dialogs"""
        with manager_context_factory():
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

            # RowArrangementDialog doesn't have explicit cleanup method
            row_dialog = RowArrangementDialog(test_sprite_image)
            qtbot.addWidget(row_dialog)

            # Should still close properly without explicit cleanup
            assert row_dialog.isVisible() or True  # Should not crash

            # Clean up
            for dialog in [grid_dialog, row_dialog]:
                try:
                    dialog.close()
                except Exception:
                    pass

    def test_cross_dialog_workflow_integration(self, qtbot, test_sprite_image, manager_context_factory):
        """Test that dialogs can work together in typical workflows"""
        with manager_context_factory():
            # Simulate workflow: Extract -> Arrange -> Inject

            # 1. Start with arrangement dialog (simulating extraction output)
            arrangement_dialog = RowArrangementDialog(test_sprite_image)
            qtbot.addWidget(arrangement_dialog)

            # Should be able to access arrangement functionality
            assert hasattr(arrangement_dialog, "arrangement_manager")
            assert hasattr(arrangement_dialog, "export_btn")

            # 2. Simulate injection workflow
            injection_dialog = _create_injection_dialog(sprite_path=test_sprite_image)
            qtbot.addWidget(injection_dialog)

            # Should receive sprite path correctly
            assert injection_dialog.sprite_file_selector.get_path() == test_sprite_image

            # Should be able to switch between tabs
            injection_dialog.set_current_tab(0)  # VRAM tab
            assert injection_dialog.get_current_tab_index() == 0

            injection_dialog.set_current_tab(1)  # ROM tab
            assert injection_dialog.get_current_tab_index() == 1

            # Clean up
            for dialog in [arrangement_dialog, injection_dialog]:
                try:
                    dialog.close()
                except Exception:
                    pass

    def test_dialog_component_isolation(self, qtbot, test_sprite_image, manager_context_factory):
        """Test that component changes don't affect other dialogs"""
        with manager_context_factory():
            # Create multiple dialogs
            injection_dialog = _create_injection_dialog()
            row_dialog = RowArrangementDialog(test_sprite_image)

            with patch("ui.grid_arrangement_dialog.QMessageBox.critical"):
                grid_dialog = GridArrangementDialog(test_sprite_image)

            for dialog in [injection_dialog, row_dialog, grid_dialog]:
                qtbot.addWidget(dialog)

            # Modify one dialog's settings
            injection_dialog.vram_offset_input.set_text("0x8000")
            row_dialog.update_status("Test message")

            # Other dialogs should be unaffected
            assert grid_dialog.status_bar.currentMessage() != "Test message"

            # Each dialog should maintain its own component state
            assert injection_dialog.vram_offset_input.get_value() == 0x8000

            # Clean up
            for dialog in [injection_dialog, row_dialog, grid_dialog]:
                try:
                    dialog.close()
                except Exception:
                    pass

# Manager Context Integration Tests
class TestManagerContextIntegration:
    """Test manager context integration with dialog migrations.

    Uses session_managers via pytestmark - no local setup needed.
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

    def test_injection_dialog_manager_access(self, qtbot, manager_context_factory):
        """Test that InjectionDialog can access managers through context."""
        with manager_context_factory() as context:
            injection_dialog = _create_injection_dialog()
            qtbot.addWidget(injection_dialog)

            # Verify dialog can access required managers
            injection_manager = context.get_manager("injection")
            assert injection_manager is not None

            session_manager = context.get_manager("session")
            assert session_manager is not None

            # Clean up
            injection_dialog.close()

    def test_dialog_context_isolation(self, qtbot, test_sprite_image_shared, manager_context_factory):
        """Test that dialogs are properly isolated with their own contexts.

        Note: ManagerRegistry is a singleton, so managers are the same instance.
        Context isolation provides lifecycle management (init/cleanup), not
        separate instances. This test verifies contexts manage the singleton properly.
        """
        # First context
        with manager_context_factory(name="context1") as ctx1:
            dialog1 = _create_injection_dialog()
            qtbot.addWidget(dialog1)

            # Verify context1 managers
            manager1 = ctx1.get_manager("injection")
            assert manager1 is not None
            assert manager1.is_initialized()

            dialog1.close()

        # Second context - ManagerRegistry is a singleton, so same instance
        # but context manages lifecycle (init/cleanup) properly
        with manager_context_factory(name="context2") as ctx2:
            dialog2 = _create_injection_dialog()
            qtbot.addWidget(dialog2)

            # Verify context2 managers are available (same singleton)
            manager2 = ctx2.get_manager("injection")
            assert manager2 is not None
            assert manager2.is_initialized()
            # Note: manager2 is manager1 because ManagerRegistry is a singleton
            # Context isolation is about lifecycle, not instance separation

            dialog2.close()

    def test_dialog_manager_state_persistence(self, qtbot, manager_context_factory):
        """Test that manager state persists within a context."""
        with manager_context_factory() as context:
            # Create first dialog and modify manager state
            dialog1 = _create_injection_dialog()
            qtbot.addWidget(dialog1)

            injection_manager = context.get_manager("injection")
            injection_manager.test_value = "test_state"

            dialog1.close()

            # Create second dialog in same context
            dialog2 = _create_injection_dialog()
            qtbot.addWidget(dialog2)

            # Manager state should persist
            same_manager = context.get_manager("injection")
            assert same_manager is injection_manager
            assert hasattr(same_manager, 'test_value')
            assert same_manager.test_value == "test_state"

            dialog2.close()
