"""Worker thread for scanning ROM for sprite offsets"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache

from typing import Any, override

from PySide6.QtCore import QMutex, QMutexLocker, Signal

from core.parallel_sprite_finder import ParallelSpriteFinder
from core.workers.base import BaseWorker, handle_worker_errors
from utils.constants import ROM_SCAN_START_DEFAULT, ROM_SCAN_STEP_TILE, ROM_SIZE_4MB
from utils.logging_config import get_logger

logger = get_logger(__name__)


class SpriteScanWorker(BaseWorker):
    """Worker thread for scanning ROM for sprite offsets.

    This worker supports two usage patterns:
    1. Simple mode: SpriteScanWorker(rom_path, step=0x1000) - for quick scans
    2. Advanced mode: SpriteScanWorker(rom_path, extractor, use_cache=True, ...) - for parallel scans with caching
    """

    # Custom signals (BaseWorker provides progress, error, warning, operation_finished)
    sprite_found = Signal(object)  # use object to avoid PySide6 copy warning
    """Emitted when a valid sprite is found. Args: sprite_info (dict with 'offset', 'quality' keys)."""

    # Compatibility signal: emits all sprites at once when scan completes
    sprites_found = Signal(list)
    """Emitted when scan completes with all found sprites. Args: list of sprite_info dicts."""

    finished = Signal()
    """Legacy compatibility signal - emitted when scan completes."""

    cache_status = Signal(str)
    """Emitted with cache status updates. Args: status_message."""

    cache_progress = Signal(int)
    """Emitted during cache save. Args: progress_percent (0-100)."""

    # For compatibility with existing code that expects (current, total) progress
    progress_detailed = Signal(int, int)
    """Emitted with detailed progress. Args: current_offset, total_offsets."""

    # Default step/alignment for scanning (tile-aligned for better sprite detection)
    _DEFAULT_STEP = ROM_SCAN_STEP_TILE

    def __init__(
        self,
        rom_path: str,
        extractor: ROMExtractor | None = None,
        use_cache: bool = True,
        start_offset: int | None = None,
        end_offset: int | None = None,
        parent: QObject | None = None,
        *,
        rom_cache: ROMCache,
        parallel_finder: ParallelSpriteFinder | None = None,
        step: int | None = None,
    ):
        super().__init__(parent)
        self.rom_path = rom_path
        self.extractor = extractor
        self.use_cache = use_cache
        self.custom_start_offset = start_offset  # Custom scan range
        self.custom_end_offset = end_offset  # Custom scan range
        self._last_save_progress = 0
        self._cancellation_token = threading.Event()

        # Store step and wire it to ParallelSpriteFinder
        self._step = step if step is not None else self._DEFAULT_STEP
        self._parallel_finder = parallel_finder or ParallelSpriteFinder(
            num_workers=4,
            chunk_size=0x40000,  # 256KB chunks
            step_size=self._step,  # Use configured step (was hardcoded 0x100)
        )

        # Assign rom_cache
        self.rom_cache = rom_cache

        # Thread-safe storage for found sprites
        self._found_sprites: dict[int, dict[str, Any]] = {}  # pyright: ignore[reportExplicitAny] - Sprite result dicts
        self._results_mutex = QMutex()

    def _add_found_sprite(self, sprite_info: dict[str, Any]) -> None:  # pyright: ignore[reportExplicitAny] - Sprite result dict
        """Thread-safe method to add a found sprite to the results."""
        offset = sprite_info.get("offset")
        if offset is not None:
            with QMutexLocker(self._results_mutex):
                self._found_sprites[offset] = sprite_info

    def _get_found_sprites_snapshot(self) -> list[dict[str, Any]]:  # pyright: ignore[reportExplicitAny] - Sprite result dicts
        """Thread-safe method to get a snapshot of all found sprites."""
        with QMutexLocker(self._results_mutex):
            return list(self._found_sprites.values())

    def _get_found_sprites_count(self) -> int:
        """Thread-safe method to get the count of found sprites."""
        with QMutexLocker(self._results_mutex):
            return len(self._found_sprites)

    def _clear_found_sprites(self) -> None:
        """Thread-safe method to clear the found sprites."""
        with QMutexLocker(self._results_mutex):
            self._found_sprites.clear()

    def get_found_sprites(self) -> list[dict[str, Any]]:  # pyright: ignore[reportExplicitAny] - Sprite result dicts
        """Public thread-safe getter for found sprites.

        Returns a copy of the found sprites list to prevent concurrent modification.
        """
        return self._get_found_sprites_snapshot()

    @handle_worker_errors("sprite scanning", handle_interruption=True)
    def run(self):
        """Scan ROM for valid sprite offsets using parallel processing"""
        if self._cancellation_token:
            self._cancellation_token.clear()

        # Use custom range if provided, otherwise use default range
        if self.custom_start_offset is not None and self.custom_end_offset is not None:
            # Use custom scan range
            start_offset = self.custom_start_offset
            end_offset = self.custom_end_offset
            logger.info(f"Using custom scan range: 0x{start_offset:X} - 0x{end_offset:X}")
        else:
            # Get ROM size to scan the entire ROM by default
            rom_size = Path(self.rom_path).stat().st_size

            # Default to scanning the entire ROM with reasonable limits
            # Use shared constants from utils.constants for consistency
            start_offset = ROM_SCAN_START_DEFAULT
            end_offset = min(rom_size, ROM_SIZE_4MB)

            logger.info(f"Scanning entire ROM: 0x{start_offset:X} to 0x{end_offset:X} (ROM size: 0x{rom_size:X})")

        # Clear any previous results (thread-safe)
        self._clear_found_sprites()

        # Define scan parameters for cache (must match scan_controller.compute_scan_params)
        scan_params = {
            "start_offset": start_offset,
            "end_offset": end_offset,
            "alignment": self._step,  # Use configured step for cache key consistency
        }

        # Initialize cache if enabled
        rom_cache = None
        original_start_offset = start_offset  # Save for progress calculations
        if self.use_cache:
            rom_cache = self.rom_cache
            self.cache_status.emit("Checking cache...")
            logger.debug(f"Checking cache with params: {scan_params}")
            partial_cache_raw = rom_cache.get_partial_scan_results(self.rom_path, scan_params)
            logger.debug(f"Cache lookup result: {partial_cache_raw is not None}")

            partial_cache: dict[str, Any] = dict(partial_cache_raw) if partial_cache_raw else {}  # pyright: ignore[reportExplicitAny] - scan cache

            if partial_cache:
                # Resume from cache - use correct field names
                cached_sprites = partial_cache.get("found_sprites", [])
                found_count = len(cached_sprites)
                last_offset = partial_cache.get("current_offset", start_offset)
                # Prevent division by zero
                scan_range = end_offset - original_start_offset
                progress_pct = int(((last_offset - original_start_offset) / scan_range) * 100) if scan_range > 0 else 0

                self.cache_status.emit(f"Resuming from {progress_pct}% (found {found_count} sprites)")
                logger.info(f"Resuming scan from offset 0x{last_offset:X}")

                # Load already-found sprites (thread-safe)
                for sprite_info in cached_sprites:
                    self._add_found_sprite(sprite_info)
                    # Emit the cached sprites immediately so they appear in the dialog
                    self.sprite_found.emit(sprite_info)

                # Update start position to continue from where we left off
                # Use the step_size from the parallel finder configuration instead of hardcoded 0x100
                # This ensures we don't skip any offsets when resuming
                start_offset = last_offset + self._parallel_finder.step_size
                # Initialize last save progress to the current progress
                self._last_save_progress = progress_pct
            else:
                self.cache_status.emit("Starting fresh scan")

        logger.info(f"Starting parallel sprite scan: 0x{start_offset:X} to 0x{end_offset:X}")

        # Progress callback to handle results as they come in
        def progress_callback(current_progress: int, total_progress: int) -> None:
            # Check cancellation before any work to prevent race condition with cache save
            if self.is_cancelled or (self._cancellation_token and self._cancellation_token.is_set()):
                return

            # Map parallel finder progress to our progress signals
            total_range = end_offset - original_start_offset  # Use original for consistency

            # Prevent division by zero and handle edge cases
            if total_range <= 0:
                logger.warning(f"Invalid scan range: {original_start_offset:X} to {end_offset:X}")
                # Emit 100% progress since we can't scan anything
                self.emit_progress(100, "Invalid scan range")
                return

            current_range = (current_progress / 100) * total_range
            current_step = int(current_range // 0x100) if total_range >= 0x100 else int(current_range)
            total_steps = max(1, int(total_range // 0x100)) if total_range >= 0x100 else max(1, int(total_range))

            # Emit progress signal
            self.progress_detailed.emit(current_step, total_steps)
            percent = int((current_progress / 100) * 100)  # Already a percentage
            self.emit_progress(percent, f"Scanning... ({current_step}/{total_steps})")

            # Save partial results periodically based on progress
            if rom_cache and current_progress >= self._last_save_progress + 10:
                self._last_save_progress = current_progress
                self.cache_status.emit(f"Saving progress ({current_progress}%)...")

                # Thread-safe snapshot of found sprites
                found_sprites_list = self._get_found_sprites_snapshot()
                current_offset = original_start_offset + int(current_range)

                if rom_cache.save_partial_scan_results(
                    self.rom_path,
                    scan_params,
                    found_sprites_list,
                    current_offset,
                    False,  # not completed
                ):
                    self.cache_progress.emit(current_progress)
                    logger.debug(f"Saved partial scan results at {current_progress}% progress")

        # Execute parallel search
        search_results = self._parallel_finder.search_parallel(
            self.rom_path,
            start_offset=start_offset,
            end_offset=end_offset,
            progress_callback=progress_callback,
            cancellation_token=self._cancellation_token,
        )

        # Convert SearchResult objects to legacy sprite info format and emit
        for result in search_results:
            sprite_info = {
                "offset": result.offset,
                "offset_hex": f"0x{result.offset:X}",
                "compressed_size": result.compressed_size,
                "decompressed_size": result.size,
                "tile_count": result.tile_count,
                "alignment": "perfect" if result.size % 32 == 0 else f"{result.size % 32} extra bytes",
                "quality": result.confidence,
            }

            # Thread-safe add
            self._add_found_sprite(sprite_info)
            self.sprite_found.emit(sprite_info)

            logger.info(
                f"Found sprite at 0x{result.offset:X}: quality={result.confidence:.2f}, tiles={result.tile_count}"
            )

        # Save final results after scan completes (thread-safe)
        total_found = self._get_found_sprites_count()
        logger.debug(f"Parallel scan completed. Found {total_found} sprites total")
        if rom_cache:
            self.cache_status.emit("Saving final results...")
            found_sprites_list = self._get_found_sprites_snapshot()
            logger.debug(f"Saving {len(found_sprites_list)} sprites to cache as completed")

            if rom_cache.save_partial_scan_results(
                self.rom_path,
                scan_params,
                found_sprites_list,
                end_offset,  # final offset
                True,  # completed
            ):
                # Ensure we emit 100% progress for the final save
                self.cache_progress.emit(100)
                logger.info("Saved final scan results to cache")

        # Log summary statistics (thread-safe snapshot for statistics)
        logger.debug("Preparing summary statistics")
        final_sprites = self._get_found_sprites_snapshot()
        if final_sprites:
            # Filter out sprites that don't have quality (e.g., from cache)
            sprites_with_quality = [s for s in final_sprites if "quality" in s]
            if sprites_with_quality:
                qualities = [s["quality"] for s in sprites_with_quality]
                avg_quality = sum(qualities) / len(qualities)
                high_quality_count = sum(1 for q in qualities if q >= 0.7)

                logger.info(f"Parallel scan complete. Found {len(final_sprites)} sprites:")
                logger.info(f"  - Average quality: {avg_quality:.2f}")
                logger.info(f"  - High quality (≥0.7): {high_quality_count}")
                logger.info(f"  - Quality range: {min(qualities):.2f} - {max(qualities):.2f}")
            else:
                # No quality data available (e.g., all sprites from cache)
                logger.info(f"Parallel scan complete. Found {len(final_sprites)} sprites (from cache)")
        else:
            logger.info("Parallel scan complete. No valid sprites found.")

        # Emit compatibility signal with all found sprites
        self.sprites_found.emit(final_sprites)

        self.finished.emit()
        self.operation_finished.emit(True, f"Scan complete. Found {len(final_sprites)} sprites.")

        # Cleanup parallel finder resources
        try:
            self._parallel_finder.shutdown()
        except Exception as cleanup_error:
            logger.warning(f"Error during parallel finder cleanup: {cleanup_error}")

    @override
    def cancel(self):
        """Cancel the scanning operation"""
        # Call parent cancel method first
        super().cancel()
        # Also set our cancellation token for the parallel finder
        self._cancellation_token.set()
        logger.debug("Sprite scan cancellation requested")
