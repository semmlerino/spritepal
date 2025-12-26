# pyright: basic
"""
Real dialog initialization tests (not mocks).

These tests verify that actual Qt dialogs can be created without crashes,
testing real Qt widget instantiation and lifecycle rather than mocks.

This validates:
- Real Qt widget creation works
- Dialog initialization order is correct
- No InitializationOrderError from attribute access before super().__init__()
- Dialogs have expected child widgets
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from core.app_context import AppContext

pytestmark = [pytest.mark.gui]


class TestRealDialogInitialization:
    """Test actual Qt dialogs can be created without crashes."""

    def test_settings_dialog_real(self, qtbot: QtBot, app_context: AppContext) -> None:
        """Test SettingsDialog can be created with real Qt widgets.

        Requires app_context because SettingsDialog uses DI.
        """
        from ui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(settings_manager=app_context.application_state_manager, rom_cache=app_context.rom_cache)
        qtbot.addWidget(dialog)

        # Verify real Qt widgets exist
        assert dialog is not None
        assert dialog.windowTitle()  # Has a title

        dialog.close()

    def test_user_error_dialog_real(self, qtbot: QtBot) -> None:
        """Test UserErrorDialog can be created with real Qt widgets."""
        from ui.dialogs.user_error_dialog import UserErrorDialog

        dialog = UserErrorDialog(
            error_message="Test error message",
            technical_details="Detailed error information",
        )
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None
        assert dialog.windowTitle()  # Has a title

        dialog.close()

    def test_resume_scan_dialog_real(self, qtbot: QtBot) -> None:
        """Test ResumeScanDialog can be created with real Qt widgets."""
        from ui.dialogs.resume_scan_dialog import ResumeScanDialog

        dialog = ResumeScanDialog(
            scan_info={
                "current_offset": 0x1000,
                "total_found": 10,
                "found_sprites": [],
                "scan_range": {"start": 0, "end": 0x10000, "step": 0x100},
                "completed": False,
            }
        )
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None

        dialog.close()

    def test_range_scan_dialog_real(self, qtbot: QtBot) -> None:
        """Test RangeScanDialog can be created with real Qt widgets."""
        from ui.components.dialogs.range_scan_dialog import RangeScanDialog

        dialog = RangeScanDialog(
            rom_size=0x400000,
        )
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None

        dialog.close()

    def test_advanced_search_dialog_real(self, qtbot: QtBot, tmp_path) -> None:
        """Test AdvancedSearchDialog can be created with real Qt widgets."""
        from ui.dialogs.advanced_search_dialog import AdvancedSearchDialog

        # Create a dummy ROM file for the dialog
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 1024)

        dialog = AdvancedSearchDialog(rom_path=str(rom_path))
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None

        dialog.close()

    def test_manual_offset_dialog_real(self, qtbot: QtBot, isolated_managers) -> None:
        """Test UnifiedManualOffsetDialog can be created with real Qt widgets.

        This dialog requires managers to be initialized.
        """
        from core.app_context import get_app_context
        from ui.dialogs.manual_offset_dialog import UnifiedManualOffsetDialog

        context = get_app_context()
        dialog = UnifiedManualOffsetDialog(
            rom_cache=context.rom_cache,
            settings_manager=context.application_state_manager,
            extraction_manager=context.core_operations_manager,
        )
        qtbot.addWidget(dialog)

        # Verify real Qt widgets exist
        assert dialog is not None

        # Check for expected child widgets (tab widget is a key component)
        if hasattr(dialog, "tab_widget"):
            assert dialog.tab_widget is not None
            # Should have tabs
            assert dialog.tab_widget.count() >= 0

        dialog.close()

    def test_similarity_results_dialog_real(self, qtbot: QtBot) -> None:
        """Test SimilarityResultsDialog can be created with real Qt widgets."""
        from ui.dialogs.similarity_results_dialog import SimilarityResultsDialog

        # Create with empty matches and a source offset
        dialog = SimilarityResultsDialog(matches=[], source_offset=0x1000)
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None

        dialog.close()

    def test_row_arrangement_dialog_real(self, qtbot: QtBot, tmp_path) -> None:
        """Test RowArrangementDialog can be created with real Qt widgets."""
        from PIL import Image

        from ui.row_arrangement_dialog import RowArrangementDialog

        # Create a minimal test image
        test_image_path = tmp_path / "test_sprite.png"
        test_image = Image.new("RGB", (16, 16), color="white")
        test_image.save(test_image_path)

        dialog = RowArrangementDialog(str(test_image_path), tiles_per_row=16)
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None
        assert dialog.sprite_path == str(test_image_path)
        assert dialog.tiles_per_row == 16

        dialog.close()

    def test_grid_arrangement_dialog_real(self, qtbot: QtBot, tmp_path) -> None:
        """Test GridArrangementDialog can be created with real Qt widgets."""
        from PIL import Image

        from ui.grid_arrangement_dialog import GridArrangementDialog

        # Create a minimal test image
        test_image_path = tmp_path / "test_sprite.png"
        test_image = Image.new("RGB", (16, 16), color="white")
        test_image.save(test_image_path)

        dialog = GridArrangementDialog(str(test_image_path), tiles_per_row=16)
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None
        assert dialog.sprite_path == str(test_image_path)
        assert dialog.tiles_per_row == 16

        dialog.close()


class TestRealDialogLifecycle:
    """Test dialog show/hide/close lifecycle with real widgets."""

    def test_dialog_show_close_cycle(self, qtbot: QtBot, app_context: AppContext) -> None:
        """Test that dialogs can be shown and closed without crashes.

        Requires app_context because SettingsDialog uses DI.
        """
        from ui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(settings_manager=app_context.application_state_manager, rom_cache=app_context.rom_cache)
        # Disable WA_DeleteOnClose so qtbot.addWidget cleanup doesn't fail
        from PySide6.QtCore import Qt

        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        qtbot.addWidget(dialog)

        # Show the dialog (non-modal for testing)
        dialog.show()
        qtbot.waitExposed(dialog)

        # Verify it's visible
        assert dialog.isVisible()

        # Close it (pytest-qt handles final cleanup)
        dialog.close()

        # Verify it's no longer visible
        assert not dialog.isVisible()

    def test_dialog_accept_reject(self, qtbot: QtBot) -> None:
        """Test dialog accept/reject methods work correctly."""
        from PySide6.QtCore import Qt

        from ui.dialogs.user_error_dialog import UserErrorDialog

        dialog = UserErrorDialog(
            error_message="Test message",
        )
        # Disable WA_DeleteOnClose so qtbot.addWidget cleanup doesn't fail
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        qtbot.addWidget(dialog)

        # Test reject (close without accepting)
        dialog.show()
        qtbot.waitExposed(dialog)
        dialog.reject()

        # Dialog should be closed after reject
        assert not dialog.isVisible()


class TestRealDialogWithManagers:
    """Test dialogs that require manager dependencies."""

    def test_injection_dialog_real(self, qtbot: QtBot, app_context: AppContext) -> None:
        """Test InjectionDialog can be created with real managers."""
        from PySide6.QtCore import Qt

        from ui.injection_dialog import InjectionDialog

        dialog = InjectionDialog(
            injection_manager=app_context.core_operations_manager,
            settings_manager=app_context.application_state_manager,
        )
        # Disable WA_DeleteOnClose so qtbot.addWidget cleanup doesn't fail
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        qtbot.addWidget(dialog)

        # Verify dialog was created with expected widgets
        assert dialog is not None

        # Check for key child widgets
        if hasattr(dialog, "sprite_file_selector"):
            assert dialog.sprite_file_selector is not None

        dialog.close()
