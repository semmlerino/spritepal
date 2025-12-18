"""Signal Registry for tracking and debugging Qt signal connections.

This module provides a centralized registry for tracking signal connections,
enabling debugging of control flow and connection management.

Usage:
    from core.services.signal_registry import SignalRegistry

    # Register a connection with description
    registry = SignalRegistry()
    registry.connect(sender.my_signal, receiver.my_slot, "Update UI on data change")

    # Debug: dump all connections
    print(registry.dump_connections())

    # Cleanup: disconnect all registered connections
    registry.disconnect_all()
"""

from __future__ import annotations

import logging
import threading
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6.QtCore import SignalInstance

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """Information about a registered signal connection."""

    signal_name: str
    sender_type: str
    slot_name: str
    receiver_type: str
    description: str
    timestamp: datetime = field(default_factory=datetime.now)
    connected: bool = True


class SignalRegistry:
    """Centralized registry for tracking Qt signal connections.

    Thread-safe singleton that tracks signal connections for debugging
    and cleanup purposes. Connections can be registered with descriptions
    to aid in understanding control flow.

    Example:
        >>> registry = SignalRegistry()
        >>> registry.connect(
        ...     worker.finished,
        ...     controller.on_finished,
        ...     "Worker completion triggers UI update"
        ... )
        >>> print(registry.dump_connections())
    """

    _instance: SignalRegistry | None = None
    _lock = threading.Lock()

    def __new__(cls) -> SignalRegistry:
        """Singleton pattern with thread safety."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the registry (only once due to singleton)."""
        if self._initialized:
            return

        self._connections: list[tuple[weakref.ref[Any] | None, Callable[..., Any], ConnectionInfo]] = []
        self._connection_lock = threading.RLock()
        self._enabled = True
        self._initialized = True

    def connect(
        self,
        signal: SignalInstance,
        slot: Callable[..., Any],
        description: str = "",
    ) -> bool:
        """Connect a signal to a slot and register the connection.

        Args:
            signal: Qt signal to connect
            slot: Slot/callable to receive the signal
            description: Human-readable description of this connection's purpose

        Returns:
            True if connection was successful, False otherwise
        """
        try:
            signal.connect(slot)

            if self._enabled:
                # Extract signal and slot info for debugging
                signal_name = getattr(signal, "signal", str(signal))
                sender = getattr(signal, "_owner", None)
                sender_type = type(sender).__name__ if sender else "Unknown"

                slot_name = getattr(slot, "__name__", str(slot))
                receiver = getattr(slot, "__self__", None)
                receiver_type = type(receiver).__name__ if receiver else "Function"

                info = ConnectionInfo(
                    signal_name=str(signal_name),
                    sender_type=sender_type,
                    slot_name=slot_name,
                    receiver_type=receiver_type,
                    description=description,
                )

                with self._connection_lock:
                    # Use weakref to sender to avoid preventing garbage collection
                    # Note: sender may be None if we can't determine it from the signal
                    sender_ref = weakref.ref(sender) if sender else None
                    self._connections.append((sender_ref, slot, info))

            return True

        except (RuntimeError, TypeError) as e:
            logger.warning("Failed to connect signal: %s", e)
            return False

    def disconnect_all(self) -> int:
        """Disconnect all registered connections.

        Returns:
            Number of connections that were disconnected
        """
        disconnected = 0

        with self._connection_lock:
            for sender_ref, slot, info in self._connections:
                if info.connected:
                    sender = sender_ref() if sender_ref else None
                    if sender is not None:
                        try:
                            # Try to find and disconnect the signal
                            signal = getattr(sender, info.signal_name.split(".")[-1], None)
                            if signal is not None:
                                signal.disconnect(slot)
                                disconnected += 1
                        except (RuntimeError, TypeError):
                            pass  # Signal already disconnected or sender deleted
                    info.connected = False

            self._connections.clear()

        logger.debug("Disconnected %d signal connections", disconnected)
        return disconnected

    def dump_connections(self, include_disconnected: bool = False) -> str:
        """Generate a human-readable dump of all registered connections.

        Args:
            include_disconnected: Whether to include disconnected connections

        Returns:
            Formatted string listing all connections
        """
        lines = ["Signal Registry Connections:", "=" * 50]

        with self._connection_lock:
            active_count = 0
            for _, _, info in self._connections:
                if not include_disconnected and not info.connected:
                    continue

                status = "ACTIVE" if info.connected else "DISCONNECTED"
                active_count += 1

                lines.append(
                    f"\n[{status}] {info.sender_type}.{info.signal_name} "
                    f"-> {info.receiver_type}.{info.slot_name}"
                )
                if info.description:
                    lines.append(f"    Purpose: {info.description}")
                lines.append(f"    Registered: {info.timestamp.isoformat()}")

        lines.append(f"\n{'=' * 50}")
        lines.append(f"Total active connections: {active_count}")

        return "\n".join(lines)

    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        with self._connection_lock:
            return sum(1 for _, _, info in self._connections if info.connected)

    def get_connections_for_sender(self, sender_type: str) -> list[ConnectionInfo]:
        """Get all connections from a specific sender type."""
        with self._connection_lock:
            return [
                info
                for _, _, info in self._connections
                if info.sender_type == sender_type and info.connected
            ]

    def get_connections_for_receiver(self, receiver_type: str) -> list[ConnectionInfo]:
        """Get all connections to a specific receiver type."""
        with self._connection_lock:
            return [
                info
                for _, _, info in self._connections
                if info.receiver_type == receiver_type and info.connected
            ]

    def enable(self) -> None:
        """Enable connection tracking."""
        self._enabled = True

    def disable(self) -> None:
        """Disable connection tracking (for performance)."""
        self._enabled = False

    def clear(self) -> None:
        """Clear all connection records without disconnecting."""
        with self._connection_lock:
            self._connections.clear()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (primarily for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.disconnect_all()
                cls._instance = None
