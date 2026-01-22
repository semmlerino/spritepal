"""Controller for Frame Mapping workspace.

Handles business logic for loading frames, managing mappings, and coordinating
between the view panels.
"""

from __future__ import annotations

import logging
import math
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap

from ui.common.qt_image_utils import pil_to_qpixmap

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

from core.frame_mapping_project import AIFrame, FrameMappingProject, GameFrame
from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import (
    CaptureResult,
    MesenCaptureParser,
)
from core.palette_utils import quantize_to_palette, snes_palette_to_rgb
from core.rom_injector import ROMInjector
from core.services.rom_verification_service import ROMVerificationService
from core.services.sprite_compositor import SpriteCompositor, TransformParams
from core.types import CompressionType
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Transparency threshold for injection - pixels with alpha < this are treated as transparent
# AI-generated images often have semi-transparent edges; 128 captures anti-aliased pixels
INJECTION_TRANSPARENCY_THRESHOLD = 128


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
    game_frame_removed = Signal(str)  # game frame ID
    mapping_created = Signal(int, str)  # ai_index, game_id
    mapping_removed = Signal(int)  # ai_index
    mapping_injected = Signal(int, str)  # ai_index, message
    error_occurred = Signal(str)  # error message
    status_update = Signal(str)  # status message for UI feedback
    save_requested = Signal()  # Emitted when auto-save should occur (e.g., after injection)
    stale_entries_warning = Signal(str)  # frame_id - Emitted when stored entry IDs are stale

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._project: FrameMappingProject | None = None
        # Cache stores (pixmap, mtime) for invalidation on file change
        self._game_frame_previews: dict[str, tuple[QPixmap, float]] = {}

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

    def _generate_unique_frame_id(self, base_id: str) -> str:
        """Generate a unique frame ID, adding suffix if collision exists.

        Args:
            base_id: The initial frame ID (e.g., from filename)

        Returns:
            A unique frame ID, potentially with _N suffix
        """
        if self._project is None:
            return base_id

        existing_ids = {gf.id for gf in self._project.game_frames}
        if base_id not in existing_ids:
            return base_id

        # Find next available suffix
        counter = 1
        while f"{base_id}_{counter}" in existing_ids:
            counter += 1

        unique_id = f"{base_id}_{counter}"
        logger.info("Renamed duplicate capture ID %s -> %s", base_id, unique_id)
        return unique_id

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

        # Replace AI frames using facade (handles index invalidation)
        self._project.replace_ai_frames(frames, directory)  # type: ignore[union-attr]

        # Bug #3 fix: Prune orphaned mappings that reference non-existent AI frame IDs
        valid_ids = {f.id for f in frames}
        removed = self._project.filter_mappings_by_valid_ai_ids(valid_ids)  # type: ignore[union-attr]
        if removed > 0:
            logger.info(
                "Pruning %d orphaned mappings after AI frames reload",
                removed,
            )

        self.ai_frames_loaded.emit(len(frames))
        self.project_changed.emit()
        logger.info("Loaded %d AI frames from %s", len(frames), directory)
        return len(frames)

    def import_mesen_capture(self, capture_path: Path, parent: QObject | None = None) -> GameFrame | None:
        """Import a game frame from a Mesen 2 capture file.

        Shows a sprite selection dialog to let the user choose which OAM entries
        to include in the import.

        Args:
            capture_path: Path to capture JSON file
            parent: Parent widget for the selection dialog

        Returns:
            The created GameFrame, or None on error/cancel
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

            # Show sprite selection dialog
            from PySide6.QtWidgets import QDialog, QWidget

            from ui.frame_mapping.dialogs.sprite_selection_dialog import (
                SpriteSelectionDialog,
            )

            parent_widget = parent if isinstance(parent, QWidget) else None
            dialog = SpriteSelectionDialog(capture_result, parent=parent_widget)

            if dialog.exec() != QDialog.DialogCode.Accepted:
                # User cancelled
                return None

            selected_entries = dialog.selected_entries
            if not selected_entries:
                self.error_occurred.emit("No sprites selected")
                return None

            # Create filtered CaptureResult with only selected entries
            from core.mesen_integration.click_extractor import CaptureResult

            filtered_capture = CaptureResult(
                frame=capture_result.frame,
                visible_count=len(selected_entries),
                obsel=capture_result.obsel,
                entries=selected_entries,
                palettes=capture_result.palettes,
                timestamp=capture_result.timestamp,
            )

            # Generate frame ID from filename or ROM offsets
            frame_id = capture_path.stem
            if frame_id.startswith("sprite_capture_"):
                frame_id = frame_id.replace("sprite_capture_", "")

            # Bug #4 fix: Ensure unique ID when importing captures with same filename
            frame_id = self._generate_unique_frame_id(frame_id)

            # Get unique ROM offsets from selected entries only
            rom_offsets = filtered_capture.unique_rom_offsets

            # Render preview using filtered capture (cropped to bounding box)
            renderer = CaptureRenderer(filtered_capture)
            preview_img = renderer.render_selection()

            # Convert PIL Image to QPixmap and cache with mtime for invalidation
            pixmap = pil_to_qpixmap(preview_img)
            mtime = capture_path.stat().st_mtime if capture_path.exists() else 0.0
            self._game_frame_previews[frame_id] = (pixmap, mtime)

            # Create game frame with selected entry IDs for filtering on retrieval
            bbox = filtered_capture.bounding_box
            # Default all ROM offsets to RAW compression (user can change in workbench)
            default_compression_types = dict.fromkeys(rom_offsets, "raw")
            frame = GameFrame(
                id=frame_id,
                rom_offsets=rom_offsets,
                capture_path=capture_path,
                palette_index=0,  # Could extract from capture
                width=bbox.width,
                height=bbox.height,
                selected_entry_ids=[entry.id for entry in selected_entries],
                compression_types=default_compression_types,
            )

            self._project.add_game_frame(frame)  # type: ignore[union-attr]
            self.game_frame_added.emit(frame_id)
            self.project_changed.emit()
            logger.info(
                "Imported game frame %s from %s (%d of %d entries selected)",
                frame_id,
                capture_path,
                len(selected_entries),
                len(capture_result.entries),
            )
            return frame

        except Exception as e:
            logger.exception("Failed to import capture from %s", capture_path)
            self.error_occurred.emit(f"Failed to import capture: {e}")
            return None

    def import_capture_directory(self, directory: Path, parent: QObject | None = None) -> int:
        """Import all captures from a directory.

        Shows a sprite selection dialog for each capture file.

        Args:
            directory: Directory containing capture JSON files
            parent: Parent widget for selection dialogs

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
            if self.import_mesen_capture(json_path, parent):
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

        # Use ID-based mapping (stable across reloads)
        self._project.create_mapping(ai_frame.id, game_frame_id)
        self.mapping_created.emit(ai_frame_index, game_frame_id)
        self.project_changed.emit()
        logger.info(
            "Created mapping: AI frame %s (idx %d) -> Game frame %s", ai_frame.id, ai_frame_index, game_frame_id
        )
        return True

    def get_existing_link_for_game_frame(self, game_frame_id: str) -> int | None:
        """Get the AI frame index currently linked to a game frame.

        Args:
            game_frame_id: ID of the game frame to check

        Returns:
            AI frame index if game frame is linked, None otherwise
        """
        if self._project is None:
            return None
        return self._project.get_ai_frame_index_linked_to_game_frame(game_frame_id)

    def get_existing_link_for_ai_frame(self, ai_frame_index: int) -> str | None:
        """Get the game frame ID currently linked to an AI frame.

        Args:
            ai_frame_index: Index of the AI frame to check

        Returns:
            Game frame ID if AI frame is linked, None otherwise
        """
        if self._project is None:
            return None
        mapping = self._project.get_mapping_for_ai_frame_index(ai_frame_index)
        return mapping.game_frame_id if mapping else None

    def remove_mapping(self, ai_frame_index: int) -> bool:
        """Remove a mapping for an AI frame.

        Args:
            ai_frame_index: Index of the AI frame

        Returns:
            True if a mapping was removed
        """
        if self._project is None:
            return False

        if self._project.remove_mapping_for_ai_frame_index(ai_frame_index):
            self.mapping_removed.emit(ai_frame_index)
            self.project_changed.emit()
            logger.info("Removed mapping for AI frame %d", ai_frame_index)
            return True
        return False

    def update_mapping_alignment(
        self,
        ai_frame_index: int,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float = 1.0,
        set_edited: bool = True,
    ) -> bool:
        """Update alignment for a mapping.

        Args:
            ai_frame_index: Index of the AI frame
            offset_x: X offset for alignment
            offset_y: Y offset for alignment
            flip_h: Horizontal flip state
            flip_v: Vertical flip state
            scale: Scale factor (0.1 - 10.0)
            set_edited: If True and status is not 'injected', set status to 'edited'.
                        Use False for auto-centering during initial link creation.

        Returns:
            True if alignment was updated
        """
        if self._project is None:
            return False

        if self._project.update_mapping_alignment_by_index(
            ai_frame_index, offset_x, offset_y, flip_h, flip_v, scale, set_edited
        ):
            self.project_changed.emit()
            logger.info(
                "Updated alignment for AI frame %d: offset=(%d, %d), flip=(%s, %s), scale=%.2f",
                ai_frame_index,
                offset_x,
                offset_y,
                flip_h,
                flip_v,
                scale,
            )
            return True
        return False

    def get_game_frame_preview(self, frame_id: str) -> QPixmap | None:
        """Get the rendered preview pixmap for a game frame.

        If the preview is not cached but the capture file exists, attempts to
        regenerate the preview from the capture file. Respects selected_entry_ids
        filtering to show only the selected entries in the preview.

        Bug #5 fix: Checks file mtime and regenerates if source file changed.

        Args:
            frame_id: Game frame ID

        Returns:
            QPixmap preview or None if not available
        """
        # Check cache with mtime validation
        if frame_id in self._game_frame_previews:
            cached_pixmap, cached_mtime = self._game_frame_previews[frame_id]

            # Get game frame to check file mtime
            if self._project is not None:
                game_frame = self._project.get_game_frame_by_id(frame_id)
                if game_frame and game_frame.capture_path and game_frame.capture_path.exists():
                    current_mtime = game_frame.capture_path.stat().st_mtime
                    if current_mtime != cached_mtime:
                        # File changed, fall through to regenerate
                        logger.debug(
                            "Preview cache invalidated for %s (mtime changed)",
                            frame_id,
                        )
                    else:
                        return cached_pixmap
                else:
                    # No file to compare, return cached
                    return cached_pixmap
            else:
                return cached_pixmap

        # Try to regenerate from capture file (with filtering applied)
        capture_result = self.get_capture_result_for_game_frame(frame_id)
        if capture_result is None or not capture_result.has_entries:
            return None

        try:
            renderer = CaptureRenderer(capture_result)
            preview_img = renderer.render_selection()

            # Convert PIL Image to QPixmap and cache with mtime
            pixmap = pil_to_qpixmap(preview_img)
            mtime = 0.0
            if self._project is not None:
                game_frame = self._project.get_game_frame_by_id(frame_id)
                if game_frame and game_frame.capture_path and game_frame.capture_path.exists():
                    mtime = game_frame.capture_path.stat().st_mtime

            self._game_frame_previews[frame_id] = (pixmap, mtime)
            logger.debug("Regenerated preview for game frame %s from capture file", frame_id)
            return pixmap

        except Exception as e:
            logger.warning("Failed to regenerate preview for game frame %s: %s", frame_id, e)
            return None

    def get_capture_result_for_game_frame(self, frame_id: str) -> CaptureResult | None:
        """Get the CaptureResult for a game frame.

        Parses the capture file associated with the game frame and returns
        the CaptureResult needed for preview generation. If the game frame
        has stored selected entry IDs, only those entries are returned.

        If stored entry IDs no longer exist in the capture file (stale),
        falls back to rom_offset filtering (mirrors injection behavior) and
        emits stale_entries_warning signal.

        Args:
            frame_id: Game frame ID

        Returns:
            CaptureResult or None if not available
        """
        if self._project is None:
            return None

        game_frame = self._project.get_game_frame_by_id(frame_id)
        if game_frame is None or game_frame.capture_path is None:
            return None

        capture_path = game_frame.capture_path
        if not capture_path.exists():
            logger.warning("Capture file not found for game frame %s: %s", frame_id, capture_path)
            return None

        try:
            parser = MesenCaptureParser()
            capture_result = parser.parse_file(capture_path)

            if not capture_result.has_entries:
                return None

            # Apply selection filter if stored (preserves import-time selection)
            if game_frame.selected_entry_ids:
                selected_ids = set(game_frame.selected_entry_ids)
                filtered_entries = [entry for entry in capture_result.entries if entry.id in selected_ids]

                if not filtered_entries:
                    # Stale entry IDs - fall back to rom_offset filtering (mirrors injection)
                    logger.warning(
                        "Stored entry IDs %s not found in capture %s. Using rom_offset fallback.",
                        game_frame.selected_entry_ids,
                        capture_path,
                    )
                    self.stale_entries_warning.emit(frame_id)
                    # Fallback to rom_offset filtering (mirrors inject_mapping behavior)
                    filtered_entries = [
                        entry for entry in capture_result.entries if entry.rom_offset in game_frame.rom_offsets
                    ]
                    if filtered_entries:
                        capture_result = CaptureResult(
                            frame=capture_result.frame,
                            visible_count=len(filtered_entries),
                            obsel=capture_result.obsel,
                            entries=filtered_entries,
                            palettes=capture_result.palettes,
                            timestamp=capture_result.timestamp,
                        )
                    # If still no entries, return unfiltered as last resort
                else:
                    # Create filtered CaptureResult with only selected entries
                    capture_result = CaptureResult(
                        frame=capture_result.frame,
                        visible_count=len(filtered_entries),
                        obsel=capture_result.obsel,
                        entries=filtered_entries,
                        palettes=capture_result.palettes,
                        timestamp=capture_result.timestamp,
                    )

            return capture_result

        except Exception as e:
            logger.warning("Failed to get capture result for game frame %s: %s", frame_id, e)
            return None

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

    def remove_game_frame(self, frame_id: str) -> bool:
        """Remove a game frame from the project.

        Also removes any associated mapping and clears the preview cache.

        Args:
            frame_id: ID of the game frame to remove.

        Returns:
            True if the frame was found and removed.
        """
        if self._project is None:
            return False

        # Clear preview cache for this frame
        if frame_id in self._game_frame_previews:
            del self._game_frame_previews[frame_id]

        if self._project.remove_game_frame(frame_id):
            self.game_frame_removed.emit(frame_id)
            self.project_changed.emit()
            logger.info("Removed game frame %s", frame_id)
            return True
        return False

    def create_injection_copy(self, rom_path: Path) -> Path | None:
        """Create a numbered copy of the ROM for injection (public API).

        Use this to pre-create a copy for batch injection operations.

        Args:
            rom_path: Path to the source ROM

        Returns:
            Path to the created copy, or None if creation failed
        """
        return self._create_injection_copy(rom_path, None)

    def _create_injection_copy(
        self,
        rom_path: Path,
        output_path: Path | None = None,
    ) -> Path | None:
        """Create a numbered copy of the ROM for injection.

        Creates a copy with a numbered suffix to avoid overwriting the original
        or conflicting with existing files.

        Args:
            rom_path: Path to the source ROM
            output_path: Optional explicit output path (if provided, uses its directory)

        Returns:
            Path to the created copy, or None if creation failed
        """
        # Determine output directory
        if output_path:
            output_dir = output_path.parent
            base_name = output_path.stem
            extension = output_path.suffix
        else:
            output_dir = rom_path.parent
            base_name = rom_path.stem
            extension = rom_path.suffix

        # Remove existing suffixes to get clean base name
        base_name = base_name.removesuffix("_modified")
        # Remove existing _injected_N suffix if present
        base_name = re.sub(r"_injected_\d+$", "", base_name)

        # Find next available number
        counter = 1
        while True:
            new_name = f"{base_name}_injected_{counter}{extension}"
            new_path = output_dir / new_name
            if not new_path.exists():
                break
            counter += 1

        # Copy the ROM
        try:
            shutil.copy2(rom_path, new_path)
            logger.info("Created injection ROM copy: %s", new_path)
            return new_path
        except OSError as e:
            logger.exception("Failed to create ROM copy: %s", e)
            return None

    def inject_mapping(
        self,
        ai_frame_index: int,
        rom_path: Path,
        output_path: Path | None = None,
        create_backup: bool = True,
        debug: bool = False,
        force_raw: bool = False,
    ) -> bool:
        """Inject a mapped frame into the ROM using tile-aware masking.

        Workflow:
        1. Load AI frame and apply alignment (offset/flip).
        2. Load original capture data to identify tile layout.
        3. For each unique ROM offset in the capture:
           a. Identify which tiles belong to this offset.
           b. Create a sub-canvas for this offset.
           c. Crop the aligned AI image to these tiles.
           d. Mask the AI image using the original game sprite's alpha channel
              (preserving silhouette/topology).
           e. Inject this specific masked chunk into the ROM.

        Args:
            ai_frame_index: Index of the AI frame to inject
            rom_path: Path to the input ROM
            output_path: Path for the output ROM (default: same as input)
            create_backup: Whether to create a backup before injection
            debug: Enable debug mode (saves intermediate images to /tmp/inject_debug/)
            force_raw: Force RAW (uncompressed) injection for all tiles, skip HAL compression

        Returns:
            True if injection was successful
        """
        logger.info(
            "inject_mapping() called: ai_frame_index=%d, rom_path=%s",
            ai_frame_index,
            rom_path,
        )

        if self._project is None:
            logger.warning("inject_mapping: No project loaded")
            self.error_occurred.emit("No project loaded")
            return False

        # 1. Retrieve Mapping and Frames
        mapping = self._project.get_mapping_for_ai_frame_index(ai_frame_index)
        if mapping is None:
            logger.warning("inject_mapping: AI frame %d is not mapped", ai_frame_index)
            self.error_occurred.emit(f"AI frame {ai_frame_index} is not mapped")
            return False

        ai_frame = self._project.get_ai_frame_by_index(ai_frame_index)
        game_frame = self._project.get_game_frame_by_id(mapping.game_frame_id)

        if ai_frame is None or game_frame is None:
            logger.warning("inject_mapping: Invalid mapping - missing frame reference")
            self.error_occurred.emit("Invalid mapping: missing frame reference")
            return False

        logger.info(
            "inject_mapping: AI frame '%s' -> Game frame '%s' (offsets: %s)",
            ai_frame.path.name,
            game_frame.id,
            [f"0x{o:X}" for o in game_frame.rom_offsets],
        )

        # 2. Validate Data
        if not game_frame.rom_offsets:
            logger.warning("inject_mapping: Game frame %s has no ROM offsets", game_frame.id)
            self.error_occurred.emit(f"Game frame {game_frame.id} has no ROM offsets associated")
            return False

        if not ai_frame.path.exists():
            logger.warning("inject_mapping: AI frame file not found: %s", ai_frame.path)
            self.error_occurred.emit(f"AI frame file not found: {ai_frame.path}")
            return False

        if not rom_path.exists():
            logger.warning("inject_mapping: ROM file not found: %s", rom_path)
            self.error_occurred.emit(f"ROM file not found: {rom_path}")
            return False

        if not game_frame.capture_path or not game_frame.capture_path.exists():
            logger.warning("inject_mapping: Capture file missing: %s", game_frame.capture_path)
            self.error_occurred.emit(f"Capture file missing (required for masking): {game_frame.capture_path}")
            return False

        # Debug mode setup - enable via environment variable SPRITEPAL_INJECT_DEBUG=true
        # TODO: Remove these lines after debugging complete
        _debug_override = os.environ.get("SPRITEPAL_INJECT_DEBUG", "").lower() == "true"
        debug = debug or _debug_override
        force_raw = force_raw or _debug_override  # Force RAW injection to avoid HAL corruption
        debug_dir: Path | None = None
        debug_log_handler: logging.FileHandler | None = None
        original_log_level: int | None = None
        if debug:
            debug_dir = Path(tempfile.gettempdir()) / "inject_debug"
            debug_dir.mkdir(exist_ok=True)
            # Add file handler to capture all debug output
            debug_log_path = debug_dir / "inject_debug.log"
            debug_log_handler = logging.FileHandler(debug_log_path, mode="w")
            debug_log_handler.setLevel(logging.DEBUG)
            debug_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
            # Temporarily set logger level to DEBUG to ensure messages reach the handler
            original_log_level = logger.level
            logger.setLevel(logging.DEBUG)
            logger.addHandler(debug_log_handler)
            logger.info("=== INJECTION DEBUG MODE ===")
            logger.info("Debug output directory: %s", debug_dir)
            logger.info("Debug log file: %s", debug_log_path)
            logger.info("Force RAW mode: %s", force_raw)
            logger.info("AI frame: %s (index %d)", ai_frame.path.name, ai_frame_index)
            logger.info("Game frame: %s", game_frame.id)
            logger.info("ROM offsets: %s", [f"0x{o:X}" for o in game_frame.rom_offsets])

        # 3. Load and Prepare Images using SpriteCompositor
        try:
            # Load AI image
            ai_img = Image.open(ai_frame.path).convert("RGBA")

            # Re-parse capture to get tile layout
            parser = MesenCaptureParser()
            capture_result = parser.parse_file(game_frame.capture_path)

            # Filter capture to relevant entries
            if game_frame.selected_entry_ids:
                selected_ids = set(game_frame.selected_entry_ids)
                relevant_entries = [e for e in capture_result.entries if e.id in selected_ids]

                # Fallback if stored IDs are stale (mirrors preview at line 601)
                if not relevant_entries:
                    logger.warning(
                        "Stored entry IDs %s not found in capture %s. Using rom_offset fallback.",
                        game_frame.selected_entry_ids,
                        game_frame.capture_path,
                    )
                    self.stale_entries_warning.emit(game_frame.id)
                    # Fallback to rom_offset filtering
                    relevant_entries = [e for e in capture_result.entries if e.rom_offset in game_frame.rom_offsets]
            else:
                relevant_entries = [e for e in capture_result.entries if e.rom_offset in game_frame.rom_offsets]

            if not relevant_entries:
                # Last resort: use all entries (mirrors preview behavior)
                logger.warning(
                    "No entries match stored IDs or ROM offsets for frame %s. Using all entries.",
                    game_frame.id,
                )
                self.stale_entries_warning.emit(game_frame.id)
                relevant_entries = capture_result.entries

            # Create filtered capture for compositing
            filtered_capture = CaptureResult(
                frame=capture_result.frame,
                visible_count=len(relevant_entries),
                obsel=capture_result.obsel,
                entries=relevant_entries,
                palettes=capture_result.palettes,
                timestamp=capture_result.timestamp,
            )

            # Use SpriteCompositor for unified transform logic (flip -> scale order)
            # Policy: "transparent" for injection (uncovered areas become index 0)
            compositor = SpriteCompositor(uncovered_policy="transparent")
            transform = TransformParams(
                offset_x=mapping.offset_x,
                offset_y=mapping.offset_y,
                flip_h=mapping.flip_h,
                flip_v=mapping.flip_v,
                scale=mapping.scale,
            )

            # Composite without quantization (tile-level quantization happens later)
            composite_result = compositor.composite_frame(
                ai_image=ai_img,
                capture_result=filtered_capture,
                transform=transform,
                quantize=False,  # Quantize per-tile later
            )

            masked_canvas = composite_result.composited_image
            canvas_width = composite_result.canvas_width
            canvas_height = composite_result.canvas_height

            # Debug: Save intermediate images
            if debug and debug_dir:
                # Render original for debug
                renderer = CaptureRenderer(filtered_capture)
                original_sprite_img = renderer.render_selection()
                original_sprite_img.save(debug_dir / "original_sprite_mask.png")
                masked_canvas.save(debug_dir / "masked_canvas.png")
                logger.info("Saved debug images: original_sprite_mask.png, masked_canvas.png")
                logger.info(
                    "Canvas size: %dx%d, AI alignment: offset=(%d,%d) flip_h=%s flip_v=%s scale=%.2f",
                    canvas_width,
                    canvas_height,
                    mapping.offset_x,
                    mapping.offset_y,
                    mapping.flip_h,
                    mapping.flip_v,
                    mapping.scale,
                )

        except Exception as e:
            logger.exception("Failed to prepare masked image")
            self.error_occurred.emit(f"Image preparation failed: {e}")
            return False

        # 4. Perform Tile-Aware Injection
        injector = ROMInjector()
        success = False
        messages = []

        # Determine injection target:
        # - If output_path is provided and exists, use it directly (for batch injection)
        # - Otherwise, create a new numbered copy of the source ROM
        if output_path and output_path.exists():
            injection_rom_path = output_path
            logger.info("Using existing output ROM: %s", injection_rom_path)
        else:
            injection_rom_path = self._create_injection_copy(rom_path, output_path)
            if injection_rom_path is None:
                self.error_occurred.emit("Failed to create ROM copy for injection")
                return False
            logger.info("Created injection ROM copy: %s", injection_rom_path)

        current_rom_path = str(injection_rom_path)
        first_injection = True

        try:
            # Verify and correct ROM attribution using ROMVerificationService
            logger.info("Emitting status_update signal: 'Verifying ROM tile attribution...'")
            self.status_update.emit("Verifying ROM tile attribution...")

            verifier = ROMVerificationService(rom_path)
            verification = verifier.verify_offsets(
                filtered_capture,
                game_frame.selected_entry_ids,
            )

            # Report verification results
            if verification.has_corrections:
                self.status_update.emit(
                    f"ROM attribution: {verification.matched_hal + verification.matched_raw - verification.total + len([o for o, n in verification.corrections.items() if o != n and n is not None])} stale offsets corrected, {verification.not_found} not found"
                )

            if not verification.all_found and verification.not_found == verification.total:
                self.status_update.emit(f"ERROR: 0/{verification.total} tiles found in ROM")
                self.error_occurred.emit(
                    "Could not find any tiles in ROM. The sprite data may use an "
                    "unknown compression format or the ROM may be modified."
                )
                return False

            if verification.all_found and not verification.has_corrections and verification.total > 0:
                self.status_update.emit(f"ROM attribution verified: {verification.total} tiles matched")

            # Apply corrections to tiles
            if debug:
                for old_offset, new_offset in verification.corrections.items():
                    if new_offset is not None and new_offset != old_offset:
                        logger.info("Correcting tile rom_offset: 0x%X → 0x%X", old_offset, new_offset)

            verifier.apply_corrections(relevant_entries, verification.corrections)

            # Group by individual tile ROM offsets (not entry-level offsets)
            # Each tile within an entry may have a different ROM offset
            # Key: rom_offset -> dict of vram_addr -> (screen_x, screen_y, palette, tile_index_in_block, flip_h, flip_v)
            tile_groups: dict[int, dict[int, tuple[int, int, int, int | None, bool, bool]]] = {}

            bbox = filtered_capture.bounding_box

            if debug:
                logger.info(
                    "Bounding box: x=%d, y=%d, w=%d, h=%d",
                    bbox.x,
                    bbox.y,
                    bbox.width,
                    bbox.height,
                )
                logger.info("Processing %d relevant entries", len(relevant_entries))

            for entry in relevant_entries:
                for tile in entry.tiles:
                    if tile.rom_offset is None:
                        continue

                    # Calculate tile's local position within entry
                    # tile.pos_x/pos_y are tile indices within the entry (0, 1, 2...)
                    local_x = tile.pos_x * 8
                    local_y = tile.pos_y * 8

                    # Apply entry-level flips to get correct screen position
                    # This mirrors CaptureRenderer._render_tile() logic
                    if entry.flip_h:
                        local_x = entry.width - local_x - 8
                    if entry.flip_v:
                        local_y = entry.height - local_y - 8

                    # Convert to screen position
                    screen_x = entry.x + local_x
                    screen_y = entry.y + local_y

                    if debug:
                        logger.info(
                            "  Entry %d tile (%d,%d): local=(%d,%d) screen=(%d,%d) flip_h=%s rom=0x%X vram=0x%X",
                            entry.id,
                            tile.pos_x,
                            tile.pos_y,
                            local_x,
                            local_y,
                            screen_x,
                            screen_y,
                            entry.flip_h,
                            tile.rom_offset,
                            tile.vram_addr,
                        )

                    if tile.rom_offset not in tile_groups:
                        tile_groups[tile.rom_offset] = {}

                    # Use vram_addr as unique key - same vram_addr means same tile data
                    # This handles cases where the same tile is displayed multiple times
                    if tile.vram_addr not in tile_groups[tile.rom_offset]:
                        tile_groups[tile.rom_offset][tile.vram_addr] = (
                            screen_x,
                            screen_y,
                            entry.palette,
                            tile.tile_index_in_block,  # Position within compressed block
                            entry.flip_h,  # Track flip for counter-flipping during extraction
                            entry.flip_v,
                        )

            logger.debug(
                "Tile-level grouping: %d unique ROM offsets from %d entries",
                len(tile_groups),
                len(relevant_entries),
            )

            # Read ROM data once for querying original tile counts
            rom_data = rom_path.read_bytes()

            for rom_offset, vram_tiles in tile_groups.items():
                # Sort tiles by tile_index_in_block when available (proper ROM order),
                # otherwise fall back to vram_addr order
                def tile_sort_key(
                    vram_addr: int,
                    tiles: dict[int, tuple[int, int, int, int | None, bool, bool]] = vram_tiles,
                ) -> tuple[int, int]:
                    _, _, _, tile_idx, _, _ = tiles[vram_addr]
                    # Use tile_index_in_block if available, otherwise use vram_addr
                    # tile_idx goes first to sort by block position, vram_addr as tiebreaker
                    if tile_idx is not None:
                        return (tile_idx, vram_addr)
                    return (vram_addr, 0)

                sorted_vram_addrs = sorted(vram_tiles.keys(), key=tile_sort_key)
                captured_tile_count = len(sorted_vram_addrs)

                if captured_tile_count == 0:
                    continue

                # Get compression type from stored setting (user-controlled via UI toggle)
                # Default to "raw" for legacy projects without stored types
                stored_compression = game_frame.compression_types.get(rom_offset, "raw")
                is_raw_tile = force_raw or stored_compression == "raw"

                if is_raw_tile:
                    # RAW: inject all captured tiles
                    original_tile_count = captured_tile_count
                    logger.info(
                        "ROM offset 0x%X: Using RAW compression",
                        rom_offset,
                    )
                else:
                    # HAL: query tile count from compressed block to avoid over-injection
                    try:
                        _, original_data, _ = injector.find_compressed_sprite(rom_data, rom_offset)
                        original_tile_count = len(original_data) // 32
                        if original_tile_count == 0:
                            original_tile_count = captured_tile_count
                    except Exception:
                        original_tile_count = captured_tile_count
                    logger.info(
                        "ROM offset 0x%X: Using HAL compression (%d tiles in block)",
                        rom_offset,
                        original_tile_count,
                    )

                # Limit to original tile count - only inject as many tiles as the ROM slot holds
                if captured_tile_count > original_tile_count:
                    logger.info(
                        "ROM offset 0x%X: Capture has %d tiles but ROM only has %d, limiting injection",
                        rom_offset,
                        captured_tile_count,
                        original_tile_count,
                    )
                    sorted_vram_addrs = sorted_vram_addrs[:original_tile_count]

                tile_count = len(sorted_vram_addrs)

                # Determine grid layout for the tiles
                # Try to make a square-ish grid, preferring wider layouts
                grid_width = math.ceil(math.sqrt(tile_count))
                grid_height = math.ceil(tile_count / grid_width)

                logger.debug(
                    "ROM offset 0x%X: injecting %d tiles (of %d captured), grid %dx%d",
                    rom_offset,
                    tile_count,
                    captured_tile_count,
                    grid_width,
                    grid_height,
                )

                # Create output image for this ROM offset's tiles
                chunk_img = Image.new(
                    "RGBA",
                    (grid_width * 8, grid_height * 8),
                    (0, 0, 0, 0),
                )

                # Get palette from first tile's entry
                first_tile_info = vram_tiles[sorted_vram_addrs[0]]
                palette_index = first_tile_info[2]

                # Extract each 8x8 tile from the masked canvas and place in grid
                for idx, vram_addr in enumerate(sorted_vram_addrs):
                    screen_x, screen_y, _, _, flip_h, flip_v = vram_tiles[vram_addr]

                    # Convert screen coords to masked_canvas coords
                    canvas_x = screen_x - bbox.x
                    canvas_y = screen_y - bbox.y

                    # Extract 8x8 tile from masked canvas
                    tile_img = masked_canvas.crop((canvas_x, canvas_y, canvas_x + 8, canvas_y + 8))

                    # Check if tile has any content above transparency threshold
                    # If not, clear it (make fully transparent) to replace original sprite data
                    tile_alpha = tile_img.split()[3]
                    has_content = any(p >= INJECTION_TRANSPARENCY_THRESHOLD for p in tile_alpha.getdata())
                    if not has_content:
                        tile_img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))

                    # Debug: Save tile before counter-flip
                    if debug and debug_dir:
                        before_flip = tile_img.copy()
                        before_flip.save(debug_dir / f"tile_0x{rom_offset:X}_v{vram_addr:X}_before.png")

                    # Counter-flip: undo screen-appearance flip so ROM stores correct data.
                    # The masked_canvas contains pixels in "screen appearance" (flipped by CaptureRenderer).
                    # ROM stores tiles in their unflipped form - SNES hardware applies flip_h/flip_v at display time.
                    # If we inject screen-appearance data, SNES will apply flip again → double-flipped = wrong.
                    # Solution: counter-flip before injection so SNES flip produces correct result.
                    if flip_h:
                        tile_img = tile_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                    if flip_v:
                        tile_img = tile_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

                    # Debug: Save tile after counter-flip
                    if debug and debug_dir:
                        tile_img.save(debug_dir / f"tile_0x{rom_offset:X}_v{vram_addr:X}_after.png")

                    # Calculate position in output grid
                    grid_x = (idx % grid_width) * 8
                    grid_y = (idx // grid_width) * 8

                    # Debug: Log extraction details
                    if debug:
                        logger.info(
                            "  Extracted vram=0x%X: canvas=(%d,%d) flip_h=%s → grid=(%d,%d)",
                            vram_addr,
                            canvas_x,
                            canvas_y,
                            flip_h,
                            grid_x,
                            grid_y,
                        )

                    chunk_img.paste(tile_img, (grid_x, grid_y))

                # Debug: Save chunk before quantization
                if debug and debug_dir:
                    chunk_img.save(debug_dir / f"chunk_0x{rom_offset:X}_pre_quant.png")
                    logger.info(
                        "ROM offset 0x%X: saved chunk (%dx%d) with %d tiles",
                        rom_offset,
                        chunk_img.width,
                        chunk_img.height,
                        tile_count,
                    )

                # Quantize to game palette for proper color mapping
                # Use higher transparency threshold to treat semi-transparent pixels as transparent
                snes_palette = capture_result.palettes.get(palette_index, [])
                if snes_palette:
                    palette_rgb = snes_palette_to_rgb(snes_palette)
                    chunk_img = quantize_to_palette(
                        chunk_img, palette_rgb, transparency_threshold=INJECTION_TRANSPARENCY_THRESHOLD
                    )
                    logger.debug(
                        "Quantized chunk for offset 0x%X to palette %d (%d colors)",
                        rom_offset,
                        palette_index,
                        len(palette_rgb),
                    )
                else:
                    logger.warning(
                        "No palette data found for palette index %d, using grayscale fallback",
                        palette_index,
                    )

                # Debug: Save chunk after quantization
                if debug and debug_dir:
                    chunk_img.save(debug_dir / f"chunk_0x{rom_offset:X}_post_quant.png")

                # Save chunk to temp file
                with tempfile.NamedTemporaryFile(suffix=f"_{rom_offset:X}.png", delete=False) as tmp:
                    chunk_path = Path(tmp.name)
                    chunk_img.save(chunk_path, "PNG")

                # Inject this chunk
                # Use RAW directly if we already know it's uncompressed, otherwise try HAL first
                compression_used = "RAW" if is_raw_tile else "HAL"
                if is_raw_tile:
                    # Direct RAW injection for uncompressed tiles
                    logger.info(
                        "ROM offset 0x%X: Injecting as RAW (uncompressed) tile",
                        rom_offset,
                    )
                    result, message = injector.inject_sprite_to_rom(
                        sprite_path=str(chunk_path),
                        rom_path=str(rom_path) if first_injection else current_rom_path,
                        output_path=current_rom_path,
                        sprite_offset=rom_offset,
                        fast_compression=False,
                        create_backup=create_backup and first_injection,
                        ignore_checksum=True,
                        force=False,
                        compression_type=CompressionType.RAW,
                    )
                else:
                    # Try HAL compression first
                    result, message = injector.inject_sprite_to_rom(
                        sprite_path=str(chunk_path),
                        rom_path=str(rom_path) if first_injection else current_rom_path,
                        output_path=current_rom_path,
                        sprite_offset=rom_offset,
                        fast_compression=True,
                        create_backup=create_backup and first_injection,
                        ignore_checksum=True,
                        force=False,
                        compression_type=CompressionType.HAL,
                    )

                    # If HAL failed (decompression error OR data too large), try RAW
                    if not result and ("decompress" in message.lower() or "too large" in message.lower()):
                        compression_used = "RAW"
                        logger.info(
                            "ROM offset 0x%X: HAL failed (%s), retrying as RAW",
                            rom_offset,
                            "size" if "too large" in message.lower() else "decompress",
                        )
                        result, message = injector.inject_sprite_to_rom(
                            sprite_path=str(chunk_path),
                            rom_path=str(rom_path) if first_injection else current_rom_path,
                            output_path=current_rom_path,
                            sprite_offset=rom_offset,
                            fast_compression=False,
                            create_backup=create_backup and first_injection,
                            ignore_checksum=True,
                            force=False,
                            compression_type=CompressionType.RAW,
                        )

                # Cleanup temp file
                chunk_path.unlink()

                if result:
                    # Debug: Verify bytes written to ROM
                    if debug:
                        try:
                            written_rom = Path(current_rom_path).read_bytes()
                            # For RAW, offset is direct; for HAL, need to account for header
                            smc_header = 512 if len(written_rom) % 0x8000 == 512 else 0
                            check_offset = rom_offset + smc_header
                            written_bytes = written_rom[check_offset : check_offset + 32]
                            logger.info(
                                "ROM 0x%X [%s]: wrote %d tiles, first 32 bytes: %s",
                                rom_offset,
                                compression_used,
                                tile_count,
                                written_bytes.hex(),
                            )
                        except Exception as e:
                            logger.warning("Could not verify ROM bytes: %s", e)

                    messages.append(f"Offset 0x{rom_offset:X}: Success ({tile_count} tiles, {compression_used})")
                    first_injection = False
                    success = True
                else:
                    messages.append(f"Offset 0x{rom_offset:X}: Failed ({message})")
                    success = False
                    break  # Stop on first failure

            # Update mapping status
            if success:
                mapping.status = "injected"
                # Emit signal for workspace to handle save with correct project path
                self.save_requested.emit()

                # Debug: Final summary
                if debug and debug_dir:
                    logger.info("=== INJECTION DEBUG COMPLETE ===")
                    logger.info("Debug output saved to: %s", debug_dir)
                    logger.info("Injection results:\n%s", "\n".join(messages))

                self.mapping_injected.emit(ai_frame_index, "\n".join(messages))
                self.project_changed.emit()
            else:
                if debug:
                    logger.info("=== INJECTION DEBUG FAILED ===")
                    logger.info("Failure messages:\n%s", "\n".join(messages))
                self.error_occurred.emit(f"Injection failed:\n{'\n'.join(messages)}")

        except Exception as e:
            logger.exception("Injection process failed")
            self.error_occurred.emit(f"Injection process failed: {e}")
            success = False
        finally:
            # Clean up debug log handler
            if debug_log_handler is not None:
                debug_log_handler.flush()
                debug_log_handler.close()
                logger.removeHandler(debug_log_handler)
            # Restore original log level
            if original_log_level is not None:
                logger.setLevel(original_log_level)

        return success
