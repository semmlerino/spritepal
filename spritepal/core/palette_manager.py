"""
Palette management for SpritePal
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.file_validator import atomic_write
from utils.constants import (
    CGRAM_EXPECTED_SIZE,
    COLOR_MASK_BLUE,
    COLOR_MASK_GREEN,
    COLOR_MASK_RED,
    COLOR_SHIFT_BLUE,
    COLOR_SHIFT_GREEN,
    COLORS_PER_PALETTE,
    OAM_Y_VISIBLE_THRESHOLD,
    PALETTE_ATTR_MASK,
    PALETTE_INFO,
    SPRITE_PALETTE_END,
    SPRITE_PALETTE_START,
)
from utils.validation import validate_cgram_file, validate_oam_file


class PaletteManager:
    """Manages palette extraction and file generation"""

    def __init__(self) -> None:
        self.cgram_data: bytes | None = None
        self.palettes: dict[int, list[list[int]]] = {}

    def load_cgram(self, cgram_path: str) -> None:
        """Load CGRAM dump file with validation"""
        # Validate file before loading
        is_valid, error_msg = validate_cgram_file(cgram_path)
        if not is_valid:
            raise ValueError(f"Invalid CGRAM file: {error_msg}")

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

                    # Convert BGR555 to RGB888 (proper 5-bit to 8-bit conversion)
                    # Use bit shifting for accurate conversion: (value << 3) | (value >> 2)
                    b = (snes_color & COLOR_MASK_BLUE) >> COLOR_SHIFT_BLUE
                    g = (snes_color & COLOR_MASK_GREEN) >> COLOR_SHIFT_GREEN
                    r = snes_color & COLOR_MASK_RED

                    # Convert 5-bit to 8-bit values (0-31 to 0-255)
                    b = (b << 3) | (b >> 2)
                    g = (g << 3) | (g >> 2)
                    r = (r << 3) | (r >> 2)

                    colors.append([r, g, b])
                else:
                    colors.append([0, 0, 0])

            self.palettes[pal_idx] = colors

    def get_palette(self, palette_index: int) -> list[list[int]]:
        """Get a specific palette"""
        return self.palettes.get(palette_index, [[0, 0, 0]] * COLORS_PER_PALETTE)

    def get_sprite_palettes(self) -> dict[int, list[list[int]]]:
        """Get only the sprite palettes (8-15)"""
        return {
            idx: self.palettes[idx]
            for idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END)
            if idx in self.palettes
        }

    def create_palette_json(
        self,
        palette_index: int,
        output_path: str,
        companion_image: str | None = None,
    ) -> str:
        """Create a .pal.json file for a specific palette"""
        colors = self.get_palette(palette_index)
        palette_name, description = PALETTE_INFO.get(
            palette_index, (f"Palette {palette_index}", "Sprite palette")
        )

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
        extraction_params: dict[str, Any] | None = None,
    ) -> str:
        """Create metadata.json for palette switching and reinsertion"""
        metadata: dict[str, Any] = {
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
                    "extraction_date": extraction_params.get(
                        "extraction_date", datetime.now(UTC).isoformat()
                    ),
                }
            else:
                # VRAM extraction metadata (existing format)
                metadata["extraction"] = {
                    "source_type": "vram",
                    "vram_source": extraction_params.get("vram_source", ""),
                    "vram_offset": f"0x{extraction_params.get('vram_offset', 0):04X}",
                    "tile_count": extraction_params.get("tile_count", 0),
                    "extraction_size": extraction_params.get("extraction_size", 0),
                    "extraction_date": extraction_params.get(
                        "extraction_date", datetime.now(UTC).isoformat()
                    ),
                }

        # Add palette references
        for pal_idx in range(SPRITE_PALETTE_START, SPRITE_PALETTE_END):
            if pal_idx in palette_files:
                metadata["palettes"][str(pal_idx)] = Path(palette_files[pal_idx]).name

                # Add palette info
                _, description = PALETTE_INFO.get(
                    pal_idx, (f"Palette {pal_idx}", "Sprite palette")
                )
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
            is_valid, error_msg = validate_oam_file(oam_path)
            if not is_valid:
                self._raise_invalid_oam(error_msg)

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
