#!/usr/bin/env python3
"""
Worker thread for sprite injection operations.
Handles background injection of sprites into VRAM dumps.
"""

from typing import override

from PySide6.QtCore import QObject, Signal

from ..services.image_converter import ImageConverter
from ..services.vram_service import VRAMService
from .base_worker import BaseWorker


class InjectWorker(BaseWorker):
    """Worker thread for sprite injection."""

    # result signal: output file path
    result = Signal(str)

    def __init__(
        self,
        png_file: str,
        vram_file: str,
        offset: int,
        output_file: str,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the injection worker.

        Args:
            png_file: Path to PNG file to inject
            vram_file: Path to VRAM dump file
            offset: Byte offset for injection
            output_file: Path for output file
            parent: Parent QObject
        """
        super().__init__(png_file, parent)
        self.png_file = png_file
        self.vram_file = vram_file
        self.offset = offset
        self.output_file = output_file
        self.converter = ImageConverter()
        self.vram_service = VRAMService()

    @override
    def run(self) -> None:
        """Execute the injection in background thread."""
        try:
            # Validate PNG
            self.emit_progress(10, "Validating PNG file...")
            valid, issues = self.converter.validate_png(self.png_file)
            if not valid:
                self.emit_error("PNG validation failed:\n" + "\n".join(issues))
                return

            if self.is_cancelled():
                return

            # Convert to SNES format
            self.emit_progress(30, "Converting to SNES format...")
            tile_data, tile_count = self.converter.png_to_tiles(self.png_file)

            if self.is_cancelled():
                return

            # Inject into VRAM
            self.emit_progress(60, f"Injecting {tile_count} tiles into VRAM...")
            output = self.vram_service.inject(tile_data, self.vram_file, self.offset, self.output_file)

            if self.is_cancelled():
                return

            if isinstance(output, str):
                self.emit_progress(100, "Injection complete!")
                self.result.emit(output)
                self.emit_finished()
            else:
                self.emit_error("Injection failed: unexpected return type")

        except Exception as e:
            self.handle_exception(e)
