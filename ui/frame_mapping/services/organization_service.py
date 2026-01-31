"""Frame and capture organization service.

Handles renaming, tagging, and display name management for AI frames and game frames.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject
    from ui.frame_mapping.undo import UndoRedoStack
    from ui.frame_mapping.undo.command_context import CommandContext

from core.frame_mapping_project import FRAME_TAGS, AIFrame
from ui.frame_mapping.undo import (
    RenameAIFrameCommand,
    RenameCaptureCommand,
    ToggleFrameTagCommand,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)


class OrganizationService(QObject):
    """Service for frame and capture organization (renaming, tagging)."""

    # Signals
    frame_renamed = Signal(str)  # ai_frame_id
    frame_tags_changed = Signal(str)  # ai_frame_id
    capture_renamed = Signal(str)  # game_frame_id

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize organization service.

        Args:
            parent: Optional parent QObject
        """
        super().__init__(parent)

    # ─── AI Frame Organization ─────────────────────────────────────────────────

    def rename_frame(
        self,
        ctx: CommandContext,
        undo_stack: UndoRedoStack,
        frame_id: str,
        display_name: str | None,
    ) -> bool:
        """Set display name for an AI frame.

        Args:
            ctx: Command context with project and services
            undo_stack: Undo stack for command
            frame_id: ID of the AI frame (filename)
            display_name: New display name, or None to clear

        Returns:
            True if frame was found and renamed
        """
        frame = ctx.project.get_ai_frame_by_id(frame_id)
        if frame is None:
            return False

        # Capture previous state for undo
        old_name = frame.display_name

        # Create and execute command via undo stack
        command = RenameAIFrameCommand(
            ctx=ctx,
            frame_id=frame_id,
            new_name=display_name,
            old_name=old_name,
        )
        undo_stack.push(command)

        logger.info("Renamed frame '%s' to '%s'", frame_id, display_name or "(cleared)")
        self.frame_renamed.emit(frame_id)
        return True

    def _rename_frame_no_history(self, project: FrameMappingProject, frame_id: str, display_name: str | None) -> bool:
        """Internal: Rename frame without undo history (for command execution).

        Args:
            project: Frame mapping project
            frame_id: ID of the AI frame (filename)
            display_name: New display name, or None to clear

        Returns:
            True if frame was found and renamed
        """
        return project.set_frame_display_name(frame_id, display_name)

    def add_frame_tag(self, project: FrameMappingProject, frame_id: str, tag: str) -> bool:
        """Add a tag to an AI frame.

        Args:
            project: Frame mapping project
            frame_id: ID of the AI frame (filename)
            tag: Tag to add (must be in FRAME_TAGS)

        Returns:
            True if frame was found and tag added
        """
        result = project.add_frame_tag(frame_id, tag)
        if result:
            self.frame_tags_changed.emit(frame_id)
        return result

    def remove_frame_tag(self, project: FrameMappingProject, frame_id: str, tag: str) -> bool:
        """Remove a tag from an AI frame.

        Args:
            project: Frame mapping project
            frame_id: ID of the AI frame (filename)
            tag: Tag to remove

        Returns:
            True if frame was found and tag removed
        """
        result = project.remove_frame_tag(frame_id, tag)
        if result:
            self.frame_tags_changed.emit(frame_id)
        return result

    def toggle_frame_tag(
        self,
        ctx: CommandContext,
        undo_stack: UndoRedoStack,
        frame_id: str,
        tag: str,
    ) -> bool:
        """Toggle a tag on an AI frame.

        Args:
            ctx: Command context with project and services
            undo_stack: Undo stack for command
            frame_id: ID of the AI frame (filename)
            tag: Tag to toggle (must be in FRAME_TAGS)

        Returns:
            True if frame was found and tag toggled
        """
        frame = ctx.project.get_ai_frame_by_id(frame_id)
        if frame is None:
            return False

        # Capture previous state for undo
        was_present = tag in frame.tags

        # Create and execute command via undo stack
        command = ToggleFrameTagCommand(
            ctx=ctx,
            frame_id=frame_id,
            tag=tag,
            was_present=was_present,
        )
        undo_stack.push(command)

        self.frame_tags_changed.emit(frame_id)
        return True

    def _toggle_frame_tag_no_history(self, project: FrameMappingProject, frame_id: str, tag: str) -> bool:
        """Internal: Toggle frame tag without undo history (for command execution).

        Args:
            project: Frame mapping project
            frame_id: ID of the AI frame (filename)
            tag: Tag to toggle

        Returns:
            True if frame was found and tag toggled
        """
        return project.toggle_frame_tag(frame_id, tag)

    def set_frame_tags(self, project: FrameMappingProject, frame_id: str, tags: frozenset[str]) -> bool:
        """Set all tags for an AI frame (replace existing).

        Args:
            project: Frame mapping project
            frame_id: ID of the AI frame (filename)
            tags: New set of tags

        Returns:
            True if frame was found and tags updated
        """
        result = project.set_frame_tags(frame_id, tags)
        if result:
            self.frame_tags_changed.emit(frame_id)
        return result

    def get_frame_tags(self, project: FrameMappingProject, frame_id: str) -> frozenset[str]:
        """Get tags for an AI frame.

        Args:
            project: Frame mapping project
            frame_id: ID of the AI frame (filename)

        Returns:
            Set of tags (empty if frame not found)
        """
        frame = project.get_ai_frame_by_id(frame_id)
        if frame is None:
            return frozenset()
        return frame.tags

    def get_frame_display_name(self, project: FrameMappingProject, frame_id: str) -> str | None:
        """Get display name for an AI frame.

        Args:
            project: Frame mapping project
            frame_id: ID of the AI frame (filename)

        Returns:
            Display name if set, None otherwise
        """
        frame = project.get_ai_frame_by_id(frame_id)
        if frame is None:
            return None
        return frame.display_name

    def get_frames_with_tag(self, project: FrameMappingProject, tag: str) -> list[AIFrame]:
        """Get all AI frames with a specific tag.

        Args:
            project: Frame mapping project
            tag: Tag to filter by

        Returns:
            List of AIFrame objects with the tag
        """
        return project.get_frames_with_tag(tag)

    @staticmethod
    def get_available_tags() -> frozenset[str]:
        """Get the set of valid frame tags.

        Returns:
            Set of valid tag names
        """
        return FRAME_TAGS

    # ─── Capture (GameFrame) Organization ──────────────────────────────────────

    def rename_capture(
        self,
        ctx: CommandContext,
        undo_stack: UndoRedoStack,
        game_frame_id: str,
        new_name: str | None,
    ) -> bool:
        """Set display name for a game frame (capture).

        Args:
            ctx: Command context with project and services
            undo_stack: Undo stack for command
            game_frame_id: ID of the game frame to rename
            new_name: New display name (empty or None to clear)

        Returns:
            True if renamed successfully, False otherwise
        """
        frame = ctx.project.get_game_frame_by_id(game_frame_id)
        if frame is None:
            return False

        # Normalize empty string to None
        display_name = new_name.strip() if new_name else None
        if display_name == "":
            display_name = None

        # Capture previous state for undo
        old_name = frame.display_name

        # Create and execute command via undo stack
        command = RenameCaptureCommand(
            ctx=ctx,
            game_frame_id=game_frame_id,
            new_name=display_name,
            old_name=old_name,
        )
        undo_stack.push(command)

        self.capture_renamed.emit(game_frame_id)
        return True

    def _rename_capture_no_history(
        self, project: FrameMappingProject, game_frame_id: str, display_name: str | None
    ) -> bool:
        """Internal: Rename capture without undo history (for command execution).

        Args:
            project: Frame mapping project
            game_frame_id: ID of the game frame
            display_name: New display name, or None to clear

        Returns:
            True if frame was found and renamed
        """
        return project.set_capture_display_name(game_frame_id, display_name)

    def get_capture_display_name(self, project: FrameMappingProject, game_frame_id: str) -> str | None:
        """Get display name for a game frame (capture).

        Args:
            project: Frame mapping project
            game_frame_id: ID of the game frame

        Returns:
            Display name if set, None otherwise
        """
        frame = project.get_game_frame_by_id(game_frame_id)
        if frame is None:
            return None
        return frame.display_name
