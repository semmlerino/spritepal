"""Facade for AI frame operations.

Groups AI frame-related controller methods: load, add, remove, reorder,
rename, and tagging operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ui.frame_mapping.services.ai_frame_service import AIFrameService
from ui.frame_mapping.services.organization_service import OrganizationService
from ui.frame_mapping.undo import ReorderAIFrameCommand
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.frame_mapping_project import AIFrame
    from ui.frame_mapping.facades.controller_context import ControllerContext
    from ui.frame_mapping.undo.command_context import CommandContext
    from ui.frame_mapping.undo.undo_stack import UndoRedoStack

logger = get_logger(__name__)


class AIFramesSignals(Protocol):
    """Protocol for AI frame-related signal emissions."""

    def emit_ai_frames_loaded(self, count: int) -> None: ...
    def emit_ai_frame_added(self, frame_id: str) -> None: ...
    def emit_ai_frame_removed(self, frame_id: str) -> None: ...
    def emit_ai_frame_moved(self, ai_frame_id: str, from_index: int, to_index: int) -> None: ...
    def emit_mapping_removed(self, ai_frame_id: str) -> None: ...
    def emit_error(self, message: str) -> None: ...
    def emit_project_changed(self) -> None: ...
    def emit_save_requested(self) -> None: ...


class AIFramesFacade:
    """Facade for AI frame operations.

    Handles loading, adding, removing, reordering AI frames, and managing
    frame organization (renaming, tagging).
    """

    def __init__(
        self,
        context: ControllerContext,
        signals: AIFramesSignals,
        ai_frame_service: AIFrameService,
        organization_service: OrganizationService,
        undo_stack: UndoRedoStack,
        get_command_context: Callable[[], CommandContext],
    ) -> None:
        """Initialize the AI frames facade.

        Args:
            context: Shared controller context for project access.
            signals: Signal emitter for UI updates.
            ai_frame_service: Service for AI frame loading/management.
            organization_service: Service for renaming and tagging.
            undo_stack: Undo/redo stack for commands.
            get_command_context: Callable to get CommandContext for undo commands.
        """
        self._context = context
        self._signals = signals
        self._ai_frame_service = ai_frame_service
        self._organization_service = organization_service
        self._undo_stack = undo_stack
        self._get_command_context = get_command_context

    # ─── Frame Loading ────────────────────────────────────────────────────────

    def load_from_directory(self, directory: Path, *, clear_undo: Callable[[], None]) -> int:
        """Load AI frames from a directory of PNG files.

        Args:
            directory: Directory containing PNG files.
            clear_undo: Callback to clear undo history (needed after reload).

        Returns:
            Number of frames loaded.
        """
        project = self._context.project
        if project is None:
            # Caller should ensure project exists before calling
            self._signals.emit_error("No project loaded")
            return 0

        if not directory.is_dir():
            self._signals.emit_error(f"Not a directory: {directory}")
            return 0

        # Delegate to service for frame creation
        frames, _orphan_count = self._ai_frame_service.load_frames_from_directory(
            project,
            directory,
        )
        if not frames:
            self._signals.emit_error(f"No PNG files found in {directory}")
            return 0

        # Replace AI frames (handles index invalidation)
        project.replace_ai_frames(frames, directory)

        # Clear undo history: old commands reference deleted frame IDs
        clear_undo()

        # Prune orphaned mappings that reference non-existent AI frame IDs
        valid_ids = {f.id for f in frames}
        removed = project.filter_mappings_by_valid_ai_ids(valid_ids)
        if removed > 0:
            logger.info(
                "Pruning %d orphaned mappings after AI frames reload",
                removed,
            )

        self._signals.emit_ai_frames_loaded(len(frames))
        self._signals.emit_project_changed()
        logger.info("Loaded %d AI frames from %s", len(frames), directory)
        return len(frames)

    def add_from_file(self, file_path: Path) -> bool:
        """Add a single AI frame from a PNG file.

        Args:
            file_path: Path to the PNG file.

        Returns:
            True if frame was added successfully.
        """
        project = self._context.project
        if project is None:
            self._signals.emit_error("No project loaded")
            return False

        if not file_path.is_file() or file_path.suffix.lower() != ".png":
            self._signals.emit_error(f"Not a PNG file: {file_path}")
            return False

        # Delegate to service for frame creation
        frame = self._ai_frame_service.create_frame_from_file(
            project,
            file_path,
        )

        if frame is None:
            # Frame already exists - just refresh UI
            existing_count = len(project.ai_frames)
            self._signals.emit_ai_frames_loaded(existing_count)
            return True

        # Add to project (may raise ValueError for duplicate ID)
        try:
            project.add_ai_frame(frame)
        except ValueError as e:
            self._signals.emit_error(f"Cannot add frame: {e}")
            return False

        # Emit targeted signal - handlers will add to AI pane and mapping panel
        self._signals.emit_ai_frame_added(frame.id)
        logger.info("Added AI frame: %s", file_path)
        return True

    # ─── Frame Management ─────────────────────────────────────────────────────

    def remove(self, frame_id: str) -> bool:
        """Remove an AI frame from the project.

        Also removes any associated mapping.

        Args:
            frame_id: ID of the AI frame to remove.

        Returns:
            True if the frame was found and removed.
        """
        project = self._context.project
        if project is None:
            logger.warning("remove: project is None")
            return False

        # Check if frame has a mapping before removal (will be deleted along with frame)
        had_mapping = project.get_mapping_for_ai_frame(frame_id) is not None
        logger.info(
            "remove: frame_id=%s, had_mapping=%s, ai_frames_count=%d", frame_id, had_mapping, len(project.ai_frames)
        )

        result = project.remove_ai_frame(frame_id)
        logger.info("remove: project.remove_ai_frame returned %s, ai_frames_count=%d", result, len(project.ai_frames))
        if result:
            # Emit mapping_removed if the frame was mapped (mapping was deleted)
            if had_mapping:
                self._signals.emit_mapping_removed(frame_id)

            self._signals.emit_ai_frame_removed(frame_id)
            logger.info("Removed AI frame %s", frame_id)
            return True
        return False

    def reorder(self, ai_frame_id: str, new_index: int) -> bool:
        """Reorder an AI frame to a new position (undoable).

        Args:
            ai_frame_id: ID of the AI frame to move.
            new_index: Target position (0-based).

        Returns:
            True if the frame was moved.
        """
        project = self._context.project
        if project is None:
            return False

        # Delegate to service for validation
        result = self._ai_frame_service.validate_reorder(project, ai_frame_id, new_index)
        if result is None:
            return False  # Invalid or no-op

        current_index, clamped_index = result

        # Create and execute command
        command = ReorderAIFrameCommand(
            ctx=self._get_command_context(),
            ai_frame_id=ai_frame_id,
            old_index=current_index,
            new_index=clamped_index,
        )
        self._undo_stack.push(command)
        # Emit signal for UI update (command emits in undo)
        self._signals.emit_ai_frame_moved(ai_frame_id, current_index, clamped_index)
        return True

    def get_frames(self) -> list[AIFrame]:
        """Get all AI frames from the current project."""
        return self._ai_frame_service.get_frames(self._context.project)

    # ─── Frame Renaming ───────────────────────────────────────────────────────

    def rename_frame(self, frame_id: str, display_name: str | None) -> bool:
        """Set display name for an AI frame.

        Args:
            frame_id: ID of the AI frame (filename).
            display_name: New display name, or None to clear.

        Returns:
            True if frame was found and renamed.
        """
        if self._context.project is None:
            return False

        result = self._organization_service.rename_frame(
            ctx=self._get_command_context(),
            undo_stack=self._undo_stack,
            frame_id=frame_id,
            display_name=display_name,
        )
        if result:
            self._signals.emit_save_requested()
        return result

    def get_display_name(self, frame_id: str) -> str | None:
        """Get display name for an AI frame.

        Args:
            frame_id: ID of the AI frame (filename).

        Returns:
            Display name if set, None otherwise.
        """
        project = self._context.project
        if project is None:
            return None
        return self._organization_service.get_frame_display_name(project=project, frame_id=frame_id)

    # ─── Frame Tagging ────────────────────────────────────────────────────────

    def toggle_tag(self, frame_id: str, tag: str) -> bool:
        """Toggle a tag on an AI frame.

        Args:
            frame_id: ID of the AI frame (filename).
            tag: Tag to toggle (must be in FRAME_TAGS).

        Returns:
            True if frame was found and tag toggled.
        """
        if self._context.project is None:
            return False

        result = self._organization_service.toggle_frame_tag(
            ctx=self._get_command_context(),
            undo_stack=self._undo_stack,
            frame_id=frame_id,
            tag=tag,
        )
        if result:
            self._signals.emit_save_requested()
        return result

    def add_tag(self, frame_id: str, tag: str) -> bool:
        """Add a tag to an AI frame.

        Args:
            frame_id: ID of the AI frame (filename).
            tag: Tag to add (must be in FRAME_TAGS).

        Returns:
            True if frame was found and tag added.
        """
        project = self._context.project
        if project is None:
            return False
        return self._organization_service.add_frame_tag(project=project, frame_id=frame_id, tag=tag)

    def remove_tag(self, frame_id: str, tag: str) -> bool:
        """Remove a tag from an AI frame.

        Args:
            frame_id: ID of the AI frame (filename).
            tag: Tag to remove.

        Returns:
            True if frame was found and tag removed.
        """
        project = self._context.project
        if project is None:
            return False
        return self._organization_service.remove_frame_tag(project=project, frame_id=frame_id, tag=tag)

    def set_tags(self, frame_id: str, tags: frozenset[str]) -> bool:
        """Set all tags for an AI frame (replace existing).

        Args:
            frame_id: ID of the AI frame (filename).
            tags: New set of tags.

        Returns:
            True if frame was found and tags updated.
        """
        project = self._context.project
        if project is None:
            return False
        return self._organization_service.set_frame_tags(project=project, frame_id=frame_id, tags=tags)

    def get_tags(self, frame_id: str) -> frozenset[str]:
        """Get tags for an AI frame.

        Args:
            frame_id: ID of the AI frame (filename).

        Returns:
            Set of tags (empty if frame not found).
        """
        project = self._context.project
        if project is None:
            return frozenset()
        return self._organization_service.get_frame_tags(project=project, frame_id=frame_id)

    def get_frames_with_tag(self, tag: str) -> list[AIFrame]:
        """Get all AI frames with a specific tag.

        Args:
            tag: Tag to filter by.

        Returns:
            List of AIFrame objects with the tag.
        """
        project = self._context.project
        if project is None:
            return []
        return self._organization_service.get_frames_with_tag(project=project, tag=tag)

    @staticmethod
    def get_available_tags() -> frozenset[str]:
        """Get the set of valid frame tags.

        Returns:
            Set of valid tag names.
        """
        return OrganizationService.get_available_tags()
