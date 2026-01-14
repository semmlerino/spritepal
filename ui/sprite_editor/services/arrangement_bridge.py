"""Bridge between grid arrangement system and sprite editing workflow.

Provides bidirectional mapping between arranged (logical) and original (physical)
tile layouts, enabling editing in a contiguous view while preserving original
tile positions for ROM injection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition

if TYPE_CHECKING:
    from ui.row_arrangement.grid_arrangement_manager import GridArrangementManager
    from ui.row_arrangement.grid_image_processor import GridImageProcessor


@dataclass
class TileMapping:
    """Maps a logical tile position to a physical tile position."""

    logical_pos: TilePosition  # Position in arranged/editing view
    physical_pos: TilePosition  # Position in original ROM layout
    tile_index: int  # Linear index in original tile data


class ArrangementBridge:
    """Bidirectional mapping between arranged and original tile layouts.

    Use case: Kirby sprites have tiles scattered in ROM memory. User wants
    to view/edit them in a contiguous layout, then restore original positions
    for ROM injection.
    """

    def __init__(
        self,
        manager: GridArrangementManager,
        processor: GridImageProcessor,
        logical_width: int | None = None,
    ) -> None:
        """Initialize bridge with arrangement state.

        Args:
            manager: Grid arrangement manager with arrangement defined
            processor: Grid image processor with tile data
            logical_width: Desired tiles per row in logical view. If None, calculated
                from arranged tile count (max 16). Pass the dialog's width_spin value
                to preserve the user's intended layout width.
        """
        self._manager = manager
        self._processor = processor
        self._mappings: list[TileMapping] = []
        self._provided_logical_width = logical_width  # User-specified width
        self._logical_width: int = 0  # Tiles per row in logical view
        self._logical_height: int = 0  # Rows in logical view
        self._physical_width: int = processor.grid_cols
        self._physical_height: int = processor.grid_rows

        # Use tile dimensions from processor for dynamic layout support
        self._tile_width: int = processor.tile_width if processor.tile_width > 0 else 8
        self._tile_height: int = processor.tile_height if processor.tile_height > 0 else 8

        # Build mapping from current arrangement
        self._build_mapping()

    def _build_mapping(self) -> None:
        """Build logical→physical tile position mapping from arrangement.

        Prefers spatial mapping (respecting canvas gaps) if grid_mapping is available,
        otherwise falls back to linear mapping (compact layout).
        """
        grid_mapping = self._manager.get_grid_mapping()
        if grid_mapping:
            self._build_spatial_mapping(grid_mapping)
        else:
            self._build_linear_mapping()

    def _build_spatial_mapping(self, grid_mapping: dict[tuple[int, int], tuple[ArrangementType, str]]) -> None:
        """Build mapping that preserves spatial layout including gaps."""
        expanded_tiles: list[tuple[int, int, TilePosition]] = []

        for (r, c), (arr_type, key) in grid_mapping.items():
            if arr_type == ArrangementType.TILE:
                try:
                    row_phys, col_phys = map(int, key.split(","))
                    expanded_tiles.append((r, c, TilePosition(row_phys, col_phys)))
                except (ValueError, IndexError):
                    continue
            elif arr_type == ArrangementType.ROW:
                try:
                    row_idx = int(key)
                    for col_phys in range(self._processor.grid_cols):
                        expanded_tiles.append((r, c + col_phys, TilePosition(row_idx, col_phys)))
                except (ValueError, IndexError):
                    continue
            elif arr_type == ArrangementType.COLUMN:
                try:
                    col_idx = int(key)
                    for row_phys in range(self._processor.grid_rows):
                        expanded_tiles.append((r + row_phys, c, TilePosition(row_phys, col_idx)))
                except (ValueError, IndexError):
                    continue
            elif arr_type == ArrangementType.GROUP:
                group = self._manager.get_groups().get(key)
                if group and group.tiles:
                    # Find relative bounding box for group tiles
                    min_row = min(p.row for p in group.tiles)
                    min_col = min(p.col for p in group.tiles)
                    for p in group.tiles:
                        dr = p.row - min_row
                        dc = p.col - min_col
                        expanded_tiles.append((r + dr, c + dc, p))

        if not expanded_tiles:
            return

        # Find bounds of expanded tiles
        max_r = max(t[0] for t in expanded_tiles)
        max_c = max(t[1] for t in expanded_tiles)

        # Set logical dimensions
        if self._provided_logical_width is not None and self._provided_logical_width > 0:
            self._logical_width = max(self._provided_logical_width, max_c + 1)
        else:
            self._logical_width = max_c + 1
        self._logical_height = max_r + 1

        # Create mappings
        for lr, lc, physical_pos in expanded_tiles:
            logical_pos = TilePosition(lr, lc)
            # Calculate linear tile index in physical ROM layout
            tile_index = physical_pos.row * self._physical_width + physical_pos.col

            self._mappings.append(
                TileMapping(
                    logical_pos=logical_pos,
                    physical_pos=physical_pos,
                    tile_index=tile_index,
                )
            )

    def _build_linear_mapping(self) -> None:
        """Fallback for older versions: Build compact mapping from arrangement order."""
        arrangement_order = self._manager.get_arrangement_order()
        if not arrangement_order:
            return

        # Collect all physical positions in arrangement order
        physical_positions: list[TilePosition] = []

        for arr_type, key in arrangement_order:
            if arr_type == ArrangementType.TILE:
                try:
                    row, col = map(int, key.split(","))
                    physical_positions.append(TilePosition(row, col))
                except (ValueError, IndexError):
                    continue

            elif arr_type == ArrangementType.ROW:
                try:
                    row_index = int(key)
                    for col in range(self._processor.grid_cols):
                        physical_positions.append(TilePosition(row_index, col))
                except (ValueError, IndexError):
                    continue

            elif arr_type == ArrangementType.COLUMN:
                try:
                    col_index = int(key)
                    for row in range(self._processor.grid_rows):
                        physical_positions.append(TilePosition(row, col_index))
                except (ValueError, IndexError):
                    continue

            elif arr_type == ArrangementType.GROUP:
                group = self._manager.get_groups().get(key)
                if group:
                    physical_positions.extend(group.tiles)

        if not physical_positions:
            return

        # Calculate logical dimensions
        # Use provided width if available, otherwise calculate from tile count
        if self._provided_logical_width is not None and self._provided_logical_width > 0:
            self._logical_width = self._provided_logical_width
        else:
            # Fallback: use min of 16 or arranged tile count
            self._logical_width = min(16, len(physical_positions))
        self._logical_height = (len(physical_positions) + self._logical_width - 1) // self._logical_width

        # Create mappings
        for i, physical_pos in enumerate(physical_positions):
            logical_row = i // self._logical_width
            logical_col = i % self._logical_width
            logical_pos = TilePosition(logical_row, logical_col)

            # Calculate linear tile index
            tile_index = physical_pos.row * self._physical_width + physical_pos.col

            self._mappings.append(
                TileMapping(
                    logical_pos=logical_pos,
                    physical_pos=physical_pos,
                    tile_index=tile_index,
                )
            )

    @property
    def has_arrangement(self) -> bool:
        """Check if a valid arrangement exists."""
        return len(self._mappings) > 0

    @property
    def logical_size(self) -> tuple[int, int]:
        """Get logical image size in pixels (width, height)."""
        return (
            self._logical_width * self._tile_width,
            self._logical_height * self._tile_height,
        )

    @property
    def physical_size(self) -> tuple[int, int]:
        """Get physical image size in pixels (width, height)."""
        return (
            self._physical_width * self._tile_width,
            self._physical_height * self._tile_height,
        )

    def physical_to_logical(self, physical_data: NDArray[np.uint8]) -> NDArray[np.uint8]:
        """Transform physical layout image to logical (arranged) layout.

        Args:
            physical_data: Image data in original physical layout (H, W)

        Returns:
            Image data rearranged into logical layout
        """
        if not self.has_arrangement:
            return physical_data.copy()

        logical_h = self._logical_height * self._tile_height
        logical_w = self._logical_width * self._tile_width
        logical_data = np.zeros((logical_h, logical_w), dtype=np.uint8)

        for mapping in self._mappings:
            # Source tile coordinates in physical image
            phys_y = mapping.physical_pos.row * self._tile_height
            phys_x = mapping.physical_pos.col * self._tile_width

            # Destination tile coordinates in logical image
            log_y = mapping.logical_pos.row * self._tile_height
            log_x = mapping.logical_pos.col * self._tile_width

            # Copy tile
            logical_data[log_y : log_y + self._tile_height, log_x : log_x + self._tile_width] = physical_data[
                phys_y : phys_y + self._tile_height, phys_x : phys_x + self._tile_width
            ]

        return logical_data

    def logical_to_physical(self, logical_data: NDArray[np.uint8]) -> NDArray[np.uint8]:
        """Transform logical (arranged) layout back to physical layout.

        Args:
            logical_data: Image data in logical arranged layout (H, W)

        Returns:
            Image data restored to original physical layout
        """
        if not self.has_arrangement:
            return logical_data.copy()

        phys_h = self._physical_height * self._tile_height
        phys_w = self._physical_width * self._tile_width
        physical_data = np.zeros((phys_h, phys_w), dtype=np.uint8)

        for mapping in self._mappings:
            # Source tile coordinates in logical image
            log_y = mapping.logical_pos.row * self._tile_height
            log_x = mapping.logical_pos.col * self._tile_width

            # Destination tile coordinates in physical image
            phys_y = mapping.physical_pos.row * self._tile_height
            phys_x = mapping.physical_pos.col * self._tile_width

            # Copy tile
            physical_data[phys_y : phys_y + self._tile_height, phys_x : phys_x + self._tile_width] = logical_data[
                log_y : log_y + self._tile_height, log_x : log_x + self._tile_width
            ]

        return physical_data

    def get_arranged_tiles(self) -> list[TileMapping]:
        """Get list of tile mappings in arrangement order."""
        return self._mappings.copy()

    def get_tile_indices(self) -> list[int]:
        """Get linear tile indices in arrangement order.

        Returns:
            List of tile indices for 4bpp byte extraction
        """
        return [m.tile_index for m in self._mappings]
