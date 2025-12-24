"""
VRAM Service for SpritePal

Handles all VRAM-based sprite extraction operations:
- VRAM sprite extraction
- VRAM preview generation
- Palette extraction from CGRAM/OAM

This service was extracted from ExtractionManager to provide
better separation of concerns between ROM and VRAM operations.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QObject, Signal, SignalInstance

if TYPE_CHECKING:
    from collections.abc import Mapping

    from core.extractor import SpriteExtractor
    from core.palette_manager import PaletteManager

from core.exceptions import ValidationError
from core.extractor import SpriteExtractor
from core.palette_manager import PaletteManager
from utils.constants import (
    BYTES_PER_TILE,
    SPRITE_PALETTE_END,
    SPRITE_PALETTE_START,
)
from utils.file_validator import FileValidator
from utils.logging_config import get_logger

logger = get_logger(__name__)


class VRAMService(QObject):
    """
    Service for VRAM-based sprite extraction operations.

    Provides:
    - VRAM sprite extraction with palette support
    - VRAM preview generation
    """

    # Signals for VRAM operations
    extraction_progress = Signal(str)  # Progress message
    extraction_warning = Signal(str)  # Warning message (partial success)
    preview_generated = Signal(object, int)  # PIL Image, tile count
    palettes_extracted = Signal(object)  # Palette data - use object to avoid PySide6 copy warning
    active_palettes_found = Signal(list)  # Active palette indices
    files_created = Signal(list)  # List of created files
    error_occurred = Signal(str)  # Error message

    # Instance attribute for parent signals
    _parent_signals: Mapping[str, SignalInstance] | None

    def __init__(
        self,
        sprite_extractor: SpriteExtractor | None = None,
        palette_manager: PaletteManager | None = None,
        parent_signals: Mapping[str, SignalInstance] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """
        Initialize the VRAM service.

        Args:
            sprite_extractor: Optional SpriteExtractor instance (created if not provided)
            palette_manager: Optional PaletteManager instance (created if not provided)
            parent_signals: Optional mapping of signal names to parent signal instances.
                           When provided, signals are emitted to parent instead of own signals.
            parent: Qt parent object
        """
        super().__init__(parent)
        self._logger = get_logger(f"services.{self.__class__.__name__}")
        self._sprite_extractor = sprite_extractor or SpriteExtractor()
        self._palette_manager = palette_manager or PaletteManager()
        self._parent_signals = parent_signals
        self._logger.info("VRAMService initialized")

    def _emit(self, signal_name: str, *args: object) -> None:
        """Emit to parent signal if available, otherwise emit to own signal.

        Args:
            signal_name: Name of the signal to emit
            *args: Arguments to pass to the signal
        """
        if self._parent_signals and signal_name in self._parent_signals:
            self._parent_signals[signal_name].emit(*args)
        else:
            getattr(self, signal_name).emit(*args)

    def cleanup(self) -> None:
        """Cleanup service resources."""
        pass  # Currently no resources to cleanup

    def extract_from_vram(
        self,
        vram_path: str,
        output_base: str,
        cgram_path: str | None = None,
        oam_path: str | None = None,
        vram_offset: int | None = None,
        create_grayscale: bool = True,
        create_metadata: bool = True,
        grayscale_mode: bool = False,
    ) -> list[str]:
        """
        Extract sprites from VRAM dump.

        Args:
            vram_path: Path to VRAM dump file
            output_base: Base name for output files (without extension)
            cgram_path: Path to CGRAM dump for palette extraction
            oam_path: Path to OAM dump for palette analysis
            vram_offset: Offset in VRAM (default: 0xC000)
            create_grayscale: Create grayscale palette files
            create_metadata: Create metadata JSON file
            grayscale_mode: Skip palette extraction entirely

        Returns:
            List of created file paths

        Raises:
            ExtractionError: If extraction fails
            ValidationError: If parameters are invalid
        """
        # Validate parameters
        if not vram_path or not output_base:
            raise ValidationError("Missing required parameters: vram_path and output_base are required")

        FileValidator.validate_vram_file_or_raise(vram_path)

        if cgram_path:
            FileValidator.validate_cgram_file_or_raise(cgram_path)

        if oam_path:
            FileValidator.validate_oam_file_or_raise(oam_path)

        extracted_files: list[str] = []
        palette_extraction_failed = False
        palette_error_msg = ""

        # Extract sprites
        self._emit("extraction_progress", "Extracting sprites from VRAM...")

        output_file = f"{output_base}.png"
        img, num_tiles = self._sprite_extractor.extract_sprites_grayscale(
            vram_path, output_file, offset=vram_offset
        )
        extracted_files.append(output_file)

        # Generate preview
        self._emit("extraction_progress", "Creating preview...")
        self._emit("preview_generated", img, num_tiles)

        # Extract palettes if requested - catch errors for partial success
        if not grayscale_mode and cgram_path:
            try:
                extracted_files.extend(
                    self._extract_palettes(
                        cgram_path,
                        output_base,
                        output_file,
                        oam_path,
                        vram_path,
                        vram_offset,
                        num_tiles,
                        create_grayscale,
                        create_metadata,
                    )
                )
            except Exception as e:
                # Log and track palette failure but don't fail sprite extraction
                palette_extraction_failed = True
                palette_error_msg = str(e)
                self._logger.warning(f"Palette extraction failed: {e}")

        # Emit appropriate completion message
        if palette_extraction_failed:
            self._emit(
                "extraction_warning",
                f"Sprites extracted but palette extraction failed: {palette_error_msg}",
            )
            self._emit("extraction_progress", "Extraction complete (palettes failed)")
        else:
            self._emit("extraction_progress", "Extraction complete!")

        self._emit("files_created", extracted_files)
        return extracted_files

    def generate_preview(self, vram_path: str, offset: int) -> tuple[Image.Image, int]:
        """
        Generate a preview image from VRAM at the specified offset.

        Args:
            vram_path: Path to VRAM dump file
            offset: Offset in VRAM to start extracting from

        Returns:
            Tuple of (PIL image, tile count)

        Raises:
            ExtractionError: If preview generation fails
        """
        # Load VRAM
        self._sprite_extractor.load_vram(vram_path)

        # Extract tiles with new offset
        tiles, num_tiles = self._sprite_extractor.extract_tiles(offset=offset)

        # Create grayscale image
        img = self._sprite_extractor.create_grayscale_image(tiles)
        return img, num_tiles

    # Private helper methods

    def _extract_palettes(
        self,
        cgram_path: str,
        output_base: str,
        png_file: str,
        oam_path: str | None,
        source_path: str,
        source_offset: int | None,
        num_tiles: int,
        create_grayscale: bool,
        create_metadata: bool,
    ) -> list[str]:
        """
        Extract palettes and create palette/metadata files.

        Returns:
            List of created file paths
        """
        created_files: list[str] = []

        self._emit("extraction_progress", "Extracting palettes...")
        self._palette_manager.load_cgram(cgram_path)

        # Get sprite palettes
        sprite_palettes = self._palette_manager.get_sprite_palettes()
        self._emit("palettes_extracted", sprite_palettes)

        # Create palette files
        if create_grayscale:
            self._emit("extraction_progress", "Creating palette files...")

            # Create main palette file (default to palette 8)
            main_pal_file = f"{output_base}.pal.json"
            self._palette_manager.create_palette_json(8, main_pal_file, png_file)
            created_files.append(main_pal_file)

            # Create individual palette files
            palette_files: dict[int, str] = {}
            for pal_idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
                pal_file = f"{output_base}_pal{pal_idx}.pal.json"
                self._palette_manager.create_palette_json(pal_idx, pal_file, png_file)
                created_files.append(pal_file)
                palette_files[pal_idx] = pal_file

            # Create metadata file
            if create_metadata:
                self._emit("extraction_progress", "Creating metadata file...")

                # Prepare extraction parameters
                extraction_params = {
                    "source": Path(source_path).name,
                    "offset": source_offset if source_offset is not None else 0xC000,
                    "tile_count": num_tiles,
                    "extraction_size": num_tiles * BYTES_PER_TILE,
                }

                metadata_file = self._palette_manager.create_metadata_json(
                    output_base, palette_files, extraction_params
                )
                created_files.append(metadata_file)

        # Analyze OAM if available
        if oam_path:
            self._emit("extraction_progress", "Analyzing sprite palette usage...")
            active_palettes = self._palette_manager.analyze_oam_palettes(oam_path)
            self._emit("active_palettes_found", active_palettes)

        return created_files
