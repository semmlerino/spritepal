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

from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.extractor import SpriteExtractor
    from core.palette_manager import PaletteManager

from core.exceptions import ValidationError
from core.extractor import SpriteExtractor
from core.palette_manager import PaletteManager
from core.services.extraction_results import ExtractionResult
from utils.file_validator import FileValidator
from utils.logging_config import get_logger

logger = get_logger(__name__)


class VRAMService:
    """
    Service for VRAM-based sprite extraction operations.

    Provides:
    - VRAM sprite extraction with palette support
    - VRAM preview generation
    """

    def __init__(
        self,
        sprite_extractor: SpriteExtractor | None = None,
        palette_manager: PaletteManager | None = None,
    ) -> None:
        """
        Initialize the VRAM service.

        Args:
            sprite_extractor: Optional SpriteExtractor instance (created if not provided)
            palette_manager: Optional PaletteManager instance (created if not provided)
        """
        self._logger = get_logger(f"services.{self.__class__.__name__}")
        self._sprite_extractor = sprite_extractor or SpriteExtractor()
        self._palette_manager = palette_manager or PaletteManager()
        self._logger.info("VRAMService initialized")

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
        progress_callback: Callable[[str], None] | None = None,
    ) -> ExtractionResult:
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
            progress_callback: Optional callback for progress messages

        Returns:
            ExtractionResult with files, preview, palettes, and any warnings

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

        def _progress(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        extracted_files: list[str] = []
        warning: str | None = None
        palettes: dict[int, list[list[int]]] = {}
        active_palette_indices: list[int] = []

        # Extract sprites
        _progress("Extracting sprites from VRAM...")

        output_file = f"{output_base}.png"
        img, num_tiles = self._sprite_extractor.extract_sprites_grayscale(vram_path, output_file, offset=vram_offset)
        extracted_files.append(output_file)

        # Generate preview
        _progress("Creating preview...")

        # Extract palettes if requested - catch errors for partial success
        if not grayscale_mode and cgram_path:
            try:
                from core.services.palette_utils import extract_palettes_and_create_files

                palette_result = extract_palettes_and_create_files(
                    palette_manager=self._palette_manager,
                    cgram_path=cgram_path,
                    output_base=output_base,
                    png_file=output_file,
                    oam_path=oam_path,
                    source_path=vram_path,
                    source_offset=vram_offset,
                    num_tiles=num_tiles,
                    create_grayscale=create_grayscale,
                    create_metadata=create_metadata,
                    progress_callback=progress_callback,
                )
                extracted_files.extend(palette_result.files)
                palettes = palette_result.palettes
                active_palette_indices = palette_result.active_palette_indices
            except Exception as e:
                # Log and track palette failure but don't fail sprite extraction
                warning = f"Sprites extracted but palette extraction failed: {e}"
                self._logger.warning(f"Palette extraction failed: {e}")

        # Log completion
        if warning:
            _progress("Extraction complete (palettes failed)")
        else:
            _progress("Extraction complete!")

        return ExtractionResult(
            files=extracted_files,
            preview_image=img,
            tile_count=num_tiles,
            palettes=palettes,
            active_palette_indices=active_palette_indices,
            warning=warning,
        )

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
