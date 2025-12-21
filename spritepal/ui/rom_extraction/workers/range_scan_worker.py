"""Worker thread for comprehensive range scanning of ROM data"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.protocols.manager_protocols import ROMCacheProtocol
    from core.rom_extractor import ROMExtractor

from PySide6.QtCore import Signal

from core.workers.base import BaseWorker, handle_worker_errors
from utils.constants import MAX_ROM_SIZE
from utils.logging_config import get_logger

# from utils.rom_cache import get_rom_cache # Removed due to DI

logger = get_logger(__name__)

class RangeScanWorker(BaseWorker):
    """Worker thread for comprehensive scanning of ROM ranges to find all sprites"""

    # Custom signals (BaseWorker provides progress, error, warning, operation_finished)
    sprite_found = Signal(int, float)
    """Emitted when a sprite is found. Args: offset (int), quality_score (float 0.0-1.0)."""

    progress_update = Signal(int, int)
    """Emitted with scan progress. Args: current_offset (int), progress_percentage (0-100)."""

    scan_complete = Signal(bool)
    """Emitted when scan completes. Args: success (bool)."""

    scan_paused = Signal()
    """Emitted when scan is paused."""

    scan_resumed = Signal()
    """Emitted when scan resumes after pause."""

    scan_stopped = Signal()
    """Emitted when scan is stopped by user."""

    cache_status = Signal(str)
    """Emitted with cache status updates. Args: status_message."""

    cache_progress_saved = Signal(int, int, int)
    """Emitted when cache progress is saved. Args: current_offset, sprites_found, progress_percent."""

    def __init__(self, rom_path: str, start_offset: int, end_offset: int,
                 step_size: int, extractor: ROMExtractor, parent: QObject | None = None, *,
                 rom_cache: ROMCacheProtocol):
        """
        Initialize range scan worker

        Args:
            rom_path: Path to ROM file
            start_offset: Starting offset for scan
            end_offset: Ending offset for scan (inclusive)
            step_size: Step size between offsets to check
            extractor: ROM extractor instance
            rom_cache: Injected ROMCacheProtocol instance
        """
        super().__init__(parent)
        self.rom_path = rom_path
        self.start_offset = start_offset
        self.end_offset = end_offset
        self.step_size = step_size
        self.extractor = extractor
        self._operation_name = f"RangeScanWorker-{start_offset:X}-{end_offset:X}"  # For logging

        # Scan parameters
        self.quality_threshold = 0.5
        self.min_sprite_size = 512  # At least 16 tiles (32 bytes per tile)
        self.max_sprite_size = 32768  # 32KB limit for decompression

        # Control flag for stopping (pause is handled by BaseWorker)
        self._should_stop = False

        # Cache integration
        self.rom_cache = rom_cache

        self.found_sprites: list[dict[str, Any]] = []
        self.current_offset = start_offset
        self.scan_params: dict[str, Any] = {}

    @handle_worker_errors("range scanning")
    def run(self):
        """Scan the entire specified range for valid sprites"""
        try:
            # Validate ROM size before loading to prevent OOM
            rom_size = Path(self.rom_path).stat().st_size
            if rom_size > MAX_ROM_SIZE:
                self.emit_error(f"ROM file too large: {rom_size:,} bytes (max: {MAX_ROM_SIZE:,})")
                return

            # Load ROM data once
            with Path(self.rom_path).open("rb") as f:
                rom_data = f.read()

            # Check for cached partial results
            self.scan_params = {
                "start_offset": self.start_offset,
                "end_offset": self.end_offset,
                "step": self.step_size,
                "quality_threshold": self.quality_threshold,
                "min_sprite_size": self.min_sprite_size,
                "max_sprite_size": self.max_sprite_size
            }

            cached_progress = self.rom_cache.get_partial_scan_results(self.rom_path, self.scan_params)
            if cached_progress and not cached_progress.get("completed", False):
                # Resume from cached progress
                self.found_sprites = cached_progress.get("found_sprites", [])
                self.current_offset = cached_progress.get("current_offset", self.start_offset)
                # Prevent division by zero
                scan_range = self.end_offset - self.start_offset
                progress_pct = int(((self.current_offset - self.start_offset) / scan_range) * 100) if scan_range > 0 else 0
                self.cache_status.emit(f"Resumed from cache: {progress_pct}% complete, {len(self.found_sprites)} sprites found")
                logger.info(f"Resuming scan from cached progress: 0x{self.current_offset:06X}, {len(self.found_sprites)} sprites found")
            else:
                self.current_offset = self.start_offset
                self.found_sprites = []
                if cached_progress and cached_progress.get("completed", False):
                    self.cache_status.emit("Starting fresh scan (completed cache found but ignored)")
                    logger.info("Found completed scan in cache, but rescanning per user request")
                else:
                    self.cache_status.emit("Starting fresh scan (no cache found)")

            sprites_found = len(self.found_sprites)

            logger.info(f"Starting range scan: 0x{self.current_offset:06X} to 0x{self.end_offset:06X}")

            # Scan through the range starting from current_offset
            for offset in range(self.current_offset, self.end_offset + 1, self.step_size):
                self.current_offset = offset
                # Check if we should stop
                if self._should_stop:
                    logger.info("Range scan stopped by user")
                    # Save progress to cache before stopping
                    self._save_progress(self.scan_params, completed=False)
                    self.scan_stopped.emit()
                    self.operation_finished.emit(False, "Scan stopped by user")
                    return

                # Check cancellation using BaseWorker method
                try:
                    self.check_cancellation()
                except InterruptedError:
                    logger.info("Range scan cancelled")
                    self._save_progress(self.scan_params, completed=False)
                    self.scan_stopped.emit()
                    self.operation_finished.emit(False, "Scan cancelled")
                    return

                # Handle pause state using BaseWorker method
                self.wait_if_paused()

                # Check stop again after potential pause
                if self._should_stop:
                    logger.info("Range scan stopped by user")
                    # Save progress to cache before stopping
                    self._save_progress(self.scan_params, completed=False)
                    self.scan_stopped.emit()
                    self.operation_finished.emit(False, "Scan stopped by user")
                    return

                # Emit progress update periodically (every 1024 steps to avoid too many signals)
                if (offset - self.start_offset) % (self.step_size * 1024) == 0:
                    # Calculate progress as percentage of scan range
                    scan_range = self.end_offset - self.start_offset
                    progress_pct = int(((offset - self.start_offset) / scan_range) * 100) if scan_range > 0 else 0
                    self.progress_update.emit(offset, progress_pct)
                    # Also emit BaseWorker progress
                    self.emit_progress(progress_pct, f"Scanning offset 0x{offset:06X}")
                    # Also save progress to cache periodically
                    if self._save_progress(self.scan_params, completed=False):
                        self.cache_progress_saved.emit(offset, len(self.found_sprites), progress_pct)

                # Boundary check
                if offset < 0 or offset >= len(rom_data):
                    continue

                try:
                    # Try to find compressed sprite at this offset
                    _, sprite_data = self.extractor.rom_injector.find_compressed_sprite(
                        rom_data, offset, expected_size=self.max_sprite_size
                    )

                    # Check if sprite data meets minimum size requirement
                    if len(sprite_data) >= self.min_sprite_size:
                        # Assess sprite quality
                        quality = self.extractor._assess_sprite_quality(sprite_data)

                        # If quality meets threshold, emit found signal
                        if quality >= self.quality_threshold:
                            self.sprite_found.emit(offset, quality)
                            sprites_found += 1
                            # Add to cached sprites list
                            sprite_info = {
                                "offset": offset,
                                "quality": quality,
                                "size": len(sprite_data)
                            }
                            self.found_sprites.append(sprite_info)
                            logger.debug(f"Found sprite at 0x{offset:06X} with quality {quality:.2f}")

                except (ValueError, IndexError, KeyError):
                    # Expected errors: invalid sprite data, invalid offset, etc.
                    # These are normal during scanning, continue silently
                    pass
                except (MemoryError, OSError) as e:
                    # Serious errors that might indicate system issues
                    logger.warning(f"System error at offset 0x{offset:06X}: {e}")
                    # Continue scanning but log the issue
                except Exception as e:
                    # Unexpected errors - log but continue
                    logger.debug(f"Unexpected error at offset 0x{offset:06X}: {e}")

            # Final progress update
            self.progress_update.emit(self.end_offset, 100)

            logger.info(f"Range scan complete. Found {sprites_found} sprites in range "
                       f"0x{self.start_offset:06X} to 0x{self.end_offset:06X}")

            # Save completed scan to cache
            if self._save_progress(self.scan_params, completed=True):
                self.cache_status.emit(f"Scan complete - saved {len(self.found_sprites)} sprites to cache")

            # Emit completion signal
            self.scan_complete.emit(True)
            self.operation_finished.emit(True, f"Scan complete. Found {sprites_found} sprites.")

        except OSError as e:
            logger.exception("File I/O error during range scan")
            self.scan_complete.emit(False)
            self.operation_finished.emit(False, f"File I/O error: {e}")
        except MemoryError as e:
            logger.exception("Memory error during range scan")
            self.scan_complete.emit(False)
            self.operation_finished.emit(False, f"Memory error: {e}")
        except Exception as e:
            logger.exception("Unexpected error during range scan")
            self.scan_complete.emit(False)
            self.operation_finished.emit(False, f"Unexpected error: {e}")

    # emit_error is inherited from BaseWorker

    def pause_scan(self):
        """Pause the scanning process"""
        if not self.is_paused:
            self.pause()  # Use BaseWorker's pause method
            logger.info("Range scan paused")
            # Save progress when pausing
            if self.scan_params:  # Only save if scan has started
                self._save_progress(self.scan_params, completed=False)
            self.scan_paused.emit()

    def resume_scan(self):
        """Resume the scanning process"""
        if self.is_paused:
            self.resume()  # Use BaseWorker's resume method
            logger.info("Range scan resumed")
            self.scan_resumed.emit()

    def stop_scan(self):
        """Stop the scanning process"""
        self._should_stop = True
        self.resume()  # Ensure we don't stay paused if stopping
        logger.info("Range scan stop requested")

    def is_stopping(self) -> bool:
        """Check if scan is currently stopping"""
        return self._should_stop or self.is_cancelled

    def _save_progress(self, scan_params: dict[str, Any], completed: bool = False) -> bool:
        """Save current scan progress to cache"""
        try:
            return self.rom_cache.save_partial_scan_results(
                self.rom_path,
                scan_params,
                self.found_sprites,
                self.current_offset,
                completed
            )
        except Exception as e:
            logger.warning(f"Failed to save scan progress to cache: {e}")
            return False
