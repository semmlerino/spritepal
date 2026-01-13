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
        return isinstance(other, TilePosition) and self.row == other.row and self.col == other.col


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
    tile_added = Signal(TilePosition)
    tile_removed = Signal(TilePosition)
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

        # Arrangement order tracking (linear sequence for ROM)
        self._arrangement_order: list[tuple[ArrangementType, str]] = []

        # Grid-based placement mapping: (target_row, target_col) -> (ArrangementType, key)
        # This allows free placement and dragging in the arrangement grid
        self._grid_mapping: dict[tuple[int, int], tuple[ArrangementType, str]] = {}

    def set_item_at(self, target_row: int, target_col: int, arr_type: ArrangementType, key: str) -> bool:
        """Place an arrangement item at a specific grid position on the canvas.

        This handles the "free dragging" in the target grid.
        If another item is there, it will be replaced/moved.
        """
        # We don't strictly validate target bounds here as the canvas can be large,
        # but we might want to if we have a fixed-width constraint.
        pos = (target_row, target_col)

        # Update mapping
        self._grid_mapping[pos] = (arr_type, key)

        # Re-derive linear arrangement order from grid mapping
        self._derive_order_from_grid()

        self.arrangement_changed.emit()
        return True

    def remove_item_at(self, target_row: int, target_col: int) -> bool:
        """Remove whatever is at the target grid position."""
        pos = (target_row, target_col)
        if pos in self._grid_mapping:
            del self._grid_mapping[pos]
            self._derive_order_from_grid()
            self.arrangement_changed.emit()
            return True
        return False

    def move_grid_item(self, source_pos: tuple[int, int], target_pos: tuple[int, int]) -> bool:
        """Move an item from one grid slot to another."""
        if source_pos not in self._grid_mapping:
            return False

        item = self._grid_mapping.pop(source_pos)

        # If target has an item, we can swap or just overwrite. Overwrite for now.
        self._grid_mapping[target_pos] = item

        self._derive_order_from_grid()
        self.arrangement_changed.emit()
        return True

    def get_item_at(self, row: int, col: int) -> tuple[ArrangementType, str] | None:
        """Get the item at a specific grid position."""
        return self._grid_mapping.get((row, col))

    def get_grid_mapping(self) -> dict[tuple[int, int], tuple[ArrangementType, str]]:
        """Get copy of current grid mapping."""
        return self._grid_mapping.copy()

    def _derive_order_from_grid(self) -> None:
        """Re-derive the linear ROM order by scanning the grid (row-major)."""
        if not self._grid_mapping:
            self._arrangement_order = []
            self._rebuild_arranged_tiles()
            return

        # Find bounds of the grid mapping
        rows = [p[0] for p in self._grid_mapping.keys()]
        cols = [p[1] for p in self._grid_mapping.keys()]
        min_r, max_r = min(rows), max(rows)
        min_c, max_c = min(cols), max(cols)

        new_order: list[tuple[ArrangementType, str]] = []
        for r in range(min_r, max_r + 1):
            for c in range(min_c, max_c + 1):
                item = self._grid_mapping.get((r, c))
                if item:
                    new_order.append(item)

        self._arrangement_order = new_order
        self._rebuild_arranged_tiles()

    def add_tile(self, position: TilePosition) -> bool:
        """Add a single tile to the arrangement"""
        # Validate tile position
        if not self._is_valid_position(position):
            return False

        if position in self._tile_set or position in self._tile_to_group:
            return False

        # Find next available slot in grid mapping (simple append logic for non-drag adds)
        target_row = 0
        target_col = 0
        if self._grid_mapping:
            # For simplicity, we can't easily know "arrangement width" here,
            # so we just find the highest row/col and increment.
            # But usually add_tile is called by double-click.
            # Let's just find the first empty slot in row-major order.
            found = False
            # Assume a reasonable search width, or just append to end
            max_r = max(p[0] for p in self._grid_mapping.keys()) if self._grid_mapping else 0
            # We don't know the preferred width here, so let's just use the current grid_cols
            # from the source as a hint, or just 16.
            width_hint = 16
            
            for r in range(max_r + 2):
                for c in range(width_hint):
                    if (r, c) not in self._grid_mapping:
                        target_row, target_col = r, c
                        found = True
                        break
                if found: break
        
        item = (ArrangementType.TILE, f"{position.row},{position.col}")
        self._grid_mapping[(target_row, target_col)] = item
        self._derive_order_from_grid()

        self.tile_added.emit(position)
        self.arrangement_changed.emit()
        return True

    def insert_tile(self, position: TilePosition, index: int) -> bool:
        """Insert a single tile at a specific position in the arrangement.

        Args:
            position: The tile position to insert
            index: The index in the arrangement order to insert at

        Returns:
            True if tile was inserted, False if invalid or already arranged
        """
        if not self._is_valid_position(position):
            return False

        if position in self._tile_set or position in self._tile_to_group:
            return False

        self._tile_set.add(position)

        # Insert in arrangement order
        tile_key = f"{position.row},{position.col}"
        index = max(0, min(index, len(self._arrangement_order)))
        self._arrangement_order.insert(index, (ArrangementType.TILE, tile_key))

        # Rebuild flat list to match order
        self._rebuild_arranged_tiles()

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
            (t, k) for t, k in self._arrangement_order if not (t == ArrangementType.TILE and k == tile_key)
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
        tiles_to_remove = [TilePosition(row_index, col) for col in range(self.total_cols)]
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
                (t, k) for t, k in self._arrangement_order if not (t == ArrangementType.ROW and k == str(row_index))
            ]
            self.arrangement_changed.emit()
            return True

        return False

    def remove_column(self, col_index: int) -> bool:
        """Remove an entire column from the arrangement"""
        tiles_to_remove = [TilePosition(row, col_index) for row in range(self.total_rows)]
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
                (t, k) for t, k in self._arrangement_order if not (t == ArrangementType.COLUMN and k == str(col_index))
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
            (t, k) for t, k in self._arrangement_order if not (t == ArrangementType.GROUP and k == group_id)
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
        group = TileGroup(id=group_id, tiles=tiles, width=width, height=height, name=name)

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

    def move_item(self, old_index: int, new_index: int) -> bool:
        """Move an item from one position to another in the arrangement order.

        Args:
            old_index: Current index of the item
            new_index: New index for the item

        Returns:
            True if item was moved, False otherwise
        """
        if not (0 <= old_index < len(self._arrangement_order)):
            return False
        if not (0 <= new_index < len(self._arrangement_order)):
            return False

        if old_index == new_index:
            return True

        item = self._arrangement_order.pop(old_index)
        self._arrangement_order.insert(new_index, item)

        # Also update the _arranged_tiles list to match the new order
        # This is more complex because one order item (like a ROW) can expand to multiple tiles
        self._rebuild_arranged_tiles()

        self.arrangement_changed.emit()
        return True

    def _rebuild_arranged_tiles(self) -> None:
        """Rebuild the _arranged_tiles list from the _arrangement_order.

        This ensures the flat tile list matches the logical arrangement order.
        """
        new_tiles: list[TilePosition] = []

        for arr_type, key in self._arrangement_order:
            if arr_type == ArrangementType.TILE:
                row, col = map(int, key.split(","))
                new_tiles.append(TilePosition(row, col))
            elif arr_type == ArrangementType.ROW:
                row_index = int(key)
                new_tiles.extend([TilePosition(row_index, col) for col in range(self.total_cols)])
            elif arr_type == ArrangementType.COLUMN:
                col_index = int(key)
                new_tiles.extend([TilePosition(row, col_index) for row in range(self.total_rows)])
            elif arr_type == ArrangementType.GROUP:
                group = self._groups.get(key)
                if group:
                    new_tiles.extend(group.tiles)

        # Update flat list (set lookup remains valid as tiles didn't change)
        self._arranged_tiles = new_tiles

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
        if self._grid_mapping:
            self._grid_mapping.clear()

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
        return 0 <= position.row < self.total_rows and 0 <= position.col < self.total_cols

    # =========================================================================
    # Internal methods for undo/redo commands
    # These methods modify state without triggering undo history.
    # They emit signals for UI updates but are called by command instances,
    # not directly by user actions.
    # =========================================================================

    def _add_tile_no_history(self, tile: TilePosition) -> bool:
        """Add a tile without triggering undo history.

        Called by command execution, not directly by user actions.

        Args:
            tile: The tile position to add

        Returns:
            True if tile was added, False if already present or invalid
        """
        if not self._is_valid_position(tile):
            return False

        if tile in self._tile_set or tile in self._tile_to_group:
            return False

        self._arranged_tiles.append(tile)
        self._tile_set.add(tile)
        self._arrangement_order.append((ArrangementType.TILE, f"{tile.row},{tile.col}"))

        self.tile_added.emit(tile)
        self.arrangement_changed.emit()
        return True

    def _remove_tile_no_history(self, tile: TilePosition) -> bool:
        """Remove a tile without triggering undo history.

        Called by command execution, not directly by user actions.
        Note: Does NOT handle group membership - caller must handle that.

        Args:
            tile: The tile position to remove

        Returns:
            True if tile was removed, False if not present
        """
        if tile not in self._tile_set:
            return False

        self._arranged_tiles.remove(tile)
        self._tile_set.remove(tile)

        # Remove from arrangement order
        tile_key = f"{tile.row},{tile.col}"
        self._arrangement_order = [
            (t, k) for t, k in self._arrangement_order if not (t == ArrangementType.TILE and k == tile_key)
        ]

        self.tile_removed.emit(tile)
        self.arrangement_changed.emit()
        return True

    def _insert_tile_no_history(self, tile: TilePosition, position: int) -> bool:
        """Insert a tile at a specific position without triggering undo history.

        Called by command undo to restore a tile at its original position.

        Args:
            tile: The tile position to insert
            position: Position in the _arranged_tiles list to insert at

        Returns:
            True if tile was inserted, False if already present or invalid
        """
        if not self._is_valid_position(tile):
            return False

        if tile in self._tile_set or tile in self._tile_to_group:
            return False

        # Clamp position to valid range
        position = max(0, min(position, len(self._arranged_tiles)))
        self._arranged_tiles.insert(position, tile)
        self._tile_set.add(tile)

        # Insert in arrangement order at corresponding position
        tile_key = f"{tile.row},{tile.col}"
        order_position = max(0, min(position, len(self._arrangement_order)))
        self._arrangement_order.insert(order_position, (ArrangementType.TILE, tile_key))

        self.tile_added.emit(tile)
        self.arrangement_changed.emit()
        return True

    def _add_group_no_history(self, group: TileGroup) -> bool:
        """Add a group without triggering undo history.

        Called by command execution, not directly by user actions.

        Args:
            group: The tile group to add

        Returns:
            True if group was added, False if any tile conflicts
        """
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

    def _remove_group_no_history(self, group_id: str) -> bool:
        """Remove a group without triggering undo history.

        Called by command execution, not directly by user actions.

        Args:
            group_id: ID of the group to remove

        Returns:
            True if group was removed, False if not found
        """
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
            (t, k) for t, k in self._arrangement_order if not (t == ArrangementType.GROUP and k == group_id)
        ]

        self.group_removed.emit(group_id)
        self.arrangement_changed.emit()
        return True

    def _add_group_at_position_no_history(self, group: TileGroup, order_position: int) -> bool:
        """Add a group at a specific arrangement order position without triggering undo history.

        Called by command undo to restore a group at its original position.

        Args:
            group: The tile group to add
            order_position: Position in _arrangement_order to insert at

        Returns:
            True if group was added, False if any tile conflicts
        """
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

        # Insert at specific position in arrangement order
        order_position = max(0, min(order_position, len(self._arrangement_order)))
        self._arrangement_order.insert(order_position, (ArrangementType.GROUP, group.id))

        self.group_added.emit(group.id)
        self.arrangement_changed.emit()
        return True

    def _set_arrangement_order_no_history(self, new_order: list[tuple[ArrangementType, str]]) -> None:
        """Set the arrangement order without triggering undo history.

        Called by command execution for reorder operations.

        Args:
            new_order: New arrangement order
        """
        self._arrangement_order = list(new_order)
        self.arrangement_changed.emit()

    def _clear_no_history(self) -> None:
        """Clear all arrangements without triggering undo history.

        Called by command execution, not directly by user actions.
        """
        self._arranged_tiles.clear()
        self._tile_set.clear()
        self._groups.clear()
        self._tile_to_group.clear()
        self._arrangement_order.clear()

        self.arrangement_cleared.emit()
        self.arrangement_changed.emit()

    def _restore_state_no_history(
        self,
        tiles: list[TilePosition],
        groups: dict[str, TileGroup],
        tile_to_group: dict[TilePosition, str],
        order: list[tuple[ArrangementType, str]],
    ) -> None:
        """Restore full state without triggering undo history.

        Called by ClearGridCommand.undo() to restore previous state.

        Args:
            tiles: List of tile positions to restore
            groups: Dict of groups to restore
            tile_to_group: Tile-to-group mapping to restore
            order: Arrangement order to restore
        """
        self._arranged_tiles = list(tiles)
        self._tile_set = set(tiles)
        self._groups = dict(groups)
        self._tile_to_group = dict(tile_to_group)
        self._arrangement_order = list(order)

        self.arrangement_changed.emit()

    def get_tile_position(self, tile: TilePosition) -> int:
        """Get the position of a tile in the arrangement.

        Args:
            tile: The tile position to find

        Returns:
            Position in the arrangement, or -1 if not found
        """
        try:
            return self._arranged_tiles.index(tile)
        except ValueError:
            return -1

    def get_group_order_position(self, group_id: str) -> int:
        """Get the position of a group in the arrangement order.

        Args:
            group_id: ID of the group to find

        Returns:
            Position in the arrangement order, or -1 if not found
        """
        for i, (arr_type, key) in enumerate(self._arrangement_order):
            if arr_type == ArrangementType.GROUP and key == group_id:
                return i
        return -1

    def get_state_snapshot(
        self,
    ) -> tuple[
        list[TilePosition],
        dict[str, TileGroup],
        dict[TilePosition, str],
        list[tuple[ArrangementType, str]],
    ]:
        """Get a snapshot of the current state for undo/redo.

        Returns:
            Tuple of (tiles, groups, tile_to_group, arrangement_order) copies
        """
        return (
            list(self._arranged_tiles),
            dict(self._groups),
            dict(self._tile_to_group),
            list(self._arrangement_order),
        )
