"""Facade for mapping operations between AI frames and game frames.

Groups mapping-related controller methods: create, remove, update_alignment,
apply_transforms, and query methods.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ui.frame_mapping.services.alignment_service import AlignmentService
from ui.frame_mapping.services.mapping_service import MappingService
from ui.frame_mapping.undo import (
    CreateMappingCommand,
    RemoveMappingCommand,
    UpdateAlignmentCommand,
)
from ui.frame_mapping.views.workbench_types import AlignmentState
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from ui.frame_mapping.facades.controller_context import ControllerContext
    from ui.frame_mapping.undo.command_context import CommandContext

logger = get_logger(__name__)


class MappingsSignals(Protocol):
    """Protocol for mapping-related signal emissions."""

    def emit_mapping_created(self, ai_frame_id: str, game_frame_id: str) -> None: ...
    def emit_mapping_removed(self, ai_frame_id: str) -> None: ...
    def emit_alignment_updated(self, ai_frame_id: str) -> None: ...
    def emit_error(self, message: str) -> None: ...
    def emit_save_requested(self) -> None: ...
    def emit_project_changed(self) -> None: ...


class MappingsFacade:
    """Facade for mapping operations.

    Handles creating, removing, and updating mappings between AI frames
    and game frames, including alignment adjustments and bulk transforms.
    """

    def __init__(
        self,
        context: ControllerContext,
        signals: MappingsSignals,
        mapping_service: MappingService,
        alignment_service: AlignmentService,
        get_command_context: Callable[[], CommandContext],
    ) -> None:
        """Initialize the mappings facade.

        Args:
            context: Shared controller context for project/undo access.
            signals: Signal emitter for UI updates.
            mapping_service: Service for mapping operations.
            alignment_service: Service for alignment operations.
            get_command_context: Callable to get CommandContext for undo commands.
        """
        self._context = context
        self._signals = signals
        self._mapping_service = mapping_service
        self._alignment_service = alignment_service
        self._get_command_context = get_command_context

    def create_mapping(self, ai_frame_id: str, game_frame_id: str) -> bool:
        """Create a mapping between an AI frame and a game frame.

        Args:
            ai_frame_id: ID of the AI frame (filename).
            game_frame_id: ID of the game frame.

        Returns:
            True if mapping was created.
        """
        project = self._context.project
        if project is None:
            self._signals.emit_error("No project loaded")
            return False

        # Validate both frames exist
        is_valid, error_msg = self._mapping_service.validate_mapping_frames(project, ai_frame_id, game_frame_id)
        if not is_valid:
            self._signals.emit_error(error_msg)
            return False

        # Capture previous state for undo
        (
            prev_ai_game_id,
            prev_game_ai_id,
            prev_ai_alignment,
            prev_game_alignment,
        ) = self._mapping_service.capture_create_mapping_undo_state(project, ai_frame_id, game_frame_id)

        # Create and execute command via undo stack
        command = CreateMappingCommand(
            ctx=self._get_command_context(),
            ai_frame_id=ai_frame_id,
            game_frame_id=game_frame_id,
            prev_ai_mapping_game_id=prev_ai_game_id,
            prev_game_mapping_ai_id=prev_game_ai_id,
            prev_ai_mapping_alignment=prev_ai_alignment,
            prev_game_mapping_alignment=prev_game_alignment,
        )
        self._context.require_undo_stack().push(command)

        self._signals.emit_mapping_created(ai_frame_id, game_frame_id)
        self._signals.emit_save_requested()
        logger.info("Created mapping: AI frame %s -> Game frame %s", ai_frame_id, game_frame_id)
        return True

    def remove_mapping(self, ai_frame_id: str) -> bool:
        """Remove a mapping for an AI frame.

        Args:
            ai_frame_id: ID of the AI frame (filename).

        Returns:
            True if a mapping was removed.
        """
        project = self._context.project
        if project is None:
            return False

        # Capture state for undo
        undo_state = self._mapping_service.capture_remove_mapping_undo_state(project, ai_frame_id)
        if undo_state is None:
            return False

        removed_game_id, removed_alignment, removed_status = undo_state

        # Create and execute command via undo stack
        command = RemoveMappingCommand(
            ctx=self._get_command_context(),
            ai_frame_id=ai_frame_id,
            removed_game_frame_id=removed_game_id,
            removed_alignment=removed_alignment,
            removed_status=removed_status,
        )
        self._context.require_undo_stack().push(command)

        self._signals.emit_mapping_removed(ai_frame_id)
        self._signals.emit_save_requested()
        logger.info("Removed mapping for AI frame %s", ai_frame_id)
        return True

    def update_alignment(
        self,
        ai_frame_id: str,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float = 1.0,
        sharpen: float = 0.0,
        resampling: str = "lanczos",
        set_edited: bool = True,
        drag_start_alignment: AlignmentState | None = None,
    ) -> bool:
        """Update alignment for a mapping.

        Args:
            ai_frame_id: ID of the AI frame (filename).
            offset_x: X offset for alignment.
            offset_y: Y offset for alignment.
            flip_h: Horizontal flip state.
            flip_v: Vertical flip state.
            scale: Scale factor (0.1 - 1.0).
            sharpen: Pre-sharpening amount (0.0 - 4.0).
            resampling: Resampling method ("lanczos" or "nearest").
            set_edited: If True and status is not 'injected', set status to 'edited'.
            drag_start_alignment: If provided, use this as old state for undo command.

        Returns:
            True if alignment was updated.
        """
        project = self._context.project
        if project is None:
            return False

        new_alignment = AlignmentState(
            offset_x=offset_x,
            offset_y=offset_y,
            flip_h=flip_h,
            flip_v=flip_v,
            scale=scale,
            sharpen=sharpen,
            resampling=resampling,
        )

        # Only record undo for explicit user edits, not auto-centering
        if set_edited:
            # Capture state for undo
            undo_state = self._alignment_service.capture_alignment_undo_state(
                project, ai_frame_id, drag_start_alignment
            )
            if undo_state is None:
                return False

            old_alignment, old_status = undo_state

            # Create and execute command via undo stack
            command = UpdateAlignmentCommand(
                ctx=self._get_command_context(),
                ai_frame_id=ai_frame_id,
                new_alignment=new_alignment,
                old_alignment=old_alignment,
                old_status=old_status,
            )
            self._context.require_undo_stack().push(command)
        else:
            # Auto-centering - update directly without history
            self._alignment_service.apply_alignment_to_project(project, ai_frame_id, new_alignment, set_edited=False)

        # Use targeted signal to avoid full UI refresh (which blanks canvas)
        self._signals.emit_alignment_updated(ai_frame_id)
        self._signals.emit_save_requested()
        logger.info(
            "Updated alignment for AI frame %s: offset=(%d, %d), flip=(%s, %s), "
            "scale=%.2f, sharpen=%.1f, resampling=%s",
            ai_frame_id,
            offset_x,
            offset_y,
            flip_h,
            flip_v,
            scale,
            sharpen,
            resampling,
        )
        return True

    def apply_transforms_to_all(
        self,
        offset_x: int,
        offset_y: int,
        scale: float,
        exclude_ai_frame_id: str | None = None,
    ) -> int:
        """Apply position and scale to all mapped frames.

        Args:
            offset_x: X offset to apply.
            offset_y: Y offset to apply.
            scale: Scale factor to apply (0.01 - 1.0).
            exclude_ai_frame_id: AI frame ID to exclude (typically the current frame).

        Returns:
            Number of mappings updated.
        """
        project = self._context.project
        if project is None:
            return 0

        updated_count = self._alignment_service.apply_transforms_to_all(
            project, offset_x, offset_y, scale, exclude_ai_frame_id
        )

        if updated_count > 0:
            self._signals.emit_project_changed()
            self._signals.emit_save_requested()

        return updated_count

    def get_existing_link_for_game_frame(self, game_frame_id: str) -> str | None:
        """Get the AI frame ID currently linked to a game frame.

        Args:
            game_frame_id: ID of the game frame.

        Returns:
            AI frame ID if linked, None otherwise.
        """
        project = self._context.project
        if project is None:
            return None
        return self._mapping_service.get_link_for_game_frame(project, game_frame_id)

    def get_existing_link_for_ai_frame(self, ai_frame_id: str) -> str | None:
        """Get the game frame ID currently linked to an AI frame.

        Args:
            ai_frame_id: ID of the AI frame.

        Returns:
            Game frame ID if linked, None otherwise.
        """
        project = self._context.project
        if project is None:
            return None
        return self._mapping_service.get_link_for_ai_frame(project, ai_frame_id)
