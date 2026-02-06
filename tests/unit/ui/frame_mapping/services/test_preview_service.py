"""Tests for PreviewService."""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtGui import QImage, QPixmap

from core.frame_mapping_project import FrameMappingProject, GameFrame
from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import CaptureResult, OAMEntry
from core.repositories.capture_result_repository import CaptureResultRepository
from tests.fixtures.timeouts import signal_timeout
from ui.frame_mapping.services.preview_service import PreviewService


@pytest.fixture
def preview_service(qtbot):
    """Create a PreviewService instance."""
    capture_repository = CaptureResultRepository()
    service = PreviewService(capture_repository=capture_repository)
    return service


@pytest.fixture
def mock_project(tmp_path):
    """Create a mock project with game frames."""
    project = Mock(spec=FrameMappingProject)

    # Create a test capture file
    capture_path = tmp_path / "test_capture.json"
    capture_path.write_text('{"frame": 100, "entries": []}')

    # Mock game frame
    game_frame = Mock(spec=GameFrame)
    game_frame.id = "frame1"
    game_frame.capture_path = capture_path
    game_frame.selected_entry_ids = [1, 2, 3]
    game_frame.rom_offsets = frozenset([0x12345, 0x67890])
    game_frame.cached_mtime = 0.0  # Initialize cached_mtime for the new field

    project.get_game_frame_by_id.return_value = game_frame

    return project, game_frame


@pytest.fixture
def mock_capture_result():
    """Create a mock CaptureResult with entries."""
    entry1 = Mock(spec=OAMEntry)
    entry1.id = 1
    entry1.rom_offset = 0x12345
    entry1.palette = 0

    entry2 = Mock(spec=OAMEntry)
    entry2.id = 2
    entry2.rom_offset = 0x12345
    entry2.palette = 0

    entry3 = Mock(spec=OAMEntry)
    entry3.id = 3
    entry3.rom_offset = 0x67890
    entry3.palette = 1

    capture = Mock(spec=CaptureResult)
    capture.has_entries = True
    capture.entries = [entry1, entry2, entry3]
    capture.frame = 100
    capture.visible_count = 3
    capture.obsel = 0
    capture.palettes = []
    capture.timestamp = "2026-01-24"

    return capture


@dataclass
class RenderingPatchContext:
    """Provides pre-configured rendering pipeline patches for preview service tests."""

    mock_get_or_parse: MagicMock
    mock_renderer_class: MagicMock
    mock_renderer_inst: MagicMock
    mock_pil_to_qimage: MagicMock
    _qimage: QImage = field(default_factory=lambda: QImage(100, 100, QImage.Format.Format_RGBA8888))

    def set_qimage(self, width: int, height: int) -> None:
        """Set custom QImage dimensions for this test."""
        self._qimage = QImage(width, height, QImage.Format.Format_RGBA8888)
        self.mock_pil_to_qimage.return_value = self._qimage


@pytest.fixture
def rendering_patches(preview_service, mock_capture_result):
    """Apply the 3-layer rendering pipeline patches and yield a context object.

    Patches:
    - capture_repository.get_or_parse → returns mock_capture_result
    - CaptureRenderer → returns mock with render_selection
    - pil_to_qimage → returns QImage(100, 100)
    """
    with patch.object(
        preview_service._capture_repository, "get_or_parse", return_value=mock_capture_result
    ) as mock_get_or_parse:
        with patch("ui.frame_mapping.services.preview_renderer.CaptureRenderer") as MockRenderer:
            renderer_inst = MockRenderer.return_value
            mock_pil_img = Mock()
            renderer_inst.render_selection.return_value = mock_pil_img

            with patch("ui.frame_mapping.services.preview_renderer.pil_to_qimage") as mock_pil_to_qimage:
                qimage = QImage(100, 100, QImage.Format.Format_RGBA8888)
                mock_pil_to_qimage.return_value = qimage

                yield RenderingPatchContext(
                    mock_get_or_parse=mock_get_or_parse,
                    mock_renderer_class=MockRenderer,
                    mock_renderer_inst=renderer_inst,
                    mock_pil_to_qimage=mock_pil_to_qimage,
                    _qimage=qimage,
                )


class TestPreviewServiceCaching:
    """Test preview cache hit/miss behavior."""

    def test_cache_miss_generates_preview(self, preview_service, mock_project, rendering_patches, qtbot):
        """Test that cache miss generates preview from capture file."""
        project, game_frame = mock_project

        # First call - cache miss (should return None)
        result = preview_service.get_cached_preview("frame1", project)
        assert result is None, "Cache miss should return None"

        # Generate preview via force_regenerate_preview
        result = preview_service.force_regenerate_preview("frame1", project)

        # Verify result type and content
        expected_width, expected_height = 100, 100
        assert result is not None
        assert isinstance(result, QPixmap)
        assert result.width() == expected_width, "Returned pixmap should have expected width"
        assert result.height() == expected_height, "Returned pixmap should have expected height"

        # Verify rendering pipeline was invoked
        rendering_patches.mock_get_or_parse.assert_called_once()
        rendering_patches.mock_renderer_class.assert_called_once()

        # Verify cache was populated (this is the key verification)
        assert "frame1" in preview_service._game_frame_previews, "Preview should be cached"
        cached_pixmap, cached_mtime, cached_entry_ids = preview_service._game_frame_previews["frame1"]
        assert cached_pixmap is result, "Cached pixmap should be the same as returned"

    def test_cache_hit_returns_cached_pixmap(self, preview_service, mock_project, rendering_patches, qtbot):
        """Test that cache hit returns cached pixmap without regeneration."""
        project, game_frame = mock_project

        # First call - generate and cache
        result1 = preview_service.force_regenerate_preview("frame1", project)

        # Second call - cache hit
        result2 = preview_service.get_cached_preview("frame1", project)

        assert result1 == result2
        # Repository should only be called once (first time)
        assert rendering_patches.mock_get_or_parse.call_count == 1

    def test_mtime_change_invalidates_cache(self, preview_service, mock_project, rendering_patches, qtbot, tmp_path):
        """Test that file mtime change invalidates cache."""
        project, game_frame = mock_project

        # Create actual file to get real mtime
        capture_path = tmp_path / "test_capture.json"
        capture_path.write_text('{"frame": 100}')
        game_frame.capture_path = capture_path

        # First call - cache population
        preview_service.force_regenerate_preview("frame1", project)

        # Ensure mtime actually changes (some filesystems have 1-second resolution)
        import os

        original_mtime = capture_path.stat().st_mtime
        # Explicitly set mtime to 1 second in the future to guarantee change
        new_mtime = original_mtime + 1.0
        capture_path.write_text('{"frame": 101}')
        os.utime(capture_path, (new_mtime, new_mtime))
        # Update cached_mtime to simulate detection of file change
        # (In production, this would happen via file watcher or manual refresh)
        game_frame.cached_mtime = new_mtime

        # Second call - cache invalidated due to mtime change (returns None)
        cached = preview_service.get_cached_preview("frame1", project)
        assert cached is None, "Cache should be invalid after mtime change"

        # Force regeneration
        preview_service.force_regenerate_preview("frame1", project)

        # Repository called twice (cache invalidated)
        assert rendering_patches.mock_get_or_parse.call_count == 2

    def test_entry_ids_change_invalidates_cache(self, preview_service, mock_project, rendering_patches, qtbot):
        """Test that entry IDs change invalidates cache."""
        project, game_frame = mock_project

        # First call - generate and cache
        preview_service.force_regenerate_preview("frame1", project)

        # Change selected entry IDs
        game_frame.selected_entry_ids = [1, 2]  # Changed from [1, 2, 3]

        # Second call - cache invalidated due to entry ID change (returns None)
        cached = preview_service.get_cached_preview("frame1", project)
        assert cached is None, "Cache should be invalid after entry ID change"

        # Force regeneration
        preview_service.force_regenerate_preview("frame1", project)

        # Repository called twice (cache invalidated)
        assert rendering_patches.mock_get_or_parse.call_count == 2


class TestPreviewServiceInvalidation:
    """Test cache invalidation methods."""

    def test_invalidate_single_entry(self, preview_service):
        """Test invalidating a single cache entry."""
        # Manually add cache entry
        mock_pixmap = QPixmap(100, 100)
        preview_service.set_preview_cache("frame1", mock_pixmap, 0.0, (1, 2, 3))

        # Verify cached
        assert "frame1" in preview_service._game_frame_previews

        # Invalidate
        preview_service.invalidate("frame1")

        assert "frame1" not in preview_service._game_frame_previews

    def test_invalidate_nonexistent_entry(self, preview_service):
        """Test that invalidating nonexistent entry is safe."""
        # Try to invalidate nonexistent entry (should not raise)
        preview_service.invalidate("nonexistent")

    def test_invalidate_all(self, preview_service):
        """Test clearing entire cache."""
        # Add multiple cache entries
        mock_pixmap = QPixmap(100, 100)
        preview_service.set_preview_cache("frame1", mock_pixmap, 0.0, (1, 2))
        preview_service.set_preview_cache("frame2", mock_pixmap, 0.0, (3, 4))

        assert len(preview_service._game_frame_previews) == 2

        # Clear all
        preview_service.invalidate_all()

        assert len(preview_service._game_frame_previews) == 0


class TestPreviewServiceStaleEntries:
    """Test stale entry ID fallback behavior."""

    def test_stale_previews_return_none_after_mark_all_stale(
        self, preview_service, mock_project, rendering_patches, qtbot
    ):
        """Test that stale previews return None after mark_all_stale()."""
        project, game_frame = mock_project

        # Generate and cache preview
        preview1 = preview_service.force_regenerate_preview("frame1", project)
        assert preview1 is not None, "Initial preview should be generated"

        # Verify it's cached and can be retrieved
        cached = preview_service.get_cached_preview("frame1", project)
        assert cached is not None, "Preview should be cached"
        assert cached == preview1, "Cached preview should match original"

        # Mark all previews as stale (simulating palette change)
        preview_service.mark_all_stale()

        # Verify frame is in stale set
        assert "frame1" in preview_service._stale_previews, "Frame should be marked stale"

        # Now get_cached_preview should return None
        cached_after_stale = preview_service.get_cached_preview("frame1", project)
        assert cached_after_stale is None, "Stale preview should return None"

        # Verify stale flag still persists (not yet cleared)
        # Stale flag is only cleared when set_preview_cache is called (regeneration succeeds)
        assert "frame1" in preview_service._stale_previews, (
            "Stale flag should persist until set_preview_cache clears it"
        )

        # Subsequent calls should also return None while stale flag persists
        # This ensures caller knows to regenerate async
        cached_second_call = preview_service.get_cached_preview("frame1", project)
        assert cached_second_call is None, "Should return None while stale flag persists"

        # Only when set_preview_cache is called (regeneration succeeds) is stale flag cleared
        new_pixmap = QImage(100, 100, QImage.Format.Format_RGBA8888)
        new_qpixmap = QPixmap.fromImage(new_pixmap)
        # Use game_frame.cached_mtime to match the current state
        preview_service.set_preview_cache("frame1", new_qpixmap, game_frame.cached_mtime, (1, 2, 3))

        # After set_preview_cache, stale flag should be cleared
        assert "frame1" not in preview_service._stale_previews, "Stale flag should be cleared after set_preview_cache"

        # Now get_cached_preview should return the new pixmap
        cached_after_regen = preview_service.get_cached_preview("frame1", project)
        assert cached_after_regen is not None, "Should return pixmap after regen"
        assert cached_after_regen == new_qpixmap, "Should return regenerated pixmap"

    def test_force_regenerate_after_stale_returns_new_pixmap(
        self, preview_service, mock_project, rendering_patches, qtbot
    ):
        """Test that force_regenerate_preview returns new pixmap after stale."""
        project, game_frame = mock_project

        # First generation
        _ = preview_service.force_regenerate_preview("frame1", project)

        # Mark stale
        preview_service.mark_all_stale()

        # get_cached_preview returns None
        assert preview_service.get_cached_preview("frame1", project) is None

        # Force regeneration should return new pixmap
        rendering_patches.set_qimage(200, 200)
        preview2 = preview_service.force_regenerate_preview("frame1", project)

        assert preview2 is not None, "Regenerated preview should not be None"
        assert preview2.width() == 200, "New pixmap should have updated dimensions"

        # Now get_cached_preview should return the new one
        cached_new = preview_service.get_cached_preview("frame1", project)
        assert cached_new is not None
        assert cached_new == preview2, "Cached preview should be the regenerated one"

    def test_stale_entries_fallback_to_rom_offset(self, preview_service, mock_project, qtbot):
        """Test that stale entry IDs fall back to rom_offset filtering."""
        project, game_frame = mock_project
        game_frame.selected_entry_ids = [99, 100]  # Stale IDs not in capture

        # Mock capture result with different entry IDs
        entry1 = Mock(spec=OAMEntry)
        entry1.id = 1
        entry1.rom_offset = 0x12345  # Matches game_frame.rom_offsets

        entry2 = Mock(spec=OAMEntry)
        entry2.id = 2
        entry2.rom_offset = 0x99999  # Does NOT match

        capture = Mock(spec=CaptureResult)
        capture.has_entries = True
        capture.entries = [entry1, entry2]
        capture.frame = 100
        capture.obsel = 0
        capture.palettes = []
        capture.timestamp = "2026-01-24"

        # Patch the repository's get_or_parse to return mock capture
        with patch.object(preview_service._capture_repository, "get_or_parse", return_value=capture):
            # Should emit stale_entries_warning and use rom_offset fallback
            with qtbot.waitSignal(preview_service.stale_entries_warning, timeout=signal_timeout()) as blocker:
                result, used_fallback = preview_service.get_capture_result_for_game_frame("frame1", project)

        assert blocker.signal_triggered
        assert blocker.args == ["frame1"]
        assert used_fallback is True
        assert result is not None
        # Only entry1 should be in filtered result (rom_offset matches)
        assert len(result.entries) == 1
        assert result.entries[0].id == 1

    def test_valid_entries_no_fallback(self, preview_service, mock_project, mock_capture_result):
        """Test that valid entry IDs don't trigger fallback."""
        project, game_frame = mock_project
        game_frame.selected_entry_ids = [1, 2, 3]  # Valid IDs in capture

        # Patch the repository's get_or_parse to return mock capture
        with patch.object(preview_service._capture_repository, "get_or_parse", return_value=mock_capture_result):
            result, used_fallback = preview_service.get_capture_result_for_game_frame("frame1", project)

        assert used_fallback is False
        assert result is not None
        assert len(result.entries) == 3


class TestPreviewServiceEdgeCases:
    """Test edge cases and error handling."""

    def test_no_project_returns_none(self, preview_service):
        """Test that None project returns None."""
        result = preview_service.get_cached_preview("frame1", None)
        assert result is None

    def test_missing_capture_file_returns_cached(self, preview_service, mock_project, qtbot):
        """Test that missing file returns cached preview (last known good)."""
        project, game_frame = mock_project

        # Pre-populate cache
        mock_pixmap = QPixmap(100, 100)
        preview_service.set_preview_cache("frame1", mock_pixmap, 0.0, (1, 2, 3))

        # Make file missing
        game_frame.capture_path.unlink()

        # Should return cached preview
        result = preview_service.get_cached_preview("frame1", project)
        assert result is not None
        assert result == mock_pixmap

    def test_parse_error_returns_none(self, preview_service, mock_project, qtbot):
        """Test that parse error returns None."""
        project, game_frame = mock_project

        # Patch the repository to raise an error
        with patch.object(preview_service._capture_repository, "get_or_parse", side_effect=Exception("Parse error")):
            result = preview_service.force_regenerate_preview("frame1", project)
            assert result is None

    def test_render_error_returns_none(self, preview_service, mock_project, mock_capture_result, qtbot):
        """Test that render error returns None."""
        project, game_frame = mock_project

        # Patch the repository to return mock capture
        with patch.object(preview_service._capture_repository, "get_or_parse", return_value=mock_capture_result):
            with patch("ui.frame_mapping.services.preview_renderer.CaptureRenderer") as MockRenderer:
                renderer_inst = MockRenderer.return_value
                renderer_inst.render_selection.side_effect = Exception("Render error")

                result = preview_service.force_regenerate_preview("frame1", project)
                assert result is None

    def test_set_preview_cache_manual(self, preview_service):
        """Test manual cache setting."""
        mock_pixmap = QPixmap(100, 100)
        preview_service.set_preview_cache("frame1", mock_pixmap, 123.45, (1, 2, 3))

        cached_pixmap, cached_mtime, cached_entries = preview_service._game_frame_previews["frame1"]
        assert cached_pixmap == mock_pixmap
        assert cached_mtime == 123.45
        assert cached_entries == (1, 2, 3)


class TestPreviewServiceIntegration:
    """Integration tests with real rendering pipeline (no mocked CaptureRenderer)."""

    @pytest.fixture
    def minimal_capture_json(self, tmp_path: Path) -> Path:
        """Create 8x8 sprite capture with all pixels = palette index 1 (red).

        SNES 4bpp tile format: 8 rows × 4 bytes each = 32 bytes per tile.
        Bitplanes: row N uses bytes at offsets 2N, 2N+1 (bp0, bp1) and 16+2N, 16+2N+1 (bp2, bp3).
        For palette index 1 (0b0001), we need bp0=1, bp1=0, bp2=0, bp3=0.
        So: bp0=0xFF (all pixels have bit0=1), bp1=0x00, bp2=0x00, bp3=0x00 for each row.
        """
        import json

        # Build 4bpp tile data: 8 rows, each row sets all 8 pixels to palette index 1
        # Format: rows 0-7 interleaved bp0/bp1, then rows 0-7 interleaved bp2/bp3
        tile_bytes = []
        for _row in range(8):
            tile_bytes.append(0xFF)  # bp0 = 1 for all pixels
            tile_bytes.append(0x00)  # bp1 = 0
        for _row in range(8):
            tile_bytes.append(0x00)  # bp2 = 0
            tile_bytes.append(0x00)  # bp3 = 0
        tile_hex = "".join(f"{b:02x}" for b in tile_bytes)

        capture_data = {
            "schema_version": "1.0",
            "frame": 100,
            "obsel": {"raw": 0},
            "visible_count": 1,
            "entries": [
                {
                    "id": 1,
                    "x": 0,
                    "y": 0,
                    "tile": 0,
                    "width": 8,
                    "height": 8,
                    "palette": 0,
                    "priority": 0,
                    "flip_h": False,
                    "flip_v": False,
                    "name_table": 0,
                    "tile_page": 0,
                    "tiles": [
                        {
                            "tile_index": 0,
                            "vram_addr": 0,
                            "pos_x": 0,
                            "pos_y": 0,
                            "data_hex": tile_hex,
                        }
                    ],
                }
            ],
            # Palette 0: index 0 = black (transparent), index 1 = red
            "palettes": {
                "0": [[0, 0, 0], [255, 0, 0]] + [[0, 0, 0]] * 14,
            },
        }
        path = tmp_path / "capture.json"
        path.write_text(json.dumps(capture_data))
        return path

    def test_preview_renders_correct_pixel_colors(self, preview_service, minimal_capture_json: Path, tmp_path: Path):
        """Verify actual pixel colors from real rendering pipeline (no CaptureRenderer mock)."""
        # Create a real project with proper structure
        project = FrameMappingProject(
            name="test",
            ai_frames_dir=tmp_path,
            ai_frames=[],
            game_frames=[],
            mappings=[],
        )

        game_frame = GameFrame(
            id="f1",
            capture_path=minimal_capture_json,
            selected_entry_ids=[1],
            rom_offsets=[0x1000],
            palette_index=0,
            width=8,
            height=8,
            compression_types={},
        )
        project.add_game_frame(game_frame)

        # Get preview using real rendering (no mocks!)
        pixmap = preview_service.force_regenerate_preview("f1", project)

        assert pixmap is not None, "Preview should be generated"
        assert pixmap.width() == 8, f"Expected width 8, got {pixmap.width()}"
        assert pixmap.height() == 8, f"Expected height 8, got {pixmap.height()}"

        # Check pixel color - center pixel should be red (palette index 1)
        image = pixmap.toImage()
        color = image.pixelColor(4, 4)
        assert color.red() == 255, f"Expected red=255, got {color.red()}"
        assert color.green() == 0, f"Expected green=0, got {color.green()}"
        assert color.blue() == 0, f"Expected blue=0, got {color.blue()}"
