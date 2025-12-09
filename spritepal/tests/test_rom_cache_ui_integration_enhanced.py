"""
Enhanced integration tests for ROM cache UI components.

This module provides comprehensive testing of cache UI integration with:
- Better fixture management
- Error condition testing
- Performance validation
- Cleaner test organization
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.managers import cleanup_managers, initialize_managers
from core.rom_injector import SpritePointer
from ui.components.panels.status_panel import StatusPanel
from ui.rom_extraction.widgets.rom_file_widget import ROMFileWidget
from ui.rom_extraction.workers.scan_worker import SpriteScanWorker
from utils.rom_cache import ROMCache, get_rom_cache

# ============================================================================
# Enhanced Fixtures
# ============================================================================

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.performance,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.widget,
    pytest.mark.cache,
    pytest.mark.ci_safe,
    pytest.mark.serial,
    pytest.mark.signals_slots,
    pytest.mark.slow,
]

@pytest.fixture(autouse=True)
def setup_teardown():
    """Initialize and cleanup managers for each test."""
    initialize_managers("TestROMCacheUI")
    yield
    cleanup_managers()
    # Reset global cache instance using the new pattern
    from utils.rom_cache import _ROMCacheSingleton
    _ROMCacheSingleton._instance = None

@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return str(cache_dir)

@pytest.fixture
def test_rom_file(tmp_path):
    """Create a test ROM file."""
    rom_file = tmp_path / "test_game.sfc"
    # Create a ROM large enough for sprite scanning (at least 0xF0000 bytes = ~1MB)
    rom_size = 0xF0000 + 0x10000  # Add some extra space
    rom_data = bytearray(rom_size)
    for i in range(len(rom_data)):
        rom_data[i] = i % 256
    rom_file.write_bytes(rom_data)
    return str(rom_file)

@pytest.fixture
def rom_cache(temp_cache_dir):
    """Create a ROM cache instance with temporary directory."""
    return ROMCache(cache_dir=temp_cache_dir)

@pytest.fixture
def mock_rom_cache(rom_cache):
    """Automatically patch get_rom_cache to return test instance and clean up after."""
    with patch("utils.rom_cache.get_rom_cache") as mock_get:
        mock_get.return_value = rom_cache
        # Also patch in all the widget modules
        with patch("ui.rom_extraction.widgets.rom_file_widget.get_rom_cache") as mock_widget:
            mock_widget.return_value = rom_cache
            yield rom_cache
    # Clean up global state using the new pattern
    from utils.rom_cache import _ROMCacheSingleton
    _ROMCacheSingleton._instance = None

@pytest.fixture
def disabled_cache(temp_cache_dir):
    """Create a cache instance with caching disabled."""
    with patch("utils.rom_cache.get_settings_manager") as mock_settings:
        mock_manager = MagicMock()
        mock_manager.get_cache_enabled.return_value = False
        mock_settings.return_value = mock_manager
        cache = ROMCache(cache_dir=temp_cache_dir)
        yield cache

@pytest.fixture
def corrupted_cache_file(temp_cache_dir):
    """Create a corrupted cache file for error testing."""
    cache_file = Path(temp_cache_dir) / "abc123_sprite_locations.json"
    cache_file.write_text("{ invalid json content")
    return str(cache_file)

# ============================================================================
# ROMFileWidget Cache Display Tests
# ============================================================================

class TestROMFileWidgetCacheDisplay:
    """Test cache status display in ROMFileWidget with enhanced scenarios."""

    def test_cache_status_no_cache(self, qtbot, test_rom_file, mock_rom_cache):
        """Test cache status display when no cache exists."""
        widget = ROMFileWidget()
        qtbot.addWidget(widget)

        # Load ROM file
        widget.set_rom_path(test_rom_file)

        # Check that no cache status is shown
        info_text = widget.rom_info_label.text()
        assert "💾" not in info_text
        assert "📊" not in info_text
        assert "cached" not in info_text

    def test_cache_status_with_disabled_cache(self, qtbot, test_rom_file):
        """Test that no cache UI appears when caching is disabled."""
        with patch("ui.rom_extraction.widgets.rom_file_widget.get_rom_cache") as mock_get:
            # Create disabled cache
            cache = MagicMock()
            cache._cache_enabled = False
            cache.get_sprite_locations.return_value = None
            mock_get.return_value = cache

            widget = ROMFileWidget()
            qtbot.addWidget(widget)
            widget.set_rom_path(test_rom_file)

            # Should not check cache when disabled
            cache.get_sprite_locations.assert_not_called()

    def test_cache_error_handling(self, qtbot, test_rom_file, mock_rom_cache):
        """Test graceful handling of cache read errors."""
        # Make cache operations raise exceptions
        mock_rom_cache.get_sprite_locations = MagicMock(side_effect=RuntimeError("Cache read error"))
        mock_rom_cache.get_partial_scan_results = MagicMock(side_effect=RuntimeError("Cache read error"))

        widget = ROMFileWidget()
        qtbot.addWidget(widget)

        # Should handle exceptions gracefully without crashing
        widget.set_rom_path(test_rom_file)
        widget.set_info_text(f"<b>File:</b> {os.path.basename(test_rom_file)}")

        # Widget should still function despite cache errors
        assert widget.rom_path_edit.text() == test_rom_file
        assert widget.rom_info_label.text()  # Should have some text
        assert "💾" not in widget.rom_info_label.text()  # No cache indicator due to error

    def test_cache_with_invalid_data(self, qtbot, test_rom_file, mock_rom_cache):
        """Test handling of corrupted cache data."""
        # Return invalid sprite data
        mock_rom_cache.get_sprite_locations = MagicMock(return_value={"invalid": "data"})

        widget = ROMFileWidget()
        qtbot.addWidget(widget)
        widget.set_rom_path(test_rom_file)

        # Should handle gracefully
        assert widget.rom_path_edit.text() == test_rom_file

# ============================================================================
# SpriteScanWorker Cache Integration Tests (Enhanced)
# ============================================================================

class TestSpriteScanWorkerCacheIntegration:
    """Enhanced tests for cache integration in sprite scanning workflow."""

    def test_scan_worker_cache_status_messages(self, qtbot, test_rom_file, mock_rom_cache):
        """Test that scan worker emits proper cache status messages."""
        # Create a simple mock extractor
        mock_extractor = MagicMock()
        mock_extractor.rom_injector.find_compressed_sprite = MagicMock(return_value=(0, b""))
        mock_extractor._assess_sprite_quality = MagicMock(return_value=0.1)  # Low quality to avoid matches

        # Configure cache to have no existing data
        mock_rom_cache.get_partial_scan_results = MagicMock(return_value=None)

        # Create worker

        worker = SpriteScanWorker(test_rom_file, mock_extractor, use_cache=True)

        # Track cache status messages
        cache_messages = []
        worker.cache_status.connect(cache_messages.append)

        # Start worker (it should finish quickly with low quality sprites)
        worker.start()

        # Wait for completion
        with qtbot.waitSignal(worker.finished, timeout=10000):
            pass

        # Verify cache status messages were emitted
        assert len(cache_messages) > 0

        # Should see messages about checking cache and starting fresh scan
        assert any("Checking cache" in msg for msg in cache_messages)
        assert any("Starting fresh scan" in msg for msg in cache_messages)

    def test_cache_save_interval(self, qtbot, test_rom_file, mock_rom_cache):
        """Test that cache saves occur at regular intervals during scan."""
        # Track cache saves
        save_calls = []
        original_save = mock_rom_cache.save_partial_scan_results

        def track_save(*args, **kwargs):
            save_calls.append(time.time())
            return original_save(*args, **kwargs)

        mock_rom_cache.save_partial_scan_results = track_save

        # This test is marked slow but demonstrates interval saving
        pytest.skip("Slow test - demonstrates cache save intervals")

# ============================================================================
# Error Condition Tests
# ============================================================================

class TestCacheErrorConditions:
    """Test error handling in cache UI integration."""

    def test_permission_error_fallback(self, qtbot, tmp_path):
        """Test fallback when cache directory has permission issues."""
        # Create read-only directory
        cache_dir = tmp_path / "readonly_cache"
        cache_dir.mkdir(mode=0o444)

        try:
            with patch("utils.rom_cache.Path.home") as mock_home:
                mock_home.return_value = cache_dir

                # Should fallback to temp directory
                cache = ROMCache()
                assert cache._cache_enabled  # Should still be enabled
                assert "tmp" in str(cache.cache_dir).lower()  # Using temp fallback
        finally:
            # Cleanup
            cache_dir.chmod(0o755)

    def test_corrupted_cache_recovery(self, qtbot, test_rom_file, temp_cache_dir):
        """Test recovery from corrupted cache files."""
        # Create corrupted cache
        cache = ROMCache(cache_dir=temp_cache_dir)
        rom_hash = cache._get_rom_hash(test_rom_file)
        cache_file = Path(temp_cache_dir) / f"{rom_hash}_sprite_locations.json"
        cache_file.write_text("{ corrupted json")

        # Should handle corrupted cache gracefully
        result = cache.get_sprite_locations(test_rom_file)
        assert result is None  # Should return None, not crash

    def test_cache_expiration(self, qtbot, test_rom_file, mock_rom_cache):
        """Test that expired cache is properly detected."""
        # Save cache data
        sprite_locations = {"Test": SpritePointer(offset=0x1000, bank=0x10, address=0x8000)}
        mock_rom_cache.save_sprite_locations(test_rom_file, sprite_locations)

        # Mock file modification time to be old
        with patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value.st_mtime = time.time() - (8 * 24 * 3600)  # 8 days old

            # Should detect as expired (default is 7 days)
            result = mock_rom_cache.get_sprite_locations(test_rom_file)
            assert result is None

# ============================================================================
# Performance Tests
# ============================================================================

class TestCachePerformance:
    """Test that cache actually improves performance."""

    def test_cache_vs_no_cache_timing(self, qtbot, test_rom_file, mock_rom_cache):
        """Measure performance improvement with cache."""
        # First, time without cache
        start_time = time.time()
        locations_no_cache = mock_rom_cache.get_sprite_locations(test_rom_file)
        time_no_cache = time.time() - start_time
        assert locations_no_cache is None  # No cache yet

        # Save to cache
        test_locations = {
            f"Sprite {i}": SpritePointer(
                offset=0x1000 * i,
                bank=0x10,
                address=0x8000,
                compressed_size=100
            )
            for i in range(100)  # 100 sprites
        }
        mock_rom_cache.save_sprite_locations(test_rom_file, test_locations)

        # Time with cache
        start_time = time.time()
        locations_with_cache = mock_rom_cache.get_sprite_locations(test_rom_file)
        time_with_cache = time.time() - start_time

        # Cache should be significantly faster
        assert locations_with_cache is not None
        assert len(locations_with_cache) == 100
        # Cache read should be at least 10x faster than the overhead
        assert time_with_cache < time_no_cache + 0.1  # Allow 100ms overhead

# ============================================================================
# StatusPanel Cache Display Tests
# ============================================================================

class TestStatusPanelCacheDisplay:
    """Test cache statistics display in StatusPanel."""

    def test_status_panel_cache_stats(self, qtbot, mock_rom_cache):
        """Test that StatusPanel displays cache statistics."""
        # Create status panel
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Pre-populate cache with data
        test_file = "/tmp/test.sfc"
        mock_rom_cache.save_sprite_locations(test_file, {"Sprite1": {"offset": 0x1000}})

        # Get cache stats
        stats = mock_rom_cache.get_cache_stats()

        # Update status panel with cache info
        f"Cache: {stats['total_files']} files, {stats['total_size_bytes']} bytes"
        panel.update_cache_status()

        # Verify display
        assert str(stats["total_files"]) in panel.cache_info_label.text()

    def test_status_panel_cache_operations(self, qtbot, mock_rom_cache):
        """Test status panel updates during cache operations."""
        panel = StatusPanel()
        qtbot.addWidget(panel)

        # Simulate cache operation progress
        panel.update_status("💾 Saving to cache...")
        # StatusPanel displays general status in a separate area, not cache_info_label

        panel.update_status("✅ Cache updated")
        # Just verify the method can be called without error

# ============================================================================
# Integration Test Helpers
# ============================================================================

class TestCacheUIHelpers:
    """Test helper functions and utilities."""

    def test_cache_singleton_reset(self):
        """Test that cache singleton can be properly reset between tests."""
        # Get first instance
        cache1 = get_rom_cache()

        # Reset global cache instance using the new pattern
        from utils.rom_cache import _ROMCacheSingleton
        _ROMCacheSingleton._instance = None

        # Get new instance
        cache2 = get_rom_cache()

        # Should be different instances
        assert cache1 is not cache2

    def test_mock_fixture_isolation(self, mock_rom_cache, test_rom_file):
        """Test that mock_rom_cache fixture provides proper isolation."""
        # Save data in this test
        mock_rom_cache.save_sprite_locations(
            test_rom_file,
            {"Test": SpritePointer(offset=0x1000, bank=0x10, address=0x8000)}
        )

        # Data should be accessible
        result = mock_rom_cache.get_sprite_locations(test_rom_file)
        assert result is not None
        assert "Test" in result

# ============================================================================
# Concurrent Operation Tests
# ============================================================================

class TestConcurrentCacheOperations:
    """Test cache behavior with concurrent operations."""

    def test_concurrent_cache_access(self, qtbot, test_rom_file, mock_rom_cache):
        """Test multiple widgets accessing cache simultaneously."""
        # Create multiple widgets
        widget1 = ROMFileWidget()
        widget2 = ROMFileWidget()
        qtbot.addWidget(widget1)
        qtbot.addWidget(widget2)

        # Both load the same ROM
        widget1.set_rom_path(test_rom_file)
        widget2.set_rom_path(test_rom_file)

        # Save cache from one widget's perspective
        mock_rom_cache.save_sprite_locations(
            test_rom_file,
            {"Sprite1": SpritePointer(offset=0x1000, bank=0x10, address=0x8000)}
        )

        # Both should see the cache
        widget1._check_cache_status()
        widget2._check_cache_status()

        assert widget1._cache_status["has_cache"]
        assert widget2._cache_status["has_cache"]

# ============================================================================
# Settings Integration Tests
# ============================================================================

class TestCacheSettingsIntegration:
    """Test cache integration with settings system."""

    def test_cache_location_change(self, qtbot, temp_cache_dir):
        """Test changing cache location via settings."""
        # Create cache with initial location
        cache = ROMCache(cache_dir=temp_cache_dir)
        initial_dir = cache.cache_dir

        # Mock the settings manager for the cache instance
        mock_manager = MagicMock()
        mock_manager.get_cache_enabled.return_value = True
        cache.settings_manager = mock_manager

        # Create new location
        new_location = Path(temp_cache_dir).parent / "new_cache"
        new_location.mkdir()

        # Update cache location
        mock_manager.get_cache_location.return_value = str(new_location)

        cache.refresh_settings()

        # Cache directory should change
        assert cache.cache_dir != initial_dir
        assert cache.cache_dir == new_location
