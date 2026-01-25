"""Tests for WorkbenchCanvas auto-align zoom behavior.

Bug: When auto-alignment produces a large offset, fitInView zooms out too much
and frames become effectively invisible (appear as tiny dots).

This test specifically reproduces the "frames disappear" scenario where the AI
frame has content far from its origin, causing auto-align to produce a large
negative offset. The union of the game and AI frame rects becomes very large,
and fitInView zooms out excessively.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw
from PySide6.QtGui import QPixmap

from core.frame_mapping_project import AIFrame, GameFrame
from tests.infrastructure.mesen_mocks import create_simple_capture
from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestAutoAlignZoomBehavior:
    """Tests for excessive zoom-out bug during auto-alignment."""

    def test_auto_align_keeps_frames_visible_with_large_offset(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align should not zoom out excessively when offset is large.

        Scenario:
        - Game frame: 64x64 at canvas origin (0, 0)
        - AI frame: 1024x1024 with VERY SMALL content far from origin
        - Content at (900, 900) to (950, 950) - 50x50 pixels
        - Auto-align will center this tiny content over game frame
        - Expected offset: extremely large and negative (~-900, -900)
        - BUG: fitInView on united rect zooms way out, frames become dots
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)
        # Set realistic canvas size
        canvas.resize(600, 500)
        canvas.show()
        qtbot.wait(50)

        # 1. Create game preview (cropped to bbox dimensions)
        game_preview_path = tmp_path / "game_preview.png"
        game_preview = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
        game_preview.save(game_preview_path)

        # 2. Create AI frame with VERY small content VERY far from origin
        ai_image_path = tmp_path / "ai_frame.png"
        ai_image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ai_image)
        # Tiny content far from origin: (900, 900) to (950, 950)
        draw.rectangle([900, 900, 950, 950], fill=(0, 255, 0, 255))
        ai_image.save(ai_image_path)

        # 3. Create mock capture result with known bbox
        mock_capture = create_simple_capture(width=64, height=64)

        # 4. Create game frame
        game_frame = GameFrame(id="test_extreme_offset", width=64, height=64)

        # 5. Setup canvas with game and AI frames
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # 6. Trigger auto-align
        canvas._on_auto_align()
        qtbot.wait(50)  # Allow scene update

        # 7. ASSERTIONS: Check that view hasn't zoomed out excessively

        # Get viewport rect mapped to scene coordinates
        viewport_rect = canvas._view.mapToScene(canvas._view.viewport().rect()).boundingRect()

        # Get actual frame scene rects
        game_rect = canvas._game_frame_item.sceneBoundingRect()
        ai_rect = canvas._ai_frame_item.sceneBoundingRect()

        # Check that both rects are non-empty (frames exist)
        assert not game_rect.isEmpty(), "Game frame should exist"
        assert not ai_rect.isEmpty(), "AI frame should exist"

        # Check that viewport scene rect is reasonable (not zoomed out to huge values)
        # With extreme offsets, the combined rect can span thousands of pixels,
        # but a REASONABLE view should focus on the actual frame content, not
        # the huge empty space. Limit viewport to 5x the actual GAME RECT size
        # (which may be scaled compared to the original image).
        max_expected_viewport_size = max(game_rect.width(), game_rect.height()) * 5

        assert viewport_rect.width() < max_expected_viewport_size, (
            f"View zoomed out too far: viewport width {viewport_rect.width():.1f} > {max_expected_viewport_size}"
        )

        assert viewport_rect.height() < max_expected_viewport_size, (
            f"View zoomed out too far: viewport height {viewport_rect.height():.1f} > {max_expected_viewport_size}"
        )

        # Check that at least the game frame center is visible in viewport
        # (This is critical - user should always see the game frame after auto-align)
        game_center = game_rect.center()
        assert viewport_rect.contains(game_center), (
            f"Game frame center {game_center} not visible in viewport {viewport_rect}"
        )

    def test_auto_align_normal_offset_shows_both_frames(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align with reasonable offset should show both frames (baseline test).

        This test ensures the fix doesn't break normal cases where offset is small.
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)
        canvas.resize(600, 500)
        canvas.show()
        qtbot.wait(50)

        # Create game preview
        game_preview_path = tmp_path / "game_preview.png"
        game_preview = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
        game_preview.save(game_preview_path)

        # Create AI frame with content near origin (normal case)
        ai_image_path = tmp_path / "ai_frame.png"
        ai_image = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ai_image)
        draw.rectangle([10, 10, 70, 70], fill=(0, 255, 0, 255))
        ai_image.save(ai_image_path)

        # Mock capture result
        mock_capture = create_simple_capture(width=64, height=64)

        game_frame = GameFrame(id="test_normal", width=64, height=64)

        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # Trigger auto-align
        canvas._on_auto_align()
        qtbot.wait(50)

        # Both frames should be visible in viewport
        viewport_rect = canvas._view.mapToScene(canvas._view.viewport().rect()).boundingRect()
        game_center = canvas._game_frame_item.sceneBoundingRect().center()
        ai_center = canvas._ai_frame_item.sceneBoundingRect().center()

        assert viewport_rect.contains(game_center), "Game frame center should be visible"
        assert viewport_rect.contains(ai_center), "AI frame center should be visible"
