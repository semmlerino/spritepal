"""Command classes for frame mapping undo/redo operations.

Each command encapsulates a single undoable action with its state
before and after execution. Commands use structural typing (duck typing)
to implement the FrameMappingCommand protocol.

Commands use CommandContext to access services for mutations and
signal emitter for undo notifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ui.frame_mapping.views.workbench_types import AlignmentState
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from ui.frame_mapping.undo.command_context import CommandContext

logger = get_logger(__name__)


# =============================================================================
# Tier 1: Core Mapping Commands
# =============================================================================


@dataclass
class CreateMappingCommand:
    """Command to create a mapping between an AI frame and a game frame.

    Captures previous mappings for both the AI frame (if re-mapped) and the
    game frame (if it was previously linked to another AI frame).
    """

    ctx: CommandContext
    ai_frame_id: str
    game_frame_id: str
    # Previous state for undo
    prev_ai_mapping_game_id: str | None = None  # Game frame previously linked to this AI frame
    prev_game_mapping_ai_id: str | None = None  # AI frame previously linked to this game frame
    prev_ai_mapping_alignment: AlignmentState | None = None
    prev_game_mapping_alignment: AlignmentState | None = None

    @property
    def description(self) -> str:
        return f"Link {self.ai_frame_id} to {self.game_frame_id}"

    def execute(self) -> None:
        self.ctx.project.create_mapping(self.ai_frame_id, self.game_frame_id)

    def undo(self) -> None:
        # Remove the mapping we just created
        self.ctx.project.remove_mapping_for_ai_frame(self.ai_frame_id)

        # Restore previous AI frame mapping if it existed
        if self.prev_ai_mapping_game_id is not None:
            self.ctx.project.create_mapping(self.ai_frame_id, self.prev_ai_mapping_game_id)
            if self.prev_ai_mapping_alignment is not None:
                self.ctx.alignment_service.apply_alignment_to_project(
                    self.ctx.project, self.ai_frame_id, self.prev_ai_mapping_alignment
                )
            # Emit signal for restored AI frame mapping
            self.ctx.signal_emitter.emit_mapping_created(self.ai_frame_id, self.prev_ai_mapping_game_id)

        # Restore previous game frame mapping if it existed
        if self.prev_game_mapping_ai_id is not None:
            self.ctx.project.create_mapping(self.prev_game_mapping_ai_id, self.game_frame_id)
            if self.prev_game_mapping_alignment is not None:
                self.ctx.alignment_service.apply_alignment_to_project(
                    self.ctx.project, self.prev_game_mapping_ai_id, self.prev_game_mapping_alignment
                )
            # Emit signal for restored game frame mapping
            self.ctx.signal_emitter.emit_mapping_created(self.prev_game_mapping_ai_id, self.game_frame_id)

        # If no mapping was restored, emit removal signal
        if self.prev_ai_mapping_game_id is None:
            self.ctx.signal_emitter.emit_mapping_removed(self.ai_frame_id)


@dataclass
class RemoveMappingCommand:
    """Command to remove a mapping for an AI frame."""

    ctx: CommandContext
    ai_frame_id: str
    # Previous state for undo
    removed_game_frame_id: str | None = None
    removed_alignment: AlignmentState | None = None
    removed_status: str = "mapped"

    @property
    def description(self) -> str:
        return f"Unlink {self.ai_frame_id}"

    def execute(self) -> None:
        self.ctx.project.remove_mapping_for_ai_frame(self.ai_frame_id)

    def undo(self) -> None:
        if self.removed_game_frame_id is not None:
            self.ctx.project.create_mapping(self.ai_frame_id, self.removed_game_frame_id)
            if self.removed_alignment is not None:
                self.ctx.alignment_service.apply_alignment_to_project(
                    self.ctx.project, self.ai_frame_id, self.removed_alignment
                )
            # Restore status
            mapping = self.ctx.project.get_mapping_for_ai_frame(self.ai_frame_id)
            if mapping is not None:
                mapping.status = self.removed_status
            # Emit signals so UI updates
            self.ctx.signal_emitter.emit_mapping_created(self.ai_frame_id, self.removed_game_frame_id)
            self.ctx.signal_emitter.emit_alignment_updated(self.ai_frame_id)


@dataclass
class UpdateAlignmentCommand:
    """Command to update alignment for a mapping."""

    ctx: CommandContext
    ai_frame_id: str
    new_alignment: AlignmentState
    old_alignment: AlignmentState
    old_status: str = "mapped"

    @property
    def description(self) -> str:
        return f"Adjust alignment for {self.ai_frame_id}"

    def execute(self) -> None:
        self.ctx.alignment_service.apply_alignment_to_project(
            self.ctx.project, self.ai_frame_id, self.new_alignment
        )

    def undo(self) -> None:
        self.ctx.alignment_service.apply_alignment_to_project(
            self.ctx.project, self.ai_frame_id, self.old_alignment
        )
        # Restore original status
        mapping = self.ctx.project.get_mapping_for_ai_frame(self.ai_frame_id)
        if mapping is not None:
            mapping.status = self.old_status
        # Emit signal so UI updates
        self.ctx.signal_emitter.emit_alignment_updated(self.ai_frame_id)


# =============================================================================
# Tier 2: Organization Commands
# =============================================================================


@dataclass
class RenameAIFrameCommand:
    """Command to rename an AI frame (set display name)."""

    ctx: CommandContext
    frame_id: str
    new_name: str | None
    old_name: str | None = None

    @property
    def description(self) -> str:
        if self.new_name:
            return f"Rename frame to '{self.new_name}'"
        return f"Clear name for {self.frame_id}"

    def execute(self) -> None:
        self.ctx.organization_service._rename_frame_no_history(
            self.ctx.project, self.frame_id, self.new_name
        )

    def undo(self) -> None:
        self.ctx.organization_service._rename_frame_no_history(
            self.ctx.project, self.frame_id, self.old_name
        )
        # Emit signal so UI updates
        self.ctx.signal_emitter.emit_frame_renamed(self.frame_id)


@dataclass
class RenameCaptureCommand:
    """Command to rename a game frame (capture)."""

    ctx: CommandContext
    game_frame_id: str
    new_name: str | None
    old_name: str | None = None

    @property
    def description(self) -> str:
        if self.new_name:
            return f"Rename capture to '{self.new_name}'"
        return f"Clear name for {self.game_frame_id}"

    def execute(self) -> None:
        self.ctx.organization_service._rename_capture_no_history(
            self.ctx.project, self.game_frame_id, self.new_name
        )

    def undo(self) -> None:
        self.ctx.organization_service._rename_capture_no_history(
            self.ctx.project, self.game_frame_id, self.old_name
        )
        # Emit signal so UI updates
        self.ctx.signal_emitter.emit_capture_renamed(self.game_frame_id)


@dataclass
class ToggleFrameTagCommand:
    """Command to toggle a tag on an AI frame."""

    ctx: CommandContext
    frame_id: str
    tag: str
    was_present: bool = False

    @property
    def description(self) -> str:
        action = "Remove" if self.was_present else "Add"
        return f"{action} '{self.tag}' tag"

    def execute(self) -> None:
        # Toggle adds if not present, removes if present
        self.ctx.organization_service._toggle_frame_tag_no_history(
            self.ctx.project, self.frame_id, self.tag
        )

    def undo(self) -> None:
        # Toggle again to reverse
        self.ctx.organization_service._toggle_frame_tag_no_history(
            self.ctx.project, self.frame_id, self.tag
        )
        # Emit signal so UI updates
        self.ctx.signal_emitter.emit_frame_tags_changed(self.frame_id)


@dataclass
class ReorderAIFrameCommand:
    """Command to reorder an AI frame to a new position."""

    ctx: CommandContext
    ai_frame_id: str
    old_index: int
    new_index: int

    @property
    def description(self) -> str:
        return f"Move frame from position {self.old_index + 1} to {self.new_index + 1}"

    def execute(self) -> None:
        success, _old, actual_new = self.ctx.reorder_ai_frame_no_history(self.ai_frame_id, self.new_index)
        if success:
            logger.info("Reordered AI frame %s to index %d", self.ai_frame_id, actual_new)

    def undo(self) -> None:
        success, _old, actual_old = self.ctx.reorder_ai_frame_no_history(self.ai_frame_id, self.old_index)
        if success:
            # Emit signal so UI updates (new_index, old_index params are from undo perspective)
            self.ctx.signal_emitter.emit_ai_frame_moved(self.ai_frame_id, self.new_index, actual_old)
