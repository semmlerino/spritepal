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


@pytest.mark.skip_thread_cleanup(reason="Uses PreviewWorkerPool which owns worker threads")
class TestCachePoisoningPrevention:
    """Tests for cache key correctness in background preload handling.

    Bug (Issue 1 from desync report): Background preloads used self._current_offset
    for the cache key instead of actual_offset, causing cache poisoning when
    the user changed offsets before a background preload completed.

    Scenario:
    1. User viewing offset 0x010000 (_current_offset = 0x010000)
    2. Background preload requests offset 0x020000 (does NOT update _current_offset)
    3. Worker completes with data for 0x020000
    4. BUG: Cache stores under key 0x010000 instead of 0x020000
    5. Cache is now corrupted - offset 0x010000 has wrong data
    """

    def test_background_preload_uses_actual_offset_for_cache_key(self, qtbot, tmp_path):
        """
        BUG REPRODUCTION: Background preload should cache under actual_offset, not _current_offset.

        This test will FAIL before the fix is applied.
        """
        from ui.common.smart_preview_coordinator import SmartPreviewCoordinator

        coordinator = SmartPreviewCoordinator()

        # Set up a ROM data provider so caching logic is exercised
        test_rom_path = tmp_path / "test.sfc"
        test_rom_path.write_bytes(b"\x00" * 0x100000)  # 1MB fake ROM

        def rom_data_provider():
            return (str(test_rom_path), b"\x00" * 100)

        coordinator.set_rom_data_provider(rom_data_provider)

        # User is currently viewing offset A
        offset_a = 0x010000
        coordinator._current_offset = offset_a

        # Background preload completes for offset B (different from current)
        offset_b = 0x020000
        test_tile_data_b = b"\xbb" * 32  # Data for offset B
        background_request_id = -1001  # Negative = background preload

        # Manually populate request context since we're skipping the request flow
        coordinator._request_contexts[background_request_id] = (None, False)

        coordinator._on_worker_preview_ready(
            request_id=background_request_id,
            tile_data=test_tile_data_b,
            width=8,
            height=8,
            sprite_name="sprite_at_offset_b",
            compressed_size=32,
            slack_size=0,
            actual_offset=offset_b,  # Worker completed for offset B
            hal_succeeded=True,
            header_bytes=b"",
        )

        # KEY ASSERTIONS:
        # 1. Cache should contain data under key for offset_b, not offset_a
        # MUST use same context as coordinator: auto|preview (None, False)
        cache_key_b = coordinator._make_cache_key(str(test_rom_path), offset_b, None, False)
        cache_key_a = coordinator._make_cache_key(str(test_rom_path), offset_a, None, False)

        cached_data_b = coordinator._cache.get(cache_key_b)
        cached_data_a = coordinator._cache.get(cache_key_a)

        # Default empty tuple returned when cache miss (SpritePreviewCache.get() returns this)
        default_cache_miss = (b"", 0, 0, None, 0, 0, -1, True, b"")

        # Offset B should be in cache (this is what the preload was for)
        assert cached_data_b != default_cache_miss, (
            f"Data for offset_b (0x{offset_b:X}) should be cached under its own key. "
            f"Bug: Cache stores under _current_offset (0x{offset_a:X}) instead of actual_offset."
        )

        # Offset A should NOT have the data (it wasn't preloaded)
        assert cached_data_a == default_cache_miss, (
            f"Offset A (0x{offset_a:X}) should NOT be cached because no preload was done for it. "
            f"Bug: Background preload for offset_b poisoned cache entry for offset_a."
        )

        # Verify the cached data is correct
        tile_data, width, height, sprite_name, *_ = cached_data_b
        assert tile_data == test_tile_data_b, "Cached tile data should match preload data"
        assert sprite_name == "sprite_at_offset_b", "Cached sprite name should match"

    def test_user_request_still_caches_correctly(self, qtbot, tmp_path):
        """
        User-triggered requests (positive IDs) should still cache correctly.

        Ensures the fix doesn't break normal user-triggered caching.
        """
        from ui.common.smart_preview_coordinator import SmartPreviewCoordinator

        coordinator = SmartPreviewCoordinator()

        # Set up ROM data provider
        test_rom_path = tmp_path / "test.sfc"
        test_rom_path.write_bytes(b"\x00" * 0x100000)

        def rom_data_provider():
            return (str(test_rom_path), b"\x00" * 100)

        coordinator.set_rom_data_provider(rom_data_provider)

        # User requests offset A (which sets _current_offset)
        offset_a = 0x030000
        coordinator._current_offset = offset_a
        test_tile_data = b"\xaa" * 32
        user_request_id = 1  # Positive = user request

        # Manually populate request context
        coordinator._request_contexts[user_request_id] = (None, False)

        coordinator._on_worker_preview_ready(
            request_id=user_request_id,
            tile_data=test_tile_data,
            width=8,
            height=8,
            sprite_name="user_sprite",
            compressed_size=32,
            slack_size=0,
            actual_offset=offset_a,  # Same as _current_offset for user requests
            hal_succeeded=True,
            header_bytes=b"",
        )

        # Cache should contain data under offset_a
        # MUST use same context as coordinator: auto|preview (None, False)
        cache_key = coordinator._make_cache_key(str(test_rom_path), offset_a, None, False)
        cached_data = coordinator._cache.get(cache_key)

        assert cached_data is not None, "User request should be cached"
        tile_data, *_ = cached_data
        assert tile_data == test_tile_data, "Cached tile data should match"
