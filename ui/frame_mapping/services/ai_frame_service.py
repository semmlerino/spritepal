"""Service for managing AI frames in frame mapping projects.

Provides AI frame loading, adding, removal, and reordering. This is a stateless
service - all methods take a project parameter rather than storing project state.

Signal emission and undo command orchestration remain in the controller. This
service provides the core business logic only.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QObject

from core.frame_mapping_project import AIFrame
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

logger = get_logger(__name__)


class AIFrameService(QObject):
    """Service for AI frame operations in frame mapping projects.

    This is a stateless service - all methods take a project parameter
    rather than storing project state internally.

    Error handling:
        Methods return success/failure status. The controller should emit
        error signals based on these return values.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the AI frame service.

        Args:
            parent: Optional Qt parent object
        """
        super().__init__(parent)

    def load_frames_from_directory(
        self,
        project: FrameMappingProject,
        directory: Path,
    ) -> tuple[list[AIFrame], int]:
        """Load AI frames from a directory of PNG files.

        Scans the directory for PNG files and creates AIFrame objects.
        Does NOT modify the project - caller should use project.replace_ai_frames().

        Args:
            project: The frame mapping project (for context, not modified)
            directory: Directory containing PNG files

        Returns:
            Tuple of (frames list, orphaned_mapping_count_to_prune).
            Empty list if directory doesn't exist or has no PNGs.
        """
        if not directory.is_dir():
            logger.warning("Not a directory: %s", directory)
            return [], 0

        # Find all PNG files, sorted by name
        png_files = sorted(directory.glob("*.png"))
        if not png_files:
            logger.warning("No PNG files found in %s", directory)
            return [], 0

        frames: list[AIFrame] = []
        for idx, png_path in enumerate(png_files):
            width, height = self._get_image_dimensions(png_path)
            frame = AIFrame(
                path=png_path,
                index=idx,
                width=width,
                height=height,
            )
            frames.append(frame)

        # Calculate orphan count (mappings that won't have valid AI frame IDs)
        valid_ids = {f.id for f in frames}
        orphan_count = sum(1 for m in project.mappings if m.ai_frame_id not in valid_ids)

        logger.info(
            "Found %d PNG files in %s (orphan mappings: %d)",
            len(frames),
            directory,
            orphan_count,
        )
        return frames, orphan_count

    def create_frame_from_file(
        self,
        project: FrameMappingProject,
        file_path: Path,
    ) -> AIFrame | None:
        """Create an AIFrame from a PNG file.

        Does NOT add to project - caller should use project.add_ai_frame().

        Args:
            project: The frame mapping project (to check for duplicates)
            file_path: Path to the PNG file

        Returns:
            AIFrame if valid and not duplicate, None otherwise.
        """
        if not file_path.is_file() or file_path.suffix.lower() != ".png":
            logger.warning("Not a PNG file: %s", file_path)
            return None

        # Check if frame already exists (by path)
        for frame in project.ai_frames:
            if frame.path == file_path:
                logger.info("AI frame already exists: %s", file_path)
                return None

        width, height = self._get_image_dimensions(file_path)
        next_index = len(project.ai_frames)

        return AIFrame(
            path=file_path,
            index=next_index,
            width=width,
            height=height,
        )

    def find_frame_index(self, project: FrameMappingProject, frame_id: str) -> int:
        """Find the index of a frame by its ID.

        Args:
            project: The frame mapping project
            frame_id: ID of the AI frame

        Returns:
            Index (0-based) or -1 if not found
        """
        for i, frame in enumerate(project.ai_frames):
            if frame.id == frame_id:
                return i
        return -1

    def validate_reorder(
        self,
        project: FrameMappingProject,
        frame_id: str,
        new_index: int,
    ) -> tuple[int, int] | None:
        """Validate a reorder operation.

        Args:
            project: The frame mapping project
            frame_id: ID of the AI frame to move
            new_index: Target position (0-based)

        Returns:
            Tuple of (current_index, clamped_new_index) if valid, None if no-op or invalid
        """
        current_index = self.find_frame_index(project, frame_id)
        if current_index == -1:
            return None

        max_index = len(project.ai_frames) - 1
        clamped_index = max(0, min(new_index, max_index))

        if current_index == clamped_index:
            return None  # No-op

        return current_index, clamped_index

    def _get_image_dimensions(self, path: Path) -> tuple[int, int]:
        """Get image dimensions from header (fast).

        Args:
            path: Path to image file

        Returns:
            (width, height) or (0, 0) if reading fails
        """
        try:
            with Image.open(path) as img:
                return img.size
        except Exception:
            return 0, 0
