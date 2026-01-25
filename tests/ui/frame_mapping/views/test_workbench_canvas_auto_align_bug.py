"""Tests for Bug: Auto-align silent failure when conditions aren't met.

Bug: When clicking the Auto-Align button, if _ai_image is None (PIL load failed)
or _capture_result is None, the method silently returns without any user feedback.
The button also remains enabled even when auto-align cannot work.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtGui import QPixmap

from core.frame_mapping_project import AIFrame, GameFrame
from tests.infrastructure.mesen_mocks import create_simple_capture
from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestAutoAlignFeedback:
    """Tests for auto-align providing feedback when it cannot align."""

    def test_auto_align_button_disabled_without_ai_image(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align button should be disabled when AI image is not loaded.

        Bug: Button stays enabled, clicking it does nothing (silent failure).
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create game frame preview
        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (32, 32), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        # Mock capture result
        mock_capture = create_simple_capture(width=32, height=32)

        game_frame = GameFrame(id="test_frame", width=32, height=32)

        # Set game frame with capture result (has what auto-align needs from game side)
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )

        # Enable mapping but DON'T set AI frame - _ai_image will be None
        canvas.set_alignment(0, 0, False, False, 1.0)

        # Bug assertion: button should be disabled because _ai_image is None
        assert not canvas._auto_align_btn.isEnabled(), (
            "Auto-align button should be disabled when AI image is not loaded"
        )

    def test_auto_align_button_disabled_without_capture_result(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align button should be disabled when capture result is not available.

        Bug: Button stays enabled, clicking it does nothing (silent failure).
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create AI image
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Set AI frame (has valid _ai_image)
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # Set game frame WITHOUT capture result
        game_frame = GameFrame(id="test_frame", width=32, height=32)
        canvas.set_game_frame(frame=game_frame, capture_result=None)

        # Enable mapping
        canvas.set_alignment(0, 0, False, False, 1.0)

        # Bug assertion: button should be disabled because _capture_result is None
        assert not canvas._auto_align_btn.isEnabled(), (
            "Auto-align button should be disabled when capture result is not available"
        )

    def test_auto_align_button_enabled_when_all_conditions_met(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align button should be enabled when all conditions are met."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create AI image
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game frame preview
        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (32, 32), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        # Mock capture result
        mock_capture = create_simple_capture(width=32, height=32)

        game_frame = GameFrame(id="test_frame", width=32, height=32)

        # Set both frames with valid data
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # Enable mapping
        canvas.set_alignment(0, 0, False, False, 1.0)

        # Button should be enabled when all conditions are met
        assert canvas._auto_align_btn.isEnabled(), (
            "Auto-align button should be enabled when AI image, capture result, and mapping are all available"
        )

    def test_auto_align_shows_status_when_cannot_align(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Clicking auto-align should show status message when it cannot align.

        Bug: Method silently returns, no feedback to user.
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Setup game frame with capture result
        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (32, 32), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        mock_capture = create_simple_capture(width=32, height=32)

        game_frame = GameFrame(id="test_frame", width=32, height=32)
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )

        # Enable mapping WITHOUT setting AI frame
        canvas.set_alignment(0, 0, False, False, 1.0)

        # Manually call _on_auto_align (simulating button click)
        # This should either:
        # 1. Be prevented (button disabled) - preferred
        # 2. Show feedback in status label - acceptable fallback
        canvas._on_auto_align()

        # If button was enabled and clicked, status should explain why it didn't work
        # (Note: This test passes if button is disabled - the preferred fix)
        status_text = canvas._status_label.text()
        if canvas._auto_align_btn.isEnabled():
            assert "AI" in status_text or "image" in status_text.lower(), (
                f"Status should explain auto-align failure, got: '{status_text}'"
            )


class TestAutoAlignButtonStateOnFrameChanges:
    """Tests that auto-align button state updates when frames change."""

    def test_button_state_updates_when_ai_frame_set(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align button should update when AI frame is set."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Setup game frame with capture result first
        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (32, 32), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        mock_capture = create_simple_capture(width=32, height=32)

        game_frame = GameFrame(id="test_frame", width=32, height=32)
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )

        # Enable mapping but no AI frame yet
        canvas.set_alignment(0, 0, False, False, 1.0)

        # Button should be disabled without AI frame
        initial_state = canvas._auto_align_btn.isEnabled()

        # Now set AI frame
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
        ai_img.save(ai_image_path)
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # Button should now be enabled
        final_state = canvas._auto_align_btn.isEnabled()

        assert not initial_state, "Button should be disabled before AI frame is set"
        assert final_state, "Button should be enabled after AI frame is set"

    def test_button_state_updates_when_game_frame_cleared(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align button should disable when game frame is cleared."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Setup both frames
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
        ai_img.save(ai_image_path)

        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (32, 32), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        mock_capture = create_simple_capture(width=32, height=32)

        game_frame = GameFrame(id="test_frame", width=32, height=32)
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))
        canvas.set_alignment(0, 0, False, False, 1.0)

        # Button should be enabled
        assert canvas._auto_align_btn.isEnabled(), "Pre-condition: button should be enabled"

        # Clear game frame
        canvas.set_game_frame(frame=None)

        # Button should now be disabled (no capture result)
        assert not canvas._auto_align_btn.isEnabled(), "Button should be disabled after game frame cleared"


class TestAutoAlignWithTransforms:
    """Tests for Bug: Auto-align doesn't account for flip/scale transforms.

    Bug: When the AI frame has scale != 1.0 or flip enabled, the auto-align
    calculates offset based on the original (untransformed) image bbox,
    resulting in incorrect positioning.

    Note: Position values in tests are in display coordinates (DISPLAY_SCALE = 2).
    Logical offset = position / DISPLAY_SCALE.
    """

    def test_auto_align_accounts_for_scale(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align should calculate offset based on scaled content position.

        Bug: With scale=0.5, the visual content center is at half position,
        but offset is calculated as if scale=1.0.
        """
        from PIL import ImageDraw

        canvas = WorkbenchCanvas()
        display_scale = canvas._display_scale  # Use instance variable instead of constant
        qtbot.addWidget(canvas)

        # Create AI image with content NOT at origin (centered at 100, 100)
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))  # Transparent bg
        draw = ImageDraw.Draw(ai_img)
        # Draw content from (80, 80) to (120, 120) - center at (100, 100)
        draw.rectangle([80, 80, 120, 120], fill=(255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game frame preview (40x40, center at 20, 20)
        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (40, 40), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        mock_capture = create_simple_capture(width=40, height=40)

        game_frame = GameFrame(id="test_frame", width=40, height=40)

        # Setup canvas
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # Set alignment with scale=0.5 (AI frame will be visually 100x100)
        # At scale=0.5: content is at visual position (40, 40) to (60, 60)
        # Visual content center: (50, 50)
        # Game center: (20, 20)
        # Expected logical offset to align centers: (20 - 50, 20 - 50) = (-30, -30)
        canvas.set_alignment(0, 0, False, False, 0.5)

        # Trigger auto-align
        canvas._on_auto_align()

        # Get resulting offset
        # With scale=0.5, visual content center is at 0.5 * 100 = 50
        # Game center is at 20
        # Logical offset should be 20 - 50 = -30
        ai_pos = canvas._ai_frame_item.pos()

        # Position is in display coordinates (logical * display_scale)
        expected_logical_offset = -30
        expected_display_x = expected_logical_offset * display_scale
        expected_display_y = expected_logical_offset * display_scale

        assert abs(ai_pos.x() - expected_display_x) < 2, (
            f"Expected display offset_x ~{expected_display_x}, got {ai_pos.x()}. "
            "Auto-align may not be accounting for scale."
        )
        assert abs(ai_pos.y() - expected_display_y) < 2, (
            f"Expected display offset_y ~{expected_display_y}, got {ai_pos.y()}. "
            "Auto-align may not be accounting for scale."
        )

    def test_auto_align_accounts_for_flip_h(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align should calculate offset based on flipped content position.

        Bug: With flip_h=True, the visual content center mirrors,
        but offset is calculated as if not flipped.
        """
        from PIL import ImageDraw

        canvas = WorkbenchCanvas()
        display_scale = canvas._display_scale  # Use instance variable instead of constant
        qtbot.addWidget(canvas)

        # Create AI image with content on the LEFT side
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))  # Transparent bg
        draw = ImageDraw.Draw(ai_img)
        # Draw content from (10, 40) to (30, 60) - center at (20, 50)
        draw.rectangle([10, 40, 30, 60], fill=(255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game frame preview (40x40, center at 20, 20)
        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (40, 40), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        mock_capture = create_simple_capture(width=40, height=40)

        game_frame = GameFrame(id="test_frame", width=40, height=40)

        # Setup canvas
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # Set alignment with flip_h=True (content visually moves to right side)
        # Original content center: (20, 50)
        # After flip_h: visual center X = 100 - 20 = 80, Y = 50
        # Game center: (20, 20)
        # Expected logical offset: (20 - 80, 20 - 50) = (-60, -30)
        canvas.set_alignment(0, 0, True, False, 1.0)

        # Trigger auto-align
        canvas._on_auto_align()

        # Get resulting offset (in display coordinates)
        ai_pos = canvas._ai_frame_item.pos()

        expected_logical_x = -60  # 20 - 80 (flipped center)
        expected_logical_y = -30  # 20 - 50 (unchanged)
        expected_display_x = expected_logical_x * display_scale
        expected_display_y = expected_logical_y * display_scale

        # Allow small rounding tolerance (int conversion in offset calculation)
        assert abs(ai_pos.x() - expected_display_x) < 4, (
            f"Expected display offset_x ~{expected_display_x}, got {ai_pos.x()}. "
            "Auto-align may not be accounting for horizontal flip."
        )
        assert abs(ai_pos.y() - expected_display_y) < 4, (
            f"Expected display offset_y ~{expected_display_y}, got {ai_pos.y()}. "
            "Auto-align should not affect Y with only horizontal flip."
        )
