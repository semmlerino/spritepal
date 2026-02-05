"""Undo/Redo stack for frame mapping operations.

Provides a stack-based command history with configurable max depth.
Adapted from ui/row_arrangement/undo_redo.py for frame mapping.
"""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QObject, Signal

from utils.logging_config import get_logger

logger = get_logger(__name__)


class FrameMappingCommand(Protocol):
    """Protocol for undoable frame mapping commands.

    All command implementations must provide these methods.
    Concrete command classes are dataclasses that implement this interface
    via structural subtyping (duck typing) - they don't explicitly inherit.
    """

    @property
    def description(self) -> str:
        """Human-readable description of the command."""
        ...

    def execute(self) -> None:
        """Execute the command (for initial execution and redo)."""
        ...

    def undo(self) -> None:
        """Undo the command."""
        ...


class UndoRedoStack(QObject):
    """Manages undo/redo history for frame mapping operations.

    Provides a stack-based command history with configurable max depth.
    Emits signals when undo/redo availability changes for UI updates.
    """

    # Signals for UI state updates
    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)

    DEFAULT_MAX_HISTORY = 50

    def __init__(self, max_history: int = DEFAULT_MAX_HISTORY, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._undo_stack: list[FrameMappingCommand] = []
        self._redo_stack: list[FrameMappingCommand] = []
        self._max_history = max_history

    def push(self, command: FrameMappingCommand) -> None:
        """Execute a command and push it onto the undo stack.

        Args:
            command: The command to execute and track
        """
        # Execute the command first
        command.execute()

        # Clear redo stack when new command is added
        if self._redo_stack:
            self._redo_stack.clear()
            self.can_redo_changed.emit(False)

        # Add to undo stack
        self._undo_stack.append(command)

        # Enforce history limit
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)

        # Emit signals
        self.can_undo_changed.emit(True)

    def undo(self) -> str | None:
        """Undo the last command.

        Returns:
            Description of the undone command, or None if nothing to undo
        """
        if not self._undo_stack:
            return None

        command = self._undo_stack.pop()
        try:
            command.undo()
        except Exception:
            logger.warning("Undo failed for '%s', discarding command", command.description, exc_info=True)
            self.can_undo_changed.emit(len(self._undo_stack) > 0)
            return command.description
        self._redo_stack.append(command)

        # Emit signals
        self.can_undo_changed.emit(len(self._undo_stack) > 0)
        self.can_redo_changed.emit(True)

        return command.description

    def redo(self) -> str | None:
        """Redo the last undone command.

        Returns:
            Description of the redone command, or None if nothing to redo
        """
        if not self._redo_stack:
            return None

        command = self._redo_stack.pop()
        try:
            command.execute()
        except Exception:
            logger.warning("Redo failed for '%s', discarding command", command.description, exc_info=True)
            self.can_redo_changed.emit(len(self._redo_stack) > 0)
            return command.description
        self._undo_stack.append(command)

        # Emit signals
        self.can_undo_changed.emit(True)
        self.can_redo_changed.emit(len(self._redo_stack) > 0)

        return command.description

    def clear(self) -> None:
        """Clear all history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.can_undo_changed.emit(False)
        self.can_redo_changed.emit(False)

    def can_undo(self) -> bool:
        """Check if undo is available."""
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        """Check if redo is available."""
        return len(self._redo_stack) > 0

    def undo_description(self) -> str | None:
        """Get description of next undo command."""
        return self._undo_stack[-1].description if self._undo_stack else None

    def redo_description(self) -> str | None:
        """Get description of next redo command."""
        return self._redo_stack[-1].description if self._redo_stack else None
