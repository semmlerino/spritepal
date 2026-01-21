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
from core.types import CompressionType

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
    mapping_injected = Signal(int, str)  # ai_index, message
    error_occurred = Signal(str)  # error message
    status_update = Signal(str)  # status message for UI feedback

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

            # Get unique ROM offsets from selected entries only
            rom_offsets = filtered_capture.unique_rom_offsets

            # Render preview using filtered capture (cropped to bounding box)
            renderer = CaptureRenderer(filtered_capture)
            preview_img = renderer.render_selection()

            # Convert PIL Image to QPixmap
            from io import BytesIO

            buffer = BytesIO()
            preview_img.save(buffer, format="PNG")
            buffer.seek(0)
            qimg = QImage()
            qimg.loadFromData(buffer.read())
            pixmap = QPixmap.fromImage(qimg)
            self._game_frame_previews[frame_id] = pixmap

            # Create game frame with selected entry IDs for filtering on retrieval
            bbox = filtered_capture.bounding_box
            frame = GameFrame(
                id=frame_id,
                rom_offsets=rom_offsets,
                capture_path=capture_path,
                palette_index=0,  # Could extract from capture
                width=bbox.width,
                height=bbox.height,
                selected_entry_ids=[entry.id for entry in selected_entries],
            )

            self._project.game_frames.append(frame)  # type: ignore[union-attr]
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

        self._project.create_mapping(ai_frame_index, game_frame_id)
        self.mapping_created.emit(ai_frame_index, game_frame_id)
        self.project_changed.emit()
        logger.info("Created mapping: AI frame %d -> Game frame %s", ai_frame_index, game_frame_id)
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
        return self._project.get_ai_frame_linked_to_game_frame(game_frame_id)

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

    def update_mapping_alignment(
        self,
        ai_frame_index: int,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float = 1.0,
    ) -> bool:
        """Update alignment for a mapping.

        Args:
            ai_frame_index: Index of the AI frame
            offset_x: X offset for alignment
            offset_y: Y offset for alignment
            flip_h: Horizontal flip state
            flip_v: Vertical flip state
            scale: Scale factor (0.1 - 10.0)

        Returns:
            True if alignment was updated
        """
        if self._project is None:
            return False

        if self._project.update_mapping_alignment(ai_frame_index, offset_x, offset_y, flip_h, flip_v, scale):
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
        regenerate the preview from the capture file.

        Args:
            frame_id: Game frame ID

        Returns:
            QPixmap preview or None if not available
        """
        # Return cached preview if available
        if frame_id in self._game_frame_previews:
            return self._game_frame_previews[frame_id]

        # Try to regenerate from capture file
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
            # Re-parse and render the capture
            parser = MesenCaptureParser()
            capture_result = parser.parse_file(capture_path)

            if not capture_result.has_entries:
                return None

            renderer = CaptureRenderer(capture_result)
            preview_img = renderer.render_selection()

            # Convert PIL Image to QPixmap
            from io import BytesIO

            buffer = BytesIO()
            preview_img.save(buffer, format="PNG")
            buffer.seek(0)
            qimg = QImage()
            qimg.loadFromData(buffer.read())
            pixmap = QPixmap.fromImage(qimg)

            # Cache for future use
            self._game_frame_previews[frame_id] = pixmap
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
                # Create filtered CaptureResult with only selected entries
                capture_result = CaptureResult(
                    frame=capture_result.frame,
                    visible_count=len(filtered_entries),
                    obsel=capture_result.obsel,
                    entries=filtered_entries,
                    palettes=capture_result.palettes,
                    timestamp=capture_result.timestamp,
                )

                if not capture_result.has_entries:
                    logger.warning(
                        "No entries matched stored selection for game frame %s (IDs: %s)",
                        frame_id,
                        game_frame.selected_entry_ids,
                    )
                    return None

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
        if self._project is None:
            self.error_occurred.emit("No project loaded")
            return False

        # 1. Retrieve Mapping and Frames
        mapping = self._project.get_mapping_for_ai_frame(ai_frame_index)
        if mapping is None:
            self.error_occurred.emit(f"AI frame {ai_frame_index} is not mapped")
            return False

        ai_frame = self._project.get_ai_frame_by_index(ai_frame_index)
        game_frame = self._project.get_game_frame_by_id(mapping.game_frame_id)

        if ai_frame is None or game_frame is None:
            self.error_occurred.emit("Invalid mapping: missing frame reference")
            return False

        # 2. Validate Data
        if not game_frame.rom_offsets:
            self.error_occurred.emit(f"Game frame {game_frame.id} has no ROM offsets associated")
            return False

        if not ai_frame.path.exists():
            self.error_occurred.emit(f"AI frame file not found: {ai_frame.path}")
            return False

        if not rom_path.exists():
            self.error_occurred.emit(f"ROM file not found: {rom_path}")
            return False

        if not game_frame.capture_path or not game_frame.capture_path.exists():
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

        # 3. Load and Prepare Images
        try:
            # Load AI image
            ai_img = Image.open(ai_frame.path).convert("RGBA")

            # Apply flips (flip first, then position)
            if mapping.flip_h:
                ai_img = ai_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if mapping.flip_v:
                ai_img = ai_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

            # Apply scale if not 1.0 (matching preview behavior in workbench_canvas)
            if abs(mapping.scale - 1.0) > 0.01:
                new_w = max(1, int(ai_img.width * mapping.scale))
                new_h = max(1, int(ai_img.height * mapping.scale))
                ai_img = ai_img.resize((new_w, new_h), Image.Resampling.NEAREST)

            # Re-parse capture to get tile layout and render original mask
            parser = MesenCaptureParser()
            capture_result = parser.parse_file(game_frame.capture_path)

            # Render the FULL original frame to use as a mask
            # We need to filter the capture to ONLY the entries relevant to this GameFrame
            # (The GameFrame might have been imported from a subset of a larger capture)
            # Filter by selected_entry_ids if available (user's explicit selection during import),
            # otherwise fall back to rom_offsets for legacy projects.

            if game_frame.selected_entry_ids:
                # Use explicit entry selection (preferred - more precise)
                selected_ids = set(game_frame.selected_entry_ids)
                relevant_entries = [e for e in capture_result.entries if e.id in selected_ids]
            else:
                # Legacy fallback: filter by ROM offset (may include unintended entries)
                relevant_entries = [e for e in capture_result.entries if e.rom_offset in game_frame.rom_offsets]

            if not relevant_entries:
                self.error_occurred.emit("No entries in capture match the GameFrame's ROM offsets.")
                return False

            # Create a filtered capture result for rendering the mask
            from core.mesen_integration.click_extractor import CaptureResult

            filtered_capture = CaptureResult(
                frame=capture_result.frame,
                visible_count=len(relevant_entries),
                obsel=capture_result.obsel,
                entries=relevant_entries,
                palettes=capture_result.palettes,
                timestamp=capture_result.timestamp,
            )

            renderer = CaptureRenderer(filtered_capture)
            # This renders the composite original sprite
            original_sprite_img = renderer.render_selection()

            # Create compositing canvas matching the GameFrame bounds
            canvas_width = original_sprite_img.width
            canvas_height = original_sprite_img.height

            canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

            # Paste aligned AI image onto canvas
            canvas.paste(ai_img, (mapping.offset_x, mapping.offset_y), ai_img)

            # Apply Mask: Use original sprite's alpha channel to clip to silhouette.
            # This ensures we only inject pixels where the original sprite had pixels.
            # Key behavior for partial coverage:
            # - Where original is opaque AND AI frame covers → AI frame pixels
            # - Where original is opaque AND AI frame doesn't cover → transparent (index 0)
            # - Where original is transparent → transparent (unchanged)
            # This is the correct behavior: uncovered areas become transparent, not filled
            # with original pixels.
            mask = original_sprite_img.split()[3]  # Get alpha channel
            masked_canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
            masked_canvas.paste(canvas, (0, 0), mask)

            # Debug: Save intermediate images
            if debug and debug_dir:
                original_sprite_img.save(debug_dir / "original_sprite_mask.png")
                canvas.save(debug_dir / "aligned_ai_frame.png")
                masked_canvas.save(debug_dir / "masked_canvas.png")
                logger.info("Saved debug images: original_sprite_mask.png, aligned_ai_frame.png, masked_canvas.png")
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

            # At this point, `masked_canvas` contains the aligned AI pixels,
            # but strictly clipped to the shape of the original sprite.
            # Areas where AI frame didn't cover remain transparent (RGBA 0,0,0,0),
            # which will be quantized to palette index 0 (transparency) during injection.

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
            # Verify and correct ROM attribution for stale offsets
            # The Mesen Lua script attributes ROM offsets to VRAM tiles during capture,
            # but if VRAM is overwritten later, the offsets become stale.
            # This searches the ROM to find the correct offset for each tile.
            self.status_update.emit("Verifying ROM tile attribution...")
            corrections = self._find_correct_rom_offsets(
                filtered_capture,
                rom_path,
                game_frame.selected_entry_ids,
            )

            # Count corrections for logging and UI feedback
            stale_count = sum(1 for old, new in corrections.items() if old != new and new is not None)
            unfound_count = sum(1 for new in corrections.values() if new is None)
            total_offsets = len(corrections)

            if stale_count > 0:
                self.status_update.emit(
                    f"ROM attribution: {stale_count} stale offsets corrected, {unfound_count} not found"
                )
                logger.info(
                    "ROM attribution: %d offsets corrected, %d not found in ROM",
                    stale_count,
                    unfound_count,
                )

            if unfound_count > 0 and unfound_count == len(corrections):
                self.status_update.emit(f"ERROR: 0/{total_offsets} tiles found in ROM")
                self.error_occurred.emit(
                    "Could not find any tiles in ROM. The sprite data may use an "
                    "unknown compression format or the ROM may be modified."
                )
                return False

            if stale_count == 0 and unfound_count == 0 and total_offsets > 0:
                self.status_update.emit(f"ROM attribution verified: {total_offsets} tiles matched")

            # Apply corrections to tiles before processing
            for entry in relevant_entries:
                for tile in entry.tiles:
                    if tile.rom_offset is not None and tile.rom_offset in corrections:
                        corrected = corrections[tile.rom_offset]
                        if corrected is not None and corrected != tile.rom_offset:
                            if debug:
                                logger.info(
                                    "Correcting tile rom_offset: 0x%X → 0x%X",
                                    tile.rom_offset,
                                    corrected,
                                )
                            tile.rom_offset = corrected

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

                # Query original ROM data to find how many tiles are actually stored here
                # This prevents injecting more tiles than the original compressed block contains
                # For RAW (uncompressed) tiles, HAL decompression will fail - that's expected
                is_raw_tile = force_raw  # Force RAW if requested
                if force_raw:
                    original_tile_count = captured_tile_count
                    logger.info(
                        "ROM offset 0x%X: Using forced RAW mode",
                        rom_offset,
                    )
                else:
                    try:
                        _, original_data, _ = injector.find_compressed_sprite(rom_data, rom_offset)
                        original_tile_count = len(original_data) // 32  # 32 bytes per 4bpp tile
                        if original_tile_count == 0:
                            # HAL decompression succeeded but no tiles - treat as RAW
                            is_raw_tile = True
                            original_tile_count = captured_tile_count
                            logger.info(
                                "ROM offset 0x%X: HAL returned no tiles, treating as RAW (1 tile)",
                                rom_offset,
                            )
                    except Exception as e:
                        # HAL decompression failed - this is expected for RAW tiles
                        is_raw_tile = True
                        original_tile_count = captured_tile_count  # For RAW, inject all captured tiles
                        logger.info(
                            "ROM offset 0x%X: HAL decompression failed (%s), treating as RAW tile",
                            rom_offset,
                            e,
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
                snes_palette = capture_result.palettes.get(palette_index, [])
                if snes_palette:
                    palette_rgb = snes_palette_to_rgb(snes_palette)
                    chunk_img = quantize_to_palette(chunk_img, palette_rgb)
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
                if self._project.ai_frames_dir:
                    try:
                        self._project.save(self._project.ai_frames_dir / "project.spritepal-mapping.json")
                    except Exception:
                        logger.warning("Failed to auto-save project after injection")

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

    def _find_correct_rom_offsets(
        self,
        capture_result: CaptureResult,
        rom_path: Path,
        selected_entry_ids: list[int] | None = None,
    ) -> dict[int, int | None]:
        """Find correct ROM offsets for tiles with stale attribution.

        Uses ROMTileMatcher to search the ROM for each tile's VRAM data.
        This handles the case where VRAM was overwritten after the Lua script
        recorded the ROM offset, making the attribution stale.

        Args:
            capture_result: Parsed capture with tile data
            rom_path: Path to ROM file
            selected_entry_ids: If provided, only process these entries

        Returns:
            Dict mapping original rom_offset → corrected rom_offset (or None if not found)
        """
        from core.mesen_integration.rom_tile_matcher import ROMTileMatcher

        corrections: dict[int, int | None] = {}

        # Initialize matcher with known sprite offsets
        matcher = ROMTileMatcher(str(rom_path))
        matcher.build_database()  # Indexes known HAL blocks

        # Read ROM data for raw tile search fallback
        rom_data = rom_path.read_bytes()

        # Track statistics
        total_tiles = 0
        matched_tiles = 0
        raw_matched = 0

        # Process each tile
        for entry in capture_result.entries:
            if selected_entry_ids and entry.id not in selected_entry_ids:
                continue
            for tile in entry.tiles:
                if tile.rom_offset is None:
                    continue

                # Skip if we've already processed this offset
                if tile.rom_offset in corrections:
                    continue

                total_tiles += 1

                # Search for this tile in ROM using ROMTileMatcher
                matches = matcher.lookup_vram_tile(tile.data_bytes)

                if matches:
                    # Use best match (first result, sorted by ROM offset)
                    best_match = matches[0]
                    corrections[tile.rom_offset] = best_match.rom_offset
                    matched_tiles += 1
                    if best_match.rom_offset != tile.rom_offset:
                        logger.debug(
                            "Tile at 0x%X corrected to 0x%X (matched via HAL index)",
                            tile.rom_offset,
                            best_match.rom_offset,
                        )
                else:
                    # Try raw tile search as fallback
                    raw_offset = self._search_raw_tile(rom_data, tile.data_bytes)
                    corrections[tile.rom_offset] = raw_offset
                    if raw_offset is not None:
                        raw_matched += 1
                        if raw_offset != tile.rom_offset:
                            logger.debug(
                                "Tile at 0x%X corrected to 0x%X (matched via raw search)",
                                tile.rom_offset,
                                raw_offset,
                            )
                    else:
                        logger.debug(
                            "Tile at 0x%X not found in ROM (VRAM data: %s...)",
                            tile.rom_offset,
                            tile.data_hex[:16],
                        )

        logger.info(
            "ROM offset correction: %d tiles processed, %d HAL matches, %d raw matches, %d not found",
            total_tiles,
            matched_tiles,
            raw_matched,
            total_tiles - matched_tiles - raw_matched,
        )

        return corrections

    def _search_raw_tile(self, rom_data: bytes, tile_data: bytes) -> int | None:
        """Search ROM for exact 32-byte tile match.

        This is a fallback for tiles that aren't in HAL-compressed blocks.
        Raw (uncompressed) tiles can be found by direct byte matching.

        Args:
            rom_data: Full ROM file contents
            tile_data: 32 bytes of SNES 4bpp tile data

        Returns:
            ROM offset where tile was found, or None if not found
        """
        if len(tile_data) != 32:
            return None

        offset = rom_data.find(tile_data)
        return offset if offset >= 0 else None
