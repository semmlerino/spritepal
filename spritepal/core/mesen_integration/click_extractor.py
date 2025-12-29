"""
Parser for Mesen 2 sprite capture JSON files.

Parses the sprite_capture.json output from mesen2_sprite_capture.lua
into typed Python dataclasses for use in extraction pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class TileData:
    """VRAM tile data from capture."""

    tile_index: int
    vram_addr: int
    pos_x: int  # Position within sprite (0, 1, 2...)
    pos_y: int
    data_hex: str  # 64 hex chars = 32 bytes of 4bpp tile data

    @property
    def data_bytes(self) -> bytes:
        """Convert hex string to bytes."""
        return bytes.fromhex(self.data_hex)


@dataclass
class OAMEntry:
    """Single OAM entry from Mesen 2 capture."""

    id: int
    x: int
    y: int
    tile: int  # Base tile index
    width: int
    height: int
    flip_h: bool
    flip_v: bool
    palette: int
    priority: int = 0
    name_table: int = 0
    size_large: bool = False
    tiles: list[TileData] = field(default_factory=list)

    @property
    def tiles_wide(self) -> int:
        """Number of 8x8 tiles horizontally."""
        return self.width // 8

    @property
    def tiles_high(self) -> int:
        """Number of 8x8 tiles vertically."""
        return self.height // 8


@dataclass
class OBSELConfig:
    """SNES OBSEL register configuration."""

    raw: int
    name_base: int
    name_select: int
    size_select: int
    tile_base_addr: int


@dataclass
class CaptureResult:
    """Complete capture result from Mesen 2 Lua script."""

    frame: int
    visible_count: int
    obsel: OBSELConfig
    entries: list[OAMEntry]
    palettes: dict[int, list[int]]  # palette_index -> list of 16 colors
    timestamp: int = 0

    @property
    def has_entries(self) -> bool:
        """Check if any entries were captured."""
        return len(self.entries) > 0

    def get_entries_by_palette(self, palette: int) -> list[OAMEntry]:
        """Get all OAM entries using a specific palette."""
        return [e for e in self.entries if e.palette == palette]

    def get_entries_in_region(
        self, x: int, y: int, width: int, height: int
    ) -> list[OAMEntry]:
        """Get all OAM entries within a screen region."""
        result = []
        for entry in self.entries:
            # Check if sprite overlaps with region
            if (
                entry.x < x + width
                and entry.x + entry.width > x
                and entry.y < y + height
                and entry.y + entry.height > y
            ):
                result.append(entry)
        return result


class MesenCaptureParser:
    """Parser for Mesen 2 sprite capture JSON files."""

    def parse_file(self, json_path: str | Path) -> CaptureResult:
        """
        Parse a sprite_capture.json file.

        Args:
            json_path: Path to the JSON file

        Returns:
            CaptureResult with parsed data

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If JSON is malformed or missing required fields
        """
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Capture file not found: {path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in capture file: {e}") from e

        return self._parse_capture_data(data)

    def parse_string(self, json_string: str) -> CaptureResult:
        """
        Parse JSON string directly.

        Args:
            json_string: JSON string to parse

        Returns:
            CaptureResult with parsed data
        """
        try:
            data = json.loads(json_string)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        return self._parse_capture_data(data)

    def _parse_capture_data(
        self,
        data: dict[str, Any],  # pyright: ignore[reportExplicitAny] - JSON data
    ) -> CaptureResult:
        """Parse raw JSON dict into CaptureResult."""
        # Parse OBSEL config
        obsel_data = data.get("obsel", {})
        obsel = OBSELConfig(
            raw=obsel_data.get("raw", 0),
            name_base=obsel_data.get("name_base", 0),
            name_select=obsel_data.get("name_select", 0),
            size_select=obsel_data.get("size_select", 0),
            tile_base_addr=obsel_data.get("tile_base_addr", 0),
        )

        # Parse OAM entries
        entries = []
        for entry_data in data.get("entries", []):
            # Parse tile data
            tiles = []
            for tile_data in entry_data.get("tiles", []):
                tile = TileData(
                    tile_index=tile_data.get("tile_index", 0),
                    vram_addr=tile_data.get("vram_addr", 0),
                    pos_x=tile_data.get("pos_x", 0),
                    pos_y=tile_data.get("pos_y", 0),
                    data_hex=tile_data.get("data_hex", ""),
                )
                tiles.append(tile)

            entry = OAMEntry(
                id=entry_data.get("id", 0),
                x=entry_data.get("x", 0),
                y=entry_data.get("y", 0),
                tile=entry_data.get("tile", 0),
                width=entry_data.get("width", 8),
                height=entry_data.get("height", 8),
                flip_h=entry_data.get("flip_h", False),
                flip_v=entry_data.get("flip_v", False),
                palette=entry_data.get("palette", 0),
                priority=entry_data.get("priority", 0),
                name_table=entry_data.get("name_table", 0),
                size_large=entry_data.get("size_large", False),
                tiles=tiles,
            )
            entries.append(entry)

        # Parse palettes
        palettes: dict[int, list[int]] = {}
        palettes_data = data.get("palettes", {})
        for pal_key, colors in palettes_data.items():
            try:
                pal_idx = int(pal_key)
                palettes[pal_idx] = list(colors)
            except (ValueError, TypeError):
                logger.warning(f"Invalid palette key: {pal_key}")

        result = CaptureResult(
            frame=data.get("frame", 0),
            visible_count=data.get("visible_count", len(entries)),
            obsel=obsel,
            entries=entries,
            palettes=palettes,
            timestamp=data.get("timestamp", 0),
        )

        logger.info(
            f"Parsed capture: {result.visible_count} visible sprites, "
            f"{len(palettes)} palettes"
        )

        return result
