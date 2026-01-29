"""Tests for AsyncPreviewService.

Verifies the async preview service properly offloads compositor work
to a background thread and handles request cancellation.
"""

from __future__ import annotations

from collections.abc import Generator
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


@pytest.fixture
def service(qtbot: QtBot) -> Generator[AsyncPreviewService, None, None]:
    """Fixture to provide an AsyncPreviewService instance with auto-cleanup."""
    svc = AsyncPreviewService()
    yield svc
    svc.shutdown()


class TestAsyncPreviewServiceBasics:
    """Basic functionality tests for AsyncPreviewService."""

    def test_service_creates_without_error(self, service: AsyncPreviewService) -> None:
        """Service should create with proper initial state (lazy initialization)."""
        assert service is not None
        # Service uses lazy initialization - worker/thread created on first request
        assert service._worker is None, "Worker should be None before first request (lazy init)"
        assert service._thread is None, "Thread should be None before first request (lazy init)"
        assert service._current_request_id == 0, "Request ID should start at 0"
        assert not service._destroyed, "Service should not be marked destroyed initially"

    def test_service_has_preview_ready_signal(self, service: AsyncPreviewService) -> None:
        """Service should have connectable preview_ready signal."""
        assert hasattr(service, "preview_ready")
        # Verify signal is connectable (the actual contract, not just attribute existence)
        callback_called: list[QImage] = []
        service.preview_ready.connect(lambda img, w, h: callback_called.append(img))
        # Signal connected successfully - disconnect to clean up
        service.preview_ready.disconnect()

    def test_service_has_preview_failed_signal(self, service: AsyncPreviewService) -> None:
        """Service should have connectable preview_failed signal."""
        assert hasattr(service, "preview_failed")
        # Verify signal is connectable
        errors: list[str] = []
        service.preview_failed.connect(lambda msg: errors.append(msg))
        service.preview_failed.disconnect()


class TestAsyncPreviewWithMockData:
    """Tests for preview generation with mock data."""

    def test_preview_generates_with_valid_data(self, service: AsyncPreviewService, qtbot: QtBot) -> None:
        """Preview should be generated when all required data is present."""
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

    def test_new_request_cancels_previous(self, service: AsyncPreviewService, qtbot: QtBot) -> None:
        """New request should cancel any in-progress work, only last request completes."""
        # Track all emitted signals with their parameters
        # Signal is (qimage: QImage, width: int, height: int)
        # Note: width/height in signal are the LOGICAL (unscaled) dimensions,
        # but the QImage itself IS scaled by display_scale
        results: list[tuple[QImage, int, int]] = []
        service.preview_ready.connect(lambda img, w, h: results.append((img, w, h)))

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

        # Request multiple previews in quick succession with distinguishable display_scale
        # This way we can verify which request's result we got by checking the QImage size
        for i in range(3):
            ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
            service.request_preview(
                ai_image=ai_img,
                capture_result=mock_capture,
                transform=transform,
                uncovered_policy="original",
                sheet_palette=None,
                ai_index_map=None,
                display_scale=i + 2,  # Scale 2, 3, 4 for requests 0, 1, 2
            )

        # Wait for processing to complete
        with qtbot.waitSignal(service.preview_ready, timeout=worker_timeout()):
            pass

        # Give time for any stale signals that might emit (they shouldn't)
        qtbot.wait(50)

        # Verify cancellation behavior:
        # 1. Only one result should be emitted (last request)
        assert len(results) == 1, (
            f"Expected exactly 1 result (only last request should complete), got {len(results)} results"
        )

        # 2. The result should be from the last request (display_scale=4)
        # The QImage is scaled by display_scale, so we can verify by checking its dimensions
        qimage, logical_width, logical_height = results[0]
        expected_scale = 4  # Last request had display_scale=4
        expected_qimage_dim = 32 * expected_scale  # bounding_box was 32x32, scaled by 4

        # Verify the QImage has the expected scaled dimensions
        assert qimage.width() == expected_qimage_dim and qimage.height() == expected_qimage_dim, (
            f"QImage dimensions ({qimage.width()}x{qimage.height()}) don't match expected "
            f"({expected_qimage_dim}x{expected_qimage_dim}) for last request with scale={expected_scale}. "
            "This would indicate an earlier request (with smaller scale) was returned instead."
        )

        # The logical dimensions should be the unscaled preview size
        assert logical_width == 32 and logical_height == 32, (
            f"Logical dimensions ({logical_width}x{logical_height}) should be unscaled (32x32)"
        )

    def test_shutdown_cleans_up_resources(self, service: AsyncPreviewService, qtbot: QtBot) -> None:
        """Shutdown should clean up worker and thread completely."""
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

        # Capture thread reference before shutdown
        thread_before = service._thread
        assert thread_before is not None
        assert thread_before.isRunning(), "Thread should be running before shutdown"

        # Shutdown should not raise
        service.shutdown()

        # Worker and thread references should be cleared
        assert service._worker is None, "Worker should be cleaned up"
        assert service._thread is None, "Thread reference should be cleared"

        # Service should be marked as destroyed
        assert service._destroyed, "Service should be marked destroyed after shutdown"

        # Original thread should have stopped (not zombie)
        assert not thread_before.isRunning(), "Thread should be stopped, not zombie"
        assert thread_before.isFinished(), "Thread should be finished"
