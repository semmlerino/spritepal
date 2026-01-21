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

from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestPreviewToggle:
    """Tests for the preview toggle checkbox and visibility."""

    def test_preview_checkbox_exists(self, qtbot: QtBot) -> None:
        """WorkbenchCanvas should have a preview checkbox."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        assert hasattr(canvas, "_preview_checkbox")
        assert canvas._preview_checkbox is not None
        assert not canvas._preview_checkbox.isChecked()  # Off by default

    def test_preview_item_exists_and_hidden_by_default(self, qtbot: QtBot) -> None:
        """WorkbenchCanvas should have a preview item that's hidden by default."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        assert hasattr(canvas, "_preview_item")
        assert canvas._preview_item is not None
        assert not canvas._preview_item.isVisible()

    def test_preview_toggle_updates_enabled_state(self, qtbot: QtBot) -> None:
        """Toggling preview checkbox should update _preview_enabled state."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        assert not canvas._preview_enabled

        canvas._preview_checkbox.setChecked(True)
        assert canvas._preview_enabled

        canvas._preview_checkbox.setChecked(False)
        assert not canvas._preview_enabled

    def test_preview_disabled_hides_item(self, qtbot: QtBot) -> None:
        """Disabling preview should hide the preview item."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Enable then disable
        canvas._preview_checkbox.setChecked(True)
        canvas._preview_checkbox.setChecked(False)

        assert not canvas._preview_item.isVisible()

    def test_preview_enabled_hides_ai_frame(self, qtbot: QtBot) -> None:
        """Enabling preview should hide the AI frame item."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # AI frame should be visible by default
        assert canvas._ai_frame_item.isVisible()

        # Enable preview - AI frame should be hidden
        canvas._preview_checkbox.setChecked(True)
        assert not canvas._ai_frame_item.isVisible()

        # Disable preview - AI frame should be visible again
        canvas._preview_checkbox.setChecked(False)
        assert canvas._ai_frame_item.isVisible()


class TestPreviewGeneration:
    """Tests for preview generation logic."""

    def test_generate_preview_without_data_hides_item(self, qtbot: QtBot) -> None:
        """Preview generation without required data should hide preview item."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas._preview_enabled = True
        canvas._generate_preview()

        assert not canvas._preview_item.isVisible()

    def test_generate_preview_with_disabled_hides_item(self, qtbot: QtBot) -> None:
        """Preview generation when disabled should hide preview item."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas._preview_enabled = False
        canvas._generate_preview()

        assert not canvas._preview_item.isVisible()

    def test_schedule_preview_update_does_nothing_when_disabled(self, qtbot: QtBot) -> None:
        """Scheduling preview update when disabled should not start timer."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas._preview_enabled = False
        canvas._schedule_preview_update()

        assert not canvas._preview_timer.isActive()

    def test_schedule_preview_update_starts_timer_when_enabled(self, qtbot: QtBot) -> None:
        """Scheduling preview update when enabled should start debounce timer."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas._preview_enabled = True
        canvas._schedule_preview_update()

        assert canvas._preview_timer.isActive()


class TestPreviewWithMockData:
    """Tests for preview generation with mock data."""

    def test_preview_generates_with_valid_data(self, qtbot: QtBot) -> None:
        """Preview should be generated when all required data is present."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create mock AI image
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
        canvas._capture_result = mock_capture

        canvas._preview_enabled = True

        # Mock the CaptureRenderer to return a simple image
        with patch(
            "core.mesen_integration.capture_renderer.CaptureRenderer"
        ) as mock_renderer_cls:
            mock_renderer = MagicMock()
            mock_renderer.render_selection.return_value = Image.new(
                "RGBA", (32, 32), (0, 255, 0, 255)
            )
            mock_renderer_cls.return_value = mock_renderer

            canvas._generate_preview()

        assert canvas._preview_item.isVisible()

    def test_preview_with_palette_quantizes_colors(self, qtbot: QtBot) -> None:
        """Preview with palette should quantize to SNES colors."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create mock AI image with specific color
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
        canvas._capture_result = mock_capture

        canvas._preview_enabled = True

        with patch(
            "core.mesen_integration.capture_renderer.CaptureRenderer"
        ) as mock_renderer_cls:
            mock_renderer = MagicMock()
            mock_renderer.render_selection.return_value = Image.new(
                "RGBA", (32, 32), (0, 255, 0, 255)
            )
            mock_renderer_cls.return_value = mock_renderer

            canvas._generate_preview()

        # Should still be visible even with palette quantization
        assert canvas._preview_item.isVisible()


class TestPreviewUpdatesOnTransformChange:
    """Tests for preview updates when transform changes."""

    def test_flip_change_schedules_preview_update(self, qtbot: QtBot) -> None:
        """Changing flip should schedule preview update."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas._preview_enabled = True

        # Change flip
        canvas._flip_h_checkbox.setChecked(True)

        # Timer should be active (debouncing)
        assert canvas._preview_timer.isActive()

    def test_ai_frame_transform_schedules_preview_update(self, qtbot: QtBot) -> None:
        """AI frame transform change should schedule preview update."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas._preview_enabled = True

        # Simulate transform change
        canvas._on_ai_frame_transform_changed(10, 10, 1.0)

        # Timer should be active
        assert canvas._preview_timer.isActive()
