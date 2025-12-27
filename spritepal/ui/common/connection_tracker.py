"""
Connection tracker for Qt signal lifecycle management.

Provides a simple way to track signal connections and disconnect them all at once,
reducing boilerplate in dialog closeEvent() handlers.

Usage:
    class MyDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._connections = ConnectionTracker()

        def _connect_worker_signals(self, worker):
            # Connections are tracked automatically
            self._connections.connect(worker.finished, self._on_finished)
            self._connections.connect(worker.error, self._on_error)

        def closeEvent(self, event):
            self._connections.disconnect_all()  # Clean up all at once
            super().closeEvent(event)
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QMetaObject


class ConnectionTracker:
    """
    Tracks Qt signal connections for bulk disconnection.

    This class provides a simple way to track signal connections made during
    object initialization or worker setup, and disconnect them all at once
    during cleanup (e.g., in closeEvent()).

    The tracker stores connection metadata rather than Qt's opaque Connection
    objects, allowing reliable disconnection even if the signal/slot pair
    changes state.
    """

    def __init__(self) -> None:
        """Initialize an empty connection tracker."""
        # Store (signal, slot) pairs for disconnection
        # We store tuples because Qt's QMetaObject.Connection isn't always reliable
        # for disconnection in PySide6. Any is required - Qt signals are dynamic.
        self._connections: list[tuple[Any, Callable[..., Any]]] = []  # pyright: ignore[reportExplicitAny]

    def connect(
        self,
        signal: Any,  # pyright: ignore[reportExplicitAny] - Qt signal
        slot: Callable[..., Any],  # pyright: ignore[reportExplicitAny] - Any callable
        connection_type: Any = None,  # pyright: ignore[reportExplicitAny] - Qt.ConnectionType
    ) -> QMetaObject.Connection:
        """
        Connect a signal to a slot and track the connection.

        Args:
            signal: Qt signal to connect (e.g., worker.finished)
            slot: Callable to connect to the signal
            connection_type: Optional Qt.ConnectionType (default: AutoConnection)

        Returns:
            QMetaObject.Connection object from the underlying connect() call

        Example:
            tracker = ConnectionTracker()
            tracker.connect(self.worker.progress, self._on_progress)
            tracker.connect(self.worker.finished, self._on_finished)
        """
        # Make the actual connection
        if connection_type is not None:
            connection = signal.connect(slot, connection_type)
        else:
            connection = signal.connect(slot)

        # Track for later disconnection
        self._connections.append((signal, slot))

        return connection

    def disconnect_all(self) -> int:
        """
        Disconnect all tracked connections.

        Returns:
            Number of connections that were disconnected (or attempted)

        Note:
            This method suppresses warnings for already-disconnected signals,
            making it safe to call multiple times or after partial cleanup.
        """
        count = len(self._connections)

        for signal, slot in self._connections:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", "Failed to disconnect", RuntimeWarning)
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    # Already disconnected or signal/slot no longer valid
                    pass

        self._connections.clear()
        return count

    def __len__(self) -> int:
        """Return the number of tracked connections."""
        return len(self._connections)

    def clear(self) -> None:
        """Clear tracked connections without disconnecting them.

        Use this if connections have already been disconnected elsewhere
        and you just want to reset the tracker state.
        """
        self._connections.clear()
