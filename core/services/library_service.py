"""
Library service for sprite persistence operations.

Provides core CRUD operations for the sprite library, extracted from
ROMWorkflowController to reduce complexity.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.sprite_library import LibrarySprite, SpriteLibrary

logger = get_logger(__name__)


# Type alias for message callback
MessageCallback = Callable[[str], None]


class LibraryService:
    """
    Service for sprite library persistence operations.

    Responsibilities:
    - Save sprites to library with metadata
    - Update sprite metadata (name, palette association)
    - Delete sprites from library
    - Query sprites by ROM hash
    - Generate/load thumbnails for library sprites

    This service wraps SpriteLibrary operations and provides a cleaner
    interface for the controller, handling error cases and messaging.
    """

    def __init__(
        self,
        sprite_library: SpriteLibrary | None = None,
        *,
        on_message: MessageCallback | None = None,
    ) -> None:
        """Initialize the library service.

        Args:
            sprite_library: The sprite library for persistence.
            on_message: Callback for displaying messages to the user.
        """
        self._sprite_library = sprite_library
        self._on_message = on_message

    def set_sprite_library(self, library: SpriteLibrary | None) -> None:
        """Set the sprite library instance."""
        self._sprite_library = library

    def set_message_callback(self, callback: MessageCallback | None) -> None:
        """Set the message callback for user notifications."""
        self._on_message = callback

    def _show_message(self, message: str) -> None:
        """Display a message to the user if callback is set."""
        if self._on_message:
            self._on_message(message)

    def is_available(self) -> bool:
        """Check if the library service is available."""
        return self._sprite_library is not None

    def sprite_exists(self, offset: int, rom_path: str) -> bool:
        """Check if a sprite already exists in the library.

        Args:
            offset: The ROM offset.
            rom_path: Path to the ROM file.

        Returns:
            True if the sprite exists in the library.
        """
        if not self._sprite_library:
            return False

        rom_hash = self._sprite_library.compute_rom_hash(rom_path)
        existing = self._sprite_library.get_by_offset(offset, rom_hash)
        return len(existing) > 0

    def save_sprite(
        self,
        offset: int,
        rom_path: str,
        name: str,
        thumbnail: Image.Image | None = None,
        palette_colors: list[tuple[int, int, int]] | None = None,
        palette_name: str = "",
        palette_source: tuple[str, int] | None = None,
    ) -> LibrarySprite | None:
        """Save a sprite to the library.

        Args:
            offset: The ROM offset.
            rom_path: Path to the ROM file.
            name: Display name for the sprite.
            thumbnail: Optional PIL Image thumbnail.
            palette_colors: Optional palette colors.
            palette_name: Optional palette name.
            palette_source: Optional palette source identifier.

        Returns:
            The created LibrarySprite, or None if save failed.
        """
        if not self._sprite_library:
            logger.warning("Cannot save to library: sprite library not available")
            self._show_message("Cannot save to library: sprite library not available")
            return None

        if not rom_path:
            logger.warning("Cannot save to library: no ROM path provided")
            self._show_message("Cannot save to library: no ROM loaded")
            return None

        library = self._sprite_library

        # Check if already in library
        rom_hash = library.compute_rom_hash(rom_path)
        existing = library.get_by_offset(offset, rom_hash)
        if existing:
            logger.info("Sprite at 0x%06X already in library", offset)
            self._show_message(f"Sprite at 0x{offset:06X} is already in library")
            return existing[0]

        # Add to library
        sprite = library.add_sprite(
            rom_offset=offset,
            rom_path=rom_path,
            name=name,
            thumbnail=thumbnail,
            palette_colors=palette_colors,
            palette_name=palette_name,
            palette_source=palette_source,
        )

        if sprite is None:
            logger.error("Failed to save sprite to library: persistence failed for 0x%06X", offset)
            self._show_message("Failed to save sprite to library (disk write error)")
            return None

        logger.info("Saved to library: %s at 0x%06X", name, offset)
        self._show_message(f"Saved '{name}' to library")
        return sprite

    def rename_sprite(self, offset: int, rom_path: str, new_name: str) -> bool:
        """Rename a sprite in the library.

        Args:
            offset: The ROM offset.
            rom_path: Path to the ROM file.
            new_name: The new name for the sprite.

        Returns:
            True if rename succeeded, False otherwise.
        """
        if not self._sprite_library or not rom_path:
            return False

        library = self._sprite_library
        rom_hash = library.compute_rom_hash(rom_path)
        existing = library.get_by_offset(offset, rom_hash)

        if existing:
            library.update_sprite(existing[0].unique_id, name=new_name)
            logger.info("Updated library sprite name: %s", new_name)
            return True

        return False

    def delete_sprite(self, offset: int, rom_path: str) -> bool:
        """Delete a sprite from the library.

        Args:
            offset: The ROM offset.
            rom_path: Path to the ROM file.

        Returns:
            True if delete succeeded, False otherwise.
        """
        if not self._sprite_library or not rom_path:
            return False

        library = self._sprite_library
        rom_hash = library.compute_rom_hash(rom_path)
        matches = library.get_by_offset(offset, rom_hash)

        deleted = False
        for sprite in matches:
            library.remove_sprite(sprite.unique_id)
            logger.info("Removed persistent sprite: %s", sprite.unique_id)
            deleted = True

        return deleted

    def get_sprites_for_rom(self, rom_path: str) -> list[LibrarySprite]:
        """Get all library sprites for a specific ROM.

        Args:
            rom_path: Path to the ROM file.

        Returns:
            List of LibrarySprite objects for this ROM.
        """
        if not self._sprite_library or not rom_path:
            return []

        library = self._sprite_library
        rom_hash = library.compute_rom_hash(rom_path)

        return [sprite for sprite in library.sprites if sprite.rom_hash == rom_hash]

    def get_thumbnail_path(self, sprite: LibrarySprite) -> Path | None:
        """Get the thumbnail path for a library sprite.

        Args:
            sprite: The library sprite.

        Returns:
            Path to the thumbnail file, or None if not available.
        """
        if not self._sprite_library:
            return None

        path = self._sprite_library.get_thumbnail_path(sprite)
        if path and path.exists():
            return path
        return None

    def update_palette_association(
        self,
        offset: int,
        rom_path: str,
        palette_colors: list[tuple[int, int, int]] | None = None,
        palette_name: str = "",
        palette_source: tuple[str, int] | None = None,
    ) -> bool:
        """Update the palette association for a library sprite.

        Args:
            offset: The ROM offset.
            rom_path: Path to the ROM file.
            palette_colors: The new palette colors.
            palette_name: The new palette name.
            palette_source: The new palette source.

        Returns:
            True if update succeeded, False otherwise.
        """
        if not self._sprite_library or not rom_path:
            return False

        library = self._sprite_library
        rom_hash = library.compute_rom_hash(rom_path)
        existing = library.get_by_offset(offset, rom_hash)

        if existing:
            library.update_sprite(
                existing[0].unique_id,
                palette_colors=palette_colors,
                palette_name=palette_name,
                palette_source=palette_source,
            )
            logger.debug(
                "Updated library palette association for 0x%06X: %s (%s)",
                offset,
                palette_name,
                palette_source,
            )
            return True

        return False

    def update_sprite_offset(
        self,
        old_offset: int,
        new_offset: int,
        rom_path: str | Path,
    ) -> bool:
        """Update the ROM offset for a library sprite.

        Used when sprite offset alignment is corrected in the browser.
        Persists the change to the library file.

        Args:
            old_offset: The current ROM offset of the sprite.
            new_offset: The corrected/aligned ROM offset.
            rom_path: Path to the ROM file for hash matching.

        Returns:
            True if update succeeded, False otherwise.
        """
        if not self._sprite_library:
            return False

        library = self._sprite_library
        rom_hash = library.compute_rom_hash(Path(rom_path))

        for sprite in library.sprites:
            if sprite.rom_hash == rom_hash and sprite.rom_offset == old_offset:
                sprite.rom_offset = new_offset
                library.save()
                logger.info(
                    "Updated library sprite offset: 0x%06X → 0x%06X",
                    old_offset,
                    new_offset,
                )
                return True

        return False
