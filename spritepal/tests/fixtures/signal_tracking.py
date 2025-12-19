"""
Signal tracking mixin for Qt test helpers.

This module provides a mixin class that eliminates the duplicated signal
tracking boilerplate found across multiple test helper classes.

Usage:
    class MyTestHelper(SignalTrackingMixin, QObject):
        my_signal = Signal()

        def __init__(self):
            super().__init__()
            # Set up tracking for signals
            self.setup_signal_tracking({
                "my_signal": self.my_signal,
            })

        def do_something(self):
            self.my_signal.emit()  # Automatically tracked

    # In test:
    helper = MyTestHelper()
    helper.do_something()
    assert helper.get_emissions("my_signal") == [True]
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6.QtCore import SignalInstance


class SignalTrackingMixin:
    """Mixin that provides signal emission tracking for test helpers.

    Eliminates the need for each test helper to implement its own
    signal_emissions dict and connection boilerplate.

    Methods:
        setup_signal_tracking: Initialize tracking for specified signals
        get_emissions: Get recorded emissions for a signal
        get_all_emissions: Get all recorded emissions
        clear_tracking: Clear all or specific signal emissions
        emission_count: Get count of emissions for a signal
    """

    def setup_signal_tracking(
        self,
        signals: dict[str, SignalInstance],
        *,
        record_args: bool = True,
    ) -> None:
        """Set up tracking for the specified signals.

        Args:
            signals: Dict mapping signal names to Signal instances
            record_args: If True, record signal arguments; if False, just record True

        Example:
            self.setup_signal_tracking({
                "offset_changed": self.offset_changed,
                "extraction_complete": self.extraction_complete,
            })
        """
        if not hasattr(self, "_signal_emissions"):
            self._signal_emissions: dict[str, list[Any]] = {}

        for name, signal in signals.items():
            self._signal_emissions[name] = []

            if record_args:
                # Connect with lambda that captures the signal name
                # Use default arg to avoid closure issues
                signal.connect(
                    lambda *args, n=name: self._record_emission(n, args)
                )
            else:
                signal.connect(
                    lambda *args, n=name: self._signal_emissions[n].append(True)
                )

    def _record_emission(self, signal_name: str, args: tuple[Any, ...]) -> None:
        """Record a signal emission with its arguments."""
        if len(args) == 0:
            self._signal_emissions[signal_name].append(True)
        elif len(args) == 1:
            self._signal_emissions[signal_name].append(args[0])
        else:
            self._signal_emissions[signal_name].append(args)

    def get_emissions(self, signal_name: str) -> list[Any]:
        """Get a copy of recorded emissions for a specific signal.

        Args:
            signal_name: Name of the signal

        Returns:
            List of recorded emissions (copy)

        Raises:
            KeyError: If signal_name is not being tracked
        """
        if not hasattr(self, "_signal_emissions"):
            raise RuntimeError("Signal tracking not initialized. Call setup_signal_tracking() first.")
        return self._signal_emissions[signal_name].copy()

    def get_all_emissions(self) -> dict[str, list[Any]]:
        """Get a copy of all recorded emissions.

        Returns:
            Dict mapping signal names to lists of emissions (all copies)
        """
        if not hasattr(self, "_signal_emissions"):
            return {}
        return {name: values.copy() for name, values in self._signal_emissions.items()}

    def clear_tracking(self, signal_name: str | None = None) -> None:
        """Clear recorded emissions.

        Args:
            signal_name: If provided, clear only that signal's emissions.
                        If None, clear all emissions.
        """
        if not hasattr(self, "_signal_emissions"):
            return

        if signal_name is not None:
            if signal_name in self._signal_emissions:
                self._signal_emissions[signal_name].clear()
        else:
            for emissions in self._signal_emissions.values():
                emissions.clear()

    def emission_count(self, signal_name: str) -> int:
        """Get the count of emissions for a signal.

        Args:
            signal_name: Name of the signal

        Returns:
            Number of times the signal was emitted
        """
        if not hasattr(self, "_signal_emissions"):
            return 0
        return len(self._signal_emissions.get(signal_name, []))

    def was_emitted(self, signal_name: str) -> bool:
        """Check if a signal was emitted at least once.

        Args:
            signal_name: Name of the signal

        Returns:
            True if the signal was emitted at least once
        """
        return self.emission_count(signal_name) > 0

    # Backward compatibility aliases
    def get_signal_emissions(self) -> dict[str, list[Any]]:
        """Backward compatible alias for get_all_emissions()."""
        return self.get_all_emissions()

    def clear_signal_tracking(self) -> None:
        """Backward compatible alias for clear_tracking()."""
        self.clear_tracking()
