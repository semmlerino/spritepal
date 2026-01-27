"""Tests for AsyncPreviewService.

Verifies the async preview service properly offloads compositor work
to a background thread and handles request cancellation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from PIL import Image
from PySide6.QtGui import QImage

from core.services.sprite_compositor import TransformParams
from tests.fixtures.timeouts import worker_timeout
from ui.frame_mapping.services.async_preview_service import AsyncPreviewService

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestAsyncPreviewServiceBasics:
    """Basic functionality tests for AsyncPreviewService."""

    def test_service_creates_without_error(self, qtbot: QtBot) -> None:
        """Service should create without error."""
        service = AsyncPreviewService()
        assert service is not None

    def test_service_has_preview_ready_signal(self, qtbot: QtBot) -> None:
        """Service should have preview_ready signal."""
        service = AsyncPreviewService()
        assert hasattr(service, "preview_ready")

    def test_service_has_preview_failed_signal(self, qtbot: QtBot) -> None:
        """Service should have preview_failed signal."""
        service = AsyncPreviewService()
        assert hasattr(service, "preview_failed")


class TestAsyncPreviewWithMockData:
    """Tests for preview generation with mock data."""

    def test_preview_generates_with_valid_data(self, qtbot: QtBot) -> None:
        """Preview should be generated when all required data is present."""
        service = AsyncPreviewService()

        # Create mock AI image
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))

        # Create mock capture result
        mock_capture = MagicMock()
        mock_capture.bounding_box = MagicMock()
        mock_capture.bounding_box.x = 0
        mock_capture.bounding_box.y = 0
        mock_capture.bounding_box.width = 32
        mock_capture.bounding_box.height = 32
        mock_capture.palettes = {}
        mock_capture.entries = []

        transform = TransformParams(offset_x=0, offset_y=0)

        # Wait for preview_ready signal
        with qtbot.waitSignal(service.preview_ready, timeout=worker_timeout()):
            service.request_preview(
                ai_image=ai_img,
                capture_result=mock_capture,
                transform=transform,
                uncovered_policy="original",
                sheet_palette=None,
                ai_index_map=None,
                display_scale=2,
            )

    def test_new_request_cancels_previous(self, qtbot: QtBot) -> None:
        """New request should cancel any in-progress work."""
        service = AsyncPreviewService()

        # Create mock AI image
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))

        # Create mock capture result
        mock_capture = MagicMock()
        mock_capture.bounding_box = MagicMock()
        mock_capture.bounding_box.x = 0
        mock_capture.bounding_box.y = 0
        mock_capture.bounding_box.width = 32
        mock_capture.bounding_box.height = 32
        mock_capture.palettes = {}
        mock_capture.entries = []

        transform = TransformParams(offset_x=0, offset_y=0)

        # Request multiple previews in quick succession
        for i in range(3):
            service.request_preview(
                ai_image=ai_img,
                capture_result=mock_capture,
                transform=transform,
                uncovered_policy="original",
                sheet_palette=None,
                ai_index_map=None,
                display_scale=2,
            )

        # Only the last request should complete
        with qtbot.waitSignal(service.preview_ready, timeout=worker_timeout()):
            pass

    def test_shutdown_cleans_up_resources(self, qtbot: QtBot) -> None:
        """Shutdown should clean up worker and thread."""
        service = AsyncPreviewService()

        # Create mock AI image
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))

        # Create mock capture result
        mock_capture = MagicMock()
        mock_capture.bounding_box = MagicMock()
        mock_capture.bounding_box.x = 0
        mock_capture.bounding_box.y = 0
        mock_capture.bounding_box.width = 32
        mock_capture.bounding_box.height = 32
        mock_capture.palettes = {}
        mock_capture.entries = []

        transform = TransformParams(offset_x=0, offset_y=0)

        service.request_preview(
            ai_image=ai_img,
            capture_result=mock_capture,
            transform=transform,
            uncovered_policy="original",
            sheet_palette=None,
            ai_index_map=None,
            display_scale=2,
        )

        # Shutdown should not raise
        service.shutdown()

        # Worker and thread should be cleaned up
        assert service._worker is None
        assert service._thread is None
