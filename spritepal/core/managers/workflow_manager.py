"""
Workflow Manager for extraction workflow state machine.

This manager handles the extraction workflow state machine including state
transitions, busy states, and capability queries. It's extracted from
ApplicationStateManager to follow the Single Responsibility Principle.
"""

from __future__ import annotations

import threading
from enum import Enum, auto
from typing import ClassVar, override

from PySide6.QtCore import QObject, Signal

from .base_manager import BaseManager


class ExtractionState(Enum):
    """States for the extraction workflow.

    This enum is the canonical source for workflow states.
    """

    IDLE = auto()  # No operation in progress
    LOADING_ROM = auto()  # Loading ROM file
    SCANNING_SPRITES = auto()  # Scanning for sprite locations
    PREVIEWING_SPRITE = auto()  # Loading sprite preview
    SEARCHING_SPRITE = auto()  # Searching for next/prev sprite
    EXTRACTING = auto()  # Performing extraction
    ERROR = auto()  # Error state


class WorkflowManager(BaseManager):
    """
    Manager for extraction workflow state machine.

    Provides:
    - Workflow state tracking (FSM)
    - State transition validation
    - Capability queries (can_extract, can_preview, etc.)
    - Convenience transition methods
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
    workflow_error = Signal(str)  # error message

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the workflow manager."""
        self._workflow_state = ExtractionState.IDLE
        self._workflow_error: str | None = None
        self._workflow_lock = threading.RLock()

        super().__init__("WorkflowManager", parent)

    @override
    def _initialize(self) -> None:
        """Initialize the workflow manager."""
        self._is_initialized = True
        self._logger.info("WorkflowManager initialized")

    @override
    def cleanup(self) -> None:
        """Clean up resources."""
        with self._workflow_lock:
            self._workflow_state = ExtractionState.IDLE
            self._workflow_error = None
        super().cleanup()

    # ========== Properties ==========

    @property
    def workflow_state(self) -> ExtractionState:
        """Get current workflow state."""
        return self._workflow_state

    @property
    def is_workflow_busy(self) -> bool:
        """Check if a blocking operation is in progress."""
        return self._workflow_state in self.BLOCKING_STATES

    @property
    def can_extract(self) -> bool:
        """Check if extraction can be started."""
        return self._workflow_state == ExtractionState.IDLE

    @property
    def can_preview(self) -> bool:
        """Check if preview can be started."""
        return self._workflow_state in {
            ExtractionState.IDLE,
            ExtractionState.SEARCHING_SPRITE,
        }

    @property
    def can_search(self) -> bool:
        """Check if search can be started."""
        return self._workflow_state in {
            ExtractionState.IDLE,
            ExtractionState.PREVIEWING_SPRITE,
        }

    @property
    def can_scan(self) -> bool:
        """Check if sprite scanning can be started."""
        return self._workflow_state == ExtractionState.IDLE

    @property
    def workflow_error_message(self) -> str | None:
        """Get error message if in error state."""
        if self._workflow_state == ExtractionState.ERROR:
            return self._workflow_error
        return None

    # ========== Transition Methods ==========

    def transition_workflow(
        self,
        new_state: ExtractionState,
        error_message: str | None = None,
    ) -> bool:
        """
        Attempt to transition to a new workflow state.

        Args:
            new_state: Target state
            error_message: Error message if transitioning to ERROR state

        Returns:
            True if transition was successful, False otherwise
        """
        with self._workflow_lock:
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
                if error_message:
                    self.workflow_error.emit(error_message)
            else:
                self._workflow_error = None

            # Emit state change signal
            self.workflow_state_changed.emit(old_state, new_state)

            self._logger.debug(
                f"Workflow transition: {old_state.name} -> {new_state.name}"
            )
            return True

    def reset_workflow(self) -> None:
        """Reset workflow to idle state."""
        # Force reset to IDLE regardless of current state
        with self._workflow_lock:
            old_state = self._workflow_state
            self._workflow_state = ExtractionState.IDLE
            self._workflow_error = None
            if old_state != ExtractionState.IDLE:
                self.workflow_state_changed.emit(old_state, ExtractionState.IDLE)

    # ========== Convenience Transition Methods ==========

    def start_loading_rom(self) -> bool:
        """Start loading ROM operation."""
        return self.transition_workflow(ExtractionState.LOADING_ROM)

    def finish_loading_rom(
        self, success: bool = True, error: str | None = None
    ) -> bool:
        """Finish loading ROM operation."""
        if success:
            return self.transition_workflow(ExtractionState.IDLE)
        return self.transition_workflow(ExtractionState.ERROR, error)

    def start_scanning(self) -> bool:
        """Start sprite scanning operation."""
        return self.transition_workflow(ExtractionState.SCANNING_SPRITES)

    def finish_scanning(self, success: bool = True, error: str | None = None) -> bool:
        """Finish sprite scanning operation."""
        if success:
            return self.transition_workflow(ExtractionState.IDLE)
        return self.transition_workflow(ExtractionState.ERROR, error)

    def start_preview(self) -> bool:
        """Start sprite preview operation."""
        return self.transition_workflow(ExtractionState.PREVIEWING_SPRITE)

    def finish_preview(self, success: bool = True, error: str | None = None) -> bool:
        """Finish sprite preview operation."""
        if success:
            return self.transition_workflow(ExtractionState.IDLE)
        return self.transition_workflow(ExtractionState.ERROR, error)

    def start_search(self) -> bool:
        """Start sprite search operation."""
        return self.transition_workflow(ExtractionState.SEARCHING_SPRITE)

    def finish_search(self, success: bool = True, error: str | None = None) -> bool:
        """Finish sprite search operation."""
        if success:
            return self.transition_workflow(ExtractionState.IDLE)
        return self.transition_workflow(ExtractionState.ERROR, error)

    def start_extraction(self) -> bool:
        """Start extraction operation."""
        return self.transition_workflow(ExtractionState.EXTRACTING)

    def finish_extraction(
        self, success: bool = True, error: str | None = None
    ) -> bool:
        """Finish extraction operation."""
        if success:
            return self.transition_workflow(ExtractionState.IDLE)
        return self.transition_workflow(ExtractionState.ERROR, error)
