"""
Grid-based arrangement state management for flexible sprite organization
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import override

from PySide6.QtCore import QObject, Signal


class ArrangementType(Enum):
    """Types of tile arrangements"""

    ROW = "row"
    COLUMN = "column"
    TILE = "tile"
    GROUP = "group"

@dataclass
class TilePosition:
    """Represents a tile's position in the grid"""

    row: int
    col: int

    @override
    def __hash__(self) -> int:
        return hash((self.row, self.col))

    @override
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, TilePosition)
            and self.row == other.row
            and self.col == other.col
        )

@dataclass
class TileGroup:
    """Represents a group of tiles that should stay together"""

    id: str
    tiles: list[TilePosition]
    width: int  # Group width in tiles
    height: int  # Group height in tiles
    name: str | None = None

class GridArrangementManager(QObject):
    """Manages grid-based sprite tile arrangements with support for rows, columns, and custom groups"""

    # Signals
    arrangement_changed = Signal()
    tile_added = Signal(object)  # TilePosition
    tile_removed = Signal(object)  # TilePosition
    group_added = Signal(str)  # Group ID
    group_removed = Signal(str)  # Group ID
    arrangement_cleared = Signal()

    def __init__(self, total_rows: int, total_cols: int):
        super().__init__()
        # Validate grid dimensions
        if total_rows <= 0 or total_cols <= 0:
            raise ValueError(f"Invalid grid dimensions: {total_rows}x{total_cols}")

        self.total_rows = total_rows
        self.total_cols = total_cols

        # Track arranged tiles
        self._arranged_tiles: list[TilePosition] = []
        self._tile_set: set[TilePosition] = set()  # For fast lookup

        # Track groups
        self._groups: dict[str, TileGroup] = {}
        self._tile_to_group: dict[TilePosition, str] = {}  # Map tiles to their group

        # Arrangement order tracking
        self._arrangement_order: list[tuple[ArrangementType, str]] = []

    def add_tile(self, position: TilePosition) -> bool:
        """Add a single tile to the arrangement"""
        # Validate tile position
        if not self._is_valid_position(position):
            return False

        if position in self._tile_set or position in self._tile_to_group:
            return False

        self._arranged_tiles.append(position)
        self._tile_set.add(position)
        self._arrangement_order.append(
            (ArrangementType.TILE, f"{position.row},{position.col}")
        )

        self.tile_added.emit(position)
        self.arrangement_changed.emit()
        return True

    def remove_tile(self, position: TilePosition) -> bool:
        """Remove a single tile from the arrangement"""
        # Check if tile is part of a group
        if position in self._tile_to_group:
            # Must remove entire group
            group_id = self._tile_to_group[position]
            return self.remove_group(group_id)

        if position not in self._tile_set:
            return False

        self._arranged_tiles.remove(position)
        self._tile_set.remove(position)

        # Remove from arrangement order
        tile_key = f"{position.row},{position.col}"
        self._arrangement_order = [
            (t, k)
            for t, k in self._arrangement_order
            if not (t == ArrangementType.TILE and k == tile_key)
        ]

        self.tile_removed.emit(position)
        self.arrangement_changed.emit()
        return True

    def add_row(self, row_index: int) -> bool:
        """Add an entire row to the arrangement"""
        # Validate row index
        if row_index < 0 or row_index >= self.total_rows:
            return False

        tiles = [TilePosition(row_index, col) for col in range(self.total_cols)]

        # Add tiles that aren't already arranged (allow overlaps)
        tiles_added = 0
        for tile in tiles:
            if tile not in self._tile_set and tile not in self._tile_to_group:
                self._arranged_tiles.append(tile)
                self._tile_set.add(tile)
                tiles_added += 1

        # Always track the row operation, even if some tiles were already arranged
        self._arrangement_order.append((ArrangementType.ROW, str(row_index)))
        self.arrangement_changed.emit()
        return True

    def add_column(self, col_index: int) -> bool:
        """Add an entire column to the arrangement"""
        # Validate column index
        if col_index < 0 or col_index >= self.total_cols:
            return False

        tiles = [TilePosition(row, col_index) for row in range(self.total_rows)]

        # Add tiles that aren't already arranged (allow overlaps)
        tiles_added = 0
        for tile in tiles:
            if tile not in self._tile_set and tile not in self._tile_to_group:
                self._arranged_tiles.append(tile)
                self._tile_set.add(tile)
                tiles_added += 1

        # Always track the column operation, even if some tiles were already arranged
        self._arrangement_order.append((ArrangementType.COLUMN, str(col_index)))
        self.arrangement_changed.emit()
        return True

    def add_group(self, group: TileGroup) -> bool:
        """Add a custom group of tiles"""
        # Check if any tile in the group is already arranged
        for tile in group.tiles:
            if tile in self._tile_set or tile in self._tile_to_group:
                return False

        # Add group
        self._groups[group.id] = group

        # Add tiles to arrangement
        for tile in group.tiles:
            self._arranged_tiles.append(tile)
            self._tile_set.add(tile)
            self._tile_to_group[tile] = group.id

        self._arrangement_order.append((ArrangementType.GROUP, group.id))
        self.group_added.emit(group.id)
        self.arrangement_changed.emit()
        return True

    def remove_row(self, row_index: int) -> bool:
        """Remove an entire row from the arrangement"""
        tiles_to_remove = [
            TilePosition(row_index, col) for col in range(self.total_cols)
        ]
        removed_count = 0

        # Remove tiles that aren't part of groups
        for tile in tiles_to_remove:
            if tile in self._tile_set and tile not in self._tile_to_group:
                self._arranged_tiles.remove(tile)
                self._tile_set.remove(tile)
                removed_count += 1

        if removed_count > 0:
            # Remove from arrangement order
            self._arrangement_order = [
                (t, k)
                for t, k in self._arrangement_order
                if not (t == ArrangementType.ROW and k == str(row_index))
            ]
            self.arrangement_changed.emit()
            return True

        return False

    def remove_column(self, col_index: int) -> bool:
        """Remove an entire column from the arrangement"""
        tiles_to_remove = [
            TilePosition(row, col_index) for row in range(self.total_rows)
        ]
        removed_count = 0

        # Remove tiles that aren't part of groups
        for tile in tiles_to_remove:
            if tile in self._tile_set and tile not in self._tile_to_group:
                self._arranged_tiles.remove(tile)
                self._tile_set.remove(tile)
                removed_count += 1

        if removed_count > 0:
            # Remove from arrangement order
            self._arrangement_order = [
                (t, k)
                for t, k in self._arrangement_order
                if not (t == ArrangementType.COLUMN and k == str(col_index))
            ]
            self.arrangement_changed.emit()
            return True

        return False

    def remove_group(self, group_id: str) -> bool:
        """Remove a group and all its tiles"""
        if group_id not in self._groups:
            return False

        group = self._groups[group_id]

        # Remove all tiles in the group
        for tile in group.tiles:
            self._arranged_tiles.remove(tile)
            self._tile_set.remove(tile)
            del self._tile_to_group[tile]

        # Remove group
        del self._groups[group_id]

        # Remove from arrangement order
        self._arrangement_order = [
            (t, k)
            for t, k in self._arrangement_order
            if not (t == ArrangementType.GROUP and k == group_id)
        ]

        self.group_removed.emit(group_id)
        self.arrangement_changed.emit()
        return True

    def create_group_from_selection(
        self, tiles: list[TilePosition], group_id: str, name: str | None = None
    ) -> TileGroup | None:
        """Create a group from a selection of tiles"""
        if not tiles:
            return None

        # Check if any tile is already arranged
        for tile in tiles:
            if tile in self._tile_set or tile in self._tile_to_group:
                return None

        # Calculate bounding box
        min_row = min(t.row for t in tiles)
        max_row = max(t.row for t in tiles)
        min_col = min(t.col for t in tiles)
        max_col = max(t.col for t in tiles)

        width = max_col - min_col + 1
        height = max_row - min_row + 1

        # Create group
        group = TileGroup(
            id=group_id, tiles=tiles, width=width, height=height, name=name
        )

        if self.add_group(group):
            return group
        return None

    def reorder_arrangement(self, new_order: list[tuple[ArrangementType, str]]) -> None:
        """Reorder the arrangement based on new order specification"""
        # Validate that all current items are in new order
        current_keys = set(self._arrangement_order)
        new_keys = set(new_order)

        if current_keys != new_keys:
            raise ValueError("New order must contain all current arrangement items")

        self._arrangement_order = new_order.copy()
        self.arrangement_changed.emit()

    def clear(self) -> None:
        """Clear all arrangements"""
        if self._arranged_tiles:
            self._arranged_tiles.clear()
        if self._tile_set:
            self._tile_set.clear()
        if self._groups:
            self._groups.clear()
        if self._tile_to_group:
            self._tile_to_group.clear()
        if self._arrangement_order:
            self._arrangement_order.clear()

        self.arrangement_cleared.emit()
        self.arrangement_changed.emit()

    def get_arranged_tiles(self) -> list[TilePosition]:
        """Get list of all arranged tiles in order"""
        return self._arranged_tiles.copy()

    def get_arrangement_order(self) -> list[tuple[ArrangementType, str]]:
        """Get the arrangement order for reconstruction"""
        return self._arrangement_order.copy()

    def get_groups(self) -> dict[str, TileGroup]:
        """Get all defined groups"""
        return self._groups.copy()

    def is_tile_arranged(self, position: TilePosition) -> bool:
        """Check if a tile is arranged"""
        return position in self._tile_set or position in self._tile_to_group

    def get_tile_group(self, position: TilePosition) -> str | None:
        """Get the group ID a tile belongs to, if any"""
        return self._tile_to_group.get(position)

    def get_arranged_count(self) -> int:
        """Get total number of arranged tiles"""
        return len(self._arranged_tiles)

    def get_row_tiles(self, row_index: int) -> list[TilePosition]:
        """Get all tiles in a specific row"""
        return [TilePosition(row_index, col) for col in range(self.total_cols)]

    def get_column_tiles(self, col_index: int) -> list[TilePosition]:
        """Get all tiles in a specific column"""
        return [TilePosition(row, col_index) for row in range(self.total_rows)]

    def is_row_fully_arranged(self, row_index: int) -> bool:
        """Check if all tiles in a row are arranged"""
        row_tiles = self.get_row_tiles(row_index)
        return all(self.is_tile_arranged(tile) for tile in row_tiles)

    def is_column_fully_arranged(self, col_index: int) -> bool:
        """Check if all tiles in a column are arranged"""
        col_tiles = self.get_column_tiles(col_index)
        return all(self.is_tile_arranged(tile) for tile in col_tiles)

    def _is_valid_position(self, position: TilePosition) -> bool:
        """Check if a tile position is within grid bounds"""
        return (
            0 <= position.row < self.total_rows and 0 <= position.col < self.total_cols
        )
