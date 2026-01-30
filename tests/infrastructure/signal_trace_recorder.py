"""Signal trace recording infrastructure for golden trace tests.

This module provides utilities for recording and verifying signal emissions
during complex multi-step operations. It catches regressions in signal cascades
that single-signal tests miss.

Key use cases:
- Verify undo commands emit correct signals for UI sync
- Catch missing intermediate signals in cascades
- Detect wrong signal order or duplicate emissions
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SignalEvent:
    """A single signal emission event."""

    signal_name: str
    args: tuple[Any, ...]
    source: str = ""  # Optional: object that emitted


@dataclass
class SignalTrace:
    """Records signal emissions during an operation."""

    events: list[SignalEvent] = field(default_factory=list)

    def record(self, signal_name: str, *args: Any, source: str = "") -> None:
        """Record a signal emission."""
        self.events.append(SignalEvent(signal_name, args, source))

    def clear(self) -> None:
        """Clear all recorded events."""
        self.events.clear()

    def signal_names(self) -> list[str]:
        """Return just signal names in emission order."""
        return [e.signal_name for e in self.events]

    def get_args(self, signal_name: str) -> tuple[Any, ...] | None:
        """Get the arguments of the first emission of a signal, or None."""
        for e in self.events:
            if e.signal_name == signal_name:
                return e.args
        return None

    def count(self, signal_name: str) -> int:
        """Count how many times a signal was emitted."""
        return sum(1 for e in self.events if e.signal_name == signal_name)


class SignalCollector:
    """Collects signal emissions from a mock or real Qt object.

    Usage with MagicMock:
        controller = MagicMock()
        collector = SignalCollector()
        collector.connect_mock(controller, ["mapping_created", "mapping_removed"])

        # ... trigger operations ...

        assert "mapping_removed" in collector.trace.signal_names()
        assert collector.trace.get_args("mapping_removed") == ("frame_01",)

    Usage with real Qt signals (e.g., from a real controller):
        collector = SignalCollector()
        collector.connect_signals(controller, ["mapping_created", "mapping_removed"])

        # ... trigger operations ...

        assert collector.trace.count("mapping_created") == 1
    """

    def __init__(self) -> None:
        self.trace = SignalTrace()
        self._connections: list[Callable[[], None]] = []

    def connect_mock(self, mock_obj: Any, signal_names: list[str]) -> None:
        """Connect to mock signals by replacing their emit methods.

        Args:
            mock_obj: A MagicMock with signal attributes (e.g., mock_obj.mapping_created)
            signal_names: Names of signals to track
        """
        for name in signal_names:
            signal = getattr(mock_obj, name, None)
            if signal is None:
                continue

            # Store original emit if it exists
            original_emit = getattr(signal, "emit", None)

            def make_recorder(sig_name: str, orig: Any) -> Callable[..., None]:
                def recorder(*args: Any) -> None:
                    self.trace.record(sig_name, *args)
                    # Call original if it's a real callable (not MagicMock's default)
                    if orig is not None and callable(orig):
                        try:
                            orig(*args)
                        except Exception:
                            pass  # Mock may not have proper signature

                return recorder

            signal.emit = make_recorder(name, original_emit)

    def connect_signals(self, obj: Any, signal_names: list[str]) -> None:
        """Connect to real Qt signals on an object.

        This is the preferred method for real Qt objects (not mocks).
        It uses signal.connect() which works with Qt's signal system.

        Args:
            obj: An object with Qt signal attributes (e.g., controller)
            signal_names: Names of signals to track
        """
        for name in signal_names:
            signal = getattr(obj, name, None)
            if signal is None:
                continue
            self.connect_signal(signal, name)

    def connect_signal(self, signal: Any, name: str) -> None:
        """Connect to a single real Qt signal.

        Args:
            signal: A Qt Signal object
            name: Name to record for this signal
        """

        def handler(*args: Any) -> None:
            self.trace.record(name, *args)

        signal.connect(handler)
        self._connections.append(lambda s=signal, h=handler: s.disconnect(h))

    def clear(self) -> None:
        """Clear all recorded events."""
        self.trace.clear()

    def disconnect_all(self) -> None:
        """Disconnect all real signal connections."""
        for disconnect in self._connections:
            try:
                disconnect()
            except Exception:
                pass
        self._connections.clear()


def assert_trace_contains(trace: SignalTrace, expected: list[str]) -> None:
    """Assert that trace contains expected signals in order (allows extras).

    Args:
        trace: The recorded signal trace
        expected: Expected signal names as subsequence

    Raises:
        AssertionError: If expected signals not found in order
    """
    actual = trace.signal_names()
    j = 0
    for signal in actual:
        if j < len(expected) and signal == expected[j]:
            j += 1
    if j != len(expected):
        missing = expected[j:]
        raise AssertionError(f"Expected signals {expected} as subsequence of {actual}, missing: {missing}")


def assert_trace_excludes(trace: SignalTrace, forbidden: list[str]) -> None:
    """Assert that trace does NOT contain any forbidden signals.

    Args:
        trace: The recorded signal trace
        forbidden: Signal names that must not appear

    Raises:
        AssertionError: If any forbidden signal found
    """
    actual = trace.signal_names()
    for signal in forbidden:
        if signal in actual:
            raise AssertionError(f"Forbidden signal '{signal}' found in trace: {actual}")


def assert_signal_emitted(trace: SignalTrace, signal_name: str, times: int = 1) -> None:
    """Assert that a signal was emitted exactly N times.

    Args:
        trace: The recorded signal trace
        signal_name: Signal name to check
        times: Expected emission count (default 1)

    Raises:
        AssertionError: If count doesn't match
    """
    actual_count = trace.count(signal_name)
    if actual_count != times:
        raise AssertionError(
            f"Expected '{signal_name}' emitted {times} time(s), got {actual_count}. Full trace: {trace.signal_names()}"
        )


def assert_signal_args(trace: SignalTrace, signal_name: str, expected_args: tuple[Any, ...]) -> None:
    """Assert that a signal was emitted with specific arguments.

    Args:
        trace: The recorded signal trace
        signal_name: Signal name to check
        expected_args: Expected arguments tuple

    Raises:
        AssertionError: If signal not found or args don't match
    """
    actual_args = trace.get_args(signal_name)
    if actual_args is None:
        raise AssertionError(f"Signal '{signal_name}' not found in trace: {trace.signal_names()}")
    if actual_args != expected_args:
        raise AssertionError(f"Signal '{signal_name}' args mismatch: expected {expected_args}, got {actual_args}")
