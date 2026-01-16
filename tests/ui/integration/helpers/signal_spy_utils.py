"""
Signal spy utilities for UI integration testing.

Provides MultiSignalRecorder for recording and verifying emissions from
multiple Qt signals with timestamps and ordering.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject

if TYPE_CHECKING:
    from collections.abc import Callable


def get_signal_receivers(obj: QObject, signal: Any) -> int:
    """Get the number of receivers connected to a Qt signal.

    In PySide6, QObject.receivers() requires a string in SIGNAL format.
    This helper handles the conversion from SignalInstance to the proper format.

    Args:
        obj: The QObject that owns the signal.
        signal: The signal to check (e.g., obj.someSignal).

    Returns:
        Number of connected receivers.
    """
    from PySide6.QtCore import SIGNAL

    # Get signal name from the SignalInstance
    # SignalInstance has a 'signal' attribute containing the signature
    if hasattr(signal, "signal"):
        # signal.signal is like "2preview_ready(bytes,int,int,str,int,int,int,bool)"
        # We need to pass it to SIGNAL() to get proper format
        sig_str = signal.signal
        # Remove the leading '2' if present (Qt internal marker)
        sig_str = sig_str.removeprefix("2")
        return obj.receivers(SIGNAL(sig_str))
    else:
        # Fallback: try direct string representation
        return 0


def assert_has_receivers(obj: QObject, signal: Any, context: str = "") -> None:
    """Assert that a Qt signal has at least one connected receiver.

    Uses QObject.receivers() to check connection count. Note that this counts
    connections but cannot identify specific receivers (e.g., lambdas).

    Args:
        obj: The QObject that owns the signal.
        signal: The signal to check (e.g., obj.someSignal).
        context: Optional context string for error messages.

    Raises:
        AssertionError: If the signal has no receivers.

    Example:
        assert_has_receivers(coordinator, coordinator.preview_ready, "preview_ready -> controller")
    """
    count = get_signal_receivers(obj, signal)
    ctx_msg = f" ({context})" if context else ""
    assert count > 0, f"Signal has no receivers{ctx_msg}. Expected at least 1, got {count}."


class MultiSignalRecorder(QObject):
    """Records emissions from multiple Qt signals with timestamps and argument capture.

    Enables verification of:
    - Signal emission count (per-signal or total)
    - Signal argument values
    - Emission order across multiple signals

    Example usage:
        recorder = MultiSignalRecorder()
        recorder.connect_signal(controller.imageChanged, "imageChanged")
        recorder.connect_signal(controller.toolChanged, "toolChanged")

        # Perform UI actions that emit signals...

        assert recorder.count("imageChanged") == 2
        assert recorder.get_args("toolChanged", 0) == ("pencil",)
        assert recorder.emission_order() == ["imageChanged", "toolChanged", "imageChanged"]
    """

    def __init__(self) -> None:
        """Initialize an empty signal recorder."""
        super().__init__()
        # List of (signal_name, args, timestamp) tuples
        self._emissions: list[tuple[str, tuple[Any, ...], float]] = []
        # Map signal names to their slot functions (kept alive)
        self._slots: dict[str, Callable[..., None]] = {}

    def connect_signal(self, signal: Any, name: str) -> None:
        """Connect a Qt signal for recording.

        Args:
            signal: The Qt signal to record (e.g., widget.clicked).
            name: A unique name for this signal in the recording.
        """

        def make_slot(signal_name: str) -> Callable[..., None]:
            """Create a slot that captures arguments and records the emission."""

            def record(*args: Any) -> None:
                self._emissions.append((signal_name, args, time.perf_counter()))

            return record

        slot = make_slot(name)
        self._slots[name] = slot
        signal.connect(slot)

    def count(self, signal_name: str | None = None) -> int:
        """Count recorded emissions.

        Args:
            signal_name: If provided, count only emissions of this signal.
                         If None, count all emissions.

        Returns:
            Number of emissions matching the filter.
        """
        if signal_name is None:
            return len(self._emissions)
        return sum(1 for n, _, _ in self._emissions if n == signal_name)

    def get_args(self, signal_name: str, index: int = -1) -> tuple[Any, ...] | None:
        """Get arguments from a specific emission.

        Args:
            signal_name: Name of the signal to retrieve.
            index: Which emission to retrieve (supports negative indexing).
                   Default -1 retrieves the most recent.

        Returns:
            Tuple of arguments emitted, or None if index is out of range.
        """
        matching = [(args, ts) for n, args, ts in self._emissions if n == signal_name]
        if not matching:
            return None
        try:
            return matching[index][0]
        except IndexError:
            return None

    def all_args(self, signal_name: str) -> list[tuple[Any, ...]]:
        """Get all argument tuples for a specific signal.

        Args:
            signal_name: Name of the signal to retrieve.

        Returns:
            List of argument tuples in emission order.
        """
        return [args for n, args, _ in self._emissions if n == signal_name]

    def emission_order(self) -> list[str]:
        """Get ordered list of signal names as emitted.

        Returns:
            List of signal names in the order they were emitted.
        """
        return [name for name, _, _ in self._emissions]

    def clear(self) -> None:
        """Clear all recorded emissions."""
        self._emissions.clear()

    def assert_emitted(self, signal_name: str, times: int = 1) -> None:
        """Assert signal was emitted expected number of times.

        Args:
            signal_name: Name of the signal to check.
            times: Expected emission count.

        Raises:
            AssertionError: If actual count doesn't match expected.
        """
        actual = self.count(signal_name)
        assert actual == times, (
            f"Expected {signal_name!r} {times}x, got {actual}x. Emission order: {self.emission_order()}"
        )

    def assert_not_emitted(self, signal_name: str) -> None:
        """Assert signal was never emitted.

        Args:
            signal_name: Name of the signal to check.

        Raises:
            AssertionError: If signal was emitted.
        """
        self.assert_emitted(signal_name, 0)

    def assert_emission_order(self, expected: list[str]) -> None:
        """Assert signals were emitted in expected order.

        Args:
            expected: List of signal names in expected order.

        Raises:
            AssertionError: If actual order doesn't match expected.
        """
        actual = self.emission_order()
        assert actual == expected, f"Expected order {expected}, got {actual}"

    def assert_contains_sequence(self, sequence: list[str]) -> None:
        """Assert that emissions contain the given sequence in order.

        The sequence doesn't need to be contiguous - only that the signals
        appear in the given order.

        Args:
            sequence: List of signal names that should appear in order.

        Raises:
            AssertionError: If sequence is not found in order.
        """
        order = self.emission_order()
        seq_idx = 0
        for name in order:
            if seq_idx < len(sequence) and name == sequence[seq_idx]:
                seq_idx += 1
        if seq_idx != len(sequence):
            raise AssertionError(
                f"Sequence {sequence} not found in order. Matched up to index {seq_idx}, full order: {order}"
            )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"MultiSignalRecorder(emissions={len(self._emissions)}, order={self.emission_order()})"
