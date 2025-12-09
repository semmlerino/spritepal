"""
Test ROM cache exception handling improvements.

Tests specific file I/O exceptions and error propagation scenarios
for the JSON-based ROM cache implementation.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.rom_cache import ROMCache

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.parallel_safe,
    pytest.mark.rom_data,
    pytest.mark.cache,
    pytest.mark.ci_safe,
]

class TestROMCacheExceptionHandling:
    """Test ROM cache exception handling and error propagation"""

    @pytest.fixture
    def temp_cache_path(self):
        """Create a temporary cache directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def cache_with_temp_path(self, temp_cache_path):
        """Create cache instance with temporary path"""
        return ROMCache(cache_dir=str(temp_cache_path))

    def test_file_permission_error_handling(self, cache_with_temp_path):
        """Test handling of permission errors when accessing cache files"""
        cache = cache_with_temp_path

        # Mock permission error during file operations
        with patch("builtins.open", side_effect=PermissionError("Permission denied to cache file")):
            result = cache.save_sprite_locations("test.rom", {"sprites": []})
            # Cache should gracefully handle permission errors and return False
            assert result is False

    def test_file_corruption_error_handling(self, cache_with_temp_path):
        """Test handling of corrupted cache files"""
        cache = cache_with_temp_path

        # Create a corrupted cache file
        rom_hash = cache._get_rom_hash("test.rom")
        cache_file = cache._get_cache_file_path(rom_hash, "sprites")

        # Write invalid JSON to simulate corruption
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w") as f:
            f.write("invalid json {{{")

        # Cache should handle corruption gracefully and return None
        result = cache.get_sprite_locations("test.rom")
        assert result is None

    def test_disk_full_error_handling(self, cache_with_temp_path):
        """Test handling of disk full errors during cache operations"""
        cache = cache_with_temp_path

        # Mock disk full error during file write
        with patch("builtins.open", side_effect=OSError("No space left on device")):
            result = cache.save_sprite_locations("test.rom", {"sprites": []})
            # Cache should gracefully handle disk full errors and return False
            assert result is False

    def test_readonly_filesystem_error_handling(self, cache_with_temp_path):
        """Test handling of read-only filesystem errors"""
        cache = cache_with_temp_path

        # Mock read-only filesystem error
        with patch("builtins.open", side_effect=OSError("Read-only file system")):
            result = cache.save_sprite_locations("test.rom", {"sprites": []})
            # Cache should gracefully handle read-only filesystem and return False
            assert result is False

    def test_json_encoding_error_handling(self, cache_with_temp_path):
        """Test handling of JSON encoding errors"""
        cache = cache_with_temp_path

        # Create data that can't be JSON serialized
        unserializable_data = {"sprites": [{1, 2, 3}]}  # sets aren't JSON serializable

        result = cache.save_sprite_locations("test.rom", unserializable_data)
        # Cache should handle JSON encoding errors and return False
        assert result is False

    def test_file_not_found_during_read(self, cache_with_temp_path):
        """Test handling of missing cache files during read"""
        cache = cache_with_temp_path

        # Try to read from non-existent cache file
        result = cache.get_sprite_locations("nonexistent.rom")
        # Should return None gracefully
        assert result is None

    def test_partial_scan_error_resilience(self, cache_with_temp_path):
        """Test error handling in partial scan operations"""
        cache = cache_with_temp_path

        # Mock I/O error during partial scan save
        with patch("builtins.open", side_effect=OSError("I/O error")):
            result = cache.save_partial_scan_results(
                "test.rom",
                {"start": 0, "end": 100},
                [{"sprite": "data"}],
                50  # current_offset
            )
            # Should handle I/O errors gracefully
            assert result is False

    def test_concurrent_access_error_handling(self, cache_with_temp_path):
        """Test handling of concurrent access to cache files"""
        cache = cache_with_temp_path

        # Simulate file being locked by another process
        with patch("builtins.open", side_effect=OSError("Resource temporarily unavailable")):
            result = cache.save_sprite_locations("test.rom", {"sprites": []})
            # Should handle concurrent access errors gracefully
            assert result is False

    def test_cache_directory_creation_failure(self, temp_cache_path):
        """Test handling of cache directory creation failures"""
        # Try to create cache in a location where we can't create directories
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("Permission denied")):
            cache = ROMCache(cache_dir=str(temp_cache_path / "restricted"))
            # Cache should initialize but return False for enabled status
            assert not cache.cache_enabled

    def test_hash_calculation_robustness(self, cache_with_temp_path):
        """Test hash calculation with problematic file paths"""
        cache = cache_with_temp_path

        # Test with non-existent file
        rom_hash = cache._get_rom_hash("nonexistent.rom")
        # Should return a consistent hash even for non-existent files
        assert isinstance(rom_hash, str)
        assert len(rom_hash) > 0

    def test_cache_stats_with_corrupted_cache(self, cache_with_temp_path):
        """Test cache statistics calculation with corrupted cache files"""
        cache = cache_with_temp_path

        # Create some corrupted cache files
        cache_dir = cache.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Create valid cache file
        valid_file = cache_dir / "valid.json"
        with open(valid_file, "w") as f:
            json.dump({"version": "1.0", "data": {}}, f)

        # Create corrupted cache file
        corrupted_file = cache_dir / "corrupted.json"
        with open(corrupted_file, "w") as f:
            f.write("invalid json {{{")

        # Stats should handle corrupted files gracefully
        stats = cache.get_cache_stats()
        assert isinstance(stats, dict)
        assert "total_files" in stats

    def test_clear_cache_with_permission_error(self, cache_with_temp_path):
        """Test cache clearing with permission errors"""
        cache = cache_with_temp_path

        # Create a cache file
        cache_dir = cache.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        test_file = cache_dir / "test.json"
        with open(test_file, "w") as f:
            json.dump({"test": "data"}, f)

        # Mock permission error during file deletion
        with patch("pathlib.Path.unlink", side_effect=PermissionError("Permission denied")):
            # Should handle permission errors gracefully
            cleared_count = cache.clear_cache()
            # Might return 0 if no files could be cleared due to permissions
            assert isinstance(cleared_count, int)

    def test_settings_refresh_error_handling(self, cache_with_temp_path):
        """Test settings refresh with missing settings manager"""
        cache = cache_with_temp_path

        # Mock settings manager to return None (not available)
        with patch("utils.rom_cache.get_settings_manager", return_value=None):
            # Should handle missing settings manager gracefully
            cache.refresh_settings()
            # Cache should still be functional
            assert isinstance(cache.cache_enabled, bool)
