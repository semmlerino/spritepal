"""
Qt dialog signal manager component for handling standard Qt dialog signals.

This component manages standard Qt dialog signals (finished, rejected, destroyed) for composed dialogs.
It's designed to avoid Qt metaclass system issues with signals in complex inheritance hierarchies
by providing clean signal proxies in a separate QObject.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

if TYPE_CHECKING:
    from PySide6.QtGui import QCloseEvent

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog


class QtDialogSignalManager(QObject):
    """
    Manages standard Qt dialog signals for composed dialogs.

    This manager provides clean proxies for standard Qt dialog signals,
    avoiding Qt metaclass issues that occur when signals are corrupted in
    complex composed inheritance hierarchies.

    Signals:
        finished: Emitted when the dialog is finished (mirrors QDialog.finished)
        rejected: Emitted when the dialog is rejected (mirrors QDialog.rejected)
        destroyed: Emitted when the dialog is destroyed (mirrors QObject.destroyed)
    """

    # Clean proxy signals for standard Qt dialog signals
    finished = Signal(int)  # result code
    rejected = Signal()
    destroyed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        """
        Initialize the Qt dialog signal manager.

        Args:
            parent: Optional parent QObject for proper cleanup
        """
        super().__init__(parent)
        self._dialog = None

    def initialize(self, context: Any) -> None:
        """
        Initialize the manager with a dialog context.

        This method sets up the signal manager as part of the composed dialog system
        and connects the clean proxy signals to the dialog's actual Qt signals.

        Args:
            context: The dialog context containing config and dialog references

        Raises:
            AttributeError: If context doesn't have required attributes
        """
        # Check if context has required attributes
        if not hasattr(context, 'dialog'):
            raise AttributeError("Context must have a 'dialog' attribute")

        self._dialog = context.dialog

        # Connect our clean proxy signals to the dialog's Qt signals (if possible)
        self._connect_to_dialog_signals()

        # Add to context for external access
        context.qt_dialog_signals = self

        # Log successful initialization
        from utils.logging_config import get_logger
        logger = get_logger(__name__)
        logger.debug("QtDialogSignalManager initialized successfully")

    def _connect_to_dialog_signals(self) -> None:
        """
        Connect proxy signals to the dialog's actual Qt signals.

        This attempts to connect to the dialog's inherited Qt signals,
        but gracefully handles failures due to Qt metaclass issues.
        """
        from utils.logging_config import get_logger
        logger = get_logger(__name__)

        if not self._dialog:
            logger.warning("No dialog available for signal connection")
            return

        try:
            # Try to connect to dialog's inherited Qt signals
            self._dialog.finished.connect(self.finished.emit)
            self._dialog.rejected.connect(self.rejected.emit)
            self._dialog.destroyed.connect(self.destroyed.emit)
            logger.debug("Successfully connected to dialog's inherited Qt signals")
        except Exception as e:
            logger.warning(f"Could not connect to inherited Qt signals ({e}), using manual triggering")
            # If inherited signals are corrupted, we'll trigger manually in dialog methods
            self._setup_manual_triggering()

    def _setup_manual_triggering(self) -> None:
        """
        Set up manual signal triggering when inherited signals are corrupted.

        This method sets up hooks in the dialog's accept/reject methods
        to manually emit our clean proxy signals.
        """
        if not self._dialog:
            return

        # Store original methods
        original_accept = self._dialog.accept
        original_reject = self._dialog.reject
        original_close_event = getattr(self._dialog, 'closeEvent', None)

        def enhanced_accept():
            """Enhanced accept that triggers our clean signals."""
            result = original_accept()
            self.finished.emit(QDialog.DialogCode.Accepted)
            return result

        def enhanced_reject():
            """Enhanced reject that triggers our clean signals."""
            result = original_reject()
            self.rejected.emit()
            self.finished.emit(QDialog.DialogCode.Rejected)
            return result

        def enhanced_close_event(event: QCloseEvent) -> None:
            """Enhanced close event that triggers destroyed signal."""
            if original_close_event:
                original_close_event(event)
            # Emit destroyed when dialog is actually closing
            if event.isAccepted():
                self.destroyed.emit()

        # Replace dialog methods with enhanced versions
        self._dialog.accept = enhanced_accept
        self._dialog.reject = enhanced_reject
        self._dialog.closeEvent = enhanced_close_event

        from utils.logging_config import get_logger
        logger = get_logger(__name__)
        logger.debug("Manual signal triggering set up successfully")

    def emit_finished(self, result: int) -> None:
        """
        Emit the finished signal safely.

        Args:
            result: The dialog result code (QDialog.DialogCode.Accepted/Rejected)
        """
        try:
            self.finished.emit(result)
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.debug(f"[QT_SIGNAL] Emitted finished: {result}")
        except Exception as e:
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(f"[QT_SIGNAL] Failed to emit finished: {e}")

    def emit_rejected(self) -> None:
        """
        Emit the rejected signal safely.
        """
        try:
            self.rejected.emit()
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.debug("[QT_SIGNAL] Emitted rejected")
        except Exception as e:
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(f"[QT_SIGNAL] Failed to emit rejected: {e}")

    def emit_destroyed(self) -> None:
        """
        Emit the destroyed signal safely.
        """
        try:
            self.destroyed.emit()
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.debug("[QT_SIGNAL] Emitted destroyed")
        except Exception as e:
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(f"[QT_SIGNAL] Failed to emit destroyed: {e}")

    def cleanup(self) -> None:
        """
        Clean up references and resources.

        This should be called when the manager is no longer needed
        to prevent reference cycles.
        """
        self._dialog = None

    @property
    def is_available(self) -> bool:
        """
        Check if the Qt dialog signal manager is available.

        Returns:
            True if the signal manager is properly initialized
        """
        return self._dialog is not None

    @override
    def __repr__(self) -> str:
        """Return string representation of the manager."""
        return f"<QtDialogSignalManager(available={self.is_available})>"
