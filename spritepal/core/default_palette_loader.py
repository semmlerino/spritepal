"""
Default palette loader for SpritePal
Provides default palettes for sprites when CGRAM data is not available
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from utils.logging_config import get_logger

logger = get_logger(__name__)

class DefaultPaletteLoader:
    """Loads and manages default sprite palettes"""

    DEFAULT_PALETTE_PATH: str = str(
        Path(__file__).parent.parent / "config" / "default_palettes.json"
    )

    # Mapping of ROM titles (or substrings) to palette category names.
    # Keys are checked as substrings of the normalized ROM title (uppercase, stripped).
    # More specific patterns should be listed first since matching stops at first hit.
    ROM_TITLE_PALETTE_MAP: ClassVar[dict[str, str]] = {
        "KIRBY SUPER STAR": "kirby_normal",
        "KIRBY SUPER DELUXE": "kirby_normal",
        "KIRBY'S FUN PAK": "kirby_normal",
        "HOSHI NO KIRBY": "kirby_normal",  # Japanese title
        "KIRBY": "kirby_normal",  # Generic fallback for any Kirby game
    }

    def __init__(self, palette_path: str | None = None) -> None:
        """
        Initialize default palette loader.

        Args:
            palette_path: Path to default palettes file (uses default if None)
        """
        self.palette_path: str = palette_path or self.DEFAULT_PALETTE_PATH
        # JSON data is inherently untyped; structure validated at runtime
        self.palette_data: dict[str, Any] = {}  # pyright: ignore[reportExplicitAny]
        self.load_palettes()

    def load_palettes(self) -> None:
        """Load default palettes from JSON file"""
        palette_path_obj = Path(self.palette_path)
        if not palette_path_obj.exists():
            logger.warning(f"Default palettes not found: {self.palette_path}")
            return

        try:
            with palette_path_obj.open() as f:
                self.palette_data = json.load(f)
            logger.info(f"Loaded default palettes: {self.palette_path}")
        except Exception:
            logger.exception("Failed to load default palettes")

    def get_sprite_palettes(self, sprite_name: str) -> list[dict[str, Any]]:  # pyright: ignore[reportExplicitAny]
        """
        Get default palettes for a specific sprite.

        Args:
            sprite_name: Name of the sprite (e.g., "kirby_normal")

        Returns:
            List of palette dictionaries with index and colors
        """
        if "palettes" not in self.palette_data:
            return []

        # Try exact match first
        if sprite_name in self.palette_data["palettes"]:
            sprite_data = self.palette_data["palettes"][sprite_name]
            return sprite_data.get("palettes", [])

        # Try partial match (e.g., "kirby" in "kirby_normal")
        for palette_key, palette_data in self.palette_data["palettes"].items():
            if sprite_name.startswith(palette_key.split("_")[0]):
                return palette_data.get("palettes", [])

        logger.warning(f"No default palettes found for sprite: {sprite_name}")
        return []

    def create_palette_files(self, sprite_name: str, output_base: str) -> list[str]:
        """
        Create .pal.json files for a sprite using default palettes.

        Args:
            sprite_name: Name of the sprite
            output_base: Base path for output files (without extension)

        Returns:
            List of created palette file paths
        """
        palettes = self.get_sprite_palettes(sprite_name)
        created_files = []

        for palette_data in palettes:
            palette_index = palette_data.get("index", 8)
            palette_name = palette_data.get("name", f"Palette {palette_index}")
            colors = palette_data.get("colors", [])

            # Create palette file
            palette_path = f"{output_base}_pal{palette_index}.pal.json"
            palette_json = {"name": palette_name, "colors": colors}

            try:
                with Path(palette_path).open("w") as f:
                    json.dump(palette_json, f, indent=2)
                created_files.append(palette_path)
                logger.info(
                    f"Created default palette: {palette_name} -> {Path(palette_path).name}"
                )
            except Exception:
                logger.exception("Failed to create palette file")

        return created_files

    def get_all_kirby_palettes(self) -> dict[int, list[tuple[int, int, int]]]:
        """
        Get all Kirby palettes as a dictionary for quick access.

        Returns:
            Dictionary mapping palette index to color list
        """
        all_palettes = {}

        # Collect all Kirby-related palettes
        for sprite_name, sprite_data in self.palette_data.get("palettes", {}).items():
            if "kirby" in sprite_name.lower():
                for palette in sprite_data.get("palettes", []):
                    index = palette.get("index", 8)
                    colors = palette.get("colors", [])
                    if colors:
                        all_palettes[index] = colors

        return all_palettes

    def has_default_palettes(self, sprite_name: str) -> bool:
        """
        Check if default palettes exist for a sprite.

        Args:
            sprite_name: Name of the sprite

        Returns:
            True if default palettes exist
        """
        return len(self.get_sprite_palettes(sprite_name)) > 0

    def get_palettes_by_rom_title(
        self, rom_title: str
    ) -> list[dict[str, Any]]:  # pyright: ignore[reportExplicitAny]
        """
        Get default palettes based on ROM title.

        Falls back to this method when sprite name lookup fails, allowing
        generic sprite names (e.g., "High_Quality_Sprite_1") to still get
        appropriate palettes based on the game being played.

        Args:
            rom_title: ROM title from header (e.g., "KIRBY SUPER STAR")

        Returns:
            List of palette dictionaries with index and colors
        """
        if "palettes" not in self.palette_data:
            return []

        # Normalize ROM title for matching
        normalized_title = rom_title.strip().upper()

        # Check against known ROM title patterns
        for title_pattern, palette_key in self.ROM_TITLE_PALETTE_MAP.items():
            if title_pattern in normalized_title:
                palettes = self.get_sprite_palettes(palette_key)
                if palettes:
                    logger.info(
                        f"Found palettes for ROM title '{rom_title}' "
                        f"via pattern '{title_pattern}' -> '{palette_key}'"
                    )
                    return palettes

        logger.debug(f"No palette mapping found for ROM title: {rom_title}")
        return []

    def has_palettes_for_rom_title(self, rom_title: str) -> bool:
        """
        Check if palettes exist for a ROM title.

        Args:
            rom_title: ROM title from header

        Returns:
            True if palettes exist for this ROM title
        """
        return len(self.get_palettes_by_rom_title(rom_title)) > 0

    def get_palette_key_for_rom_title(self, rom_title: str) -> str | None:
        """
        Get the palette key that matches a ROM title.

        Args:
            rom_title: ROM title from header

        Returns:
            Palette key (e.g., "kirby_normal") or None if no match
        """
        normalized_title = rom_title.strip().upper()
        for title_pattern, palette_key in self.ROM_TITLE_PALETTE_MAP.items():
            if title_pattern in normalized_title:
                return palette_key
        return None
