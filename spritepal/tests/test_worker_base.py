# pyright: basic  # Less strict for test files
# pyright: reportPrivateUsage=false  # Allow testing private methods
# pyright: reportUnknownMemberType=warning  # Mock attributes are dynamic

from __future__ import annotations

"""
Unit tests for worker base classes.

Tests the BaseWorker and ManagedWorker classes to ensure proper signal
emission, cancellation/pause mechanisms, and error handling.
"""

from typing import TYPE_CHECKING
from unittest.mock import Mock

if TYPE_CHECKING:
    from tests.infrastructure.test_protocols import MockQtBotProtocol

import pytest
from PySide6.QtTest import QSignalSpy

from core.managers.base_manager import BaseManager
from core.workers.base import BaseWorker, ManagedWorker

# Serial execution required: QApplication management
pytestmark = [

    pytest.mark.serial,
    pytest.mark.qt_application,
    pytest.mark.headless,
    pytest.mark.requires_display,
    pytest.mark.signals_slots,
]

class TestBaseWorker:
    """Test the BaseWorker base class."""

    def test_worker_initialization(self, qtbot: MockQtBotProtocol) -> None:
        """Test worker initialization with proper default values."""

        class TestWorker(BaseWorker):
            def run(self) -> None:
                pass

        worker = TestWorker()
        qtbot.addWidget(worker)

        assert not worker.is_cancelled
        assert not worker.is_paused
        assert worker._operation_name == "TestWorker"

    def test_worker_cancellation(self, qtbot: MockQtBotProtocol) -> None:
        """Test worker cancellation mechanism."""

        class TestWorker(BaseWorker):
            def run(self):
                self.check_cancellation()

        worker = TestWorker()
        qtbot.addWidget(worker)

        # Test cancellation request
        worker.cancel()
        assert worker.is_cancelled

        # Test that check_cancellation raises InterruptedError
        with pytest.raises(InterruptedError, match="Operation was cancelled"):
            worker.check_cancellation()

    def test_worker_pause_resume(self, qtbot: MockQtBotProtocol) -> None:
        """Test worker pause and resume mechanism."""

        class TestWorker(BaseWorker):
            def __init__(self) -> None:
                super().__init__()
                self.wait_called = False

            def run(self) -> None:
                self.wait_if_paused()
                self.wait_called = True

        worker = TestWorker()
        qtbot.addWidget(worker)

        # Test pause request
        worker.pause()
        assert worker.is_paused

        # Test resume
        worker.resume()
        assert not worker.is_paused

    def test_progress_emission(self, qtbot: MockQtBotProtocol) -> None:
        """Test progress signal emission with proper clamping."""

        class TestWorker(BaseWorker):
            def run(self) -> None:
                pass

        worker = TestWorker()
        qtbot.addWidget(worker)

        progress_spy = QSignalSpy(worker.progress)

        # Test normal progress
        worker.emit_progress(50, "Half done")
        assert progress_spy.count() == 1
        assert progress_spy.at(0) == [50, "Half done"]

        # Test clamping - values below 0
        worker.emit_progress(-10, "Negative")
        assert progress_spy.at(progress_spy.count() - 1) == [0, "Negative"]

        # Test clamping - values above 100
        worker.emit_progress(150, "Over 100")
        assert progress_spy.at(progress_spy.count() - 1) == [100, "Over 100"]

    def test_error_emission(self, qtbot):
        """Test error signal emission."""

        class TestWorker(BaseWorker):
            def run(self) -> None:
                pass

        worker = TestWorker()
        qtbot.addWidget(worker)

        error_spy = QSignalSpy(worker.error)

        # Test error emission with message only
        worker.emit_error("Test error")
        assert error_spy.count() == 1
        assert error_spy.at(0)[0] == "Test error"
        assert isinstance(error_spy.at(0)[1], Exception)

        # Test error emission with custom exception
        custom_exception = ValueError("Custom error")
        worker.emit_error("Custom error message", custom_exception)
        assert error_spy.at(error_spy.count() - 1)[0] == "Custom error message"
        assert error_spy.at(error_spy.count() - 1)[1] is custom_exception

    def test_warning_emission(self, qtbot):
        """Test warning signal emission."""

        class TestWorker(BaseWorker):
            def run(self) -> None:
                pass

        worker = TestWorker()
        qtbot.addWidget(worker)

        warning_spy = QSignalSpy(worker.warning)

        worker.emit_warning("Test warning")
        assert warning_spy.count() == 1
        assert warning_spy.at(0) == ["Test warning"]

    def test_wait_if_paused_with_cancellation(self, qtbot):
        """Test that wait_if_paused exits when cancelled."""

        class TestWorker(BaseWorker):
            def __init__(self):
                super().__init__()
                self.wait_started = False
                self.wait_finished = False

            def run(self):
                self.pause()
                self.wait_started = True
                # This should exit quickly due to cancellation
                self.wait_if_paused()
                self.wait_finished = True

        worker = TestWorker()
        qtbot.addWidget(worker)

        # Test the method directly instead of using QTimer in test
        worker.pause()
        assert worker.is_paused

        # Cancel and test that wait_if_paused exits
        worker.cancel()
        worker.wait_if_paused()  # Should exit immediately

        # Test passed if we reach here without hanging

class TestManagedWorker:
    """Test the ManagedWorker base class."""

    def test_managed_worker_initialization(self, qtbot):
        """Test managed worker initialization with manager."""

        class TestManagedWorker(ManagedWorker):
            def perform_operation(self):
                pass

        manager = Mock(spec=BaseManager)
        worker = TestManagedWorker(manager)
        qtbot.addWidget(worker)

        assert worker.manager is manager
        assert worker._connections == []
        assert worker._operation_name == "TestManagedWorker"

    def test_signal_connection_management(self, qtbot):
        """Test manager signal connection and disconnection."""

        class TestManagedWorker(ManagedWorker):
            def connect_manager_signals(self):
                # Mock connection with disconnect method
                connection = Mock()
                connection.disconnect = Mock()
                self._connections.append(connection)

            def perform_operation(self):
                self.operation_finished.emit(True, "Success")

        manager = Mock(spec=BaseManager)
        worker = TestManagedWorker(manager)
        qtbot.addWidget(worker)

        # Test that connections are created
        worker.connect_manager_signals()
        assert len(worker._connections) == 1

        # Test disconnection
        worker.disconnect_manager_signals()
        # Verify disconnect was called on the connection
        worker._connections[0].disconnect.assert_called_once()
        assert worker._connections == []

    def test_successful_operation_lifecycle(self, qtbot):
        """Test successful operation lifecycle."""

        class TestManagedWorker(ManagedWorker):
            def __init__(self, manager):
                super().__init__(manager)
                self.operation_called = False
                self.signals_connected = False
                self.signals_disconnected = False

            def connect_manager_signals(self):
                self.signals_connected = True

            def disconnect_manager_signals(self):
                self.signals_disconnected = True

            def perform_operation(self):
                self.operation_called = True
                self.operation_finished.emit(True, "Operation completed")

        manager = Mock(spec=BaseManager)
        worker = TestManagedWorker(manager)
        qtbot.addWidget(worker)

        finished_spy = QSignalSpy(worker.operation_finished)

        # Run the worker
        worker.start()
        worker.wait(1000)

        # Verify lifecycle
        assert worker.operation_called
        assert worker.signals_connected
        assert worker.signals_disconnected
        assert finished_spy.count() == 1
        assert finished_spy.at(0) == [True, "Operation completed"]

    def test_error_handling_in_operation(self, qtbot):
        """Test error handling during operation."""

        class TestManagedWorker(ManagedWorker):
            def connect_manager_signals(self):
                pass

            def perform_operation(self):
                raise ValueError("Test error")

        manager = Mock(spec=BaseManager)
        worker = TestManagedWorker(manager)
        qtbot.addWidget(worker)

        error_spy = QSignalSpy(worker.error)
        finished_spy = QSignalSpy(worker.operation_finished)

        # Run the worker
        worker.start()
        worker.wait(1000)

        # Verify error handling
        assert error_spy.count() == 1
        assert "Data format error during managed operation: Test error" in error_spy.at(0)[0]
        assert isinstance(error_spy.at(0)[1], ValueError)

        assert finished_spy.count() == 1
        assert finished_spy.at(0)[0] is False  # Success = False
        assert "Data format error during managed operation: Test error" in finished_spy.at(0)[1]

    def test_cancellation_handling(self, qtbot):
        """Test cancellation handling in managed worker."""

        class TestManagedWorker(ManagedWorker):
            def connect_manager_signals(self):
                pass

            def perform_operation(self):
                self.check_cancellation()  # This will raise InterruptedError

        manager = Mock(spec=BaseManager)
        worker = TestManagedWorker(manager)
        qtbot.addWidget(worker)

        # Cancel before starting
        worker.cancel()

        finished_spy = QSignalSpy(worker.operation_finished)

        # Run the worker
        worker.start()
        worker.wait(1000)

        # Verify cancellation handling
        assert finished_spy.count() == 1
        assert finished_spy.at(0) == [False, "Operation cancelled"]

    def test_cleanup_on_exception(self, qtbot):
        """Test that cleanup occurs even when operation raises exception."""

        class TestManagedWorker(ManagedWorker):
            def __init__(self, manager):
                super().__init__(manager)
                self.cleanup_called = False

            def connect_manager_signals(self):
                pass

            def disconnect_manager_signals(self):
                self.cleanup_called = True

            def perform_operation(self):
                raise RuntimeError("Cleanup test")

        manager = Mock(spec=BaseManager)
        worker = TestManagedWorker(manager)
        qtbot.addWidget(worker)

        # Run the worker
        worker.start()
        worker.wait(1000)

        # Verify cleanup was called despite exception
        assert worker.cleanup_called

@pytest.fixture
def qtbot():
    """Provide qtbot for Qt testing."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    class QtBot:
        def addWidget(self, widget):
            pass

    return QtBot()
