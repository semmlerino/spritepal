"""Preview cache service for Frame Mapping.

Manages preview pixmap generation and caching with mtime-based invalidation.
"""

from __future__ import annotations

from json import JSONDecodeError
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

from core.frame_mapping_exceptions import CaptureParseError
from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import CaptureResult, MesenCaptureParser
from core.repositories.capture_result_repository import CaptureResultRepository
from core.services.image_utils import pil_to_qimage
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

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        capture_repository: CaptureResultRepository | None = None,
    ) -> None:
        """Initialize preview service.

        Args:
            parent: Optional Qt parent object
            capture_repository: Shared repository for caching parsed capture files.
                If None, creates a local parser (no caching shared with other services).
        """
        super().__init__(parent)
        # Cache stores (pixmap, mtime, selected_entry_ids) for invalidation on change
        self._game_frame_previews: dict[str, tuple[QPixmap, float, tuple[int, ...]]] = {}
        # Cache for filtered CaptureResult to avoid redundant filtering
        # Key: frame_id, Value: (CaptureResult, file_mtime, entry_ids_tuple)
        self._capture_result_cache: dict[str, tuple[CaptureResult, float, tuple[int, ...]]] = {}
        # Track stale entries (need regeneration but keep cached for display)
        self._stale_previews: set[str] = set()
        # Shared repository for raw capture parsing (optional)
        self._capture_repository = capture_repository
        # Fallback parser when no repository provided
        self._parser = MesenCaptureParser() if capture_repository is None else None

    def get_preview(self, frame_id: str, project: FrameMappingProject | None) -> QPixmap | None:
        """Get the rendered preview pixmap for a game frame.

        If the preview is not cached but the capture file exists, attempts to
        regenerate the preview from the capture file. Respects selected_entry_ids
        filtering to show only the selected entries in the preview.

        If the preview is marked stale (e.g., after palette change), returns the
        cached preview immediately but triggers regeneration. This provides
        responsive UI while keeping previews up-to-date.

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
        is_stale = frame_id in self._stale_previews

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
                    elif is_stale:
                        # Stale entry - return cached immediately for responsive UI
                        # Caller should schedule async regeneration separately
                        return cached_pixmap
                    else:
                        # Valid cache hit - return immediately
                        return cached_pixmap
                else:
                    # File missing: return cached preview
                    # This allows previews to persist if the source file is temporarily
                    # unavailable or deleted, providing a "last known good" view.
                    return cached_pixmap
            else:
                # No project/game_frame - invalidate stale cache entry
                del self._game_frame_previews[frame_id]
                self._stale_previews.discard(frame_id)
                return None

        # Try to regenerate from capture file (with filtering applied)
        capture_result, _ = self.get_capture_result_for_game_frame(frame_id, project)
        if capture_result is None or not capture_result.has_entries:
            return None

        try:
            renderer = CaptureRenderer(capture_result)
            preview_img = renderer.render_selection()

            # Convert PIL Image to QPixmap via QImage (faster than PNG encode/decode)
            qimage = pil_to_qimage(preview_img, with_alpha=True)
            if qimage.isNull():
                logger.warning("Failed to convert preview image to QImage for frame %s", frame_id)
                return None
            pixmap = QPixmap.fromImage(qimage)

            current_mtime = 0.0
            current_entries: tuple[int, ...] = ()
            if project is not None:
                game_frame = project.get_game_frame_by_id(frame_id)
                if game_frame:
                    current_entries = tuple(game_frame.selected_entry_ids)
                    if game_frame.capture_path and game_frame.capture_path.exists():
                        current_mtime = game_frame.capture_path.stat().st_mtime

            self._game_frame_previews[frame_id] = (pixmap, current_mtime, current_entries)
            # Clear stale flag since we just regenerated
            self._stale_previews.discard(frame_id)

            # Notify if this was a cache invalidation (not first-time generation)
            if cache_was_invalidated or is_stale:
                self.preview_cache_invalidated.emit(frame_id)

            return pixmap

        except (OSError, ValueError, CaptureParseError, Exception) as e:
            logger.warning("Failed to regenerate preview for game frame %s: %s", frame_id, e)
            return None

    def get_capture_result_for_game_frame(
        self, frame_id: str, project: FrameMappingProject | None
    ) -> tuple[CaptureResult | None, bool]:
        """Get the CaptureResult for a game frame.

        Parses the capture file associated with the game frame and returns
        the CaptureResult needed for preview generation. If the game frame
        has stored selected entry IDs, only those entries are returned.

        Results are cached by frame_id with mtime and entry_ids validation.
        Cache is invalidated when file mtime or selected_entry_ids change.

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

        # Get current file mtime and entry IDs for cache validation
        try:
            current_mtime = capture_path.stat().st_mtime
        except OSError:
            return (None, False)
        current_entry_ids = tuple(game_frame.selected_entry_ids)

        # Check cache for valid entry
        if frame_id in self._capture_result_cache:
            cached_result, cached_mtime, cached_entries = self._capture_result_cache[frame_id]
            if cached_mtime == current_mtime and cached_entries == current_entry_ids:
                # Cache hit - return cached result
                # Note: used_fallback is False for cache hits since we store the final result
                return (cached_result, False)
            # Cache miss due to mtime or entry change - will re-parse below

        try:
            # Use shared repository if available, otherwise parse directly
            if self._capture_repository is not None:
                capture_result = self._capture_repository.get_or_parse(capture_path)
            else:
                assert self._parser is not None
                capture_result = self._parser.parse_file(capture_path)

            if not capture_result.has_entries:
                return (None, False)

            # Use shared filtering utility
            from core.mesen_integration.entry_filtering import (
                create_filtered_capture,
                filter_capture_entries,
            )

            filtering = filter_capture_entries(
                capture_result,
                selected_entry_ids=list(game_frame.selected_entry_ids),
                rom_offsets=game_frame.rom_offsets,
                allow_all_entries_fallback=False,
                context_label=frame_id,
            )

            if filtering.is_stale:
                self.stale_entries_warning.emit(frame_id)

            if filtering.has_entries:
                capture_result = create_filtered_capture(capture_result, filtering.entries)

            # Cache the result (only cache if not using fallback to avoid caching stale state)
            if not filtering.used_fallback:
                self._capture_result_cache[frame_id] = (capture_result, current_mtime, current_entry_ids)

            return (capture_result, filtering.used_fallback)

        except (OSError, JSONDecodeError, KeyError, ValueError, CaptureParseError, Exception) as e:
            logger.warning("Failed to get capture result for game frame %s: %s", frame_id, e)
            return (None, False)

    def invalidate(self, frame_id: str) -> None:
        """Invalidate (clear) cache entry for a single game frame.

        Clears both the preview cache and capture result cache for this frame,
        as well as any stale marking.

        Args:
            frame_id: Game frame ID to invalidate
        """
        if frame_id in self._game_frame_previews:
            del self._game_frame_previews[frame_id]
            self.preview_cache_invalidated.emit(frame_id)
        # Also clear capture result cache and stale flag
        if frame_id in self._capture_result_cache:
            del self._capture_result_cache[frame_id]
        self._stale_previews.discard(frame_id)

    def invalidate_all(self) -> None:
        """Clear the entire preview cache and capture result cache."""
        self._game_frame_previews.clear()
        self._capture_result_cache.clear()
        self._stale_previews.clear()

    def mark_all_stale(self) -> None:
        """Mark all cached previews as stale without clearing them.

        Stale previews will be returned immediately on get_preview() but
        will also be regenerated. This provides responsive UI during
        palette changes while ensuring previews eventually update.

        Call this instead of invalidate_all() when you want existing
        previews to remain visible during regeneration.

        Note: Does NOT clear capture_result_cache since palette doesn't
        affect the parsed JSON structure - only the rendered preview.
        """
        self._stale_previews.update(self._game_frame_previews.keys())

    def force_regenerate_preview(self, frame_id: str, project: FrameMappingProject | None) -> QPixmap | None:
        """Force regeneration of a preview, bypassing stale-return optimization.

        Used by async regeneration service after returning cached stale preview.

        Args:
            frame_id: Game frame ID
            project: Current project

        Returns:
            Newly generated QPixmap or None if generation failed
        """
        # Clear from stale set to force regeneration path
        was_stale = frame_id in self._stale_previews
        self._stale_previews.discard(frame_id)

        # Remove from preview cache to force regeneration
        old_pixmap = self._game_frame_previews.pop(frame_id, None)

        # Regenerate
        new_pixmap = self.get_preview(frame_id, project)

        # If regeneration failed, restore old cached pixmap
        if new_pixmap is None and old_pixmap is not None:
            self._game_frame_previews[frame_id] = old_pixmap
            if was_stale:
                self._stale_previews.add(frame_id)

        return new_pixmap

    def regenerate_visible_previews(self, visible_frame_ids: list[str], project: FrameMappingProject | None) -> None:
        """Regenerate previews for visible frames first.

        Prioritizes regenerating stale previews that are currently visible,
        ensuring the user sees updated content quickly.

        Args:
            visible_frame_ids: List of frame IDs currently visible in the UI
            project: Current project
        """
        for frame_id in visible_frame_ids:
            if frame_id in self._stale_previews:
                # Force regeneration (bypasses stale-return optimization)
                self.force_regenerate_preview(frame_id, project)

    def get_stale_count(self) -> int:
        """Get the number of stale preview entries.

        Returns:
            Number of previews marked as stale
        """
        return len(self._stale_previews)

    def set_preview_cache(self, frame_id: str, pixmap: QPixmap, mtime: float, entry_ids: tuple[int, ...]) -> None:
        """Manually set preview cache entry (used during capture import).

        Args:
            frame_id: Game frame ID
            pixmap: Preview pixmap
            mtime: File modification time
            entry_ids: Tuple of selected entry IDs
        """
        self._game_frame_previews[frame_id] = (pixmap, mtime, entry_ids)
