"""
Lightweight signal test double for non-Qt test objects.

This module provides TestSignal, a simple signal implementation for use in tests
where real Qt signals aren't needed or appropriate. Use this for:
- Test doubles for non-QObject classes
- Pure Python mock objects that need signal-like behavior
- Tracking signal emissions without Qt dependencies

For real Qt components, use actual Signal() objects with QSignalSpy instead.

See UNIFIED_TESTING_GUIDE_DO_NOT_DELETE.md for usage guidance.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class TestSignal:
    """
    Lightweight signal test double for non-Qt test objects.

    Provides a Qt Signal-like interface without Qt dependencies.
    Use for test doubles when the code under test doesn't require
    actual Qt signal infrastructure.

    Example:
        >>> class MockManager:
        ...     def __init__(self):
        ...         self.command_completed = TestSignal()
        ...
        >>> manager = MockManager()
        >>> received = []
        >>> manager.command_completed.connect(lambda x: received.append(x))
        >>> manager.command_completed.emit("result")
        >>> assert manager.command_completed.was_emitted
        >>> assert received == ["result"]  # Callback receives unpacked args

    Note:
        For real Qt components, use actual Signal() objects.
        QSignalSpy only works with real Qt signals.
    """

    __test__ = False  # Prevent pytest collection

    def __init__(self) -> None:
        """Initialize an empty test signal."""
        self.emissions: list[tuple[Any, ...]] = []
        self.callbacks: list[Callable[..., Any]] = []

    def emit(self, *args: Any) -> None:
        """
        Emit the signal with given arguments.

        Records the emission and calls all connected callbacks.

        Args:
            *args: Arguments to pass to callbacks.
        """
        self.emissions.append(args)
        for callback in self.callbacks:
            callback(*args)

    def connect(self, callback: Callable[..., Any]) -> None:
        """
        Connect a callback to this signal.

        Args:
            callback: Function to call when signal is emitted.
        """
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def disconnect(self, callback: Callable[..., Any]) -> None:
        """
        Disconnect a callback from this signal.

        Args:
            callback: Function to disconnect.

        Raises:
            ValueError: If callback was not connected.
        """
        self.callbacks.remove(callback)

    def disconnect_all(self) -> None:
        """Disconnect all callbacks from this signal."""
        self.callbacks.clear()

    @property
    def was_emitted(self) -> bool:
        """Check if signal has been emitted at least once."""
        return len(self.emissions) > 0

    @property
    def emission_count(self) -> int:
        """Get the number of times this signal was emitted."""
        return len(self.emissions)

    @property
    def last_emission(self) -> tuple[Any, ...] | None:
        """
        Get the arguments from the last emission.

        Returns:
            Tuple of arguments from last emit(), or None if never emitted.
        """
        return self.emissions[-1] if self.emissions else None

    @property
    def first_emission(self) -> tuple[Any, ...] | None:
        """
        Get the arguments from the first emission.

        Returns:
            Tuple of arguments from first emit(), or None if never emitted.
        """
        return self.emissions[0] if self.emissions else None

    def get_emission(self, index: int) -> tuple[Any, ...]:
        """
        Get arguments from a specific emission.

        Args:
            index: Index of emission (0-based, supports negative indexing).

        Returns:
            Tuple of arguments from that emission.

        Raises:
            IndexError: If index is out of range.
        """
        return self.emissions[index]

    def reset(self) -> None:
        """Clear all recorded emissions (keeps callbacks connected)."""
        self.emissions.clear()

    def clear(self) -> None:
        """Clear emissions and disconnect all callbacks."""
        self.emissions.clear()
        self.callbacks.clear()

    def __len__(self) -> int:
        """Return number of emissions (for compatibility with QSignalSpy-like usage)."""
        return len(self.emissions)

    def __bool__(self) -> bool:
        """Return True if signal was emitted at least once."""
        return self.was_emitted

    def __repr__(self) -> str:
        """Return string representation."""
        return f"TestSignal(emissions={len(self.emissions)}, callbacks={len(self.callbacks)})"


class TestSignalBlocker:
    """
    Context manager for waiting on TestSignal emissions.

    Similar to qtbot.waitSignal() but for TestSignal.
    Useful for testing async-like behavior in synchronous code.

    Example:
        >>> signal = TestSignal()
        >>> with TestSignalBlocker(signal) as blocker:
        ...     signal.emit("done")
        >>> assert blocker.signal_triggered
        >>> assert blocker.args == ("done",)
    """

    __test__ = False  # Prevent pytest collection

    def __init__(self, signal: TestSignal) -> None:
        """
        Initialize blocker for a TestSignal.

        Args:
            signal: TestSignal to monitor.
        """
        self.signal = signal
        self.signal_triggered = False
        self.args: tuple[Any, ...] | None = None
        self._initial_count = 0

    def __enter__(self) -> TestSignalBlocker:
        """Start monitoring the signal."""
        self._initial_count = self.signal.emission_count
        return self

    def __exit__(self, *args: Any) -> None:
        """Check if signal was emitted during the context."""
        if self.signal.emission_count > self._initial_count:
            self.signal_triggered = True
            self.args = self.signal.last_emission
