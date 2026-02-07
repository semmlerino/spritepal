"""Service for managing frame mappings in frame mapping projects.

Provides mapping creation, removal, and lookup operations. This is a stateless
service - all methods take a project parameter rather than storing project state.

Signal emission and undo command orchestration remain in the controller. This
service provides the core business logic and state extraction for undo support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject

from core.frame_mapping_project import MappingStatus
from ui.frame_mapping.views.workbench_types import AlignmentState
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

logger = get_logger(__name__)


class MappingService(QObject):
    """Service for mapping operations in frame mapping projects.

    This is a stateless service - all methods take a project parameter
    rather than storing project state internally.

    Undo support:
        Methods that capture state for undo return dataclass tuples that
        the controller can use to build undo commands.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the mapping service.

        Args:
            parent: Optional Qt parent object
        """
        super().__init__(parent)

    def get_link_for_ai_frame(
        self,
        project: FrameMappingProject | None,
        ai_frame_id: str,
    ) -> str | None:
        """Get the game frame ID currently linked to an AI frame.

        Args:
            project: The frame mapping project
            ai_frame_id: ID of the AI frame to check

        Returns:
            Game frame ID if AI frame is linked, None otherwise
        """
        if project is None:
            return None
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        return mapping.game_frame_id if mapping else None

    def validate_mapping_frames(
        self,
        project: FrameMappingProject,
        ai_frame_id: str,
        game_frame_id: str,
    ) -> tuple[bool, str]:
        """Validate that both frames exist for a mapping.

        Args:
            project: The frame mapping project
            ai_frame_id: ID of the AI frame
            game_frame_id: ID of the game frame

        Returns:
            Tuple of (is_valid, error_message). Error message is empty if valid.
        """
        ai_frame = project.get_ai_frame_by_id(ai_frame_id)
        if ai_frame is None:
            return False, f"AI frame {ai_frame_id} not found"

        game_frame = project.get_game_frame_by_id(game_frame_id)
        if game_frame is None:
            return False, f"Game frame {game_frame_id} not found"

        return True, ""

    def capture_create_mapping_undo_state(
        self,
        project: FrameMappingProject,
        ai_frame_id: str,
        game_frame_id: str,
    ) -> tuple[str | None, str | None, AlignmentState | None, AlignmentState | None]:
        """Capture state needed for undo when creating a mapping.

        Returns the previous mapping states for both AI and game frames,
        which may need to be restored on undo.

        Args:
            project: The frame mapping project
            ai_frame_id: ID of the AI frame being mapped
            game_frame_id: ID of the game frame being mapped

        Returns:
            Tuple of (prev_ai_game_id, prev_game_ai_id, prev_ai_alignment, prev_game_alignment)
        """
        prev_ai_mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        prev_game_mapping = project.get_mapping_for_game_frame(game_frame_id)

        prev_ai_game_id = prev_ai_mapping.game_frame_id if prev_ai_mapping else None
        prev_game_ai_id = prev_game_mapping.ai_frame_id if prev_game_mapping else None

        prev_ai_alignment: AlignmentState | None = None
        prev_game_alignment: AlignmentState | None = None

        if prev_ai_mapping:
            prev_ai_alignment = AlignmentState.from_mapping(prev_ai_mapping)
        if prev_game_mapping and prev_game_ai_id != ai_frame_id:
            prev_game_alignment = AlignmentState.from_mapping(prev_game_mapping)

        return prev_ai_game_id, prev_game_ai_id, prev_ai_alignment, prev_game_alignment

    def capture_remove_mapping_undo_state(
        self,
        project: FrameMappingProject,
        ai_frame_id: str,
    ) -> tuple[str, AlignmentState, MappingStatus] | None:
        """Capture state needed for undo when removing a mapping.

        Args:
            project: The frame mapping project
            ai_frame_id: ID of the AI frame

        Returns:
            Tuple of (game_frame_id, alignment, status) or None if no mapping exists
        """
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is None:
            return None

        alignment = AlignmentState.from_mapping(mapping)

        return mapping.game_frame_id, alignment, mapping.status
