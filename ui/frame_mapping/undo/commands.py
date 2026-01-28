"""Command classes for frame mapping undo/redo operations.

Each command encapsulates a single undoable action with its state
before and after execution. Commands use structural typing (duck typing)
to implement the FrameMappingCommand protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


# =============================================================================
# Tier 1: Core Mapping Commands
# =============================================================================


@dataclass
class CreateMappingCommand:
    """Command to create a mapping between an AI frame and a game frame.

    Captures previous mappings for both the AI frame (if re-mapped) and the
    game frame (if it was previously linked to another AI frame).
    """

    controller: FrameMappingController
    ai_frame_id: str
    game_frame_id: str
    # Previous state for undo (all 7 alignment properties)
    prev_ai_mapping_game_id: str | None = None  # Game frame previously linked to this AI frame
    prev_game_mapping_ai_id: str | None = None  # AI frame previously linked to this game frame
    prev_ai_mapping_alignment: tuple[int, int, bool, bool, float, float, str] | None = None
    prev_game_mapping_alignment: tuple[int, int, bool, bool, float, float, str] | None = None

    @property
    def description(self) -> str:
        return f"Link {self.ai_frame_id} to {self.game_frame_id}"

    def execute(self) -> None:
        self.controller._create_mapping_no_history(self.ai_frame_id, self.game_frame_id)

    def undo(self) -> None:
        # Remove the mapping we just created
        self.controller._remove_mapping_no_history(self.ai_frame_id)

        # Restore previous AI frame mapping if it existed
        if self.prev_ai_mapping_game_id is not None:
            self.controller._create_mapping_no_history(self.ai_frame_id, self.prev_ai_mapping_game_id)
            if self.prev_ai_mapping_alignment:
                x, y, fh, fv, scale, sharpen, resampling = self.prev_ai_mapping_alignment
                self.controller._update_alignment_no_history(self.ai_frame_id, x, y, fh, fv, scale, sharpen, resampling)

        # Restore previous game frame mapping if it existed
        if self.prev_game_mapping_ai_id is not None:
            self.controller._create_mapping_no_history(self.prev_game_mapping_ai_id, self.game_frame_id)
            if self.prev_game_mapping_alignment:
                x, y, fh, fv, scale, sharpen, resampling = self.prev_game_mapping_alignment
                self.controller._update_alignment_no_history(
                    self.prev_game_mapping_ai_id, x, y, fh, fv, scale, sharpen, resampling
                )


@dataclass
class RemoveMappingCommand:
    """Command to remove a mapping for an AI frame."""

    controller: FrameMappingController
    ai_frame_id: str
    # Previous state for undo (all 7 alignment properties)
    removed_game_frame_id: str | None = None
    removed_alignment: tuple[int, int, bool, bool, float, float, str] | None = None
    removed_status: str = "mapped"

    @property
    def description(self) -> str:
        return f"Unlink {self.ai_frame_id}"

    def execute(self) -> None:
        self.controller._remove_mapping_no_history(self.ai_frame_id)

    def undo(self) -> None:
        if self.removed_game_frame_id is not None:
            self.controller._create_mapping_no_history(self.ai_frame_id, self.removed_game_frame_id)
            if self.removed_alignment:
                x, y, fh, fv, scale, sharpen, resampling = self.removed_alignment
                self.controller._update_alignment_no_history(self.ai_frame_id, x, y, fh, fv, scale, sharpen, resampling)
            # Restore status
            self.controller._set_mapping_status_no_history(self.ai_frame_id, self.removed_status)


@dataclass
class UpdateAlignmentCommand:
    """Command to update alignment for a mapping."""

    controller: FrameMappingController
    ai_frame_id: str
    # New alignment values
    new_offset_x: int
    new_offset_y: int
    new_flip_h: bool
    new_flip_v: bool
    new_scale: float
    new_sharpen: float = 0.0
    new_resampling: str = "lanczos"
    # Previous state for undo
    old_offset_x: int = 0
    old_offset_y: int = 0
    old_flip_h: bool = False
    old_flip_v: bool = False
    old_scale: float = 1.0
    old_sharpen: float = 0.0
    old_resampling: str = "lanczos"
    old_status: str = "mapped"

    @property
    def description(self) -> str:
        return f"Adjust alignment for {self.ai_frame_id}"

    def execute(self) -> None:
        self.controller._update_alignment_no_history(
            self.ai_frame_id,
            self.new_offset_x,
            self.new_offset_y,
            self.new_flip_h,
            self.new_flip_v,
            self.new_scale,
            self.new_sharpen,
            self.new_resampling,
        )

    def undo(self) -> None:
        self.controller._update_alignment_no_history(
            self.ai_frame_id,
            self.old_offset_x,
            self.old_offset_y,
            self.old_flip_h,
            self.old_flip_v,
            self.old_scale,
            self.old_sharpen,
            self.old_resampling,
        )
        # Restore original status
        self.controller._set_mapping_status_no_history(self.ai_frame_id, self.old_status)


# =============================================================================
# Tier 2: Organization Commands
# =============================================================================


@dataclass
class RenameAIFrameCommand:
    """Command to rename an AI frame (set display name)."""

    controller: FrameMappingController
    frame_id: str
    new_name: str | None
    old_name: str | None = None

    @property
    def description(self) -> str:
        if self.new_name:
            return f"Rename frame to '{self.new_name}'"
        return f"Clear name for {self.frame_id}"

    def execute(self) -> None:
        self.controller._rename_frame_no_history(self.frame_id, self.new_name)

    def undo(self) -> None:
        self.controller._rename_frame_no_history(self.frame_id, self.old_name)


@dataclass
class RenameCaptureCommand:
    """Command to rename a game frame (capture)."""

    controller: FrameMappingController
    game_frame_id: str
    new_name: str | None
    old_name: str | None = None

    @property
    def description(self) -> str:
        if self.new_name:
            return f"Rename capture to '{self.new_name}'"
        return f"Clear name for {self.game_frame_id}"

    def execute(self) -> None:
        self.controller._rename_capture_no_history(self.game_frame_id, self.new_name)

    def undo(self) -> None:
        self.controller._rename_capture_no_history(self.game_frame_id, self.old_name)


@dataclass
class ToggleFrameTagCommand:
    """Command to toggle a tag on an AI frame."""

    controller: FrameMappingController
    frame_id: str
    tag: str
    was_present: bool = False

    @property
    def description(self) -> str:
        action = "Remove" if self.was_present else "Add"
        return f"{action} '{self.tag}' tag"

    def execute(self) -> None:
        # Toggle adds if not present, removes if present
        self.controller._toggle_frame_tag_no_history(self.frame_id, self.tag)

    def undo(self) -> None:
        # Toggle again to reverse
        self.controller._toggle_frame_tag_no_history(self.frame_id, self.tag)
