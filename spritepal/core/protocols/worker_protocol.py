"""
Protocol for worker lifecycle management.

This protocol defines the interface for managing QThread worker lifecycle,
enabling core/ to depend on the interface without importing from ui/.
"""
from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QThread


class WorkerManagerProtocol(Protocol):
    """Protocol for managing worker thread lifecycle."""

    @staticmethod
    def cleanup_worker(
        worker: QThread | None,
        timeout: int = 5000,
        enable_force_cleanup: bool = False
    ) -> None:
        """
        Safely clean up a worker thread.

        Args:
            worker: The worker thread to clean up (can be None)
            timeout: Milliseconds to wait for graceful shutdown
            enable_force_cleanup: Deprecated parameter (ignored)
        """
        ...
