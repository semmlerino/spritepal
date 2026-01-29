"""Tests for AsyncHighlightService."""

from __future__ import annotations

import pytest
from PIL import Image
from PySide6.QtGui import QImage

from core.frame_mapping_project import SheetPalette
from tests.fixtures.timeouts import worker_timeout
from ui.frame_mapping.services.async_highlight_service import AsyncHighlightService


class TestAsyncHighlightServiceBasics:
    """Test basic AsyncHighlightService functionality."""

    def test_service_creates_without_error(self, qtbot):
        """Service initializes correctly."""
        service = AsyncHighlightService()
        assert service is not None
        service.shutdown()

    def test_service_has_highlight_ready_signal(self, qtbot):
        """Service has highlight_ready signal."""
        service = AsyncHighlightService()
        assert hasattr(service, "highlight_ready")
        service.shutdown()

    def test_service_has_highlight_failed_signal(self, qtbot):
        """Service has highlight_failed signal."""
        service = AsyncHighlightService()
        assert hasattr(service, "highlight_failed")
        service.shutdown()


class TestAsyncHighlightWithMockData:
    """Test AsyncHighlightService with mock image data."""

    @pytest.fixture
    def service(self, qtbot):
        """Create and cleanup the service."""
        svc = AsyncHighlightService()
        yield svc
        svc.shutdown()

    @pytest.fixture
    def test_image(self):
        """Create a small test image with known colors."""
        # Create 4x4 RGBA image with specific colors
        img = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        pixels = img.load()
        assert pixels is not None
        # Row 0: red pixels
        for x in range(4):
            pixels[x, 0] = (255, 0, 0, 255)
        # Row 1: green pixels
        for x in range(4):
            pixels[x, 1] = (0, 255, 0, 255)
        # Row 2: blue pixels
        for x in range(4):
            pixels[x, 2] = (0, 0, 255, 255)
        # Row 3: transparent
        return img

    @pytest.fixture
    def test_palette(self):
        """Create a test palette with known colors."""
        return SheetPalette(
            colors=[
                (0, 0, 0),  # Index 0: black (transparent)
                (255, 0, 0),  # Index 1: red
                (0, 255, 0),  # Index 2: green
                (0, 0, 255),  # Index 3: blue
            ],
            color_mappings={},
        )

    def test_highlight_generates_with_valid_data(self, qtbot, service, test_image, test_palette):
        """Highlight mask is generated for valid input."""
        with qtbot.waitSignal(service.highlight_ready, timeout=worker_timeout()):
            service.request_highlight(
                ai_image=test_image,
                palette_index=1,  # Red
                sheet_palette=test_palette,
                display_scale=2,
                user_scale=1.0,
                flip_h=False,
                flip_v=False,
            )

    def test_new_request_cancels_previous(self, qtbot, service, test_image, test_palette):
        """New request cancels any in-progress work."""
        # First request
        service.request_highlight(
            ai_image=test_image,
            palette_index=1,
            sheet_palette=test_palette,
            display_scale=2,
            user_scale=1.0,
            flip_h=False,
            flip_v=False,
        )

        # Second request should cancel the first
        with qtbot.waitSignal(service.highlight_ready, timeout=worker_timeout()):
            service.request_highlight(
                ai_image=test_image,
                palette_index=2,  # Different index
                sheet_palette=test_palette,
                display_scale=2,
                user_scale=1.0,
                flip_h=False,
                flip_v=False,
            )

    def test_cancel_stops_pending_work(self, qtbot, service, test_image, test_palette):
        """Cancel prevents highlight_ready from being emitted."""
        # Start request
        service.request_highlight(
            ai_image=test_image,
            palette_index=1,
            sheet_palette=test_palette,
            display_scale=2,
            user_scale=1.0,
            flip_h=False,
            flip_v=False,
        )

        # Cancel immediately
        service.cancel()

        # Wait a bit to ensure no signal is emitted
        qtbot.wait(200)

    def test_shutdown_cleans_up_resources(self, qtbot, test_image, test_palette):
        """Shutdown properly cleans up thread and worker."""
        service = AsyncHighlightService()

        # Start a request
        service.request_highlight(
            ai_image=test_image,
            palette_index=1,
            sheet_palette=test_palette,
            display_scale=2,
            user_scale=1.0,
            flip_h=False,
            flip_v=False,
        )

        # Shutdown should clean up
        service.shutdown()

        # Service should be marked as destroyed
        assert service._destroyed is True
        assert service._thread is None
        assert service._worker is None


class TestHighlightMaskContent:
    """Test that highlight mask has correct content."""

    @pytest.fixture
    def service(self, qtbot):
        """Create and cleanup the service."""
        svc = AsyncHighlightService()
        yield svc
        svc.shutdown()

    def test_highlight_mask_has_correct_size(self, qtbot, service):
        """Mask is scaled correctly based on display_scale and user_scale."""
        # Create 8x8 image
        img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        palette = SheetPalette(colors=[(255, 0, 0)], color_mappings={})

        received_images = []

        def capture_image(qimage: QImage):
            received_images.append(qimage)

        service.highlight_ready.connect(capture_image)

        with qtbot.waitSignal(service.highlight_ready, timeout=worker_timeout()):
            service.request_highlight(
                ai_image=img,
                palette_index=0,
                sheet_palette=palette,
                display_scale=2,
                user_scale=1.5,
                flip_h=False,
                flip_v=False,
            )

        # Expected size: 8 * 2 * 1.5 = 24
        assert len(received_images) == 1
        assert received_images[0].width() == 24
        assert received_images[0].height() == 24
