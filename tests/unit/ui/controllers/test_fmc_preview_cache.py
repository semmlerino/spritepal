"""Tests for FrameMappingController preview cache and game frame preview filtering.

Covers preview cache invalidation, file change detection, and filtering behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.frame_mapping_project import FrameMappingProject, GameFrame, SheetPalette
from tests.fixtures.frame_mapping_helpers import create_test_capture
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


class TestGetGameFramePreviewFiltering:
    """Tests for game frame preview generation respecting selected_entry_ids.

    Bug: Preview generation was rendering full capture instead of filtered
    entries per selected_entry_ids. Users saw all entries in preview but only
    selected entries got injected.
    """

    def test_game_frame_preview_respects_selected_entry_ids(self, tmp_path: Path, qtbot) -> None:
        """Preview pixmap must match render of filtered entries, not full capture.

        Creates entries at very different positions so the bounding box differs
        between full and filtered captures.
        """
        from core.mesen_integration import CaptureRenderer, MesenCaptureParser

        # Create capture with two entries at very different positions
        # Entry 0 at top-left, Entry 1 at bottom-right (far away)
        capture_data = create_test_capture([0, 1])
        capture_data["entries"][0]["x"] = 10
        capture_data["entries"][0]["y"] = 10
        capture_data["entries"][1]["x"] = 200  # Far right
        capture_data["entries"][1]["y"] = 200  # Far down

        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with project - select only entry 0 (top-left)
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[0],  # Only entry 0
            )
        )
        controller._project = project

        # Generate preview using force_regenerate
        preview = controller._preview_service.force_regenerate_preview("F001", project)
        assert preview is not None

        # Render what the filtered result SHOULD look like (returns tuple)
        filtered_result, _ = controller.get_capture_result_for_game_frame("F001")
        assert filtered_result is not None
        assert len(filtered_result.entries) == 1

        expected_renderer = CaptureRenderer(filtered_result)
        expected_img = expected_renderer.render_selection()

        # Also render full capture to show it's different
        parser = MesenCaptureParser()
        full_result = parser.parse_file(capture_path)
        full_renderer = CaptureRenderer(full_result)
        full_img = full_renderer.render_selection()

        # The preview dimensions should match filtered, not full
        # Full image spans from (10,10) to (200+8, 200+8) = large
        # Filtered image spans only (10,10) to (10+8, 10+8) = small
        assert full_img.width > expected_img.width, "Test setup: full should be wider"
        assert full_img.height > expected_img.height, "Test setup: full should be taller"

        # The actual assertion: preview must match filtered size
        assert preview.width() == expected_img.width, (
            f"Preview width {preview.width()} should match filtered {expected_img.width}, not full {full_img.width}"
        )
        assert preview.height() == expected_img.height, (
            f"Preview height {preview.height()} should match filtered {expected_img.height}, not full {full_img.height}"
        )

    def test_game_frame_preview_shows_all_when_no_selection(self, tmp_path: Path, qtbot) -> None:
        """Preview shows all entries when selected_entry_ids is empty."""
        from core.mesen_integration import CaptureRenderer

        # Create capture with entries at different positions
        capture_data = create_test_capture([0, 1, 2])
        capture_data["entries"][0]["x"] = 10
        capture_data["entries"][1]["x"] = 50
        capture_data["entries"][2]["x"] = 100

        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[],  # Empty = show all
            )
        )
        controller._project = project

        # Generate preview
        preview = controller._preview_service.force_regenerate_preview("F001", project)
        assert preview is not None

        # Get capture result (unfiltered, returns tuple)
        full_result, _ = controller.get_capture_result_for_game_frame("F001")
        assert full_result is not None
        assert len(full_result.entries) == 3

        # Render expected
        expected_renderer = CaptureRenderer(full_result)
        expected_img = expected_renderer.render_selection()

        # Preview should span all entries
        assert preview.width() == expected_img.width
        assert preview.height() == expected_img.height

    def test_preview_cached_after_first_request(self, tmp_path: Path, qtbot) -> None:
        """Preview is cached and subsequent requests don't re-render."""
        capture_data = create_test_capture([0, 1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[1],
            )
        )
        controller._project = project

        # First request - generate
        preview1 = controller._preview_service.force_regenerate_preview("F001", project)
        # Second request should return same object (cached)
        preview2 = controller.get_cached_game_frame_preview("F001")

        assert preview1 is not None
        # Same object returned from cache
        assert preview1 is preview2


class TestPreviewCacheInvalidation:
    """Tests for Bug #5: Preview cache never invalidates.

    The cache should check file mtime and regenerate if the source file changed.
    """

    def test_preview_cache_invalidates_on_file_change(self, tmp_path: Path, qtbot) -> None:
        """Preview regenerates when source capture file is modified."""
        import time

        # Create initial capture
        capture_data = create_test_capture([0, 1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        game_frame = GameFrame(
            id="F001",
            capture_path=capture_path,
            selected_entry_ids=[0, 1],
        )
        project.add_game_frame(game_frame)
        controller._project = project

        # First request caches the preview
        preview1 = controller._preview_service.force_regenerate_preview("F001", project)
        assert preview1 is not None

        # Ensure mtime changes (some filesystems have second-level precision)
        time.sleep(0.1)

        # Modify the capture file
        capture_data2 = create_test_capture([0, 1, 2])  # Add a third entry
        capture_path.write_text(json.dumps(capture_data2))

        # Update cached_mtime to trigger invalidation
        game_frame.cached_mtime = capture_path.stat().st_mtime

        # Cached preview should be invalid now
        cached = controller.get_cached_game_frame_preview("F001")
        assert cached is None, "Cache should be invalid after file change"

        # Regenerate
        preview2 = controller._preview_service.force_regenerate_preview("F001", project)
        assert preview2 is not None

        # Should be different pixmap objects (regenerated)
        assert preview1 is not preview2

    def test_preview_cache_returns_cached_if_file_unchanged(self, tmp_path: Path, qtbot) -> None:
        """Preview returns cached pixmap when file hasn't changed."""
        capture_data = create_test_capture([0, 1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[0, 1],
            )
        )
        controller._project = project

        # First request - generate
        preview1 = controller._preview_service.force_regenerate_preview("F001", project)
        # Second request should return same cached object
        preview2 = controller.get_cached_game_frame_preview("F001")

        assert preview1 is not None
        assert preview1 is preview2  # Same object from cache

    def test_preview_cache_returns_cached_if_no_file(self, tmp_path: Path, qtbot) -> None:
        """Preview returns cached pixmap when capture_path is None."""
        from PySide6.QtGui import QPixmap

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=None,  # No file
                selected_entry_ids=[],
            )
        )
        controller._project = project

        # Manually add a preview to the cache via service
        cached_pixmap = QPixmap(10, 10)
        # Cache stores (pixmap, mtime, entry_ids) - use 0.0 mtime and empty tuple for no-file case
        controller._preview_service.set_preview_cache("F001", cached_pixmap, 0.0, ())

        # Should return cached even with no file to compare
        preview = controller.get_cached_game_frame_preview("F001")
        assert preview is cached_pixmap

    def test_preview_cache_returns_cached_if_file_deleted(self, tmp_path: Path, qtbot) -> None:
        """Preview returns cached pixmap when file has been deleted."""
        capture_data = create_test_capture([0, 1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[0, 1],
            )
        )
        controller._project = project

        # First request caches the preview
        preview1 = controller._preview_service.force_regenerate_preview("F001", project)
        assert preview1 is not None

        # Delete the source file
        capture_path.unlink()

        # Should return cached since file doesn't exist anymore
        preview2 = controller.get_cached_game_frame_preview("F001")
        assert preview2 is preview1


class TestPreviewCacheInvalidationOnPaletteChange:
    """Tests for BUG-2 fix: preview cache invalidation when palette changes.

    Note: As of Phase 4 performance optimization, palette changes call
    mark_all_stale() instead of invalidate_all() for deferred regeneration.
    """

    def test_preview_cache_marked_stale_on_palette_set(self, qtbot) -> None:
        """Setting sheet palette marks preview cache as stale."""
        controller = FrameMappingController()
        controller.new_project()

        # Spy on the mark_all_stale method
        stale_calls: list[bool] = []
        original_mark_stale = controller._preview_service.mark_all_stale

        def spy_mark_stale() -> None:
            stale_calls.append(True)
            original_mark_stale()

        controller._preview_service.mark_all_stale = spy_mark_stale

        # Set a palette
        colors = [(0, 0, 0)] * 16
        palette = SheetPalette(colors=colors)
        controller.set_sheet_palette(palette)

        # Preview cache should have been marked stale
        assert len(stale_calls) == 1

    def test_preview_cache_marked_stale_on_palette_color_change(self, qtbot) -> None:
        """Changing a single palette color marks preview cache as stale."""
        controller = FrameMappingController()
        controller.new_project()

        # Set initial palette
        colors = [(0, 0, 0)] * 16
        palette = SheetPalette(colors=colors)
        controller.set_sheet_palette(palette)

        # Spy on mark_all_stale after initial set
        stale_calls: list[bool] = []
        original_mark_stale = controller._preview_service.mark_all_stale

        def spy_mark_stale() -> None:
            stale_calls.append(True)
            original_mark_stale()

        controller._preview_service.mark_all_stale = spy_mark_stale

        # Change a single color
        controller.set_sheet_palette_color(5, (255, 0, 0))

        # Preview cache should have been marked stale
        assert len(stale_calls) == 1

    def test_preview_cache_marked_stale_on_palette_clear(self, qtbot) -> None:
        """Clearing the sheet palette marks preview cache as stale."""
        controller = FrameMappingController()
        controller.new_project()

        # Set initial palette
        colors = [(0, 0, 0)] * 16
        palette = SheetPalette(colors=colors)
        controller.set_sheet_palette(palette)

        # Spy on mark_all_stale after initial set
        stale_calls: list[bool] = []
        original_mark_stale = controller._preview_service.mark_all_stale

        def spy_mark_stale() -> None:
            stale_calls.append(True)
            original_mark_stale()

        controller._preview_service.mark_all_stale = spy_mark_stale

        # Clear palette
        controller.set_sheet_palette(None)

        # Preview cache should have been marked stale
        assert len(stale_calls) == 1
