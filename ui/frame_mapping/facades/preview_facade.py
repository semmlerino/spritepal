"""Facade for preview operations.

Groups preview-related controller methods: get preview, get cached,
request async, and get capture result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ui.frame_mapping.services.async_game_frame_preview_service import (
    AsyncGameFramePreviewService,
)
from ui.frame_mapping.services.preview_service import PreviewService
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from PySide6.QtGui import QPixmap

    from core.mesen_integration.click_extractor import CaptureResult
    from ui.frame_mapping.facades.controller_context import ControllerContext

logger = get_logger(__name__)


class PreviewSignals(Protocol):
    """Protocol for preview-related signal emissions."""

    def emit_game_frame_previews_finished(self) -> None: ...


class PreviewFacade:
    """Facade for preview operations.

    Handles game frame preview generation, caching, and async requests.
    """

    def __init__(
        self,
        context: ControllerContext,
        signals: PreviewSignals,
        preview_service: PreviewService,
        async_preview_service: AsyncGameFramePreviewService,
    ) -> None:
        """Initialize the preview facade.

        Args:
            context: Shared controller context for project access.
            signals: Signal emitter for UI updates.
            preview_service: Service for sync preview operations.
            async_preview_service: Service for async preview generation.
        """
        self._context = context
        self._signals = signals
        self._preview_service = preview_service
        self._async_preview_service = async_preview_service

    # ─── Preview Access ───────────────────────────────────────────────────────

    def get_preview(self, frame_id: str) -> QPixmap | None:
        """Get the rendered preview pixmap for a game frame.

        Delegates to preview service for caching and rendering.

        Args:
            frame_id: Game frame ID.

        Returns:
            QPixmap preview or None if not available.
        """
        return self._preview_service.get_preview(frame_id, self._context.project)

    def get_cached_preview(self, frame_id: str) -> QPixmap | None:
        """Get cached preview without triggering regeneration.

        Returns the cached preview only if it's available and valid.
        Does not block to regenerate - use this for non-blocking UI updates.
        Call request_previews_async() for any cache misses.

        Args:
            frame_id: Game frame ID.

        Returns:
            Cached QPixmap or None if not available/stale.
        """
        return self._preview_service.get_cached_preview(frame_id, self._context.project)

    def get_capture_result(self, frame_id: str) -> tuple[CaptureResult | None, bool]:
        """Get the CaptureResult for a game frame.

        Delegates to preview service for capture parsing and filtering.

        Args:
            frame_id: Game frame ID.

        Returns:
            Tuple of (CaptureResult or None, used_fallback flag).
            used_fallback is True if the stored entry IDs were stale and
            rom_offset filtering was used instead.
        """
        return self._preview_service.get_capture_result_for_game_frame(frame_id, self._context.project)

    # ─── Async Preview Requests ───────────────────────────────────────────────

    def request_previews_async(self, frame_ids: list[str]) -> None:
        """Request async preview generation for specified game frames.

        Generates previews in a background thread, emitting game_frame_preview_ready
        for each completed preview.

        Args:
            frame_ids: List of game frame IDs to generate previews for.
        """
        project = self._context.project
        if project is None:
            self._signals.emit_game_frame_previews_finished()
            return

        self._async_preview_service.request_previews(frame_ids, project)
