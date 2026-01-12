"""
Sprite Library for persistent sprite storage.

Stores discovered sprites with metadata (ROM offset, thumbnail, name, notes)
for quick access across sessions without re-discovery.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


def _datetime_to_iso(dt: datetime | None) -> str | None:
    """Convert datetime to ISO format string."""
    return dt.isoformat() if dt is not None else None


def _iso_to_datetime(s: object | None) -> datetime | None:
    """Convert ISO format string to datetime."""
    if isinstance(s, str):
        return datetime.fromisoformat(s)
    return None


@dataclass
class LibrarySprite:
    """A sprite entry in the library.

    Attributes:
        rom_offset: Offset in ROM where sprite data begins
        rom_hash: SHA256 hash of ROM file (for matching across sessions)
        name: User-assigned name for the sprite
        thumbnail_path: Path to PNG thumbnail (relative to library directory)
        notes: User notes about the sprite
        created_at: When the sprite was added to library
        last_edited: When the sprite was last modified (None if never edited)
        tags: Optional list of tags for categorization
    """

    rom_offset: int
    rom_hash: str
    name: str
    thumbnail_path: str = ""
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_edited: datetime | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def offset_hex(self) -> str:
        """ROM offset as hex string."""
        return f"0x{self.rom_offset:06X}"

    @property
    def unique_id(self) -> str:
        """Unique identifier combining ROM hash and offset."""
        return f"{self.rom_hash[:8]}_{self.rom_offset:06X}"

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d["created_at"] = _datetime_to_iso(self.created_at)
        d["last_edited"] = _datetime_to_iso(self.last_edited)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> LibrarySprite:
        """Create from dictionary (JSON deserialization)."""
        created_at = _iso_to_datetime(d.get("created_at")) or datetime.now()
        last_edited = _iso_to_datetime(d.get("last_edited"))

        tags_obj = d.get("tags", [])
        tags = [str(t) for t in tags_obj] if isinstance(tags_obj, list) else []

        return cls(
            rom_offset=int(str(d["rom_offset"])),
            rom_hash=str(d["rom_hash"]),
            name=str(d["name"]),
            thumbnail_path=str(d.get("thumbnail_path", "")),
            notes=str(d.get("notes", "")),
            created_at=created_at,
            last_edited=last_edited,
            tags=tags,
        )


class SpriteLibrary(QObject):
    """
    Persistent storage for discovered sprites.

    Stores sprites in a JSON file with PNG thumbnails in a subdirectory.
    Provides filtering, searching, and tagging capabilities.

    Signals:
        sprite_added: Emitted when a sprite is added. Args: (LibrarySprite)
        sprite_removed: Emitted when a sprite is removed. Args: (unique_id: str)
        sprite_updated: Emitted when a sprite is updated. Args: (LibrarySprite)
        library_loaded: Emitted when library is loaded from disk. Args: (count: int)
    """

    sprite_added = Signal(object)  # LibrarySprite
    sprite_removed = Signal(str)  # unique_id
    sprite_updated = Signal(object)  # LibrarySprite
    library_loaded = Signal(int)  # count

    def __init__(
        self,
        library_dir: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        # Default to ~/.spritepal/library/
        if library_dir is None:
            library_dir = Path.home() / ".spritepal" / "library"

        self._library_dir = library_dir
        self._library_file = library_dir / "sprites.json"
        self._thumbnails_dir = library_dir / "thumbnails"

        self._sprites: dict[str, LibrarySprite] = {}  # unique_id -> sprite
        self._loaded = False

    @property
    def library_dir(self) -> Path:
        """Directory containing library data."""
        return self._library_dir

    @property
    def sprites(self) -> list[LibrarySprite]:
        """All sprites in the library."""
        return list(self._sprites.values())

    @property
    def count(self) -> int:
        """Number of sprites in the library."""
        return len(self._sprites)

    def ensure_directories(self) -> None:
        """Ensure library directories exist."""
        self._library_dir.mkdir(parents=True, exist_ok=True)
        self._thumbnails_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> bool:
        """
        Load library from disk.

        Returns:
            True if loaded successfully, False if file doesn't exist or error.
        """
        if not self._library_file.exists():
            logger.debug("Library file does not exist: %s", self._library_file)
            self._loaded = True
            return False

        try:
            with self._library_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            self._sprites.clear()
            for sprite_data in data.get("sprites", []):
                try:
                    sprite = LibrarySprite.from_dict(sprite_data)
                    self._sprites[sprite.unique_id] = sprite
                except (KeyError, TypeError) as e:
                    logger.warning("Failed to load sprite: %s", e)

            self._loaded = True
            logger.info("Loaded %d sprites from library", len(self._sprites))
            self.library_loaded.emit(len(self._sprites))
            return True

        except (OSError, json.JSONDecodeError) as e:
            logger.error("Failed to load library: %s", e)
            self._loaded = True
            return False

    def save(self) -> bool:
        """
        Save library to disk.

        Returns:
            True if saved successfully, False on error.
        """
        self.ensure_directories()

        data = {
            "version": 1,
            "sprites": [s.to_dict() for s in self._sprites.values()],
        }

        try:
            # Write to temp file first, then rename for atomicity
            temp_file = self._library_file.with_suffix(".tmp")
            with temp_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_file.replace(self._library_file)

            logger.debug("Saved %d sprites to library", len(self._sprites))
            return True

        except OSError as e:
            logger.error("Failed to save library: %s", e)
            return False

    def add_sprite(
        self,
        rom_offset: int,
        rom_path: Path | str,
        name: str,
        thumbnail: Image.Image | None = None,
        notes: str = "",
        tags: list[str] | None = None,
    ) -> LibrarySprite | None:
        """
        Add a sprite to the library.

        Args:
            rom_offset: Offset in ROM where sprite data begins
            rom_path: Path to ROM file (used for hash calculation)
            name: User-assigned name for the sprite
            thumbnail: Optional PIL Image for thumbnail
            notes: Optional notes about the sprite
            tags: Optional list of tags

        Returns:
            The created LibrarySprite, or None if persistence failed.
        """
        rom_hash = self._compute_rom_hash(Path(rom_path))

        sprite = LibrarySprite(
            rom_offset=rom_offset,
            rom_hash=rom_hash,
            name=name,
            notes=notes,
            tags=tags or [],
        )

        # Save thumbnail if provided
        if thumbnail is not None:
            thumbnail_path = self._save_thumbnail(sprite.unique_id, thumbnail)
            sprite.thumbnail_path = thumbnail_path

        self._sprites[sprite.unique_id] = sprite

        # Persist to disk - if this fails, rollback and return None
        if not self.save():
            logger.error("Failed to persist sprite to library, rolling back: %s", name)
            del self._sprites[sprite.unique_id]
            return None

        logger.info("Added sprite to library: %s at %s", name, sprite.offset_hex)
        self.sprite_added.emit(sprite)
        return sprite

    def remove_sprite(self, unique_id: str) -> bool:
        """
        Remove a sprite from the library.

        Args:
            unique_id: Unique identifier of sprite to remove

        Returns:
            True if removed, False if not found
        """
        if unique_id not in self._sprites:
            return False

        sprite = self._sprites.pop(unique_id)

        # Delete thumbnail if exists
        if sprite.thumbnail_path:
            thumbnail_file = self._thumbnails_dir / sprite.thumbnail_path
            if thumbnail_file.exists():
                try:
                    thumbnail_file.unlink()
                except OSError:
                    logger.warning("Failed to delete thumbnail: %s", thumbnail_file)

        self.save()

        logger.info("Removed sprite from library: %s", unique_id)
        self.sprite_removed.emit(unique_id)
        return True

    def update_sprite(
        self,
        unique_id: str,
        name: str | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
        thumbnail: Image.Image | None = None,
    ) -> LibrarySprite | None:
        """
        Update a sprite's metadata.

        Args:
            unique_id: Unique identifier of sprite to update
            name: New name (None to keep current)
            notes: New notes (None to keep current)
            tags: New tags (None to keep current)
            thumbnail: New thumbnail (None to keep current)

        Returns:
            Updated sprite, or None if not found
        """
        if unique_id not in self._sprites:
            return None

        sprite = self._sprites[unique_id]

        if name is not None:
            sprite.name = name
        if notes is not None:
            sprite.notes = notes
        if tags is not None:
            sprite.tags = tags
        if thumbnail is not None:
            sprite.thumbnail_path = self._save_thumbnail(unique_id, thumbnail)

        sprite.last_edited = datetime.now()
        self.save()

        logger.debug("Updated sprite: %s", unique_id)
        self.sprite_updated.emit(sprite)
        return sprite

    def get_sprite(self, unique_id: str) -> LibrarySprite | None:
        """Get a sprite by unique ID."""
        return self._sprites.get(unique_id)

    def get_by_offset(self, rom_offset: int, rom_hash: str | None = None) -> list[LibrarySprite]:
        """
        Find sprites by ROM offset.

        Args:
            rom_offset: ROM offset to search for
            rom_hash: Optional ROM hash to filter by

        Returns:
            List of matching sprites
        """
        matches = []
        for sprite in self._sprites.values():
            if sprite.rom_offset == rom_offset:
                if rom_hash is None or sprite.rom_hash == rom_hash:
                    matches.append(sprite)
        return matches

    def search(self, query: str) -> list[LibrarySprite]:
        """
        Search sprites by name, notes, or tags.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching sprites
        """
        query = query.lower()
        matches = []
        for sprite in self._sprites.values():
            if (
                query in sprite.name.lower()
                or query in sprite.notes.lower()
                or any(query in tag.lower() for tag in sprite.tags)
            ):
                matches.append(sprite)
        return matches

    def get_thumbnail_path(self, sprite: LibrarySprite) -> Path | None:
        """Get full path to sprite's thumbnail."""
        if not sprite.thumbnail_path:
            return None
        path = self._thumbnails_dir / sprite.thumbnail_path
        return path if path.exists() else None

    def compute_rom_hash(self, rom_path: Path | str) -> str:
        """Compute SHA256 hash of ROM file (public access)."""
        return self._compute_rom_hash(Path(rom_path))

    def _compute_rom_hash(self, rom_path: Path) -> str:
        """Compute SHA256 hash of ROM file."""
        try:
            hasher = hashlib.sha256()
            with rom_path.open("rb") as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError as e:
            logger.error("Failed to compute ROM hash: %s", e)
            return ""

    def _save_thumbnail(self, unique_id: str, image: Image.Image) -> str:
        """Save thumbnail image and return relative path."""
        self.ensure_directories()

        # Resize if needed (max 64x64)
        max_size = 64
        if image.width > max_size or image.height > max_size:
            # Use LANCZOS for high-quality downscaling
            image.thumbnail((max_size, max_size), resample=Image.Resampling.LANCZOS)

        filename = f"{unique_id}.png"
        path = self._thumbnails_dir / filename

        try:
            image.save(path, "PNG")
            return filename
        except OSError as e:
            logger.error("Failed to save thumbnail: %s", e)
            return ""

    def cleanup(self) -> None:
        """Cleanup resources and save pending changes."""
        if self._loaded and self._sprites:
            self.save()
