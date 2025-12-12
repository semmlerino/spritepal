"""
Background worker for scanning ROM for HAL-compressed sprites.

This worker moves the heavy sprite scanning operation off the main thread
to prevent UI freezes during ROM scanning.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal

from core.sprite_finder import SpriteFinder
from core.workers.base import handle_worker_errors
from core.workers.specialized import ScanWorkerBase
from utils.logging_config import get_logger

logger = get_logger(__name__)


class SpriteScanWorker(ScanWorkerBase):
    """
    Background worker that scans a ROM for HAL-compressed sprites.

    Moves the blocking ROM reading and sprite validation operations
    off the main thread to keep the UI responsive.

    Signals (inherited from ScanWorkerBase):
        item_found(dict): Emitted when a sprite is found during scanning
        scan_progress(int, int): Emitted with (current, total) progress
        scan_finished(bool): Emitted when scan completes

    Signals (custom):
        sprites_found(list): Emitted with final list of all found sprites
    """

    # Custom signal for final results
    sprites_found = Signal(list)  # Final list of all found sprites

    def __init__(
        self,
        rom_path: str,
        step: int = 0x1000,
    ) -> None:
        """
        Initialize sprite scan worker.

        Args:
            rom_path: Path to the ROM file to scan
            step: Step size in bytes between scan attempts (default: 4KB)
        """
        super().__init__()
        self.rom_path = rom_path
        self.step = step
        self._operation_name = "SpriteScanWorker"

        logger.debug(f"SpriteScanWorker initialized for: {Path(rom_path).name}")

    @handle_worker_errors("sprite scanning", handle_interruption=True)
    def run(self) -> None:
        """Scan ROM for sprites in background thread."""
        rom_name = Path(self.rom_path).name
        logger.info(f"Starting sprite scan for: {rom_name}")
        self.emit_progress(0, f"Loading ROM {rom_name}...")

        # Check for cancellation early
        self.check_cancellation()

        # Read ROM data
        with Path(self.rom_path).open("rb") as f:
            rom_data = f.read()

        rom_size = len(rom_data)
        total_offsets = rom_size // self.step
        logger.info(f"Scanning {total_offsets} offsets (step=0x{self.step:X})")

        self.check_cancellation()

        # Create sprite finder
        finder = SpriteFinder()
        found_sprites: list[dict[str, Any]] = []

        # Scan through ROM
        for i, offset in enumerate(range(0, rom_size, self.step)):
            # Check for cancellation periodically
            self.check_cancellation()

            # Emit progress
            self.emit_scan_progress(i, total_offsets)

            # Try to find sprite at this offset
            sprite_info = finder.find_sprite_at_offset(rom_data, offset)
            if sprite_info:
                found_sprites.append(sprite_info)
                self.emit_item_found(sprite_info)
                logger.info(
                    f"Found sprite at 0x{offset:X}: "
                    f"{sprite_info.get('tile_count', '?')} tiles"
                )

        # Emit final results
        self.sprites_found.emit(found_sprites)
        self.scan_finished.emit(True)
        self.emit_progress(100, f"Found {len(found_sprites)} sprites")
        self.operation_finished.emit(
            True, f"Scan complete: found {len(found_sprites)} sprites"
        )

        logger.info(f"Sprite scan complete: found {len(found_sprites)} sprites")
