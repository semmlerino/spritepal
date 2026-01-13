"""
Sprite project persistence for saving and loading edited sprites.

A .spritepal file contains all data needed to reinject an edited sprite:
- Tile data (4bpp format)
- Palette (16 colors)
- ROM injection metadata (offset, compression info, etc.)
- Edit metadata (timestamps, notes)
"""

from __future__ import annotations

import base64
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from PIL import Image

from core.tile_utils import decode_4bpp_tile
from utils.file_validator import atomic_write

logger = logging.getLogger(__name__)

FORMAT_VERSION = "1.0"


class SpriteProjectError(Exception):
    """Error loading or saving sprite project."""


@dataclass
class SpriteProject:
    """
    A saved sprite project containing all data needed for reinjection.

    Attributes:
        name: Display name for the sprite
        width: Sprite width in pixels
        height: Sprite height in pixels
        tile_data: Raw 4bpp tile bytes (32 bytes per 8x8 tile)
        tile_count: Number of 8x8 tiles
        preview_png: Optional rendered PNG for thumbnails

        palette_colors: 16 RGB color tuples
        palette_name: Name of the palette
        palette_index: Palette index (0-7 typically)

        original_rom_offset: File offset in source ROM
        original_compressed_size: Size of compressed data in ROM
        header_bytes: Alignment bytes prepended during extraction
        compression_type: "hal" or "raw"
        rom_title: Source ROM title
        rom_checksum: Source ROM checksum (hex string)

        created_at: When the project was first saved
        last_modified: When the project was last modified
        notes: User notes
    """

    # Sprite data
    name: str
    width: int
    height: int
    tile_data: bytes
    tile_count: int
    preview_png: bytes | None = None

    # Palette
    palette_colors: list[tuple[int, int, int]] = field(default_factory=list)
    palette_name: str = ""
    palette_index: int = 0

    # Injection metadata
    original_rom_offset: int = 0
    original_compressed_size: int = 0
    header_bytes: bytes = b""
    compression_type: str = "hal"
    rom_title: str = ""
    rom_checksum: str = ""

    # Edit metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_modified: datetime = field(default_factory=lambda: datetime.now(UTC))
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        return {
            "format_version": FORMAT_VERSION,
            "sprite": {
                "name": self.name,
                "width": self.width,
                "height": self.height,
                "tile_data_b64": base64.b64encode(self.tile_data).decode("ascii"),
                "tile_count": self.tile_count,
                "preview_png_b64": (base64.b64encode(self.preview_png).decode("ascii") if self.preview_png else None),
            },
            "palette": {
                "name": self.palette_name,
                "colors": [list(c) for c in self.palette_colors],
                "index": self.palette_index,
            },
            "injection_metadata": {
                "original_rom_offset": self.original_rom_offset,
                "original_rom_offset_hex": f"0x{self.original_rom_offset:06X}",
                "original_compressed_size": self.original_compressed_size,
                "header_bytes_b64": base64.b64encode(self.header_bytes).decode("ascii"),
                "compression_type": self.compression_type,
                "rom_title": self.rom_title,
                "rom_checksum": self.rom_checksum,
            },
            "edit_metadata": {
                "created_at": self.created_at.isoformat(),
                "last_modified": self.last_modified.isoformat(),
                "notes": self.notes,
            },
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SpriteProject:
        """Create from dictionary (parsed JSON)."""
        version = data.get("format_version", "unknown")
        if version != FORMAT_VERSION:
            logger.warning("Loading project with version %s (current: %s)", version, FORMAT_VERSION)

        # Cast nested dicts to proper types
        sprite = cast(dict[str, object], data.get("sprite", {}))
        palette = cast(dict[str, object], data.get("palette", {}))
        injection = cast(dict[str, object], data.get("injection_metadata", {}))
        edit = cast(dict[str, object], data.get("edit_metadata", {}))

        # Validate required fields
        required_sprite = ["name", "width", "height", "tile_data_b64", "tile_count"]
        for field_name in required_sprite:
            if field_name not in sprite:
                raise SpriteProjectError(f"Missing required field: sprite.{field_name}")

        # Decode base64 data
        try:
            tile_data = base64.b64decode(cast(str, sprite["tile_data_b64"]))
        except Exception as e:
            raise SpriteProjectError(f"Invalid tile_data_b64: {e}") from e

        preview_png = None
        preview_b64 = sprite.get("preview_png_b64")
        if preview_b64:
            try:
                preview_png = base64.b64decode(cast(str, preview_b64))
            except Exception as e:
                logger.warning("Could not decode preview_png_b64: %s", e)

        header_bytes = b""
        header_b64 = injection.get("header_bytes_b64")
        if header_b64:
            try:
                header_bytes = base64.b64decode(cast(str, header_b64))
            except Exception as e:
                logger.warning("Could not decode header_bytes_b64: %s", e)

        # Parse palette colors
        palette_colors: list[tuple[int, int, int]] = []
        colors_list = cast(list[list[int]], palette.get("colors", []))
        for color in colors_list:
            if len(color) >= 3:
                palette_colors.append((int(color[0]), int(color[1]), int(color[2])))

        # Parse timestamps
        created_at = datetime.now(UTC)
        created_at_str = edit.get("created_at")
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(cast(str, created_at_str))
            except ValueError:
                pass

        last_modified = datetime.now(UTC)
        last_modified_str = edit.get("last_modified")
        if last_modified_str:
            try:
                last_modified = datetime.fromisoformat(cast(str, last_modified_str))
            except ValueError:
                pass

        return cls(
            name=cast(str, sprite["name"]),
            width=cast(int, sprite["width"]),
            height=cast(int, sprite["height"]),
            tile_data=tile_data,
            tile_count=cast(int, sprite["tile_count"]),
            preview_png=preview_png,
            palette_colors=palette_colors,
            palette_name=cast(str, palette.get("name", "")),
            palette_index=cast(int, palette.get("index", 0)),
            original_rom_offset=cast(int, injection.get("original_rom_offset", 0)),
            original_compressed_size=cast(int, injection.get("original_compressed_size", 0)),
            header_bytes=header_bytes,
            compression_type=cast(str, injection.get("compression_type", "hal")),
            rom_title=cast(str, injection.get("rom_title", "")),
            rom_checksum=cast(str, injection.get("rom_checksum", "")),
            created_at=created_at,
            last_modified=last_modified,
            notes=cast(str, edit.get("notes", "")),
        )

    @classmethod
    def from_json(cls, json_str: str) -> SpriteProject:
        """Deserialize from JSON string."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise SpriteProjectError(f"Invalid JSON: {e}") from e
        return cls.from_dict(data)

    def save(self, path: Path | str) -> None:
        """
        Save project to file using atomic write.

        Args:
            path: Destination file path

        Raises:
            SpriteProjectError: If save fails
        """
        path = Path(path)
        self.last_modified = datetime.now(UTC)

        try:
            json_bytes = self.to_json().encode("utf-8")
            atomic_write(path, json_bytes)
            logger.info("Saved sprite project to %s", path)
        except Exception as e:
            raise SpriteProjectError(f"Failed to save project: {e}") from e

    @classmethod
    def load(cls, path: Path | str) -> SpriteProject:
        """
        Load project from file.

        Args:
            path: Source file path

        Returns:
            Loaded SpriteProject

        Raises:
            SpriteProjectError: If load fails
        """
        path = Path(path)

        if not path.exists():
            raise SpriteProjectError(f"File not found: {path}")

        try:
            json_str = path.read_text(encoding="utf-8")
            return cls.from_json(json_str)
        except SpriteProjectError:
            raise
        except Exception as e:
            raise SpriteProjectError(f"Failed to load project: {e}") from e

    def generate_preview_png(self) -> bytes:
        """
        Generate a PNG preview image from tile data and palette.

        Returns:
            PNG image as bytes
        """
        if not self.tile_data or not self.palette_colors:
            raise SpriteProjectError("Cannot generate preview: missing tile data or palette")

        # Decode tiles to pixel indices
        num_tiles = len(self.tile_data) // 32
        if num_tiles == 0:
            raise SpriteProjectError("No tiles in tile_data")

        # Calculate grid dimensions (tiles per row)
        tiles_per_row = self.width // 8 if self.width >= 8 else 1
        tiles_per_col = self.height // 8 if self.height >= 8 else 1

        # Create indexed image
        img = Image.new("P", (self.width, self.height), 0)

        # Build flat palette for PIL (R, G, B, R, G, B, ...)
        flat_palette: list[int] = []
        for r, g, b in self.palette_colors[:16]:
            flat_palette.extend([r, g, b])
        # Pad to 256 colors (768 values)
        while len(flat_palette) < 768:
            flat_palette.extend([0, 0, 0])
        img.putpalette(flat_palette)

        # Decode and place tiles
        pixels = img.load()
        for tile_idx in range(min(num_tiles, tiles_per_row * tiles_per_col)):
            tile_x = (tile_idx % tiles_per_row) * 8
            tile_y = (tile_idx // tiles_per_row) * 8

            tile_bytes = self.tile_data[tile_idx * 32 : (tile_idx + 1) * 32]
            tile_pixels = decode_4bpp_tile(tile_bytes)

            for py in range(8):
                for px in range(8):
                    x = tile_x + px
                    y = tile_y + py
                    if x < self.width and y < self.height and pixels is not None:
                        pixels[x, y] = tile_pixels[py][px]

        # Convert to PNG bytes
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def update_preview(self) -> None:
        """Regenerate the preview PNG from current tile data."""
        try:
            self.preview_png = self.generate_preview_png()
        except Exception as e:
            logger.warning("Could not generate preview: %s", e)
            self.preview_png = None
