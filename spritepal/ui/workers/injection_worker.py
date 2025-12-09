"""
Qt worker thread for sprite injection process.
This module contains the Qt-specific worker thread for sprite injection.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from core.injector import SpriteInjector
from core.workers.base import BaseWorker, handle_worker_errors
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

logger = get_logger(__name__)


class InjectionWorker(BaseWorker):
    """Worker thread for sprite injection process.

    Migrated to BaseWorker for standardized signals and cancellation support.
    The injection_finished signal is maintained for backwards compatibility
    and is automatically emitted when operation_finished fires.
    """

    def __init__(
        self,
        sprite_path: str,
        vram_input: str,
        vram_output: str,
        offset: int,
        metadata_path: str | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.sprite_path: str = sprite_path
        self.vram_input: str = vram_input
        self.vram_output: str = vram_output
        self.offset: int = offset
        self.metadata_path: str | None = metadata_path
        self.injector: SpriteInjector = SpriteInjector()

        # Backwards compatibility: alias operation_finished to injection_finished
        # Callers expecting injection_finished(bool, str) will still work
        # since operation_finished has the same signature
        self.injection_finished = self.operation_finished

    @override
    @handle_worker_errors("sprite injection", handle_interruption=True)
    def run(self) -> None:
        """Run the injection process with cancellation support."""
        logger.info(
            f"Starting injection worker: sprite={self.sprite_path}, "
            f"vram_in={self.vram_input}, vram_out={self.vram_output}"
        )

        # Load metadata if available
        if self.metadata_path:
            self.check_cancellation()
            self.emit_progress(10, "Loading metadata...")
            logger.debug(f"Loading metadata from {self.metadata_path}")
            self.injector.load_metadata(self.metadata_path)

        # Validate sprite
        self.check_cancellation()
        self.emit_progress(30, "Validating sprite file...")
        logger.debug(f"Validating sprite: {self.sprite_path}")
        valid, message = self.injector.validate_sprite(self.sprite_path)
        if not valid:
            logger.error(f"Sprite validation failed: {message}")
            self.operation_finished.emit(False, message)
            return

        # Perform injection
        self.check_cancellation()
        self.emit_progress(50, "Converting sprite to 4bpp format...")

        self.check_cancellation()
        self.emit_progress(70, f"Injecting into VRAM at offset 0x{self.offset:04X}...")

        success, message = self.injector.inject_sprite(
            self.sprite_path, self.vram_input, self.vram_output, self.offset
        )

        if success:
            self.emit_progress(100, "Injection complete!")
            logger.info(f"Injection completed successfully: {message}")
        else:
            logger.error(f"Injection failed: {message}")

        self.operation_finished.emit(success, message)
