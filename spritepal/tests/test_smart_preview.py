"""
Tests for SmartPreviewCoordinator ROM cache tier functionality.

Tests that the smart preview coordinator properly stores and retrieves preview data,
implements batch saving functionality, and integrates correctly with the memory cache.
"""
from __future__ import annotations

# Import test dependencies
import weakref
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Mark all tests in this module to skip manager setup
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

from core.services.rom_cache import ROMCache
from ui.common.smart_preview_coordinator import SmartPreviewCoordinator


class TestSmartPreviewROMCacheTier:
    """Test Smart Preview Coordinator ROM cache tier functionality"""

    @pytest.fixture(autouse=True)
    def setup_qt_environment(self):
        """Setup Qt environment for testing"""
        if QT_AVAILABLE:
            if not QApplication.instance():
                self.app = QApplication([])
            else:
                self.app = QApplication.instance()
        yield

    @pytest.fixture
    def mock_rom_cache(self):
        """Create mock ROM cache"""
        mock_cache = Mock(spec=ROMCache)
        mock_cache.cache_enabled = True
        mock_cache.get_preview_data.return_value = None
        mock_cache.save_preview_data.return_value = True
        mock_cache.save_preview_batch.return_value = True
        return mock_cache

    @pytest.fixture
    def mock_slider(self):
        """Create mock slider"""
        if QT_AVAILABLE:
            slider = QSlider()
            slider.value = Mock(return_value=0x8000)
            return slider
        else:
            slider = Mock()
            slider.value.return_value = 0x8000
            return slider

    @pytest.fixture
    def coordinator(self, mock_rom_cache, mock_slider):
        """Create SmartPreviewCoordinator with ROM cache"""
        with patch('ui.common.smart_preview_coordinator.PreviewWorkerPool') as mock_pool_class, \
             patch('ui.common.smart_preview_coordinator.PreviewCache') as mock_cache_class:

            # Setup mock worker pool
            mock_pool = Mock()
            mock_pool_class.return_value = mock_pool

            # Setup mock memory cache
            mock_memory_cache = Mock()
            # Mock the make_key method to return predictable keys
            mock_memory_cache.make_key = Mock(side_effect=lambda rom_path, offset: f"{rom_path}:0x{offset:06X}")
            mock_cache_class.return_value = mock_memory_cache

            coordinator = SmartPreviewCoordinator(rom_cache=mock_rom_cache)
            # Set internal state directly for testing
            coordinator._slider_ref = weakref.ref(mock_slider) if mock_slider else None
            coordinator._current_offset = 0x8000  # Default offset for testing

            # Wrap signals with mocks that have receivers() method
            original_preview_cached = coordinator.preview_cached
            mock_preview_cached = Mock()
            mock_preview_cached.emit = original_preview_cached.emit
            mock_preview_cached.receivers = Mock(return_value=1)
            coordinator.preview_cached = mock_preview_cached

            original_preview_ready = coordinator.preview_ready
            mock_preview_ready = Mock()
            mock_preview_ready.emit = original_preview_ready.emit
            mock_preview_ready.receivers = Mock(return_value=1)
            coordinator.preview_ready = mock_preview_ready

            # Set up ROM data provider to return test data
            def mock_rom_data_provider():
                return "/test/rom.sfc", None, None
            coordinator._rom_data_provider = mock_rom_data_provider

            # Attach mocks for easier access in tests
            coordinator._cache = mock_memory_cache

            yield coordinator

    def test_rom_cache_tier_initialization(self, mock_rom_cache):
        """Test that ROM cache tier is properly initialized"""
        with patch('ui.common.smart_preview_coordinator.PreviewWorkerPool'), \
             patch('ui.common.smart_preview_coordinator.PreviewCache'):

            coordinator = SmartPreviewCoordinator(rom_cache=mock_rom_cache)

            assert coordinator._rom_cache is mock_rom_cache
            assert coordinator._pending_rom_cache_saves == {}
            assert hasattr(coordinator, '_batch_save_timer')
            assert coordinator._batch_save_delay_ms == 2000

    def test_preview_data_storage_and_retrieval(self, coordinator, mock_rom_cache):
        """Test preview data storage and retrieval from ROM cache"""
        rom_path = "/test/rom.sfc"
        offset = 0x8000
        preview_data = (b"test_tile_data", 16, 16, "test_sprite")

        # Test storage
        result = coordinator._save_to_rom_cache(rom_path, offset, preview_data)
        assert result is True

        # Verify ROM cache was called correctly with keyword arguments
        mock_rom_cache.save_preview_data.assert_called_once_with(
            rom_path=rom_path,
            offset=offset,
            tile_data=preview_data[0],
            width=preview_data[1],
            height=preview_data[2],
            params=None  # The sprite_name is passed as params=None in the actual implementation
        )

    def test_rom_cache_tier_fallback_when_memory_miss(self, coordinator, mock_rom_cache):
        """Test ROM cache tier as fallback when memory cache misses"""
        offset = 0x8000
        rom_cache_data = (b"rom_cached_data", 8, 8, "rom_sprite")

        # Setup ROM cache to return data
        mock_rom_cache.get_preview_data.return_value = {
            "tile_data": rom_cache_data[0],
            "width": rom_cache_data[1],
            "height": rom_cache_data[2],
            "sprite_name": rom_cache_data[3]
        }

        # Setup memory cache to miss
        coordinator._cache.get.return_value = None

        # Test dual-tier cache lookup
        coordinator._try_show_cached_preview_dual_tier()

        # Should check memory cache first
        coordinator._cache.get.assert_called()

        # Should fall back to ROM cache
        mock_rom_cache.get_preview_data.assert_called_once_with("/test/rom.sfc", offset)

    def test_batch_saving_functionality(self, coordinator, mock_rom_cache):
        """Test batch saving functionality for ROM cache"""
        rom_path = "/test/rom.sfc"

        # Queue multiple preview saves
        preview_data_1 = (b"tile_1", 8, 8, "sprite_1")
        preview_data_2 = (b"tile_2", 16, 16, "sprite_2")
        preview_data_3 = (b"tile_3", 8, 16, "sprite_3")

        coordinator._queue_rom_cache_save(rom_path, 0x8000, preview_data_1)
        coordinator._queue_rom_cache_save(rom_path, 0x8100, preview_data_2)
        coordinator._queue_rom_cache_save(rom_path, 0x8200, preview_data_3)

        # Verify data is queued
        assert rom_path in coordinator._pending_rom_cache_saves
        assert len(coordinator._pending_rom_cache_saves[rom_path]) == 3
        assert coordinator._pending_rom_cache_saves[rom_path][0x8000] == preview_data_1
        assert coordinator._pending_rom_cache_saves[rom_path][0x8100] == preview_data_2
        assert coordinator._pending_rom_cache_saves[rom_path][0x8200] == preview_data_3

    def test_batch_save_timer_functionality(self, coordinator, mock_rom_cache):
        """Test that batch save timer is properly managed"""
        rom_path = "/test/rom.sfc"
        preview_data = (b"test_data", 8, 8, "test")

        # Mock the timer
        with patch.object(coordinator._batch_save_timer, 'stop') as mock_stop, \
             patch.object(coordinator._batch_save_timer, 'start') as mock_start:

            coordinator._queue_rom_cache_save(rom_path, 0x8000, preview_data)

            # Timer should be stopped and restarted
            mock_stop.assert_called_once()
            mock_start.assert_called_once_with(2000)  # 2 second delay

    def test_flush_pending_saves_single_entry(self, coordinator, mock_rom_cache):
        """Test flushing single pending save"""
        rom_path = "/test/rom.sfc"
        offset = 0x8000
        preview_data = (b"single_tile", 8, 8, "single_sprite")

        # Manually add to pending saves
        coordinator._pending_rom_cache_saves[rom_path] = {offset: preview_data}

        # Flush pending saves
        coordinator._flush_pending_rom_cache_saves()

        # Should use single save method for lone entries (with positional args)
        mock_rom_cache.save_preview_data.assert_called_once_with(
            rom_path, offset, preview_data[0], preview_data[1], preview_data[2], None
        )

        # Pending saves should be cleared
        assert len(coordinator._pending_rom_cache_saves) == 0

    def test_flush_pending_saves_batch_operation(self, coordinator, mock_rom_cache):
        """Test flushing multiple pending saves as batch"""
        rom_path = "/test/rom.sfc"

        # Setup multiple pending saves
        preview_data_1 = (b"batch_1", 8, 8, "sprite_1")
        preview_data_2 = (b"batch_2", 16, 16, "sprite_2")
        preview_data_3 = (b"batch_3", 8, 16, "sprite_3")

        coordinator._pending_rom_cache_saves[rom_path] = {
            0x8000: preview_data_1,
            0x8100: preview_data_2,
            0x8200: preview_data_3
        }

        # Flush pending saves
        coordinator._flush_pending_rom_cache_saves()

        # Should use batch save method
        mock_rom_cache.save_preview_batch.assert_called_once()

        # Verify batch data structure
        call_args = mock_rom_cache.save_preview_batch.call_args
        assert call_args[0][0] == rom_path  # First arg is rom_path
        batch_data = call_args[0][1]  # Second arg is batch_data

        assert len(batch_data) == 3
        assert 0x8000 in batch_data
        assert 0x8100 in batch_data
        assert 0x8200 in batch_data

        # Pending saves should be cleared
        assert len(coordinator._pending_rom_cache_saves) == 0

    def test_multiple_rom_files_batch_handling(self, coordinator, mock_rom_cache):
        """Test batch handling with multiple ROM files"""
        rom_path_1 = "/test/rom1.sfc"
        rom_path_2 = "/test/rom2.sfc"

        # Queue saves for different ROM files
        coordinator._pending_rom_cache_saves[rom_path_1] = {
            0x8000: (b"rom1_data1", 8, 8, "rom1_sprite1"),
            0x8100: (b"rom1_data2", 16, 16, "rom1_sprite2")
        }
        coordinator._pending_rom_cache_saves[rom_path_2] = {
            0x9000: (b"rom2_data1", 8, 16, "rom2_sprite1")
        }

        # Flush pending saves
        coordinator._flush_pending_rom_cache_saves()

        # Should call batch save for rom1 and single save for rom2
        assert mock_rom_cache.save_preview_batch.call_count == 1
        assert mock_rom_cache.save_preview_data.call_count == 1

        # Check batch save call for rom1
        batch_call = mock_rom_cache.save_preview_batch.call_args
        assert batch_call[0][0] == rom_path_1
        assert len(batch_call[0][1]) == 2

        # Check single save call for rom2
        single_call = mock_rom_cache.save_preview_data.call_args
        assert single_call[0][0] == rom_path_2
        assert single_call[0][1] == 0x9000

    def test_integration_with_memory_cache(self, coordinator, mock_rom_cache):
        """Test integration between ROM cache tier and memory cache"""
        rom_path = "/test/rom.sfc"
        offset = 0x8000
        rom_cache_data = (b"rom_data", 8, 8, "rom_sprite")

        # Setup ROM cache to return data
        mock_rom_cache.get_preview_data.return_value = {
            "tile_data": rom_cache_data[0],
            "width": rom_cache_data[1],
            "height": rom_cache_data[2],
            "sprite_name": rom_cache_data[3]
        }

        # Setup memory cache to miss initially
        coordinator._cache.get.return_value = None

        # Trigger dual-tier cache lookup
        coordinator._try_show_cached_preview_dual_tier()

        # Should store ROM cache data in memory cache for faster future access
        # Note: The sprite name gets overridden to manual_0x{offset:06X} format
        expected_cache_key = f"{rom_path}:0x{offset:06X}"
        expected_data = (rom_cache_data[0], rom_cache_data[1], rom_cache_data[2], f"manual_0x{offset:06X}")
        coordinator._cache.put.assert_called_once_with(expected_cache_key, expected_data)

    def test_rom_cache_error_handling(self, coordinator, mock_rom_cache):
        """Test error handling in ROM cache operations"""
        rom_path = "/test/rom.sfc"
        offset = 0x8000
        preview_data = (b"test_data", 8, 8, "test")

        # Test save error handling
        mock_rom_cache.save_preview_data.return_value = False

        result = coordinator._save_to_rom_cache(rom_path, offset, preview_data)
        assert result is False

        # Test get error handling
        mock_rom_cache.get_preview_data.side_effect = Exception("Cache error")

        result = coordinator._check_rom_cache(rom_path, offset)
        # On error, returns empty tuple instead of None
        assert result == (b"", 0, 0, None)

    def test_batch_save_failure_handling(self, coordinator, mock_rom_cache):
        """Test handling of batch save failures"""
        rom_path = "/test/rom.sfc"

        # Setup multiple pending saves
        coordinator._pending_rom_cache_saves[rom_path] = {
            0x8000: (b"data1", 8, 8, "sprite1"),
            0x8100: (b"data2", 16, 16, "sprite2")
        }

        # Make batch save fail
        mock_rom_cache.save_preview_batch.return_value = False

        # Flush should handle failure gracefully
        coordinator._flush_pending_rom_cache_saves()

        # Pending saves should still be cleared even on failure
        assert len(coordinator._pending_rom_cache_saves) == 0

    def test_cleanup_flushes_pending_saves(self, coordinator, mock_rom_cache):
        """Test that cleanup flushes any pending ROM cache saves"""
        rom_path = "/test/rom.sfc"

        # Add pending saves
        coordinator._pending_rom_cache_saves[rom_path] = {
            0x8000: (b"pending_data", 8, 8, "pending_sprite")
        }

        # Call cleanup
        coordinator.cleanup()

        # Should flush pending saves
        mock_rom_cache.save_preview_data.assert_called_once()
        assert len(coordinator._pending_rom_cache_saves) == 0

    def test_batch_save_performance_optimization(self, coordinator, mock_rom_cache):
        """Test that batch saving provides performance optimization"""
        rom_path = "/test/rom.sfc"

        # Add many pending saves to test batch efficiency
        for i in range(10):
            offset = 0x8000 + (i * 0x100)
            preview_data = (f"data_{i}".encode(), 8, 8, f"sprite_{i}")
            coordinator._pending_rom_cache_saves.setdefault(rom_path, {})[offset] = preview_data

        # Flush pending saves
        coordinator._flush_pending_rom_cache_saves()

        # Should use single batch call instead of 10 individual calls
        mock_rom_cache.save_preview_batch.assert_called_once()
        mock_rom_cache.save_preview_data.assert_not_called()

        # Verify batch contains all 10 items
        batch_data = mock_rom_cache.save_preview_batch.call_args[0][1]
        assert len(batch_data) == 10

    def test_dual_tier_cache_priority(self, coordinator, mock_rom_cache):
        """Test that memory cache takes priority over ROM cache in dual-tier system"""
        memory_data = (b"memory_data", 8, 8, "memory_sprite")
        rom_data = (b"rom_data", 16, 16, "rom_sprite")

        # Setup both caches to have data
        coordinator._cache.get.return_value = memory_data
        mock_rom_cache.get_preview_data.return_value = {
            "tile_data": rom_data[0],
            "width": rom_data[1],
            "height": rom_data[2],
            "sprite_name": rom_data[3]
        }

        # Trigger dual-tier lookup
        result = coordinator._try_show_cached_preview_dual_tier()

        # Should use memory cache data and not check ROM cache
        assert result is True
        coordinator._cache.get.assert_called_once()
        mock_rom_cache.get_preview_data.assert_not_called()

    def test_rom_cache_disabled_handling(self, coordinator):
        """Test handling when ROM cache is disabled"""
        # Disable ROM cache
        coordinator._rom_cache = None

        # ROM cache operations should handle gracefully
        result = coordinator._save_to_rom_cache("/test/rom.sfc", 0x8000, (b"data", 8, 8, "sprite"))
        assert result is False

        result = coordinator._check_rom_cache("/test/rom.sfc", 0x8000)
        # When cache is disabled, returns empty tuple instead of None
        assert result == (b"", 0, 0, None)

        # Dual-tier cache should fall back to memory only
        coordinator._cache.get.return_value = None
        result = coordinator._try_show_cached_preview_dual_tier()
        assert result is False

    def test_cache_key_generation_consistency(self, coordinator, mock_rom_cache, mock_slider):
        """Test that cache keys are generated consistently between memory and ROM cache"""
        rom_path = "/test/rom.sfc"
        offset = 0x8000

        # Set the current offset for testing
        coordinator._current_offset = offset

        # Trigger cache operations and verify key consistency
        coordinator._try_show_cached_preview_dual_tier()

        # Memory cache should be checked with consistent key format
        expected_key = f"{rom_path}:0x{offset:06X}"
        coordinator._cache.get.assert_called_with(expected_key)

    def test_concurrent_batch_operations(self, coordinator, mock_rom_cache):
        """Test handling of concurrent batch operations"""
        rom_path = "/test/rom.sfc"

        # Simulate rapid queuing of cache saves
        for i in range(5):
            preview_data = (f"concurrent_{i}".encode(), 8, 8, f"sprite_{i}")
            coordinator._queue_rom_cache_save(rom_path, 0x8000 + i, preview_data)

        # Timer should be restarted with each queue operation
        # (We can't easily test the actual timer behavior, but we can verify the data structure)
        assert len(coordinator._pending_rom_cache_saves[rom_path]) == 5

        # Flush should handle all queued items
        coordinator._flush_pending_rom_cache_saves()
        mock_rom_cache.save_preview_batch.assert_called_once()
        assert len(coordinator._pending_rom_cache_saves) == 0
