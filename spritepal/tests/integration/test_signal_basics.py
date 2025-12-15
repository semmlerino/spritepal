"""
Basic signal/slot integration tests that can run in any environment.

These tests focus on the core signal/slot mechanisms without requiring
full GUI setup, making them suitable for CI/headless environments.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from utils.logging_config import get_logger

logger = get_logger(__name__)

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Integration tests involve managers that spawn threads"),
    pytest.mark.shared_state_safe,
]

class SimpleEmitter(QObject):
    """Simple emitter for testing."""
    value_changed = Signal(int)
    message_sent = Signal(str)
    data_ready = Signal(int, str)

    def emit_value(self, value: int):
        """Emit value_changed signal."""
        self.value_changed.emit(value)

    def emit_message(self, msg: str):
        """Emit message_sent signal."""
        self.message_sent.emit(msg)

    def emit_data(self, num: int, text: str):
        """Emit data_ready signal."""
        self.data_ready.emit(num, text)

class SimpleReceiver(QObject):
    """Simple receiver for testing."""

    def __init__(self):
        super().__init__()
        self.received_values: list[int] = []
        self.received_messages: list[str] = []
        self.received_data: list[tuple] = []

    @Slot(int)
    def on_value_changed(self, value: int):
        """Handle value_changed signal."""
        self.received_values.append(value)
        logger.debug(f"Received value: {value}")

    @Slot(str)
    def on_message_sent(self, msg: str):
        """Handle message_sent signal."""
        self.received_messages.append(msg)
        logger.debug(f"Received message: {msg}")

    @Slot(int, str)
    def on_data_ready(self, num: int, text: str):
        """Handle data_ready signal."""
        self.received_data.append((num, text))
        logger.debug(f"Received data: {num}, {text}")

    def clear(self):
        """Clear all received data."""
        self.received_values.clear()
        self.received_messages.clear()
        self.received_data.clear()

@pytest.mark.headless
@pytest.mark.usefixtures("session_managers")
@pytest.mark.shared_state_safe
class TestBasicSignalSlot:
    """Test basic signal/slot functionality."""

    def test_signal_emission_and_reception(self):
        """Test that signals are emitted and received correctly."""
        emitter = SimpleEmitter()
        receiver = SimpleReceiver()

        # Connect signals to slots
        emitter.value_changed.connect(receiver.on_value_changed)
        emitter.message_sent.connect(receiver.on_message_sent)
        emitter.data_ready.connect(receiver.on_data_ready)

        # Emit signals
        emitter.emit_value(42)
        emitter.emit_message("Hello")
        emitter.emit_data(100, "World")

        # Verify reception
        assert receiver.received_values == [42]
        assert receiver.received_messages == ["Hello"]
        assert receiver.received_data == [(100, "World")]

    def test_multiple_connections(self):
        """Test multiple receivers connected to same signal."""
        emitter = SimpleEmitter()
        receiver1 = SimpleReceiver()
        receiver2 = SimpleReceiver()

        # Connect both receivers
        emitter.value_changed.connect(receiver1.on_value_changed)
        emitter.value_changed.connect(receiver2.on_value_changed)

        # Emit signal
        emitter.emit_value(123)

        # Both should receive
        assert receiver1.received_values == [123]
        assert receiver2.received_values == [123]

    def test_disconnection(self):
        """Test signal disconnection."""
        emitter = SimpleEmitter()
        receiver = SimpleReceiver()

        # Connect and emit
        emitter.value_changed.connect(receiver.on_value_changed)
        emitter.emit_value(1)
        assert receiver.received_values == [1]

        # Disconnect and emit
        emitter.value_changed.disconnect(receiver.on_value_changed)
        emitter.emit_value(2)

        # Should not receive second emission
        assert receiver.received_values == [1]

    def test_unique_connection(self):
        """Test Qt.UniqueConnection prevents duplicates."""
        emitter = SimpleEmitter()
        receiver = SimpleReceiver()

        # Connect multiple times with UniqueConnection
        for _ in range(5):
            emitter.value_changed.connect(
                receiver.on_value_changed,
                Qt.ConnectionType.UniqueConnection
            )

        # Emit once
        emitter.emit_value(999)

        # Should only receive once
        assert receiver.received_values == [999]

    def test_signal_parameter_types(self):
        """Test different parameter types in signals."""
        class TypedEmitter(QObject):
            int_signal = Signal(int)
            float_signal = Signal(float)
            str_signal = Signal(str)
            bool_signal = Signal(bool)
            list_signal = Signal(list)
            dict_signal = Signal(dict)

        emitter = TypedEmitter()
        received = {}

        # Connect with lambdas to capture values
        emitter.int_signal.connect(lambda v: received.update({'int': v}))
        emitter.float_signal.connect(lambda v: received.update({'float': v}))
        emitter.str_signal.connect(lambda v: received.update({'str': v}))
        emitter.bool_signal.connect(lambda v: received.update({'bool': v}))
        emitter.list_signal.connect(lambda v: received.update({'list': v}))
        emitter.dict_signal.connect(lambda v: received.update({'dict': v}))

        # Emit all types
        emitter.int_signal.emit(42)
        emitter.float_signal.emit(3.14)
        emitter.str_signal.emit("test")
        emitter.bool_signal.emit(True)
        emitter.list_signal.emit([1, 2, 3])
        emitter.dict_signal.emit({'key': 'value'})

        # Verify all received correctly
        assert received['int'] == 42
        assert received['float'] == 3.14
        assert received['str'] == "test"
        assert received['bool'] == True
        assert received['list'] == [1, 2, 3]
        assert received['dict'] == {'key': 'value'}

@pytest.mark.headless
class TestDialogSignalPatterns:
    """Test signal patterns specific to dialogs."""

    def test_dialog_signal_simulation(self):
        """Test simulating dialog signals without real dialog."""

        class MockDialog(QObject):
            """Mock dialog with signals."""
            offset_changed = Signal(int)
            sprite_found = Signal(int, str)

            def set_offset(self, offset: int):
                """Simulate setting offset."""
                self.offset_changed.emit(offset)

            def find_sprite(self, offset: int, name: str):
                """Simulate finding sprite."""
                self.sprite_found.emit(offset, name)

        class MockPanel(QObject):
            """Mock panel that receives signals."""

            def __init__(self):
                super().__init__()
                self.current_offset = 0
                self.found_sprites: list[tuple] = []

            @Slot(int)
            def on_offset_changed(self, offset: int):
                """Handle offset change."""
                self.current_offset = offset
                logger.debug(f"Panel: offset changed to {offset}")

            @Slot(int, str)
            def on_sprite_found(self, offset: int, name: str):
                """Handle sprite found."""
                self.found_sprites.append((offset, name))
                logger.debug(f"Panel: sprite found at {offset}: {name}")

        # Create mock components
        dialog = MockDialog()
        panel = MockPanel()

        # Connect signals
        dialog.offset_changed.connect(panel.on_offset_changed)
        dialog.sprite_found.connect(panel.on_sprite_found)

        # Simulate dialog operations
        dialog.set_offset(0x1000)
        assert panel.current_offset == 0x1000

        dialog.find_sprite(0x2000, "test_sprite")
        assert panel.found_sprites == [(0x2000, "test_sprite")]

        # Multiple operations
        dialog.set_offset(0x3000)
        dialog.find_sprite(0x3000, "sprite_2")
        dialog.set_offset(0x4000)

        assert panel.current_offset == 0x4000
        assert len(panel.found_sprites) == 2

    def test_singleton_pattern_simulation(self):
        """Test singleton pattern for dialog without real implementation."""

        class SingletonDialog(QObject):
            """Simulated singleton dialog."""
            _instance = None

            offset_changed = Signal(int)

            @classmethod
            def get_instance(cls):
                """Get singleton instance."""
                if cls._instance is None:
                    cls._instance = cls()
                return cls._instance

            @classmethod
            def reset(cls):
                """Reset singleton for testing."""
                cls._instance = None

        # First access creates instance
        dialog1 = SingletonDialog.get_instance()
        dialog2 = SingletonDialog.get_instance()

        # Should be same instance
        assert dialog1 is dialog2

        # Connect to signal
        received = []
        dialog1.offset_changed.connect(lambda v: received.append(v))

        # Emit from either reference
        dialog2.offset_changed.emit(555)
        assert received == [555]

        # Reset and verify new instance
        SingletonDialog.reset()
        dialog3 = SingletonDialog.get_instance()
        assert dialog3 is not dialog1

    def test_deferred_connection_pattern(self):
        """Test deferred signal connection pattern."""

        class DeferredDialog(QObject):
            """Dialog with deferred connections."""
            signal = Signal(str)

            def __init__(self):
                super().__init__()
                self._deferred_connections = []

            def add_deferred_connection(self, slot):
                """Add connection to be made later."""
                self._deferred_connections.append(slot)

            def connect_deferred(self):
                """Connect all deferred connections."""
                for slot in self._deferred_connections:
                    self.signal.connect(slot)
                self._deferred_connections.clear()

        dialog = DeferredDialog()
        received = []

        # Add deferred connection
        dialog.add_deferred_connection(lambda v: received.append(v))

        # Signal emission before connection - nothing happens
        dialog.signal.emit("too_early")
        assert received == []

        # Connect deferred
        dialog.connect_deferred()

        # Now signals work
        dialog.signal.emit("connected")
        assert received == ["connected"]

@pytest.mark.headless
class TestSignalThreadSafety:
    """Test thread safety aspects of signals."""

    def test_cross_thread_signal_safety(self):
        """Test signal emission across threads."""

        class ThreadedEmitter(QObject):
            """Emitter that works across threads."""
            result = Signal(str)

            @Slot()
            def do_work(self):
                """Work method for thread."""
                thread_id = QThread.currentThread()
                self.result.emit(f"Work done in thread {id(thread_id)}")

        emitter = ThreadedEmitter()
        thread = QThread()
        received = []

        # Move to thread
        emitter.moveToThread(thread)

        # Connect signal
        emitter.result.connect(lambda v: received.append(v))

        # Start work
        thread.started.connect(emitter.do_work)
        thread.start()

        # Wait for completion
        thread.quit()
        thread.wait(1000)

        # Should have received result
        assert len(received) == 1
        assert "Work done in thread" in received[0]

    def test_signal_emission_order(self):
        """Test that signal emission order is preserved."""
        emitter = SimpleEmitter()
        receiver = SimpleReceiver()

        emitter.value_changed.connect(receiver.on_value_changed)

        # Emit multiple values
        for i in range(10):
            emitter.emit_value(i)

        # Should be received in order
        assert receiver.received_values == list(range(10))

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
