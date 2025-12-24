"""
Integration tests for Qt signal/slot connections in SpritePal.

This module tests the critical signal/slot connections between UnifiedManualOffsetDialog
and ROMExtractionPanel, ensuring proper:
- Signal emission and reception
- Parameter types and values
- Connection timing and order
- Thread safety
- Connection lifecycle management
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from tests.fixtures.timeouts import SHORT, signal_timeout
from ui.dialogs.manual_offset_dialog import UnifiedManualOffsetDialog
from ui.rom_extraction_panel import ROMExtractionPanel
from utils.logging_config import get_logger

logger = get_logger(__name__)


def _create_dialog(parent=None) -> UnifiedManualOffsetDialog:
    """Create UnifiedManualOffsetDialog with injected dependencies.

    Used by tests that have managers_initialized fixture.
    """
    from core.di_container import inject
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.services.rom_cache import ROMCache

    return UnifiedManualOffsetDialog(
        parent,
        rom_cache=inject(ROMCache),
        settings_manager=inject(ApplicationStateManager),
        extraction_manager=inject(CoreOperationsManager),
    )


@pytest.fixture
def temp_rom_file():
    """Create a temporary ROM file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.sfc', delete=False) as f:
        # Write minimal ROM header
        f.write(b'\x00' * 0x8000)  # 32KB of zeros
        temp_path = f.name

    yield temp_path

    # Cleanup
    try:
        Path(temp_path).unlink()
    except Exception:
        # Caught exception during operation
        pass
@pytest.fixture
def real_extraction_manager():
    """Create a mock extraction manager."""
    manager = MagicMock()
    manager.extract_sprite = MagicMock(return_value=(None, None))
    manager.get_sprite_at_offset = MagicMock(return_value=None)
    return manager

class SignalRecorder(QObject):
    """Helper class to record signal emissions with parameters."""

    def __init__(self):
        super().__init__()
        self.emissions: list[tuple[str, tuple, float]] = []
        self.lock = QThread.currentThread()  # Thread safety check

    @Slot(int)
    def record_offset_changed(self, offset: int):
        """Record offset_changed signal."""
        self._record_signal('offset_changed', (offset,))

    @Slot(int, str)
    def record_sprite_found(self, offset: int, name: str):
        """Record sprite_found signal."""
        self._record_signal('sprite_found', (offset, name))

    def _record_signal(self, signal_name: str, args: tuple):
        """Record a signal emission with timestamp."""
        # Verify we're in the correct thread
        current_thread = QThread.currentThread()
        if current_thread != self.lock:
            logger.warning(f"Signal {signal_name} received in different thread!")

        timestamp = time.time()
        self.emissions.append((signal_name, args, timestamp))
        logger.debug(f"Recorded signal: {signal_name}{args} at {timestamp}")

    def clear(self):
        """Clear recorded emissions."""
        self.emissions.clear()

    def get_emissions(self, signal_name: str | None = None) -> list[tuple[tuple, float]]:
        """Get emissions for a specific signal or all."""
        if signal_name:
            return [(args, ts) for name, args, ts in self.emissions if name == signal_name]
        return [(args, ts) for _, args, ts in self.emissions]

    def count(self, signal_name: str | None = None) -> int:
        """Count emissions for a specific signal or all."""
        if signal_name:
            return sum(1 for name, _, _ in self.emissions if name == signal_name)
        return len(self.emissions)

@pytest.mark.gui
@pytest.mark.usefixtures("session_managers")
@pytest.mark.shared_state_safe
class TestDialogSignalConnections:
    """Test UnifiedManualOffsetDialog signal connections."""

    def test_dialog_signals_exist(self, qtbot, managers_initialized):
        """Test that dialog has required signals."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        # Check signals exist
        assert hasattr(dialog, 'offset_changed')
        assert hasattr(dialog, 'sprite_found')

        # Check they are Qt signals
        assert isinstance(dialog.offset_changed, Signal)
        assert isinstance(dialog.sprite_found, Signal)

    def test_offset_changed_emission(self, qtbot, managers_initialized):
        """Test offset_changed signal is emitted with correct value."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        # Create signal spy
        with qtbot.waitSignal(dialog.offset_changed, timeout=signal_timeout()) as blocker:
            # Trigger offset change
            dialog.set_offset(0x1000)

        # Verify signal was emitted with correct value
        assert blocker.args == [0x1000]

    def test_sprite_found_emission(self, qtbot, managers_initialized):
        """Test sprite_found signal is emitted with correct parameters."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        # Create signal spy
        with qtbot.waitSignal(dialog.sprite_found, timeout=signal_timeout()) as blocker:
            # Trigger sprite found (simulate Apply button)
            dialog._apply_offset()

        # Verify signal was emitted with offset and name
        assert len(blocker.args) == 2
        assert isinstance(blocker.args[0], int)  # offset
        assert isinstance(blocker.args[1], str)  # sprite name

    def test_multiple_rapid_emissions(self, qtbot, managers_initialized, wait_for_signal_processed):
        """Test handling of multiple rapid signal emissions."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        recorder = SignalRecorder()
        dialog.offset_changed.connect(recorder.record_offset_changed)

        # Emit multiple signals rapidly
        offsets = [0x1000, 0x2000, 0x3000, 0x4000, 0x5000]
        for offset in offsets:
            dialog.set_offset(offset)

        # Wait for all signals to be processed
        qtbot.waitUntil(lambda: recorder.count('offset_changed') == len(offsets), timeout=signal_timeout())

        # Verify all signals were received
        emissions = recorder.get_emissions('offset_changed')
        received_offsets = [args[0] for args, _ in emissions]
        assert received_offsets == offsets

    def test_signal_connection_types(self, qtbot, managers_initialized, wait_for_signal_processed):
        """Test different Qt connection types for cross-thread safety."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        recorder = SignalRecorder()

        # Test AutoConnection (default)
        dialog.offset_changed.connect(recorder.record_offset_changed)

        # Test QueuedConnection (for cross-thread)
        dialog.sprite_found.connect(
            recorder.record_sprite_found,
            Qt.ConnectionType.QueuedConnection
        )

        # Emit signals
        dialog.set_offset(0x1000)
        dialog._apply_offset()

        # Wait for queued connections to be processed
        qtbot.waitUntil(lambda: recorder.count() == 2, timeout=signal_timeout())

        # Verify both signals received
        assert recorder.count('offset_changed') == 1
        assert recorder.count('sprite_found') == 1

@pytest.mark.gui
@pytest.mark.usefixtures("session_managers")
@pytest.mark.shared_state_safe
class TestThreadSafetyAndTiming:
    """Test thread safety and timing of signal emissions."""

    def test_signal_thread_affinity(self, qtbot, managers_initialized, wait_for_signal_processed):
        """Test that signals are emitted and received in correct threads."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        main_thread = QThread.currentThread()
        emission_thread = None
        reception_thread = None

        @Slot(int)
        def check_thread(offset):
            nonlocal reception_thread
            reception_thread = QThread.currentThread()

        dialog.offset_changed.connect(check_thread)

        # Emit from main thread
        emission_thread = QThread.currentThread()
        dialog.offset_changed.emit(0x1000)
        qtbot.waitUntil(lambda: reception_thread is not None, timeout=signal_timeout(SHORT))

        # Both should be in main thread for GUI operations
        assert emission_thread == main_thread
        assert reception_thread == main_thread

    def test_worker_thread_signal_emission(self, qtbot, managers_initialized, wait_for_signal_processed):
        """Test signal emission from worker thread to main thread."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        main_thread = QThread.currentThread()
        worker_emissions = []
        main_receptions = []

        class Worker(QObject):
            def __init__(self, dialog):
                super().__init__()
                self.dialog = dialog

            @Slot()
            def do_work(self):
                # This runs in worker thread
                worker_thread = QThread.currentThread()
                worker_emissions.append(worker_thread)

                # Emit signal from worker thread
                self.dialog.offset_changed.emit(0x2000)

        @Slot(int)
        def receive_in_main(offset):
            main_receptions.append(QThread.currentThread())

        # Connect to receive in main thread
        dialog.offset_changed.connect(receive_in_main, Qt.ConnectionType.QueuedConnection)

        # Create worker and thread
        worker = Worker(dialog)
        thread = QThread()
        worker.moveToThread(thread)

        # Connect and start
        thread.started.connect(worker.do_work)
        thread.start()

        # Wait for cross-thread signal to be received in main thread
        qtbot.waitUntil(lambda: len(main_receptions) > 0, timeout=signal_timeout())
        thread.quit()
        thread.wait()

        # Verify cross-thread signal delivery
        assert len(worker_emissions) == 1
        assert len(main_receptions) == 1
        assert worker_emissions[0] != main_thread  # Emitted from worker
        assert main_receptions[0] == main_thread   # Received in main

    def test_signal_emission_timing(self, qtbot, managers_initialized, wait_for_signal_processed):
        """Test timing and order of signal emissions."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        recorder = SignalRecorder()
        dialog.offset_changed.connect(recorder.record_offset_changed)
        dialog.sprite_found.connect(recorder.record_sprite_found)

        # Emit signals with timing
        time.time()

        dialog.offset_changed.emit(0x1000)
        qtbot.waitUntil(lambda: recorder.count() >= 1, timeout=signal_timeout(SHORT))

        dialog.offset_changed.emit(0x2000)
        qtbot.waitUntil(lambda: recorder.count() >= 2, timeout=signal_timeout(SHORT))

        dialog.sprite_found.emit(0x2000, "sprite_1")
        qtbot.waitUntil(lambda: recorder.count() >= 3, timeout=signal_timeout(SHORT))

        # Verify order and timing
        emissions = recorder.emissions
        assert len(emissions) == 3

        # Check order
        assert emissions[0][0] == 'offset_changed'
        assert emissions[1][0] == 'offset_changed'
        assert emissions[2][0] == 'sprite_found'

        # Check timing (should be sequential)
        for i in range(1, len(emissions)):
            assert emissions[i][2] > emissions[i-1][2]  # Later timestamp

    def test_high_frequency_emissions(self, qtbot, managers_initialized, wait_for_signal_processed):
        """Test handling of high-frequency signal emissions."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        received_count = 0

        @Slot(int)
        def count_receptions(offset):
            nonlocal received_count
            received_count += 1

        dialog.offset_changed.connect(count_receptions)

        # Emit many signals rapidly
        emission_count = 100
        for i in range(emission_count):
            dialog.offset_changed.emit(i * 100)

        # Wait for all signals to be received
        qtbot.waitUntil(lambda: received_count == emission_count, timeout=signal_timeout())

        # All signals should be received
        assert received_count == emission_count

@pytest.mark.gui
@pytest.mark.usefixtures("session_managers")
@pytest.mark.shared_state_safe
class TestSignalBlockingAndError:
    """Test signal blocking and error conditions."""

    def test_blocked_signals(self, qtbot, managers_initialized, wait_for_signal_processed):
        """Test that blocked signals are not emitted."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        recorder = SignalRecorder()
        dialog.offset_changed.connect(recorder.record_offset_changed)

        # Block signals
        dialog.blockSignals(True)

        # Try to emit
        dialog.offset_changed.emit(0x1000)
        wait_for_signal_processed()

        # Should not receive
        assert recorder.count() == 0

        # Unblock and emit
        dialog.blockSignals(False)
        dialog.offset_changed.emit(0x2000)
        qtbot.waitUntil(lambda: recorder.count() == 1, timeout=signal_timeout(SHORT))

        # Now should receive
        assert recorder.count() == 1

    def test_exception_in_slot(self, qtbot, managers_initialized, wait_for_signal_processed):
        """Test that exceptions in slots don't break signal system."""
        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        faulty_calls: list[int] = []
        good_calls: list[int] = []

        @Slot(int)
        def faulty_slot(offset: int) -> None:
            faulty_calls.append(offset)
            if len(faulty_calls) == 1:
                raise ValueError("Test exception")

        @Slot(int)
        def good_slot(offset: int) -> None:
            good_calls.append(offset)

        # Connect both slots
        dialog.offset_changed.connect(faulty_slot)
        dialog.offset_changed.connect(good_slot)

        # Emit signal - use capture_exceptions to catch the expected ValueError
        with qtbot.capture_exceptions() as exceptions:
            dialog.offset_changed.emit(0x1000)
            wait_for_signal_processed()

        # Verify the exception was caught
        assert len(exceptions) == 1
        assert isinstance(exceptions[0][1], ValueError)

        # Both slots should be called despite exception
        assert len(faulty_calls) == 1
        assert len(good_calls) == 1

        # Emit again - faulty slot won't raise this time
        dialog.offset_changed.emit(0x2000)
        wait_for_signal_processed()

        assert len(faulty_calls) == 2
        assert len(good_calls) == 2

    def test_deleted_receiver(self, qtbot, managers_initialized, wait_for_signal_processed):
        """Test that deleted receivers don't cause crashes."""
        import gc
        import weakref

        dialog = _create_dialog(None)
        qtbot.addWidget(dialog)

        # Track receptions with a list (avoids class attribute pollution)
        receptions: list[int] = []

        # Create receiver that will be deleted
        class Receiver(QObject):
            @Slot(int)
            def receive(self, offset: int) -> None:
                receptions.append(offset)

        receiver = Receiver()
        weak_receiver = weakref.ref(receiver)
        dialog.offset_changed.connect(receiver.receive)

        # Emit with valid receiver
        dialog.offset_changed.emit(0x1000)
        qtbot.waitUntil(lambda: len(receptions) > 0, timeout=signal_timeout(SHORT))
        assert receptions == [0x1000]

        # Delete receiver and wait for actual deletion
        receiver.deleteLater()
        del receiver  # Release our reference
        wait_for_signal_processed()
        gc.collect()  # Force garbage collection

        # Wait until the weak reference is dead
        qtbot.waitUntil(lambda: weak_receiver() is None, timeout=signal_timeout())

        # Emit again - should not crash (receiver is now deleted)
        dialog.offset_changed.emit(0x2000)
        wait_for_signal_processed()

        # Should not have been received (receiver was deleted)
        assert receptions == [0x1000]

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
