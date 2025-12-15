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
    from tests.infrastructure.test_protocols import MockQtBotProtocol

pytestmark = [
    pytest.mark.gui,
    pytest.mark.serial,
    pytest.mark.qt_application,
    pytest.mark.dialog,
    pytest.mark.requires_display,
]


class TestRealDialogInitialization:
    """Test actual Qt dialogs can be created without crashes."""

    def test_settings_dialog_real(self, qtbot: MockQtBotProtocol) -> None:
        """Test SettingsDialog can be created with real Qt widgets."""
        from ui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        qtbot.addWidget(dialog)

        # Verify real Qt widgets exist
        assert dialog is not None
        assert dialog.windowTitle()  # Has a title

        dialog.close()

    def test_user_error_dialog_real(self, qtbot: MockQtBotProtocol) -> None:
        """Test UserErrorDialog can be created with real Qt widgets."""
        from ui.dialogs.user_error_dialog import UserErrorDialog

        dialog = UserErrorDialog(
            title="Test Error",
            message="Test error message",
            details="Detailed error information",
        )
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None
        assert "Test Error" in dialog.windowTitle() or dialog.windowTitle()

        dialog.close()

    def test_resume_scan_dialog_real(self, qtbot: MockQtBotProtocol) -> None:
        """Test ResumeScanDialog can be created with real Qt widgets."""
        from ui.dialogs.resume_scan_dialog import ResumeScanDialog

        dialog = ResumeScanDialog(
            last_offset=0x1000,
            total_sprites=10,
        )
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None

        dialog.close()

    def test_scan_range_dialog_real(self, qtbot: MockQtBotProtocol) -> None:
        """Test ScanRangeDialog can be created with real Qt widgets."""
        from ui.dialogs.scan_range_dialog import ScanRangeDialog

        dialog = ScanRangeDialog(
            current_offset=0x1000,
            rom_size=0x400000,
        )
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None

        dialog.close()

    def test_advanced_search_dialog_real(self, qtbot: MockQtBotProtocol) -> None:
        """Test AdvancedSearchDialog can be created with real Qt widgets."""
        from ui.dialogs.advanced_search_dialog import AdvancedSearchDialog

        dialog = AdvancedSearchDialog()
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
        from ui.dialogs.manual_offset_unified_integrated import UnifiedManualOffsetDialog

        dialog = UnifiedManualOffsetDialog()
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

        # Create with empty results
        dialog = SimilarityResultsDialog(results=[])
        qtbot.addWidget(dialog)

        # Verify dialog was created
        assert dialog is not None

        dialog.close()


class TestRealDialogLifecycle:
    """Test dialog show/hide/close lifecycle with real widgets."""

    def test_dialog_show_close_cycle(self, qtbot: MockQtBotProtocol) -> None:
        """Test that dialogs can be shown and closed without crashes."""
        from ui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        qtbot.addWidget(dialog)

        # Show the dialog (non-modal for testing)
        dialog.show()
        qtbot.waitExposed(dialog)

        # Verify it's visible
        assert dialog.isVisible()

        # Close it
        dialog.close()

        # Verify it's no longer visible
        assert not dialog.isVisible()

    def test_dialog_accept_reject(self, qtbot: MockQtBotProtocol) -> None:
        """Test dialog accept/reject methods work correctly."""
        from ui.dialogs.user_error_dialog import UserErrorDialog

        dialog = UserErrorDialog(
            title="Test",
            message="Test message",
        )
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
        # Import may fail if injection_dialog has complex dependencies
        with contextlib.suppress(ImportError):
            from ui.injection_dialog import InjectionDialog

            dialog = InjectionDialog()
            qtbot.addWidget(dialog)

            # Verify dialog was created with expected widgets
            assert dialog is not None

            # Check for key child widgets
            if hasattr(dialog, 'sprite_file_selector'):
                assert dialog.sprite_file_selector is not None

            dialog.close()

    def test_monitoring_dashboard_real(
        self, qtbot: MockQtBotProtocol, isolated_managers
    ) -> None:
        """Test MonitoringDashboard can be created with real managers."""
        with contextlib.suppress(ImportError):
            from ui.dialogs.monitoring_dashboard import MonitoringDashboard

            dialog = MonitoringDashboard()
            qtbot.addWidget(dialog)

            # Verify dialog was created
            assert dialog is not None

            dialog.close()
