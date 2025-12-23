"""Signal connection tracking for cleanup.

Provides a mixin for tracking signal/slot connections and disconnecting
them on cleanup. Use this to prevent memory leaks from orphaned handlers.

Usage:
    class MyManager(SignalConnectionRegistry):
        def __init__(self):
            super().__init__()
            self.connect_tracked(some_signal, self.on_something)

        def cleanup(self):
            self.disconnect_all_tracked()
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import SignalInstance

logger = logging.getLogger(__name__)


class SignalConnectionRegistry:
    """Mixin for tracking and cleaning up signal connections.

    Tracks signal/slot pairs so they can be disconnected on cleanup.
    Thread-safe for the common case of connect in __init__, cleanup in closeEvent.
    """

    def __init__(self) -> None:
        """Initialize the connection tracking list."""
        self._tracked_connections: list[tuple[SignalInstance, Callable[..., object]]] = []

    def connect_tracked(
        self,
        signal: SignalInstance,
        slot: Callable[..., object],
    ) -> None:
        """Connect a signal to a slot and track it for cleanup.

        Args:
            signal: Qt signal to connect
            slot: Callable to receive the signal
        """
        signal.connect(slot)
        self._tracked_connections.append((signal, slot))

    def disconnect_all_tracked(self) -> int:
        """Disconnect all tracked connections.

        Returns:
            Number of connections that were disconnected.
        """
        disconnected = 0
        for signal, slot in self._tracked_connections:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", "Failed to disconnect", RuntimeWarning)
                try:
                    signal.disconnect(slot)
                    disconnected += 1
                except (TypeError, RuntimeError):
                    # Already disconnected or object deleted
                    pass
        self._tracked_connections.clear()

        if disconnected > 0:
            logger.debug("Disconnected %d signal connections", disconnected)

        return disconnected

    def tracked_connection_count(self) -> int:
        """Get the number of tracked connections."""
        return len(self._tracked_connections)
