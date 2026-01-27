"""Compression strategies for tile injection.

Encapsulates HAL vs RAW compression behavior differences:
- Tile count detection
- Padding behavior
- Grid positioning
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, override

from core.types import CompressionType
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.rom_injector import ROMInjector
    from core.services.rom_staging_manager import ROMStagingManager

logger = get_logger(__name__)


class CompressionStrategy(ABC):
    """Base class for compression type strategies."""

    @abstractmethod
    def get_compression_type(self) -> CompressionType:
        """Return the compression type for this strategy."""
        ...

    @abstractmethod
    def should_pad_tiles(self) -> bool:
        """Whether to pad tile count to original for full VRAM overwrite."""
        ...

    @abstractmethod
    def get_grid_position(self, tile_idx: int | None, sequential_idx: int, grid_width: int) -> tuple[int, int]:
        """Calculate grid position (in pixels) for a tile.

        Args:
            tile_idx: The tile_index_in_block from capture (may be None)
            sequential_idx: Sequential index in sorted order
            grid_width: Width of the tile grid in tiles

        Returns:
            (grid_x, grid_y) position in pixels
        """
        ...

    @abstractmethod
    def detect_original_tile_count(
        self,
        rom_data: bytes,
        rom_offset: int,
        captured_tile_count: int,
        staging_manager: ROMStagingManager,
        rom_injector: ROMInjector,
    ) -> int:
        """Detect how many tiles exist at the ROM offset.

        Args:
            rom_data: Full ROM data
            rom_offset: Offset to check
            captured_tile_count: Number of tiles captured (fallback)
            staging_manager: For RAW slot detection
            rom_injector: For HAL decompression

        Returns:
            Number of tiles at offset
        """
        ...


class HALCompressionStrategy(CompressionStrategy):
    """Strategy for HAL-compressed sprite blocks.

    HAL compression stores multiple tiles in a single compressed block.
    All tiles share one ROM offset, and tile_index_in_block indicates
    position within the decompressed data.

    Key behaviors:
    - Pads to original tile count to fully clear VRAM
    - Uses tile_index_in_block for grid positioning
    - Decompresses to detect original tile count
    """

    @override
    def get_compression_type(self) -> CompressionType:
        return CompressionType.HAL

    @override
    def should_pad_tiles(self) -> bool:
        return True

    @override
    def get_grid_position(self, tile_idx: int | None, sequential_idx: int, grid_width: int) -> tuple[int, int]:
        """Use tile_index_in_block for positioning within decompressed block."""
        if tile_idx is not None:
            grid_x = (tile_idx % grid_width) * 8
            grid_y = (tile_idx // grid_width) * 8
        else:
            # Fallback to sequential if no tile index
            grid_x = (sequential_idx % grid_width) * 8
            grid_y = (sequential_idx // grid_width) * 8
        return (grid_x, grid_y)

    @override
    def detect_original_tile_count(
        self,
        rom_data: bytes,
        rom_offset: int,
        captured_tile_count: int,
        staging_manager: ROMStagingManager,
        rom_injector: ROMInjector,
    ) -> int:
        """Decompress HAL block to count tiles."""
        try:
            _, original_data, _ = rom_injector.find_compressed_sprite(rom_data, rom_offset)
            original_tile_count = len(original_data) // 32
            if original_tile_count == 0:
                original_tile_count = captured_tile_count
        except Exception:
            original_tile_count = captured_tile_count

        logger.info(
            "ROM offset 0x%X: Using HAL (%d tiles in block)",
            rom_offset,
            original_tile_count,
        )
        return original_tile_count


class RawCompressionStrategy(CompressionStrategy):
    """Strategy for raw (uncompressed) sprite tiles.

    RAW tiles are stored without compression. Each tile has its own
    ROM offset, so tile_index_in_block is irrelevant.

    Key behaviors:
    - No padding (would overwrite adjacent tiles)
    - Uses sequential index for grid positioning
    - Detects slot boundaries for tile count
    """

    @override
    def get_compression_type(self) -> CompressionType:
        return CompressionType.RAW

    @override
    def should_pad_tiles(self) -> bool:
        return False

    @override
    def get_grid_position(self, tile_idx: int | None, sequential_idx: int, grid_width: int) -> tuple[int, int]:
        """Use sequential index (each tile at its own ROM offset)."""
        grid_x = (sequential_idx % grid_width) * 8
        grid_y = (sequential_idx // grid_width) * 8
        return (grid_x, grid_y)

    @override
    def detect_original_tile_count(
        self,
        rom_data: bytes,
        rom_offset: int,
        captured_tile_count: int,
        staging_manager: ROMStagingManager,
        rom_injector: ROMInjector,
    ) -> int:
        """Detect RAW slot size from ROM boundaries."""
        detected_slot_size = staging_manager.detect_raw_slot_size(rom_data, rom_offset)
        if detected_slot_size is not None:
            logger.info(
                "ROM offset 0x%X: Using RAW (detected slot: %d tiles)",
                rom_offset,
                detected_slot_size,
            )
            return detected_slot_size
        else:
            logger.info(
                "ROM offset 0x%X: Using RAW (no boundary, using captured: %d tiles)",
                rom_offset,
                captured_tile_count,
            )
            return captured_tile_count


def get_compression_strategy(is_raw: bool) -> CompressionStrategy:
    """Factory function to get the appropriate compression strategy.

    Args:
        is_raw: True for RAW compression, False for HAL

    Returns:
        Appropriate CompressionStrategy instance
    """
    if is_raw:
        return RawCompressionStrategy()
    return HALCompressionStrategy()
