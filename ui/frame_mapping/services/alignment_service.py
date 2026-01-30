"""Service for managing alignment in frame mapping projects.

Provides alignment update and batch transform operations. This is a stateless
service - all methods take a project parameter rather than storing project state.

Signal emission and undo command orchestration remain in the controller. This
service provides the core business logic and state extraction for undo support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject

from ui.frame_mapping.views.workbench_types import AlignmentState
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

logger = get_logger(__name__)


class AlignmentService(QObject):
    """Service for alignment operations in frame mapping projects.

    This is a stateless service - all methods take a project parameter
    rather than storing project state internally.

    Undo support:
        Methods that capture state for undo return dataclass tuples that
        the controller can use to build undo commands.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the alignment service.

        Args:
            parent: Optional Qt parent object
        """
        super().__init__(parent)

    def capture_alignment_undo_state(
        self,
        project: FrameMappingProject,
        ai_frame_id: str,
        drag_start_alignment: AlignmentState | None = None,
    ) -> tuple[AlignmentState, str] | None:
        """Capture state needed for undo when updating alignment.

        Args:
            project: The frame mapping project
            ai_frame_id: ID of the AI frame
            drag_start_alignment: If provided, use this as old state for undo command.
                                 This creates a single undo for an entire drag operation.

        Returns:
            Tuple of (old_alignment, old_status) or None if no mapping exists
        """
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is None:
            return None

        # Use drag start alignment for undo if provided (creates single undo for entire drag)
        # Otherwise use current mapping state (for keyboard nudge, etc.)
        if drag_start_alignment is not None:
            old_alignment = drag_start_alignment
        else:
            old_alignment = AlignmentState(
                offset_x=mapping.offset_x,
                offset_y=mapping.offset_y,
                flip_h=mapping.flip_h,
                flip_v=mapping.flip_v,
                scale=mapping.scale,
                sharpen=mapping.sharpen,
                resampling=mapping.resampling,
            )

        return old_alignment, mapping.status

    def apply_alignment_to_project(
        self,
        project: FrameMappingProject,
        ai_frame_id: str,
        alignment: AlignmentState,
        set_edited: bool = True,
    ) -> bool:
        """Apply alignment to a mapping without undo (for command execution).

        Args:
            project: The frame mapping project
            ai_frame_id: ID of the AI frame
            alignment: The alignment to apply
            set_edited: If True and status is not 'injected', set status to 'edited'

        Returns:
            True if alignment was updated
        """
        return project.update_mapping_alignment(
            ai_frame_id,
            alignment.offset_x,
            alignment.offset_y,
            alignment.flip_h,
            alignment.flip_v,
            alignment.scale,
            alignment.sharpen,
            alignment.resampling,
            set_edited=set_edited,
        )

    def apply_transforms_to_all(
        self,
        project: FrameMappingProject,
        offset_x: int,
        offset_y: int,
        scale: float,
        exclude_ai_frame_id: str | None = None,
    ) -> int:
        """Apply position and scale to all mapped frames.

        This is a batch operation without undo support - typically used
        for "apply current alignment to all" operations.

        Args:
            project: The frame mapping project
            offset_x: X offset to apply
            offset_y: Y offset to apply
            scale: Scale factor to apply (0.01 - 1.0)
            exclude_ai_frame_id: AI frame ID to exclude (typically the current frame)

        Returns:
            Number of mappings updated
        """
        updated_count = 0
        clamped_scale = max(0.01, min(1.0, scale))

        for mapping in project.mappings:
            # Skip excluded frame
            if mapping.ai_frame_id == exclude_ai_frame_id:
                continue

            # Update position and scale, preserve flip values
            mapping.offset_x = offset_x
            mapping.offset_y = offset_y
            mapping.scale = clamped_scale
            mapping.status = "edited"
            updated_count += 1

        if updated_count > 0:
            logger.info(
                "Applied transforms to %d mappings: offset=(%d, %d), scale=%.2f",
                updated_count,
                offset_x,
                offset_y,
                clamped_scale,
            )

        return updated_count
