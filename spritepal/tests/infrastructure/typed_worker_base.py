"""
Typed Worker Base for type-safe worker testing.

This module provides generic base classes and patterns for testing workers
with compile-time type safety, eliminating the need for unsafe cast() operations.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Generic, TypeVar, cast

from core.managers.base_manager import BaseManager
from PySide6.QtCore import QObject, QThread, Signal
from ui.common.worker_manager import WorkerManager

# Type variables for generic typing
M = TypeVar("M", bound=BaseManager)
W = TypeVar("W", bound=QThread)
P = TypeVar("P")  # Parameter type
R = TypeVar("R")  # Result type

class TypedWorkerBase(QThread, Generic[M, P, R]):
    """
    Generic base class for type-safe workers.

    Provides compile-time type safety for:
    - Manager type (M)
    - Parameter type (P)
    - Result type (R)
    """

    # Type-safe signals
    started_signal = Signal()
    progress_signal = Signal(int)
    result_signal = Signal(object)  # Will contain R type
    error_signal = Signal(str, object)  # Use 'object' for safer Qt meta-type handling
    finished_signal = Signal()

    def __init__(self, manager: M, params: P, parent: QObject | None = None):
        """
        Initialize typed worker.

        Args:
            manager: Typed manager instance
            params: Typed parameters
            parent: Optional parent object
        """
        super().__init__(parent)
        self._manager: M = manager
        self._params: P = params
        self._result: R | None = None
        self._error: Exception | None = None
        self._interrupted = False

    @property
    def manager(self) -> M:
        """Get the typed manager."""
        return self._manager

    @property
    def params(self) -> P:
        """Get the typed parameters."""
        return self._params

    @property
    def result(self) -> R | None:
        """Get the typed result."""
        return self._result

    @property
    def error(self) -> Exception | None:
        """Get any error that occurred."""
        return self._error

    def run(self) -> None:
        """Execute the worker task."""
        try:
            self.started_signal.emit()

            # Check for interruption
            if self.isInterruptionRequested():
                self._interrupted = True
                return

            # Execute the work
            self._result = self._execute_work()

            # Emit result if not interrupted
            if not self.isInterruptionRequested():
                self.result_signal.emit(self._result)

        except Exception as e:
            self._error = e
            self.error_signal.emit(str(e), e)
        finally:
            self.finished_signal.emit()

    @abstractmethod
    def _execute_work(self) -> R:
        """
        Execute the actual work.

        Must be implemented by subclasses.

        Returns:
            Typed result
        """
        raise NotImplementedError

    def check_interruption(self) -> bool:
        """
        Check if worker has been interrupted.

        Returns:
            True if interrupted
        """
        return self.isInterruptionRequested() or self._interrupted

    def emit_progress(self, value: int) -> None:
        """
        Emit progress update.

        Args:
            value: Progress value (0-100)
        """
        if not self.check_interruption():
            self.progress_signal.emit(value)

class ExtractionWorkerBase(TypedWorkerBase[M, P, R]):
    """
    Base class for extraction workers with type safety.
    """

    # Additional extraction-specific signals
    sprite_found_signal = Signal(int, object)
    preview_ready_signal = Signal(bytes)

    def emit_sprite_found(self, offset: int, sprite_data: Any) -> None:
        """
        Emit sprite found signal.

        Args:
            offset: Sprite offset
            sprite_data: Sprite data
        """
        if not self.check_interruption():
            self.sprite_found_signal.emit(offset, sprite_data)

    def emit_preview_ready(self, preview_data: bytes) -> None:
        """
        Emit preview ready signal.

        Args:
            preview_data: Preview image data
        """
        if not self.check_interruption():
            self.preview_ready_signal.emit(preview_data)

class InjectionWorkerBase(TypedWorkerBase[M, P, R]):
    """
    Base class for injection workers with type safety.
    """

    # Additional injection-specific signals
    validation_complete_signal = Signal(bool, str)
    compression_progress_signal = Signal(int)

    def emit_validation_complete(self, valid: bool, message: str) -> None:
        """
        Emit validation complete signal.

        Args:
            valid: Whether validation passed
            message: Validation message
        """
        if not self.check_interruption():
            self.validation_complete_signal.emit(valid, message)

    def emit_compression_progress(self, progress: int) -> None:
        """
        Emit compression progress signal.

        Args:
            progress: Compression progress (0-100)
        """
        if not self.check_interruption():
            self.compression_progress_signal.emit(progress)

class WorkerTestHelper(Generic[W]):
    """
    Helper class for testing workers with type safety.
    """

    def __init__(self, worker_class: type[W]):
        """
        Initialize worker test helper.

        Args:
            worker_class: The worker class to test
        """
        self._worker_class = worker_class
        self._worker: W | None = None
        self._worker_manager = WorkerManager()
        self._signals_received: dict[str, list[Any]] = {}

    def create_worker(self, *args: Any, **kwargs: Any) -> W:
        """
        Create a worker instance.

        Args:
            *args: Positional arguments for worker
            **kwargs: Keyword arguments for worker

        Returns:
            Created worker instance
        """
        self._worker = self._worker_class(*args, **kwargs)
        self._connect_signals()
        return self._worker

    def _connect_signals(self) -> None:
        """Connect to worker signals for monitoring."""
        if not self._worker:
            return

        # Connect to standard signals if they exist
        signal_names = [
            "started_signal", "progress_signal", "result_signal",
            "error_signal", "finished_signal", "sprite_found_signal",
            "preview_ready_signal", "validation_complete_signal",
            "compression_progress_signal"
        ]

        for signal_name in signal_names:
            if hasattr(self._worker, signal_name):
                signal = getattr(self._worker, signal_name)
                self._signals_received[signal_name] = []
                signal.connect(lambda *args, name=signal_name:
                             self._signals_received[name].append(args))

    def run_and_wait(self, timeout: int = 5000) -> bool:
        """
        Run the worker and wait for completion.

        Args:
            timeout: Maximum time to wait in milliseconds

        Returns:
            True if completed, False if timeout
        """
        if not self._worker:
            raise RuntimeError("No worker created")

        self._worker.start()
        return self._worker.wait(timeout)

    def get_signal_data(self, signal_name: str) -> list[Any]:
        """
        Get data received from a signal.

        Args:
            signal_name: Name of the signal

        Returns:
            List of signal emissions
        """
        return self._signals_received.get(signal_name, [])

    def was_signal_emitted(self, signal_name: str) -> bool:
        """
        Check if a signal was emitted.

        Args:
            signal_name: Name of the signal

        Returns:
            True if signal was emitted
        """
        return len(self.get_signal_data(signal_name)) > 0

    def cleanup(self) -> None:
        """Clean up the worker."""
        if self._worker:
            self._worker_manager.cleanup_worker(self._worker)
            self._worker = None
        self._signals_received.clear()

class TypedWorkerValidator:
    """
    Validator for ensuring worker type safety.
    """

    @staticmethod
    def validate_manager_type(worker: Any, expected_manager_type: type[M]) -> M:
        """
        Validate and return typed manager from worker.

        Args:
            worker: Worker instance
            expected_manager_type: Expected manager type

        Returns:
            Typed manager instance

        Raises:
            TypeError: If manager type doesn't match
        """
        if not hasattr(worker, "manager"):
            raise AttributeError(f"Worker {type(worker).__name__} has no manager attribute")

        manager = worker.manager
        if not isinstance(manager, expected_manager_type):
            raise TypeError(
                f"Worker manager is {type(manager).__name__}, "
                f"expected {expected_manager_type.__name__}"
            )

        return cast(M, manager)

    @staticmethod
    def validate_params_type(worker: Any, expected_params_type: type[P]) -> P:
        """
        Validate and return typed parameters from worker.

        Args:
            worker: Worker instance
            expected_params_type: Expected parameters type

        Returns:
            Typed parameters

        Raises:
            TypeError: If parameters type doesn't match
        """
        if not hasattr(worker, "params"):
            raise AttributeError(f"Worker {type(worker).__name__} has no params attribute")

        params = worker.params

        # Handle dict types specially
        if expected_params_type is dict:
            if not isinstance(params, dict):
                raise TypeError(f"Worker params is {type(params).__name__}, expected dict")
        elif not isinstance(params, expected_params_type):
            raise TypeError(
                f"Worker params is {type(params).__name__}, "
                f"expected {expected_params_type.__name__}"
            )

        return cast(P, params)

    @staticmethod
    def validate_result_type(worker: Any, expected_result_type: type[R]) -> R | None:
        """
        Validate and return typed result from worker.

        Args:
            worker: Worker instance
            expected_result_type: Expected result type

        Returns:
            Typed result or None

        Raises:
            TypeError: If result type doesn't match
        """
        if not hasattr(worker, "result"):
            raise AttributeError(f"Worker {type(worker).__name__} has no result attribute")

        result = worker.result
        if result is not None and not isinstance(result, expected_result_type):
            raise TypeError(
                f"Worker result is {type(result).__name__}, "
                f"expected {expected_result_type.__name__}"
            )

        return cast(R | None, result)

# Example concrete implementations for testing

class TypedExtractionWorker(ExtractionWorkerBase["ExtractionManager", dict[str, Any], list[Any]]):
    """
    Example extraction worker for testing.
    """

    def _execute_work(self) -> list[Any]:
        """Execute extraction work."""
        results = []

        # Simulate extraction with progress
        for i in range(10):
            if self.check_interruption():
                break

            self.emit_progress(i * 10)

            # Simulate finding a sprite
            if i % 3 == 0:
                sprite_data = {"offset": i * 0x1000, "size": 0x800}
                self.emit_sprite_found(i * 0x1000, sprite_data)
                results.append(sprite_data)

        return results

class TypedInjectionWorker(InjectionWorkerBase["InjectionManager", dict[str, Any], bool]):
    """
    Example injection worker for testing.
    """

    def _execute_work(self) -> bool:
        """Execute injection work."""
        # Validate parameters
        self.emit_validation_complete(True, "Parameters valid")

        # Simulate compression
        for i in range(10):
            if self.check_interruption():
                return False

            self.emit_compression_progress(i * 10)

        return True

# Pytest fixtures (if pytest is available)
try:
    import pytest
    from core.managers.extraction_manager import ExtractionManager  # noqa: F401
    from core.managers.injection_manager import InjectionManager  # noqa: F401

    @pytest.fixture
    def extraction_worker_helper():
        """Pytest fixture for extraction worker testing."""
        helper = WorkerTestHelper(TypedExtractionWorker)
        yield helper
        helper.cleanup()

    @pytest.fixture
    def injection_worker_helper():
        """Pytest fixture for injection worker testing."""
        helper = WorkerTestHelper(TypedInjectionWorker)
        yield helper
        helper.cleanup()

    @pytest.fixture
    def worker_validator():
        """Pytest fixture for worker type validation."""
        return TypedWorkerValidator()

except ImportError:
    # pytest not available, fixtures won't be registered
    pass
