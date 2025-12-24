"""
Optimized thumbnail generation with parallel processing and smart caching.

Performance optimizations:
1. Parallel thumbnail generation using thread pool
2. Multi-level caching (memory + disk)
3. Batch processing for better I/O efficiency
4. Progressive loading for large batches
5. Smart priority queue for visible items first
"""
from __future__ import annotations

import concurrent.futures
import heapq
import io
import logging
import pickle
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Protocol, TypedDict

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor

# Maximum queue size to prevent memory exhaustion during rapid scrolling
MAX_QUEUE_SIZE = 500

from PIL import Image

logger = logging.getLogger(__name__)


# Type alias for thumbnail callbacks
ThumbnailCallback = Callable[[int, Image.Image], None]


class SpriteRendererProtocol(Protocol):
    """Protocol for sprite renderers used in thumbnail generation."""
    def render_sprite(self, sprite_data: bytes) -> Image.Image | None:
        """Render sprite data to an image."""
        ...


class ThumbnailCacheStats(TypedDict):
    """Statistics from ThumbnailCache.get_stats()."""
    memory_hits: int
    disk_hits: int
    misses: int
    hit_rate: float
    memory_size: int
    disk_files: int


class GeneratorStats(TypedDict):
    """Statistics from OptimizedThumbnailGenerator.get_stats()."""
    generated: int
    average_time_ms: float
    total_time_ms: float
    pending_tasks: int
    active_tasks: int
    cache_stats: ThumbnailCacheStats

@dataclass(order=True)
class ThumbnailTask:
    """Task for thumbnail generation with priority."""
    priority: int
    offset: int = field(compare=False)
    size: tuple[int, int] = field(compare=False)
    callback: ThumbnailCallback | None = field(compare=False, default=None)
    cache_key: str = field(compare=False, default="")

    def __post_init__(self):
        """Generate cache key if not provided."""
        if not self.cache_key:
            self.cache_key = f"{self.offset}_{self.size[0]}x{self.size[1]}"

class ThumbnailCache:
    """
    Multi-level thumbnail cache for optimal performance.

    L1: In-memory LRU cache (fastest, limited size)
    L2: Disk cache (persistent, larger capacity)
    """

    def __init__(
        self,
        memory_size: int = 200,
        disk_cache_dir: Path | None = None,
        cache_ttl: int = 3600
    ):
        """
        Initialize multi-level cache.

        Args:
            memory_size: Maximum items in memory cache
            disk_cache_dir: Directory for disk cache (None = temp dir)
            cache_ttl: Time-to-live in seconds for cached items
        """
        # L1: Memory cache (LRU)
        self._memory_cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._memory_size = memory_size
        self._memory_lock = Lock()

        # L2: Disk cache
        if disk_cache_dir is None:
            import tempfile
            self._disk_cache_dir = Path(tempfile.gettempdir()) / "spritepal_thumbnails"
        else:
            self._disk_cache_dir = Path(disk_cache_dir)

        self._disk_cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_ttl = cache_ttl

        # Statistics
        self._hits = {"memory": 0, "disk": 0}
        self._misses = 0

        logger.info(f"Initialized thumbnail cache (memory={memory_size}, disk={self._disk_cache_dir})")

    def get(self, key: str) -> Image.Image | None:
        """
        Get thumbnail from cache.

        Checks memory first, then disk.
        """
        # Check L1 (memory)
        with self._memory_lock:
            if key in self._memory_cache:
                # Move to end (most recently used)
                self._memory_cache.move_to_end(key)
                self._hits["memory"] += 1
                return self._memory_cache[key].copy()

        # Check L2 (disk)
        disk_path = self._disk_cache_dir / f"{key}.pkl"
        if disk_path.exists():
            try:
                # Check if not expired
                age = time.time() - disk_path.stat().st_mtime
                if age < self._cache_ttl:
                    with disk_path.open("rb") as f:
                        image_data = pickle.load(f)

                    # Recreate PIL Image from bytes
                    image = Image.open(io.BytesIO(image_data))

                    # Promote to memory cache
                    self._add_to_memory(key, image)

                    self._hits["disk"] += 1
                    return image.copy()
                # Expired, remove
                disk_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to load from disk cache: {e}")

        self._misses += 1
        return None

    def put(self, key: str, image: Image.Image):
        """
        Store thumbnail in cache.

        Stores in both memory and disk.
        """
        # Add to memory cache
        self._add_to_memory(key, image)

        # Save to disk cache
        disk_path = self._disk_cache_dir / f"{key}.pkl"
        try:
            # Convert PIL Image to bytes for pickling
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_data = buffer.getvalue()

            with disk_path.open("wb") as f:
                pickle.dump(image_data, f)
        except Exception as e:
            logger.warning(f"Failed to save to disk cache: {e}")

    def _add_to_memory(self, key: str, image: Image.Image):
        """Add to memory cache with LRU eviction."""
        with self._memory_lock:
            # Remove oldest if at capacity
            if len(self._memory_cache) >= self._memory_size:
                oldest = next(iter(self._memory_cache))
                del self._memory_cache[oldest]

            self._memory_cache[key] = image.copy()

    def get_stats(self) -> ThumbnailCacheStats:
        """Get cache statistics."""
        total_hits = sum(self._hits.values())
        total_requests = total_hits + self._misses

        return {
            "memory_hits": self._hits["memory"],
            "disk_hits": self._hits["disk"],
            "misses": self._misses,
            "hit_rate": total_hits / max(total_requests, 1),
            "memory_size": len(self._memory_cache),
            "disk_files": len(list(self._disk_cache_dir.glob("*.pkl")))
        }

    def clear(self):
        """Clear all caches."""
        with self._memory_lock:
            self._memory_cache.clear()

        # Clear disk cache
        for file in self._disk_cache_dir.glob("*.pkl"):
            file.unlink(missing_ok=True)

        self._hits = {"memory": 0, "disk": 0}
        self._misses = 0

class OptimizedThumbnailGenerator:
    """
    High-performance thumbnail generator with parallel processing.

    Features:
    - Parallel generation using thread pool
    - Multi-level caching
    - Batch processing
    - Priority queue for visible items
    - Progressive loading
    """

    def __init__(
        self,
        max_workers: int = 4,
        cache_size: int = 200,
        batch_size: int = 20
    ):
        """
        Initialize optimized thumbnail generator.

        Args:
            max_workers: Maximum parallel workers
            cache_size: Size of memory cache
            batch_size: Batch size for processing
        """
        self.max_workers = max_workers
        self.batch_size = batch_size

        # Thread pool for parallel generation
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

        # Multi-level cache
        self._cache = ThumbnailCache(memory_size=cache_size)

        # Priority queue for tasks
        self._task_queue: list[ThumbnailTask] = []
        self._queue_lock = Lock()

        # Active futures
        self._active_futures: dict[str, concurrent.futures.Future[Image.Image | None]] = {}
        self._futures_lock = Lock()

        # Generation function (to be set by user)
        self._generate_func: Callable[[int, tuple[int, int]], Image.Image] | None = None

        # Statistics
        self._generated_count = 0
        self._total_time_ms = 0.0
        self._shutdown_called = False

        logger.info(
            f"Initialized OptimizedThumbnailGenerator "
            f"(workers={max_workers}, cache={cache_size}, batch={batch_size})"
        )

    def __del__(self) -> None:
        """Ensure executor is shut down when object is garbage collected."""
        self.shutdown()

    def __enter__(self) -> OptimizedThumbnailGenerator:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """Context manager exit - ensures cleanup."""
        self.shutdown()

    def set_generator(self, func: Callable[[int, tuple[int, int]], Image.Image]):
        """
        Set the thumbnail generation function.

        Args:
            func: Function that takes (offset, size) and returns PIL Image
        """
        self._generate_func = func

    def generate(
        self,
        offset: int,
        size: tuple[int, int] = (128, 128),
        priority: int = 100,
        callback: ThumbnailCallback | None = None,
        use_cache: bool = True
    ) -> Image.Image | None:
        """
        Generate or retrieve a thumbnail.

        Args:
            offset: Data offset
            size: Thumbnail size (width, height)
            priority: Priority (0 = highest)
            callback: Optional callback when ready
            use_cache: Whether to use cache

        Returns:
            Thumbnail image if immediately available, None otherwise
        """
        cache_key = f"{offset}_{size[0]}x{size[1]}"

        # Check cache first
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached:
                if callback:
                    callback(offset, cached)
                return cached

        # Check if already generating
        with self._futures_lock:
            if cache_key in self._active_futures:
                # Already generating, add callback if provided
                if callback:
                    future = self._active_futures[cache_key]
                    def on_ready(f: concurrent.futures.Future[Image.Image | None]) -> None:
                        result = f.result()
                        if result is not None:
                            callback(offset, result)
                    future.add_done_callback(on_ready)
                return None

        # Queue for generation
        task = ThumbnailTask(
            priority=priority,
            offset=offset,
            size=size,
            callback=callback,
            cache_key=cache_key
        )

        with self._queue_lock:
            if len(self._task_queue) >= MAX_QUEUE_SIZE:
                # Discard lowest priority task (highest priority value) when queue is full
                heapq.heappushpop(self._task_queue, task)
            else:
                heapq.heappush(self._task_queue, task)

        # Process queue
        self._process_queue()

        return None

    def generate_batch(
        self,
        offsets: list[int],
        size: tuple[int, int] = (128, 128),
        priority_start: int = 100,
        callback: ThumbnailCallback | None = None,
        parallel: bool = True
    ) -> dict[int, Image.Image | None]:
        """
        Generate multiple thumbnails.

        Args:
            offsets: List of data offsets
            size: Thumbnail size for all
            priority_start: Starting priority
            callback: Optional callback for each thumbnail
            parallel: Whether to use parallel processing

        Returns:
            Dictionary mapping offset to image (None if not ready)
        """
        results = {}

        if parallel:
            # Queue all tasks
            for i, offset in enumerate(offsets):
                priority = priority_start + i
                results[offset] = self.generate(offset, size, priority, callback)
        else:
            # Sequential generation
            for offset in offsets:
                results[offset] = self._generate_single(offset, size)
                if callback and results[offset]:
                    callback(offset, results[offset])

        return results

    def _generate_single(self, offset: int, size: tuple[int, int]) -> Image.Image | None:
        """Generate a single thumbnail synchronously."""
        if not self._generate_func:
            logger.error("No generation function set")
            return None

        cache_key = f"{offset}_{size[0]}x{size[1]}"

        # Check cache
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        try:
            start_time = time.perf_counter()

            # Generate thumbnail
            image = self._generate_func(offset, size)

            # Cache result
            if image:
                self._cache.put(cache_key, image)

            # Update statistics
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._generated_count += 1
            self._total_time_ms += elapsed_ms

            logger.debug(f"Generated thumbnail for 0x{offset:X} in {elapsed_ms:.1f}ms")

            return image

        except Exception as e:
            logger.error(f"Failed to generate thumbnail for 0x{offset:X}: {e}")
            return None

    def _process_queue(self):
        """Process queued tasks in parallel."""
        with self._queue_lock:
            if not self._task_queue:
                return

            # Take a batch of tasks (highest priority = lowest value first)
            batch = []
            while self._task_queue and len(batch) < self.batch_size:
                task = heapq.heappop(self._task_queue)

                # Skip if already processing
                with self._futures_lock:
                    if task.cache_key not in self._active_futures:
                        batch.append(task)

        # Submit batch to thread pool
        for task in batch:
            future = self._executor.submit(self._generate_single, task.offset, task.size)

            # Track active future
            with self._futures_lock:
                self._active_futures[task.cache_key] = future

            # Add completion callback
            def make_callback(t: ThumbnailTask) -> Callable[[concurrent.futures.Future[Image.Image | None]], None]:
                def on_complete(f: concurrent.futures.Future[Image.Image | None]) -> None:
                    try:
                        result = f.result()
                        if result and t.callback:
                            t.callback(t.offset, result)
                    except Exception as e:
                        logger.error(f"Thumbnail generation failed: {e}")
                    finally:
                        # Remove from active futures
                        with self._futures_lock:
                            self._active_futures.pop(t.cache_key, None)

                return on_complete

            future.add_done_callback(make_callback(task))

    def wait_for_all(self, timeout: float = 10.0) -> bool:
        """
        Wait for all pending thumbnails to complete.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if all completed, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            with self._futures_lock:
                if not self._active_futures:
                    return True

            time.sleep(0.1)

        return False

    def cancel_all(self):
        """Cancel all pending thumbnail generation."""
        # Clear queue
        with self._queue_lock:
            self._task_queue.clear()

        # Cancel active futures
        with self._futures_lock:
            for future in self._active_futures.values():
                future.cancel()
            self._active_futures.clear()

    def get_stats(self) -> GeneratorStats:
        """Get generation statistics."""
        avg_time = self._total_time_ms / max(self._generated_count, 1)

        return {
            "generated": self._generated_count,
            "average_time_ms": avg_time,
            "total_time_ms": self._total_time_ms,
            "pending_tasks": len(self._task_queue),
            "active_tasks": len(self._active_futures),
            "cache_stats": self._cache.get_stats()
        }

    def clear_cache(self):
        """Clear thumbnail cache."""
        self._cache.clear()

    def shutdown(self) -> None:
        """Shutdown the generator and free resources. Safe to call multiple times."""
        if self._shutdown_called:
            return
        self._shutdown_called = True
        try:
            self.cancel_all()
            self._executor.shutdown(wait=True)
            self.clear_cache()
            logger.info("Thumbnail generator shutdown complete")
        except Exception as e:
            logger.warning(f"Error during thumbnail generator shutdown: {e}")

def create_optimized_generator(
    rom_extractor: ROMExtractor,
    tile_renderer: SpriteRendererProtocol,
    rom_path: str | Path,
    max_workers: int = 4
) -> OptimizedThumbnailGenerator:
    """
    Create an optimized thumbnail generator with ROM extraction.

    Args:
        rom_extractor: ROM extractor instance
        tile_renderer: Tile renderer instance
        max_workers: Maximum parallel workers

    Returns:
        Configured thumbnail generator
    """
    generator = OptimizedThumbnailGenerator(max_workers=max_workers)
    rom_path_str = str(rom_path)

    def generate_thumbnail(offset: int, size: tuple[int, int]) -> Image.Image | None:
        """Generate thumbnail from ROM sprite."""
        try:
            # Extract sprite data
            sprite_data = rom_extractor.extract_sprite_data(rom_path_str, offset)

            if not sprite_data:
                return None

            # Render to image
            image = tile_renderer.render_sprite(sprite_data)

            if not image:
                return None

            # Resize to thumbnail size
            thumbnail = image.resize(size, Image.Resampling.LANCZOS)

            return thumbnail

        except Exception as e:
            logger.error(f"Failed to generate thumbnail: {e}")
            return None

    generator.set_generator(generate_thumbnail)  # type: ignore[arg-type]  # Generator can return None on error

    return generator
