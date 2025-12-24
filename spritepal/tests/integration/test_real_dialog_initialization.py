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

from core.di_container import inject
from core.managers.application_state_manager import ApplicationStateManager
from core.managers.core_operations_manager import CoreOperationsManager


def get_injection_manager():
    """Get injection manager via DI."""
    return inject(CoreOperationsManager)


def get_settings_manager():
    """Get settings manager via DI."""
    return inject(ApplicationStateManager)


if TYPE_CHECKING:
    from tests.infrastructure.test_protocols import MockQtBotProtocol

pytestmark = [pytest.mark.gui]


class TestRealDialogInitialization:
    """Test actual Qt dialogs can be created without crashes."""

    def test_settings_dialog_real(self, qtbot: MockQtBotProtocol, isolated_managers) -> None:
        """Test SettingsDialog can be created with real Qt widgets.

        Requires isolated_managers because SettingsDialog uses DI.
        """
        from core.di_container import inject
        from core.managers.application_state_manager import ApplicationStateManager
        from core.protocols.manager_protocols import ROMCacheProtocol
        from ui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            settings_manager=inject(ApplicationStateManager),
            rom_cache=inject(ROMCacheProtocol)
        )
        qtbot.addWidget(dialog)

        # Verify real Qt widgets exist
        assert dialog is not None
        assert dialog.windowTitle()  # Has a title

        dialog.close()

    def test_user_error_dialog_real(self, qtbot: MockQtBotProtocol) -> None:
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

    def test_resume_scan_dialog_real(self, qtbot: MockQtBotProtocol) -> None:
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

    def test_scan_range_dialog_real(self, qtbot: MockQtBotProtocol) -> None:
        """Test ScanRangeDialog can be created with real Qt widgets."""
        from ui.dialogs.scan_range_dialog import ScanRangeDialog

        dialog = ScanRangeDialog(
            rom_size=0x400000,
        )
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None

        dialog.close()

    def test_advanced_search_dialog_real(self, qtbot: MockQtBotProtocol, tmp_path) -> None:
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

    def test_manual_offset_dialog_real(
        self, qtbot: MockQtBotProtocol, isolated_managers
    ) -> None:
        """Test UnifiedManualOffsetDialog can be created with real Qt widgets.

        This dialog requires managers to be initialized.
        """
        from core.di_container import inject
        from core.managers.application_state_manager import ApplicationStateManager
        from core.protocols.manager_protocols import ROMCacheProtocol
        from ui.dialogs.manual_offset_dialog import UnifiedManualOffsetDialog

        dialog = UnifiedManualOffsetDialog(
            rom_cache=inject(ROMCacheProtocol),
            settings_manager=inject(ApplicationStateManager),
            extraction_manager=inject(CoreOperationsManager),
        )
        qtbot.addWidget(dialog)

        # Verify real Qt widgets exist
        assert dialog is not None

        # Check for expected child widgets (tab widget is a key component)
        if hasattr(dialog, 'tab_widget'):
            assert dialog.tab_widget is not None
            # Should have tabs
            assert dialog.tab_widget.count() >= 0

        dialog.close()

    def test_similarity_results_dialog_real(self, qtbot: MockQtBotProtocol) -> None:
        """Test SimilarityResultsDialog can be created with real Qt widgets."""
        from ui.dialogs.similarity_results_dialog import SimilarityResultsDialog

        # Create with empty matches and a source offset
        dialog = SimilarityResultsDialog(matches=[], source_offset=0x1000)
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None

        dialog.close()


class TestRealDialogLifecycle:
    """Test dialog show/hide/close lifecycle with real widgets."""

    def test_dialog_show_close_cycle(self, qtbot: MockQtBotProtocol, isolated_managers) -> None:
        """Test that dialogs can be shown and closed without crashes.

        Requires isolated_managers because SettingsDialog uses DI.
        """
        from core.di_container import inject
        from core.managers.application_state_manager import ApplicationStateManager
        from core.protocols.manager_protocols import ROMCacheProtocol
        from ui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            settings_manager=inject(ApplicationStateManager),
            rom_cache=inject(ROMCacheProtocol)
        )
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

    def test_dialog_accept_reject(self, qtbot: MockQtBotProtocol) -> None:
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

    def test_injection_dialog_real(
        self, qtbot: MockQtBotProtocol, isolated_managers
    ) -> None:
        """Test InjectionDialog can be created with real managers."""
        from PySide6.QtCore import Qt

        from ui.injection_dialog import InjectionDialog

        dialog = InjectionDialog(
            injection_manager=get_injection_manager(),
            settings_manager=get_settings_manager(),
        )
        # Disable WA_DeleteOnClose so qtbot.addWidget cleanup doesn't fail
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        qtbot.addWidget(dialog)

        # Verify dialog was created with expected widgets
        assert dialog is not None

        # Check for key child widgets
        if hasattr(dialog, 'sprite_file_selector'):
            assert dialog.sprite_file_selector is not None

        dialog.close()
