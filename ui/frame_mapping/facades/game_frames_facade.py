"""Facade for game frame operations.

Groups game frame-related controller methods: remove, update compression,
and organization (renaming) operations.

Note: The capture import workflow (import_mesen_capture, complete_capture_import,
import_capture_directory) remains in the controller due to its complexity with
multiple service callbacks and UI coordination.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from core.types import CompressionType
from ui.frame_mapping.services.organization_service import OrganizationService
from ui.frame_mapping.services.preview_service import PreviewService
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.frame_mapping_project import GameFrame
    from ui.frame_mapping.facades.controller_context import ControllerContext
    from ui.frame_mapping.undo.command_context import CommandContext
    from ui.frame_mapping.undo.undo_stack import UndoRedoStack

logger = get_logger(__name__)


class GameFramesSignals(Protocol):
    """Protocol for game frame-related signal emissions."""

    def emit_game_frame_removed(self, frame_id: str) -> None: ...
    def emit_mapping_removed(self, ai_frame_id: str) -> None: ...
    def emit_error(self, message: str) -> None: ...
    def emit_project_changed(self) -> None: ...
    def emit_save_requested(self) -> None: ...


class GameFramesFacade:
    """Facade for game frame operations.

    Handles removing, updating compression, and organizing game frames.
    """

    def __init__(
        self,
        context: ControllerContext,
        signals: GameFramesSignals,
        preview_service: PreviewService,
        organization_service: OrganizationService,
        undo_stack: UndoRedoStack,
        get_command_context: Callable[[], CommandContext],
    ) -> None:
        """Initialize the game frames facade.

        Args:
            context: Shared controller context for project access.
            signals: Signal emitter for UI updates.
            preview_service: Service for preview cache management.
            organization_service: Service for renaming operations.
            undo_stack: Undo/redo stack for commands.
            get_command_context: Callable to get CommandContext for undo commands.
        """
        self._context = context
        self._signals = signals
        self._preview_service = preview_service
        self._organization_service = organization_service
        self._undo_stack = undo_stack
        self._get_command_context = get_command_context

    # ─── Frame Management ─────────────────────────────────────────────────────

    def remove(self, frame_id: str) -> bool:
        """Remove a game frame from the project.

        Also removes any associated mapping and clears the preview cache.

        Args:
            frame_id: ID of the game frame to remove.

        Returns:
            True if the frame was found and removed.
        """
        project = self._context.project
        if project is None:
            return False

        # Capture affected AI frame IDs BEFORE removal (mappings will be deleted)
        affected_ai_ids = [m.ai_frame_id for m in project.mappings if m.game_frame_id == frame_id]

        # Clear preview cache for this frame
        self._preview_service.invalidate(frame_id)

        if project.remove_game_frame(frame_id):
            # Emit mapping_removed for each orphaned mapping
            for ai_id in affected_ai_ids:
                self._signals.emit_mapping_removed(ai_id)

            self._signals.emit_game_frame_removed(frame_id)
            logger.info("Removed game frame %s", frame_id)
            return True
        return False

    def get_frames(self) -> list[GameFrame]:
        """Get all game frames from the current project."""
        project = self._context.project
        if project is None:
            return []
        return project.game_frames

    def update_compression(self, frame_id: str, compression_type: CompressionType) -> bool:
        """Update compression type for a game frame.

        Updates the compression type for all ROM offsets in the game frame.
        By design, compression is a single setting per game frame, not per offset.

        Args:
            frame_id: ID of the game frame.
            compression_type: New compression type (CompressionType enum).

        Returns:
            True if the update was successful.
        """
        project = self._context.project
        if project is None:
            self._signals.emit_error("No project loaded")
            return False

        game_frame = project.get_game_frame_by_id(frame_id)
        if game_frame is None:
            self._signals.emit_error(f"Game frame {frame_id} not found")
            return False

        # Update compression type for all ROM offsets
        for rom_offset in game_frame.rom_offsets:
            game_frame.compression_types[rom_offset] = compression_type

        self._signals.emit_project_changed()
        self._signals.emit_save_requested()
        logger.info(
            "Updated compression type for game frame %s to %s (%d offsets)",
            frame_id,
            compression_type,
            len(game_frame.rom_offsets),
        )
        return True

    # ─── Frame Renaming ───────────────────────────────────────────────────────

    def rename_capture(self, game_frame_id: str, new_name: str | None) -> bool:
        """Set display name for a game frame (capture).

        Args:
            game_frame_id: ID of the game frame to rename.
            new_name: New display name (empty or None to clear).

        Returns:
            True if renamed successfully.
        """
        if self._context.project is None:
            return False

        result = self._organization_service.rename_capture(
            ctx=self._get_command_context(),
            undo_stack=self._undo_stack,
            game_frame_id=game_frame_id,
            new_name=new_name,
        )
        if result:
            self._signals.emit_save_requested()
        return result

    def get_display_name(self, game_frame_id: str) -> str | None:
        """Get display name for a game frame (capture).

        Args:
            game_frame_id: ID of the game frame.

        Returns:
            Display name if set, None otherwise.
        """
        project = self._context.project
        if project is None:
            return None
        return self._organization_service.get_capture_display_name(project=project, game_frame_id=game_frame_id)
