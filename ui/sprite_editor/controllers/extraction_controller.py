#!/usr/bin/env python3
"""
Extraction controller for sprite extraction from VRAM dumps.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog

from ui.common.signal_utils import safe_disconnect

from ..services import SpriteRenderer
from ..workers import ExtractWorker, MultiPaletteExtractWorker

if TYPE_CHECKING:
    from PIL import Image

    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache

    from ..views.tabs import ExtractTab


class ExtractionController(QObject):
    """Controller for sprite extraction operations."""

    # Signals
    extraction_failed = Signal(str)  # error message
    progress_updated = Signal(int, str)  # percent, message
    multi_palette_completed = Signal(dict, int)  # palette_images, tile_count

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        rom_cache: "ROMCache | None" = None,
        rom_extractor: "ROMExtractor | None" = None,
    ) -> None:
        super().__init__(parent)
        self._view: ExtractTab | None = None
        self._multi_palette_view: object = None
        self._worker: ExtractWorker | None = None
        self._multi_worker: MultiPaletteExtractWorker | None = None
        self.renderer = SpriteRenderer()

        # ROM services - injected dependencies
        self.rom_cache = rom_cache
        self.rom_extractor = rom_extractor
        self._mode = "vram"

        # File paths
        self.vram_file: str = ""
        self.cgram_file: str = ""
        self.oam_file: str = ""
        self.rom_file: str = ""

    def _cleanup_worker(self) -> None:
        """Clean up existing workers before creating new ones."""
        if self._worker is not None:
            safe_disconnect(self._worker.progress)
            safe_disconnect(self._worker.error)
            safe_disconnect(self._worker.result)
            safe_disconnect(self._worker.finished_signal)
            self._worker = None

        if self._multi_worker is not None:
            safe_disconnect(self._multi_worker.progress)
            safe_disconnect(self._multi_worker.error)
            safe_disconnect(self._multi_worker.result)
            safe_disconnect(self._multi_worker.finished_signal)
            self._multi_worker = None

    def cleanup(self) -> None:
        """Clean up resources before destruction."""
        self._cleanup_worker()
        if self._view is not None:
            safe_disconnect(self._view.extract_requested)
            safe_disconnect(self._view.browse_vram_requested)
            safe_disconnect(self._view.browse_cgram_requested)

    def set_view(self, view: "ExtractTab") -> None:
        """Set the extract tab view."""
        self._view = view
        self._connect_view_signals()

    def set_multi_palette_view(self, view: object) -> None:
        """Connect multi-palette tab signals.

        Args:
            view: MultiPaletteTab instance (typed as object to avoid circular import)
        """
        self._multi_palette_view = view

        # Set controller reference in view for prerequisite validation
        if hasattr(view, "set_extraction_controller"):
            view.set_extraction_controller(self)  # type: ignore[attr-defined]

        # Check if view has the required signals before connecting
        if hasattr(view, "browse_oam_requested"):
            view.browse_oam_requested.connect(self.browse_oam_file)  # type: ignore[attr-defined]

        if hasattr(view, "generate_preview_requested"):
            view.generate_preview_requested.connect(self._on_generate_multi_preview)  # type: ignore[attr-defined]

        # Controller → Tab: connect completion signal
        self.multi_palette_completed.connect(self._deliver_multi_palette_results)

    def _on_generate_multi_preview(self) -> None:
        """Handle preview generation request from tab."""
        # Get preview size from view (default 128 tiles if method doesn't exist)
        preview_size = 128
        if self._multi_palette_view is not None and hasattr(self._multi_palette_view, "get_preview_size"):
            preview_size = self._multi_palette_view.get_preview_size()  # type: ignore[attr-defined]

        self.generate_multi_palette_preview(preview_size)

    def _connect_view_signals(self) -> None:
        """Connect view signals to controller methods."""
        if not self._view:
            return

        self._view.extract_requested.connect(self.extract_sprites)
        self._view.load_rom_requested.connect(self.extract_from_rom)
        self._view.browse_vram_requested.connect(self.browse_vram_file)
        self._view.browse_cgram_requested.connect(self.browse_cgram_file)
        if hasattr(self._view, "browse_rom_requested"):
            self._view.browse_rom_requested.connect(self.browse_rom_file)

    def set_mode(self, mode: str) -> None:
        """Set the extraction mode ('vram' or 'rom')."""
        self._mode = mode
        if self._view:
            self._view.set_mode(mode)

    def browse_rom_file(self) -> None:
        """Open file dialog to select ROM file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Open ROM File",
            "",
            "SNES ROMs (*.sfc *.smc);;All Files (*)",
        )
        if file_path:
            self.rom_file = file_path
            if self._view and hasattr(self._view, "set_rom_file"):
                self._view.set_rom_file(file_path)

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
            # Trigger validation in multi-palette tab
            if self._multi_palette_view is not None and hasattr(self._multi_palette_view, "_validate_prerequisites"):
                self._multi_palette_view._validate_prerequisites()  # type: ignore[attr-defined]

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
            # Trigger validation in multi-palette tab
            if self._multi_palette_view is not None and hasattr(self._multi_palette_view, "_validate_prerequisites"):
                self._multi_palette_view._validate_prerequisites()  # type: ignore[attr-defined]

    def browse_oam_file(self) -> None:
        """Open file dialog to select OAM dump."""
        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Open OAM Dump",
            "",
            "OAM Dumps (*.dmp *.bin);;All Files (*)",
        )
        if file_path:
            self.oam_file = file_path
            # Update multi-palette view if it exists
            if self._multi_palette_view is not None and hasattr(self._multi_palette_view, "set_oam_file"):
                self._multi_palette_view.set_oam_file(file_path)  # type: ignore[attr-defined]

    def extract_from_rom(self) -> None:
        """Extract sprite directly from ROM."""
        if not self._view:
            return

        if not self.rom_extractor:
            self._view.append_output("ERROR: ROM extractor not initialized")
            return

        params = self._view.get_extraction_params()
        rom_file = str(params.get("rom_file", ""))
        offset = int(params["offset"])  # type: ignore

        if not rom_file:
            self._view.append_output("ERROR: ROM file required")
            return

        self._view.append_output(f"Loading from ROM: {rom_file} at 0x{offset:X}")

        # Use temp dir for output
        import tempfile
        from pathlib import Path

        from PIL import Image

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                output_base = str(Path(tmp_dir) / "rom_extract")

                # Run extraction (synchronous for now, could be threaded)
                png_path, info = self.rom_extractor.extract_sprite_from_rom(
                    rom_file, offset, output_base, sprite_name=f"sprite_{offset:X}"
                )

                # Load the result image
                image = Image.open(png_path)
                # Force load to ensure file can be closed/deleted if needed (though temp dir handles it)
                image.load()

                tile_count = int(info["tile_count"])  # type: ignore

                self._view.append_output(f"Loaded {tile_count} tiles.")

        except Exception as e:
            self._view.append_output(f"ERROR: {e}")
            self.extraction_failed.emit(str(e))

    def extract_sprites(self) -> None:
        """Start sprite extraction."""
        if not self._view:
            return

        # Validate parameters first
        is_valid, error_msg = self._view.validate_params()
        if not is_valid:
            self._view.append_output(f"Validation failed:\n{error_msg}")
            return

        params = self._view.get_extraction_params()

        # Clear output
        self._view.clear_output()
        self._view.set_extract_enabled(False)
        self._view.append_output(f"Extracting from: {params['vram_file']}")

        # Clean up any existing worker before creating new one
        self._cleanup_worker()

        # Create and start worker
        from typing import cast

        self._worker = ExtractWorker(
            vram_file=cast(str, params["vram_file"]),
            offset=cast(int, params["offset"]),
            size=cast(int, params["size"]),
            tiles_per_row=cast(int, params["tiles_per_row"]),
            palette_num=cast(int | None, params.get("palette_num")),
            cgram_file=cast(str | None, params.get("cgram_file")),
        )

        self._worker.progress.connect(self._on_progress)
        self._worker.error.connect(self._on_error)
        self._worker.result.connect(self._on_extraction_complete)
        self._worker.finished_signal.connect(self._on_worker_finished)

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
        # Clean up any existing worker before creating new one
        self._cleanup_worker()

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
        self._multi_worker.finished_signal.connect(self._on_worker_finished)

        self._multi_worker.start()

    def generate_multi_palette_preview(self, preview_size: int) -> None:
        """Generate multi-palette preview using current VRAM/CGRAM."""
        if not self.vram_file or not self.cgram_file:
            error_msg = "VRAM and CGRAM files required"
            self.extraction_failed.emit(error_msg)
            if self._view:
                self._view.append_output(f"ERROR: {error_msg}")
            return

        self.extract_multi_palette(
            vram_file=self.vram_file,
            cgram_file=self.cgram_file,
            offset=0xC000,
            size=preview_size * 32,
            oam_file=self.oam_file if self.oam_file else None,
        )

    def _on_progress(self, percent: int, message: str) -> None:
        """Handle progress updates."""
        self.progress_updated.emit(percent, message)
        if self._view:
            self._view.append_output(f"[{percent}%] {message}")

    def _on_error(self, error: str) -> None:
        """Handle extraction error."""
        self.extraction_failed.emit(error)

        # Route multi-palette errors to multi-palette tab
        if "multi-palette" in error.lower():
            if self._multi_palette_view is not None and hasattr(self._multi_palette_view, "append_output"):
                self._multi_palette_view.append_output(f"ERROR: {error}")  # type: ignore[attr-defined]
        elif self._view:
            # Route to extract tab
            self._view.append_output(f"ERROR: {error}")
            self._view.set_extract_enabled(True)

    def _on_extraction_complete(self, image: "Image.Image", tile_count: int) -> None:
        """Handle successful extraction."""
        if self._view:
            self._view.append_output(f"Extracted {tile_count} tiles successfully!")

    def _on_multi_palette_complete(self, palette_images: dict[str, "Image.Image"], tile_count: int) -> None:
        """Handle successful multi-palette extraction."""
        self.multi_palette_completed.emit(palette_images, tile_count)

    def _deliver_multi_palette_results(self, palette_images: dict[str, "Image.Image"], tile_count: int) -> None:
        """Send multi-palette results to view."""
        if self._multi_palette_view is None:
            return

        # Use new direct image method (efficient, no re-rendering)
        if hasattr(self._multi_palette_view, "set_palette_images"):
            self._multi_palette_view.set_palette_images(palette_images)  # type: ignore[attr-defined]
            # Use correct field names expected by viewer
            stats: dict[str, int | dict[int, int]] = {"sprite_count": tile_count}
            # Add palette_usage if OAM mapper available
            if self.renderer.oam_mapper:
                palette_usage = self.renderer.oam_mapper.get_active_palettes()
                if palette_usage:
                    stats["palette_usage"] = dict.fromkeys(palette_usage, 1)
            self._multi_palette_view.set_oam_statistics(stats)  # type: ignore[attr-defined]

        # Fallback to old method for backward compatibility
        elif hasattr(self._multi_palette_view, "set_single_image_all_palettes"):
            base_img = palette_images.get("palette_0")
            if base_img and base_img.mode == "P":
                # Extract palette data from pre-rendered images
                palettes: list[list[tuple[int, int, int]]] = []
                for i in range(16):
                    img = palette_images.get(f"palette_{i}")
                    if img and img.mode == "P":
                        flat_pal = img.getpalette()
                        if flat_pal:
                            palette = [(flat_pal[j], flat_pal[j + 1], flat_pal[j + 2]) for j in range(0, 48, 3)]
                            palettes.append(palette)

                if palettes:
                    self._multi_palette_view.set_single_image_all_palettes(base_img, palettes)  # type: ignore[attr-defined]
                    # Use correct field names expected by viewer
                    stats2: dict[str, int | dict[int, int]] = {"sprite_count": tile_count}
                    # Add palette_usage if OAM mapper available
                    if self.renderer.oam_mapper:
                        palette_usage = self.renderer.oam_mapper.get_active_palettes()
                        if palette_usage:
                            stats2["palette_usage"] = dict.fromkeys(palette_usage, 1)
                    self._multi_palette_view.set_oam_statistics(stats2)  # type: ignore[attr-defined]

    def _on_worker_finished(self) -> None:
        """Handle worker completion."""
        if self._view:
            self._view.set_extract_enabled(True)
        self._worker = None
        self._multi_worker = None
