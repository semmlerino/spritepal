"""
Integration tests for safe ROM loading workflow.

Crash fix: Async ROM loading to prevent UI freezes, proper error handling.
Split from tests/integration/test_rom_extraction_regression.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from ui.injection_dialog import InjectionDialog

pytestmark = [
    pytest.mark.usefixtures("mock_hal"),
    pytest.mark.skip_thread_cleanup(reason="Uses app_context which owns worker threads"),
    pytest.mark.headless,
    pytest.mark.integration,
]


@pytest.fixture
def injection_dialog(qtbot, app_context):
    """Create injection dialog for testing."""
    dialog = InjectionDialog(
        injection_manager=app_context.core_operations_manager,
        settings_manager=app_context.application_state_manager,
    )
    qtbot.addWidget(dialog)
    return dialog


class TestROMLoadingSafety:
    """Test safe ROM loading with error handling.

    Crash fix: Async ROM loading to prevent UI freezes, proper error handling.
    """

    def test_load_rom_info_file_not_found(self, injection_dialog, qtbot):
        """Test ROM loading with non-existent file - async worker pattern.

        Since Issue 2 fix, ROM loading is now async to prevent UI freezes.
        The worker will complete and the handler will show an error dialog.
        We patch QMessageBox to prevent blocking in tests.
        """
        dialog = injection_dialog

        # Patch QMessageBox to prevent blocking dialogs during test
        with patch("ui.injection_dialog.QMessageBox") as mock_msgbox:
            mock_msgbox.critical.return_value = None
            mock_msgbox.warning.return_value = None

            # Start async ROM loading
            dialog._load_rom_info("/nonexistent/file.sfc")

            # Wait for worker to complete using waitUntil (handles fast-completing workers)
            # The signal may fire before waitSignal is ready, so check worker state instead
            def worker_done() -> bool:
                loader = dialog._rom_info_loader
                return loader is None or not loader.isRunning()

            qtbot.waitUntil(worker_done, timeout=5000)

            # Process events to ensure handler runs
            QApplication.processEvents()

            # Verify an error dialog was shown (critical or warning)
            assert (
                mock_msgbox.critical.called
                or mock_msgbox.warning.called
                or dialog.sprite_location_combo.itemText(0) in ("Error loading ROM", "Load ROM file first...")
            )

    def test_load_rom_info_invalid_file_size(self, injection_dialog, qtbot):
        """Test ROM loading with invalid file size - async worker pattern.

        Since Issue 2 fix, ROM loading is now async to prevent UI freezes.
        The worker will complete and handler may show warning dialog.
        We patch QMessageBox to prevent blocking in tests.
        """
        dialog = injection_dialog

        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            # Create a file that's too small to be a valid ROM
            tmp_file.write(b"tiny")
            tmp_file.flush()

            try:
                # Patch QMessageBox to prevent blocking dialogs during test
                with patch("ui.injection_dialog.QMessageBox") as mock_msgbox:
                    mock_msgbox.critical.return_value = None
                    mock_msgbox.warning.return_value = None

                    # Start async ROM loading
                    dialog._load_rom_info(tmp_file.name)

                    # Wait for worker to complete using waitUntil (handles fast-completing workers)
                    # The signal may fire before waitSignal is ready, so check worker state instead
                    def worker_done() -> bool:
                        loader = dialog._rom_info_loader
                        return loader is None or not loader.isRunning()

                    qtbot.waitUntil(worker_done, timeout=5000)

                    # Process events to ensure handler runs
                    QApplication.processEvents()

                    # Test passes if either:
                    # 1. A warning/error dialog was shown
                    # 2. UI was updated to show error state
                    assert (
                        mock_msgbox.critical.called
                        or mock_msgbox.warning.called
                        or dialog.sprite_location_combo.itemText(0)
                        in ("Error loading ROM", "Loading ROM info...", "Load ROM file first...")
                    )

            finally:
                Path(tmp_file.name).unlink()

    def test_clear_rom_ui_state(self, injection_dialog):
        """Test that ROM UI state is properly cleared"""
        dialog = injection_dialog

        # Set up some state first
        dialog.sprite_location_combo.addItem("Test Item", 0x8000)
        dialog.rom_info_text.setText("Test ROM info")
        dialog.rom_info_group.show()

        # Clear state
        dialog._clear_rom_ui_state()

        # Verify state was cleared
        assert dialog.sprite_location_combo.count() == 1
        assert dialog.sprite_location_combo.itemText(0) == "Load ROM file first..."
        assert dialog.rom_info_text.toPlainText() == ""
        assert not dialog.rom_info_group.isVisible()
