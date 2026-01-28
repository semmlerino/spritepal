"""Tests for WorkbenchCanvas preview toggle functionality.

The preview toggle shows an in-game preview of the final sprite after
quantization and silhouette clipping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPixmap

from tests.fixtures.timeouts import worker_timeout
from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestPreviewToggle:
    """Tests for the preview toggle checkbox and visibility."""

    def test_preview_disabled_by_default(self, qtbot: QtBot) -> None:
        """WorkbenchCanvas should have preview disabled by default."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Preview is off by default
        assert not canvas.is_preview_enabled()

    def test_preview_item_hidden_by_default(self, qtbot: QtBot) -> None:
        """WorkbenchCanvas should have preview item hidden by default."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Preview item is hidden by default
        assert not canvas.is_preview_visible()

    def test_preview_toggle_updates_enabled_state(self, qtbot: QtBot) -> None:
        """Toggling preview should update enabled state."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        assert not canvas.is_preview_enabled()

        canvas.set_preview_enabled(True)
        assert canvas.is_preview_enabled()

        canvas.set_preview_enabled(False)
        assert not canvas.is_preview_enabled()

    def test_preview_disabled_hides_item(self, qtbot: QtBot) -> None:
        """Disabling preview should hide the preview item."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Enable then disable
        canvas.set_preview_enabled(True)
        canvas.set_preview_enabled(False)

        assert not canvas.is_preview_visible()

    def test_preview_enabled_puts_ai_frame_in_ghost_mode(self, qtbot: QtBot) -> None:
        """Enabling preview should put AI frame in ghost mode."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # AI frame should not be in ghost mode by default
        assert not canvas.is_ai_frame_in_ghost_mode()

        # Enable preview - AI frame should enter ghost mode (still visible, but outline only)
        canvas.set_preview_enabled(True)
        assert canvas.is_ai_frame_in_ghost_mode()

        # Disable preview - AI frame should exit ghost mode
        canvas.set_preview_enabled(False)
        assert not canvas.is_ai_frame_in_ghost_mode()


class TestPreviewGeneration:
    """Tests for preview generation logic."""

    def test_generate_preview_without_data_hides_item(self, qtbot: QtBot) -> None:
        """Preview generation without required data should hide preview item."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas.set_preview_enabled(True)
        canvas._generate_preview()

        assert not canvas.is_preview_visible()

    def test_generate_preview_with_disabled_hides_item(self, qtbot: QtBot) -> None:
        """Preview generation when disabled should hide preview item."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas.set_preview_enabled(False)
        canvas._generate_preview()

        assert not canvas.is_preview_visible()

    def test_schedule_preview_update_does_nothing_when_disabled(self, qtbot: QtBot) -> None:
        """Scheduling preview update when disabled should not start timer."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Preview disabled by default, schedule update does nothing
        canvas._schedule_preview_update()

        assert not canvas.is_preview_update_pending()

    def test_schedule_preview_update_starts_timer_when_enabled(self, qtbot: QtBot) -> None:
        """Scheduling preview update when enabled should start debounce timer."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas.set_preview_enabled(True)
        canvas._schedule_preview_update()

        assert canvas.is_preview_update_pending()


class TestPreviewWithMockData:
    """Tests for preview generation with mock data.

    These tests verify async preview generation using the AsyncPreviewService.
    They wait for the preview_ready signal to confirm preview completion.
    """

    def test_preview_generates_with_valid_data(self, qtbot: QtBot) -> None:
        """Preview should be generated when all required data is present."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create mock AI image (test data setup - internal access acceptable)
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        canvas._ai_image = ai_img

        # Create mock game pixmap
        canvas._game_pixmap = QPixmap(32, 32)

        # Create mock capture result with bounding box
        mock_capture = MagicMock()
        mock_capture.bounding_box = MagicMock()
        mock_capture.bounding_box.x = 0
        mock_capture.bounding_box.y = 0
        mock_capture.bounding_box.width = 32
        mock_capture.bounding_box.height = 32
        mock_capture.palettes = {}
        mock_capture.entries = []  # Required for compositor
        canvas._capture_result = mock_capture

        canvas.set_preview_enabled(True)

        # Mock the CaptureRenderer to return a simple image
        with patch("core.mesen_integration.capture_renderer.CaptureRenderer") as mock_renderer_cls:
            mock_renderer = MagicMock()
            mock_renderer.render_selection.return_value = Image.new("RGBA", (32, 32), (0, 255, 0, 255))
            mock_renderer_cls.return_value = mock_renderer

            # Wait for async preview completion
            with qtbot.waitSignal(
                canvas._async_preview_service.preview_ready,
                timeout=worker_timeout(),
            ):
                canvas._generate_preview()

        assert canvas.is_preview_visible()

        # Verify preview has expected dimensions (not just visibility)
        preview_pixmap = canvas._preview_item.pixmap()
        assert preview_pixmap is not None, "Preview should have pixmap"
        assert not preview_pixmap.isNull(), "Preview pixmap should not be null"

        # Preview should match game frame dimensions * display_scale
        expected_width = 32 * canvas._display_scale
        expected_height = 32 * canvas._display_scale
        assert preview_pixmap.width() == expected_width, (
            f"Preview width {preview_pixmap.width()} should be {expected_width}"
        )
        assert preview_pixmap.height() == expected_height, (
            f"Preview height {preview_pixmap.height()} should be {expected_height}"
        )

    def test_preview_with_palette_quantizes_colors(self, qtbot: QtBot) -> None:
        """Preview with palette should quantize to SNES colors."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create mock AI image with specific color (test data setup)
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        canvas._ai_image = ai_img

        # Create mock game pixmap
        canvas._game_pixmap = QPixmap(32, 32)

        # Create mock capture result with palette
        mock_capture = MagicMock()
        mock_capture.bounding_box = MagicMock()
        mock_capture.bounding_box.x = 0
        mock_capture.bounding_box.y = 0
        mock_capture.bounding_box.width = 32
        mock_capture.bounding_box.height = 32
        # Provide a 16-color palette
        mock_capture.palettes = {0: [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)] + [(128, 128, 128)] * 12}
        mock_capture.entries = []  # Required for compositor
        canvas._capture_result = mock_capture

        canvas.set_preview_enabled(True)

        with patch("core.mesen_integration.capture_renderer.CaptureRenderer") as mock_renderer_cls:
            mock_renderer = MagicMock()
            mock_renderer.render_selection.return_value = Image.new("RGBA", (32, 32), (0, 255, 0, 255))
            mock_renderer_cls.return_value = mock_renderer

            # Wait for async preview completion
            with qtbot.waitSignal(
                canvas._async_preview_service.preview_ready,
                timeout=worker_timeout(),
            ):
                canvas._generate_preview()

        # Should still be visible even with palette quantization
        assert canvas.is_preview_visible()


class TestPreviewUpdatesOnTransformChange:
    """Tests for preview updates when transform changes."""

    def test_flip_change_schedules_preview_update(self, qtbot: QtBot) -> None:
        """Changing flip should schedule preview update."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas.set_preview_enabled(True)

        # Change flip (using internal checkbox as this is an input trigger)
        canvas._flip_h_checkbox.setChecked(True)

        # Timer should be active (debouncing)
        assert canvas.is_preview_update_pending()

    def test_ai_frame_transform_schedules_preview_update(self, qtbot: QtBot) -> None:
        """AI frame transform change should schedule preview update."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas.set_preview_enabled(True)

        # Simulate transform change
        canvas._on_ai_frame_transform_changed(10, 10, 1.0)

        # Timer should be active
        assert canvas.is_preview_update_pending()
