"""Tests for WorkbenchCanvas alignment controls state management.

Bug #2: clear_alignment() sets _has_mapping=False then calls set_alignment()
which unconditionally sets _has_mapping=True, re-enabling controls incorrectly.

Bug #3: Auto-align makes both frames disappear by moving AI frame outside scene rect.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw
from PySide6.QtGui import QPixmap

from core.frame_mapping_project import AIFrame, GameFrame
from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestAlignmentControlsState:
    """Tests for Bug #2: alignment controls enabled without mapping."""

    def test_clear_alignment_disables_controls(self, qtbot: QtBot) -> None:
        """clear_alignment must leave controls disabled."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # First set a mapping to enable controls
        canvas.set_alignment(10, 20, True, False, 1.5)
        assert canvas._has_mapping is True
        assert canvas._flip_h_checkbox.isEnabled()
        assert canvas._flip_v_checkbox.isEnabled()
        assert canvas._scale_slider.isEnabled()

        # Now clear alignment - controls should be disabled
        canvas.clear_alignment()

        assert canvas._has_mapping is False
        assert not canvas._flip_h_checkbox.isEnabled()
        assert not canvas._flip_v_checkbox.isEnabled()
        assert not canvas._scale_slider.isEnabled()

    def test_clear_alignment_resets_values_to_defaults(self, qtbot: QtBot) -> None:
        """clear_alignment should reset values to defaults while keeping controls disabled."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Set non-default values
        canvas.set_alignment(50, -30, True, True, 2.0)

        # Clear should reset to 0,0 no-flip 1.0x
        canvas.clear_alignment()

        # Values should be reset
        assert canvas._flip_h_checkbox.isChecked() is False
        assert canvas._flip_v_checkbox.isChecked() is False
        assert canvas._scale_slider.value() == 100  # 1.0x
        # Controls should still be disabled
        assert canvas._has_mapping is False

    def test_set_alignment_enables_controls(self, qtbot: QtBot) -> None:
        """set_alignment (normal call) should enable controls."""
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Initially no mapping
        assert canvas._has_mapping is False
        assert not canvas._flip_h_checkbox.isEnabled()

        # Set alignment should enable
        canvas.set_alignment(0, 0, False, False, 1.0)

        assert canvas._has_mapping is True
        assert canvas._flip_h_checkbox.isEnabled()
        assert canvas._flip_v_checkbox.isEnabled()
        assert canvas._scale_slider.isEnabled()


class TestAutoAlignVisibility:
    """Tests for Bug #3: Auto-align moves frames outside visible area."""

    def test_auto_align_keeps_frames_visible(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align should keep both frames visible (regression test).

        Bug: Auto-align moves AI frame outside scene rect, making frames disappear.
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create AI image with content NOT at origin (typical case)
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ai_img)
        draw.rectangle([100, 100, 150, 150], fill=(255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game frame preview (32x32)
        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (32, 32), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        # Mock capture result with 32x32 bbox
        class MockBoundingBox:
            x = 0
            y = 0
            width = 32
            height = 32

        class MockCaptureResult:
            entries: list[object] = []
            palettes: dict[int, object] = {}
            bounding_box = MockBoundingBox()

        # Create a proper GameFrame
        game_frame = GameFrame(id="test_frame", width=32, height=32)

        # Set frames
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=MockCaptureResult(),  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # Trigger auto-align
        canvas._on_auto_align()

        # Verify: Both frames should be within scene rect
        scene_rect = canvas._view.sceneRect()
        ai_rect = canvas._ai_frame_item.sceneBoundingRect()
        game_rect = canvas._game_frame_item.sceneBoundingRect()

        assert scene_rect.intersects(ai_rect), "AI frame moved outside scene"
        assert scene_rect.intersects(game_rect), "Game frame not in scene"

    def test_auto_align_frames_in_viewport(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align should show both frames in the actual viewport (not just scene rect).

        Bug: centerOn() doesn't scroll the view properly when scroll bars are hidden
        and the viewport is smaller than the scene. fitInView() is needed instead.
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)
        # Give the canvas a realistic size (smaller than typical AI images)
        canvas.resize(400, 300)
        canvas.show()
        qtbot.wait(50)  # Allow layout to settle

        # Create AI image with content NOT at origin (typical case)
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ai_img)
        draw.rectangle([100, 100, 150, 150], fill=(255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game frame preview (32x32)
        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (32, 32), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        # Mock capture result with 32x32 bbox
        class MockBoundingBox:
            x = 0
            y = 0
            width = 32
            height = 32

        class MockCaptureResult:
            entries: list[object] = []
            palettes: dict[int, object] = {}
            bounding_box = MockBoundingBox()

        # Create a proper GameFrame
        game_frame = GameFrame(id="test_frame", width=32, height=32)

        # Set frames
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=MockCaptureResult(),  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # Trigger auto-align
        canvas._on_auto_align()
        qtbot.wait(50)  # Allow event processing

        # Verify: mapped viewport should contain both frame centers
        viewport_rect = canvas._view.mapToScene(canvas._view.viewport().rect()).boundingRect()
        game_center = canvas._game_frame_item.sceneBoundingRect().center()
        ai_center = canvas._ai_frame_item.sceneBoundingRect().center()

        assert viewport_rect.contains(game_center), f"Game frame center {game_center} not in viewport {viewport_rect}"
        assert viewport_rect.contains(ai_center), f"AI frame center {ai_center} not in viewport {viewport_rect}"


class TestAutoAlignCoordinates:
    """Tests for Bug #4: Initial auto-align uses wrong bounding box coordinates.

    Bug: _attempt_link() passes capture bounding box x,y (screen coordinates)
    to calculate_auto_alignment(), but the canvas displays the game frame at (0,0).
    This causes large incorrect offsets when the capture position != (0,0).

    The fix: Always use (0, 0) for game_bbox_x/y since that's where the game frame
    is displayed on the canvas.
    """

    def test_auto_alignment_uses_canvas_origin_not_capture_position(self, tmp_path: Path) -> None:
        """Auto-alignment should calculate offset relative to canvas origin (0,0).

        When a sprite is captured at screen position (120, 80), the bounding box
        will have x=120, y=80. But on the canvas, the game frame is always displayed
        at (0, 0). The alignment offset must be calculated relative to (0, 0).

        This test FAILS until _attempt_link is fixed to use (0, 0) instead of bbox.x/y.
        """
        from unittest.mock import MagicMock, patch

        from core.services.tile_sampling_service import calculate_auto_alignment

        # Create AI image with content at (100, 100) to (150, 150)
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ai_img)
        draw.rectangle([100, 100, 150, 150], fill=(255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Track what coordinates are passed to calculate_auto_alignment
        captured_args: list[tuple[int, int, int, int]] = []
        original_func = calculate_auto_alignment

        def tracking_wrapper(
            ai_image: Image.Image,
            game_bbox_x: int,
            game_bbox_y: int,
            game_bbox_width: int,
            game_bbox_height: int,
        ) -> tuple[int, int]:
            captured_args.append((game_bbox_x, game_bbox_y, game_bbox_width, game_bbox_height))
            return original_func(ai_image, game_bbox_x, game_bbox_y, game_bbox_width, game_bbox_height)

        # Patch at the import location in frame_mapping_workspace
        with patch(
            "ui.workspaces.frame_mapping_workspace.calculate_auto_alignment",
            side_effect=tracking_wrapper,
        ):
            from ui.workspaces.frame_mapping_workspace import FrameMappingWorkspace

            # Create minimal workspace with mocked controller
            workspace = MagicMock(spec=FrameMappingWorkspace)
            workspace._controller = MagicMock()
            workspace._message_service = None
            workspace._auto_advance_enabled = False
            workspace._alignment_canvas = MagicMock()

            # Setup project with AI frame
            mock_project = MagicMock()
            mock_ai_frame = MagicMock()
            mock_ai_frame.path = ai_image_path
            mock_ai_frame.id = "frame0.png"
            mock_ai_frame.index = 0
            mock_project.get_ai_frame_by_id.return_value = mock_ai_frame
            mock_project.get_mapping_for_ai_frame.return_value = None
            workspace._controller.project = mock_project
            workspace._controller.get_existing_link_for_ai_frame.return_value = None
            workspace._controller.get_existing_link_for_game_frame.return_value = None

            # Setup capture result with NON-ZERO screen position (the bug trigger)
            mock_capture = MagicMock()
            mock_capture.has_entries = True
            mock_capture.bounding_box.x = 120  # Screen position, NOT canvas position
            mock_capture.bounding_box.y = 80
            mock_capture.bounding_box.width = 32
            mock_capture.bounding_box.height = 32
            workspace._controller.get_capture_result_for_game_frame.return_value = (mock_capture, False)

            # Call the real _attempt_link method
            FrameMappingWorkspace._attempt_link(workspace, ai_frame_id="frame0.png", game_frame_id="frame1")

        # ASSERTION: Should be called with (0, 0) for canvas-relative alignment
        # BUG: Currently called with (120, 80) from capture screen position
        assert len(captured_args) == 1, f"Expected 1 call, got {len(captured_args)}"
        bbox_x, bbox_y, bbox_w, bbox_h = captured_args[0]

        assert bbox_x == 0, f"Expected bbox_x=0 (canvas origin), got {bbox_x} (screen position)"
        assert bbox_y == 0, f"Expected bbox_y=0 (canvas origin), got {bbox_y} (screen position)"
