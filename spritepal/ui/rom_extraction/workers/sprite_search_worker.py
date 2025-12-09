"""
Sprite Search Worker

Worker thread for searching sprites in a specific direction from current position.
Used for intelligent next/previous navigation that skips empty ROM areas.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.protocols.manager_protocols import ROMExtractorProtocol

from PySide6.QtCore import Signal

from core.workers.base import BaseWorker, handle_worker_errors
from utils.constants import MAX_ROM_SIZE
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Search constants
SEARCH_STEP = 0x100  # Search in 256-byte increments
MAX_SEARCH_DISTANCE = 0x100000  # Stop after 1MB
SEARCH_BATCH_SIZE = 100  # Check this many offsets before yielding

class SpriteSearchWorker(BaseWorker):
    """
    Worker for searching next/previous sprite from current position.

    Features:
    - Directional search (forward/backward)
    - Region-aware skipping of empty areas
    - Progress reporting
    - Cancellation support
    """

    # Signals
    sprite_found = Signal(int, float)  # offset, quality
    search_complete = Signal(bool)  # True if sprite found

    # Note: progress signal is already defined in BaseWorker as Signal(int, str)
    # We'll override emit_progress to convert our (current, total) to (percent, message)

    def __init__(self, rom_path: str, start_offset: int, end_offset: int,
                 direction: int, rom_extractor: ROMExtractorProtocol, parent: QObject | None = None):
        super().__init__(parent)
        self.rom_path = rom_path
        self.start_offset = start_offset
        self.end_offset = end_offset
        self.direction = direction  # 1 for forward, -1 for backward
        self.rom_extractor = rom_extractor

    @handle_worker_errors("sprite search", handle_interruption=True)
    def run(self):
        """Search for sprites in the specified direction"""
        logger.debug(f"Starting sprite search from 0x{self.start_offset:06X} "
                    f"direction={self.direction}")

        # Calculate search parameters
        if self.direction > 0:
            # Forward search
            current = self.start_offset + SEARCH_STEP
            end = min(self.end_offset, self.start_offset + MAX_SEARCH_DISTANCE)
            step = SEARCH_STEP
        else:
            # Backward search
            current = self.start_offset - SEARCH_STEP
            end = max(self.end_offset, self.start_offset - MAX_SEARCH_DISTANCE)
            step = -SEARCH_STEP

        # Calculate total steps for progress
        total_distance = abs(end - current)
        total_steps = total_distance // abs(step)
        current_step = 0

        # Validate ROM size before loading to prevent OOM
        rom_size = Path(self.rom_path).stat().st_size
        if rom_size > MAX_ROM_SIZE:
            self.emit_error(f"ROM file too large: {rom_size:,} bytes (max: {MAX_ROM_SIZE:,})")
            return

        # Open ROM file
        with Path(self.rom_path).open("rb") as rom_file:
            rom_data = rom_file.read()

        # Search loop
        batch_count = 0
        while (self.direction > 0 and current < end) or \
              (self.direction < 0 and current > end):

            # Check cancellation using BaseWorker method
            self.check_cancellation()

            # Check if this offset contains a valid sprite
            try:
                # Quick validation check
                is_valid = self._quick_sprite_check(rom_data, current)

                if is_valid:
                    # Do full validation
                    quality = self._full_sprite_validation(rom_data, current)
                    if quality > 0:
                        logger.info(f"Found sprite at 0x{current:06X} "
                                  f"with quality {quality:.2f}")
                        self.sprite_found.emit(current, quality)
                        self.search_complete.emit(True)
                        self.operation_finished.emit(True, f"Found sprite at 0x{current:06X}")
                        return

            except Exception as e:
                logger.debug(f"Error checking offset 0x{current:06X}: {e}")

            # Update progress
            current_step += 1
            if current_step % 10 == 0:  # Update every 10 steps
                percent = int((current_step / total_steps) * 100) if total_steps > 0 else 0
                self.emit_progress(percent, f"Searching... (step {current_step}/{total_steps})")

            # Move to next offset
            current += step

            # Yield periodically to stay responsive
            batch_count += 1
            if batch_count >= SEARCH_BATCH_SIZE:
                self.msleep(1)  # Brief pause
                batch_count = 0

        # No sprite found
        logger.debug("Search complete, no sprites found")
        self.search_complete.emit(False)
        self.operation_finished.emit(True, "Search complete - no sprites found")

    def _quick_sprite_check(self, rom_data: bytes, offset: int) -> bool:
        """
        Quick check if offset might contain a sprite.
        Uses heuristics to filter out obviously invalid data.
        """
        if offset + 0x20 > len(rom_data):
            return False

        # Check for common sprite signatures
        # Many sprites start with specific compression headers
        header = rom_data[offset:offset+4]

        # Check for LZ compression signature (common in SNES)
        if header[0] == 0x10:  # LZ compressed
            return True

        # Check for other common patterns
        # Non-zero data that isn't all 0xFF
        chunk = rom_data[offset:offset+0x20]
        non_zero = sum(1 for b in chunk if b != 0)
        non_ff = sum(1 for b in chunk if b != 0xFF)

        # If chunk has reasonable data distribution
        return bool(non_zero > 4 and non_ff > 4)

    def _full_sprite_validation(self, rom_data: bytes, offset: int) -> float:
        """
        Full sprite validation to determine quality score.
        Returns 0.0 if not a valid sprite, otherwise quality score 0.0-1.0.
        """
        try:
            # Use the ROM extractor's sprite finder for validation
            # TODO: Implement sprite_finder attribute on ROMExtractor
            sprite_finder = self.rom_extractor.sprite_finder  # type: ignore[attr-defined]

            # Try to decompress and validate
            result = sprite_finder.find_sprite_at_offset(rom_data, offset)

            if result and result.get("valid", False):
                # Calculate quality based on various factors
                tile_count = result.get("tile_count", 0)
                compressed_size = result.get("compressed_size", 0)

                # Basic quality calculation
                quality = 0.5  # Base quality for valid sprite

                # Bonus for reasonable tile count
                if 4 <= tile_count <= 256:
                    quality += 0.2

                # Bonus for good compression ratio
                if compressed_size > 0 and tile_count > 0:
                    uncompressed_size = tile_count * 32  # 32 bytes per tile
                    ratio = compressed_size / uncompressed_size
                    if 0.1 <= ratio <= 0.8:
                        quality += 0.3

                return min(1.0, quality)

        except Exception as e:
            logger.debug(f"Validation error at 0x{offset:06X}: {e}")

        return 0.0

    # cancel() method is inherited from BaseWorker
