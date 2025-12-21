"""Worker thread for scanning ROM for sprite offsets"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.protocols.manager_protocols import ROMCacheProtocol, ROMExtractorProtocol

from typing import Any, override

from PySide6.QtCore import Signal

from core.parallel_sprite_finder import ParallelSpriteFinder
from core.workers.base import BaseWorker, handle_worker_errors
from utils.logging_config import get_logger

logger = get_logger(__name__)

class SpriteScanWorker(BaseWorker):
    """Worker thread for scanning ROM for sprite offsets.

    This worker supports two usage patterns:
    1. Simple mode: SpriteScanWorker(rom_path, step=0x1000) - for quick scans
    2. Advanced mode: SpriteScanWorker(rom_path, extractor, use_cache=True, ...) - for parallel scans with caching
    """

    # Custom signals (BaseWorker provides progress, error, warning, operation_finished)
    sprite_found = Signal(dict)
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

    def __init__(self, rom_path: str, extractor: ROMExtractorProtocol | None = None, use_cache: bool = True,
                 start_offset: int | None = None, end_offset: int | None = None, parent: QObject | None = None, *,
                 rom_cache: ROMCacheProtocol,
                 parallel_finder: ParallelSpriteFinder | None = None,
                 step: int | None = None):
        super().__init__(parent)
        self.rom_path = rom_path
        self.extractor = extractor
        self.use_cache = use_cache
        self.custom_start_offset = start_offset  # Custom scan range
        self.custom_end_offset = end_offset      # Custom scan range
        self._last_save_progress = 0
        self._cancellation_token = threading.Event()
        self._parallel_finder = parallel_finder or ParallelSpriteFinder(
            num_workers=4,
            chunk_size=0x40000,  # 256KB chunks
            step_size=0x100      # 256-byte alignment
        )

        # Assign rom_cache
        self.rom_cache = rom_cache

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
            # Start from 0x40000 to skip headers and early data
            # End at ROM size or reasonable max (4MB for SNES ROMs)
            start_offset = 0x40000  # Skip headers and early data
            end_offset = min(rom_size, 0x400000)  # Cap at 4MB for safety

            logger.info(f"Scanning entire ROM: 0x{start_offset:X} to 0x{end_offset:X} (ROM size: 0x{rom_size:X})")

        found_sprites = {}  # Track unique sprites by offset

        # Define scan parameters for cache
        scan_params = {
            "start_offset": start_offset,
            "end_offset": end_offset,
            "alignment": 0x100
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

                # Load already-found sprites
                for sprite_info in cached_sprites:
                    offset = sprite_info.get("offset")
                    if offset:
                        found_sprites[offset] = sprite_info
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

                found_sprites_list = list(found_sprites.values())
                current_offset = original_start_offset + int(current_range)

                if rom_cache.save_partial_scan_results(
                    self.rom_path,
                    scan_params,
                    found_sprites_list,
                    current_offset,
                    False  # not completed
                ):
                    self.cache_progress.emit(current_progress)
                    logger.debug(f"Saved partial scan results at {current_progress}% progress")

        # Execute parallel search
        search_results = self._parallel_finder.search_parallel(
            self.rom_path,
            start_offset=start_offset,
            end_offset=end_offset,
            progress_callback=progress_callback,
            cancellation_token=self._cancellation_token
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
                "quality": result.confidence
            }

            found_sprites[result.offset] = sprite_info
            self.sprite_found.emit(sprite_info)

            logger.info(
                f"Found sprite at 0x{result.offset:X}: quality={result.confidence:.2f}, "
                f"tiles={result.tile_count}"
            )

        # Save final results after scan completes
        logger.debug(f"Parallel scan completed. Found {len(found_sprites)} sprites total")
        if rom_cache:
            self.cache_status.emit("Saving final results...")
            found_sprites_list = list(found_sprites.values())
            logger.debug(f"Saving {len(found_sprites_list)} sprites to cache as completed")

            if rom_cache.save_partial_scan_results(
                self.rom_path,
                scan_params,
                found_sprites_list,
                end_offset,   # final offset
                True          # completed
            ):
                # Ensure we emit 100% progress for the final save
                self.cache_progress.emit(100)
                logger.info("Saved final scan results to cache")

        # Log summary statistics
        logger.debug("Preparing summary statistics")
        if found_sprites:
            # Filter out sprites that don't have quality (e.g., from cache)
            sprites_with_quality = [s for s in found_sprites.values() if "quality" in s]
            if sprites_with_quality:
                qualities = [s["quality"] for s in sprites_with_quality]
                avg_quality = sum(qualities) / len(qualities)
                high_quality_count = sum(1 for q in qualities if q >= 0.7)

                logger.info(f"Parallel scan complete. Found {len(found_sprites)} sprites:")
                logger.info(f"  - Average quality: {avg_quality:.2f}")
                logger.info(f"  - High quality (≥0.7): {high_quality_count}")
                logger.info(f"  - Quality range: {min(qualities):.2f} - {max(qualities):.2f}")
            else:
                # No quality data available (e.g., all sprites from cache)
                logger.info(f"Parallel scan complete. Found {len(found_sprites)} sprites (from cache)")
        else:
            logger.info("Parallel scan complete. No valid sprites found.")

        # Emit compatibility signal with all found sprites
        self.sprites_found.emit(list(found_sprites.values()))

        self.finished.emit()
        self.operation_finished.emit(True, f"Scan complete. Found {len(found_sprites)} sprites.")

        # Cleanup parallel finder resources
        if hasattr(self, "_parallel_finder"):
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
        if hasattr(self, "_cancellation_token"):
            self._cancellation_token.set()
            logger.debug("Sprite scan cancellation requested")
