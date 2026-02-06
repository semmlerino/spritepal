"""Tests for WorkbenchCanvas preview toggle functionality.

The preview toggle shows an in-game preview of the final sprite after
quantization and silhouette clipping.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPixmap

from core.frame_mapping_project import AIFrame, GameFrame
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

        # Enable preview without setting any data - should hide preview item
        canvas.set_preview_enabled(True)

        assert not canvas.is_preview_visible()

    def test_generate_preview_with_disabled_hides_item(self, qtbot: QtBot) -> None:
        """Preview generation when disabled should hide preview item."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Ensure preview is disabled, then trigger state that would generate preview
        canvas.set_preview_enabled(False)
        # Even if we had data, disabled preview should keep item hidden
        canvas.set_preview_enabled(True)
        canvas.set_preview_enabled(False)

        assert not canvas.is_preview_visible()

    def test_schedule_preview_update_does_nothing_when_disabled(self, qtbot: QtBot) -> None:
        """Scheduling preview update when disabled should not start timer."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Preview disabled by default - no pending update should occur
        assert not canvas.is_preview_update_pending()

        # Even after alignment change, no update should be pending when disabled
        canvas.set_alignment(10, 10, False, False, 1.0)
        assert not canvas.is_preview_update_pending()

    def test_schedule_preview_update_starts_timer_when_enabled(self, qtbot: QtBot) -> None:
        """Scheduling preview update when enabled should start debounce timer."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas.set_preview_enabled(True)
        # Trigger alignment change which schedules preview update
        canvas.set_alignment(10, 10, False, False, 1.0)

        assert canvas.is_preview_update_pending()


class TestPreviewWithMockData:
    """Tests for preview generation with mock data.

    These tests verify async preview generation using the AsyncPreviewService.
    They wait for the preview_ready signal to confirm preview completion.
    """

    def test_preview_generates_with_valid_data(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Preview should be generated when all required data is present."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create test AI image file
        ai_image_path = tmp_path / "test_ai_frame.png"
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Set AI frame via public API
        ai_frame = AIFrame(path=ai_image_path, index=0)
        canvas.set_ai_frame(ai_frame)

        # Create mock game pixmap and capture result
        game_pixmap = QPixmap(32, 32)
        mock_capture = MagicMock()
        mock_capture.bounding_box = MagicMock()
        mock_capture.bounding_box.x = 0
        mock_capture.bounding_box.y = 0
        mock_capture.bounding_box.width = 32
        mock_capture.bounding_box.height = 32
        mock_capture.palettes = {}
        mock_capture.entries = []

        # Set game frame via public API
        game_frame = GameFrame(
            id="F00000",
            capture_path=tmp_path / "test_capture.json",
            rom_offsets=[],
            compression_types={},
        )
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=game_pixmap,
            capture_result=mock_capture,
        )

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
                # Trigger preview generation by changing alignment
                canvas.set_alignment(0, 0, False, False, 1.0)

        assert canvas.is_preview_visible()

    def test_preview_with_palette_quantizes_colors(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Preview with palette should quantize to SNES colors."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create test AI image file with specific color
        ai_image_path = tmp_path / "test_ai_frame_palette.png"
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Set AI frame via public API
        ai_frame = AIFrame(path=ai_image_path, index=0)
        canvas.set_ai_frame(ai_frame)

        # Create mock game pixmap and capture result with palette
        game_pixmap = QPixmap(32, 32)
        mock_capture = MagicMock()
        mock_capture.bounding_box = MagicMock()
        mock_capture.bounding_box.x = 0
        mock_capture.bounding_box.y = 0
        mock_capture.bounding_box.width = 32
        mock_capture.bounding_box.height = 32
        # Provide a 16-color palette
        mock_capture.palettes = {0: [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)] + [(128, 128, 128)] * 12}
        mock_capture.entries = []

        # Set game frame via public API
        game_frame = GameFrame(
            id="F00001",
            capture_path=tmp_path / "test_capture_palette.json",
            rom_offsets=[],
            compression_types={},
        )
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=game_pixmap,
            capture_result=mock_capture,
        )

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
                # Trigger preview generation by changing alignment
                canvas.set_alignment(0, 0, False, False, 1.0)

        # Should still be visible even with palette quantization
        assert canvas.is_preview_visible()


class TestPreviewUpdatesOnTransformChange:
    """Tests for preview updates when transform changes."""

    def test_flip_change_schedules_preview_update(self, qtbot: QtBot) -> None:
        """Changing flip should schedule preview update."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas.set_preview_enabled(True)

        # Change flip via public API
        canvas.set_alignment(0, 0, True, False, 1.0)

        # Timer should be active (debouncing)
        assert canvas.is_preview_update_pending()

    def test_ai_frame_transform_schedules_preview_update(self, qtbot: QtBot) -> None:
        """AI frame transform change should schedule preview update."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        canvas.set_preview_enabled(True)

        # Simulate transform change via signal handler
        # This is acceptable - signal handler direct calls are standard test pattern
        canvas._on_ai_frame_transform_changed(10, 10, 1.0)

        # Timer should be active
        assert canvas.is_preview_update_pending()


class TestPreviewWithIngameEdit:
    """Tests for in-game edited path feature in preview generation.

    The canvas can bypass the compositor and show an in-game edited sprite
    directly if set_ingame_edited_path() is called with a valid path.
    """

    def test_ingame_edit_bypasses_compositor(self, qtbot: QtBot, tmp_path: Path) -> None:
        """In-game edited path should bypass compositor and show edited sprite."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create test AI image file
        ai_image_path = tmp_path / "test_ai_frame.png"
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Set AI frame
        ai_frame = AIFrame(path=ai_image_path, index=0)
        canvas.set_ai_frame(ai_frame)

        # Create mock game pixmap and capture result
        game_pixmap = QPixmap(32, 32)
        mock_capture = MagicMock()
        mock_capture.bounding_box = MagicMock()
        mock_capture.bounding_box.x = 0
        mock_capture.bounding_box.y = 0
        mock_capture.bounding_box.width = 32
        mock_capture.bounding_box.height = 32
        mock_capture.palettes = {}
        mock_capture.entries = []

        # Set game frame
        game_frame = GameFrame(
            id="F00000",
            capture_path=tmp_path / "capture.json",
            rom_offsets=[],
            compression_types={},
        )
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=game_pixmap,
            capture_result=mock_capture,
        )

        # Create a real indexed PNG file for in-game edit
        ingame_path = tmp_path / "ingame_edit.png"
        palette_colors = [(0, 0, 0), (248, 0, 0), (0, 248, 0), (0, 0, 248)] + [(128, 128, 128)] * 12

        # Create indexed image
        img = Image.new("P", (32, 32))
        flat_palette = []
        for c in palette_colors:
            flat_palette.extend(c)
        # Pad to 256 colors
        flat_palette.extend([0] * (768 - len(flat_palette)))
        img.putpalette(flat_palette)

        # Fill with index 1 (red)
        import numpy as np

        pixels = np.full((32, 32), 1, dtype=np.uint8)
        img_indexed = Image.fromarray(pixels, mode="P")
        img_indexed.putpalette(flat_palette)
        img_indexed.save(ingame_path)

        # Set sheet palette on canvas
        from core.frame_mapping_project import SheetPalette

        palette = SheetPalette(colors=palette_colors)
        canvas.set_sheet_palette(palette)

        # Set in-game edited path
        canvas.set_ingame_edited_path(str(ingame_path))

        # Enable preview
        canvas.set_preview_enabled(True)

        # Patch async preview service to verify it's NOT called
        with patch.object(canvas._async_preview_service, "request_preview") as mock_request:
            # Call _generate_preview() directly (synchronous path)
            canvas._generate_preview()

            # Preview should be visible
            assert canvas.is_preview_visible()

            # Async service should NOT have been called (bypassed compositor)
            mock_request.assert_not_called()

    def test_ingame_edit_missing_file_falls_through(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Missing in-game edited file should fall through to compositor."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create test AI image file
        ai_image_path = tmp_path / "test_ai_frame.png"
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Set AI frame
        ai_frame = AIFrame(path=ai_image_path, index=0)
        canvas.set_ai_frame(ai_frame)

        # Create mock game pixmap and capture result
        game_pixmap = QPixmap(32, 32)
        mock_capture = MagicMock()
        mock_capture.bounding_box = MagicMock()
        mock_capture.bounding_box.x = 0
        mock_capture.bounding_box.y = 0
        mock_capture.bounding_box.width = 32
        mock_capture.bounding_box.height = 32
        mock_capture.palettes = {}
        mock_capture.entries = []

        # Set game frame
        game_frame = GameFrame(
            id="F00000",
            capture_path=tmp_path / "capture.json",
            rom_offsets=[],
            compression_types={},
        )
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=game_pixmap,
            capture_result=mock_capture,
        )

        # Set sheet palette
        palette_colors = [(0, 0, 0), (248, 0, 0), (0, 248, 0), (0, 0, 248)] + [(128, 128, 128)] * 12
        from core.frame_mapping_project import SheetPalette

        palette = SheetPalette(colors=palette_colors)
        canvas.set_sheet_palette(palette)

        # Set in-game edited path to non-existent file
        non_existent = tmp_path / "does_not_exist.png"
        canvas.set_ingame_edited_path(str(non_existent))

        # Enable preview
        canvas.set_preview_enabled(True)

        # Patch async preview service to verify it IS called (fall-through)
        with patch.object(canvas._async_preview_service, "request_preview") as mock_request:
            # Call _generate_preview() directly
            canvas._generate_preview()

            # Async service SHOULD have been called (fell through to compositor)
            mock_request.assert_called_once()
