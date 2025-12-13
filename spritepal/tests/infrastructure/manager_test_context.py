"""
Manager Test Context for proper lifecycle management in tests.

This module provides context managers and fixtures for safely managing
manager lifecycles during testing, ensuring proper initialization,
isolation, and cleanup.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Iterator
from typing import Any, TypeVar, cast

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from core.managers.base_manager import BaseManager
from core.managers.extraction_manager import ExtractionManager
from core.managers.injection_manager import InjectionManager
from core.managers.session_manager import SessionManager

from .qt_application_factory import ApplicationFactory
from .real_component_factory import RealComponentFactory
from .test_data_repository import get_test_data_repository

M = TypeVar("M", bound=BaseManager)

class ManagerTestContext:
    """
    Context manager for safe manager lifecycle management in tests.

    Provides:
    - Proper manager initialization and cleanup
    - Thread-safe operation
    - Parallel test support
    - Automatic resource cleanup
    """

    def __init__(self, ensure_qt_app: bool = True):
        """
        Initialize the manager test context.

        Args:
            ensure_qt_app: Whether to ensure QApplication exists
        """
        self._managers: dict[str, BaseManager] = {}
        self._workers: list[QThread] = []
        self._factory = RealComponentFactory()
        self._data_repo = get_test_data_repository()
        self._lock = threading.RLock()

        # Ensure QApplication for Qt components using ApplicationFactory for consistency
        # (ApplicationFactory handles offscreen args, config, and lifecycle)
        if ensure_qt_app:
            self._app = ApplicationFactory.get_application()
            self._created_app = False  # Factory manages lifecycle
        else:
            self._app = None
            self._created_app = False

        # Store original registry state for restoration
        self._original_registry_state: dict[str, Any] = {}

    def initialize_managers(self, *manager_types: str) -> None:
        """
        Initialize specified manager types.

        Args:
            *manager_types: Types of managers to initialize
                           ("extraction", "injection", "session", or "all")
        """
        with self._lock:
            if "all" in manager_types:
                manager_types = ("extraction", "injection", "session")

            for manager_type in manager_types:
                if manager_type not in self._managers:
                    self._create_manager(manager_type)

    def _create_manager(self, manager_type: str) -> BaseManager:
        """
        Create a manager of the specified type.

        Args:
            manager_type: Type of manager to create

        Returns:
            Created manager instance

        Raises:
            ValueError: If manager type is unknown
        """
        if manager_type == "extraction":
            manager = self._factory.create_extraction_manager(with_test_data=True)
        elif manager_type == "injection":
            manager = self._factory.create_injection_manager(with_test_data=True)
        elif manager_type == "session":
            manager = self._factory.create_session_manager("TestApp")
        else:
            raise ValueError(f"Unknown manager type: {manager_type}")

        self._managers[manager_type] = manager

        # Note: ManagerRegistry is a singleton that manages its own state internally
        # We don't need to manually register/unregister as the singleton pattern handles this

        return manager

    def get_manager(self, manager_type: str) -> BaseManager:
        """
        Get a manager by type.

        Args:
            manager_type: Type of manager to get

        Returns:
            Manager instance

        Raises:
            KeyError: If manager not initialized
        """
        with self._lock:
            if manager_type not in self._managers:
                self._create_manager(manager_type)
            return self._managers[manager_type]

    def get_typed_manager(self, manager_type: str, manager_class: type[M]) -> M:
        """
        Get a typed manager with compile-time type safety.

        Args:
            manager_type: Type of manager to get
            manager_class: Expected manager class for type checking

        Returns:
            Typed manager instance
        """
        manager = self.get_manager(manager_type)
        if not isinstance(manager, manager_class):
            raise TypeError(
                f"Manager '{manager_type}' is not of type {manager_class.__name__}"
            )
        return manager

    def get_extraction_manager(self) -> ExtractionManager:
        """Get the extraction manager with proper typing."""
        return self.get_typed_manager("extraction", ExtractionManager)

    def get_injection_manager(self) -> InjectionManager:
        """Get the injection manager with proper typing."""
        return self.get_typed_manager("injection", InjectionManager)

    def get_session_manager(self) -> SessionManager:
        """Get the session manager with proper typing."""
        return self.get_typed_manager("session", SessionManager)

    def create_worker(self, manager_type: str, params: dict[str, Any] | None = None) -> QThread:
        """
        Create a worker for the specified manager type.

        Args:
            manager_type: Type of manager to create worker for
            params: Optional parameters for the worker

        Returns:
            Created worker instance
        """
        self.get_manager(manager_type)

        if manager_type == "extraction":
            if params is None:
                params = self._data_repo.get_vram_extraction_data("small")
            worker = self._factory.create_extraction_worker(params)
        elif manager_type == "injection":
            if params is None:
                params = self._data_repo.get_injection_data("small")
            worker = self._factory.create_injection_worker(params)
        else:
            raise ValueError(f"No worker type for manager: {manager_type}")

        self._workers.append(worker)
        return worker

    def run_worker_and_wait(self, worker: QThread, timeout: int = 5000) -> bool:
        """
        Run a worker and wait for completion.

        Args:
            worker: Worker to run
            timeout: Maximum time to wait in milliseconds

        Returns:
            True if worker completed, False if timeout
        """
        worker.start()

        # Process events to allow signals to propagate
        if self._app:
            self._app.processEvents()

        return worker.wait(timeout)

    def cleanup_workers(self) -> None:
        """Clean up all active workers, force-terminating if necessary."""
        logger = logging.getLogger(__name__)
        for worker in self._workers:
            try:
                if worker.isRunning():
                    worker.requestInterruption()
                    worker.quit()
                    if not worker.wait(1000):
                        # Worker didn't stop gracefully - force terminate
                        logger.warning(f"Worker {worker} didn't stop in 1s, terminating")
                        worker.terminate()
                        if not worker.wait(500):
                            logger.error(f"Worker {worker} failed to terminate")
                worker.deleteLater()
            except Exception as e:
                logger.warning(f"Error cleaning up worker {worker}: {e}")

        self._workers.clear()

    def cleanup_managers(self) -> None:
        """Clean up all managers and reset global registry singleton."""
        with self._lock:
            # Clean up our managers (the ManagerRegistry is a singleton and doesn't support direct registration)
            for manager in self._managers.values():
                try:
                    if hasattr(manager, "cleanup"):
                        manager.cleanup()
                    manager.deleteLater()
                except Exception:
                    pass  # Ignore cleanup errors

            self._managers.clear()
            self._original_registry_state.clear()

            # Reset global registry singleton to prevent state pollution
            # BUT only if session_managers fixture is NOT active - otherwise
            # the session fixture owns the registry lifecycle
            try:
                from tests.fixtures.core_fixtures import is_session_managers_active

                if not is_session_managers_active():
                    # Safe to reset - no session fixture is managing the registry
                    from core.managers import cleanup_managers as registry_cleanup
                    from core.managers.registry import ManagerRegistry

                    registry_cleanup()
                    ManagerRegistry.reset_for_tests()
            except Exception:
                pass  # Best-effort cleanup

    def cleanup(self) -> None:
        """Clean up all resources."""
        self.cleanup_workers()
        self.cleanup_managers()
        self._factory.cleanup()

        # Clean up QApplication if we created it
        if self._created_app and self._app:
            self._app.quit()

    def __enter__(self) -> ManagerTestContext:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit with cleanup."""
        self.cleanup()

@contextlib.contextmanager
def manager_context(*manager_types: str) -> Iterator[ManagerTestContext]:
    """
    Context manager for testing with managers.

    Args:
        *manager_types: Types of managers to initialize

    Yields:
        ManagerTestContext with initialized managers

    Example:
        with manager_context("extraction", "injection") as ctx:
            extraction_mgr = ctx.get_extraction_manager()
            injection_mgr = ctx.get_injection_manager()
            # Test code here
    """
    context = ManagerTestContext()
    try:
        context.initialize_managers(*manager_types)
        yield context
    finally:
        context.cleanup()

@contextlib.contextmanager
def isolated_manager_test() -> Iterator[ManagerTestContext]:
    """
    Context manager for completely isolated manager testing.

    Creates a fresh manager context with no shared state.

    Yields:
        ManagerTestContext for isolated testing
    """
    # Note: ManagerRegistry is a singleton, so we can't truly isolate it
    # Instead, we create an isolated context that uses its own managers
    context = ManagerTestContext()
    try:
        yield context
    finally:
        context.cleanup()

class ParallelManagerContext:
    """
    Context for running manager tests in parallel.

    Ensures thread safety and isolation between parallel tests.
    """

    def __init__(self, num_contexts: int = 4):
        """
        Initialize parallel manager context.

        Args:
            num_contexts: Number of parallel contexts to create
        """
        self._contexts: list[ManagerTestContext] = []
        self._num_contexts = num_contexts
        self._lock = threading.RLock()
        self._available_contexts: list[ManagerTestContext] = []

    def __enter__(self) -> ParallelManagerContext:
        """Set up parallel contexts."""
        for _ in range(self._num_contexts):
            context = ManagerTestContext(ensure_qt_app=False)
            self._contexts.append(context)
            self._available_contexts.append(context)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Clean up all parallel contexts."""
        for context in self._contexts:
            context.cleanup()
        self._contexts.clear()
        self._available_contexts.clear()

    @contextlib.contextmanager
    def get_context(self) -> Iterator[ManagerTestContext]:
        """
        Get an available context for parallel testing.

        Yields:
            Available ManagerTestContext
        """
        context = None
        with self._lock:
            if self._available_contexts:
                context = self._available_contexts.pop()

        if context is None:
            # All contexts in use, create a temporary one
            context = ManagerTestContext(ensure_qt_app=False)
            temporary = True
        else:
            temporary = False

        try:
            yield context
        finally:
            if temporary:
                context.cleanup()
            else:
                with self._lock:
                    self._available_contexts.append(context)

# Pytest fixtures (if pytest is available)
try:
    import pytest

    @pytest.fixture
    def manager_test_context():
        """Pytest fixture for manager test context."""
        with manager_context("all") as ctx:
            yield ctx

    @pytest.fixture
    def extraction_manager():
        """Pytest fixture for extraction manager."""
        with manager_context("extraction") as ctx:
            yield ctx.get_extraction_manager()

    @pytest.fixture
    def injection_manager():
        """Pytest fixture for injection manager."""
        with manager_context("injection") as ctx:
            yield ctx.get_injection_manager()

    @pytest.fixture
    def session_manager():
        """Pytest fixture for session manager."""
        with manager_context("session") as ctx:
            yield ctx.get_session_manager()

    @pytest.fixture
    def isolated_test_context():
        """Pytest fixture for isolated testing."""
        with isolated_manager_test() as ctx:
            yield ctx

except ImportError:
    # pytest not available, fixtures won't be registered
    pass
