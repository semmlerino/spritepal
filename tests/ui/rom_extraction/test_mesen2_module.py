"""
Tests for Mesen2Module.

Validates signal forwarding, widget connections, and lifecycle management.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock, PropertyMock, call

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

from core.mesen_integration.log_watcher import CapturedOffset
from tests.fixtures.timeouts import signal_timeout
from ui.rom_extraction.modules import Mesen2Module

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def mock_log_watcher(qapp: QObject) -> Mock:
    """Create a mock LogWatcher with Qt signals."""

    # Create a real QObject to host signals
    class MockLogWatcher(QObject):
        offset_discovered = Signal(object)
        watch_started = Signal()
        watch_stopped = Signal()
        error_occurred = Signal(str)

        def __init__(self) -> None:
            super().__init__()
            self.is_watching_value = False
            self.start_watching = Mock(return_value=True)
            self.stop_watching = Mock()
            self.load_persistent_clicks = Mock(return_value=[])

        @property
        def is_watching(self) -> bool:
            return self.is_watching_value

        @is_watching.setter
        def is_watching(self, value: bool) -> None:
            self.is_watching_value = value

    return MockLogWatcher()


@pytest.fixture
def mock_widget(qapp: QObject) -> Mock:
    """Create a mock MesenCapturesSection widget."""
    widget = Mock()
    widget.add_capture = Mock()
    widget.set_watching = Mock()
    widget.load_persistent = Mock()
    return widget


@pytest.fixture
def mesen2_module(mock_log_watcher: Mock, qapp: QObject) -> Mesen2Module:
    """Create a Mesen2Module with mock log watcher."""
    return Mesen2Module(log_watcher=mock_log_watcher)


class TestMesen2ModuleInit:
    """Test Mesen2Module initialization."""

    def test_init_stores_log_watcher(self, mock_log_watcher: Mock, qapp: QObject) -> None:
        """Module stores log watcher reference."""
        module = Mesen2Module(log_watcher=mock_log_watcher)
        assert module.log_watcher is mock_log_watcher

class TestMesen2ModuleProperties:
    """Test Mesen2Module properties."""

    def test_is_watching_delegates_to_log_watcher(self, mesen2_module: Mesen2Module, mock_log_watcher: Mock) -> None:
        """is_watching property delegates to log watcher."""
        mock_log_watcher.is_watching = False
        assert mesen2_module.is_watching is False

        mock_log_watcher.is_watching = True
        assert mesen2_module.is_watching is True


class TestMesen2ModuleLifecycle:
    """Test Mesen2Module lifecycle methods."""

    def test_start_watching(self, mesen2_module: Mesen2Module, mock_log_watcher: Mock) -> None:
        """start_watching delegates to log watcher."""
        result = mesen2_module.start_watching()
        assert result is True
        mock_log_watcher.start_watching.assert_called_once()

    def test_stop_watching(self, mesen2_module: Mesen2Module, mock_log_watcher: Mock) -> None:
        """stop_watching delegates to log watcher."""
        mesen2_module.stop_watching()
        mock_log_watcher.stop_watching.assert_called_once()

    def test_load_persistent_clicks(self, mesen2_module: Mesen2Module, mock_log_watcher: Mock) -> None:
        """load_persistent_clicks delegates to log watcher."""
        test_captures = [
            CapturedOffset(
                offset=0x100000,
                frame=1800,
                timestamp=datetime.now(UTC),
                raw_line="test line 1",
            ),
            CapturedOffset(
                offset=0x200000,
                frame=1900,
                timestamp=datetime.now(UTC),
                raw_line="test line 2",
            ),
        ]
        mock_log_watcher.load_persistent_clicks.return_value = test_captures

        result = mesen2_module.load_persistent_clicks()
        assert result == test_captures
        mock_log_watcher.load_persistent_clicks.assert_called_once()


class TestMesen2ModuleWidgetConnection:
    """Test Mesen2Module widget connection."""

    def test_connect_to_widget_wires_signals(
        self, mesen2_module: Mesen2Module, mock_log_watcher: Mock, mock_widget: Mock, qtbot: QtBot
    ) -> None:
        """connect_to_widget wires log_watcher signals to widget methods."""
        # Module not watching initially
        mock_log_watcher.is_watching = False

        mesen2_module.connect_to_widget(mock_widget)

        # Should start watching
        mock_log_watcher.start_watching.assert_called_once()

        # Emit offset_discovered - widget should receive it
        capture = CapturedOffset(
            offset=0x100000,
            frame=1800,
            timestamp=datetime.now(UTC),
            raw_line="test line",
        )
        mock_log_watcher.offset_discovered.emit(capture)
        qtbot.waitUntil(lambda: mock_widget.add_capture.called, timeout=signal_timeout())
        mock_widget.add_capture.assert_called_once_with(capture)

        # Emit watch_started - widget should receive it
        mock_log_watcher.watch_started.emit()
        qtbot.waitUntil(lambda: mock_widget.set_watching.call_count >= 1, timeout=signal_timeout())
        assert mock_widget.set_watching.call_count >= 1
        # Check that True was passed at some point
        calls = mock_widget.set_watching.call_args_list
        assert any(call_args[0][0] is True for call_args in calls)

        # Emit watch_stopped - widget should receive it
        initial_call_count = mock_widget.set_watching.call_count
        mock_log_watcher.watch_stopped.emit()
        qtbot.waitUntil(
            lambda: mock_widget.set_watching.call_count > initial_call_count,
            timeout=signal_timeout(),
        )
        # Check that False was passed
        calls = mock_widget.set_watching.call_args_list
        assert any(call_args[0][0] is False for call_args in calls)

    def test_connect_to_widget_loads_persistent_clicks(
        self, mesen2_module: Mesen2Module, mock_log_watcher: Mock, mock_widget: Mock
    ) -> None:
        """connect_to_widget loads persistent clicks if not watching."""
        test_captures = [
            CapturedOffset(
                offset=0x100000,
                frame=1800,
                timestamp=datetime.now(UTC),
                raw_line="test line",
            )
        ]
        mock_log_watcher.load_persistent_clicks.return_value = test_captures
        mock_log_watcher.is_watching = False

        mesen2_module.connect_to_widget(mock_widget)

        mock_log_watcher.load_persistent_clicks.assert_called_once()
        mock_widget.load_persistent.assert_called_once_with(test_captures)

    def test_connect_to_widget_skips_persistent_if_watching(
        self, mesen2_module: Mesen2Module, mock_log_watcher: Mock, mock_widget: Mock
    ) -> None:
        """connect_to_widget skips persistent loading if already watching."""
        mock_log_watcher.is_watching = True

        mesen2_module.connect_to_widget(mock_widget)

        # Should not call load_persistent_clicks
        mock_log_watcher.load_persistent_clicks.assert_not_called()
        mock_widget.load_persistent.assert_not_called()

        # Should set watching state
        mock_widget.set_watching.assert_called_with(True)

    def test_connect_to_widget_prevents_duplicate_connection(
        self, mesen2_module: Mesen2Module, mock_log_watcher: Mock, mock_widget: Mock
    ) -> None:
        """connect_to_widget prevents duplicate connections."""
        mock_log_watcher.is_watching = False

        mesen2_module.connect_to_widget(mock_widget)
        assert mock_log_watcher.start_watching.call_count == 1

        # Try connecting again
        mesen2_module.connect_to_widget(mock_widget)

        # Should not start watching again
        assert mock_log_watcher.start_watching.call_count == 1

    def test_disconnect_widget_removes_connections(
        self, mesen2_module: Mesen2Module, mock_log_watcher: Mock, mock_widget: Mock, qtbot: QtBot
    ) -> None:
        """disconnect_widget removes signal connections."""
        mock_log_watcher.is_watching = False
        mesen2_module.connect_to_widget(mock_widget)

        # Reset mock to clear previous calls
        mock_widget.reset_mock()

        # Disconnect
        mesen2_module.disconnect_widget(mock_widget)

        # Emit signal - widget should NOT receive it
        capture = CapturedOffset(
            offset=0x100000,
            frame=1800,
            timestamp=datetime.now(UTC),
            raw_line="test line",
        )
        mock_log_watcher.offset_discovered.emit(capture)
        # Process events but don't wait - widget shouldn't receive the signal
        QCoreApplication.processEvents()
        mock_widget.add_capture.assert_not_called()

    def test_disconnect_widget_handles_not_connected(self, mesen2_module: Mesen2Module, mock_widget: Mock) -> None:
        """disconnect_widget handles widget that was never connected."""
        # Should not raise exception
        mesen2_module.disconnect_widget(mock_widget)

    def cleanup_stops_watching(self, mesen2_module: Mesen2Module, mock_log_watcher: Mock) -> None:
        """cleanup stops watching and clears connected widgets."""
        mock_log_watcher.is_watching = True

        mesen2_module.cleanup()

        mock_log_watcher.stop_watching.assert_called_once()
        assert mesen2_module.get_connected_widget_count() == 0


class TestMesen2ModuleIntegration:
    """Integration tests for Mesen2Module."""

    def test_multiple_widgets_connection(
        self, mesen2_module: Mesen2Module, mock_log_watcher: Mock, qapp: QObject, qtbot: QtBot
    ) -> None:
        """Module can connect to multiple widgets."""
        widget1 = Mock()
        widget1.add_capture = Mock()
        widget1.set_watching = Mock()
        widget1.load_persistent = Mock()

        widget2 = Mock()
        widget2.add_capture = Mock()
        widget2.set_watching = Mock()
        widget2.load_persistent = Mock()

        mock_log_watcher.is_watching = False

        mesen2_module.connect_to_widget(widget1)
        mesen2_module.connect_to_widget(widget2)

        # Emit signal - both widgets should receive it
        capture = CapturedOffset(
            offset=0x100000,
            frame=1800,
            timestamp=datetime.now(UTC),
            raw_line="test line",
        )
        mock_log_watcher.offset_discovered.emit(capture)
        qtbot.waitUntil(
            lambda: widget1.add_capture.called and widget2.add_capture.called,
            timeout=signal_timeout(),
        )

        widget1.add_capture.assert_called_once_with(capture)
        widget2.add_capture.assert_called_once_with(capture)
