"""
Tests for SmartPreviewCoordinator memory cache functionality.

Tests that the smart preview coordinator properly stores and retrieves preview data
using the memory LRU cache.
"""

from __future__ import annotations

import weakref
from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.no_manager_setup

try:
    from PySide6.QtCore import QObject, QTimer, Signal
    from PySide6.QtWidgets import QApplication, QSlider

    QT_AVAILABLE = True
except ImportError:
    QApplication = Mock
    QSlider = Mock
    QObject = Mock
    QTimer = Mock
    Signal = Mock
    QT_AVAILABLE = False

from ui.common.smart_preview_coordinator import SmartPreviewCoordinator


class TestSmartPreviewMemoryCache:
    """Test Smart Preview Coordinator memory cache functionality."""

    @pytest.fixture(autouse=True)
    def setup_qt_environment(self):
        """Setup Qt environment for testing."""
        if QT_AVAILABLE:
            if not QApplication.instance():
                self.app = QApplication([])
            else:
                self.app = QApplication.instance()
        yield

    @pytest.fixture
    def mock_slider(self):
        """Create mock slider."""
        if QT_AVAILABLE:
            slider = QSlider()
            slider.value = Mock(return_value=0x8000)
            return slider
        else:
            slider = Mock()
            slider.value.return_value = 0x8000
            return slider

    @pytest.fixture
    def coordinator(self, mock_slider):
        """Create SmartPreviewCoordinator."""
        with (
            patch("ui.common.smart_preview_coordinator.PreviewWorkerPool") as mock_pool_class,
            patch("ui.common.smart_preview_coordinator.PreviewCache") as mock_cache_class,
        ):
            # Setup mock worker pool
            mock_pool = Mock()
            mock_pool_class.return_value = mock_pool

            # Setup mock memory cache
            mock_memory_cache = Mock()
            mock_memory_cache.make_key = Mock(side_effect=lambda rom_path, offset: f"{rom_path}:0x{offset:06X}")
            mock_cache_class.return_value = mock_memory_cache

            coordinator = SmartPreviewCoordinator()
            coordinator._slider_ref = weakref.ref(mock_slider) if mock_slider else None
            coordinator._current_offset = 0x8000

            # Set up ROM data provider
            def mock_rom_data_provider():
                return "/test/rom.sfc", Mock()  # rom_path, extractor

            coordinator._rom_data_provider = mock_rom_data_provider

            # Attach mocks for easier access in tests
            coordinator._cache = mock_memory_cache

            yield coordinator

    def test_initialization(self):
        """Test that coordinator is properly initialized."""
        with (
            patch("ui.common.smart_preview_coordinator.PreviewWorkerPool"),
            patch("ui.common.smart_preview_coordinator.PreviewCache"),
        ):
            coordinator = SmartPreviewCoordinator()

            assert coordinator._drag_state is not None
            assert coordinator._request_counter == 0
            assert coordinator._cache is not None
            assert coordinator._worker_pool is not None

    def test_cache_key_generation(self, coordinator):
        """Test that cache keys are generated consistently."""
        rom_path = "/test/rom.sfc"
        offset = 0x8000

        coordinator._current_offset = offset
        coordinator._try_show_cached_preview()

        expected_key = f"{rom_path}:0x{offset:06X}"
        coordinator._cache.get.assert_called_with(expected_key)

    def test_memory_cache_hit(self, coordinator):
        """Test memory cache hit returns cached data."""
        # Cache format: (tile_data, width, height, sprite_name, compressed_size, slack_size)
        cached_data = (b"test_tile_data\x01\x02", 16, 16, "test_sprite", 100, 0)

        # Setup memory cache to return valid data
        coordinator._cache.get.return_value = cached_data

        result = coordinator._try_show_cached_preview()

        assert result is True
        coordinator._cache.get.assert_called_once()

    def test_memory_cache_miss(self, coordinator):
        """Test memory cache miss returns False."""
        coordinator._cache.get.return_value = None

        result = coordinator._try_show_cached_preview()

        assert result is False

    def test_invalid_cached_data_removed(self, coordinator):
        """Test that all-zero cached data is removed from cache."""
        # Setup memory cache to return all-zeros data (invalid)
        # Cache format: (tile_data, width, height, sprite_name, compressed_size, slack_size)
        cached_data = (b"\x00" * 100, 16, 16, "test_sprite", 100, 0)
        coordinator._cache.get.return_value = cached_data

        result = coordinator._try_show_cached_preview()

        # Should return False (cache miss due to invalid data)
        assert result is False
        # Invalid entry should be removed
        coordinator._cache.remove.assert_called_once()

    def test_cleanup_clears_cache(self, coordinator):
        """Test that cleanup properly clears the cache."""
        coordinator.cleanup()

        coordinator._cache.clear.assert_called_once()

    def test_request_preview_checks_cache_first(self, coordinator):
        """Test that request_preview checks cache before scheduling worker."""
        # Cache format: (tile_data, width, height, sprite_name, compressed_size, slack_size)
        cached_data = (b"test_data\x01\x02", 8, 8, "sprite", 50, 0)
        coordinator._cache.get.return_value = cached_data

        coordinator.request_preview(0x8000)

        # Should check cache
        coordinator._cache.get.assert_called()

    def test_worker_preview_caches_result(self, coordinator):
        """Test that worker preview results are cached."""
        tile_data = b"new_tile_data\x01\x02\x03"
        width = 16
        height = 16
        sprite_name = "new_sprite"
        compressed_size = 75
        slack_size = 0

        # Simulate worker callback (includes slack_size as 7th arg)
        coordinator._on_worker_preview_ready(1, tile_data, width, height, sprite_name, compressed_size, slack_size)

        # Should cache the result
        coordinator._cache.put.assert_called_once()
        call_args = coordinator._cache.put.call_args
        # Cache format: (tile_data, width, height, sprite_name, compressed_size, slack_size)
        assert call_args[0][1] == (tile_data, width, height, sprite_name, compressed_size, slack_size)

    def test_stale_preview_not_cached(self, coordinator):
        """Test that stale preview results are not processed."""
        # Set request counter high to make request_id=1 stale
        coordinator._request_counter = 10

        coordinator._on_worker_preview_ready(1, b"data", 8, 8, "sprite", 50)

        # Should not cache stale result
        coordinator._cache.put.assert_not_called()
