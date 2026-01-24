"""Controller for Frame Mapping workspace.

Handles business logic for loading frames, managing mappings, and coordinating
between the view panels.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

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
from core.palette_utils import snes_palette_to_rgb
from core.services.injection_debug_context import InjectionDebugContext
from core.services.injection_orchestrator import InjectionOrchestrator
from core.services.injection_results import InjectionRequest
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
    # Capture import signal - emitted when capture parsed, workspace shows dialog
    capture_import_requested = Signal(object, object)  # (CaptureResult, capture_path: Path)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._project: FrameMappingProject | None = None
        # Cache stores (pixmap, mtime, selected_entry_ids) for invalidation on change
        self._game_frame_previews: dict[str, tuple[QPixmap, float, tuple[int, ...]]] = {}
        # Injection orchestrator for frame injection pipeline
        self._injection_orchestrator = InjectionOrchestrator()

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

    def create_mapping(self, ai_frame_id: str, game_frame_id: str) -> bool:
        """Create a mapping between an AI frame and a game frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            game_frame_id: ID of the game frame

        Returns:
            True if mapping was created
        """
        if self._project is None:
            self.error_occurred.emit("No project loaded")
            return False

        # Verify both frames exist
        ai_frame = self._project.get_ai_frame_by_id(ai_frame_id)
        if ai_frame is None:
            self.error_occurred.emit(f"AI frame {ai_frame_id} not found")
            return False

        game_frame = self._project.get_game_frame_by_id(game_frame_id)
        if game_frame is None:
            self.error_occurred.emit(f"Game frame {game_frame_id} not found")
            return False

        # Use ID-based mapping (stable across reloads)
        self._project.create_mapping(ai_frame_id, game_frame_id)
        self.mapping_created.emit(ai_frame_id, game_frame_id)
        self.project_changed.emit()
        self.save_requested.emit()
        logger.info("Created mapping: AI frame %s -> Game frame %s", ai_frame_id, game_frame_id)
        return True

    def get_existing_link_for_game_frame(self, game_frame_id: str) -> str | None:
        """Get the AI frame ID currently linked to a game frame.

        Args:
            game_frame_id: ID of the game frame to check

        Returns:
            AI frame ID if game frame is linked, None otherwise
        """
        if self._project is None:
            return None
        return self._project.get_ai_frame_linked_to_game_frame(game_frame_id)

    def get_existing_link_for_ai_frame(self, ai_frame_id: str) -> str | None:
        """Get the game frame ID currently linked to an AI frame.

        Args:
            ai_frame_id: ID of the AI frame to check

        Returns:
            Game frame ID if AI frame is linked, None otherwise
        """
        if self._project is None:
            return None
        mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
        return mapping.game_frame_id if mapping else None

    def remove_mapping(self, ai_frame_id: str) -> bool:
        """Remove a mapping for an AI frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)

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
        ai_frame_id: str,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float = 1.0,
        set_edited: bool = True,
    ) -> bool:
        """Update alignment for a mapping.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            offset_x: X offset for alignment
            offset_y: Y offset for alignment
            flip_h: Horizontal flip state
            flip_v: Vertical flip state
            scale: Scale factor (0.1 - 1.0)
            set_edited: If True and status is not 'injected', set status to 'edited'.
                        Use False for auto-centering during initial link creation.

        Returns:
            True if alignment was updated
        """
        if self._project is None:
            return False

        if self._project.update_mapping_alignment(ai_frame_id, offset_x, offset_y, flip_h, flip_v, scale, set_edited):
            # Use targeted signal to avoid full UI refresh (which blanks canvas)
            self.alignment_updated.emit(ai_frame_id)
            logger.info(
                "Updated alignment for AI frame %s: offset=(%d, %d), flip=(%s, %s), scale=%.2f",
                ai_frame_id,
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
                    # File missing: return cached preview
                    # This allows previews to persist if the source file is temporarily
                    # unavailable or deleted, providing a "last known good" view.
                    return cached_pixmap
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
                with Image.open(ai_frame.path) as img:
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
        from core.services.rom_staging_manager import ROMStagingManager

        staging_manager = ROMStagingManager()
        return staging_manager.create_injection_copy(rom_path, None)

    def inject_mapping(
        self,
        ai_frame_id: str,
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

        Delegates to InjectionOrchestrator for the actual injection pipeline.

        Args:
            ai_frame_id: ID of the AI frame to inject (filename)
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
            "inject_mapping() called: ai_frame_id=%s, rom_path=%s",
            ai_frame_id,
            rom_path,
        )

        if self._project is None:
            logger.warning("inject_mapping: No project loaded")
            self.error_occurred.emit("No project loaded")
            return False

        # Build injection request
        request = InjectionRequest(
            ai_frame_id=ai_frame_id,
            rom_path=rom_path,
            output_path=output_path,
            create_backup=create_backup,
            force_raw=force_raw,
            allow_fallback=allow_fallback,
            preserve_sprite=preserve_sprite,
            emit_project_changed=emit_project_changed,
        )

        # Progress callback wraps Qt signal
        def emit_progress(msg: str) -> None:
            self.status_update.emit(msg)

        # Execute via orchestrator with debug context
        with InjectionDebugContext.from_env() as debug_ctx:
            # Override with explicit debug flag if passed
            if debug and not debug_ctx.enabled:
                debug_ctx = InjectionDebugContext(enabled=True)
                debug_ctx.__enter__()
                try:
                    result = self._injection_orchestrator.execute(
                        request=request,
                        project=self._project,
                        debug_context=debug_ctx,
                        on_progress=emit_progress,
                    )
                finally:
                    debug_ctx.__exit__(None, None, None)
            else:
                result = self._injection_orchestrator.execute(
                    request=request,
                    project=self._project,
                    debug_context=debug_ctx,
                    on_progress=emit_progress,
                )

        # Handle stale entries warning
        if result.needs_fallback_confirmation and result.stale_frame_id:
            self.stale_entries_warning.emit(result.stale_frame_id)

        # Handle result
        if result.success:
            # Update mapping status
            mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
            if mapping is not None and result.new_mapping_status:
                mapping.status = result.new_mapping_status

            self.mapping_injected.emit(ai_frame_id, "\n".join(result.messages))

            # Emit project changed and save requested
            if emit_project_changed:
                self.project_changed.emit()
            self.save_requested.emit()

            return True
        else:
            # Emit error
            if result.error:
                self.error_occurred.emit(result.error)
            return False

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
