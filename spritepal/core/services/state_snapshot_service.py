"""
State Snapshot Service for managing application state snapshots.

This service handles creating, storing, and restoring state snapshots for
undo/restore functionality. It's extracted from ApplicationStateManager to
follow the Single Responsibility Principle.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

from PySide6.QtCore import QObject, Signal

from utils.state_manager import StateSnapshot


class StateSnapshotService(QObject):
    """
    Service for managing state snapshots.

    Provides functionality to:
    - Create snapshots of runtime state
    - Restore from snapshots
    - Manage snapshot storage (with max limit)
    """

    # Signals
    snapshot_created = Signal(str)  # snapshot_id
    snapshot_restored = Signal(str)  # snapshot_id

    DEFAULT_MAX_SNAPSHOTS = 10

    def __init__(
        self,
        max_snapshots: int = DEFAULT_MAX_SNAPSHOTS,
        parent: QObject | None = None,
    ) -> None:
        """
        Initialize the state snapshot service.

        Args:
            max_snapshots: Maximum number of snapshots to keep
            parent: Optional Qt parent object
        """
        super().__init__(parent)
        self._max_snapshots = max_snapshots
        self._snapshots: OrderedDict[str, StateSnapshot] = OrderedDict()
        self._lock = threading.RLock()

    def create_snapshot(
        self,
        states: dict[str, Any],
        namespace: str | None = None,
    ) -> str:
        """
        Create a snapshot of the provided state.

        Args:
            states: Dictionary of state values to snapshot
            namespace: Optional namespace identifier for this snapshot

        Returns:
            Snapshot ID (UUID string)
        """
        with self._lock:
            snapshot = StateSnapshot(states, namespace)

            # Limit number of snapshots (remove oldest if at capacity)
            if len(self._snapshots) >= self._max_snapshots:
                self._snapshots.popitem(last=False)

            self._snapshots[snapshot.id] = snapshot
            self.snapshot_created.emit(snapshot.id)
            return snapshot.id

    def restore_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """
        Retrieve state from a snapshot.

        Args:
            snapshot_id: ID of snapshot to restore

        Returns:
            Dictionary of snapshot states, or None if not found
        """
        with self._lock:
            if snapshot_id not in self._snapshots:
                return None

            snapshot = self._snapshots[snapshot_id]
            self.snapshot_restored.emit(snapshot_id)
            return snapshot.states.copy()

    def get_snapshot(self, snapshot_id: str) -> StateSnapshot | None:
        """
        Get a snapshot by ID.

        Args:
            snapshot_id: ID of snapshot to retrieve

        Returns:
            StateSnapshot or None if not found
        """
        with self._lock:
            return self._snapshots.get(snapshot_id)

    def get_snapshot_namespace(self, snapshot_id: str) -> str | None:
        """
        Get the namespace of a snapshot.

        Args:
            snapshot_id: ID of snapshot

        Returns:
            Namespace string or None
        """
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            return snapshot.namespace if snapshot else None

    def list_snapshots(self) -> list[str]:
        """
        List all snapshot IDs in creation order.

        Returns:
            List of snapshot IDs (oldest first)
        """
        with self._lock:
            return list(self._snapshots.keys())

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """
        Delete a specific snapshot.

        Args:
            snapshot_id: ID of snapshot to delete

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if snapshot_id in self._snapshots:
                del self._snapshots[snapshot_id]
                return True
            return False

    def clear(self) -> None:
        """Clear all snapshots."""
        with self._lock:
            self._snapshots.clear()

    @property
    def count(self) -> int:
        """Get the number of stored snapshots."""
        with self._lock:
            return len(self._snapshots)

    @property
    def max_snapshots(self) -> int:
        """Get the maximum number of snapshots allowed."""
        return self._max_snapshots

    def cleanup(self) -> None:
        """Clean up resources."""
        self.clear()
