"""
Shared palette extraction utilities.

This module provides shared palette extraction logic used by both
ROMService and VRAMService to avoid code duplication.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.services.extraction_results import PaletteExtractionResult
from utils.constants import (
    BYTES_PER_TILE,
    SPRITE_PALETTE_END,
    SPRITE_PALETTE_START,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.palette_manager import PaletteManager


def extract_palettes_and_create_files(
    palette_manager: PaletteManager,
    cgram_path: str,
    output_base: str,
    png_file: str,
    oam_path: str | None,
    source_path: str,
    source_offset: int | None,
    num_tiles: int,
    create_grayscale: bool,
    create_metadata: bool,
    progress_callback: Callable[[str], None] | None = None,
) -> PaletteExtractionResult:
    """
    Extract palettes and create palette/metadata files.

    This function is shared between ROMService and VRAMService to avoid
    code duplication.

    Args:
        palette_manager: The palette manager instance to use
        cgram_path: Path to CGRAM data file
        output_base: Base path for output files (without extension)
        png_file: Path to the PNG file (for metadata reference)
        oam_path: Optional path to OAM data file
        source_path: Original source file path (for metadata)
        source_offset: Offset in source file (for metadata)
        num_tiles: Number of tiles extracted (for metadata)
        create_grayscale: Whether to create grayscale palette files
        create_metadata: Whether to create metadata JSON file
        progress_callback: Optional callback for progress messages

    Returns:
        PaletteExtractionResult with files, palettes, and active indices
    """
    created_files: list[str] = []

    def _progress(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    _progress("Extracting palettes...")
    palette_manager.load_cgram(cgram_path)

    # Get sprite palettes
    sprite_palettes = palette_manager.get_sprite_palettes()

    # Create palette files
    if create_grayscale:
        _progress("Creating palette files...")

        # Create main palette file (default to palette 8)
        main_pal_file = f"{output_base}.pal.json"
        palette_manager.create_palette_json(8, main_pal_file, png_file)
        created_files.append(main_pal_file)

        # Create individual palette files
        palette_files: dict[int, str] = {}
        for pal_idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
            pal_file = f"{output_base}_pal{pal_idx}.pal.json"
            palette_manager.create_palette_json(pal_idx, pal_file, png_file)
            created_files.append(pal_file)
            palette_files[pal_idx] = pal_file

        # Create metadata file
        if create_metadata:
            _progress("Creating metadata file...")

            # Prepare extraction parameters
            extraction_params = {
                "source": Path(source_path).name,
                "offset": source_offset if source_offset is not None else 0xC000,
                "tile_count": num_tiles,
                "extraction_size": num_tiles * BYTES_PER_TILE,
            }

            metadata_file = palette_manager.create_metadata_json(output_base, palette_files, extraction_params)
            created_files.append(metadata_file)

    # Analyze OAM if available
    active_palettes: list[int] = []
    if oam_path:
        _progress("Analyzing sprite palette usage...")
        active_palettes = palette_manager.analyze_oam_palettes(oam_path)

    return PaletteExtractionResult(
        files=created_files,
        palettes=sprite_palettes,
        active_palette_indices=active_palettes,
    )
