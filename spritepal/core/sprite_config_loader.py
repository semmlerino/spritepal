"""
Sprite configuration loader for SpritePal
Loads sprite locations from external configuration files
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.logging_config import get_logger

logger = get_logger(__name__)

@dataclass
class SpriteConfig:
    """Configuration for a single sprite location"""

    name: str
    offset: int
    description: str
    compressed: bool
    estimated_size: int
    palette_indices: list[int] | None = None
    offset_variants: list[int] | None = None

class SpriteConfigLoader:
    """Loads and manages sprite location configurations"""

    DEFAULT_CONFIG_PATH: str = str(
        Path(__file__).parent.parent / "config" / "sprite_locations.json"
    )

    def __init__(self, config_path: str | None = None) -> None:
        """
        Initialize sprite config loader.

        Args:
            config_path: Path to configuration file (uses default if None)
        """
        self.config_path: str = config_path or self.DEFAULT_CONFIG_PATH
        # JSON data is inherently untyped; structure validated at runtime
        self.config_data: dict[str, Any] = {}  # pyright: ignore[reportExplicitAny]
        self.load_config()

    def load_config(self) -> None:
        """Load sprite configuration from JSON file"""
        config_path_obj = Path(self.config_path)
        if not config_path_obj.exists():
            logger.warning(f"Sprite config not found: {self.config_path}")
            return

        try:
            with config_path_obj.open() as f:
                self.config_data = json.load(f)
            logger.info(f"Loaded sprite config: {self.config_path}")
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load sprite config")

    @staticmethod
    def _get_size_field(
        sprite_data: dict[str, Any], default: int = 8192  # pyright: ignore[reportExplicitAny]
    ) -> int:
        """
        Get sprite size from config, supporting both field name conventions.

        Args:
            sprite_data: Sprite configuration dictionary
            default: Default size if neither field is present

        Returns:
            Sprite size in bytes
        """
        # Prefer 'estimated_size' for backward compatibility with existing code
        if "estimated_size" in sprite_data:
            return int(sprite_data["estimated_size"])
        # Fall back to 'expected_size' (used in newer JSON configs from scanner)
        if "expected_size" in sprite_data:
            return int(sprite_data["expected_size"])
        return default

    def find_game_config(
        self, rom_title: str, rom_checksum: int
    ) -> tuple[str | None, Mapping[str, object] | None]:
        """
        Find game configuration by checksum (preferred) or flexible title matching.

        This method provides consistent game matching for both sprite extraction
        and palette extraction, using checksum matching first (most reliable),
        then falling back to flexible title matching with regional variant support.

        Args:
            rom_title: ROM title from header
            rom_checksum: ROM checksum

        Returns:
            Tuple of (game_name, game_config) or (None, None) if not found
        """
        if "games" not in self.config_data:
            return None, None

        checksum_hex = f"0x{rom_checksum:04X}"

        # Try to find matching game by checksum first (most reliable)
        checksum_matched_game = None

        for game_name, game_data in self.config_data["games"].items():
            checksums = game_data.get("checksums", {})
            for version, expected_checksum in checksums.items():
                # Parse checksum
                if isinstance(expected_checksum, str):
                    expected = (
                        int(expected_checksum, 16)
                        if expected_checksum.startswith("0x")
                        else int(expected_checksum)
                    )
                else:
                    expected = expected_checksum

                if rom_checksum == expected:
                    checksum_matched_game = game_name
                    logger.info(f"Found checksum match: {game_name} ({version}) = {checksum_hex}")
                    break

            if checksum_matched_game:
                break

        # Then try title matching with flexible patterns
        title_matched_games = []
        for game_name in self.config_data["games"]:
            if self._title_matches(game_name, rom_title):
                title_matched_games.append(game_name)
                logger.debug(f"Title pattern match: '{game_name}' matches '{rom_title}'")

        # Decide which game config to use
        selected_game = None

        if checksum_matched_game:
            selected_game = checksum_matched_game
            if selected_game not in title_matched_games:
                logger.warning(
                    f"ROM checksum {checksum_hex} matches '{selected_game}' but "
                    f"title '{rom_title}' doesn't match expected pattern"
                )
        elif title_matched_games:
            selected_game = title_matched_games[0]
            logger.warning(
                f"No checksum match for {checksum_hex}, using title match: '{selected_game}'"
            )
        else:
            logger.debug(
                f"No game configuration found for ROM: title='{rom_title}', checksum={checksum_hex}"
            )
            return None, None

        return selected_game, self.config_data["games"][selected_game]

    def get_game_sprites(
        self, rom_title: str, rom_checksum: int
    ) -> dict[str, SpriteConfig]:
        """
        Get sprite configurations for a specific game.

        Args:
            rom_title: ROM title from header
            rom_checksum: ROM checksum

        Returns:
            Dictionary of sprite name to SpriteConfig
        """
        sprites = {}

        if "games" not in self.config_data:
            return sprites

        # Convert checksum to hex string for logging
        checksum_hex = f"0x{rom_checksum:04X}"
        logger.info(f"Looking for ROM configuration: title='{rom_title}', checksum={checksum_hex}")

        # Try to find matching game by checksum first (most reliable)
        checksum_matched_game = None
        checksum_matched_version = None

        for game_name, game_data in self.config_data["games"].items():
            checksums = game_data.get("checksums", {})
            for version, expected_checksum in checksums.items():
                # Parse checksum
                if isinstance(expected_checksum, str):
                    expected = (
                        int(expected_checksum, 16)
                        if expected_checksum.startswith("0x")
                        else int(expected_checksum)
                    )
                else:
                    expected = expected_checksum

                if rom_checksum == expected:
                    checksum_matched_game = game_name
                    checksum_matched_version = version
                    logger.info(f"Found checksum match: {game_name} ({version}) = {checksum_hex}")
                    break

            if checksum_matched_game:
                break

        # Then try title matching with flexible patterns
        title_matched_games = []
        for game_name in self.config_data["games"]:
            # Check multiple title matching patterns
            if self._title_matches(game_name, rom_title):
                title_matched_games.append(game_name)
                logger.debug(f"Title pattern match: '{game_name}' matches '{rom_title}'")

        # Decide which game config to use
        selected_game = None
        selected_version = None

        if checksum_matched_game:
            # Prefer checksum match
            selected_game = checksum_matched_game
            selected_version = checksum_matched_version

            # Warn if title doesn't match
            if selected_game not in title_matched_games:
                logger.warning(
                    f"ROM checksum {checksum_hex} matches '{selected_game}' but "
                    f"title '{rom_title}' doesn't match expected pattern"
                )
        elif title_matched_games:
            # Use title match if no checksum match
            selected_game = title_matched_games[0]
            logger.warning(
                f"No checksum match for {checksum_hex}, using title match: '{selected_game}'"
            )

            # Log all known checksums for this game
            game_data = self.config_data["games"][selected_game]
            checksums = game_data.get("checksums", {})
            if checksums:
                logger.info(f"Known checksums for {selected_game}:")
                for version, cs in checksums.items():
                    logger.info(f"  {version}: {cs}")
        else:
            logger.error(
                f"No configuration found for ROM: title='{rom_title}', checksum={checksum_hex}"
            )
            return sprites

        # Load sprite configurations
        game_data = self.config_data["games"][selected_game]
        logger.info(f"Loading sprite configurations from: {selected_game}")

        # Get game-level offset_variants for fallback (some configs store variants at game level)
        game_level_variants = game_data.get("offset_variants", {})

        for sprite_name, sprite_data in game_data.get("sprites", {}).items():
            # Skip metadata entries like "_note"
            if sprite_name.startswith("_"):
                continue

            offset_str = sprite_data.get("offset", "0x0")
            offset = (
                int(offset_str, 16)
                if offset_str.startswith("0x")
                else int(offset_str)
            )

            # Get offset variants if available (sprite-level first, then game-level fallback)
            offset_variants = None
            if selected_version:
                # Check sprite-level offset_variants first
                if "offset_variants" in sprite_data:
                    version_variants = sprite_data["offset_variants"].get(selected_version, [])
                # Fall back to game-level offset_variants
                elif game_level_variants:
                    version_variants = game_level_variants.get(selected_version, [])
                else:
                    version_variants = []

                if version_variants:
                    # Convert hex strings to integers
                    offset_variants = []
                    for variant in version_variants:
                        try:
                            variant_offset = (
                                int(variant, 16) if variant.startswith("0x") else int(variant)
                            )
                            offset_variants.append(variant_offset)
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid offset variant: {variant}")

                    if offset_variants:
                        logger.debug(
                            f"Found {len(offset_variants)} offset variants for "
                            f"{sprite_name} ({selected_version})"
                        )

            sprites[sprite_name] = SpriteConfig(
                name=sprite_name,
                offset=offset,
                description=sprite_data.get("description", ""),
                compressed=sprite_data.get("compressed", True),
                estimated_size=self._get_size_field(sprite_data),
                palette_indices=sprite_data.get("palette_indices", None),
                offset_variants=offset_variants,
            )

        logger.info(f"Loaded {len(sprites)} sprite configurations")
        return sprites

    def _title_matches(self, game_name: str, rom_title: str) -> bool:
        """
        Check if a game name matches a ROM title with flexible patterns.

        Args:
            game_name: Game name from config
            rom_title: ROM title from header

        Returns:
            True if titles match
        """
        game_upper = game_name.upper()
        title_upper = rom_title.upper()

        # Direct substring match
        if game_upper in title_upper:
            return True

        # Check for common variations
        # KIRBY SUPER STAR <-> KIRBY'S FUN PAK
        if "KIRBY" in game_upper and "KIRBY" in title_upper:
            # Both are Kirby games, check for known equivalents
            equivalents = [
                ("SUPER STAR", "FUN PAK"),
                ("SUPER DELUXE", "FUN PAK"),
            ]

            for equiv1, equiv2 in equivalents:
                if (equiv1 in game_upper and equiv2 in title_upper) or \
                   (equiv2 in game_upper and equiv1 in title_upper):
                    return True

        return False

    def get_all_known_sprites(self) -> dict[str, dict[str, SpriteConfig]]:
        """
        Get all known sprite configurations for all games.

        Returns:
            Dictionary of game name to sprite configurations
        """
        all_sprites = {}

        if "games" not in self.config_data:
            return all_sprites

        for game_name, game_data in self.config_data["games"].items():
            sprites = {}

            for sprite_name, sprite_data in game_data.get("sprites", {}).items():
                offset_str = sprite_data.get("offset", "0x0")
                offset = (
                    int(offset_str, 16)
                    if offset_str.startswith("0x")
                    else int(offset_str)
                )

                sprites[sprite_name] = SpriteConfig(
                    name=sprite_name,
                    offset=offset,
                    description=sprite_data.get("description", ""),
                    compressed=sprite_data.get("compressed", True),
                    estimated_size=self._get_size_field(sprite_data),
                    palette_indices=sprite_data.get("palette_indices", None),
                )

            all_sprites[game_name] = sprites

        return all_sprites

    def add_custom_sprite(
        self,
        game_name: str,
        sprite_name: str,
        offset: int,
        description: str = "",
        compressed: bool = True,
        estimated_size: int = 8192,
    ) -> None:
        """
        Add a custom sprite location (runtime only, not saved).

        Args:
            game_name: Name of the game
            sprite_name: Name of the sprite
            offset: ROM offset
            description: Sprite description
            compressed: Whether sprite is compressed
            estimated_size: Estimated size in bytes
        """
        if "games" not in self.config_data:
            self.config_data["games"] = {}

        if game_name not in self.config_data["games"]:
            self.config_data["games"][game_name] = {"sprites": {}}

        self.config_data["games"][game_name]["sprites"][sprite_name] = {
            "offset": f"0x{offset:X}",
            "description": description,
            "compressed": compressed,
            "estimated_size": estimated_size,
        }

        logger.info(f"Added custom sprite: {game_name} - {sprite_name} at 0x{offset:X}")

    def save_config(self, output_path: str | None = None) -> None:
        """
        Save current configuration to file.

        Args:
            output_path: Path to save to (uses original path if None)
        """
        save_path = output_path or self.config_path

        try:
            with Path(save_path).open("w") as f:
                json.dump(self.config_data, f, indent=2)
            logger.info(f"Saved sprite config: {save_path}")
        except OSError:
            logger.exception("Failed to save sprite config")
