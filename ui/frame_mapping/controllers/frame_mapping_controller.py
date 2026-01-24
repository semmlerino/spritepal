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
from typing import TYPE_CHECKING, Literal

from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap

from ui.common.qt_image_utils import pil_to_qpixmap

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

from core.frame_mapping_project import (
    FRAME_TAGS,
    AIFrame,
    FrameMappingProject,
    GameFrame,
    SheetPalette,
)
from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import (
    CaptureResult,
    MesenCaptureParser,
)
from core.palette_utils import (
    QUANTIZATION_TRANSPARENCY_THRESHOLD,
    quantize_to_palette,
    quantize_with_mappings,
    snes_palette_to_rgb,
)
from core.rom_injector import ROMInjector
from core.services.rom_verification_service import ROMVerificationService
from core.services.sprite_compositor import SpriteCompositor, TransformParams
from core.types import CompressionType
from utils.logging_config import get_logger

logger = get_logger(__name__)


class FrameMappingController(QObject):
    """Controller for frame mapping operations.

    Manages the data model and coordinates view updates.

    Signals:
        project_changed: Emitted when project is loaded/created/modified (structural changes)
        ai_frames_loaded: Emitted when AI frames are loaded (count)
        game_frame_added: Emitted when a game frame is added (frame_id)
        mapping_created: Emitted when a mapping is created (ai_index, game_id)
        mapping_removed: Emitted when a mapping is removed (ai_index)
        alignment_updated: Emitted when mapping alignment changes (ai_frame_index)
        error_occurred: Emitted on errors (error_message)
    """

    project_changed = Signal()
    ai_frames_loaded = Signal(int)  # count
    game_frame_added = Signal(str)  # game frame ID
    game_frame_removed = Signal(str)  # game frame ID
    mapping_created = Signal(str, str)  # ai_frame_id, game_frame_id
    mapping_removed = Signal(str)  # ai_frame_id
    mapping_injected = Signal(str, str)  # ai_frame_id, message
    error_occurred = Signal(str)  # error message
    status_update = Signal(str)  # status message for UI feedback
    save_requested = Signal()  # Emitted when auto-save should occur (e.g., after injection)
    stale_entries_warning = Signal(str)  # frame_id - Emitted when stored entry IDs are stale
    alignment_updated = Signal(str)  # ai_frame_id - Emitted when alignment changes (not structural)
    sheet_palette_changed = Signal()  # Emitted when sheet palette is set/cleared
    # AI Frame Organization signals (V4)
    frame_renamed = Signal(str)  # ai_frame_id - display name changed
    frame_tags_changed = Signal(str)  # ai_frame_id - tags changed
    # Capture Organization signals
    capture_renamed = Signal(str)  # game_frame_id - display name changed
    # Preview cache signal - emitted when a preview is regenerated (mtime/entries changed)
    preview_cache_invalidated = Signal(str)  # game_frame_id - preview was regenerated

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._project: FrameMappingProject | None = None
        # Cache stores (pixmap, mtime, selected_entry_ids) for invalidation on change
        self._game_frame_previews: dict[str, tuple[QPixmap, float, tuple[int, ...]]] = {}

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

            # Convert PIL Image to QPixmap and cache with mtime + entry IDs for invalidation
            pixmap = pil_to_qpixmap(preview_img)
            mtime = capture_path.stat().st_mtime if capture_path.exists() else 0.0
            entry_ids = tuple(entry.id for entry in selected_entries)
            self._game_frame_previews[frame_id] = (pixmap, mtime, entry_ids)

            # Infer palette from selected entries (use first entry's palette if all same)
            palette_idx = 0
            if selected_entries:
                first_palette = selected_entries[0].palette
                if all(e.palette == first_palette for e in selected_entries):
                    palette_idx = first_palette

            # Create game frame with selected entry IDs for filtering on retrieval
            bbox = filtered_capture.bounding_box
            # Default all ROM offsets to RAW compression (user can change in workbench)
            default_compression_types = dict.fromkeys(rom_offsets, "raw")
            frame = GameFrame(
                id=frame_id,
                rom_offsets=rom_offsets,
                capture_path=capture_path,
                palette_index=palette_idx,  # Inferred from selected entries
                width=bbox.width,
                height=bbox.height,
                selected_entry_ids=[entry.id for entry in selected_entries],
                compression_types=default_compression_types,
            )

            self._project.add_game_frame(frame)  # type: ignore[union-attr]
            self.game_frame_added.emit(frame_id)
            self.project_changed.emit()
            self.save_requested.emit()
            logger.info(
                "Imported game frame %s from %s (%d of %d entries selected, palette=%d)",
                frame_id,
                capture_path,
                len(selected_entries),
                len(capture_result.entries),
                palette_idx,
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
        self.mapping_created.emit(ai_frame.id, game_frame_id)
        self.project_changed.emit()
        self.save_requested.emit()
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

        # Get the AI frame ID before removing (for signal emission)
        ai_frame = self._project.get_ai_frame_by_index(ai_frame_index)
        if ai_frame is None:
            return False

        if self._project.remove_mapping_for_ai_frame_index(ai_frame_index):
            self.mapping_removed.emit(ai_frame.id)
            self.project_changed.emit()
            self.save_requested.emit()
            logger.info("Removed mapping for AI frame %s (idx %d)", ai_frame.id, ai_frame_index)
            return True
        return False

    def remove_mapping_by_id(self, ai_frame_id: str) -> bool:
        """Remove a mapping for an AI frame using ID.

        Args:
            ai_frame_id: AI frame ID (filename)

        Returns:
            True if a mapping was removed
        """
        if self._project is None:
            return False

        if self._project.remove_mapping_for_ai_frame(ai_frame_id):
            self.mapping_removed.emit(ai_frame_id)
            self.project_changed.emit()
            self.save_requested.emit()
            logger.info("Removed mapping for AI frame %s", ai_frame_id)
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

        # Get AI frame for ID-based signal emission
        ai_frame = self._project.get_ai_frame_by_index(ai_frame_index)
        if ai_frame is None:
            return False

        if self._project.update_mapping_alignment_by_index(
            ai_frame_index, offset_x, offset_y, flip_h, flip_v, scale, set_edited
        ):
            # Use targeted signal to avoid full UI refresh (which blanks canvas)
            self.alignment_updated.emit(ai_frame.id)
            logger.info(
                "Updated alignment for AI frame %s (idx %d): offset=(%d, %d), flip=(%s, %s), scale=%.2f",
                ai_frame.id,
                ai_frame_index,
                offset_x,
                offset_y,
                flip_h,
                flip_v,
                scale,
            )
            return True
        return False

    def apply_transforms_to_all_mappings(
        self,
        offset_x: int,
        offset_y: int,
        scale: float,
        exclude_ai_frame_id: str | None = None,
    ) -> int:
        """Apply position and scale to all mapped frames.

        Args:
            offset_x: X offset to apply
            offset_y: Y offset to apply
            scale: Scale factor to apply (0.1 - 1.0)
            exclude_ai_frame_id: AI frame ID to exclude (typically the current frame)

        Returns:
            Number of mappings updated
        """
        if self._project is None:
            return 0

        updated_count = 0
        for mapping in self._project.mappings:
            # Skip excluded frame
            if mapping.ai_frame_id == exclude_ai_frame_id:
                continue

            # Update position and scale, preserve flip values
            mapping.offset_x = offset_x
            mapping.offset_y = offset_y
            mapping.scale = max(0.1, min(1.0, scale))
            mapping.status = "edited"
            updated_count += 1

        if updated_count > 0:
            self.project_changed.emit()
            self.save_requested.emit()

        return updated_count

    def get_game_frame_preview(self, frame_id: str) -> QPixmap | None:
        """Get the rendered preview pixmap for a game frame.

        If the preview is not cached but the capture file exists, attempts to
        regenerate the preview from the capture file. Respects selected_entry_ids
        filtering to show only the selected entries in the preview.

        Cache key includes (mtime, selected_entry_ids) to invalidate when either changes.
        Emits preview_cache_invalidated when a cached preview is regenerated due to
        mtime or entry ID changes.

        Args:
            frame_id: Game frame ID

        Returns:
            QPixmap preview or None if not available
        """
        cache_was_invalidated = False

        # Check cache first
        if frame_id in self._game_frame_previews:
            cached_pixmap, cached_mtime, cached_entries = self._game_frame_previews[frame_id]

            # Get game frame to validate cache
            game_frame = self._project.get_game_frame_by_id(frame_id) if self._project else None
            if game_frame:
                current_entries = tuple(game_frame.selected_entry_ids)

                # If file exists, check both mtime and entries
                if game_frame.capture_path and game_frame.capture_path.exists():
                    current_mtime = game_frame.capture_path.stat().st_mtime
                    if current_mtime != cached_mtime or current_entries != cached_entries:
                        cache_was_invalidated = True
                    else:
                        return cached_pixmap
                else:
                    # File missing: invalidate cache and fall through to regeneration
                    # (which will return None since file doesn't exist)
                    del self._game_frame_previews[frame_id]
                    cache_was_invalidated = True
            else:
                # No project/game_frame - invalidate stale cache entry
                del self._game_frame_previews[frame_id]
                return None

        # Try to regenerate from capture file (with filtering applied)
        capture_result, _ = self.get_capture_result_for_game_frame(frame_id)
        if capture_result is None or not capture_result.has_entries:
            return None

        try:
            renderer = CaptureRenderer(capture_result)
            preview_img = renderer.render_selection()

            # Convert PIL Image to QPixmap and cache with mtime + entry IDs
            pixmap = pil_to_qpixmap(preview_img)
            current_mtime = 0.0
            current_entries: tuple[int, ...] = ()
            if self._project is not None:
                game_frame = self._project.get_game_frame_by_id(frame_id)
                if game_frame:
                    current_entries = tuple(game_frame.selected_entry_ids)
                    if game_frame.capture_path and game_frame.capture_path.exists():
                        current_mtime = game_frame.capture_path.stat().st_mtime

            self._game_frame_previews[frame_id] = (pixmap, current_mtime, current_entries)

            # Notify if this was a cache invalidation (not first-time generation)
            if cache_was_invalidated:
                self.preview_cache_invalidated.emit(frame_id)

            return pixmap

        except Exception as e:
            logger.warning("Failed to regenerate preview for game frame %s: %s", frame_id, e)
            return None

    def get_capture_result_for_game_frame(self, frame_id: str) -> tuple[CaptureResult | None, bool]:
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
            Tuple of (CaptureResult or None, used_fallback flag).
            used_fallback is True if the stored entry IDs were stale and
            rom_offset filtering was used instead.
        """
        if self._project is None:
            return (None, False)

        game_frame = self._project.get_game_frame_by_id(frame_id)
        if game_frame is None or game_frame.capture_path is None:
            return (None, False)

        capture_path = game_frame.capture_path
        if not capture_path.exists():
            logger.warning("Capture file not found for game frame %s: %s", frame_id, capture_path)
            return (None, False)

        try:
            parser = MesenCaptureParser()
            capture_result = parser.parse_file(capture_path)
            used_fallback = False

            if not capture_result.has_entries:
                return (None, False)

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
                    used_fallback = True
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

            return (capture_result, used_fallback)

        except Exception as e:
            logger.warning("Failed to get capture result for game frame %s: %s", frame_id, e)
            return (None, False)

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

    # --- Sheet Palette Methods ---

    def get_sheet_palette(self) -> SheetPalette | None:
        """Get the current sheet palette.

        Returns:
            SheetPalette if defined, None otherwise
        """
        if self._project is None:
            return None
        return self._project.sheet_palette

    def set_sheet_palette(self, palette: SheetPalette | None) -> None:
        """Set the sheet palette for the project.

        Args:
            palette: SheetPalette to set, or None to clear
        """
        if self._project is None:
            logger.warning("set_sheet_palette: No project loaded")
            return

        self._project.sheet_palette = palette
        self.sheet_palette_changed.emit()
        self.project_changed.emit()
        if palette is not None:
            logger.info("Set sheet palette with %d color mappings", len(palette.color_mappings))
        else:
            logger.info("Cleared sheet palette")

    def set_sheet_palette_color(self, index: int, rgb: tuple[int, int, int]) -> None:
        """Update a single color in the sheet palette.

        Args:
            index: Palette index (0-15)
            rgb: New RGB color tuple
        """
        if self._project is None:
            logger.warning("set_sheet_palette_color: No project loaded")
            return

        if self._project.sheet_palette is None:
            logger.warning("set_sheet_palette_color: No sheet palette defined")
            return

        if not 0 <= index < 16:
            logger.warning("set_sheet_palette_color: Invalid index %d", index)
            return

        # Update the palette color
        palette = self._project.sheet_palette
        colors = list(palette.colors)
        if index < len(colors):
            colors[index] = rgb
        else:
            # Extend if needed
            while len(colors) <= index:
                colors.append((0, 0, 0))
            colors[index] = rgb

        # Update color_mappings: keep existing mappings unchanged
        updated_mappings = dict(palette.color_mappings)

        # Create new palette with updated colors
        from core.frame_mapping_project import SheetPalette

        self._project.sheet_palette = SheetPalette(
            colors=colors,
            color_mappings=updated_mappings,
        )

        self.sheet_palette_changed.emit()
        self.project_changed.emit()
        logger.info("Updated sheet palette color [%d] to RGB%s", index, rgb)

    def extract_sheet_colors(self) -> dict[tuple[int, int, int], int]:
        """Extract unique colors from all AI frames in the project.

        Returns:
            Dict mapping RGB tuples to pixel counts
        """
        from core.palette_utils import extract_unique_colors

        if self._project is None:
            return {}

        all_colors: dict[tuple[int, int, int], int] = {}

        for ai_frame in self._project.ai_frames:
            if not ai_frame.path.exists():
                continue

            try:
                img = Image.open(ai_frame.path)
                frame_colors = extract_unique_colors(img, ignore_transparent=True)
                # Merge with totals
                for color, count in frame_colors.items():
                    all_colors[color] = all_colors.get(color, 0) + count
            except Exception as e:
                logger.warning("Failed to extract colors from %s: %s", ai_frame.path, e)

        logger.info("Extracted %d unique colors from %d AI frames", len(all_colors), len(self._project.ai_frames))
        return all_colors

    def generate_sheet_palette_from_colors(
        self,
        colors: dict[tuple[int, int, int], int] | None = None,
    ) -> SheetPalette:
        """Generate a 16-color palette from AI sheet colors.

        Args:
            colors: Color counts to use, or None to extract from AI frames

        Returns:
            Generated SheetPalette with auto-mapped colors
        """
        from core.palette_utils import (
            find_nearest_palette_index,
            quantize_colors_to_palette,
        )

        if colors is None:
            colors = self.extract_sheet_colors()

        # Generate 16-color palette
        palette_colors = quantize_colors_to_palette(colors, max_colors=16, snap_to_snes=True)

        # Auto-map all colors to nearest palette colors
        color_mappings: dict[tuple[int, int, int], int] = {}
        for color in colors:
            color_mappings[color] = find_nearest_palette_index(color, palette_colors)

        return SheetPalette(colors=palette_colors, color_mappings=color_mappings)

    def copy_game_palette_to_sheet(self, game_frame_id: str) -> SheetPalette | None:
        """Create a SheetPalette from a game frame's palette.

        Args:
            game_frame_id: ID of game frame to copy palette from

        Returns:
            SheetPalette with the game frame's colors, or None if not found
        """
        from core.palette_utils import find_nearest_palette_index

        if self._project is None:
            return None

        game_frame = self._project.get_game_frame_by_id(game_frame_id)
        if game_frame is None or game_frame.capture_path is None:
            return None

        # Parse capture to get palette
        try:
            parser = MesenCaptureParser()
            capture_result = parser.parse_file(game_frame.capture_path)
            palette_index = game_frame.palette_index
            snes_palette = capture_result.palettes.get(palette_index, [])

            if not snes_palette:
                logger.warning("No palette found for game frame %s", game_frame_id)
                return None

            # Convert to RGB
            palette_rgb = snes_palette_to_rgb(snes_palette)

            # Ensure 16 colors
            while len(palette_rgb) < 16:
                palette_rgb.append((0, 0, 0))
            palette_rgb = palette_rgb[:16]

            # Auto-map sheet colors to this palette
            sheet_colors = self.extract_sheet_colors()
            color_mappings: dict[tuple[int, int, int], int] = {}
            for color in sheet_colors:
                color_mappings[color] = find_nearest_palette_index(color, palette_rgb)

            logger.info("Copied palette from game frame %s", game_frame_id)
            return SheetPalette(colors=palette_rgb, color_mappings=color_mappings)

        except Exception as e:
            logger.exception("Failed to copy game palette from %s: %s", game_frame_id, e)
            return None

    def get_game_palettes(self) -> dict[str, list[tuple[int, int, int]]]:
        """Get palettes from all game frames.

        Returns:
            Dict mapping game frame IDs to their RGB palettes
        """
        if self._project is None:
            return {}

        result: dict[str, list[tuple[int, int, int]]] = {}

        for game_frame in self._project.game_frames:
            if game_frame.capture_path is None or not game_frame.capture_path.exists():
                continue

            try:
                parser = MesenCaptureParser()
                capture_result = parser.parse_file(game_frame.capture_path)
                palette_index = game_frame.palette_index
                snes_palette = capture_result.palettes.get(palette_index, [])

                if snes_palette:
                    result[game_frame.id] = snes_palette_to_rgb(snes_palette)
            except Exception as e:
                logger.debug("Could not load palette for %s: %s", game_frame.id, e)

        return result

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

    def remove_ai_frame(self, frame_id: str) -> bool:
        """Remove an AI frame from the project.

        Also removes any associated mapping.

        Args:
            frame_id: ID of the AI frame to remove.

        Returns:
            True if the frame was found and removed.
        """
        if self._project is None:
            return False

        if self._project.remove_ai_frame(frame_id):
            self.project_changed.emit()
            logger.info("Removed AI frame %s", frame_id)
            return True
        return False

    def update_game_frame_compression(self, frame_id: str, compression_type: str) -> bool:
        """Update compression type for a game frame.

        Updates the compression type for all ROM offsets in the game frame.
        By design, compression is a single setting per game frame, not per offset.
        This routes compression changes through the controller instead of
        directly mutating game frame state.

        Args:
            frame_id: ID of the game frame
            compression_type: New compression type ('raw' or 'hal')

        Returns:
            True if the update was successful
        """
        if self._project is None:
            self.error_occurred.emit("No project loaded")
            return False

        game_frame = self._project.get_game_frame_by_id(frame_id)
        if game_frame is None:
            self.error_occurred.emit(f"Game frame {frame_id} not found")
            return False

        # Update compression type for all ROM offsets
        for rom_offset in game_frame.rom_offsets:
            game_frame.compression_types[rom_offset] = compression_type

        self.project_changed.emit()
        self.save_requested.emit()
        logger.info(
            "Updated compression type for game frame %s to %s (%d offsets)",
            frame_id,
            compression_type,
            len(game_frame.rom_offsets),
        )
        return True

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

    def _create_staging_copy(self, source_path: Path) -> Path | None:
        """Create a staging copy of the ROM for atomic injection.

        Creates a temporary copy that will be written to during injection.
        On success, it can be atomically renamed to the target. On failure,
        it is deleted and the original ROM remains unchanged.

        Args:
            source_path: Path to the source ROM to copy

        Returns:
            Path to the staging file, or None if creation failed
        """
        try:
            # Create staging file in same directory for atomic rename
            staging_path = source_path.with_suffix(source_path.suffix + ".staging")
            shutil.copy2(source_path, staging_path)
            logger.info("Created staging ROM copy: %s", staging_path)
            return staging_path
        except OSError as e:
            logger.exception("Failed to create staging ROM copy: %s", e)
            return None

    def _commit_staging(self, staging_path: Path, target_path: Path) -> bool:
        """Commit staging file by atomically replacing target.

        Args:
            staging_path: Path to the staging file
            target_path: Path to the target file to replace

        Returns:
            True if commit succeeded, False otherwise
        """
        try:
            # Atomic rename (on same filesystem)
            staging_path.replace(target_path)
            logger.info("Committed staging file to: %s", target_path)
            return True
        except OSError as e:
            logger.exception("Failed to commit staging file: %s", e)
            return False

    def _rollback_staging(self, staging_path: Path | None) -> None:
        """Delete staging file on injection failure.

        Args:
            staging_path: Path to the staging file, or None if not created
        """
        if staging_path is not None and staging_path.exists():
            try:
                staging_path.unlink()
                logger.info("Rolled back staging file: %s", staging_path)
            except OSError as e:
                logger.warning("Failed to delete staging file %s: %s", staging_path, e)

    def _detect_raw_slot_size(
        self,
        rom_data: bytes,
        file_offset: int,
        max_tiles: int = 256,
    ) -> int | None:
        """Detect the size of a RAW (uncompressed) sprite slot in ROM.

        Scans from the offset, counting 32-byte tiles (8x8 4bpp) until hitting
        a padding boundary (block of all 0x00 or 0xFF bytes).

        This prevents overwriting adjacent ROM data when the captured sprite
        has more tiles than the original slot can hold.

        Args:
            rom_data: Full ROM data bytes
            file_offset: Starting file offset (accounting for SMC header)
            max_tiles: Maximum tiles to scan before giving up

        Returns:
            Number of tiles in the slot, or None if no boundary detected
        """
        # Account for SMC header (512 bytes if present)
        smc_header = 512 if len(rom_data) % 0x8000 == 512 else 0
        actual_offset = file_offset + smc_header

        # Validate offset is within ROM
        if actual_offset < 0 or actual_offset >= len(rom_data):
            logger.warning(
                "_detect_raw_slot_size: offset 0x%X out of bounds (ROM size: 0x%X)",
                file_offset,
                len(rom_data),
            )
            return None

        tile_size = 32  # 8x8 4bpp tile = 32 bytes

        for tile_index in range(max_tiles):
            tile_start = actual_offset + (tile_index * tile_size)
            tile_end = tile_start + tile_size

            # Stop if we would read past end of ROM
            if tile_end > len(rom_data):
                break

            tile_data = rom_data[tile_start:tile_end]

            # Check for padding boundary (all 0x00 or all 0xFF)
            if all(b == 0x00 for b in tile_data) or all(b == 0xFF for b in tile_data):
                # Found boundary - return count of tiles before it
                return tile_index if tile_index > 0 else None

        # No boundary found within max_tiles
        return None

    def inject_mapping(
        self,
        ai_frame_index: int,
        rom_path: Path,
        output_path: Path | None = None,
        create_backup: bool = True,
        debug: bool = False,
        force_raw: bool = False,
        allow_fallback: bool = False,
        emit_project_changed: bool = True,
        preserve_sprite: bool = False,
    ) -> bool:
        """Inject a mapped frame into the ROM using tile-aware masking.

        Workflow:
        1. Load AI frame and apply alignment (offset/flip).
        2. Load original capture data to identify tile layout.
        3. For each unique ROM offset in the capture:
           a. Identify which tiles belong to this offset.
           b. Create a sub-canvas for this offset.
           c. Crop the aligned AI image to these tiles.
           d. Composite AI over original (or replace completely).
           e. Inject this specific chunk into the ROM.

        Args:
            ai_frame_index: Index of the AI frame to inject
            rom_path: Path to the input ROM
            output_path: Path for the output ROM (default: same as input)
            create_backup: Whether to create a backup before injection
            debug: Enable debug mode (saves intermediate images to /tmp/inject_debug/)
            force_raw: Force RAW (uncompressed) injection for all tiles, skip HAL compression
            allow_fallback: If True, allow fallback to rom_offset filtering or all entries
                           when stored entry IDs are stale. If False (default), abort injection
                           and emit stale_entries_warning for user to decide.
            emit_project_changed: If True (default), emit project_changed after success.
                                 Set False for batch operations to emit once at the end.
            preserve_sprite: If True, original sprite remains visible where AI doesn't
                            cover it. If False (default), original sprite is completely
                            removed - only AI content remains.

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

                # Fallback if stored IDs are stale
                if not relevant_entries:
                    logger.warning(
                        "Stored entry IDs %s not found in capture %s.",
                        game_frame.selected_entry_ids,
                        game_frame.capture_path,
                    )
                    self.stale_entries_warning.emit(game_frame.id)

                    if not allow_fallback:
                        # Abort injection - let caller handle (show dialog, retry with allow_fallback=True)
                        self.error_occurred.emit(
                            f"Entry selection for '{game_frame.id}' is outdated. "
                            "Reimport the capture or enable fallback mode."
                        )
                        return False

                    # Fallback to rom_offset filtering (user allowed it)
                    logger.info("Using rom_offset fallback (allow_fallback=True)")
                    relevant_entries = [e for e in capture_result.entries if e.rom_offset in game_frame.rom_offsets]
            else:
                relevant_entries = [e for e in capture_result.entries if e.rom_offset in game_frame.rom_offsets]

            if not relevant_entries:
                # Last resort: use all entries
                logger.warning(
                    "No entries match stored IDs or ROM offsets for frame %s.",
                    game_frame.id,
                )
                self.stale_entries_warning.emit(game_frame.id)

                if not allow_fallback:
                    # Abort injection - let caller handle
                    self.error_occurred.emit(
                        f"No valid entries found for '{game_frame.id}'. "
                        "The capture file may have changed. Reimport the capture."
                    )
                    return False

                # Use all entries (user allowed fallback)
                logger.info("Using all entries fallback (allow_fallback=True)")
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
            # Policy based on preserve_sprite:
            # - False (default): "transparent" - original sprite removed, only AI content
            # - True: "original" - original sprite visible where AI doesn't cover
            uncovered_policy: Literal["transparent", "original"] = "original" if preserve_sprite else "transparent"
            compositor = SpriteCompositor(uncovered_policy=uncovered_policy)
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
        # Track whether we're reusing an existing ROM (vs freshly created) for preserve_existing logic
        using_existing_output = output_path is not None and output_path.exists()
        injection_rom_path: Path
        if using_existing_output and output_path is not None:
            injection_rom_path = output_path
            logger.info("Using existing output ROM: %s", injection_rom_path)
        else:
            created_path = self._create_injection_copy(rom_path, output_path)
            if created_path is None:
                self.error_occurred.emit("Failed to create ROM copy for injection")
                return False
            injection_rom_path = created_path
            logger.info("Created injection ROM copy: %s", injection_rom_path)

        # Create staging copy for atomic injection
        # All writes go to staging; on success we commit (atomic rename), on failure we rollback (delete)
        staging_path = self._create_staging_copy(injection_rom_path)
        if staging_path is None:
            self.error_occurred.emit("Failed to create staging file for injection")
            # Clean up injection copy if we created it
            if not using_existing_output:
                injection_rom_path.unlink(missing_ok=True)
            return False
        staging_committed = False

        current_rom_path = str(staging_path)
        # Tracks whether this is the first tile group within THIS frame injection.
        # Reset per inject_mapping() call - not per batch. Used for:
        # - Deciding whether to create backup (only on first tile group)
        # - Choosing source ROM when not using existing output
        first_tile_group_in_frame = True

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
                    # RAW: detect slot boundary to prevent overwriting adjacent data
                    detected_slot_size = self._detect_raw_slot_size(rom_data, rom_offset)
                    if detected_slot_size is not None:
                        original_tile_count = detected_slot_size
                        logger.info(
                            "ROM offset 0x%X: Using RAW compression (detected slot: %d tiles)",
                            rom_offset,
                            detected_slot_size,
                        )
                    else:
                        # No boundary detected - fall back to captured count
                        original_tile_count = captured_tile_count
                        logger.info(
                            "ROM offset 0x%X: Using RAW compression (no boundary, using captured: %d tiles)",
                            rom_offset,
                            captured_tile_count,
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
                    has_content = any(p >= QUANTIZATION_TRANSPARENCY_THRESHOLD for p in tile_alpha.getdata())
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

                # Quantize to palette for proper color mapping
                # Use higher transparency threshold to treat semi-transparent pixels as transparent
                # Priority: sheet_palette > capture palette
                if self._project and self._project.sheet_palette:
                    # Use sheet palette (user-defined for consistent AI frame rendering)
                    sheet_palette = self._project.sheet_palette
                    palette_rgb = list(sheet_palette.colors)
                    if sheet_palette.color_mappings:
                        # Use explicit color mappings
                        chunk_img = quantize_with_mappings(
                            chunk_img,
                            palette_rgb,
                            sheet_palette.color_mappings,
                            transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
                        )
                    else:
                        # Sheet palette without explicit mappings -> nearest color
                        chunk_img = quantize_to_palette(
                            chunk_img, palette_rgb, transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD
                        )
                else:
                    # Fallback: use capture palette (original behavior)
                    snes_palette = capture_result.palettes.get(palette_index, [])
                    if snes_palette:
                        palette_rgb = snes_palette_to_rgb(snes_palette)
                        chunk_img = quantize_to_palette(
                            chunk_img, palette_rgb, transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD
                        )
                    else:
                        logger.warning(
                            "No palette data found for palette index %d, using grayscale fallback",
                            palette_index,
                        )

                # Debug: Save chunk after quantization
                if debug and debug_dir:
                    chunk_img.save(debug_dir / f"chunk_0x{rom_offset:X}_post_quant.png")

                # Save chunk to temp file and inject with guaranteed cleanup
                chunk_path: Path | None = None
                try:
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
                        # preserve_existing=True when:
                        # - using_existing_output: batch injection with pre-created output ROM
                        # - not first_tile_group_in_frame: subsequent tile groups within this frame
                        # When preserve_existing=True, ROMInjector reads from output_path (staging),
                        # so rom_path is only used for validation and initial copy.
                        result, message = injector.inject_sprite_to_rom(
                            sprite_path=str(chunk_path),
                            rom_path=str(rom_path),
                            output_path=current_rom_path,
                            sprite_offset=rom_offset,
                            fast_compression=False,
                            create_backup=create_backup and first_tile_group_in_frame,
                            ignore_checksum=True,
                            force=False,
                            compression_type=CompressionType.RAW,
                            preserve_existing=using_existing_output or not first_tile_group_in_frame,
                        )
                    else:
                        # Try HAL compression first
                        # preserve_existing logic same as RAW injection above
                        result, message = injector.inject_sprite_to_rom(
                            sprite_path=str(chunk_path),
                            rom_path=str(rom_path),
                            output_path=current_rom_path,
                            sprite_offset=rom_offset,
                            fast_compression=True,
                            create_backup=create_backup and first_tile_group_in_frame,
                            ignore_checksum=True,
                            force=False,
                            compression_type=CompressionType.HAL,
                            preserve_existing=using_existing_output or not first_tile_group_in_frame,
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
                                rom_path=str(rom_path),
                                output_path=current_rom_path,
                                sprite_offset=rom_offset,
                                fast_compression=False,
                                create_backup=create_backup and first_tile_group_in_frame,
                                ignore_checksum=True,
                                force=False,
                                compression_type=CompressionType.RAW,
                                preserve_existing=using_existing_output or not first_tile_group_in_frame,
                            )
                finally:
                    # Guaranteed cleanup of temp file
                    if chunk_path is not None:
                        chunk_path.unlink(missing_ok=True)

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
                    first_tile_group_in_frame = False
                    success = True
                else:
                    messages.append(f"Offset 0x{rom_offset:X}: Failed ({message})")
                    success = False
                    break  # Stop on first failure

            # Update mapping status
            if success:
                # Commit staging file (atomic rename to target)
                if not self._commit_staging(staging_path, injection_rom_path):
                    self.error_occurred.emit("Failed to commit staged injection to ROM")
                    self._rollback_staging(staging_path)
                    return False
                staging_committed = True

                mapping.status = "injected"
                # Emit signal for workspace to handle save with correct project path
                self.save_requested.emit()

                # Debug: Final summary
                if debug and debug_dir:
                    logger.info("=== INJECTION DEBUG COMPLETE ===")
                    logger.info("Debug output saved to: %s", debug_dir)
                    logger.info("Injection results:\n%s", "\n".join(messages))

                self.mapping_injected.emit(ai_frame.id, "\n".join(messages))
                if emit_project_changed:
                    self.project_changed.emit()
            else:
                # Rollback staging on failure - original ROM unchanged
                self._rollback_staging(staging_path)
                if debug:
                    logger.info("=== INJECTION DEBUG FAILED ===")
                    logger.info("Failure messages:\n%s", "\n".join(messages))
                self.error_occurred.emit(f"Injection failed:\n{'\n'.join(messages)}")

        except Exception as e:
            logger.exception("Injection process failed")
            self.error_occurred.emit(f"Injection process failed: {e}")
            # Rollback staging on exception
            self._rollback_staging(staging_path)
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
            # Safety net: ensure staging is cleaned up if not committed
            if not staging_committed:
                self._rollback_staging(staging_path)

        return success

    # ─── AI Frame Organization (V4) ───────────────────────────────────────────

    def rename_frame(self, frame_id: str, display_name: str | None) -> bool:
        """Set display name for an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)
            display_name: New display name, or None to clear

        Returns:
            True if frame was found and renamed
        """
        if self._project is None:
            return False
        result = self._project.set_frame_display_name(frame_id, display_name)
        if result:
            logger.info("Renamed frame '%s' to '%s'", frame_id, display_name or "(cleared)")
            self.frame_renamed.emit(frame_id)
        return result

    def add_frame_tag(self, frame_id: str, tag: str) -> bool:
        """Add a tag to an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)
            tag: Tag to add (must be in FRAME_TAGS)

        Returns:
            True if frame was found and tag added
        """
        if self._project is None:
            return False
        result = self._project.add_frame_tag(frame_id, tag)
        if result:
            self.frame_tags_changed.emit(frame_id)
        return result

    def remove_frame_tag(self, frame_id: str, tag: str) -> bool:
        """Remove a tag from an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)
            tag: Tag to remove

        Returns:
            True if frame was found and tag removed
        """
        if self._project is None:
            return False
        result = self._project.remove_frame_tag(frame_id, tag)
        if result:
            self.frame_tags_changed.emit(frame_id)
        return result

    def toggle_frame_tag(self, frame_id: str, tag: str) -> bool:
        """Toggle a tag on an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)
            tag: Tag to toggle (must be in FRAME_TAGS)

        Returns:
            True if frame was found and tag toggled
        """
        if self._project is None:
            return False
        result = self._project.toggle_frame_tag(frame_id, tag)
        if result:
            self.frame_tags_changed.emit(frame_id)
        return result

    def set_frame_tags(self, frame_id: str, tags: frozenset[str]) -> bool:
        """Set all tags for an AI frame (replace existing).

        Args:
            frame_id: ID of the AI frame (filename)
            tags: New set of tags

        Returns:
            True if frame was found and tags updated
        """
        if self._project is None:
            return False
        result = self._project.set_frame_tags(frame_id, tags)
        if result:
            self.frame_tags_changed.emit(frame_id)
        return result

    def get_frame_tags(self, frame_id: str) -> frozenset[str]:
        """Get tags for an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)

        Returns:
            Set of tags (empty if frame not found)
        """
        if self._project is None:
            return frozenset()
        frame = self._project.get_ai_frame_by_id(frame_id)
        if frame is None:
            return frozenset()
        return frame.tags

    def get_frame_display_name(self, frame_id: str) -> str | None:
        """Get display name for an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)

        Returns:
            Display name if set, None otherwise
        """
        if self._project is None:
            return None
        frame = self._project.get_ai_frame_by_id(frame_id)
        if frame is None:
            return None
        return frame.display_name

    def get_frames_with_tag(self, tag: str) -> list[AIFrame]:
        """Get all AI frames with a specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of AIFrame objects with the tag
        """
        if self._project is None:
            return []
        return self._project.get_frames_with_tag(tag)

    @staticmethod
    def get_available_tags() -> frozenset[str]:
        """Get the set of valid frame tags.

        Returns:
            Set of valid tag names
        """
        return FRAME_TAGS

    # ─── Capture (GameFrame) Organization ──────────────────────────────────────

    def rename_capture(self, game_frame_id: str, new_name: str | None) -> bool:
        """Set display name for a game frame (capture).

        Args:
            game_frame_id: ID of the game frame to rename
            new_name: New display name (empty or None to clear)

        Returns:
            True if renamed successfully, False otherwise
        """
        if self._project is None:
            return False
        # Normalize empty string to None
        display_name = new_name.strip() if new_name else None
        if display_name == "":
            display_name = None
        if self._project.set_capture_display_name(game_frame_id, display_name):
            self.capture_renamed.emit(game_frame_id)
            self.save_requested.emit()
            return True
        return False

    def get_capture_display_name(self, game_frame_id: str) -> str | None:
        """Get display name for a game frame (capture).

        Args:
            game_frame_id: ID of the game frame

        Returns:
            Display name if set, None otherwise
        """
        if self._project is None:
            return None
        frame = self._project.get_game_frame_by_id(game_frame_id)
        if frame is None:
            return None
        return frame.display_name
