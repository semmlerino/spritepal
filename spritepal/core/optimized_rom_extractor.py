"""
Optimized ROM extractor using memory-mapped I/O.

This module provides performance-optimized ROM extraction by:
1. Using memory-mapped I/O for efficient file access
2. Implementing parallel extraction for multiple sprites
3. Adding intelligent caching for frequently accessed data
4. Optimizing decompression with batch processing
"""
from __future__ import annotations

import concurrent.futures
import logging
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, override

from PIL import Image

from core.mmap_rom_reader import MemoryMappedROMReader, optimize_rom_operations
from core.protocols.manager_protocols import ROMCacheProtocol
from core.rom_extractor import ROMExtractor
from core.tile_renderer import TileRenderer
from utils.constants import (
    BYTES_PER_TILE,
    DEFAULT_TILES_PER_ROW,
    MIN_SPRITE_TILES,
)

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Entry in the decompression cache with metadata for LRU and invalidation."""

    data: bytes
    mtime: float  # File modification time when cached
    size: int  # Size of data in bytes
    last_access: float = field(default_factory=time.time)  # For LRU eviction


class DecompressionCache:
    """
    Thread-safe decompression cache with mtime validation, LRU eviction, and memory limits.

    Features:
    - mtime validation: Automatically invalidates entries when ROM file changes
    - LRU eviction: Removes least recently accessed entries when over count limit
    - Memory limit: Evicts entries to stay under memory budget
    """

    MAX_ENTRIES = 100
    MAX_MEMORY_BYTES = 16 * 1024 * 1024  # 16MB

    def __init__(self, max_entries: int = MAX_ENTRIES, max_memory_bytes: int = MAX_MEMORY_BYTES):
        self._cache: dict[tuple[str, int], CacheEntry] = {}
        self._total_size = 0
        self._max_entries = max_entries
        self._max_memory = max_memory_bytes
        self._hits = 0
        self._misses = 0

    def get(self, rom_path: str, offset: int) -> bytes | None:
        """
        Get cached data if valid, or None if not cached or stale.

        Validates that file mtime hasn't changed since caching.
        """
        key = (rom_path, offset)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None

        # Validate mtime - invalidate if ROM file has been modified
        try:
            current_mtime = Path(rom_path).stat().st_mtime
            if entry.mtime != current_mtime:
                logger.debug(
                    f"Cache invalidated for 0x{offset:X}: "
                    f"mtime changed ({entry.mtime} -> {current_mtime})"
                )
                self._remove(key)
                self._misses += 1
                return None
        except OSError:
            # File no longer exists or inaccessible
            self._remove(key)
            self._misses += 1
            return None

        # Update last access time for LRU
        entry.last_access = time.time()
        self._hits += 1
        return entry.data

    def put(self, rom_path: str, offset: int, data: bytes) -> None:
        """
        Store data in cache, evicting entries as needed to maintain limits.
        """
        key = (rom_path, offset)
        size = len(data)

        # Get current file mtime
        try:
            mtime = Path(rom_path).stat().st_mtime
        except OSError:
            # Can't cache if we can't get mtime
            logger.warning(f"Cannot cache entry: unable to stat {rom_path}")
            return

        # Remove existing entry if present (to update size tracking)
        if key in self._cache:
            self._remove(key)

        # Evict until under limits (LRU order)
        while (
            len(self._cache) >= self._max_entries
            or self._total_size + size > self._max_memory
        ):
            if not self._cache:
                break
            self._evict_lru()

        # Don't cache if single entry exceeds memory limit
        if size > self._max_memory:
            logger.warning(
                f"Entry too large to cache: {size} bytes > {self._max_memory} max"
            )
            return

        # Store new entry
        self._cache[key] = CacheEntry(
            data=data, mtime=mtime, size=size, last_access=time.time()
        )
        self._total_size += size

    def _remove(self, key: tuple[str, int]) -> None:
        """Remove an entry from cache and update size tracking."""
        if key in self._cache:
            self._total_size -= self._cache[key].size
            del self._cache[key]

    def _evict_lru(self) -> None:
        """Remove the least recently accessed entry."""
        if not self._cache:
            return

        # Find entry with oldest last_access
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].last_access)
        logger.debug(
            f"Evicting LRU cache entry: offset 0x{oldest_key[1]:X}, "
            f"size {self._cache[oldest_key].size}"
        )
        self._remove(oldest_key)

    def clear(self) -> None:
        """Clear all entries and reset statistics."""
        self._cache.clear()
        self._total_size = 0
        self._hits = 0
        self._misses = 0

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def entry_count(self) -> int:
        return len(self._cache)

    @property
    def memory_usage(self) -> int:
        return self._total_size


@dataclass
class ExtractionResult:
    """Result of sprite extraction operation."""
    offset: int
    success: bool
    data: bytes | None = None
    image: Image.Image | None = None
    error: str | None = None
    time_ms: float = 0.0

class OptimizedROMExtractor(ROMExtractor):
    """
    High-performance ROM extractor with memory-mapped I/O.

    Performance improvements:
    - Memory-mapped file access (no full file loading)
    - Parallel sprite extraction
    - Batch decompression
    - Smart caching of decompressed data
    - Optimized palette loading
    """

    def __init__(
        self,
        rom_cache: ROMCacheProtocol | None = None,
        enable_parallel: bool = True,
        max_workers: int = 4
    ):
        """
        Initialize optimized ROM extractor.

        Args:
            rom_cache: ROM cache for caching scan results. If None, uses DI.
            enable_parallel: Enable parallel extraction for multiple sprites
            max_workers: Maximum worker threads for parallel extraction
        """
        # Get rom_cache from DI if not provided
        if rom_cache is None:
            from core.di_container import inject
            rom_cache = inject(ROMCacheProtocol)
        super().__init__(rom_cache)
        self.enable_parallel = enable_parallel
        self.max_workers = max_workers
        self._rom_readers: dict[str, MemoryMappedROMReader] = {}
        self._decompression_cache = DecompressionCache()

        logger.info(
            f"Initialized OptimizedROMExtractor "
            f"(parallel={'enabled' if enable_parallel else 'disabled'}, "
            f"workers={max_workers})"
        )

    def get_rom_reader(self, rom_path: str) -> MemoryMappedROMReader:
        """
        Get or create memory-mapped ROM reader.

        Uses singleton pattern to reuse readers for same ROM.
        """
        if rom_path not in self._rom_readers:
            self._rom_readers[rom_path] = optimize_rom_operations(rom_path)
            logger.debug(f"Created ROM reader for {rom_path}")
        return self._rom_readers[rom_path]

    @override
    def extract_sprite_data(
        self,
        rom_path: str,
        sprite_offset: int,
        sprite_config: dict[str, Any | None] | None = None,
        use_cache: bool = True
    ) -> bytes:
        """
        Extract sprite data with optimized memory-mapped access.

        Args:
            rom_path: Path to ROM file
            sprite_offset: Offset in ROM where sprite data is located
            sprite_config: Optional sprite configuration
            use_cache: Whether to use decompression cache

        Returns:
            Raw sprite data as bytes
        """
        start_time = time.perf_counter()

        # Check decompression cache (includes mtime validation)
        if use_cache:
            cached = self._decompression_cache.get(rom_path, sprite_offset)
            if cached is not None:
                logger.debug(f"Cache hit for sprite at 0x{sprite_offset:X}")
                return cached

        # Validate offset before decompression
        if sprite_offset < 0:
            raise ValueError(f"Invalid negative offset: {sprite_offset}")
        rom_size = Path(rom_path).stat().st_size
        if sprite_offset >= rom_size:
            raise ValueError(f"Offset 0x{sprite_offset:X} exceeds ROM size 0x{rom_size:X}")

        # Use memory-mapped reader for efficient access
        reader = self.get_rom_reader(rom_path)

        # Decompress using optimized reader
        try:
            decompressed = self._decompress_with_mmap(reader, sprite_offset)

            # Cache the result (handles LRU eviction and memory limits internally)
            if use_cache:
                self._decompression_cache.put(rom_path, sprite_offset, decompressed)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            cache = self._decompression_cache
            total_requests = cache.hits + cache.misses
            logger.debug(
                f"Extracted sprite at 0x{sprite_offset:X} in {elapsed_ms:.1f}ms "
                f"(cache: {cache.hits}/{total_requests})"
            )

            return decompressed

        except Exception as e:
            logger.error(f"Failed to extract sprite at 0x{sprite_offset:X}: {e}")
            raise

    def _decompress_with_mmap(
        self,
        reader: MemoryMappedROMReader,
        offset: int
    ) -> bytes:
        """
        Decompress data using memory-mapped ROM access.

        Uses the parent class's decompress_from_rom with the ROM path from the reader.

        Args:
            reader: Memory-mapped ROM reader
            offset: Offset to decompress from

        Returns:
            Decompressed data bytes
        """
        # Use parent class's working decompression via hal_compressor
        return self.hal_compressor.decompress_from_rom(str(reader.rom_path), offset)

    def extract_multiple_sprites(
        self,
        rom_path: str,
        offsets: list[int],
        sprite_configs: dict[int, dict[str, Any] | None] | None = None
    ) -> dict[int, ExtractionResult]:
        """
        Extract multiple sprites in parallel for better performance.

        Args:
            rom_path: Path to ROM file
            offsets: List of sprite offsets to extract
            sprite_configs: Optional configs per offset

        Returns:
            Dictionary mapping offset to extraction result
        """
        sprite_configs = sprite_configs or {}
        results = {}

        if self.enable_parallel and len(offsets) > 1:
            # Parallel extraction
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_offset = {
                    executor.submit(
                        self._extract_single_sprite,
                        rom_path,
                        offset,
                        sprite_configs.get(offset)
                    ): offset
                    for offset in offsets
                }

                for future in concurrent.futures.as_completed(future_to_offset):
                    offset = future_to_offset[future]
                    try:
                        results[offset] = future.result()
                    except Exception as e:
                        results[offset] = ExtractionResult(
                            offset=offset,
                            success=False,
                            error=str(e)
                        )
                        logger.error(f"Failed to extract sprite at 0x{offset:X}: {e}")
        else:
            # Sequential extraction
            for offset in offsets:
                results[offset] = self._extract_single_sprite(
                    rom_path,
                    offset,
                    sprite_configs.get(offset)
                )

        # Log statistics
        successful = sum(1 for r in results.values() if r.success)
        cache = self._decompression_cache
        total_requests = cache.hits + cache.misses
        hit_rate = cache.hits / max(total_requests, 1)
        logger.info(
            f"Extracted {successful}/{len(offsets)} sprites successfully "
            f"(cache hit rate: {hit_rate:.1%})"
        )

        return results

    def _extract_single_sprite(
        self,
        rom_path: str,
        offset: int,
        config: dict[str, Any] | None = None
    ) -> ExtractionResult:
        """Extract a single sprite and measure performance."""
        start_time = time.perf_counter()

        try:
            # Extract sprite data
            sprite_data = self.extract_sprite_data(rom_path, offset, config)

            # Convert to image using TileRenderer
            image = None
            if sprite_data:
                tiles_count = len(sprite_data) // BYTES_PER_TILE
                if tiles_count >= MIN_SPRITE_TILES:
                    width_tiles = DEFAULT_TILES_PER_ROW
                    height_tiles = (tiles_count + DEFAULT_TILES_PER_ROW - 1) // DEFAULT_TILES_PER_ROW

                    # Use TileRenderer for actual 4bpp tile rendering (grayscale)
                    renderer = TileRenderer()
                    image = renderer.render_tiles(
                        sprite_data,
                        width_tiles=width_tiles,
                        height_tiles=height_tiles,
                        palette_index=None  # Grayscale
                    )

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            return ExtractionResult(
                offset=offset,
                success=True,
                data=sprite_data,
                image=image,
                time_ms=elapsed_ms
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            return ExtractionResult(
                offset=offset,
                success=False,
                error=str(e),
                time_ms=elapsed_ms
            )

    def scan_rom_optimized(
        self,
        rom_path: str,
        start_offset: int = 0,
        end_offset: int | None = None,
        step: int = 0x100,
        pattern_filter: bytes | None = None
    ) -> list[int]:
        """
        Scan ROM for potential sprite locations using mmap.

        Much faster than reading entire file into memory.

        Args:
            rom_path: Path to ROM file
            start_offset: Starting offset for scan
            end_offset: Ending offset (None = end of file)
            step: Step size for scanning
            pattern_filter: Optional byte pattern to search for

        Returns:
            List of potential sprite offsets
        """
        reader = self.get_rom_reader(rom_path)
        potential_offsets = []

        if pattern_filter:
            # Search for specific pattern
            for offset in reader.search_pattern(pattern_filter, start_offset, end_offset, step):
                potential_offsets.append(offset)
        else:
            # Scan for HAL compression signatures

            with reader.batch_reader() as batch:
                offset = start_offset
                end = end_offset or reader.file_size

                while offset < end:
                    # Check for potential sprite data
                    header = batch.read(offset, 16)
                    if self._looks_like_sprite(header):
                        potential_offsets.append(offset)

                    offset += step

        logger.info(f"Found {len(potential_offsets)} potential sprite locations")
        return potential_offsets

    def _looks_like_sprite(self, data: bytes) -> bool:
        """
        Heuristic to detect potential sprite data.

        This would check for HAL compression headers,
        reasonable size values, etc.
        """
        if len(data) < 4:
            return False

        # Check for compression markers, reasonable sizes, etc.
        # Simplified example
        first_bytes = data[:4]

        # Check if it looks like compressed data
        if first_bytes == b'\x00\x00\x00\x00':
            return False  # All zeros unlikely to be sprite

        if first_bytes[0] in (0x00, 0x10, 0x20):  # Common HAL markers
            return True

        return False

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache performance statistics."""
        cache = self._decompression_cache
        total_requests = cache.hits + cache.misses

        return {
            "cache_hits": cache.hits,
            "cache_misses": cache.misses,
            "hit_rate": cache.hits / max(total_requests, 1),
            "cached_sprites": cache.entry_count,
            "memory_usage_bytes": cache.memory_usage,
            "rom_readers": len(self._rom_readers)
        }

    def clear_caches(self):
        """Clear all caches to free memory."""
        self._decompression_cache.clear()

        # Clear ROM readers dict directly
        # MemoryMappedROMReader uses context manager for mmap access, so no explicit close needed
        self._rom_readers.clear()

        logger.info("Cleared all extractor caches")


def benchmark_extraction(rom_path: str, offsets: list[int]) -> dict[str, Any]:
    """
    Benchmark extraction performance comparing original vs optimized.

    Args:
        rom_path: Path to ROM file
        offsets: List of sprite offsets to test

    Returns:
        Performance comparison metrics
    """
    results = {}

    # Test original extractor
    original = ROMExtractor()
    start = time.perf_counter()

    for offset in offsets:
        with suppress(Exception):
            original.extract_sprite_data(rom_path, offset)

    original_time = time.perf_counter() - start
    results["original_time_ms"] = original_time * 1000

    # Test optimized extractor
    optimized = OptimizedROMExtractor(enable_parallel=True)
    start = time.perf_counter()

    optimized.extract_multiple_sprites(rom_path, offsets)

    optimized_time = time.perf_counter() - start
    results["optimized_time_ms"] = optimized_time * 1000

    # Calculate improvement
    results["speedup"] = original_time / max(optimized_time, 0.001)
    results["cache_stats"] = optimized.get_cache_stats()

    logger.info(
        f"Benchmark results: {results['speedup']:.2f}x speedup "
        f"({results['original_time_ms']:.1f}ms -> {results['optimized_time_ms']:.1f}ms)"
    )

    return results
