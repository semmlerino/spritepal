"""
Parser for Mesen 2 sprite capture JSON files.

Parses the sprite_capture.json output from mesen2_sprite_capture.lua
into typed Python dataclasses for use in extraction pipeline.

Validation is performed at parse time to catch malformed data early:
- Coordinate bounds: X ∈ [-256, 255] (signed 9-bit), Y ∈ [0, 255] (unsigned 8-bit)
- Palette index: ∈ [0, 7] (SNES OBJ uses palettes 0-7)
- Tile hex length: exactly 64 chars (32 bytes of 4bpp data)
- VRAM address: ∈ [0, 0xFFFF] (64KB byte-addressed VRAM)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.logging_config import get_logger

logger = get_logger(__name__)


# Validation constants for SNES hardware limits
MIN_OAM_X = -256  # Signed 9-bit coordinate (allows off-screen left)
MAX_OAM_X = 255
MIN_OAM_Y = 0  # Unsigned 8-bit coordinate
MAX_OAM_Y = 255
MIN_PALETTE = 0
MAX_PALETTE = 7  # OBJ uses palettes 0-7
MIN_VRAM_ADDR = 0
MAX_VRAM_ADDR = 0xFFFF  # 64KB byte-addressed
TILE_HEX_LENGTH = 64  # 32 bytes = 64 hex chars
HEX_PATTERN = re.compile(r"^[0-9A-Fa-f]+$")


class CaptureValidationError(ValueError):
    """Raised when capture data fails validation."""

    pass


@dataclass
class TileData:
    """VRAM tile data from capture."""

    tile_index: int
    vram_addr: int
    pos_x: int  # Position within sprite (0, 1, 2...)
    pos_y: int
    data_hex: str  # 64 hex chars = 32 bytes of 4bpp tile data
    rom_offset: int | None = None  # ROM file offset from VRAM attribution
    tile_index_in_block: int | None = None  # Position within compressed ROM block

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
    rom_offset: int | None = None
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
    oam_base_addr: int
    oam_addr_offset: int


@dataclass(frozen=True)
class CaptureBoundingBox:
    """Bounding box for all entries in a capture."""

    x: int
    y: int
    width: int
    height: int


@dataclass
class CaptureResult:
    """Complete capture result from Mesen 2 Lua script."""

    frame: int
    visible_count: int
    obsel: OBSELConfig
    entries: list[OAMEntry]
    palettes: dict[int, list[int | list[int]]]  # palette_index -> 16 colors (SNES int or RGB triplet)
    timestamp: int = 0

    @property
    def has_entries(self) -> bool:
        """Check if any entries were captured."""
        return len(self.entries) > 0

    @property
    def oam_entries(self) -> list[OAMEntry]:
        """Compatibility alias for sprite reassembly code."""
        return self.entries

    @property
    def bounding_box(self) -> CaptureBoundingBox:
        """Calculate bounding box for all entries."""
        if not self.entries:
            return CaptureBoundingBox(0, 0, 0, 0)

        min_x = min(entry.x for entry in self.entries)
        min_y = min(entry.y for entry in self.entries)
        max_x = max(entry.x + entry.width for entry in self.entries)
        max_y = max(entry.y + entry.height for entry in self.entries)
        return CaptureBoundingBox(min_x, min_y, max_x - min_x, max_y - min_y)

    @property
    def unique_rom_offsets(self) -> list[int]:
        """Get unique ROM offsets referenced by the capture."""
        offsets = {entry.rom_offset for entry in self.entries if entry.rom_offset is not None}
        return sorted(offsets)

    def get_entries_for_rom_offset(self, rom_offset: int) -> list[OAMEntry]:
        """Filter entries by ROM offset."""
        return [entry for entry in self.entries if entry.rom_offset == rom_offset]

    def get_entries_by_palette(self, palette: int) -> list[OAMEntry]:
        """Get all OAM entries using a specific palette."""
        return [e for e in self.entries if e.palette == palette]

    def get_entries_in_region(self, x: int, y: int, width: int, height: int) -> list[OAMEntry]:
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

        Also looks for vram_attribution.json alongside the capture to enrich
        tiles with ROM offsets from sprite_rom_finder.lua's attribution tracking.

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

        result = self._parse_capture_data(data)

        # Try to enrich tiles with ROM offsets from VRAM attribution
        self._enrich_with_vram_attribution(result, path)

        return result

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
        """Parse raw JSON dict into CaptureResult.

        Validates all data at parse time to catch malformed captures early.
        Raises CaptureValidationError for invalid data.
        """
        # Parse OBSEL config
        obsel_data = data.get("obsel", {})
        obsel = OBSELConfig(
            raw=obsel_data.get("raw", 0),
            name_base=obsel_data.get("name_base", 0),
            name_select=obsel_data.get("name_select", 0),
            size_select=obsel_data.get("size_select", 0),
            tile_base_addr=obsel_data.get("tile_base_addr", 0),
            oam_base_addr=obsel_data.get("oam_base_addr", 0),
            oam_addr_offset=obsel_data.get("oam_addr_offset", 0),
        )

        # Parse OAM entries with validation
        entries = []
        for entry_idx, entry_data in enumerate(data.get("entries", [])):
            entry_id = entry_data.get("id", entry_idx)

            # Parse and validate tile data
            tiles = []
            for tile_idx, tile_data in enumerate(entry_data.get("tiles", [])):
                # Validate tile hex data
                data_hex = tile_data.get("data_hex", "")
                if data_hex:  # Only validate non-empty tiles
                    if len(data_hex) != TILE_HEX_LENGTH:
                        raise CaptureValidationError(
                            f"Entry {entry_id}, tile {tile_idx}: data_hex must be exactly "
                            f"{TILE_HEX_LENGTH} chars (32 bytes), got {len(data_hex)}"
                        )
                    if not HEX_PATTERN.match(data_hex):
                        raise CaptureValidationError(
                            f"Entry {entry_id}, tile {tile_idx}: data_hex contains "
                            f"invalid characters (must be hex: 0-9, A-F)"
                        )

                # Validate VRAM address
                vram_addr = tile_data.get("vram_addr", 0)
                if not (MIN_VRAM_ADDR <= vram_addr <= MAX_VRAM_ADDR):
                    raise CaptureValidationError(
                        f"Entry {entry_id}, tile {tile_idx}: vram_addr={vram_addr:#x} "
                        f"out of range [0x{MIN_VRAM_ADDR:04X}, 0x{MAX_VRAM_ADDR:04X}]"
                    )

                # Parse tile ROM offset if present in JSON
                tile_rom_offset_raw = tile_data.get("rom_offset")
                if tile_rom_offset_raw is not None:
                    try:
                        tile_rom_offset: int | None = int(tile_rom_offset_raw)
                    except (TypeError, ValueError):
                        tile_rom_offset = None
                else:
                    tile_rom_offset = None

                # Parse tile index within block if present
                tile_idx_in_block_raw = tile_data.get("tile_index_in_block")
                if tile_idx_in_block_raw is not None:
                    try:
                        tile_idx_in_block: int | None = int(tile_idx_in_block_raw)
                    except (TypeError, ValueError):
                        tile_idx_in_block = None
                else:
                    tile_idx_in_block = None

                tile = TileData(
                    tile_index=tile_data.get("tile_index", 0),
                    vram_addr=vram_addr,
                    pos_x=tile_data.get("pos_x", 0),
                    pos_y=tile_data.get("pos_y", 0),
                    data_hex=data_hex,
                    rom_offset=tile_rom_offset,
                    tile_index_in_block=tile_idx_in_block,
                )
                tiles.append(tile)

            # Validate OAM entry coordinates
            x = entry_data.get("x", 0)
            y = entry_data.get("y", 0)
            if not (MIN_OAM_X <= x <= MAX_OAM_X):
                raise CaptureValidationError(f"Entry {entry_id}: x={x} out of range [{MIN_OAM_X}, {MAX_OAM_X}]")
            if not (MIN_OAM_Y <= y <= MAX_OAM_Y):
                raise CaptureValidationError(f"Entry {entry_id}: y={y} out of range [{MIN_OAM_Y}, {MAX_OAM_Y}]")

            # Validate palette index
            palette = entry_data.get("palette", 0)
            if not (MIN_PALETTE <= palette <= MAX_PALETTE):
                raise CaptureValidationError(
                    f"Entry {entry_id}: palette={palette} out of range [{MIN_PALETTE}, {MAX_PALETTE}]"
                )

            # Validate tile count vs dimensions
            width = entry_data.get("width", 8)
            height = entry_data.get("height", 8)
            expected_tiles = (width // 8) * (height // 8)
            if tiles and len(tiles) != expected_tiles:
                # Log warning but don't fail - some captures have incomplete tile data
                logger.warning(
                    f"Entry {entry_id}: tile count mismatch - expected {expected_tiles} "
                    f"tiles for {width}x{height} sprite, got {len(tiles)}"
                )

            tile_page = entry_data.get("tile_page")
            name_table = tile_page if tile_page is not None else entry_data.get("name_table", 0)
            rom_offset_raw = entry_data.get("rom_offset")
            if rom_offset_raw is None:
                rom_offset = None
            else:
                try:
                    rom_offset = int(rom_offset_raw)
                except (TypeError, ValueError):
                    logger.warning("Invalid rom_offset value for entry %s: %r", entry_id, rom_offset_raw)
                    rom_offset = None
            entry = OAMEntry(
                id=entry_id,
                x=x,
                y=y,
                tile=entry_data.get("tile", 0),
                width=width,
                height=height,
                flip_h=bool(entry_data.get("flip_h", False)),
                flip_v=bool(entry_data.get("flip_v", False)),
                palette=palette,
                rom_offset=rom_offset,
                priority=entry_data.get("priority", 0),
                name_table=name_table,
                size_large=entry_data.get("size_large", False),
                tiles=tiles,
            )
            entries.append(entry)

        # Parse palettes with validation
        palettes: dict[int, list[int | list[int]]] = {}
        palettes_data = data.get("palettes", {})
        for pal_key, colors in palettes_data.items():
            try:
                pal_idx = int(pal_key)
                if not (MIN_PALETTE <= pal_idx <= MAX_PALETTE):
                    logger.warning(f"Palette index {pal_idx} outside standard OBJ range [0-7]")
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

        logger.info(f"Parsed capture: {result.visible_count} visible sprites, {len(palettes)} palettes")

        return result

    def _enrich_with_vram_attribution(self, result: CaptureResult, capture_path: Path) -> None:
        """Enrich tiles with ROM offsets from VRAM attribution map.

        Looks for vram_attribution.json exported by sprite_rom_finder.lua (E key)
        and uses it to fill in rom_offset for each tile based on vram_addr.

        Args:
            result: The parsed CaptureResult to enrich
            capture_path: Path to the capture file (used to find attribution file)
        """
        from core.mesen_integration.vram_attribution import (
            find_attribution_file,
            load_vram_attribution,
        )

        # Find attribution file
        attr_path = find_attribution_file(capture_path)
        if attr_path is None:
            logger.debug("No VRAM attribution file found for %s", capture_path)
            return

        # Load attribution map
        attr_map = load_vram_attribution(attr_path)
        if attr_map is None:
            logger.warning("Failed to load VRAM attribution from %s", attr_path)
            return

        # Enrich each tile with its ROM offset
        tiles_enriched = 0
        tiles_total = 0
        for entry in result.entries:
            for tile in entry.tiles:
                tiles_total += 1
                if tile.rom_offset is not None:
                    # Already has offset (from capture JSON)
                    tiles_enriched += 1
                    continue

                # Look up ROM offset from attribution map
                rom_offset = attr_map.get_rom_offset(tile.vram_addr)
                if rom_offset is not None:
                    tile.rom_offset = rom_offset
                    tiles_enriched += 1

            # Also update entry-level rom_offset if not set
            # Use the first tile's ROM offset as the entry's offset
            if entry.rom_offset is None and entry.tiles:
                first_tile_offset = entry.tiles[0].rom_offset
                if first_tile_offset is not None:
                    entry.rom_offset = first_tile_offset

        if tiles_total > 0:
            logger.info(
                "VRAM attribution: enriched %d/%d tiles with ROM offsets from %s",
                tiles_enriched,
                tiles_total,
                attr_path.name,
            )
