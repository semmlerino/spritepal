"""Tests for WorkbenchCanvas out-of-bounds clipping indicator.

These tests verify that the canvas properly shows warnings and visual
indicators when AI frame content extends outside the tile injection area.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPixmap

from core.frame_mapping_project import AIFrame, GameFrame
from tests.infrastructure.mesen_mocks import MockBoundingBox, MockCaptureResult, MockOAMEntry
from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def create_capture_with_entries(width: int, height: int, x: int = 0, y: int = 0) -> MockCaptureResult:
    """Create a capture result with a single OAM entry.

    Args:
        width: Width of the OAM entry
        height: Height of the OAM entry
        x: X position
        y: Y position

    Returns:
        MockCaptureResult with the specified entry
    """
    entry = MockOAMEntry(id=0, x=x, y=y, width=width, height=height)
    bbox = MockBoundingBox(x=x, y=y, width=width, height=height)
    return MockCaptureResult(entries=[entry], _bounding_box=bbox)


class TestOutOfBoundsWarningBanner:
    """Tests for the out-of-bounds warning banner."""

    def test_warning_banner_hidden_initially(self, qtbot: QtBot) -> None:
        """Warning banner should be hidden when canvas is created."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        assert canvas._out_of_bounds_warning_label is not None
        # Use isHidden() since isVisible() returns False when parent isn't shown
        assert canvas._out_of_bounds_warning_label.isHidden() is True

    def test_warning_banner_hidden_when_no_ai_image(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Warning banner should stay hidden when no AI image is loaded."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Set up game frame without AI image
        capture = create_capture_with_entries(width=16, height=16)
        game_pixmap = QPixmap(16, 16)
        game_pixmap.fill()

        game_frame = GameFrame(id="test_game")
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=game_pixmap,
            capture_result=capture,  # type: ignore[arg-type]
        )

        # Trigger tile touch status update
        canvas._update_tile_touch_status()

        # Use isHidden() since isVisible() returns False when parent isn't shown
        assert canvas._out_of_bounds_warning_label.isHidden() is True

    def test_warning_banner_shows_when_ai_frame_outside_tiles(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Warning banner should show when AI frame extends past tile area."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create 32x32 AI image
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game frame with small capture (16x16 tiles)
        capture = create_capture_with_entries(width=16, height=16)
        game_pixmap = QPixmap(16, 16)
        game_pixmap.fill()

        ai_frame = AIFrame(path=ai_image_path, index=0)
        game_frame = GameFrame(id="test_game")

        # Load frames - AI frame (32x32) is larger than tiles (16x16)
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=game_pixmap,
            capture_result=capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(ai_frame)
        canvas.set_alignment(0, 0, False, False, 1.0)

        # Trigger tile touch status update
        canvas._update_tile_touch_status()

        # AI frame at 32x32 extends past 16x16 tile area
        # Use isHidden() since isVisible() returns False when parent isn't shown
        assert canvas._out_of_bounds_warning_label.isHidden() is False

    def test_warning_banner_hides_when_ai_frame_inside_tiles(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Warning banner should hide when AI frame is within tile area."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create 8x8 AI image (smaller than tiles)
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game frame with 16x16 tiles
        capture = create_capture_with_entries(width=16, height=16)
        game_pixmap = QPixmap(16, 16)
        game_pixmap.fill()

        ai_frame = AIFrame(path=ai_image_path, index=0)
        game_frame = GameFrame(id="test_game")

        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=game_pixmap,
            capture_result=capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(ai_frame)
        canvas.set_alignment(0, 0, False, False, 1.0)

        canvas._update_tile_touch_status()

        # 8x8 AI frame fits in 16x16 tile area
        # Use isHidden() since isVisible() returns False when parent isn't shown
        assert canvas._out_of_bounds_warning_label.isHidden() is True


class TestClippingOverlayItem:
    """Tests for the ClippingOverlayItem visual indicator."""

    def test_clipping_overlay_exists(self, qtbot: QtBot) -> None:
        """Clipping overlay item should be created and added to scene."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        assert canvas._clipping_overlay_item is not None
        assert canvas._clipping_overlay_item.scene() == canvas._scene

    def test_clipping_overlay_empty_initially(self, qtbot: QtBot) -> None:
        """Clipping overlay should have no rects initially."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        assert canvas._clipping_overlay_item._clipped_rects == []

    def test_clipping_overlay_shows_overflow_rects(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Clipping overlay should show rectangles for overflow areas."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create 32x32 AI image
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game frame with 16x16 tiles
        capture = create_capture_with_entries(width=16, height=16)
        game_pixmap = QPixmap(16, 16)
        game_pixmap.fill()

        ai_frame = AIFrame(path=ai_image_path, index=0)
        game_frame = GameFrame(id="test_game")

        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=game_pixmap,
            capture_result=capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(ai_frame)
        canvas.set_alignment(0, 0, False, False, 1.0)

        canvas._update_tile_touch_status()

        # Should have overflow rects (32x32 AI > 16x16 tiles)
        assert len(canvas._clipping_overlay_item._clipped_rects) > 0

    def test_clipping_overlay_clears_when_no_overflow(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Clipping overlay rects should be cleared when no overflow."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create 8x8 AI image
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game frame with 16x16 tiles
        capture = create_capture_with_entries(width=16, height=16)
        game_pixmap = QPixmap(16, 16)
        game_pixmap.fill()

        ai_frame = AIFrame(path=ai_image_path, index=0)
        game_frame = GameFrame(id="test_game")

        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=game_pixmap,
            capture_result=capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(ai_frame)
        canvas.set_alignment(0, 0, False, False, 1.0)

        canvas._update_tile_touch_status()

        # No overflow - rects should be empty
        assert canvas._clipping_overlay_item._clipped_rects == []


class TestClippingOverlayDuringDrag:
    """Tests for clipping overlay updates during drag operations."""

    def test_clipping_overlay_updates_on_position_change(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Clipping overlay should update when AI frame position changes."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create 16x16 AI image
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game frame with 16x16 tiles at origin
        capture = create_capture_with_entries(width=16, height=16)
        game_pixmap = QPixmap(16, 16)
        game_pixmap.fill()

        ai_frame = AIFrame(path=ai_image_path, index=0)
        game_frame = GameFrame(id="test_game")

        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=game_pixmap,
            capture_result=capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(ai_frame)

        # Start with AI frame inside tiles (offset 0,0)
        canvas.set_alignment(0, 0, False, False, 1.0)
        canvas._update_tile_touch_status()
        # Use isHidden() since isVisible() returns False when parent isn't shown
        assert canvas._out_of_bounds_warning_label.isHidden() is True

        # Move AI frame outside tiles (offset 10,10 pushes 16x16 frame past 16x16 tile boundary)
        canvas.set_alignment(10, 10, False, False, 1.0)
        canvas._update_tile_touch_status()
        assert canvas._out_of_bounds_warning_label.isHidden() is False
        assert len(canvas._clipping_overlay_item._clipped_rects) > 0

        # Move back inside
        canvas.set_alignment(0, 0, False, False, 1.0)
        canvas._update_tile_touch_status()
        assert canvas._out_of_bounds_warning_label.isHidden() is True
        assert canvas._clipping_overlay_item._clipped_rects == []


class TestComputeTileUnionRect:
    """Tests for the _compute_tile_union_rect helper method."""

    def test_empty_tile_list(self, qtbot: QtBot) -> None:
        """Empty tile list should return zero rect."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        from PySide6.QtCore import QRect

        result = canvas._compute_tile_union_rect([])
        assert result == (0, 0, 0, 0)

    def test_single_tile(self, qtbot: QtBot) -> None:
        """Single tile should return that tile's bounds."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        from PySide6.QtCore import QRect

        tiles = [QRect(10, 20, 8, 8)]
        result = canvas._compute_tile_union_rect(tiles)
        assert result == (10, 20, 18, 28)  # (x, y, x+w, y+h)

    def test_multiple_tiles(self, qtbot: QtBot) -> None:
        """Multiple tiles should return their union bounds."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        from PySide6.QtCore import QRect

        tiles = [
            QRect(0, 0, 8, 8),  # Top-left
            QRect(8, 0, 8, 8),  # Top-right
            QRect(0, 8, 8, 8),  # Bottom-left
            QRect(8, 8, 8, 8),  # Bottom-right
        ]
        result = canvas._compute_tile_union_rect(tiles)
        assert result == (0, 0, 16, 16)

    def test_non_contiguous_tiles(self, qtbot: QtBot) -> None:
        """Non-contiguous tiles should still compute correct union."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        from PySide6.QtCore import QRect

        tiles = [
            QRect(0, 0, 8, 8),  # Origin
            QRect(100, 100, 8, 8),  # Far corner
        ]
        result = canvas._compute_tile_union_rect(tiles)
        assert result == (0, 0, 108, 108)
