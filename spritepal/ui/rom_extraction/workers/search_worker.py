"""Worker thread for searching next/previous valid sprite"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ROMExtractorProtocol

from PySide6.QtCore import QThread, Signal

from core.parallel_sprite_finder import ParallelSpriteFinder
from core.workers.base import handle_worker_errors
from utils.constants import MAX_ROM_SIZE
from utils.logging_config import get_logger

logger = get_logger(__name__)

class SpriteSearchWorker(QThread):
    """Worker thread for searching next/previous valid sprite"""

    sprite_found = Signal(int, float)  # offset, quality
    search_complete = Signal(bool)  # found
    error = Signal(str, Exception)  # error message, exception
    progress = Signal(int, int)  # current, total

    def __init__(self, rom_path: str, start_offset: int, end_offset: int,
                 direction: int, extractor: ROMExtractorProtocol, parent: QThread | None = None):
        super().__init__(parent)
        self.rom_path = rom_path
        self.start_offset = start_offset
        self.end_offset = end_offset
        self.direction = direction  # 1 for forward, -1 for backward
        self.extractor = extractor
        self._cancelled = False
        self._cancellation_token = threading.Event()

        # Default step size
        self.step = 0x100  # 256-byte alignment

        # Create parallel finder for more efficient searching
        self._parallel_finder = ParallelSpriteFinder(
            num_workers=2,  # Use fewer workers for single direction search
            chunk_size=0x20000,  # 128KB chunks for smaller search areas
            step_size=self.step
        )

    @handle_worker_errors("sprite searching")
    def run(self):
        """Search for valid sprite in the specified direction"""
        try:
            if self._cancellation_token:
                self._cancellation_token.clear()

            # Validate ROM size before loading to prevent OOM
            rom_size = Path(self.rom_path).stat().st_size
            if rom_size > MAX_ROM_SIZE:
                self.error.emit(
                    f"ROM file too large: {rom_size:,} bytes (max: {MAX_ROM_SIZE:,})",
                    ValueError(f"ROM exceeds max size of {MAX_ROM_SIZE}")
                )
                return

            with Path(self.rom_path).open("rb") as f:
                rom_data = f.read()

            # Search parameters
            max_search_distance = 0x100000  # Search up to 1MB away
            quality_threshold = 0.3  # Lower threshold for better detection
            rom_size = len(rom_data)

            # Determine search range
            if self.direction > 0:
                search_start = self.start_offset + self.step
                search_end = min(self.end_offset, self.start_offset + max_search_distance, rom_size)
            else:
                # For backward search
                search_end = self.start_offset - self.step
                search_start = max(self.end_offset, self.start_offset - max_search_distance, 0)
                # Swap for proper range handling
                search_start, search_end = search_end, search_start

            # Validate range
            search_start = max(0, search_start)
            search_end = min(rom_size, search_end)

            if search_start >= search_end:
                logger.debug("Invalid search range, no sprites found")
                self.search_complete.emit(False)
                return

            logger.debug(f"Searching range 0x{search_start:X} to 0x{search_end:X} (direction: {self.direction})")

            # Progress callback
            def progress_callback(current_progress: int, total_progress: int):
                # Simple progress mapping
                search_range = search_end - search_start
                current_step = int((current_progress / 100) * (search_range // self.step))
                total_steps = int(search_range // self.step)
                self.progress.emit(current_step, total_steps)

            # Use parallel finder for the search
            search_results = self._parallel_finder.search_parallel(
                self.rom_path,
                start_offset=search_start,
                end_offset=search_end,
                progress_callback=progress_callback,
                cancellation_token=self._cancellation_token
            )

            # Filter results by quality threshold and find the best match
            valid_results = [r for r in search_results if r.confidence >= quality_threshold]

            if valid_results:
                # For forward search, take the first (closest to start)
                # For backward search, take the last (closest to original position)
                if self.direction > 0:
                    best_result = min(valid_results, key=lambda r: r.offset)
                else:
                    best_result = max(valid_results, key=lambda r: r.offset)

                logger.info(
                    f"Found sprite at 0x{best_result.offset:X}: "
                    f"quality={best_result.confidence:.2f}, tiles={best_result.tile_count}"
                )

                self.sprite_found.emit(best_result.offset, best_result.confidence)
                self.search_complete.emit(True)
            else:
                logger.debug("No valid sprites found in search range")
                self.search_complete.emit(False)

        except Exception as e:
            logger.exception("Error in sprite search")
            self.error.emit("Search failed", e)
            self.search_complete.emit(False)
        finally:
            # Cleanup parallel finder resources
            if hasattr(self, "_parallel_finder"):
                try:
                    self._parallel_finder.shutdown()
                except Exception as cleanup_error:
                    logger.warning(f"Error during parallel finder cleanup: {cleanup_error}")

    def cancel(self):
        """Cancel the search"""
        self._cancelled = True
        if hasattr(self, "_cancellation_token"):
            self._cancellation_token.set()
            logger.debug("Sprite search cancellation requested")
