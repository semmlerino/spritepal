"""
Tests for cache invalidation after ROM injection.

These tests verify that:
1. invalidate_rom_cache() clears all cache types for the specified ROM
2. Cache invalidation doesn't affect unrelated ROMs
3. Successful ROM injection triggers cache invalidation
4. Failed injection does not invalidate cache
5. VRAM injection does not affect ROM cache
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [
    pytest.mark.headless,
    pytest.mark.no_manager_setup,
    pytest.mark.allows_registry_state(reason="Cache tests are stateless"),
]


class TestROMCacheInvalidation:
    """Tests for ROMCache.invalidate_rom_cache() method."""

    @pytest.fixture
    def mock_settings_manager(self) -> MagicMock:
        """Create a mock settings manager with realistic behavior."""
        manager = MagicMock()
        manager.get_cache_enabled.return_value = True
        manager.get_cache_location.return_value = None
        manager.get_cache_expiry_days.return_value = 30
        return manager

    @pytest.fixture
    def rom_cache(self, tmp_path: Path, mock_settings_manager: MagicMock):
        """Create a ROMCache instance with a temporary directory."""
        from core.services.rom_cache import ROMCache

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        cache = ROMCache(mock_settings_manager, cache_dir=str(cache_dir))
        return cache

    @pytest.fixture
    def sample_rom(self, tmp_path: Path) -> Path:
        """Create a sample ROM file for testing."""
        rom_path = tmp_path / "sample.sfc"
        rom_path.write_bytes(b"SNES ROM DATA" * 1000)  # ~13KB fake ROM
        return rom_path

    def test_invalidate_clears_sprite_locations_cache(
        self, rom_cache, sample_rom: Path, tmp_path: Path
    ) -> None:
        """invalidate_rom_cache() clears sprite_locations cache."""
        # Save some sprite locations
        sprite_data = {"sprites": [{"offset": 0x1000, "name": "test"}]}
        save_result = rom_cache.save_sprite_locations(str(sample_rom), sprite_data)
        assert save_result is True, "Failed to save sprite locations"

        # Verify cache exists by checking files directly
        rom_hash = rom_cache._get_rom_hash(str(sample_rom))
        cache_file = rom_cache.cache_dir / f"{rom_hash}_sprite_locations.json"
        assert cache_file.exists(), "Cache file was not created"

        # Invalidate
        removed = rom_cache.invalidate_rom_cache(str(sample_rom))

        # Verify cache file was deleted
        assert removed >= 1
        assert not cache_file.exists(), "Cache file was not deleted"

    def test_invalidate_clears_rom_info_cache(
        self, rom_cache, sample_rom: Path
    ) -> None:
        """invalidate_rom_cache() clears rom_info cache."""
        # Save some ROM info
        rom_info = {"title": "Test ROM", "checksum": "ABCD"}
        save_result = rom_cache.save_rom_info(str(sample_rom), rom_info)
        assert save_result is True, "Failed to save ROM info"

        # Verify cache file exists
        rom_hash = rom_cache._get_rom_hash(str(sample_rom))
        cache_file = rom_cache.cache_dir / f"{rom_hash}_rom_info.json"
        assert cache_file.exists(), "Cache file was not created"

        # Invalidate
        removed = rom_cache.invalidate_rom_cache(str(sample_rom))

        # Verify cache file was deleted
        assert removed >= 1
        assert not cache_file.exists(), "Cache file was not deleted"

    def test_invalidate_clears_preview_cache(
        self, rom_cache, sample_rom: Path
    ) -> None:
        """invalidate_rom_cache() clears preview caches."""
        # Save some preview data
        preview_data = b"fake tile data"
        save_result = rom_cache.save_preview_data(
            str(sample_rom), offset=0x1000, tile_data=preview_data,
            width=8, height=8
        )
        assert save_result is True, "Failed to save preview data"

        # Verify cache file exists
        rom_hash = rom_cache._get_rom_hash(str(sample_rom))
        preview_files = list(rom_cache.cache_dir.glob(f"{rom_hash}_preview_*.json"))
        assert len(preview_files) > 0, "Preview cache file was not created"

        # Invalidate
        removed = rom_cache.invalidate_rom_cache(str(sample_rom))

        # Verify cache files were deleted
        assert removed >= 1
        preview_files_after = list(rom_cache.cache_dir.glob(f"{rom_hash}_preview_*.json"))
        assert len(preview_files_after) == 0, "Preview cache files were not deleted"

    def test_invalidate_clears_hash_cache(
        self, rom_cache, sample_rom: Path
    ) -> None:
        """invalidate_rom_cache() clears in-memory hash cache entry."""
        # Access ROM to populate hash cache
        rom_cache._get_rom_hash(str(sample_rom))

        # Verify hash is cached
        with rom_cache._hash_cache_lock:
            cached_keys = [
                k for k in rom_cache._hash_cache
                if k.startswith(str(sample_rom))
            ]
            assert len(cached_keys) > 0

        # Invalidate
        rom_cache.invalidate_rom_cache(str(sample_rom))

        # Verify hash cache was cleared
        with rom_cache._hash_cache_lock:
            cached_keys = [
                k for k in rom_cache._hash_cache
                if k.startswith(str(sample_rom))
            ]
            assert len(cached_keys) == 0

    def test_invalidate_does_not_affect_other_roms(
        self, rom_cache, sample_rom: Path, tmp_path: Path
    ) -> None:
        """invalidate_rom_cache() only clears cache for specified ROM."""
        # Create another ROM
        other_rom = tmp_path / "other.sfc"
        other_rom.write_bytes(b"OTHER ROM DATA" * 1000)

        # Save caches for both ROMs
        rom_cache.save_sprite_locations(str(sample_rom), {"sprites": []})
        rom_cache.save_sprite_locations(str(other_rom), {"sprites": []})
        rom_cache.save_rom_info(str(sample_rom), {"title": "Sample"})
        rom_cache.save_rom_info(str(other_rom), {"title": "Other"})

        # Verify both have cache files
        sample_hash = rom_cache._get_rom_hash(str(sample_rom))
        other_hash = rom_cache._get_rom_hash(str(other_rom))
        sample_cache = rom_cache.cache_dir / f"{sample_hash}_sprite_locations.json"
        other_cache = rom_cache.cache_dir / f"{other_hash}_sprite_locations.json"
        assert sample_cache.exists()
        assert other_cache.exists()

        # Invalidate only sample_rom
        rom_cache.invalidate_rom_cache(str(sample_rom))

        # Verify sample_rom cache cleared but other_rom untouched
        assert not sample_cache.exists()
        assert other_cache.exists()

    def test_invalidate_returns_zero_when_cache_disabled(
        self, tmp_path: Path
    ) -> None:
        """invalidate_rom_cache() returns 0 when caching is disabled."""
        from core.services.rom_cache import ROMCache

        mock_settings = MagicMock()
        mock_settings.get_cache_enabled.return_value = False

        cache = ROMCache(mock_settings)

        result = cache.invalidate_rom_cache("/some/rom.sfc")
        assert result == 0

    def test_invalidate_handles_nonexistent_rom(
        self, rom_cache
    ) -> None:
        """invalidate_rom_cache() handles nonexistent ROM gracefully."""
        # Should not raise, just return 0
        removed = rom_cache.invalidate_rom_cache("/nonexistent/rom.sfc")
        # May be 0 or more depending on any cleanup
        assert removed >= 0


class TestInjectionCacheIntegration:
    """Tests for cache invalidation integration with injection."""

    def test_on_worker_finished_calls_invalidation_on_success(self) -> None:
        """_on_worker_finished calls cache invalidation on successful injection."""
        from core.managers.core_operations_manager import CoreOperationsManager

        # Create manager with mocked dependencies
        with patch.object(CoreOperationsManager, '__init__', lambda self: None):
            manager = CoreOperationsManager()
            manager._logger = MagicMock()
            manager._current_worker = MagicMock()
            manager._current_worker.params = {
                'mode': 'rom',
                'output_rom': '/path/to/output.sfc'
            }

            # Mock the methods we don't want to test
            manager._handle_worker_completion = MagicMock()
            manager.injection_finished = MagicMock()

            # Mock the cache (now accessed via _ensure_rom_cache)
            mock_cache = MagicMock()
            mock_cache.invalidate_rom_cache.return_value = 5

            with patch.object(manager, '_ensure_rom_cache', return_value=mock_cache):
                manager._on_worker_finished(success=True, message="OK")

            # Verify cache invalidation was called
            mock_cache.invalidate_rom_cache.assert_called_once_with('/path/to/output.sfc')

    def test_on_worker_finished_skips_invalidation_on_failure(self) -> None:
        """_on_worker_finished does not invalidate cache on failed injection."""
        from core.managers.core_operations_manager import CoreOperationsManager

        with patch.object(CoreOperationsManager, '__init__', lambda self: None):
            manager = CoreOperationsManager()
            manager._logger = MagicMock()
            manager._current_worker = MagicMock()
            manager._current_worker.params = {
                'mode': 'rom',
                'output_rom': '/path/to/output.sfc'
            }

            manager._handle_worker_completion = MagicMock()
            manager.injection_finished = MagicMock()

            mock_cache = MagicMock()

            with patch('core.di_container.inject', return_value=mock_cache):
                manager._on_worker_finished(success=False, message="Error")

            # Verify cache invalidation was NOT called
            mock_cache.invalidate_rom_cache.assert_not_called()

    def test_invalidation_skipped_for_vram_mode(self) -> None:
        """_invalidate_injection_cache skips invalidation for VRAM injection."""
        from core.managers.core_operations_manager import CoreOperationsManager

        with patch.object(CoreOperationsManager, '__init__', lambda self: None):
            manager = CoreOperationsManager()
            manager._logger = MagicMock()
            manager._current_worker = MagicMock()
            manager._current_worker.params = {
                'mode': 'vram',  # VRAM mode, not ROM
                'output_vram': '/path/to/output.vram'
            }

            mock_cache = MagicMock()

            with patch('core.di_container.inject', return_value=mock_cache):
                manager._invalidate_injection_cache()

            # Verify cache invalidation was NOT called for VRAM
            mock_cache.invalidate_rom_cache.assert_not_called()

    def test_invalidation_handles_missing_worker(self) -> None:
        """_invalidate_injection_cache handles case when worker is None."""
        from core.managers.core_operations_manager import CoreOperationsManager

        with patch.object(CoreOperationsManager, '__init__', lambda self: None):
            manager = CoreOperationsManager()
            manager._logger = MagicMock()
            manager._current_worker = None  # No worker

            # Should not raise
            manager._invalidate_injection_cache()

    def test_invalidation_handles_missing_params(self) -> None:
        """_invalidate_injection_cache handles case when worker has no params."""
        from core.managers.core_operations_manager import CoreOperationsManager

        with patch.object(CoreOperationsManager, '__init__', lambda self: None):
            manager = CoreOperationsManager()
            manager._logger = MagicMock()
            manager._current_worker = MagicMock(spec=[])  # No params attribute

            # Should not raise
            manager._invalidate_injection_cache()
