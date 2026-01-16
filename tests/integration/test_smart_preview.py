from __future__ import annotations

import weakref
from unittest.mock import Mock, patch

import pytest

from core.services.preview_generator import PreviewGenerator

pytestmark = [pytest.mark.integration, pytest.mark.no_manager_setup]

"""
Tests for SmartPreviewCoordinator memory cache functionality.

Tests that the smart preview coordinator properly stores and retrieves preview data
using the memory LRU cache.
"""


def test_smart_preview_initialization():
    """Verify PreviewGenerator can be initialized."""
    # This replaces more complex tests that were removed or redundant
    generator = PreviewGenerator()
    assert generator is not None


@pytest.mark.skip_thread_cleanup(reason="Uses PreviewWorkerPool which owns worker threads")
class TestBackgroundPreloadStalenessCheck:
    """Tests for background preload handling in SmartPreviewCoordinator.

    Bug: Background preloads use negative request_ids to differentiate them
    from user-triggered requests. However, the staleness check
    `if request_id < self._request_counter` always rejects negative IDs
    since _request_counter is always non-negative.

    This defeats the background preloading optimization entirely.
    """

    def test_negative_request_id_not_treated_as_stale(self, qtbot):
        """
        BUG REPRODUCTION: Negative request IDs should NOT be rejected as stale.

        Background preloads use negative request_ids (-1001, -1002, etc.) to
        differentiate them from user-triggered requests. The staleness check
        should only apply to positive IDs.

        This test will FAIL before the fix is applied.
        """
        from ui.common.smart_preview_coordinator import SmartPreviewCoordinator

        # Create coordinator with minimal setup
        # (SmartPreviewCoordinator is a QObject, not QWidget)
        coordinator = SmartPreviewCoordinator()

        # Track if preview_ready is emitted (indicates result was processed)
        preview_received = []

        def on_preview_ready(
            tile_data,
            width,
            height,
            sprite_name,
            compressed_size,
            slack_size,
            actual_offset,
            hal_succeeded,
            header_bytes,
        ):
            preview_received.append((tile_data, actual_offset))

        coordinator.preview_ready.connect(on_preview_ready)

        # Simulate a background preload result with negative request_id
        negative_request_id = -1001  # Typical background preload ID
        test_tile_data = b"\x01" * 32  # 1 tile of data
        test_offset = 0x1234

        # Manually invoke the handler (simulating worker completing)
        coordinator._on_worker_preview_ready(
            request_id=negative_request_id,
            tile_data=test_tile_data,
            width=8,
            height=8,
            sprite_name="test",
            compressed_size=32,
            slack_size=0,
            actual_offset=test_offset,
            hal_succeeded=True,
            header_bytes=b"",
        )

        # KEY ASSERTION: The preview should be processed, not rejected as stale
        # Bug: Currently negative IDs are always < _request_counter (which is >= 0)
        # so they're incorrectly treated as stale and the signal is never emitted.
        assert len(preview_received) == 1, (
            f"Expected 1 preview (negative ID should not be stale), got {len(preview_received)}. "
            f"Background preload with request_id={negative_request_id} was incorrectly "
            f"rejected as stale because it's less than _request_counter={coordinator._request_counter}."
        )
        assert preview_received[0][0] == test_tile_data, "Tile data mismatch"
        assert preview_received[0][1] == test_offset, "Offset mismatch"

    def test_positive_request_id_staleness_check_still_works(self, qtbot):
        """
        Positive request IDs should still be checked for staleness normally.

        This ensures the fix doesn't break the normal staleness detection.
        """
        from ui.common.smart_preview_coordinator import SmartPreviewCoordinator

        # (SmartPreviewCoordinator is a QObject, not QWidget)
        coordinator = SmartPreviewCoordinator()

        preview_received = []

        def on_preview_ready(
            tile_data,
            width,
            height,
            sprite_name,
            compressed_size,
            slack_size,
            actual_offset,
            hal_succeeded,
            header_bytes,
        ):
            preview_received.append(actual_offset)

        coordinator.preview_ready.connect(on_preview_ready)

        # Simulate request counter being incremented (user made new request)
        coordinator._request_counter = 5

        # Old request with ID less than current counter should be rejected
        stale_request_id = 3  # Less than current counter (5)
        coordinator._on_worker_preview_ready(
            request_id=stale_request_id,
            tile_data=b"\x01" * 32,
            width=8,
            height=8,
            sprite_name="stale",
            compressed_size=32,
            slack_size=0,
            actual_offset=0x1000,
            hal_succeeded=True,
            header_bytes=b"",
        )

        # Stale request should be ignored
        assert len(preview_received) == 0, (
            f"Stale request (id={stale_request_id}) should be ignored, "
            f"but {len(preview_received)} previews were received."
        )

        # Current request with ID >= counter should be processed
        current_request_id = 5  # Equal to current counter
        coordinator._on_worker_preview_ready(
            request_id=current_request_id,
            tile_data=b"\x02" * 32,
            width=8,
            height=8,
            sprite_name="current",
            compressed_size=32,
            slack_size=0,
            actual_offset=0x2000,
            hal_succeeded=True,
            header_bytes=b"",
        )

        # Current request should be processed
        assert len(preview_received) == 1, (
            f"Current request (id={current_request_id}) should be processed, but got {len(preview_received)} previews."
        )
