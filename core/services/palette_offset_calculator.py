"""Palette ROM offset calculation service.

Determines where palette data should be written in a ROM based on game
configuration and character hint matching.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import GameFrame
    from core.rom_extractor import ROMExtractor
    from core.sprite_config_loader import SpriteConfigLoader

logger = get_logger(__name__)


def parse_offset(value: str | int) -> int:
    """Parse an offset value from string or int format.

    Args:
        value: Offset as hex string (e.g., "0x1234") or integer.

    Returns:
        Integer offset value.
    """
    if isinstance(value, str):
        return int(value, 16) if value.startswith("0x") else int(value)
    return value


class PaletteOffsetCalculator:
    """Calculates palette ROM offsets from game configuration.

    Uses character hint matching to select character-specific offsets,
    falling back to generic palette calculation based on palette index.
    """

    def __init__(
        self,
        rom_extractor: ROMExtractor,
        config_loader: SpriteConfigLoader,
    ) -> None:
        """Initialize the calculator.

        Args:
            rom_extractor: Extractor for reading ROM headers.
            config_loader: Loader for game sprite configurations.
        """
        self._rom_extractor = rom_extractor
        self._config_loader = config_loader

    def calculate(self, rom_path: Path, game_frame: GameFrame) -> int | None:
        """Calculate palette ROM offset for a game frame.

        First checks for character-specific palette offsets (e.g., King Dedede),
        then falls back to the generic palette calculation.

        Args:
            rom_path: Path to the ROM file.
            game_frame: Game frame to calculate offset for.

        Returns:
            ROM offset where the palette should be written, or None if not available.
        """
        try:
            # Read ROM header to get title/checksum
            header = self._rom_extractor.read_rom_header(str(rom_path))

            # Find game config
            game_name, game_config = self._config_loader.find_game_config(header.title, header.checksum)
            if not game_config:
                logger.debug(
                    "No game config found for %s (checksum 0x%04X)",
                    header.title,
                    header.checksum,
                )
                return None

            palettes = game_config.get("palettes", {})
            if not isinstance(palettes, dict):
                return None

            # Try character-specific offset first
            character_offset = self._find_character_offset(palettes, game_frame)
            if character_offset is not None:
                return character_offset

            # Fall back to generic palette calculation
            return self._calculate_generic_offset(palettes, game_frame, game_name)

        except Exception as e:
            logger.warning("Failed to calculate palette offset: %s", e)
            return None

    def _find_character_offset(
        self,
        palettes: dict[str, object],
        game_frame: GameFrame,
    ) -> int | None:
        """Find character-specific palette offset via hint matching.

        Args:
            palettes: Palette configuration from game config.
            game_frame: Game frame to match against hints.

        Returns:
            Character-specific offset if found, None otherwise.
        """
        character_offsets = palettes.get("character_offsets", {})
        if not isinstance(character_offsets, dict):
            return None

        # Try hint-based matching first
        for char_name, char_config in character_offsets.items():
            if not isinstance(char_config, dict):
                continue

            rom_offset_hints = char_config.get("rom_offset_hints", [])
            if not isinstance(rom_offset_hints, list) or not rom_offset_hints:
                continue

            # Convert hints to integers for comparison
            hint_ints: set[int] = set()
            for hint in rom_offset_hints:
                if isinstance(hint, (str, int)):
                    hint_ints.add(parse_offset(hint))

            # Check if any of the game frame's ROM offsets match the hints
            if game_frame.rom_offsets and hint_ints.intersection(game_frame.rom_offsets):
                char_offset_str = char_config.get("offset")
                if char_offset_str and isinstance(char_offset_str, str):
                    char_offset = parse_offset(char_offset_str)
                    logger.info(
                        "Using character-specific palette offset for %s (hint match): 0x%X",
                        char_name,
                        char_offset,
                    )
                    return char_offset

        # No hint match - if there's only one character config, use it as default
        # This handles the common case of single-character replacement projects
        if len(character_offsets) == 1:
            char_name, char_config = next(iter(character_offsets.items()))
            if isinstance(char_config, dict):
                char_offset_str = char_config.get("offset")
                if char_offset_str and isinstance(char_offset_str, str):
                    char_offset = parse_offset(char_offset_str)
                    logger.info(
                        "Using character-specific palette offset for %s (single character default): 0x%X",
                        char_name,
                        char_offset,
                    )
                    return char_offset

        return None

    def _calculate_generic_offset(
        self,
        palettes: dict[str, object],
        game_frame: GameFrame,
        game_name: str | None,
    ) -> int | None:
        """Calculate generic palette offset based on palette index.

        Args:
            palettes: Palette configuration from game config.
            game_frame: Game frame with palette_index.
            game_name: Game name for logging.

        Returns:
            Calculated offset, or None if not available.
        """
        base_offset_str = palettes.get("offset")
        if not base_offset_str or not isinstance(base_offset_str, str):
            logger.debug("No palette offset in game config for %s", game_name)
            return None

        base_offset = parse_offset(base_offset_str)

        # Calculate offset for this palette index
        # Each palette is 32 bytes (16 colors x 2 bytes BGR555)
        palette_offset = base_offset + (game_frame.palette_index * 32)
        logger.info(
            "Calculated palette ROM offset: 0x%X (base 0x%X + palette_index %d * 32)",
            palette_offset,
            base_offset,
            game_frame.palette_index,
        )
        return palette_offset
