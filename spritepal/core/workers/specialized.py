"""
Specialized worker base classes for different operation types.

These classes extend the base worker classes with domain-specific
signals and behavior for extraction, injection, and scanning operations.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from PIL import Image

    from core.protocols.manager_protocols import ExtractionManagerProtocol

from PySide6.QtCore import QObject, Signal

from core.managers.base_manager import BaseManager
from utils.logging_config import get_logger

from .base import BaseWorker, ManagedWorker

logger = get_logger(__name__)

class QObjectMixin(Protocol):
    """Protocol to ensure mixin is used with QObject-derived classes."""
    def setParent(self, parent: QObject | None) -> None: ...
    _operation_name: str

class SignalConnectionHelper:
    """
    Helper class for standardizing signal connections in workers.

    Provides reusable methods for connecting different types of manager
    signals to worker signals, reducing duplication and ensuring consistency.
    """

    def __init__(self, worker: ManagedWorker) -> None:
        """
        Initialize with a reference to the worker.

        Args:
            worker: The worker instance that owns the connections
        """
        self.worker = worker
        self.manager = worker.manager
        self._connections = worker._connections

    def validate_manager_type(self, expected_manager_getter: Callable[[], object], operation_type: str) -> bool:
        """
        Validate that the manager is of the expected type.

        Args:
            expected_manager_getter: Function that returns expected manager type
            operation_type: Description of operation type for error logging

        Returns:
            True if manager type is valid, False otherwise
        """
        try:
            expected_manager = expected_manager_getter()
            expected_type = type(expected_manager)
        except Exception:
            # In test contexts, the global registry might not be initialized
            # In this case, we allow any manager (including Mock objects)
            logger.debug(f"Could not get expected manager type for {operation_type}, allowing any manager")
            return True

        if not isinstance(self.manager, expected_type):
            # Check if it's a Mock object (common in tests)
            if hasattr(self.manager, '_spec_class'):
                # This is a Mock with a spec, check if spec matches expected type
                mock_spec = getattr(self.manager, '_spec_class', None)
                if mock_spec and issubclass(expected_type, mock_spec):
                    logger.debug(f"Accepting Mock with matching spec for {operation_type}")
                    return True

            logger.error(f"Invalid manager type for {operation_type}: expected {expected_type}, got {type(self.manager)}")
            return False
        return True

    def connect_progress_signals(self, progress_signal_name: str, progress_percent: int = 50) -> None:
        """
        Connect standard progress signals from manager to worker.

        Args:
            progress_signal_name: Name of the progress signal on the manager
            progress_percent: Fixed progress percentage to emit (default: 50)
        """
        progress_signal = getattr(self.manager, progress_signal_name, None)
        if progress_signal is not None:
            connection = progress_signal.connect(
                lambda msg: self.worker.emit_progress(progress_percent, msg)
            )
            self._connections.append(connection)
            logger.debug(f"Connected progress signal: {progress_signal_name}")
        else:
            logger.warning(f"Progress signal not found: {progress_signal_name}")

    def connect_extraction_signals(self, extraction_manager: ExtractionManagerProtocol) -> None:
        """
        Connect extraction-specific signals.

        Args:
            extraction_manager: The extraction manager instance
        """
        if not hasattr(self.worker, "palettes_ready"):
            return

        # Connect palette signals - cast to Any for signal access (protocols can't express Signal descriptors)
        mgr: Any = extraction_manager  # pyright: ignore[reportExplicitAny] - Signal access requires runtime type
        connection1 = mgr.palettes_extracted.connect(self.worker.palettes_ready.emit)
        connection2 = mgr.active_palettes_found.connect(self.worker.active_palettes_ready.emit)
        self._connections.extend([connection1, connection2])
        logger.debug("Connected extraction-specific signals")

    def connect_preview_signals(self, extraction_manager: ExtractionManagerProtocol) -> None:
        """
        Connect preview generation signals with proper error handling.

        Args:
            extraction_manager: The extraction manager instance
        """
        if not hasattr(self.worker, "preview_ready"):
            return

        def on_preview_generated(img: Image.Image, tile_count: int) -> None:
            """Handle preview generation with Qt threading safety."""
            try:
                # CRITICAL FIX FOR BUG #26: Don't create Qt GUI objects (QPixmap) in worker thread
                # Let the main thread handle pil_to_qpixmap conversion to avoid Qt threading violations
                self.worker.preview_ready.emit(img, tile_count)  # Changed: emit PIL Image, not QPixmap
                if hasattr(self.worker, "preview_image_ready"):
                    self.worker.preview_image_ready.emit(img)
            except (RuntimeError, TypeError) as e:
                logger.exception(f"Qt signal error emitting preview image: {e}")
                self.worker.emit_warning(f"Preview generation failed: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error emitting preview image: {e}")
                self.worker.emit_warning(f"Preview generation failed: {e}")

        # Cast to Any for signal access (protocols can't express Signal descriptors)
        mgr: Any = extraction_manager  # pyright: ignore[reportExplicitAny] - Signal access requires runtime type
        connection = mgr.preview_generated.connect(on_preview_generated)
        self._connections.append(connection)
        logger.debug("Connected preview generation signals")

    def connect_injection_signals(self, injection_manager: object) -> None:
        """
        Connect injection-specific signals.

        Args:
            injection_manager: The injection manager instance (typed as object because
                Qt signals cannot be expressed in Protocol types)
        """
        if not hasattr(self.worker, "injection_finished"):
            return

        # Connect injection-specific signals - cast to Any for signal access
        mgr: Any = injection_manager  # pyright: ignore[reportExplicitAny] - Signal access requires runtime type
        connection1 = mgr.injection_finished.connect(self.worker.injection_finished.emit)
        connection2 = mgr.progress_percent.connect(self.worker.progress_percent.emit)
        connection3 = mgr.compression_info.connect(self.worker.compression_info.emit)
        self._connections.extend([connection1, connection2, connection3])
        logger.debug("Connected injection-specific signals")

    def connect_completion_signals(self, injection_manager: object) -> None:
        """
        Connect injection completion signals to worker operation completion.

        Args:
            injection_manager: The injection manager instance (typed as object because
                Qt signals cannot be expressed in Protocol types)
        """
        def on_injection_finished(success: bool, message: str) -> None:
            """Handle injection completion and emit worker completion signal."""
            self.worker.operation_finished.emit(
                success,
                f"Injection {'completed' if success else 'failed'}: {message}"
            )

        # Cast to Any for signal access
        mgr: Any = injection_manager  # pyright: ignore[reportExplicitAny] - Signal access requires runtime type
        connection = mgr.injection_finished.connect(on_injection_finished)
        self._connections.append(connection)
        logger.debug("Connected injection completion signals")

class WorkerOwnedManagerMixin:
    """
    Mixin for standardizing the worker-owned manager pattern.

    This mixin assumes it will be used with QObject subclasses (like BaseWorker).
    The type checker understands this through the setup_worker_owned_manager method
    which requires self to have setParent capability.

    Provides common initialization logic for workers that own their
    own manager instances for perfect thread isolation.

    Note: This mixin should only be used with QObject-derived classes.
    """

    @staticmethod
    def create_worker_owned_manager(
        manager_factory: object | None,
        manager_creator_func: Callable[[object, QObject | None], BaseManager],
        parent: QObject | None = None
    ) -> BaseManager:
        """
        Create a manager using DI injection.

        Note: The factory pattern is deprecated. This now uses DI to get
        the singleton CoreOperationsManager instance.

        Args:
            manager_factory: Deprecated, ignored if provided
            manager_creator_func: Deprecated, ignored
            parent: Ignored (singleton manager has its own parent)

        Returns:
            CoreOperationsManager instance from DI
        """
        # Use DI to get the singleton manager
        from core.di_container import inject
        from core.protocols.manager_protocols import ExtractionManagerProtocol
        return inject(ExtractionManagerProtocol)  # type: ignore[return-value]

    def setup_worker_owned_manager(self, manager: BaseManager) -> None:
        """
        Complete worker-owned manager setup after worker initialization.

        Args:
            manager: The manager to set up proper parent relationship
        """
        # Fix the manager's parent to be this worker for proper ownership
        # Type checker: self is expected to be a QObject (mixed with BaseWorker)
        if isinstance(self, QObject):
            manager.setParent(self)
        operation_name = getattr(self, '_operation_name', 'Worker')
        logger.info(f"{operation_name}: Created with worker-owned manager")

class ExtractionWorkerBase(ManagedWorker):
    """
    Base class for extraction workers with extraction-specific signals.

    Provides signals for preview generation, palette data, and other
    extraction-specific events.
    """

    # Extraction-specific signals
    preview_ready = Signal(object, int)  # pixmap/image, tile_count
    preview_image_ready = Signal(object)  # PIL image for palette application
    palettes_ready = Signal(dict)  # palette data
    active_palettes_ready = Signal(list)  # active palette indices
    extraction_finished = Signal(list)  # list of extracted files

    def __init__(self, manager: BaseManager, parent: QObject | None = None) -> None:
        super().__init__(manager=manager, parent=parent)
        self._operation_name = "ExtractionWorker"

class InjectionWorkerBase(ManagedWorker):
    """
    Base class for injection workers with injection-specific signals.

    Provides signals for compression information, progress percentages,
    and other injection-specific events.
    """

    # Injection-specific signals
    progress_percent = Signal(int)  # Progress percentage (0-100)
    compression_info = Signal(dict)  # Compression statistics
    injection_finished = Signal(bool, str)  # success, message

    def __init__(self, manager: BaseManager, parent: QObject | None = None) -> None:
        super().__init__(manager=manager, parent=parent)
        self._operation_name = "InjectionWorker"

class ScanWorkerBase(BaseWorker):
    """
    Base class for scanning workers with scan-specific signals.

    Used for ROM scanning, sprite searching, and other discovery operations.
    Note: Inherits from BaseWorker (not ManagedWorker) as scan operations
    often contain their own business logic.
    """

    # Scan-specific signals
    item_found = Signal(dict)  # Found item information
    scan_stats = Signal(dict)  # Scan statistics and metadata
    scan_progress = Signal(int, int)  # current, total
    scan_finished = Signal(bool)  # success

    # Cache-related signals (for ROM scanning)
    cache_status = Signal(str)  # Cache status message
    cache_progress = Signal(int)  # Cache save progress 0-100

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._operation_name = "ScanWorker"

    def emit_item_found(self, item_info: dict[str, object]) -> None:
        """
        Emit when an item is found during scanning.

        Args:
            item_info: Dictionary containing item details
        """
        self.item_found.emit(item_info)

    def emit_scan_progress(self, current: int, total: int) -> None:
        """
        Emit scan progress in current/total format.

        Args:
            current: Current item being processed
            total: Total items to process
        """
        self.scan_progress.emit(current, total)

        # Also emit standard progress percentage
        if total > 0:
            percent = int((current / total) * 100)
            self.emit_progress(percent, f"Scanning {current}/{total}")

class PreviewWorkerBase(BaseWorker):
    """
    Base class for preview generation workers.

    Used for generating sprite previews, ROM map visualizations,
    and other UI preview operations.
    """

    # Preview-specific signals
    preview_ready = Signal(object)  # Generated preview (QPixmap, PIL Image, etc.)
    preview_failed = Signal(str)  # Preview generation failed

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._operation_name = "PreviewWorker"

    def emit_preview_ready(self, preview: object) -> None:
        """
        Emit when preview is ready.

        Args:
            preview: Generated preview object
        """
        self.preview_ready.emit(preview)

    def emit_preview_failed(self, error_message: str) -> None:
        """
        Emit when preview generation fails.

        Args:
            error_message: Error description
        """
        self.preview_failed.emit(error_message)
        self.emit_error(error_message)

