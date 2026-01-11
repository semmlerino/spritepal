"""Regression test for processEvents() availability in offscreen mode.

This test verifies that processEvents() is called in offscreen mode.
Previously, IS_HEADLESS incorrectly treated offscreen as "no Qt",
causing processEvents() to be skipped in fixture cleanup.

The fix ensures that event processing runs whenever a QApplication exists,
which is required for Qt cleanup mechanisms (deleteLater, signal queuing, etc).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget


class TestProcessEventsInOffscreen:
    """Verify processEvents() works in offscreen mode.

    Regression: IS_HEADLESS was True for offscreen mode, causing fixture
    cleanup to skip processEvents(). This prevented Qt cleanup mechanisms
    from running at all in CI environments.
    """

    def test_qapplication_exists_in_offscreen(self, qtbot: object) -> None:
        """QApplication should exist and be usable in offscreen mode."""
        app = QApplication.instance()
        assert app is not None, "QApplication should exist in offscreen mode"

    def test_process_events_is_callable(self, qtbot: object) -> None:
        """processEvents() should be callable without error in offscreen mode."""
        app = QApplication.instance()
        assert app is not None

        # This should not raise - the fix ensures processEvents is called
        app.processEvents()

    def test_can_create_and_schedule_deletion(self, qtbot: object) -> None:
        """Can create Qt objects and schedule them for deletion."""
        app = QApplication.instance()
        assert app is not None

        # Create objects and schedule deletion (should not crash)
        obj = QObject()
        widget = QWidget()

        obj.deleteLater()
        widget.deleteLater()

        # Process events - ensures deletion can be processed
        app.processEvents()

    def test_signals_can_be_queued_and_processed(self, qtbot: object) -> None:
        """Queued signal connections should work in offscreen mode."""

        class SignalEmitter(QObject):
            test_signal = Signal(int)

        emitter = SignalEmitter()
        received_values: list[int] = []

        def on_signal(value: int) -> None:
            received_values.append(value)

        # Use queued connection (requires event processing)
        from PySide6.QtCore import Qt

        emitter.test_signal.connect(on_signal, Qt.ConnectionType.QueuedConnection)

        # Emit signal - won't be delivered until processEvents
        emitter.test_signal.emit(42)

        # Before processing, signal shouldn't have been delivered
        assert len(received_values) == 0, "Queued signal delivered before processEvents"

        # Process events to deliver the queued signal
        app = QApplication.instance()
        assert app is not None
        app.processEvents()

        # Now the signal should have been delivered
        assert received_values == [42], (
            f"Queued signal not delivered after processEvents. Got {received_values}. "
            "This indicates processEvents() is not working in offscreen mode."
        )


class TestEnvironmentDetection:
    """Verify environment detection distinguishes offscreen from headless."""

    def test_offscreen_is_not_headless(self) -> None:
        """Offscreen mode should NOT be considered headless.

        Headless = no Qt at all
        Offscreen = Qt works, just no physical display
        """
        from tests.infrastructure.environment_detection import get_environment_info

        info = get_environment_info()

        # In test environment with QT_QPA_PLATFORM=offscreen
        if info.is_offscreen:
            # Offscreen mode means Qt is available (not headless)
            assert not info.is_headless, (
                "Offscreen mode incorrectly treated as headless. "
                "This would cause processEvents() to be skipped in fixture cleanup."
            )

    def test_qt_is_available_in_offscreen(self) -> None:
        """Qt should be fully functional in offscreen mode."""
        from tests.infrastructure.environment_detection import get_environment_info

        info = get_environment_info()

        if info.is_offscreen:
            assert info.pyside6_available, "PySide6 should be available in offscreen mode"
            assert QApplication.instance() is not None, "QApplication should exist"
