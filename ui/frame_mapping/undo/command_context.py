"""Command context for undo/redo operations.

Provides services and signal emitter access to commands without creating
circular dependencies with the controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject
    from ui.frame_mapping.services.ai_frame_service import AIFrameService
    from ui.frame_mapping.services.alignment_service import AlignmentService
    from ui.frame_mapping.services.mapping_service import MappingService
    from ui.frame_mapping.services.organization_service import OrganizationService


class CommandSignalEmitter(Protocol):
    """Protocol for signal emission from commands.

    Commands need to emit signals during undo operations to notify the UI
    of state changes. This protocol defines the minimal interface needed.
    """

    def emit_mapping_created(self, ai_frame_id: str, game_frame_id: str) -> None:
        """Emit mapping_created signal."""
        ...

    def emit_mapping_removed(self, ai_frame_id: str) -> None:
        """Emit mapping_removed signal."""
        ...

    def emit_alignment_updated(self, ai_frame_id: str) -> None:
        """Emit alignment_updated signal."""
        ...

    def emit_frame_renamed(self, frame_id: str) -> None:
        """Emit frame_renamed signal."""
        ...

    def emit_frame_tags_changed(self, frame_id: str) -> None:
        """Emit frame_tags_changed signal."""
        ...

    def emit_capture_renamed(self, game_frame_id: str) -> None:
        """Emit capture_renamed signal."""
        ...

    def emit_ai_frame_moved(self, ai_frame_id: str, from_index: int, to_index: int) -> None:
        """Emit ai_frame_moved signal."""
        ...


@dataclass
class CommandContext:
    """Context providing services and project to commands.

    This allows commands to call service methods directly for mutations
    while using the signal emitter for undo notifications.
    """

    project: FrameMappingProject
    mapping_service: MappingService
    alignment_service: AlignmentService
    organization_service: OrganizationService
    ai_frame_service: AIFrameService
    signal_emitter: CommandSignalEmitter

    def reorder_ai_frame_no_history(self, ai_frame_id: str, new_index: int) -> tuple[bool, int, int]:
        """Reorder AI frame without undo history.

        This method lives on CommandContext because it requires both project mutation
        and ai_frame_service for index lookup.

        Args:
            ai_frame_id: ID of the AI frame to move
            new_index: Target index

        Returns:
            Tuple of (success, old_index, actual_new_index)
        """
        old_index = self.ai_frame_service.find_frame_index(self.project, ai_frame_id)
        if old_index == -1:
            return False, -1, -1

        if self.project.reorder_ai_frame(ai_frame_id, new_index):
            actual_new_index = self.ai_frame_service.find_frame_index(self.project, ai_frame_id)
            return True, old_index, actual_new_index
        return False, old_index, old_index
