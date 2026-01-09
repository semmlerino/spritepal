"""
Parallel sprite finder for improved search performance.

This module implements concurrent sprite searching across ROM regions,
providing 3-4x speedup on multi-core systems.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from core.sprite_finder import SpriteFinder
from core.types import CancellationToken
from utils.constants import (
    CHUNK_SIZE_PARALLEL,
    DEFAULT_SCAN_STEP,
    MIN_SPRITE_SIZE,
    ROM_SCAN_STEP_TILE,
)
from utils.rom_utils import load_rom_data_stripped

logger = logging.getLogger(__name__)


@dataclass
class SearchChunk:
    """Represents a ROM region to search."""

    start: int
    end: int
    chunk_id: int

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass
class SearchResult:
    """Container for sprite search results."""

    offset: int
    size: int
    tile_count: int
    compressed_size: int
    confidence: float
    metadata: dict[str, object]


class ParallelSpriteFinder:
    """
    High-performance parallel sprite finder.

    Divides ROM into chunks and searches them concurrently,
    providing significant speedup on multi-core systems.
    """

    def __init__(self, num_workers: int = 4, chunk_size: int = CHUNK_SIZE_PARALLEL, step_size: int = DEFAULT_SCAN_STEP):
        """
        Initialize parallel sprite finder.

        Args:
            num_workers: Number of parallel workers
            chunk_size: Size of each search chunk in bytes
            step_size: Step size for scanning within chunks
        """
        self.num_workers = num_workers
        self.chunk_size = chunk_size
        self.step_size = step_size
        self.executor = ThreadPoolExecutor(max_workers=num_workers)

        # Create sprite finders for each worker
        self.sprite_finders = [SpriteFinder() for _ in range(num_workers)]

        self._shutdown = False
        logger.info(
            f"Initialized ParallelSpriteFinder with {num_workers} workers, "
            f"chunk size: 0x{chunk_size:X}, step: 0x{step_size:X}"
        )

    def __del__(self) -> None:
        """Ensure executor is shut down when object is garbage collected."""
        self.shutdown()

    def __enter__(self) -> ParallelSpriteFinder:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """Context manager exit - ensures cleanup."""
        self.shutdown()

    def search_parallel(
        self,
        rom_path: str,
        start_offset: int = 0,
        end_offset: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> list[SearchResult]:
        """
        Search for sprites in parallel across ROM regions.

        Args:
            rom_path: Path to ROM file
            start_offset: Starting offset for search
            end_offset: Ending offset (None for entire ROM)
            progress_callback: Optional progress callback(current, total)
            cancellation_token: Optional token to cancel search

        Returns:
            List of found sprites sorted by offset
        """
        # Read ROM data, stripping SMC header if present
        rom_data = load_rom_data_stripped(rom_path)
        rom_size = len(rom_data)
        end_offset = rom_size if end_offset is None else min(end_offset, rom_size)

        # Create search chunks
        chunks = self._create_chunks(start_offset, end_offset)
        total_chunks = len(chunks)

        logger.info(
            f"Starting parallel search: ROM size=0x{rom_size:X}, "
            f"range=0x{start_offset:X}-0x{end_offset:X}, "
            f"chunks={total_chunks}"
        )

        # Submit search tasks
        start_time = time.time()
        futures = {}

        for i, chunk in enumerate(chunks):
            # Check cancellation
            if cancellation_token and cancellation_token.is_set():
                logger.info("Search cancelled by user")
                break

            # Use worker-specific sprite finder
            finder = self.sprite_finders[i % self.num_workers]

            future = self.executor.submit(self._search_chunk, finder, rom_data, chunk, cancellation_token)
            futures[future] = chunk

        # Collect results
        all_results = []
        completed_chunks = 0

        for future in as_completed(futures):
            chunk = futures[future]

            try:
                results = future.result()
                all_results.extend(results)
                completed_chunks += 1

                # Update progress
                if progress_callback:
                    progress = int((completed_chunks / total_chunks) * 100)
                    progress_callback(progress, 100)

                logger.debug(f"Chunk {chunk.chunk_id} complete: found {len(results)} sprites")

            except Exception as e:
                logger.exception(f"Error searching chunk {chunk.chunk_id}: {e}")

        # Sort results by offset
        all_results.sort(key=lambda x: x.offset)

        elapsed = time.time() - start_time
        rate = len(all_results) / elapsed if elapsed > 0 else 0.0
        logger.info(
            f"Parallel search complete: found {len(all_results)} sprites in {elapsed:.2f}s ({rate:.1f} sprites/sec)"
        )

        return all_results

    def _create_chunks(self, start: int, end: int) -> list[SearchChunk]:
        """Divide search range into chunks."""
        chunks = []

        for chunk_id, offset in enumerate(range(start, end, self.chunk_size)):
            chunk_end = min(offset + self.chunk_size, end)
            chunk = SearchChunk(start=offset, end=chunk_end, chunk_id=chunk_id)
            chunks.append(chunk)

        return chunks

    def _search_chunk(
        self,
        finder: SpriteFinder,
        rom_data: bytes,
        chunk: SearchChunk,
        end_offset: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> list[SearchResult]:
        """Search a single chunk for sprites.

        Delegates all validation to SpriteFinder.scan_offset() to ensure
        consistent behavior between sequential and parallel scanning.
        """
        results = []

        # Use adaptive step sizing based on chunk characteristics
        step = self._calculate_adaptive_step(finder, rom_data, chunk)

        # Use a while loop to ensure we check up to and including the last valid offset
        offset = chunk.start
        while offset < chunk.end:
            # Check cancellation
            if cancellation_token and cancellation_token.is_set():
                break

            # Skip if too close to end
            if offset + MIN_SPRITE_SIZE > len(rom_data):
                break

            # Use SpriteFinder's unified scan_offset (includes quick_check)
            scan_result = finder.scan_offset(rom_data, offset, quick_check=True, full_visual_validation=False)

            if scan_result:
                result = SearchResult(
                    offset=offset,
                    size=scan_result.decompressed_size,
                    tile_count=scan_result.tile_count,
                    compressed_size=scan_result.compressed_size,
                    confidence=scan_result.confidence,
                    metadata=scan_result.to_dict(),
                )
                results.append(result)

                # Skip ahead past this sprite
                # Use confidence-based skip distance to avoid missing sprites
                # when compressed_size estimation is unreliable
                if scan_result.confidence >= 0.8:
                    # High confidence - trust compressed_size
                    skip_distance = max(scan_result.compressed_size, self.step_size)
                else:
                    # Low confidence - cap skip distance to avoid missing sprites
                    # when HAL parsing might have overestimated compressed_size
                    skip_distance = min(max(scan_result.compressed_size, self.step_size), self.step_size * 2)
                offset += skip_distance
            else:
                # Move to next offset
                offset += step

        return results

    def _calculate_adaptive_step(self, finder: SpriteFinder, rom_data: bytes, chunk: SearchChunk) -> int:
        """
        Calculate adaptive step size based on chunk characteristics.

        Dense sprite regions get smaller steps (down to tile alignment),
        sparse regions get larger steps for efficiency.
        """
        # Sample the chunk to estimate sprite density
        sample_size = min(0x4000, chunk.size)  # 16KB sample
        sample_offset = chunk.start

        # Count potential sprite markers in sample
        potential_sprites = 0
        for i in range(0, sample_size - 16, 0x80):  # Check every 128 bytes
            offset = sample_offset + i
            if offset + 16 < len(rom_data):
                if finder._quick_sprite_check(rom_data, offset):
                    potential_sprites += 1

        # Calculate density (sprites per KB)
        density = potential_sprites / (sample_size / 1024)

        # Adjust step based on density
        if density > 0.5:  # High density - use tile-aligned step
            return ROM_SCAN_STEP_TILE  # 32 bytes (1 tile)
        if density > 0.1:  # Medium density
            return max(ROM_SCAN_STEP_TILE, self.step_size // 2)
        if density < 0.01:  # Very sparse
            return min(0x1000, self.step_size * 4)
        # Normal density
        return self.step_size

    def shutdown(self) -> None:
        """Shutdown the thread pool. Safe to call multiple times."""
        if self._shutdown:
            return
        self._shutdown = True
        try:
            self.executor.shutdown(wait=True)
            logger.info("ParallelSpriteFinder shutdown complete")
        except Exception as e:
            logger.warning(f"Error during ParallelSpriteFinder shutdown: {e}")
