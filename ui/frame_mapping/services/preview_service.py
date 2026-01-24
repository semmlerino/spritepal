"""Preview cache service for Frame Mapping.

Manages preview pixmap generation and caching with mtime-based invalidation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import CaptureResult, MesenCaptureParser
from ui.common.qt_image_utils import pil_to_qpixmap
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

logger = get_logger(__name__)


class PreviewService(QObject):
    """Service for managing game frame preview cache.

    Handles preview pixmap generation, caching, and invalidation based on
    file modification times and selected entry IDs.

    Signals:
        preview_cache_invalidated: Emitted when a cached preview is regenerated (str: game_frame_id)
        stale_entries_warning: Emitted when stored entry IDs are stale (str: game_frame_id)
    """

    preview_cache_invalidated = Signal(str)  # game_frame_id
    stale_entries_warning = Signal(str)  # game_frame_id

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize preview service.

        Args:
            parent: Optional Qt parent object
        """
        super().__init__(parent)
        # Cache stores (pixmap, mtime, selected_entry_ids) for invalidation on change
        self._game_frame_previews: dict[str, tuple[QPixmap, float, tuple[int, ...]]] = {}

    def get_preview(self, frame_id: str, project: FrameMappingProject | None) -> QPixmap | None:
        """Get the rendered preview pixmap for a game frame.

        If the preview is not cached but the capture file exists, attempts to
        regenerate the preview from the capture file. Respects selected_entry_ids
        filtering to show only the selected entries in the preview.

        Cache key includes (mtime, selected_entry_ids) to invalidate when either changes.
        Emits preview_cache_invalidated when a cached preview is regenerated due to
        mtime or entry ID changes.

        Args:
            frame_id: Game frame ID
            project: Current project (needed for game frame lookup)

        Returns:
            QPixmap preview or None if not available
        """
        cache_was_invalidated = False

        # Check cache first
        if frame_id in self._game_frame_previews:
            cached_pixmap, cached_mtime, cached_entries = self._game_frame_previews[frame_id]

            # Get game frame to validate cache
            game_frame = project.get_game_frame_by_id(frame_id) if project else None
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
        capture_result, _ = self.get_capture_result_for_game_frame(frame_id, project)
        if capture_result is None or not capture_result.has_entries:
            return None

        try:
            renderer = CaptureRenderer(capture_result)
            preview_img = renderer.render_selection()

            # Convert PIL Image to QPixmap and cache with mtime + entry IDs
            pixmap = pil_to_qpixmap(preview_img)
            current_mtime = 0.0
            current_entries: tuple[int, ...] = ()
            if project is not None:
                game_frame = project.get_game_frame_by_id(frame_id)
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

    def get_capture_result_for_game_frame(
        self, frame_id: str, project: FrameMappingProject | None
    ) -> tuple[CaptureResult | None, bool]:
        """Get the CaptureResult for a game frame.

        Parses the capture file associated with the game frame and returns
        the CaptureResult needed for preview generation. If the game frame
        has stored selected entry IDs, only those entries are returned.

        If stored entry IDs no longer exist in the capture file (stale),
        falls back to rom_offset filtering (mirrors injection behavior) and
        emits stale_entries_warning signal.

        Args:
            frame_id: Game frame ID
            project: Current project (needed for game frame lookup)

        Returns:
            Tuple of (CaptureResult or None, used_fallback flag).
            used_fallback is True if the stored entry IDs were stale and
            rom_offset filtering was used instead.
        """
        if project is None:
            return (None, False)

        game_frame = project.get_game_frame_by_id(frame_id)
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

    def invalidate(self, frame_id: str) -> None:
        """Invalidate (clear) cache entry for a single game frame.

        Args:
            frame_id: Game frame ID to invalidate
        """
        if frame_id in self._game_frame_previews:
            del self._game_frame_previews[frame_id]
            self.preview_cache_invalidated.emit(frame_id)

    def invalidate_all(self) -> None:
        """Clear the entire preview cache."""
        self._game_frame_previews.clear()

    def set_preview_cache(self, frame_id: str, pixmap: QPixmap, mtime: float, entry_ids: tuple[int, ...]) -> None:
        """Manually set preview cache entry (used during capture import).

        Args:
            frame_id: Game frame ID
            pixmap: Preview pixmap
            mtime: File modification time
            entry_ids: Tuple of selected entry IDs
        """
        self._game_frame_previews[frame_id] = (pixmap, mtime, entry_ids)
