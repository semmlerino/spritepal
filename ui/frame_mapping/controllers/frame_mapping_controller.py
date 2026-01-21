"""Controller for Frame Mapping workspace.

Handles business logic for loading frames, managing mappings, and coordinating
between the view panels.
"""

from __future__ import annotations

import logging
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
from core.mesen_integration.click_extractor import MesenCaptureParser, OAMEntry
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

            # Create game frame
            bbox = filtered_capture.bounding_box
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

    def inject_mapping(
        self,
        ai_frame_index: int,
        rom_path: Path,
        output_path: Path | None = None,
        create_backup: bool = True,
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

        # 3. Load and Prepare Images
        try:
            # Load AI image
            ai_img = Image.open(ai_frame.path).convert("RGBA")

            # Apply flips (flip first, then position)
            if mapping.flip_h:
                ai_img = ai_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if mapping.flip_v:
                ai_img = ai_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

            # Re-parse capture to get tile layout and render original mask
            parser = MesenCaptureParser()
            capture_result = parser.parse_file(game_frame.capture_path)

            # Render the FULL original frame to use as a mask
            # We need to filter the capture to ONLY the entries relevant to this GameFrame
            # (The GameFrame might have been imported from a subset of a larger capture)
            # However, GameFrame logic in import_mesen_capture filters the capture *result*
            # effectively by creating a new one? No, it creates a filtered CaptureResult in memory
            # but doesn't save it to disk. It reads the original full file here.
            # We must filter again based on the ROM offsets associated with the GameFrame.

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

        # We need to track the current ROM path as we update it
        current_rom_path = str(output_path) if output_path else str(rom_path)
        first_injection = True

        try:
            # Group entries by ROM offset
            offset_groups: dict[int, list[OAMEntry]] = {}
            for entry in relevant_entries:
                if entry.rom_offset is not None:
                    if entry.rom_offset not in offset_groups:
                        offset_groups[entry.rom_offset] = []
                    offset_groups[entry.rom_offset].append(entry)

            # Get bounding box of the whole selection to map local coords
            bbox = filtered_capture.bounding_box

            for rom_offset, entries in offset_groups.items():
                # Determine the bounding box of JUST this group of tiles
                # This helps us crop the relevant part of the masked_canvas
                min_x = min(e.x for e in entries)
                min_y = min(e.y for e in entries)
                max_x = max(e.x + e.width for e in entries)
                max_y = max(e.y + e.height for e in entries)

                # Calculate crop coordinates relative to the full `masked_canvas`
                # masked_canvas (0,0) corresponds to bbox.x, bbox.y
                crop_x = min_x - bbox.x
                crop_y = min_y - bbox.y
                crop_w = max_x - min_x
                crop_h = max_y - min_y

                # Crop the relevant part for this ROM offset
                chunk_img = masked_canvas.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))

                # Save chunk to temp file
                with tempfile.NamedTemporaryFile(suffix=f"_{rom_offset:X}.png", delete=False) as tmp:
                    chunk_path = Path(tmp.name)
                    chunk_img.save(chunk_path, "PNG")

                # Inject this chunk
                result, message = injector.inject_sprite_to_rom(
                    sprite_path=str(chunk_path),
                    rom_path=str(rom_path) if first_injection else current_rom_path,
                    output_path=current_rom_path,
                    sprite_offset=rom_offset,
                    fast_compression=True,
                    create_backup=create_backup and first_injection,  # Only backup once
                    ignore_checksum=True,
                    force=False,
                    compression_type=CompressionType.HAL,
                )

                # Cleanup temp file
                chunk_path.unlink()

                if result:
                    messages.append(f"Offset 0x{rom_offset:X}: Success")
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

                self.mapping_injected.emit(ai_frame_index, "\n".join(messages))
                self.project_changed.emit()
            else:
                self.error_occurred.emit(f"Injection failed:\n{'\n'.join(messages)}")

        except Exception as e:
            logger.exception("Injection process failed")
            self.error_occurred.emit(f"Injection process failed: {e}")
            success = False

        return success
