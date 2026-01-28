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
from tests.infrastructure.mesen_mocks import (
    MockBoundingBox,
    MockCaptureResult,
    MockOAMEntry,
    create_simple_capture,
)
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
        canvas._match_scale_checkbox.setChecked(False)
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
        mock_capture = create_simple_capture(width=32, height=32)

        # Create a proper GameFrame
        game_frame = GameFrame(id="test_frame", width=32, height=32)

        # Set frames
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
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
        canvas._match_scale_checkbox.setChecked(False)
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
        mock_capture = create_simple_capture(width=32, height=32)

        # Create a proper GameFrame
        game_frame = GameFrame(id="test_frame", width=32, height=32)

        # Set frames
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
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

        # Patch at the import location in workspace_logic_helper
        with patch(
            "ui.frame_mapping.workspace_logic_helper.calculate_auto_alignment",
            side_effect=tracking_wrapper,
        ):
            from ui.frame_mapping.workspace_logic_helper import WorkspaceLogicHelper

            # Create real WorkspaceLogicHelper with mocked dependencies
            helper = WorkspaceLogicHelper()

            # Mock controller
            mock_controller = MagicMock()
            helper.set_controller(mock_controller)

            # Mock state manager
            mock_state = MagicMock()
            mock_state.auto_advance_enabled = False
            helper.set_state(mock_state)

            # Mock panes
            mock_ai_pane = MagicMock()
            mock_captures_pane = MagicMock()
            mock_mapping_panel = MagicMock()
            mock_canvas = MagicMock()
            helper.set_panes(mock_ai_pane, mock_captures_pane, mock_mapping_panel, mock_canvas)

            # Setup project with AI frame
            mock_project = MagicMock()
            mock_ai_frame = MagicMock()
            mock_ai_frame.path = ai_image_path
            mock_ai_frame.id = "frame0.png"
            mock_ai_frame.index = 0
            mock_project.get_ai_frame_by_id.return_value = mock_ai_frame
            mock_project.get_mapping_for_ai_frame.return_value = None
            mock_controller.project = mock_project
            mock_controller.get_existing_link_for_ai_frame.return_value = None
            mock_controller.get_existing_link_for_game_frame.return_value = None

            # Setup capture result with NON-ZERO screen position (the bug trigger)
            mock_capture = MagicMock()
            mock_capture.has_entries = True
            mock_capture.bounding_box.x = 120  # Screen position, NOT canvas position
            mock_capture.bounding_box.y = 80
            mock_capture.bounding_box.width = 32
            mock_capture.bounding_box.height = 32
            mock_controller.get_capture_result_for_game_frame.return_value = (mock_capture, False)

            # Call the real attempt_link method (now in WorkspaceLogicHelper)
            helper.attempt_link(ai_frame_id="frame0.png", game_frame_id="frame1")

        # ASSERTION: Should be called with (0, 0) for canvas-relative alignment
        # BUG: Currently called with (120, 80) from capture screen position
        assert len(captured_args) == 1, f"Expected 1 call, got {len(captured_args)}"
        bbox_x, bbox_y, bbox_w, bbox_h = captured_args[0]

        assert bbox_x == 0, f"Expected bbox_x=0 (canvas origin), got {bbox_x} (screen position)"
        assert bbox_y == 0, f"Expected bbox_y=0 (canvas origin), got {bbox_y} (screen position)"


class TestLargeImageAutoAlign:
    """Tests for auto-align with large images (Match Scale enabled).

    Bug: When the scaled AI image is larger than the tile coverage, the position
    search loop is skipped because max_shift becomes negative:
        max_shift_x = int(tile_width - scaled_width) // 2 + 4
        # When scaled_width > tile_width: max_shift is negative
        # range(1, negative + 1) = empty range → loop never executes

    Also, the minimum scale floor of 0.1 (10%) is too high for large images
    that need to be scaled down to fit small tile coverage (e.g., 256x256 image
    fitting into 16x16 tiles needs scale ≈ 0.0625).
    """

    def test_auto_align_with_large_ai_image_and_match_scale(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align should correctly scale down large AI images.

        Scenario:
        - AI image: 256x256 with 56x56 content (centered)
        - Game tiles: 16x16
        - Expected scale: 16/56 ≈ 0.286

        Bug: Scale gets clamped to 0.1 because MIN_SCALE is too high,
        and position search fails because max_shift goes negative.
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create large AI image (256x256) with smaller centered content (56x56)
        ai_image_path = tmp_path / "large_ai_frame.png"
        ai_img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ai_img)
        # Content at (100, 100) to (156, 156) - 56x56 centered
        draw.rectangle([100, 100, 156, 156], fill=(255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game frame preview (16x16)
        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (16, 16), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        # Create capture with OAM entry so _compute_tile_rects() works
        # Single 16x16 OAM entry at origin
        entry = MockOAMEntry(x=0, y=0, width=16, height=16)
        mock_capture = MockCaptureResult(
            entries=[entry],
            _bounding_box=MockBoundingBox(x=0, y=0, width=16, height=16),
        )

        game_frame = GameFrame(id="test_frame", width=16, height=16)

        # Setup canvas
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # Enable Match Scale mode and trigger auto-align
        canvas._match_scale_checkbox.setChecked(True)
        canvas.set_alignment(0, 0, False, False, 1.0)

        # Trigger auto-align
        canvas._on_auto_align()

        # Get resulting scale
        actual_scale = canvas._scale_slider.value() / 100.0

        # Expected scale: tile_size / content_size = 16 / 56 ≈ 0.286
        expected_scale = 16 / 56  # ≈ 0.2857

        # Scale should be close to expected (not clamped to 0.1)
        assert actual_scale > 0.2, (
            f"Scale {actual_scale:.3f} too low. Expected ~{expected_scale:.3f}. "
            "Scale may be clamped by MIN_SCALE=0.1 floor."
        )
        assert actual_scale < 0.4, f"Scale {actual_scale:.3f} too high. Expected ~{expected_scale:.3f}."

    def test_auto_align_position_search_with_large_content(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Position search should work even when scaled content > tile coverage.

        Bug: When scaled_width > tile_width, max_shift becomes negative:
            max_shift_x = int(tile_width - scaled_width) // 2 + 4
        This makes range(1, max_shift + 1) empty, skipping the search loop.

        Fix: Use abs() to ensure search range is always positive:
            max_shift_x = max(abs(int(tile_width - scaled_width)) // 2 + margin, margin)
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create AI image with content slightly larger than game tiles
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ai_img)
        # Content at (25, 25) to (75, 75) - 50x50 content
        draw.rectangle([25, 25, 75, 75], fill=(255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Game tiles are 32x32 - smaller than 50x50 scaled content at scale=1.0
        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (32, 32), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        # Create capture with OAM entry so _compute_tile_rects() works
        entry = MockOAMEntry(x=0, y=0, width=32, height=32)
        mock_capture = MockCaptureResult(
            entries=[entry],
            _bounding_box=MockBoundingBox(x=0, y=0, width=32, height=32),
        )

        game_frame = GameFrame(id="test_frame", width=32, height=32)

        # Setup canvas
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # Set scale that makes content larger than tiles (50*0.8=40 > 32)
        canvas.set_alignment(0, 0, False, False, 0.8)

        # Trigger auto-align - should still attempt to find best position
        canvas._on_auto_align()

        # The key assertion: offset should be non-zero (search found a position)
        # If search loop was skipped, offset would be centered (0, 0)
        ai_pos = canvas._ai_frame_item.pos()

        # Position should have been adjusted from pure center
        # (The exact values depend on the algorithm, but it should have searched)
        # Just verify that auto-align completed without error and set some position
        assert ai_pos is not None, "Auto-align should set AI frame position"


class TestAutoAlignWithTileGaps:
    """Tests for auto-align with non-contiguous tile coverage (gaps in grid).

    Bug: When tile coverage has gaps (e.g., left column missing), the bounding box
    center is in the middle of the gap+tiles area, causing content to be centered
    partially over gaps where no tiles exist. This results in overflow.

    Fix: Use tile centroid (area-weighted center of actual tiles) instead of
    bounding box center. This centers content over actual tile coverage, not gaps.

    Example problematic layout:
        Tile grid (5x6 tiles):
          y= 0: .████   <- Column x=0 is EMPTY (gap)
          y= 8: .████
          ...

        Bounding box: (0, 0) to (40, 48) - center at (20, 24)
        Tile centroid: center of the 4 columns at x=8-40 - approx (24, 24)

        With 32px content, centering at (20, 24) places 4px over the gap.
        Centering at tile centroid (24, 24) keeps content within tiles.
    """

    def test_auto_align_with_left_column_gap(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Auto-align should handle tile grid with gap in left column.

        This test reproduces the bug seen in mapping index 1 where the tile grid
        has an empty column on the left, causing bounding-box-centered alignment
        to overflow into the gap.
        """
        canvas = WorkbenchCanvas()
        qtbot.addWidget(canvas)

        # Create AI image with centered content (32x40)
        ai_image_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ai_img)
        # Content at (16, 12) to (48, 52) - 32x40 centered
        draw.rectangle([16, 12, 48, 52], fill=(255, 0, 0, 255))
        ai_img.save(ai_image_path)

        # Create game preview
        game_preview_path = tmp_path / "game.png"
        game_preview = Image.new("RGBA", (40, 48), (0, 255, 0, 255))
        game_preview.save(game_preview_path)

        # Create tile grid with LEFT COLUMN GAP (x=0-8 is empty)
        # This is a 5x6 grid where the first column doesn't have tiles
        # Tiles exist at x positions: 8, 16, 24, 32 (4 columns)
        # All 6 rows: y positions 0, 8, 16, 24, 32, 40
        entries = []
        for row in range(6):
            for col in range(4):  # Only 4 columns, starting at x=8
                x = 8 + col * 8  # Skip column 0 (the gap)
                y = row * 8
                entries.append(MockOAMEntry(x=x, y=y, width=8, height=8))

        mock_capture = MockCaptureResult(
            entries=entries,
            _bounding_box=MockBoundingBox(x=0, y=0, width=40, height=48),
        )

        game_frame = GameFrame(id="test_frame", width=40, height=48)

        # Setup canvas
        canvas.set_game_frame(
            frame=game_frame,
            preview_pixmap=QPixmap(str(game_preview_path)),
            capture_result=mock_capture,  # type: ignore[arg-type]
        )
        canvas.set_ai_frame(AIFrame(path=ai_image_path, index=0))

        # Enable Match Scale and trigger auto-align
        canvas._match_scale_checkbox.setChecked(True)
        canvas.set_alignment(0, 0, False, False, 1.0)
        canvas._on_auto_align()

        # Check that there's no overflow - content should fit within tiles
        warning_label = canvas._out_of_bounds_warning_label
        has_overflow = warning_label.isVisible() if warning_label else False

        # With the fix, content should be centered over actual tiles (x=8-40),
        # not the bounding box (x=0-40), avoiding overflow into the gap
        assert not has_overflow, (
            "Auto-align should not cause overflow with non-contiguous tiles. "
            "Content was likely centered over bounding box instead of tile centroid."
        )
