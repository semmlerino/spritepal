"""
Comprehensive tests for OptimizedROMExtractor and DecompressionCache.

Tests cover:
- Cache operations (put/get, LRU eviction, mtime validation)
- Sprite extraction (single and parallel)
- ROM scanning
- Error handling and edge cases
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch

import pytest
from PIL import Image

from core.optimized_rom_extractor import (
    CacheEntry,
    DecompressionCache,
    ExtractionResult,
    OptimizedROMExtractor,
)

if TYPE_CHECKING:
    from collections.abc import Generator

pytestmark = pytest.mark.headless


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def cache() -> DecompressionCache:
    """Create a fresh DecompressionCache for testing."""
    return DecompressionCache()


@pytest.fixture
def small_cache() -> DecompressionCache:
    """Create a cache with small limits for testing eviction."""
    return DecompressionCache(max_entries=3, max_memory_bytes=1024)


@pytest.fixture
def test_rom(tmp_path: Path) -> Path:
    """Create a test ROM file with known content."""
    rom_path = tmp_path / "test.rom"
    # Create a ROM with some test data (4KB)
    rom_data = bytes(range(256)) * 16
    rom_path.write_bytes(rom_data)
    return rom_path


@pytest.fixture
def mock_hal_compressor() -> Generator[MagicMock, None, None]:
    """Mock HALCompressor to avoid real decompression."""
    with patch("core.optimized_rom_extractor.ROMExtractor.__init__") as mock_init:
        mock_init.return_value = None
        yield mock_init


@pytest.fixture
def mock_rom_cache() -> Mock:
    """Create a mock ROMCacheProtocol."""
    cache = Mock()
    cache.get_cached_offsets.return_value = []
    cache.cache_offset.return_value = None
    return cache


@pytest.fixture
def extractor(mock_rom_cache: Mock) -> OptimizedROMExtractor:
    """Create an OptimizedROMExtractor with mocked dependencies."""
    with patch("core.optimized_rom_extractor.ROMExtractor.__init__"):
        ext = OptimizedROMExtractor(
            rom_cache=mock_rom_cache,
            enable_parallel=True,
            max_workers=2
        )
        # Mock the HAL compressor
        ext.hal_compressor = Mock()
        ext.hal_compressor.decompress_from_rom.return_value = b"\x00" * 128
        return ext


# =============================================================================
# DecompressionCache - Basic Operations
# =============================================================================


class TestDecompressionCacheBasics:
    """Tests for basic cache operations."""

    def test_cache_put_and_get(self, cache: DecompressionCache, test_rom: Path) -> None:
        """Store and retrieve cached data successfully."""
        test_data = b"test sprite data"
        cache.put(str(test_rom), 0x1000, test_data)

        result = cache.get(str(test_rom), 0x1000)
        assert result == test_data

    def test_cache_miss_returns_none(self, cache: DecompressionCache, test_rom: Path) -> None:
        """Accessing non-existent key returns None."""
        result = cache.get(str(test_rom), 0x9999)
        assert result is None

    def test_cache_hit_increments_counter(self, cache: DecompressionCache, test_rom: Path) -> None:
        """Successful retrieves increment hits counter."""
        cache.put(str(test_rom), 0x1000, b"data")
        initial_hits = cache.hits

        cache.get(str(test_rom), 0x1000)

        assert cache.hits == initial_hits + 1

    def test_cache_miss_increments_counter(self, cache: DecompressionCache, test_rom: Path) -> None:
        """Failed retrieves increment misses counter."""
        initial_misses = cache.misses

        cache.get(str(test_rom), 0x9999)

        assert cache.misses == initial_misses + 1

    def test_cache_clear_resets_all(self, cache: DecompressionCache, test_rom: Path) -> None:
        """clear() resets cache, size tracking, and statistics."""
        cache.put(str(test_rom), 0x1000, b"data")
        cache.get(str(test_rom), 0x1000)  # Hit
        cache.get(str(test_rom), 0x9999)  # Miss

        cache.clear()

        assert cache.entry_count == 0
        assert cache.memory_usage == 0
        assert cache.hits == 0
        assert cache.misses == 0


# =============================================================================
# DecompressionCache - mtime Validation
# =============================================================================


class TestDecompressionCacheMtimeValidation:
    """Tests for mtime-based cache invalidation."""

    def test_cache_invalidation_on_mtime_change(
        self, cache: DecompressionCache, test_rom: Path
    ) -> None:
        """Cache entry is invalidated when file mtime changes."""
        cache.put(str(test_rom), 0x1000, b"original data")

        # Modify the file to change mtime
        time.sleep(0.01)  # Ensure mtime difference
        test_rom.write_bytes(b"modified content")

        result = cache.get(str(test_rom), 0x1000)
        assert result is None

    def test_cache_invalidation_on_file_not_found(
        self, cache: DecompressionCache, tmp_path: Path
    ) -> None:
        """Entry removed and None returned when file no longer exists."""
        rom_path = tmp_path / "temp.rom"
        rom_path.write_bytes(b"temp data")
        cache.put(str(rom_path), 0x1000, b"cached data")

        # Delete the file
        rom_path.unlink()

        result = cache.get(str(rom_path), 0x1000)
        assert result is None
        assert cache.entry_count == 0

    def test_cache_hit_updates_last_access_time(
        self, cache: DecompressionCache, test_rom: Path
    ) -> None:
        """Accessing entry updates last_access timestamp for LRU ordering."""
        cache.put(str(test_rom), 0x1000, b"data")
        # Get direct access to entry for testing
        key = (str(test_rom), 0x1000)
        initial_access = cache._cache[key].last_access

        time.sleep(0.01)
        cache.get(str(test_rom), 0x1000)

        assert cache._cache[key].last_access > initial_access

    def test_cache_put_fails_gracefully_on_stat_error(
        self, cache: DecompressionCache
    ) -> None:
        """put() logs warning and doesn't cache if stat() fails."""
        # Use a path that doesn't exist
        fake_path = "/nonexistent/path/to/rom.bin"
        cache.put(fake_path, 0x1000, b"data")

        assert cache.entry_count == 0


# =============================================================================
# DecompressionCache - LRU Eviction
# =============================================================================


class TestDecompressionCacheLRUEviction:
    """Tests for LRU eviction behavior."""

    def test_lru_eviction_on_max_entries_exceeded(
        self, small_cache: DecompressionCache, tmp_path: Path
    ) -> None:
        """When cache reaches MAX_ENTRIES, LRU entry is evicted."""
        # Create test files
        roms = []
        for i in range(4):
            rom = tmp_path / f"rom{i}.bin"
            rom.write_bytes(b"x" * 100)
            roms.append(rom)

        # Fill cache to max (3 entries)
        for i in range(3):
            small_cache.put(str(roms[i]), 0x1000, b"data" * 10)
            time.sleep(0.01)  # Ensure different access times

        assert small_cache.entry_count == 3

        # Add 4th entry - should evict oldest
        small_cache.put(str(roms[3]), 0x1000, b"data" * 10)

        assert small_cache.entry_count == 3
        # First entry should be evicted
        assert small_cache.get(str(roms[0]), 0x1000) is None

    def test_lru_eviction_on_memory_limit_exceeded(
        self, tmp_path: Path
    ) -> None:
        """When memory usage exceeds MAX_MEMORY_BYTES, LRU entry evicted."""
        # Cache with 500 byte memory limit
        cache = DecompressionCache(max_entries=100, max_memory_bytes=500)

        rom = tmp_path / "rom.bin"
        rom.write_bytes(b"x" * 1000)

        # Add entries that together exceed memory limit
        cache.put(str(rom), 0x1000, b"a" * 200)
        time.sleep(0.01)
        cache.put(str(rom), 0x2000, b"b" * 200)
        time.sleep(0.01)

        # This should trigger eviction of first entry
        cache.put(str(rom), 0x3000, b"c" * 200)

        # Memory should be under limit
        assert cache.memory_usage <= 500

    def test_lru_eviction_removes_oldest_entry(
        self, small_cache: DecompressionCache, tmp_path: Path
    ) -> None:
        """Eviction removes entry with oldest last_access time."""
        rom = tmp_path / "rom.bin"
        rom.write_bytes(b"x" * 1000)

        # Add 3 entries with different access times
        small_cache.put(str(rom), 0x1000, b"first")
        time.sleep(0.01)
        small_cache.put(str(rom), 0x2000, b"second")
        time.sleep(0.01)
        small_cache.put(str(rom), 0x3000, b"third")
        time.sleep(0.01)

        # Access first entry to make it more recent
        small_cache.get(str(rom), 0x1000)
        time.sleep(0.01)

        # Add 4th entry - should evict 0x2000 (now oldest)
        small_cache.put(str(rom), 0x4000, b"fourth")

        assert small_cache.get(str(rom), 0x1000) is not None  # Accessed recently
        assert small_cache.get(str(rom), 0x2000) is None  # Evicted
        assert small_cache.get(str(rom), 0x3000) is not None

    def test_lru_eviction_stops_when_cache_empty(
        self, cache: DecompressionCache
    ) -> None:
        """_evict_lru() returns gracefully when cache is empty."""
        # Should not raise
        cache._evict_lru()
        assert cache.entry_count == 0

    def test_entry_exceeds_memory_limit(
        self, tmp_path: Path
    ) -> None:
        """Single entry larger than MAX_MEMORY_BYTES not cached."""
        cache = DecompressionCache(max_entries=100, max_memory_bytes=100)

        rom = tmp_path / "rom.bin"
        rom.write_bytes(b"x" * 1000)

        # Try to cache data larger than memory limit
        cache.put(str(rom), 0x1000, b"x" * 200)

        assert cache.entry_count == 0


# =============================================================================
# DecompressionCache - Edge Cases
# =============================================================================


class TestDecompressionCacheEdgeCases:
    """Tests for cache edge cases."""

    def test_cache_entry_replacement(
        self, cache: DecompressionCache, test_rom: Path
    ) -> None:
        """Putting entry with existing key removes old entry first."""
        cache.put(str(test_rom), 0x1000, b"original")
        original_size = cache.memory_usage

        cache.put(str(test_rom), 0x1000, b"replacement data longer")

        # Size should reflect new data
        assert cache.memory_usage != original_size
        result = cache.get(str(test_rom), 0x1000)
        assert result == b"replacement data longer"

    def test_entry_size_tracking_accuracy(
        self, cache: DecompressionCache, test_rom: Path
    ) -> None:
        """Total size correctly tracked after put/remove operations."""
        cache.put(str(test_rom), 0x1000, b"a" * 100)
        cache.put(str(test_rom), 0x2000, b"b" * 200)

        assert cache.memory_usage == 300

        # Remove one entry via clear
        cache._remove((str(test_rom), 0x1000))

        assert cache.memory_usage == 200

    def test_cache_with_one_entry_limit(self, tmp_path: Path) -> None:
        """max_entries=1 limits cache to single entry."""
        cache = DecompressionCache(max_entries=1, max_memory_bytes=10000)
        rom = tmp_path / "rom.bin"
        rom.write_bytes(b"x" * 100)

        cache.put(str(rom), 0x1000, b"first")
        cache.put(str(rom), 0x2000, b"second")

        # Only most recent entry should remain
        assert cache.entry_count == 1
        assert cache.get(str(rom), 0x1000) is None
        assert cache.get(str(rom), 0x2000) == b"second"

    def test_cache_statistics_consistency(
        self, cache: DecompressionCache, test_rom: Path
    ) -> None:
        """hits + misses match total requests accurately."""
        cache.put(str(test_rom), 0x1000, b"data")

        # Generate some hits and misses
        cache.get(str(test_rom), 0x1000)  # Hit
        cache.get(str(test_rom), 0x1000)  # Hit
        cache.get(str(test_rom), 0x9999)  # Miss
        cache.get(str(test_rom), 0x8888)  # Miss

        assert cache.hits == 2
        assert cache.misses == 2


# =============================================================================
# OptimizedROMExtractor - Initialization
# =============================================================================


class TestOptimizedROMExtractorInit:
    """Tests for extractor initialization."""

    def test_init_with_rom_cache(self, mock_rom_cache: Mock) -> None:
        """Initializer accepts ROMCacheProtocol and stores it."""
        with patch("core.optimized_rom_extractor.ROMExtractor.__init__"):
            _ext = OptimizedROMExtractor(rom_cache=mock_rom_cache)
            # Verify super().__init__ was called with the cache
            # (extractor stores it via parent class)

    def test_init_with_parallel_enabled(self, mock_rom_cache: Mock) -> None:
        """enable_parallel=True sets flag correctly."""
        with patch("core.optimized_rom_extractor.ROMExtractor.__init__"):
            ext = OptimizedROMExtractor(
                rom_cache=mock_rom_cache,
                enable_parallel=True
            )
            assert ext.enable_parallel is True

    def test_init_with_parallel_disabled(self, mock_rom_cache: Mock) -> None:
        """enable_parallel=False disables parallel extraction."""
        with patch("core.optimized_rom_extractor.ROMExtractor.__init__"):
            ext = OptimizedROMExtractor(
                rom_cache=mock_rom_cache,
                enable_parallel=False
            )
            assert ext.enable_parallel is False

    def test_init_with_custom_max_workers(self, mock_rom_cache: Mock) -> None:
        """max_workers parameter controls thread pool size."""
        with patch("core.optimized_rom_extractor.ROMExtractor.__init__"):
            ext = OptimizedROMExtractor(
                rom_cache=mock_rom_cache,
                max_workers=8
            )
            assert ext.max_workers == 8

    def test_init_creates_empty_caches(self, mock_rom_cache: Mock) -> None:
        """Initialization creates empty caches."""
        with patch("core.optimized_rom_extractor.ROMExtractor.__init__"):
            ext = OptimizedROMExtractor(rom_cache=mock_rom_cache)
            assert ext._decompression_cache.entry_count == 0
            assert len(ext._rom_readers) == 0


# =============================================================================
# OptimizedROMExtractor - ROM Reader Management
# =============================================================================


class TestOptimizedROMExtractorROMReader:
    """Tests for ROM reader management."""

    def test_get_rom_reader_creates_new_reader(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """get_rom_reader() creates MemoryMappedROMReader for new path."""
        with patch(
            "core.optimized_rom_extractor.optimize_rom_operations"
        ) as mock_optimize:
            mock_reader = Mock()
            mock_optimize.return_value = mock_reader

            reader = extractor.get_rom_reader(str(test_rom))

            mock_optimize.assert_called_once_with(str(test_rom))
            assert reader == mock_reader

    def test_get_rom_reader_reuses_existing(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Subsequent calls for same path return cached reader."""
        with patch(
            "core.optimized_rom_extractor.optimize_rom_operations"
        ) as mock_optimize:
            mock_reader = Mock()
            mock_optimize.return_value = mock_reader

            reader1 = extractor.get_rom_reader(str(test_rom))
            reader2 = extractor.get_rom_reader(str(test_rom))

            # Should only create reader once
            assert mock_optimize.call_count == 1
            assert reader1 is reader2

    def test_get_rom_reader_different_paths(
        self, extractor: OptimizedROMExtractor, tmp_path: Path
    ) -> None:
        """Multiple ROM paths each get their own reader."""
        rom1 = tmp_path / "rom1.bin"
        rom2 = tmp_path / "rom2.bin"
        rom1.write_bytes(b"data1")
        rom2.write_bytes(b"data2")

        with patch(
            "core.optimized_rom_extractor.optimize_rom_operations"
        ) as mock_optimize:
            mock_optimize.side_effect = [Mock(), Mock()]

            reader1 = extractor.get_rom_reader(str(rom1))
            reader2 = extractor.get_rom_reader(str(rom2))

            assert mock_optimize.call_count == 2
            assert reader1 is not reader2


# =============================================================================
# OptimizedROMExtractor - extract_sprite_data
# =============================================================================


class TestExtractSpriteData:
    """Tests for single sprite extraction."""

    def test_extract_sprite_data_success(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Valid offset extracts sprite data and caches it."""
        expected_data = b"decompressed sprite data"
        extractor.hal_compressor.decompress_from_rom.return_value = expected_data

        result = extractor.extract_sprite_data(str(test_rom), 0x100)

        assert result == expected_data
        extractor.hal_compressor.decompress_from_rom.assert_called_once()

    def test_extract_sprite_data_negative_offset(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Negative offset raises ValueError."""
        with pytest.raises(ValueError, match="Invalid negative offset"):
            extractor.extract_sprite_data(str(test_rom), -1)

    def test_extract_sprite_data_offset_exceeds_rom(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Offset >= rom_size raises ValueError."""
        rom_size = test_rom.stat().st_size

        with pytest.raises(ValueError, match="exceeds ROM size"):
            extractor.extract_sprite_data(str(test_rom), rom_size + 1000)

    def test_extract_sprite_data_uses_cache(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Cache hit returns cached data without decompression."""
        # First extraction
        extractor.hal_compressor.decompress_from_rom.return_value = b"data"
        extractor.extract_sprite_data(str(test_rom), 0x100)

        # Reset mock
        extractor.hal_compressor.decompress_from_rom.reset_mock()

        # Second extraction should use cache
        result = extractor.extract_sprite_data(str(test_rom), 0x100)

        assert result == b"data"
        extractor.hal_compressor.decompress_from_rom.assert_not_called()

    def test_extract_sprite_data_cache_bypass(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """use_cache=False bypasses cache entirely."""
        # Prime the cache
        extractor.hal_compressor.decompress_from_rom.return_value = b"cached"
        extractor.extract_sprite_data(str(test_rom), 0x100)

        # Extract with cache bypass
        extractor.hal_compressor.decompress_from_rom.return_value = b"fresh"
        result = extractor.extract_sprite_data(
            str(test_rom), 0x100, use_cache=False
        )

        assert result == b"fresh"

    def test_extract_sprite_data_decompression_error(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Decompression failure is caught and re-raised."""
        extractor.hal_compressor.decompress_from_rom.side_effect = RuntimeError(
            "Decompression failed"
        )

        with pytest.raises(RuntimeError, match="Decompression failed"):
            extractor.extract_sprite_data(str(test_rom), 0x100)


# =============================================================================
# OptimizedROMExtractor - extract_multiple_sprites
# =============================================================================


class TestExtractMultipleSprites:
    """Tests for parallel sprite extraction."""

    def test_extract_multiple_single_offset(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Single offset uses sequential (not parallel) extraction."""
        extractor.hal_compressor.decompress_from_rom.return_value = b"data"

        results = extractor.extract_multiple_sprites(str(test_rom), [0x100])

        assert len(results) == 1
        assert 0x100 in results
        assert results[0x100].success is True

    def test_extract_multiple_parallel_enabled(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Multiple offsets with parallel=True uses ThreadPoolExecutor."""
        extractor.enable_parallel = True
        extractor.hal_compressor.decompress_from_rom.return_value = b"data"

        results = extractor.extract_multiple_sprites(
            str(test_rom), [0x100, 0x200, 0x300]
        )

        assert len(results) == 3
        assert all(r.success for r in results.values())

    def test_extract_multiple_parallel_disabled(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Multiple offsets with parallel=False uses sequential extraction."""
        extractor.enable_parallel = False
        extractor.hal_compressor.decompress_from_rom.return_value = b"data"

        results = extractor.extract_multiple_sprites(
            str(test_rom), [0x100, 0x200]
        )

        assert len(results) == 2

    def test_extract_multiple_some_fail(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Some extractions fail, results marked with success=False and error set."""
        def side_effect(path: str, offset: int) -> bytes:
            if offset == 0x200:
                raise RuntimeError("Failed at 0x200")
            return b"data"

        extractor.hal_compressor.decompress_from_rom.side_effect = side_effect

        results = extractor.extract_multiple_sprites(
            str(test_rom), [0x100, 0x200, 0x300]
        )

        assert results[0x100].success is True
        assert results[0x200].success is False
        assert "Failed at 0x200" in str(results[0x200].error)
        assert results[0x300].success is True

    def test_extract_multiple_empty_offsets_list(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Empty offset list returns empty results dict."""
        results = extractor.extract_multiple_sprites(str(test_rom), [])

        assert results == {}

    def test_extract_multiple_with_configs(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Extraction uses provided configs from sprite_configs dict."""
        extractor.hal_compressor.decompress_from_rom.return_value = b"data"

        configs = {
            0x100: {"width": 16, "height": 16},
            0x200: {"width": 32, "height": 32},
        }

        results = extractor.extract_multiple_sprites(
            str(test_rom), [0x100, 0x200], sprite_configs=configs
        )

        assert len(results) == 2


# =============================================================================
# OptimizedROMExtractor - _extract_single_sprite
# =============================================================================


class TestExtractSingleSprite:
    """Tests for single sprite extraction helper."""

    def test_extract_single_sprite_success(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Valid sprite extracted and returned with success=True."""
        # Return enough data for MIN_SPRITE_TILES
        extractor.hal_compressor.decompress_from_rom.return_value = b"\x00" * 128

        result = extractor._extract_single_sprite(str(test_rom), 0x100)

        assert result.success is True
        assert result.offset == 0x100
        assert result.data is not None

    def test_extract_single_sprite_renders_image(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Extracted data converted to image using TileRenderer."""
        # Return enough data for multiple tiles (MIN_SPRITE_TILES = 4)
        from utils.constants import BYTES_PER_TILE, MIN_SPRITE_TILES
        extractor.hal_compressor.decompress_from_rom.return_value = (
            b"\x00" * (BYTES_PER_TILE * (MIN_SPRITE_TILES + 1))
        )

        with patch("core.optimized_rom_extractor.TileRenderer") as MockRenderer:
            mock_instance = Mock()
            mock_instance.render_tiles.return_value = Image.new("RGB", (64, 64))
            MockRenderer.return_value = mock_instance

            result = extractor._extract_single_sprite(str(test_rom), 0x100)

            assert result.image is not None
            mock_instance.render_tiles.assert_called_once()

    def test_extract_single_sprite_too_small(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """sprite_data with < MIN_SPRITE_TILES doesn't render image."""
        # Return data smaller than MIN_SPRITE_TILES
        extractor.hal_compressor.decompress_from_rom.return_value = b"\x00" * 10

        result = extractor._extract_single_sprite(str(test_rom), 0x100)

        assert result.success is True
        assert result.image is None  # Too small to render

    def test_extract_single_sprite_decompression_fails(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Decompression error caught, result has success=False."""
        extractor.hal_compressor.decompress_from_rom.side_effect = RuntimeError(
            "Decompression error"
        )

        result = extractor._extract_single_sprite(str(test_rom), 0x100)

        assert result.success is False
        assert "Decompression error" in str(result.error)

    def test_extract_single_sprite_timing_measured(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """time_ms calculated and returned in result."""
        extractor.hal_compressor.decompress_from_rom.return_value = b"\x00" * 128

        result = extractor._extract_single_sprite(str(test_rom), 0x100)

        assert result.time_ms >= 0


# =============================================================================
# OptimizedROMExtractor - scan_rom_optimized
# =============================================================================


class TestScanROMOptimized:
    """Tests for ROM scanning."""

    def test_scan_rom_with_pattern_filter(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Pattern search delegated to reader.search_pattern()."""
        mock_reader = Mock()
        mock_reader.search_pattern.return_value = [0x100, 0x200]

        with patch.object(extractor, "get_rom_reader", return_value=mock_reader):
            results = extractor.scan_rom_optimized(
                str(test_rom), pattern_filter=b"\x10\x00"
            )

        assert results == [0x100, 0x200]
        mock_reader.search_pattern.assert_called_once()

    def test_scan_rom_without_pattern(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Scans for HAL signatures using batch reader."""
        mock_reader = Mock()
        mock_reader.file_size = 1024
        mock_batch = Mock()
        # Return data that looks like sprite (starts with 0x10)
        mock_batch.read.side_effect = lambda offset, size: (
            b"\x10\x00\x00\x00" + b"\x00" * 12
            if offset == 0
            else b"\x00" * 16
        )

        # Properly mock context manager
        context_manager = MagicMock()
        context_manager.__enter__.return_value = mock_batch
        context_manager.__exit__.return_value = None
        mock_reader.batch_reader.return_value = context_manager

        with patch.object(extractor, "get_rom_reader", return_value=mock_reader):
            results = extractor.scan_rom_optimized(str(test_rom), step=0x100)

        assert 0 in results  # First offset should be detected

    def test_scan_rom_custom_start_offset(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Start offset parameter respected in scan."""
        mock_reader = Mock()
        mock_reader.file_size = 0x1000  # Large enough for start_offset
        mock_batch = Mock()
        mock_batch.read.return_value = b"\x00" * 16

        # Properly mock context manager
        context_manager = MagicMock()
        context_manager.__enter__.return_value = mock_batch
        context_manager.__exit__.return_value = None
        mock_reader.batch_reader.return_value = context_manager

        with patch.object(extractor, "get_rom_reader", return_value=mock_reader):
            extractor.scan_rom_optimized(
                str(test_rom), start_offset=0x500, end_offset=0x600, step=0x100
            )

        # Verify first read was at start_offset
        calls = mock_batch.read.call_args_list
        assert len(calls) > 0
        assert calls[0][0][0] == 0x500

    def test_scan_rom_custom_end_offset(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """End offset parameter limits scan range."""
        mock_reader = Mock()
        mock_reader.file_size = 10000
        mock_batch = Mock()
        mock_batch.read.return_value = b"\x00" * 16

        # Properly mock context manager
        context_manager = MagicMock()
        context_manager.__enter__.return_value = mock_batch
        context_manager.__exit__.return_value = None
        mock_reader.batch_reader.return_value = context_manager

        with patch.object(extractor, "get_rom_reader", return_value=mock_reader):
            extractor.scan_rom_optimized(
                str(test_rom), start_offset=0, end_offset=0x400, step=0x100
            )

        # Should only scan 4 positions (0, 0x100, 0x200, 0x300)
        assert mock_batch.read.call_count == 4


# =============================================================================
# OptimizedROMExtractor - _looks_like_sprite
# =============================================================================


class TestLooksLikeSprite:
    """Tests for sprite detection heuristics."""

    def test_looks_like_sprite_too_short(
        self, extractor: OptimizedROMExtractor
    ) -> None:
        """Data < 4 bytes returns False."""
        assert extractor._looks_like_sprite(b"\x10\x00") is False

    def test_looks_like_sprite_all_zeros(
        self, extractor: OptimizedROMExtractor
    ) -> None:
        """b'\\x00\\x00\\x00\\x00' returns False."""
        assert extractor._looks_like_sprite(b"\x00\x00\x00\x00") is False

    def test_looks_like_sprite_compression_marker_0x00(
        self, extractor: OptimizedROMExtractor
    ) -> None:
        """First byte 0x00 (with non-zero others) returns True."""
        assert extractor._looks_like_sprite(b"\x00\x01\x02\x03") is True

    def test_looks_like_sprite_compression_marker_0x10(
        self, extractor: OptimizedROMExtractor
    ) -> None:
        """First byte 0x10 returns True."""
        assert extractor._looks_like_sprite(b"\x10\x00\x00\x00") is True

    def test_looks_like_sprite_compression_marker_0x20(
        self, extractor: OptimizedROMExtractor
    ) -> None:
        """First byte 0x20 returns True."""
        assert extractor._looks_like_sprite(b"\x20\x00\x00\x00") is True

    def test_looks_like_sprite_non_marker(
        self, extractor: OptimizedROMExtractor
    ) -> None:
        """Data without markers returns False."""
        assert extractor._looks_like_sprite(b"\xFF\x01\x02\x03") is False


# =============================================================================
# OptimizedROMExtractor - Cache Statistics
# =============================================================================


class TestCacheStatistics:
    """Tests for cache statistics."""

    def test_get_cache_stats_empty_cache(
        self, extractor: OptimizedROMExtractor
    ) -> None:
        """Empty cache returns zeros for hits/misses."""
        stats = extractor.get_cache_stats()

        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0
        assert stats["cached_sprites"] == 0

    def test_get_cache_stats_with_activity(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Cache stats reflect hits, misses, and entries."""
        extractor.hal_compressor.decompress_from_rom.return_value = b"data"

        # Generate activity
        extractor.extract_sprite_data(str(test_rom), 0x100)  # Miss + cache
        extractor.extract_sprite_data(str(test_rom), 0x100)  # Hit
        extractor.extract_sprite_data(str(test_rom), 0x200)  # Miss + cache

        stats = extractor.get_cache_stats()

        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 2
        assert stats["cached_sprites"] == 2

    def test_get_cache_stats_hit_rate_calculation(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """hit_rate = hits / (hits + misses), handles zero division."""
        extractor.hal_compressor.decompress_from_rom.return_value = b"data"

        extractor.extract_sprite_data(str(test_rom), 0x100)  # Miss
        extractor.extract_sprite_data(str(test_rom), 0x100)  # Hit
        extractor.extract_sprite_data(str(test_rom), 0x100)  # Hit

        stats = extractor.get_cache_stats()

        # 2 hits, 1 miss = 2/3 = 0.666...
        assert abs(stats["hit_rate"] - 2/3) < 0.01

    def test_get_cache_stats_rom_readers_count(
        self, extractor: OptimizedROMExtractor, tmp_path: Path
    ) -> None:
        """rom_readers count matches _rom_readers dict size."""
        rom1 = tmp_path / "rom1.bin"
        rom2 = tmp_path / "rom2.bin"
        rom1.write_bytes(b"data")
        rom2.write_bytes(b"data")

        with patch(
            "core.optimized_rom_extractor.optimize_rom_operations"
        ) as mock:
            mock.return_value = Mock()
            extractor.get_rom_reader(str(rom1))
            extractor.get_rom_reader(str(rom2))

        stats = extractor.get_cache_stats()
        assert stats["rom_readers"] == 2


# =============================================================================
# OptimizedROMExtractor - clear_caches
# =============================================================================


class TestClearCaches:
    """Tests for cache clearing."""

    def test_clear_caches_clears_decompression(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """clear_caches() calls _decompression_cache.clear()."""
        extractor.hal_compressor.decompress_from_rom.return_value = b"data"
        extractor.extract_sprite_data(str(test_rom), 0x100)

        extractor.clear_caches()

        assert extractor._decompression_cache.entry_count == 0

    def test_clear_caches_clears_rom_readers(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """clear_caches() clears _rom_readers dict."""
        with patch(
            "core.optimized_rom_extractor.optimize_rom_operations"
        ) as mock:
            mock.return_value = Mock()
            extractor.get_rom_reader(str(test_rom))

        assert len(extractor._rom_readers) == 1

        extractor.clear_caches()

        assert len(extractor._rom_readers) == 0

    def test_clear_caches_after_activity(
        self, extractor: OptimizedROMExtractor, test_rom: Path
    ) -> None:
        """Stats reset to zero after clear."""
        extractor.hal_compressor.decompress_from_rom.return_value = b"data"
        extractor.extract_sprite_data(str(test_rom), 0x100)
        extractor.extract_sprite_data(str(test_rom), 0x100)

        extractor.clear_caches()

        stats = extractor.get_cache_stats()
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0


# =============================================================================
# ExtractionResult Dataclass
# =============================================================================


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_extraction_result_success_fields(self) -> None:
        """Successful result has correct fields."""
        result = ExtractionResult(
            offset=0x1000,
            success=True,
            data=b"sprite data",
            image=Image.new("RGB", (64, 64)),
            time_ms=12.5
        )

        assert result.offset == 0x1000
        assert result.success is True
        assert result.data == b"sprite data"
        assert result.image is not None
        assert result.error is None
        assert result.time_ms == 12.5

    def test_extraction_result_failure_fields(self) -> None:
        """Failed result has error field set."""
        result = ExtractionResult(
            offset=0x2000,
            success=False,
            error="Decompression failed"
        )

        assert result.offset == 0x2000
        assert result.success is False
        assert result.data is None
        assert result.error == "Decompression failed"


# =============================================================================
# CacheEntry Dataclass
# =============================================================================


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_cache_entry_fields(self) -> None:
        """CacheEntry has all required fields."""
        entry = CacheEntry(
            data=b"test data",
            mtime=1234567890.0,
            size=9
        )

        assert entry.data == b"test data"
        assert entry.mtime == 1234567890.0
        assert entry.size == 9
        assert entry.last_access > 0  # Auto-set by default_factory

    def test_cache_entry_last_access_default(self) -> None:
        """last_access defaults to current time."""
        before = time.time()
        entry = CacheEntry(data=b"x", mtime=0, size=1)
        after = time.time()

        assert before <= entry.last_access <= after
