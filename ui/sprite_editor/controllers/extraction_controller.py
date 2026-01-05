#!/usr/bin/env python3
"""
Extraction controller for sprite extraction from VRAM dumps.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog

from ..services import SpriteRenderer
from ..workers import ExtractWorker, MultiPaletteExtractWorker

if TYPE_CHECKING:
    from PIL import Image

    from ..views.tabs import ExtractTab


class ExtractionController(QObject):
    """Controller for sprite extraction operations."""

    # Signals
    extraction_completed = Signal(object, int)  # image, tile_count
    extraction_failed = Signal(str)  # error message
    progress_updated = Signal(int, str)  # percent, message
    multi_palette_completed = Signal(dict, int)  # palette_images, tile_count

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._view: ExtractTab | None = None
        self._worker: ExtractWorker | None = None
        self._multi_worker: MultiPaletteExtractWorker | None = None
        self.renderer = SpriteRenderer()

        # File paths
        self.vram_file: str = ""
        self.cgram_file: str = ""

    def set_view(self, view: "ExtractTab") -> None:
        """Set the extract tab view."""
        self._view = view
        self._connect_view_signals()

    def _connect_view_signals(self) -> None:
        """Connect view signals to controller methods."""
        if not self._view:
            return

        self._view.extract_requested.connect(self.extract_sprites)
        self._view.browse_vram_requested.connect(self.browse_vram_file)
        self._view.browse_cgram_requested.connect(self.browse_cgram_file)

    def browse_vram_file(self) -> None:
        """Open file dialog to select VRAM dump."""
        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Open VRAM Dump",
            "",
            "VRAM Dumps (*.dmp *.bin);;All Files (*)",
        )
        if file_path:
            self.vram_file = file_path
            if self._view:
                self._view.set_vram_file(file_path)

    def browse_cgram_file(self) -> None:
        """Open file dialog to select CGRAM dump."""
        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Open CGRAM Dump",
            "",
            "CGRAM Dumps (*.dmp *.bin);;All Files (*)",
        )
        if file_path:
            self.cgram_file = file_path
            if self._view:
                self._view.set_cgram_file(file_path)

    def extract_sprites(self) -> None:
        """Start sprite extraction."""
        if not self._view:
            return

        params = self._view.get_extraction_params()

        if not params["vram_file"]:
            self._view.append_output("Error: No VRAM file selected")
            return

        # Clear output
        self._view.clear_output()
        self._view.set_extract_enabled(False)
        self._view.append_output(f"Extracting from: {params['vram_file']}")

        # Create and start worker
        self._worker = ExtractWorker(
            vram_file=params["vram_file"],
            offset=params["offset"],
            size=params["size"],
            tiles_per_row=params["tiles_per_row"],
            palette_num=params["palette_num"] if params["use_palette"] else None,
            cgram_file=params["cgram_file"] if params["use_palette"] else None,
        )

        self._worker.progress.connect(self._on_progress)
        self._worker.error.connect(self._on_error)
        self._worker.result.connect(self._on_extraction_complete)
        self._worker.finished.connect(self._on_worker_finished)

        self._worker.start()

    def extract_multi_palette(
        self,
        vram_file: str,
        cgram_file: str,
        offset: int,
        size: int,
        tiles_per_row: int = 16,
        oam_file: str | None = None,
    ) -> None:
        """Start multi-palette extraction."""
        self._multi_worker = MultiPaletteExtractWorker(
            vram_file=vram_file,
            offset=offset,
            size=size,
            cgram_file=cgram_file,
            tiles_per_row=tiles_per_row,
            oam_file=oam_file,
        )

        self._multi_worker.progress.connect(self._on_progress)
        self._multi_worker.error.connect(self._on_error)
        self._multi_worker.result.connect(self._on_multi_palette_complete)
        self._multi_worker.finished.connect(self._on_worker_finished)

        self._multi_worker.start()

    def _on_progress(self, percent: int, message: str) -> None:
        """Handle progress updates."""
        self.progress_updated.emit(percent, message)
        if self._view:
            self._view.append_output(f"[{percent}%] {message}")

    def _on_error(self, error: str) -> None:
        """Handle extraction error."""
        self.extraction_failed.emit(error)
        if self._view:
            self._view.append_output(f"ERROR: {error}")
            self._view.set_extract_enabled(True)

    def _on_extraction_complete(self, image: "Image.Image", tile_count: int) -> None:
        """Handle successful extraction."""
        if self._view:
            self._view.append_output(f"Extracted {tile_count} tiles successfully!")
        self.extraction_completed.emit(image, tile_count)

    def _on_multi_palette_complete(self, palette_images: dict, tile_count: int) -> None:
        """Handle successful multi-palette extraction."""
        self.multi_palette_completed.emit(palette_images, tile_count)

    def _on_worker_finished(self) -> None:
        """Handle worker completion."""
        if self._view:
            self._view.set_extract_enabled(True)
        self._worker = None
        self._multi_worker = None
