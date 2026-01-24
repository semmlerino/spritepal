"""
Palette management for SpritePal
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.palette_utils import bgr555_to_rgb
from core.services.extraction_results import PaletteExtractionResult
from utils.constants import (
    BYTES_PER_TILE,
    CGRAM_EXPECTED_SIZE,
    COLORS_PER_PALETTE,
    OAM_Y_VISIBLE_THRESHOLD,
    PALETTE_ATTR_MASK,
    PALETTE_ENTRIES,
    PALETTE_INFO,
    SPRITE_PALETTE_END,
    SPRITE_PALETTE_START,
)
from utils.file_validator import FileValidator, atomic_write


class PaletteManager:
    """Manages palette extraction and file generation"""

    def __init__(self) -> None:
        self.cgram_data: bytes | None = None
        self.palettes: dict[int, list[list[int]]] = {}

    def load_cgram(self, cgram_path: str) -> None:
        """Load CGRAM dump file with validation"""
        # Validate file before loading
        result = FileValidator.validate_cgram_file(cgram_path)
        if not result.is_valid:
            raise ValueError(f"Invalid CGRAM file: {result.error_message}")

        with Path(cgram_path).open("rb") as f:
            self.cgram_data = f.read()

        # Extract all palettes
        self._extract_palettes()

    def _extract_palettes(self) -> None:
        """Extract all palettes from CGRAM data"""
        self.palettes.clear()

        if self.cgram_data is None:
            return

        for pal_idx in range(16):
            colors: list[list[int]] = []
            for color_idx in range(COLORS_PER_PALETTE):
                offset = (pal_idx * COLORS_PER_PALETTE + color_idx) * 2

                if offset + 1 < len(self.cgram_data):
                    color_low = self.cgram_data[offset]
                    color_high = self.cgram_data[offset + 1]
                    snes_color = (color_high << 8) | color_low

                    # Convert BGR555 to RGB888 using shared utility
                    r, g, b = bgr555_to_rgb(snes_color)
                    colors.append([r, g, b])
                else:
                    colors.append([0, 0, 0])

            self.palettes[pal_idx] = colors

    def refresh_palettes(self) -> None:
        """Re-extract palettes from current CGRAM data.

        Public API for triggering palette re-extraction after CGRAM updates.
        """
        self._extract_palettes()

    def get_palette(self, palette_index: int) -> list[list[int]]:
        """Get a specific palette"""
        return self.palettes.get(palette_index, [[0, 0, 0]] * COLORS_PER_PALETTE)

    def get_flat_palette(self, palette_index: int) -> list[int]:
        """Get a specific palette as a flat list of 768 RGB values (for PIL)."""
        colors = self.get_palette(palette_index)
        flat = []
        for r, g, b in colors:
            flat.extend([r, g, b])

        # Pad to 256 colors (768 values)
        while len(flat) < 768:
            flat.extend([0, 0, 0])

        return flat

    @staticmethod
    def get_grayscale_palette() -> list[int]:
        """
        Get default grayscale palette for preview.

        Returns:
            List of 768 RGB values forming a grayscale palette
        """
        palette = []
        for i in range(PALETTE_ENTRIES):
            # For 4bpp sprites, map 0-15 to 0-255
            gray = (i * 255) // 15 if i < COLORS_PER_PALETTE else 0
            palette.extend([gray, gray, gray])
        return palette

    @staticmethod
    def get_default_snes_palette() -> list[tuple[int, int, int]]:
        """
        Get a default SNES-style color palette for initial sprite display.

        Returns a visually distinct 16-color palette similar to what SNES games
        commonly use. Color 0 is typically transparent (black in display).

        Returns:
            List of 16 (R, G, B) tuples in 0-255 range.
        """
        return [
            (0, 0, 0),  # 0: Transparent (black)
            (255, 255, 255),  # 1: White
            (248, 216, 176),  # 2: Skin tone light
            (232, 168, 120),  # 3: Skin tone medium
            (200, 120, 88),  # 4: Skin tone dark
            (255, 200, 120),  # 5: Yellow/blonde
            (248, 88, 88),  # 6: Red
            (88, 144, 248),  # 7: Blue
            (120, 216, 88),  # 8: Green
            (248, 168, 200),  # 9: Pink
            (168, 88, 200),  # 10: Purple
            (88, 88, 88),  # 11: Dark gray
            (168, 168, 168),  # 12: Light gray
            (200, 160, 88),  # 13: Brown/orange
            (48, 48, 48),  # 14: Near black
            (255, 216, 88),  # 15: Gold/highlight
        ]

    def get_sprite_palettes(self) -> dict[int, list[list[int]]]:
        """Get only the sprite palettes (8-15)"""
        return {
            idx: self.palettes[idx] for idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END) if idx in self.palettes
        }

    def create_palette_json(
        self,
        palette_index: int,
        output_path: str,
        companion_image: str | None = None,
    ) -> str:
        """Create a .pal.json file for a specific palette"""
        colors = self.get_palette(palette_index)
        palette_name, description = PALETTE_INFO.get(palette_index, (f"Palette {palette_index}", "Sprite palette"))

        palette_data = {
            "format_version": "1.0",
            "format_description": "Indexed Pixel Editor Palette File",
            "palette": {
                "name": palette_name,
                "colors": colors,
                "color_count": len(colors),
                "format": "RGB888",
            },
            "usage_hints": {
                "transparent_index": 0,
                "typical_use": "sprite",
                "extraction_mode": "grayscale_companion",
            },
            "editor_compatibility": {
                "indexed_pixel_editor": True,
                "supports_grayscale_mode": True,
                "auto_loadable": True,
            },
        }

        # Add source info if available
        if companion_image:
            palette_data["source"] = {
                "palette_index": palette_index,
                "extraction_tool": "SpritePal",
                "companion_image": companion_image,
                "description": description,
            }

        # Save file atomically with fsync to prevent data loss on crash
        json_bytes = json.dumps(palette_data, indent=2).encode("utf-8")
        atomic_write(output_path, json_bytes)

        return output_path

    def create_metadata_json(
        self,
        output_base: str,
        palette_files: dict[int, str],
        extraction_params: dict[str, Any] | None = None,  # pyright: ignore[reportExplicitAny] - extraction params can contain various types
    ) -> str:
        """Create metadata.json for palette switching and reinsertion"""
        metadata: dict[str, Any] = {  # pyright: ignore[reportExplicitAny] - JSON metadata can contain various types
            "format_version": "1.0",
            "description": "Sprite palettes extracted by SpritePal",
            "palettes": {},
            "default_palette": 8,
            "palette_info": {},
        }

        # Add extraction parameters if provided
        if extraction_params:
            # Check if this is ROM extraction or VRAM extraction
            source_type = extraction_params.get("source_type", "vram")

            if source_type == "rom":
                # ROM extraction metadata
                metadata["extraction"] = {
                    "source_type": "rom",
                    "rom_source": extraction_params.get("rom_source", ""),
                    "rom_offset": extraction_params.get("rom_offset", "0x0"),
                    "sprite_name": extraction_params.get("sprite_name", ""),
                    "compressed_size": extraction_params.get("compressed_size", 0),
                    "tile_count": extraction_params.get("tile_count", 0),
                    "extraction_size": extraction_params.get("extraction_size", 0),
                    "rom_title": extraction_params.get("rom_title", ""),
                    "rom_checksum": extraction_params.get("rom_checksum", ""),
                    "extraction_date": extraction_params.get("extraction_date", datetime.now(UTC).isoformat()),
                }
            else:
                # VRAM extraction metadata (existing format)
                metadata["extraction"] = {
                    "source_type": "vram",
                    "vram_source": extraction_params.get("vram_source", ""),
                    "vram_offset": f"0x{extraction_params.get('vram_offset', 0):04X}",
                    "tile_count": extraction_params.get("tile_count", 0),
                    "extraction_size": extraction_params.get("extraction_size", 0),
                    "extraction_date": extraction_params.get("extraction_date", datetime.now(UTC).isoformat()),
                }

        # Add palette references
        for pal_idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
            if pal_idx in palette_files:
                metadata["palettes"][str(pal_idx)] = Path(palette_files[pal_idx]).name

                # Add palette info
                _, description = PALETTE_INFO.get(pal_idx, (f"Palette {pal_idx}", "Sprite palette"))
                metadata["palette_info"][str(pal_idx)] = description

        # Save metadata file atomically with fsync to prevent data loss on crash
        metadata_path = f"{output_base}.metadata.json"
        json_bytes = json.dumps(metadata, indent=2).encode("utf-8")
        atomic_write(metadata_path, json_bytes)

        return metadata_path

    def analyze_oam_palettes(self, oam_path: str) -> list[int]:
        """Analyze OAM data to find active palettes"""
        active_palettes = set()

        try:
            # Validate file before loading
            result = FileValidator.validate_oam_file(oam_path)
            if not result.is_valid:
                self._raise_invalid_oam(result.error_message or "Unknown error")

            with Path(oam_path).open("rb") as f:
                oam_data = f.read()

            # Parse OAM entries
            for i in range(0, min(CGRAM_EXPECTED_SIZE, len(oam_data)), 4):
                if i + 3 < len(oam_data):
                    y_pos = oam_data[i + 1]
                    attrs = oam_data[i + 3]

                    # Check if sprite is on-screen
                    if y_pos < OAM_Y_VISIBLE_THRESHOLD:  # Y < 224
                        # Extract palette (lower 3 bits)
                        oam_palette = attrs & PALETTE_ATTR_MASK
                        cgram_palette = oam_palette + 8
                        active_palettes.add(cgram_palette)

        except Exception:
            # If OAM analysis fails, just return all sprite palettes
            return list(range(SPRITE_PALETTE_START, SPRITE_PALETTE_END))

        return sorted(active_palettes)

    def _raise_invalid_oam(self, error_msg: str) -> None:
        """Helper method to raise ValueError for invalid OAM (for TRY301 compliance)"""
        raise ValueError(f"Invalid OAM file: {error_msg}")

    def extract_and_create_palette_files(
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
        progress_callback: Callable[[str], None] | None = None,
    ) -> PaletteExtractionResult:
        """Extract palettes and create palette/metadata files.

        Consolidates palette extraction logic used by both ROM and VRAM workflows.

        Args:
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
        self.load_cgram(cgram_path)

        # Get sprite palettes
        sprite_palettes = self.get_sprite_palettes()

        # Create palette files
        if create_grayscale:
            _progress("Creating palette files...")

            # Create main palette file (default to palette 8)
            main_pal_file = f"{output_base}.pal.json"
            self.create_palette_json(8, main_pal_file, png_file)
            created_files.append(main_pal_file)

            # Create individual palette files
            palette_files: dict[int, str] = {}
            for pal_idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
                pal_file = f"{output_base}_pal{pal_idx}.pal.json"
                self.create_palette_json(pal_idx, pal_file, png_file)
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

                metadata_file = self.create_metadata_json(output_base, palette_files, extraction_params)
                created_files.append(metadata_file)

        # Analyze OAM if available
        active_palettes: list[int] = []
        if oam_path:
            _progress("Analyzing sprite palette usage...")
            active_palettes = self.analyze_oam_palettes(oam_path)

        return PaletteExtractionResult(
            files=created_files,
            palettes=sprite_palettes,
            active_palette_indices=active_palettes,
        )
