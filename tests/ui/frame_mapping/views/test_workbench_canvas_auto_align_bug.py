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
        class MockBoundingBox:
            x = 0
            y = 0
            width = 32
            height = 32

        class MockCaptureResult:
            entries: list[object] = []
            palettes: dict[int, object] = {}
            bounding_box = MockBoundingBox()

        game_frame = GameFrame(id="test_frame", width=32, height=32)

        # Set game frame with capture result (has what auto-align needs from game side)
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=MockCaptureResult(),  # type: ignore[arg-type]
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
        class MockBoundingBox:
            x = 0
            y = 0
            width = 32
            height = 32

        class MockCaptureResult:
            entries: list[object] = []
            palettes: dict[int, object] = {}
            bounding_box = MockBoundingBox()

        game_frame = GameFrame(id="test_frame", width=32, height=32)

        # Set both frames with valid data
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=MockCaptureResult(),  # type: ignore[arg-type]
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

        class MockBoundingBox:
            x = 0
            y = 0
            width = 32
            height = 32

        class MockCaptureResult:
            entries: list[object] = []
            palettes: dict[int, object] = {}
            bounding_box = MockBoundingBox()

        game_frame = GameFrame(id="test_frame", width=32, height=32)
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=MockCaptureResult(),  # type: ignore[arg-type]
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

        class MockBoundingBox:
            x = 0
            y = 0
            width = 32
            height = 32

        class MockCaptureResult:
            entries: list[object] = []
            palettes: dict[int, object] = {}
            bounding_box = MockBoundingBox()

        game_frame = GameFrame(id="test_frame", width=32, height=32)
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=MockCaptureResult(),  # type: ignore[arg-type]
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

        class MockBoundingBox:
            x = 0
            y = 0
            width = 32
            height = 32

        class MockCaptureResult:
            entries: list[object] = []
            palettes: dict[int, object] = {}
            bounding_box = MockBoundingBox()

        game_frame = GameFrame(id="test_frame", width=32, height=32)
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=MockCaptureResult(),  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))
        canvas.set_alignment(0, 0, False, False, 1.0)

        # Button should be enabled
        assert canvas._auto_align_btn.isEnabled(), "Pre-condition: button should be enabled"

        # Clear game frame
        canvas.set_game_frame(frame=None)

        # Button should now be disabled (no capture result)
        assert not canvas._auto_align_btn.isEnabled(), "Button should be disabled after game frame cleared"
