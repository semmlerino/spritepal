"""ROM Map Importer - Load sprite tiles from ROM using a ROM map.

Loads tiles directly from ROM based on sprite_rom_mapper.py output,
preserving ROM offset information for reinjection.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class ROMTile:
    """A tile loaded from ROM with its address metadata."""

    vram_word: int  # VRAM word address
    rom_offset: int  # ROM file offset
    image: Image.Image  # 8x8 RGBA image
    row: int = 0  # Grid position row
    col: int = 0  # Grid position column


@dataclass
class ROMMapData:
    """Data loaded from a ROM map file."""

    frame_name: str
    palette_index: int
    vram_base: int
    tiles: list[ROMTile]
    palette: list[tuple[int, int, int, int]] | None = None  # RGBA colors

    # Lookup for quick access
    _by_vram: dict[int, ROMTile] = field(default_factory=dict, repr=False)
    _by_position: dict[tuple[int, int], ROMTile] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._build_lookups()

    def _build_lookups(self) -> None:
        """Build lookup dictionaries."""
        self._by_vram = {t.vram_word: t for t in self.tiles}
        self._by_position = {(t.row, t.col): t for t in self.tiles}

    def get_by_vram(self, vram_word: int) -> ROMTile | None:
        """Get tile by VRAM word address."""
        return self._by_vram.get(vram_word)

    def get_by_position(self, row: int, col: int) -> ROMTile | None:
        """Get tile by grid position."""
        return self._by_position.get((row, col))

    @property
    def width_tiles(self) -> int:
        """Width in tiles."""
        if not self.tiles:
            return 0
        return max(t.col for t in self.tiles) + 1

    @property
    def height_tiles(self) -> int:
        """Height in tiles."""
        if not self.tiles:
            return 0
        return max(t.row for t in self.tiles) + 1


def decode_4bpp_tile(
    tile_data: bytes,
    palette: list[tuple[int, int, int, int]] | None = None,
) -> Image.Image:
    """Decode 32-byte SNES 4bpp tile to 8x8 RGBA image.

    Args:
        tile_data: 32-byte 4bpp tile
        palette: Optional RGBA palette (16 colors). If None, uses grayscale.

    Returns:
        8x8 RGBA PIL Image
    """
    if palette is None:
        # Default grayscale palette
        palette = [(i * 17, i * 17, i * 17, 255 if i > 0 else 0) for i in range(16)]

    img = Image.new("RGBA", (8, 8))
    pixels = []

    for row in range(8):
        bp0 = tile_data[row * 2]
        bp1 = tile_data[row * 2 + 1]
        bp2 = tile_data[16 + row * 2]
        bp3 = tile_data[16 + row * 2 + 1]

        for col in range(8):
            bit = 7 - col
            pixel_idx = (
                ((bp0 >> bit) & 1) | (((bp1 >> bit) & 1) << 1) | (((bp2 >> bit) & 1) << 2) | (((bp3 >> bit) & 1) << 3)
            )
            pixels.append(palette[pixel_idx])

    img.putdata(pixels)
    return img


def parse_cgram_palette(
    cgram_data: bytes,
    palette_index: int,
) -> list[tuple[int, int, int, int]]:
    """Extract RGBA palette from CGRAM dump.

    Args:
        cgram_data: 512-byte CGRAM dump
        palette_index: Sprite palette 0-7

    Returns:
        List of 16 RGBA tuples
    """
    offset = 0x100 + (palette_index * 32)
    palette_data = cgram_data[offset : offset + 32]

    colors: list[tuple[int, int, int, int]] = []
    for i in range(0, 32, 2):
        bgr555 = palette_data[i] | (palette_data[i + 1] << 8)
        r = (bgr555 & 0x1F) << 3
        g = ((bgr555 >> 5) & 0x1F) << 3
        b = ((bgr555 >> 10) & 0x1F) << 3
        alpha = 0 if i == 0 else 255
        colors.append((r, g, b, alpha))

    return colors


def load_rom_map(
    rom_map_path: str | Path,
    rom_path: str | Path,
    cgram_path: str | Path | None = None,
    palette_index: int = 7,
) -> ROMMapData | None:
    """Load tiles from ROM using a ROM map.

    Args:
        rom_map_path: Path to ROM map JSON (from sprite_rom_mapper.py)
        rom_path: Path to ROM file
        cgram_path: Optional path to CGRAM dump for palette
        palette_index: Palette index to use (default 7)

    Returns:
        ROMMapData with loaded tiles, or None on error
    """
    rom_map_path = Path(rom_map_path)
    rom_path = Path(rom_path)

    if not rom_map_path.exists():
        logger.error(f"ROM map not found: {rom_map_path}")
        return None

    if not rom_path.exists():
        logger.error(f"ROM not found: {rom_path}")
        return None

    # Load ROM map
    try:
        with open(rom_map_path) as f:
            rom_map = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load ROM map: {e}")
        return None

    # Load ROM
    try:
        rom_data = rom_path.read_bytes()
    except OSError as e:
        logger.error(f"Failed to load ROM: {e}")
        return None

    # Load palette
    palette: list[tuple[int, int, int, int]] | None = None
    if cgram_path:
        cgram_path = Path(cgram_path)
        if cgram_path.exists():
            try:
                cgram_data = cgram_path.read_bytes()
                palette = parse_cgram_palette(cgram_data, palette_index)
                logger.info(f"Loaded palette {palette_index} from {cgram_path.name}")
            except OSError as e:
                logger.warning(f"Failed to load CGRAM: {e}")

    # Extract tiles
    tiles: list[ROMTile] = []
    mappings = rom_map.get("mappings", [])

    # Calculate grid positions from VRAM addresses
    vram_base = rom_map.get("vram_base", 0x6000)

    # Build position map: sort by VRAM address to get consistent ordering
    sorted_mappings = sorted(mappings, key=lambda m: m.get("vram_word", 0))

    # Calculate grid layout (8 tiles per row by default)
    grid_cols = 8
    for i, mapping in enumerate(sorted_mappings):
        vram_word = mapping.get("vram_word")
        rom_offset = mapping.get("rom_offset")

        if vram_word is None or rom_offset is None:
            continue

        # Read tile data from ROM
        if rom_offset + 32 > len(rom_data):
            logger.warning(f"Tile at 0x{rom_offset:06X} extends past ROM end")
            continue

        tile_data = rom_data[rom_offset : rom_offset + 32]
        tile_img = decode_4bpp_tile(tile_data, palette)

        # Calculate grid position
        row = i // grid_cols
        col = i % grid_cols

        tiles.append(
            ROMTile(
                vram_word=vram_word,
                rom_offset=rom_offset,
                image=tile_img,
                row=row,
                col=col,
            )
        )

    if not tiles:
        logger.error("No tiles loaded from ROM map")
        return None

    logger.info(f"Loaded {len(tiles)} tiles from ROM using map {rom_map_path.name}")

    return ROMMapData(
        frame_name=rom_map.get("frame_name", "unknown"),
        palette_index=rom_map.get("palette", palette_index),
        vram_base=vram_base,
        tiles=tiles,
        palette=palette,
    )


def get_modified_tiles(
    original_data: ROMMapData,
    current_tiles: dict[tuple[int, int], Image.Image],
) -> dict[int, Image.Image]:
    """Compare current tiles to originals and return modified ones.

    Args:
        original_data: Original ROMMapData
        current_tiles: Dict of (row, col) -> current tile image

    Returns:
        Dict of vram_word -> modified tile image
    """
    modified: dict[int, Image.Image] = {}

    for (row, col), current_img in current_tiles.items():
        original_tile = original_data.get_by_position(row, col)
        if original_tile is None:
            continue

        # Simple comparison: check if images differ
        # (In practice, you might want more sophisticated comparison)
        if current_img.tobytes() != original_tile.image.tobytes():
            modified[original_tile.vram_word] = current_img

    return modified
