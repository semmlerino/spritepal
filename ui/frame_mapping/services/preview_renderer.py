"""Shared preview rendering utilities for Frame Mapping.

Provides a single implementation for rendering capture previews,
used by both PreviewService (sync) and AsyncGameFramePreviewService (async).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtGui import QImage

from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import CaptureResult
from core.services.image_utils import pil_to_qimage
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.repositories.capture_result_repository import CaptureResultRepository

logger = get_logger(__name__)


class PreviewRenderer:
    """Shared preview rendering logic for game frame captures.

    Provides static methods to render preview images from CaptureResult objects,
    ensuring consistent rendering behavior across sync and async paths.
    """

    @staticmethod
    def render_preview_image(capture_result: CaptureResult) -> Image.Image | None:
        """Render a preview PIL Image from a capture result.

        Args:
            capture_result: The parsed capture result with entries

        Returns:
            PIL Image of the rendered preview, or None if rendering fails
        """
        if not capture_result.has_entries:
            return None

        try:
            renderer = CaptureRenderer(capture_result)
            return renderer.render_selection()
        except Exception as e:
            logger.warning("Error rendering preview: %s", e)
            return None

    @staticmethod
    def render_preview_qimage(capture_result: CaptureResult) -> QImage | None:
        """Render a preview QImage from a capture result.

        Suitable for use in worker threads (QImage is thread-safe).

        Args:
            capture_result: The parsed capture result with entries

        Returns:
            QImage of the rendered preview, or None if rendering fails
        """
        preview_img = PreviewRenderer.render_preview_image(capture_result)
        if preview_img is None:
            return None

        qimage = pil_to_qimage(preview_img, with_alpha=True)
        if qimage.isNull():
            logger.warning("Failed to convert preview image to QImage")
            return None
        return qimage

    @staticmethod
    def parse_and_filter_capture(
        capture_path: Path,
        selected_entry_ids: list[int],
        rom_offsets: list[int],
        frame_id: str,
        capture_repository: CaptureResultRepository,
    ) -> tuple[CaptureResult | None, bool, bool]:
        """Parse a capture file and filter its entries.

        Args:
            capture_path: Path to capture JSON file
            selected_entry_ids: Entry IDs to filter (empty = no filtering)
            rom_offsets: ROM offsets for fallback filtering
            frame_id: Frame ID for logging context
            capture_repository: Shared repository for caching

        Returns:
            Tuple of (filtered CaptureResult or None, used_fallback flag, is_stale flag).
            is_stale indicates stored entry IDs no longer exist in capture file.
        """
        if not capture_path.exists():
            return (None, False, False)

        try:
            # Parse capture (use repository for caching)
            capture_result = capture_repository.get_or_parse(capture_path)

            if not capture_result.has_entries:
                return (None, False, False)

            # Apply filtering if entry IDs specified
            from core.mesen_integration.entry_filtering import (
                create_filtered_capture,
                filter_capture_entries,
            )

            filtering = filter_capture_entries(
                capture_result,
                selected_entry_ids=selected_entry_ids,
                rom_offsets=rom_offsets,
                allow_all_entries_fallback=False,
                context_label=frame_id,
            )

            if filtering.has_entries:
                capture_result = create_filtered_capture(capture_result, filtering.entries)

            return (capture_result, filtering.used_fallback, filtering.is_stale)

        except Exception as e:
            logger.warning("Error parsing capture for %s: %s", frame_id, e)
            return (None, False, False)
