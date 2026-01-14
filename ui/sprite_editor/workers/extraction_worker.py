#!/usr/bin/env python3
"""
Worker thread for sprite extraction operations.
Handles background extraction of sprites from VRAM dumps.
"""

import logging
from pathlib import Path
from typing import override

from PySide6.QtCore import QObject, Signal

from core.palette_manager import PaletteManager

from ..services.sprite_renderer import SpriteRenderer
from .base_worker import BaseWorker

logger = logging.getLogger(__name__)


class ExtractWorker(BaseWorker):
    """Worker thread for sprite extraction."""

    # result signal: (image, tile_count)
    result = Signal(object, int)

    def __init__(
        self,
        vram_file: str,
        offset: int,
        size: int,
        tiles_per_row: int = 16,
        palette_num: int | None = None,
        cgram_file: str | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the extraction worker.

        Args:
            vram_file: Path to VRAM dump file
            offset: Byte offset to start extraction
            size: Number of bytes to extract
            tiles_per_row: Number of tiles per row in output
            palette_num: Optional palette number to apply
            cgram_file: Optional CGRAM file for palette
            parent: Parent QObject
        """
        super().__init__(vram_file, parent)
        self.vram_file = vram_file
        self.offset = offset
        self.size = size
        self.tiles_per_row = tiles_per_row
        self.palette_num = palette_num
        self.cgram_file = cgram_file
        self.renderer = SpriteRenderer()

    @override
    def run(self) -> None:
        """Execute the extraction in background thread."""
        try:
            self.emit_progress(10, "Extracting sprites from VRAM...")

            if self.is_cancelled():
                return

            # Extract sprites
            image, tile_count = self.renderer.extract(self.vram_file, self.offset, self.size, self.tiles_per_row)

            if self.is_cancelled():
                return

            # Apply palette if requested
            cgram_path = Path(self.cgram_file) if self.cgram_file else None
            if self.palette_num is not None and cgram_path and cgram_path.exists():
                # OAM palette numbers (0-7) map to CGRAM sprite palettes (8-15)
                cgram_palette_num = self.palette_num + 8 if self.palette_num < 8 else self.palette_num
                self.emit_progress(70, f"Applying palette {self.palette_num} (CGRAM {cgram_palette_num})...")
                
                pm = PaletteManager()
                try:
                    pm.load_cgram(str(cgram_path))
                    palette = pm.get_flat_palette(cgram_palette_num)
                    if palette:
                        image.putpalette(palette)
                except Exception as e:
                    logger.warning(f"Failed to apply palette: {e}")

            if self.is_cancelled():
                return

            self.emit_progress(100, "Extraction complete!")
            self.result.emit(image, tile_count)
            self.emit_finished()

        except Exception as e:
            self.handle_exception(e)


class MultiPaletteExtractWorker(BaseWorker):
    """Worker thread for multi-palette extraction."""

    # result signal: (dict of palette_name -> image, tile_count)
    result = Signal(dict, int)

    def __init__(
        self,
        vram_file: str,
        offset: int,
        size: int,
        cgram_file: str,
        tiles_per_row: int = 16,
        oam_file: str | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the multi-palette extraction worker.

        Args:
            vram_file: Path to VRAM dump file
            offset: Byte offset to start extraction
            size: Number of bytes to extract
            cgram_file: CGRAM file for palettes
            tiles_per_row: Number of tiles per row
            oam_file: Optional OAM file for palette mapping
            parent: Parent QObject
        """
        super().__init__(vram_file, parent)
        self.vram_file = vram_file
        self.offset = offset
        self.size = size
        self.cgram_file = cgram_file
        self.tiles_per_row = tiles_per_row
        self.oam_file = oam_file
        self.renderer = SpriteRenderer()

    @override
    def run(self) -> None:
        """Execute the multi-palette extraction in background thread."""
        try:
            self.emit_progress(10, "Setting up extraction...")

            if self.is_cancelled():
                return

            # Set up OAM mapper if available
            oam_path = Path(self.oam_file) if self.oam_file else None
            if oam_path and oam_path.exists():
                from ..services.oam_palette_mapper import create_tile_palette_map

                oam_mapper = create_tile_palette_map(str(oam_path))
                self.renderer.set_oam_mapper(oam_mapper)

            if self.is_cancelled():
                return

            self.emit_progress(30, "Extracting with multiple palettes...")

            # Extract with multiple palettes
            palette_images, tile_count = self.renderer.extract_multi_palette(
                self.vram_file, self.offset, self.size, self.cgram_file, self.tiles_per_row
            )

            if self.is_cancelled():
                return

            self.emit_progress(100, "Multi-palette extraction complete!")
            self.result.emit(palette_images, tile_count)
            self.emit_finished()

        except Exception as e:
            self.handle_exception(e)
