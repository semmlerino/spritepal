"""
Worker Manager for consistent QThread worker lifecycle management.

This module provides simplified worker management that matches the patterns
used throughout the SpritePal codebase:
- Safe cleanup with cancel() and wait() (no dangerous terminate())
- Qt's built-in cancellation support via requestInterruption()
- Proper timeout handling with multiple attempts
- Consistent logging and error reporting

Note: This module was moved from ui/common/worker_manager.py to core/services/
to fix layer boundary violations (core was importing from ui).
"""
from __future__ import annotations

import contextlib
from typing import Any

from PySide6.QtCore import QThread

from utils.logging_config import get_logger

logger = get_logger(__name__)

class WorkerManager:
    """
    Safe helper for managing QThread worker lifecycle.

    This class provides:
    - Safe worker cancellation patterns (no terminate())
    - Qt's built-in cancellation via requestInterruption()
    - Graceful shutdown with timeout handling
    - Debug logging for worker operations

    CRITICAL: Never uses QThread.terminate() which can corrupt Qt's internal state.
    Instead uses a multi-stage shutdown process:
    1. Call if hasattr(worker, "cancel"):
     worker.cancel()  # type: ignore[attr-defined] if available (BaseWorker pattern)
    2. Use Qt's requestInterruption() mechanism
    3. Call quit() and wait() for clean shutdown
    4. Log warnings for unresponsive workers
    """

    @staticmethod
    def cleanup_worker(
        worker: QThread | None,
        timeout: int = 5000,
        enable_force_cleanup: bool = False
    ) -> None:
        """
        Safely clean up a worker thread without using dangerous terminate().

        Uses a multi-stage approach:
        1. Request cancellation via if hasattr(worker, "cancel"):
     worker.cancel()  # type: ignore[attr-defined] if available
        2. Use Qt's requestInterruption() mechanism
        3. Call quit() and wait() for clean shutdown
        4. Log warnings for unresponsive workers (never terminate)

        Args:
            worker: The worker thread to clean up (can be None)
            timeout: Milliseconds to wait for graceful shutdown (default: 5000)
            enable_force_cleanup: DEPRECATED - kept for backwards compatibility.
                                 This parameter is ignored as terminate() is never used.

        Note:
            The enable_force_cleanup parameter is deprecated and ignored.
            This method will never use terminate() regardless of this setting.
        """
        if worker is None:
            return

        worker_name = worker.__class__.__name__

        if not worker.isRunning():
            logger.debug(f"{worker_name} already stopped")
            worker.deleteLater()
            return

        logger.debug(f"Stopping {worker_name} safely")

        # Stage 1: Request cancellation via cancel() if available (BaseWorker pattern)
        if hasattr(worker, "cancel") and callable(getattr(worker, "cancel", None)):
            logger.debug(f"{worker_name}: Requesting cancellation via cancel()")
            try:
                worker.cancel()  # type: ignore[attr-defined]
            except Exception as e:
                logger.warning(f"{worker_name}: Error calling cancel(): {e}")

        # Stage 2: Use Qt's built-in interruption mechanism
        logger.debug(f"{worker_name}: Requesting interruption via Qt mechanism")
        worker.requestInterruption()

        # Stage 3: Request graceful shutdown
        logger.debug(f"{worker_name}: Requesting graceful shutdown via quit()")
        worker.quit()

        # Stage 4: Wait for clean shutdown
        if worker.wait(timeout):
            logger.debug(f"{worker_name}: Stopped gracefully")
        else:
            # Worker is unresponsive - log warning but NEVER terminate
            logger.warning(
                f"{worker_name}: Did not stop within {timeout}ms. "
                "Worker may be unresponsive but will not be forcibly terminated "
                "to avoid Qt corruption. Consider reviewing worker cancellation logic."
            )

        # Schedule for deletion regardless of shutdown success
        worker.deleteLater()
        logger.debug(f"{worker_name}: Scheduled for deletion")

    @staticmethod
    def start_worker(
        worker: QThread,
        cleanup_existing: QThread | None = None,
        cleanup_timeout: int = 5000
    ) -> None:
        """
        Start a new worker, optionally cleaning up an existing one first.

        Args:
            worker: The new worker to start
            cleanup_existing: Existing worker to clean up first (optional)
            cleanup_timeout: Timeout for cleaning up existing worker (default: 5000ms)
        """
        # Clean up existing worker if provided
        if cleanup_existing is not None:
            WorkerManager.cleanup_worker(cleanup_existing, cleanup_timeout)

        # Start the new worker
        worker_name = worker.__class__.__name__
        logger.debug(f"Starting {worker_name}")
        worker.start()

    @staticmethod
    def create_and_start(
        worker_class: type,
        *args: Any,
        cleanup_existing: QThread | None = None,
        cleanup_timeout: int = 5000,
        **kwargs: Any
    ) -> QThread:
        """
        Create and start a worker in one call.

        Args:
            worker_class: The worker class to instantiate
            *args: Arguments for worker constructor
            cleanup_existing: Existing worker to clean up first (optional)
            cleanup_timeout: Timeout for cleaning up existing worker (default: 5000ms)
            **kwargs: Keyword arguments for worker constructor

        Returns:
            The newly created and started worker
        """
        # Clean up existing worker if provided
        if cleanup_existing is not None:
            WorkerManager.cleanup_worker(cleanup_existing, cleanup_timeout)

        # Create and start new worker
        worker = worker_class(*args, **kwargs)
        WorkerManager.start_worker(worker)
        return worker

    @staticmethod
    def safe_cancel_worker(
        worker: QThread | None,
        timeout: int = 3000,
        check_interruption: bool = True
    ) -> bool:
        """
        Safely cancel a running worker without terminating the thread.

        This method is designed for cancelling workers that are currently running
        but should be stopped gracefully. Unlike cleanup_worker(), this method
        focuses specifically on cancellation without deletion.

        Args:
            worker: The worker thread to cancel (can be None)
            timeout: Milliseconds to wait for cancellation (default: 3000ms)
            check_interruption: Whether to check isInterruptionRequested() (default: True)

        Returns:
            bool: True if worker was successfully cancelled or wasn't running,
                  False if worker is still running after timeout

        Note:
            This method is useful when you want to cancel a worker but keep the
            thread object alive for status checking or reuse.
        """
        if worker is None:
            return True

        worker_name = worker.__class__.__name__

        if not worker.isRunning():
            logger.debug(f"{worker_name}: Already stopped")
            return True

        logger.debug(f"{worker_name}: Requesting cancellation")

        # Stage 1: Call cancel() if available (BaseWorker pattern)
        if hasattr(worker, "cancel") and callable(getattr(worker, "cancel", None)):
            logger.debug(f"{worker_name}: Calling cancel()")
            try:
                worker.cancel()  # type: ignore[attr-defined]
            except Exception as e:
                logger.warning(f"{worker_name}: Error during cancel(): {e}")

        # Stage 2: Use Qt's built-in interruption mechanism
        worker.requestInterruption()

        # Stage 3: Wait briefly for worker to respond to cancellation
        initial_wait = min(timeout // 2, 1000)  # Wait up to 1 second initially
        if worker.wait(initial_wait):
            logger.debug(f"{worker_name}: Cancelled successfully")
            return True

        # Stage 4: Check if worker is respecting interruption requests
        if check_interruption and hasattr(worker, "isInterruptionRequested"):
            try:
                if worker.isInterruptionRequested():
                    logger.debug(f"{worker_name}: Interruption acknowledged, waiting longer")
                    remaining_timeout = timeout - initial_wait
                    if worker.wait(remaining_timeout):
                        logger.debug(f"{worker_name}: Cancelled after interruption")
                        return True
            except Exception as e:
                logger.warning(f"{worker_name}: Error checking interruption status: {e}")

        # Worker didn't respond to cancellation
        logger.warning(
            f"{worker_name}: Did not respond to cancellation within {timeout}ms. "
            "Worker may be unresponsive or not checking cancellation flags."
        )
        return False

    @staticmethod
    def is_worker_responsive(worker: QThread | None, test_timeout: int = 1000) -> bool:
        """
        Test if a worker thread is responsive to interruption requests.

        This is a diagnostic method that can help identify workers that may
        have issues with their cancellation logic.

        Args:
            worker: The worker thread to test (can be None)
            test_timeout: Milliseconds to wait for response test (default: 1000ms)

        Returns:
            bool: True if worker is responsive or not running, False if unresponsive

        Note:
            This method temporarily requests interruption to test responsiveness.
            It should only be used for diagnostics, not for actual cancellation.
        """
        if worker is None:
            return True

        worker_name = worker.__class__.__name__

        if not worker.isRunning():
            logger.debug(f"{worker_name}: Not running, considered responsive")
            return True

        # Test interruption responsiveness
        logger.debug(f"{worker_name}: Testing responsiveness")

        # Store original interruption state if possible
        if hasattr(worker, "isInterruptionRequested"):
            with contextlib.suppress(Exception):
                worker.isInterruptionRequested()

        try:
            # Request interruption for testing
            worker.requestInterruption()

            # Brief wait to see if worker responds
            responsive = worker.wait(test_timeout)

            if responsive:
                logger.debug(f"{worker_name}: Responsive to interruption")
            else:
                logger.debug(f"{worker_name}: No response to interruption within {test_timeout}ms")

        except Exception as e:
            logger.warning(f"{worker_name}: Error during responsiveness test: {e}")
            return False
        else:
            return responsive
