"""Shared context for all domain facades.

The ControllerContext provides access to shared state (project, undo stack,
repositories) that facades need to operate. This avoids passing the full
controller reference to facades, enabling cleaner separation of concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject
    from core.repositories.capture_result_repository import CaptureResultRepository
    from ui.frame_mapping.undo.undo_stack import UndoRedoStack


@dataclass
class ControllerContext:
    """Shared state for domain facades.

    This context object provides access to:
    - The current project (mutable reference, may be None)
    - The undo/redo stack
    - The capture result repository

    Facades receive this context rather than the full controller,
    enabling them to operate on shared state without circular dependencies.
    """

    _project_holder: list[FrameMappingProject | None] = field(default_factory=lambda: [None])
    undo_stack: UndoRedoStack | None = None
    capture_repository: CaptureResultRepository | None = None

    @property
    def project(self) -> FrameMappingProject | None:
        """Get the current project, may be None."""
        return self._project_holder[0]

    @project.setter
    def project(self, value: FrameMappingProject | None) -> None:
        """Set the current project."""
        self._project_holder[0] = value

    def require_project(self) -> FrameMappingProject:
        """Get the current project, raising if None.

        Raises:
            ValueError: If no project is loaded.
        """
        if self._project_holder[0] is None:
            raise ValueError("No project loaded")
        return self._project_holder[0]

    def require_undo_stack(self) -> UndoRedoStack:
        """Get the undo stack, raising if None.

        Raises:
            ValueError: If undo stack is not initialized.
        """
        if self.undo_stack is None:
            raise ValueError("Undo stack not initialized")
        return self.undo_stack

    def require_capture_repository(self) -> CaptureResultRepository:
        """Get the capture repository, raising if None.

        Raises:
            ValueError: If capture repository is not initialized.
        """
        if self.capture_repository is None:
            raise ValueError("Capture repository not initialized")
        return self.capture_repository
