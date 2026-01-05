#!/usr/bin/env python3
"""
Palette data model for the sprite editor.
Handles SNES 16-color palettes with JSON and CGRAM format support.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.palette_utils import read_cgram_palette


@dataclass
class PaletteModel:
    """
    Model for managing palette data.
    Handles multiple palettes and format conversions.
    """

    colors: list[tuple[int, int, int]] = field(default_factory=lambda: [(i * 17, i * 17, i * 17) for i in range(16)])
    name: str = "Default"
    index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)  # type: ignore[reportExplicitAny]

    def from_rgb_list(self, rgb_list: list[tuple[int, int, int]]) -> None:
        """Load palette from RGB tuples."""
        if len(rgb_list) < 16:
            # Pad with black if needed
            rgb_list = rgb_list + [(0, 0, 0)] * (16 - len(rgb_list))
        elif len(rgb_list) > 16:
            # Truncate if too many
            rgb_list = rgb_list[:16]

        self.colors = rgb_list

    def from_flat_list(self, flat_list: list[int]) -> None:
        """Load palette from flat list [r,g,b,r,g,b,...]"""
        if len(flat_list) < 48:  # 16 colors * 3 components
            flat_list = flat_list + [0] * (48 - len(flat_list))

        self.colors = []
        for i in range(0, 48, 3):
            self.colors.append((flat_list[i], flat_list[i + 1], flat_list[i + 2]))

    def to_flat_list(self) -> list[int]:
        """Convert to flat list for PIL."""
        flat: list[int] = []
        for r, g, b in self.colors:
            flat.extend([r, g, b])
        # PIL expects 256 colors for mode P
        flat.extend([0] * (768 - len(flat)))  # Pad to 256 colors
        return flat

    def from_json_file(self, file_path: str) -> bool:
        """
        Load palette from JSON file.
        Returns True on success.
        """
        try:
            with Path(file_path).open() as f:
                data = json.load(f)

            if "palette" in data and "colors" in data["palette"]:
                colors_data = data["palette"]["colors"]
                self.colors = [tuple(c) for c in colors_data]
                self.name = data["palette"].get("name", Path(file_path).stem)
                self.metadata = data
                return True

        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return False

        return False

    def to_json_file(self, file_path: str) -> bool:
        """Save palette to JSON file."""
        try:
            data = {
                "palette": {
                    "name": self.name,
                    "colors": [list(c) for c in self.colors],
                    "format": "RGB888",
                }
            }
            # Add any additional metadata
            if self.metadata:
                data.update(self.metadata)

            with Path(file_path).open("w") as f:
                json.dump(data, f, indent=2)

            return True

        except OSError:
            return False

    def from_cgram_file(self, cgram_file: str, palette_num: int) -> bool:
        """
        Load palette from CGRAM dump file.
        Returns True on success.
        """
        palette_data = read_cgram_palette(cgram_file, palette_num)
        if palette_data:
            self.from_flat_list(palette_data[:48])  # First 16 colors
            self.name = f"Palette {palette_num}"
            self.index = palette_num
            return True
        return False


@dataclass
class PaletteCollection:
    """
    Manages multiple palettes (for CGRAM with 16 palettes).
    """

    palettes: dict[int, PaletteModel] = field(default_factory=dict)
    current_index: int = 8  # Default to Kirby's palette

    def add_palette(self, index: int, palette: PaletteModel) -> None:
        """Add or replace a palette at the given index."""
        palette.index = index
        self.palettes[index] = palette

    def get_palette(self, index: int) -> PaletteModel | None:
        """Get palette at index."""
        return self.palettes.get(index)

    def get_current_palette(self) -> PaletteModel | None:
        """Get the currently selected palette."""
        return self.palettes.get(self.current_index)

    def set_current_index(self, index: int) -> bool:
        """Set current palette index. Returns True if palette exists."""
        if index in self.palettes:
            self.current_index = index
            return True
        return False

    def get_palette_count(self) -> int:
        """Get number of loaded palettes."""
        return len(self.palettes)

    def load_all_from_cgram(self, cgram_file: str) -> int:
        """
        Load all 16 palettes from CGRAM file.
        Returns number of palettes loaded.
        """
        count = 0
        for i in range(16):
            palette = PaletteModel()
            if palette.from_cgram_file(cgram_file, i):
                self.add_palette(i, palette)
                count += 1
        return count

    def clear(self) -> None:
        """Clear all palettes."""
        self.palettes.clear()
        self.current_index = 8
