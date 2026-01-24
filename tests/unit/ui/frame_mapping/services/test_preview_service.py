"""Tests for PreviewService."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtGui import QPixmap

from core.frame_mapping_project import FrameMappingProject, GameFrame
from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import CaptureResult, OAMEntry
from tests.fixtures.timeouts import signal_timeout
from ui.frame_mapping.services.preview_service import PreviewService


@pytest.fixture
def preview_service(qtbot):
    """Create a PreviewService instance."""
    service = PreviewService()
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


class TestPreviewServiceCaching:
    """Test preview cache hit/miss behavior."""

    def test_cache_miss_generates_preview(self, preview_service, mock_project, mock_capture_result, qtbot):
        """Test that cache miss generates preview from capture file."""
        project, game_frame = mock_project

        with patch("ui.frame_mapping.services.preview_service.MesenCaptureParser") as MockParser:
            with patch("ui.frame_mapping.services.preview_service.CaptureRenderer") as MockRenderer:
                # Setup mocks
                parser_inst = MockParser.return_value
                parser_inst.parse_file.return_value = mock_capture_result

                renderer_inst = MockRenderer.return_value
                mock_pil_img = Mock()
                renderer_inst.render_selection.return_value = mock_pil_img

                with patch("ui.frame_mapping.services.preview_service.pil_to_qpixmap") as mock_pil_to_qpixmap:
                    mock_pixmap = QPixmap(100, 100)
                    mock_pil_to_qpixmap.return_value = mock_pixmap

                    # First call - cache miss
                    result = preview_service.get_preview("frame1", project)

                    assert result is not None
                    assert isinstance(result, QPixmap)
                    parser_inst.parse_file.assert_called_once()
                    MockRenderer.assert_called_once()

    def test_cache_hit_returns_cached_pixmap(self, preview_service, mock_project, mock_capture_result, qtbot):
        """Test that cache hit returns cached pixmap without regeneration."""
        project, game_frame = mock_project

        with patch("ui.frame_mapping.services.preview_service.MesenCaptureParser") as MockParser:
            with patch("ui.frame_mapping.services.preview_service.CaptureRenderer") as MockRenderer:
                # Setup mocks
                parser_inst = MockParser.return_value
                parser_inst.parse_file.return_value = mock_capture_result

                renderer_inst = MockRenderer.return_value
                mock_pil_img = Mock()
                renderer_inst.render_selection.return_value = mock_pil_img

                with patch("ui.frame_mapping.services.preview_service.pil_to_qpixmap") as mock_pil_to_qpixmap:
                    mock_pixmap = QPixmap(100, 100)
                    mock_pil_to_qpixmap.return_value = mock_pixmap

                    # First call - cache miss
                    result1 = preview_service.get_preview("frame1", project)

                    # Second call - cache hit
                    result2 = preview_service.get_preview("frame1", project)

                    assert result1 == result2
                    # Parser should only be called once (first time)
                    assert parser_inst.parse_file.call_count == 1

    def test_mtime_change_invalidates_cache(self, preview_service, mock_project, mock_capture_result, qtbot, tmp_path):
        """Test that file mtime change invalidates cache."""
        project, game_frame = mock_project

        # Create actual file to get real mtime
        capture_path = tmp_path / "test_capture.json"
        capture_path.write_text('{"frame": 100}')
        game_frame.capture_path = capture_path

        with patch("ui.frame_mapping.services.preview_service.MesenCaptureParser") as MockParser:
            with patch("ui.frame_mapping.services.preview_service.CaptureRenderer") as MockRenderer:
                # Setup mocks
                parser_inst = MockParser.return_value
                parser_inst.parse_file.return_value = mock_capture_result

                renderer_inst = MockRenderer.return_value
                mock_pil_img = Mock()
                renderer_inst.render_selection.return_value = mock_pil_img

                with patch("ui.frame_mapping.services.preview_service.pil_to_qpixmap") as mock_pil_to_qpixmap:
                    mock_pixmap = QPixmap(100, 100)
                    mock_pil_to_qpixmap.return_value = mock_pixmap

                    # First call - cache miss
                    with qtbot.waitSignal(
                        preview_service.preview_cache_invalidated, timeout=signal_timeout(), raising=False
                    ):
                        preview_service.get_preview("frame1", project)

                    # Modify file (change mtime)
                    capture_path.write_text('{"frame": 101}')

                    # Second call - cache invalidated due to mtime change
                    with qtbot.waitSignal(
                        preview_service.preview_cache_invalidated, timeout=signal_timeout()
                    ) as blocker:
                        preview_service.get_preview("frame1", project)

                    assert blocker.signal_triggered
                    assert blocker.args == ["frame1"]
                    # Parser called twice (cache invalidated)
                    assert parser_inst.parse_file.call_count == 2

    def test_entry_ids_change_invalidates_cache(self, preview_service, mock_project, mock_capture_result, qtbot):
        """Test that entry IDs change invalidates cache."""
        project, game_frame = mock_project

        with patch("ui.frame_mapping.services.preview_service.MesenCaptureParser") as MockParser:
            with patch("ui.frame_mapping.services.preview_service.CaptureRenderer") as MockRenderer:
                # Setup mocks
                parser_inst = MockParser.return_value
                parser_inst.parse_file.return_value = mock_capture_result

                renderer_inst = MockRenderer.return_value
                mock_pil_img = Mock()
                renderer_inst.render_selection.return_value = mock_pil_img

                with patch("ui.frame_mapping.services.preview_service.pil_to_qpixmap") as mock_pil_to_qpixmap:
                    mock_pixmap = QPixmap(100, 100)
                    mock_pil_to_qpixmap.return_value = mock_pixmap

                    # First call - cache miss
                    preview_service.get_preview("frame1", project)

                    # Change selected entry IDs
                    game_frame.selected_entry_ids = [1, 2]  # Changed from [1, 2, 3]

                    # Second call - cache invalidated due to entry ID change
                    with qtbot.waitSignal(
                        preview_service.preview_cache_invalidated, timeout=signal_timeout()
                    ) as blocker:
                        preview_service.get_preview("frame1", project)

                    assert blocker.signal_triggered
                    # Parser called twice (cache invalidated)
                    assert parser_inst.parse_file.call_count == 2


class TestPreviewServiceInvalidation:
    """Test cache invalidation methods."""

    def test_invalidate_single_entry(self, preview_service, qtbot):
        """Test invalidating a single cache entry."""
        # Manually add cache entry
        mock_pixmap = QPixmap(100, 100)
        preview_service.set_preview_cache("frame1", mock_pixmap, 0.0, (1, 2, 3))

        # Verify cached
        assert "frame1" in preview_service._game_frame_previews

        # Invalidate and verify signal
        with qtbot.waitSignal(preview_service.preview_cache_invalidated, timeout=signal_timeout()) as blocker:
            preview_service.invalidate("frame1")

        assert blocker.signal_triggered
        assert blocker.args == ["frame1"]
        assert "frame1" not in preview_service._game_frame_previews

    def test_invalidate_nonexistent_entry_no_signal(self, preview_service, qtbot):
        """Test that invalidating nonexistent entry doesn't emit signal."""
        # Try to invalidate nonexistent entry
        with qtbot.assertNotEmitted(preview_service.preview_cache_invalidated, wait=100):
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

        with patch("ui.frame_mapping.services.preview_service.MesenCaptureParser") as MockParser:
            parser_inst = MockParser.return_value
            parser_inst.parse_file.return_value = capture

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

        with patch("ui.frame_mapping.services.preview_service.MesenCaptureParser") as MockParser:
            parser_inst = MockParser.return_value
            parser_inst.parse_file.return_value = mock_capture_result

            result, used_fallback = preview_service.get_capture_result_for_game_frame("frame1", project)

            assert used_fallback is False
            assert result is not None
            assert len(result.entries) == 3


class TestPreviewServiceEdgeCases:
    """Test edge cases and error handling."""

    def test_no_project_returns_none(self, preview_service):
        """Test that None project returns None."""
        result = preview_service.get_preview("frame1", None)
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
        result = preview_service.get_preview("frame1", project)
        assert result is not None
        assert result == mock_pixmap

    def test_parse_error_returns_none(self, preview_service, mock_project, qtbot):
        """Test that parse error returns None."""
        project, game_frame = mock_project

        with patch("ui.frame_mapping.services.preview_service.MesenCaptureParser") as MockParser:
            parser_inst = MockParser.return_value
            parser_inst.parse_file.side_effect = Exception("Parse error")

            result = preview_service.get_preview("frame1", project)
            assert result is None

    def test_render_error_returns_none(self, preview_service, mock_project, mock_capture_result, qtbot):
        """Test that render error returns None."""
        project, game_frame = mock_project

        with patch("ui.frame_mapping.services.preview_service.MesenCaptureParser") as MockParser:
            with patch("ui.frame_mapping.services.preview_service.CaptureRenderer") as MockRenderer:
                parser_inst = MockParser.return_value
                parser_inst.parse_file.return_value = mock_capture_result

                renderer_inst = MockRenderer.return_value
                renderer_inst.render_selection.side_effect = Exception("Render error")

                result = preview_service.get_preview("frame1", project)
                assert result is None

    def test_set_preview_cache_manual(self, preview_service):
        """Test manual cache setting."""
        mock_pixmap = QPixmap(100, 100)
        preview_service.set_preview_cache("frame1", mock_pixmap, 123.45, (1, 2, 3))

        cached_pixmap, cached_mtime, cached_entries = preview_service._game_frame_previews["frame1"]
        assert cached_pixmap == mock_pixmap
        assert cached_mtime == 123.45
        assert cached_entries == (1, 2, 3)
