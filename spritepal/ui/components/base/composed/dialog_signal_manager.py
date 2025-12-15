"""
Dialog signal manager component for handling custom dialog signals.

This component manages custom signals (offset_changed, sprite_found, etc.) for composed dialogs.
It's designed to avoid Qt metaclass system issues with signals in complex inheritance hierarchies.
"""
from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import QObject, Signal


class DialogSignalManager(QObject):
    """
    Manages custom signals for composed dialogs.

    This manager provides a centralized way to handle dialog-specific signals,
    avoiding Qt metaclass issues that occur when signals are defined in
    complex composed inheritance hierarchies.

    Signals:
        offset_changed: Emitted when the dialog's offset changes
        sprite_found: Emitted when a sprite is found during search
        validation_failed: Emitted when validation fails
    """

    # Custom dialog signals
    offset_changed = Signal(int)  # offset value
    sprite_found = Signal(int, str)  # offset, name
    validation_failed = Signal(str)  # error message

    def __init__(self, parent: QObject | None = None) -> None:
        """
        Initialize the dialog signal manager.

        Args:
            parent: Optional parent QObject for proper cleanup
        """
        super().__init__(parent)

    def initialize(self, context: Any) -> None:
        """
        Initialize the manager with a dialog context.

        This method sets up the signal manager as part of the composed dialog system.

        Args:
            context: The dialog context containing config and dialog references

        Raises:
            AttributeError: If context doesn't have required attributes
        """
        # Check if context has required attributes
        if not hasattr(context, 'config'):
            raise AttributeError("Context must have a 'config' attribute")

        # Add to context for external access
        context.dialog_signals = self

        # Log successful initialization
        from utils.logging_config import get_logger
        logger = get_logger(__name__)
        logger.debug("DialogSignalManager initialized successfully")

    def emit_offset_changed(self, offset: int) -> None:
        """
        Emit the offset_changed signal safely.

        Args:
            offset: The new offset value
        """
        try:
            self.offset_changed.emit(offset)
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.debug(f"[SIGNAL] Emitted offset_changed: 0x{offset:06X}")
        except Exception as e:
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(f"[SIGNAL] Failed to emit offset_changed: {e}")

    def emit_sprite_found(self, offset: int, name: str) -> None:
        """
        Emit the sprite_found signal safely.

        Args:
            offset: The offset where the sprite was found
            name: The name/description of the sprite
        """
        try:
            self.sprite_found.emit(offset, name)
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.debug(f"[SIGNAL] Emitted sprite_found: 0x{offset:06X}, {name}")
        except Exception as e:
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(f"[SIGNAL] Failed to emit sprite_found: {e}")

    def emit_validation_failed(self, message: str) -> None:
        """
        Emit the validation_failed signal safely.

        Args:
            message: The validation error message
        """
        try:
            self.validation_failed.emit(message)
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.debug(f"[SIGNAL] Emitted validation_failed: {message}")
        except Exception as e:
            from utils.logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(f"[SIGNAL] Failed to emit validation_failed: {e}")

    def cleanup(self) -> None:
        """
        Clean up references and resources.

        This should be called when the manager is no longer needed
        to prevent reference cycles.
        """
        # Clear any internal state if needed
        pass

    @property
    def is_available(self) -> bool:
        """
        Check if the signal manager is available.

        Returns:
            True if the signal manager is properly initialized
        """
        return True

    @override
    def __repr__(self) -> str:
        """Return string representation of the manager."""
        return "<DialogSignalManager(available)>"
