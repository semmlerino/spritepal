"""
Workflow State Manager for extraction operations.

Manages the state machine for ROM extraction workflow with defined transitions
and blocking states. This is a focused manager with single responsibility.
"""

from __future__ import annotations

import logging
import threading
from typing import ClassVar

from PySide6.QtCore import QObject, Signal

from .workflow_manager import ExtractionState

__all__ = ["ExtractionState", "WorkflowStateManager"]


class WorkflowStateManager(QObject):
    """
    Manages workflow state machine for extraction operations.

    This manager handles:
    - State transitions with validation
    - Blocking state detection
    - Capability queries (can_extract, can_preview, etc.)
    - Error state tracking

    Thread-safe: All state access is protected by a lock.
    """

    # Valid state transitions for the workflow state machine
    VALID_TRANSITIONS: ClassVar[dict[ExtractionState, set[ExtractionState]]] = {
        ExtractionState.IDLE: {
            ExtractionState.LOADING_ROM,
            ExtractionState.SCANNING_SPRITES,
            ExtractionState.PREVIEWING_SPRITE,
            ExtractionState.SEARCHING_SPRITE,
            ExtractionState.EXTRACTING,
        },
        ExtractionState.LOADING_ROM: {
            ExtractionState.IDLE,
            ExtractionState.ERROR,
        },
        ExtractionState.SCANNING_SPRITES: {
            ExtractionState.IDLE,
            ExtractionState.ERROR,
        },
        ExtractionState.PREVIEWING_SPRITE: {
            ExtractionState.IDLE,
            ExtractionState.ERROR,
            ExtractionState.SEARCHING_SPRITE,  # Can search while preview loads
        },
        ExtractionState.SEARCHING_SPRITE: {
            ExtractionState.IDLE,
            ExtractionState.ERROR,
            ExtractionState.PREVIEWING_SPRITE,  # Preview after finding
        },
        ExtractionState.EXTRACTING: {
            ExtractionState.IDLE,
            ExtractionState.ERROR,
        },
        ExtractionState.ERROR: {
            ExtractionState.IDLE,  # Reset to idle from error
        },
    }

    # States that block new operations
    BLOCKING_STATES: ClassVar[set[ExtractionState]] = {
        ExtractionState.LOADING_ROM,
        ExtractionState.SCANNING_SPRITES,
        ExtractionState.EXTRACTING,
    }

    # Signals
    workflow_state_changed = Signal(object, object)  # old_state, new_state

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize workflow state manager."""
        super().__init__(parent)
        self._logger = logging.getLogger(__name__)
        self._workflow_state = ExtractionState.IDLE
        self._workflow_error: str | None = None
        self._lock = threading.RLock()

    # ========== State Properties ==========

    @property
    def workflow_state(self) -> ExtractionState:
        """Get current workflow state."""
        return self._workflow_state

    @property
    def is_busy(self) -> bool:
        """Check if a blocking operation is in progress."""
        return self._workflow_state in self.BLOCKING_STATES

    @property
    def can_extract(self) -> bool:
        """Check if extraction can be started."""
        return self._workflow_state == ExtractionState.IDLE

    @property
    def can_preview(self) -> bool:
        """Check if preview can be started."""
        return self._workflow_state in {ExtractionState.IDLE, ExtractionState.SEARCHING_SPRITE}

    @property
    def can_search(self) -> bool:
        """Check if search can be started."""
        return self._workflow_state in {ExtractionState.IDLE, ExtractionState.PREVIEWING_SPRITE}

    @property
    def can_scan(self) -> bool:
        """Check if sprite scanning can be started."""
        return self._workflow_state == ExtractionState.IDLE

    @property
    def error_message(self) -> str | None:
        """Get error message if in error state."""
        return self._workflow_error if self._workflow_state == ExtractionState.ERROR else None

    # ========== State Transitions ==========

    def transition(
        self, new_state: ExtractionState, error_message: str | None = None
    ) -> bool:
        """
        Attempt to transition to a new workflow state.

        Args:
            new_state: Target state
            error_message: Error message if transitioning to ERROR state

        Returns:
            True if transition was successful, False otherwise
        """
        with self._lock:
            # Check if transition is valid
            valid_targets = self.VALID_TRANSITIONS.get(self._workflow_state, set())
            if new_state not in valid_targets:
                self._logger.warning(
                    f"Invalid workflow transition: {self._workflow_state.name} -> {new_state.name}"
                )
                return False

            old_state = self._workflow_state
            self._workflow_state = new_state

            # Handle error state
            if new_state == ExtractionState.ERROR:
                self._workflow_error = error_message
            else:
                self._workflow_error = None

            self._logger.debug(f"Workflow transition: {old_state.name} -> {new_state.name}")

        # Emit signal outside lock to prevent deadlock
        self.workflow_state_changed.emit(old_state, new_state)
        return True

    def reset_state(self) -> None:
        """Reset internal state for test isolation."""
        with self._lock:
            self._workflow_state = ExtractionState.IDLE
            self._workflow_error = None

    # ========== Convenience Methods ==========

    def start_scanning(self) -> bool:
        """Start sprite scanning operation."""
        return self.transition(ExtractionState.SCANNING_SPRITES)

    def finish_scanning(self, success: bool = True, error: str | None = None) -> bool:
        """Finish sprite scanning operation."""
        if success:
            return self.transition(ExtractionState.IDLE)
        return self.transition(ExtractionState.ERROR, error)
