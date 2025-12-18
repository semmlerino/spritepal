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

# Timeout constants for worker cleanup
DEFAULT_CLEANUP_TIMEOUT = 1000  # 1 second - reasonable for most workers
QUICK_CLEANUP_TIMEOUT = 100  # 100ms - for application shutdown scenarios

class WorkerManager:
    """
    Safe helper for managing QThread worker lifecycle.

    This class provides:
    - Safe worker cancellation patterns (no terminate())
    - Qt's built-in cancellation via requestInterruption()
    - Graceful shutdown with timeout handling
    - Debug logging for worker operations
    - Global worker registry for cleanup_all()

    CRITICAL: Never uses QThread.terminate() which can corrupt Qt's internal state.
    Instead uses a multi-stage shutdown process:
    1. Call if hasattr(worker, "cancel"):
     worker.cancel()  # type: ignore[attr-defined] if available (BaseWorker pattern)
    2. Use Qt's requestInterruption() mechanism
    3. Call quit() and wait() for clean shutdown
    4. Log warnings for unresponsive workers
    """

    # Class-level registry of all workers for cleanup_all()
    # Use strong references to ensure workers aren't GC'd before cleanup
    # Workers are removed from registry after cleanup or when they finish
    _worker_registry: set[QThread] = set()

    @staticmethod
    def _register_worker(worker: QThread) -> None:
        """
        Register a worker in the global registry for cleanup_all().

        Workers remain in the registry until explicitly cleaned up via
        cleanup_all() or cleanup_worker(). This ensures they're properly
        stopped and waited for before removal.

        Args:
            worker: Worker to register
        """
        # Add worker to registry
        WorkerManager._worker_registry.add(worker)
        logger.debug(f"Registered worker {worker.__class__.__name__} (registry size: {len(WorkerManager._worker_registry)})")

    @staticmethod
    def cleanup_worker(
        worker: QThread | None,
        timeout: int = DEFAULT_CLEANUP_TIMEOUT,
        enable_force_cleanup: bool = False
    ) -> None:
        """
        Safely clean up a worker thread without using dangerous terminate().

        Uses a multi-stage approach:
        1. Request cancellation via cancel() if available (BaseWorker pattern)
        2. Use Qt's requestInterruption() mechanism
        3. Call quit() and wait() for clean shutdown
        4. Log warnings for unresponsive workers (never terminate)

        Args:
            worker: The worker thread to clean up (can be None)
            timeout: Milliseconds to wait for graceful shutdown (default: 1000ms).
                    Use QUICK_CLEANUP_TIMEOUT (100ms) for shutdown scenarios.
            enable_force_cleanup: DEPRECATED - kept for backwards compatibility.
                                 This parameter is ignored as terminate() is never used.

        Note:
            The enable_force_cleanup parameter is deprecated and ignored.
            This method will never use terminate() regardless of this setting.
        """
        if worker is None:
            return

        # Block signals FIRST to prevent race conditions with queued signals
        # This ensures no callbacks fire on deleted objects during cleanup
        worker.blockSignals(True)

        worker_name = worker.__class__.__name__

        if not worker.isRunning():
            logger.debug(f"{worker_name} already stopped (isFinished: {worker.isFinished()})")
            # Even if not running, wait to ensure thread has fully exited
            # QThread may have emitted finished() but not yet fully cleaned up the OS thread
            if not worker.isFinished():
                # If not finished, wait for it to finish
                worker.wait(timeout)
            else:
                # Already finished, but still wait to ensure OS thread cleanup
                worker.wait(200)  # Wait for OS thread to fully exit
            WorkerManager._worker_registry.discard(worker)
            worker.deleteLater()
            logger.debug(f"{worker_name}: Cleanup complete for stopped worker")
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

        # Additional wait to ensure thread has fully exited
        # This helps prevent thread leak detection from seeing the thread
        if worker.isFinished():
            # Thread has signaled finished, wait a bit more for complete cleanup
            worker.wait(50)  # Extra 50ms to ensure thread exit is complete

        # Remove from registry
        WorkerManager._worker_registry.discard(worker)

        # Schedule for deletion regardless of shutdown success
        worker.deleteLater()
        logger.debug(f"{worker_name}: Scheduled for deletion")

    @staticmethod
    def start_worker(
        worker: QThread,
        cleanup_existing: QThread | None = None,
        cleanup_timeout: int = DEFAULT_CLEANUP_TIMEOUT
    ) -> None:
        """
        Start a new worker, optionally cleaning up an existing one first.

        Args:
            worker: The new worker to start
            cleanup_existing: Existing worker to clean up first (optional)
            cleanup_timeout: Timeout for cleaning up existing worker (default: 1000ms)
        """
        # Clean up existing worker if provided
        if cleanup_existing is not None:
            WorkerManager.cleanup_worker(cleanup_existing, cleanup_timeout)

        # Register the new worker for cleanup_all()
        WorkerManager._register_worker(worker)

        # Start the new worker
        worker_name = worker.__class__.__name__
        logger.debug(f"Starting {worker_name}")
        worker.start()

    @staticmethod
    def create_and_start(
        worker_class: type,
        *args: Any,
        cleanup_existing: QThread | None = None,
        cleanup_timeout: int = DEFAULT_CLEANUP_TIMEOUT,
        **kwargs: Any
    ) -> QThread:
        """
        Create and start a worker in one call.

        Args:
            worker_class: The worker class to instantiate
            *args: Arguments for worker constructor
            cleanup_existing: Existing worker to clean up first (optional)
            cleanup_timeout: Timeout for cleaning up existing worker (default: 1000ms)
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

    @staticmethod
    def quick_cleanup(worker: QThread | None) -> None:
        """
        Quick cleanup for application shutdown scenarios.

        Uses QUICK_CLEANUP_TIMEOUT (100ms) for minimal blocking during shutdown.
        Workers that don't respond quickly will be scheduled for deletion anyway.

        Args:
            worker: The worker thread to clean up (can be None)
        """
        WorkerManager.cleanup_worker(worker, timeout=QUICK_CLEANUP_TIMEOUT)

    @staticmethod
    def cleanup_workers(workers: list[QThread | None], quick: bool = False) -> None:
        """
        Clean up multiple workers efficiently.

        Args:
            workers: List of worker threads to clean up (can contain None values)
            quick: If True, use QUICK_CLEANUP_TIMEOUT for faster shutdown
        """
        timeout = QUICK_CLEANUP_TIMEOUT if quick else DEFAULT_CLEANUP_TIMEOUT
        for worker in workers:
            if worker is not None:
                WorkerManager.cleanup_worker(worker, timeout=timeout)

    @staticmethod
    def cleanup_all(timeout: int = QUICK_CLEANUP_TIMEOUT) -> int:
        """
        Clean up all registered workers.

        This method is primarily used by test fixtures to ensure all workers
        are properly cleaned up between tests. It cleans up all workers that
        were registered via start_worker() or create_and_start().

        Args:
            timeout: Timeout in milliseconds for each worker cleanup.
                    Defaults to QUICK_CLEANUP_TIMEOUT (100ms) for faster test cleanup.

        Returns:
            int: Number of workers that were cleaned up

        Note:
            This method only cleans up workers that were started through
            WorkerManager methods. Workers started directly (worker.start())
            without going through WorkerManager won't be tracked.
        """
        logger.debug(f"cleanup_all: Starting cleanup (registry size: {len(WorkerManager._worker_registry)})")

        # Get all workers from registry (they're already strong references)
        workers_to_cleanup = list(WorkerManager._worker_registry)

        logger.debug(f"cleanup_all: Found {len(workers_to_cleanup)} registered workers")

        # Clean up all workers (both running and stopped)
        cleanup_count = 0
        for worker in workers_to_cleanup:
            # Check if Qt object is still valid before accessing it
            # This prevents "Internal C++ object already deleted" errors
            try:
                from shiboken6 import isValid
                if not isValid(worker):
                    worker_name = getattr(worker, '__class__', type(worker)).__name__
                    logger.debug(f"cleanup_all: Skipping already-deleted worker {worker_name}")
                    continue
            except (ImportError, RuntimeError):
                # shiboken6 not available or worker already invalid - proceed with caution
                pass

            try:
                if worker.isRunning():
                    logger.debug(f"cleanup_all: Cleaning up running worker {worker.__class__.__name__}")
                    cleanup_count += 1
                else:
                    logger.debug(f"cleanup_all: Cleaning up stopped worker {worker.__class__.__name__}")

                # Always call cleanup_worker to ensure proper shutdown sequence
                # This handles both running and stopped workers consistently
                WorkerManager.cleanup_worker(worker, timeout=timeout)

                # Additional explicit cleanup to help with thread counting
                # Disconnect all signals to break reference cycles
                try:
                    worker.blockSignals(True)
                    # Try to set parent to None to help with cleanup
                    worker.setParent(None)
                except Exception as e:
                    logger.debug(f"Error during final cleanup of {worker.__class__.__name__}: {e}")
            except RuntimeError as e:
                # Qt object was deleted between isValid check and method call
                if "Internal C++ object" in str(e) and "already deleted" in str(e):
                    logger.debug(f"cleanup_all: Worker was deleted during cleanup: {e}")
                else:
                    raise

        # Clear the registry after cleanup (cleanup_worker removes workers individually,
        # but this ensures the registry is fully cleared)
        WorkerManager._worker_registry.clear()

        # Delete all worker references to help with immediate cleanup
        del workers_to_cleanup

        # Process Qt events to allow deleteLater() calls to complete
        # This helps ensure threads are fully cleaned up before returning
        try:
            from PySide6.QtCore import QCoreApplication
            app = QCoreApplication.instance()
            if app:
                # Process events multiple times to ensure cleanup
                for _ in range(10):
                    app.processEvents()
                logger.debug("cleanup_all: Processed Qt events for cleanup completion")
        except Exception as e:
            logger.debug(f"cleanup_all: Could not process events: {e}")

        # Force garbage collection to help clean up deleted workers
        try:
            import gc
            gc.collect()
            logger.debug("cleanup_all: Forced garbage collection")
        except Exception as e:
            logger.debug(f"cleanup_all: Could not force GC: {e}")

        # Give the OS a moment to fully destroy threads
        # This is necessary because Python's threading.active_count() may still
        # see threads that are in the process of being destroyed
        try:
            import time
            time.sleep(0.05)  # 50ms should be enough for OS thread cleanup
            logger.debug("cleanup_all: Waited for OS thread cleanup")
        except Exception as e:
            logger.debug(f"cleanup_all: Could not sleep: {e}")

        # Defensive check: Warn if there are QThreads running that weren't registered
        # This helps catch workers started directly with .start() bypassing WorkerManager
        try:
            import threading
            from PySide6.QtCore import QThread
            active_threads = threading.enumerate()
            unknown_workers = []
            for t in active_threads:
                # Check if this is a QThread-backed thread
                if 'QThread' in t.name or 'Dummy-' in t.name:
                    # Don't warn about the main thread or known helper threads
                    if t.name not in ('MainThread', 'QThread'):
                        unknown_workers.append(t.name)
            if unknown_workers:
                logger.warning(
                    f"Found {len(unknown_workers)} potential unregistered QThread(s) after cleanup: "
                    f"{unknown_workers[:5]}. Use WorkerManager.start_worker() for proper lifecycle tracking."
                )
        except Exception as e:
            logger.debug(f"cleanup_all: Could not check for unregistered workers: {e}")

        if cleanup_count > 0:
            logger.info(f"cleanup_all: Cleaned up {cleanup_count} worker(s)")
        else:
            logger.debug("cleanup_all: No workers needed cleanup")

        return cleanup_count

    @staticmethod
    def get_active_worker_count() -> int:
        """Get the number of currently registered workers.

        Returns:
            int: Number of workers in the registry (may be running or stopped)
        """
        return len(WorkerManager._worker_registry)

    @staticmethod
    def get_running_worker_count() -> int:
        """Get the number of currently running workers.

        Returns:
            int: Number of workers that are currently running
        """
        return sum(1 for w in WorkerManager._worker_registry if w.isRunning())

    @staticmethod
    def get_active_worker_names() -> list[str]:
        """Get names of all registered workers for debugging.

        Returns:
            list[str]: List of worker class names and their running status
        """
        return [
            f"{w.__class__.__name__} (running={w.isRunning()})"
            for w in WorkerManager._worker_registry
        ]

    @staticmethod
    def assert_no_active_workers(message: str = "") -> None:
        """Assert that no workers are registered (for test cleanup verification).

        This method should be called at the end of tests to verify all workers
        have been properly cleaned up. It fails with detailed information
        about any remaining workers.

        Args:
            message: Optional context message to include in failure

        Raises:
            AssertionError: If any workers are still registered
        """
        count = WorkerManager.get_active_worker_count()
        if count > 0:
            worker_info = WorkerManager.get_active_worker_names()
            msg_parts = [
                f"Expected 0 active workers, but found {count}:",
                *[f"  - {info}" for info in worker_info],
            ]
            if message:
                msg_parts.insert(0, message)
            msg_parts.append("")
            msg_parts.append("Hint: Ensure WorkerManager.cleanup_all() was called.")
            raise AssertionError("\n".join(msg_parts))
