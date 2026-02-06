"""Tests for preview cache stale flag lifecycle in PreviewService.

Verifies that the stale flag persists until explicit regeneration succeeds,
and is cleared after successful cache update.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from PySide6.QtGui import QPixmap

from core.frame_mapping_project import FrameMappingProject, GameFrame
from core.repositories.capture_result_repository import CaptureResultRepository
from ui.frame_mapping.services.preview_service import PreviewService


@pytest.fixture
def preview_service(qtbot):
    """Create a PreviewService instance."""
    capture_repository = CaptureResultRepository()
    service = PreviewService(capture_repository=capture_repository)
    return service


@pytest.fixture
def mock_project(tmp_path):
    """Create a mock project with game frame."""
    project = Mock(spec=FrameMappingProject)

    # Create a test capture file
    capture_path = tmp_path / "test_capture.json"
    capture_path.write_text('{"frame": 100, "entries": []}')

    # Mock game frame
    game_frame = Mock(spec=GameFrame)
    game_frame.id = "frame_1"
    game_frame.capture_path = capture_path
    game_frame.selected_entry_ids = [0]
    game_frame.rom_offsets = frozenset([0x1000])
    game_frame.cached_mtime = 100.0

    project.get_game_frame_by_id.return_value = game_frame

    return project, game_frame


def test_stale_flag_persists_until_regen_success(preview_service, mock_project, qtbot) -> None:
    """After marking stale, get_cached_preview returns None until regen succeeds.

    The stale flag should persist across multiple get_cached_preview calls,
    not be cleared on the first None return.
    """
    project, game_frame = mock_project

    # Seed the cache with a valid preview
    pixmap = QPixmap(8, 8)
    preview_service.set_preview_cache("frame_1", pixmap, 100.0, (0,))

    # Verify cache hit works
    result = preview_service.get_cached_preview("frame_1", project)
    assert result is not None

    # Mark all stale (simulates palette change)
    preview_service.mark_all_stale()

    # First call should return None (stale)
    result1 = preview_service.get_cached_preview("frame_1", project)
    assert result1 is None

    # BUG: Second call ALSO should return None (stale flag should persist until regen succeeds)
    # Currently, the first call clears the stale flag, so the second call returns the stale pixmap
    result2 = preview_service.get_cached_preview("frame_1", project)
    assert result2 is None, "Stale flag should persist until regen succeeds, not be cleared on first None return"


def test_stale_flag_cleared_after_set_preview_cache(preview_service, mock_project, qtbot) -> None:
    """After marking stale, set_preview_cache clears the stale flag.

    Subsequent get_cached_preview calls should return the new pixmap.
    """
    project, game_frame = mock_project

    # Seed the cache with a valid preview
    pixmap = QPixmap(8, 8)
    preview_service.set_preview_cache("frame_1", pixmap, 100.0, (0,))

    # Mark all stale (simulates palette change)
    preview_service.mark_all_stale()

    # Call get_cached_preview → None (stale)
    result = preview_service.get_cached_preview("frame_1", project)
    assert result is None

    # Now simulate successful regen by calling set_preview_cache with new pixmap
    new_pixmap = QPixmap(8, 8)
    preview_service.set_preview_cache("frame_1", new_pixmap, 100.0, (0,))

    # After successful regen, should return the new pixmap
    result = preview_service.get_cached_preview("frame_1", project)
    assert result is not None, "After set_preview_cache (regen success), stale flag should be cleared"
