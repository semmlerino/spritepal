"""
Signal connection helper for worker threads.

Provides reusable methods for connecting manager signals to worker signals,
reducing boilerplate and ensuring consistent signal wiring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL import Image

    from core.managers.core_operations_manager import CoreOperationsManager

from utils.logging_config import get_logger

from .base import ManagedWorker

logger = get_logger(__name__)


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

    def validate_manager_type(self, expected_type: type, operation_type: str) -> bool:
        """
        Validate that the manager is of the expected type.

        Args:
            expected_type: The expected manager class type
            operation_type: Description of operation type for error logging

        Returns:
            True if manager type is valid, False otherwise
        """
        if not isinstance(self.manager, expected_type):
            # Check if it's a Mock object (common in tests)
            if hasattr(self.manager, "_spec_class"):
                # This is a Mock with a spec, check if spec matches expected type
                mock_spec = getattr(self.manager, "_spec_class", None)
                if mock_spec and issubclass(expected_type, mock_spec):
                    logger.debug(f"Accepting Mock with matching spec for {operation_type}")
                    return True

            logger.error(
                f"Invalid manager type for {operation_type}: expected {expected_type}, got {type(self.manager)}"
            )
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
            connection = progress_signal.connect(lambda msg: self.worker.emit_progress(progress_percent, msg))
            self._connections.append(connection)
            logger.debug(f"Connected progress signal: {progress_signal_name}")
        else:
            logger.warning(f"Progress signal not found: {progress_signal_name}")

    def connect_extraction_signals(self, extraction_manager: CoreOperationsManager) -> None:
        """
        Connect extraction-specific signals.

        Args:
            extraction_manager: The extraction manager instance
        """
        # Connect palette signals - cast to Any for signal access (protocols can't express Signal descriptors)
        mgr: Any = extraction_manager  # pyright: ignore[reportExplicitAny] - Signal access requires runtime type
        connection1 = mgr.palettes_extracted.connect(self.worker.palettes_ready.emit)
        connection2 = mgr.active_palettes_found.connect(self.worker.active_palettes_ready.emit)
        self._connections.extend([connection1, connection2])
        logger.debug("Connected extraction-specific signals")

    def connect_preview_signals(self, extraction_manager: CoreOperationsManager) -> None:
        """
        Connect preview generation signals with proper error handling.

        Args:
            extraction_manager: The extraction manager instance
        """
        def on_preview_generated(img: Image.Image, tile_count: int) -> None:
            """Handle preview generation with Qt threading safety."""
            try:
                # CRITICAL FIX FOR BUG #26: Don't create Qt GUI objects (QPixmap) in worker thread
                # Let the main thread handle pil_to_qpixmap conversion to avoid Qt threading violations
                self.worker.preview_ready.emit(img, tile_count)  # Changed: emit PIL Image, not QPixmap
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
            self.worker.operation_finished.emit(success, f"Injection {'completed' if success else 'failed'}: {message}")

        # Cast to Any for signal access
        mgr: Any = injection_manager  # pyright: ignore[reportExplicitAny] - Signal access requires runtime type
        connection = mgr.injection_finished.connect(on_injection_finished)
        self._connections.append(connection)
        logger.debug("Connected injection completion signals")
