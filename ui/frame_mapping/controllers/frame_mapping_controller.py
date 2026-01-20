"""Controller for Frame Mapping workspace.

Handles business logic for loading frames, managing mappings, and coordinating
between the view panels.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

from core.frame_mapping_project import AIFrame, FrameMappingProject, GameFrame
from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import MesenCaptureParser

logger = logging.getLogger(__name__)


class FrameMappingController(QObject):
    """Controller for frame mapping operations.

    Manages the data model and coordinates view updates.

    Signals:
        project_changed: Emitted when project is loaded/created/modified
        ai_frames_loaded: Emitted when AI frames are loaded (count)
        game_frame_added: Emitted when a game frame is added (frame_id)
        mapping_created: Emitted when a mapping is created (ai_index, game_id)
        mapping_removed: Emitted when a mapping is removed (ai_index)
        error_occurred: Emitted on errors (error_message)
    """

    project_changed = Signal()
    ai_frames_loaded = Signal(int)  # count
    game_frame_added = Signal(str)  # game frame ID
    mapping_created = Signal(int, str)  # ai_index, game_id
    mapping_removed = Signal(int)  # ai_index
    error_occurred = Signal(str)  # error message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._project: FrameMappingProject | None = None
        self._game_frame_previews: dict[str, QPixmap] = {}

    @property
    def project(self) -> FrameMappingProject | None:
        """Get the current project."""
        return self._project

    @property
    def has_project(self) -> bool:
        """Check if a project is loaded."""
        return self._project is not None

    def new_project(self, name: str = "Untitled") -> None:
        """Create a new empty project.

        Args:
            name: Project name
        """
        self._project = FrameMappingProject(name=name)
        self._game_frame_previews.clear()
        self.project_changed.emit()
        logger.info("Created new frame mapping project: %s", name)

    def load_project(self, path: Path) -> bool:
        """Load a project from file.

        Args:
            path: Path to project file

        Returns:
            True if loaded successfully
        """
        try:
            self._project = FrameMappingProject.load(path)
            self._game_frame_previews.clear()
            self.project_changed.emit()
            logger.info("Loaded frame mapping project from %s", path)
            return True
        except Exception as e:
            logger.exception("Failed to load project from %s", path)
            self.error_occurred.emit(f"Failed to load project: {e}")
            return False

    def save_project(self, path: Path) -> bool:
        """Save the current project to file.

        Args:
            path: Destination path

        Returns:
            True if saved successfully
        """
        if self._project is None:
            self.error_occurred.emit("No project to save")
            return False

        try:
            self._project.save(path)
            logger.info("Saved frame mapping project to %s", path)
            return True
        except Exception as e:
            logger.exception("Failed to save project to %s", path)
            self.error_occurred.emit(f"Failed to save project: {e}")
            return False

    def load_ai_frames_from_directory(self, directory: Path) -> int:
        """Load AI frames from a directory of PNG files.

        Args:
            directory: Directory containing PNG files

        Returns:
            Number of frames loaded
        """
        if self._project is None:
            self.new_project()

        if not directory.is_dir():
            self.error_occurred.emit(f"Not a directory: {directory}")
            return 0

        # Find all PNG files, sorted by name
        png_files = sorted(directory.glob("*.png"))
        if not png_files:
            self.error_occurred.emit(f"No PNG files found in {directory}")
            return 0

        frames: list[AIFrame] = []
        for idx, png_path in enumerate(png_files):
            # Get image dimensions
            img = QImage(str(png_path))
            width = img.width() if not img.isNull() else 0
            height = img.height() if not img.isNull() else 0

            frame = AIFrame(
                path=png_path,
                index=idx,
                width=width,
                height=height,
            )
            frames.append(frame)

        self._project.ai_frames = frames  # type: ignore[union-attr]
        self._project.ai_frames_dir = directory  # type: ignore[union-attr]

        self.ai_frames_loaded.emit(len(frames))
        self.project_changed.emit()
        logger.info("Loaded %d AI frames from %s", len(frames), directory)
        return len(frames)

    def import_mesen_capture(self, capture_path: Path) -> GameFrame | None:
        """Import a game frame from a Mesen 2 capture file.

        Args:
            capture_path: Path to capture JSON file

        Returns:
            The created GameFrame, or None on error
        """
        if self._project is None:
            self.new_project()

        try:
            # Parse the capture file
            parser = MesenCaptureParser()
            capture_result = parser.parse_file(capture_path)

            if not capture_result.has_entries:
                self.error_occurred.emit(f"No sprite entries in capture: {capture_path}")
                return None

            # Generate frame ID from filename or ROM offsets
            frame_id = capture_path.stem
            if frame_id.startswith("sprite_capture_"):
                frame_id = frame_id.replace("sprite_capture_", "")

            # Get unique ROM offsets
            rom_offsets = capture_result.unique_rom_offsets

            # Render preview - create a new renderer for each capture
            renderer = CaptureRenderer(capture_result)
            preview_img = renderer.render_composite()

            # Convert PIL Image to QPixmap
            from io import BytesIO

            buffer = BytesIO()
            preview_img.save(buffer, format="PNG")
            buffer.seek(0)
            qimg = QImage()
            qimg.loadFromData(buffer.read())
            pixmap = QPixmap.fromImage(qimg)
            self._game_frame_previews[frame_id] = pixmap

            # Create game frame
            bbox = capture_result.bounding_box
            frame = GameFrame(
                id=frame_id,
                rom_offsets=rom_offsets,
                capture_path=capture_path,
                palette_index=0,  # Could extract from capture
                width=bbox.width,
                height=bbox.height,
            )

            self._project.game_frames.append(frame)  # type: ignore[union-attr]
            self.game_frame_added.emit(frame_id)
            self.project_changed.emit()
            logger.info("Imported game frame %s from %s", frame_id, capture_path)
            return frame

        except Exception as e:
            logger.exception("Failed to import capture from %s", capture_path)
            self.error_occurred.emit(f"Failed to import capture: {e}")
            return None

    def import_capture_directory(self, directory: Path) -> int:
        """Import all captures from a directory.

        Args:
            directory: Directory containing capture JSON files

        Returns:
            Number of captures imported
        """
        if not directory.is_dir():
            self.error_occurred.emit(f"Not a directory: {directory}")
            return 0

        json_files = sorted(directory.glob("sprite_capture_*.json"))
        if not json_files:
            json_files = sorted(directory.glob("*.json"))

        imported = 0
        for json_path in json_files:
            if self.import_mesen_capture(json_path):
                imported += 1

        logger.info("Imported %d captures from %s", imported, directory)
        return imported

    def create_mapping(self, ai_frame_index: int, game_frame_id: str) -> bool:
        """Create a mapping between an AI frame and a game frame.

        Args:
            ai_frame_index: Index of the AI frame
            game_frame_id: ID of the game frame

        Returns:
            True if mapping was created
        """
        if self._project is None:
            self.error_occurred.emit("No project loaded")
            return False

        # Verify both frames exist
        ai_frame = self._project.get_ai_frame_by_index(ai_frame_index)
        if ai_frame is None:
            self.error_occurred.emit(f"AI frame {ai_frame_index} not found")
            return False

        game_frame = self._project.get_game_frame_by_id(game_frame_id)
        if game_frame is None:
            self.error_occurred.emit(f"Game frame {game_frame_id} not found")
            return False

        self._project.create_mapping(ai_frame_index, game_frame_id)
        self.mapping_created.emit(ai_frame_index, game_frame_id)
        self.project_changed.emit()
        logger.info("Created mapping: AI frame %d -> Game frame %s", ai_frame_index, game_frame_id)
        return True

    def remove_mapping(self, ai_frame_index: int) -> bool:
        """Remove a mapping for an AI frame.

        Args:
            ai_frame_index: Index of the AI frame

        Returns:
            True if a mapping was removed
        """
        if self._project is None:
            return False

        if self._project.remove_mapping_for_ai_frame(ai_frame_index):
            self.mapping_removed.emit(ai_frame_index)
            self.project_changed.emit()
            logger.info("Removed mapping for AI frame %d", ai_frame_index)
            return True
        return False

    def get_game_frame_preview(self, frame_id: str) -> QPixmap | None:
        """Get the rendered preview pixmap for a game frame.

        Args:
            frame_id: Game frame ID

        Returns:
            QPixmap preview or None if not available
        """
        return self._game_frame_previews.get(frame_id)

    def get_ai_frames(self) -> list[AIFrame]:
        """Get all AI frames from the current project."""
        if self._project is None:
            return []
        return self._project.ai_frames

    def get_game_frames(self) -> list[GameFrame]:
        """Get all game frames from the current project."""
        if self._project is None:
            return []
        return self._project.game_frames
