"""Undo/Redo infrastructure for arrangement dialogs.

This module provides a command-pattern based undo/redo system for both
RowArrangementDialog and GridArrangementDialog.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from ui.row_arrangement.arrangement_manager import ArrangementManager
    from ui.row_arrangement.grid_arrangement_manager import (
        ArrangementType,
        GridArrangementManager,
        TileGroup,
        TilePosition,
    )


# =============================================================================
# Base Command Protocol
# =============================================================================


class ArrangementCommand(Protocol):
    """Protocol for undoable arrangement commands.

    All command implementations must provide these methods.
    Concrete command classes are dataclasses that implement this interface
    via structural subtyping (duck typing) - they don't explicitly inherit.
    """

    @property
    def description(self) -> str:
        """Human-readable description of the command."""
        ...

    def execute(self) -> None:
        """Execute the command (for initial execution and redo)."""
        ...

    def undo(self) -> None:
        """Undo the command."""
        ...


# Type alias for concrete commands (they all implement ArrangementCommand via duck typing)
Command = ArrangementCommand


# =============================================================================
# Undo/Redo Stack Manager
# =============================================================================


class UndoRedoStack(QObject):
    """Manages undo/redo history for arrangement operations.

    Provides a stack-based command history with configurable max depth.
    Emits signals when undo/redo availability changes for UI updates.
    """

    # Signals for UI state updates
    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)
    stack_changed = Signal()

    DEFAULT_MAX_HISTORY = 50

    def __init__(self, max_history: int = DEFAULT_MAX_HISTORY, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._undo_stack: list[ArrangementCommand] = []
        self._redo_stack: list[ArrangementCommand] = []
        self._max_history = max_history

    def push(self, command: ArrangementCommand) -> None:
        """Execute a command and push it onto the undo stack.

        Args:
            command: The command to execute and track
        """
        # Execute the command first
        command.execute()

        # Clear redo stack when new command is added
        if self._redo_stack:
            self._redo_stack.clear()
            self.can_redo_changed.emit(False)

        # Add to undo stack
        self._undo_stack.append(command)

        # Enforce history limit
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)

        # Emit signals
        self.can_undo_changed.emit(True)
        self.stack_changed.emit()

    def undo(self) -> str | None:
        """Undo the last command.

        Returns:
            Description of the undone command, or None if nothing to undo
        """
        if not self._undo_stack:
            return None

        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)

        # Emit signals
        self.can_undo_changed.emit(len(self._undo_stack) > 0)
        self.can_redo_changed.emit(True)
        self.stack_changed.emit()

        return command.description

    def redo(self) -> str | None:
        """Redo the last undone command.

        Returns:
            Description of the redone command, or None if nothing to redo
        """
        if not self._redo_stack:
            return None

        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)

        # Emit signals
        self.can_undo_changed.emit(True)
        self.can_redo_changed.emit(len(self._redo_stack) > 0)
        self.stack_changed.emit()

        return command.description

    def clear(self) -> None:
        """Clear all history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.can_undo_changed.emit(False)
        self.can_redo_changed.emit(False)
        self.stack_changed.emit()

    def can_undo(self) -> bool:
        """Check if undo is available."""
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        """Check if redo is available."""
        return len(self._redo_stack) > 0

    def undo_description(self) -> str | None:
        """Get description of next undo command."""
        return self._undo_stack[-1].description if self._undo_stack else None

    def redo_description(self) -> str | None:
        """Get description of next redo command."""
        return self._redo_stack[-1].description if self._redo_stack else None


# =============================================================================
# Row Arrangement Commands
# =============================================================================


@dataclass
class AddRowCommand:
    """Command to add a single row to the arrangement."""

    manager: ArrangementManager
    row_index: int

    @property
    def description(self) -> str:
        return f"Add row {self.row_index}"

    def execute(self) -> None:
        self.manager._add_row_no_history(self.row_index)

    def undo(self) -> None:
        self.manager._remove_row_no_history(self.row_index)


@dataclass
class RemoveRowCommand:
    """Command to remove a single row from the arrangement."""

    manager: ArrangementManager
    row_index: int
    position: int = -1  # Position in arrangement, captured at creation

    @property
    def description(self) -> str:
        return f"Remove row {self.row_index}"

    def execute(self) -> None:
        self.manager._remove_row_no_history(self.row_index)

    def undo(self) -> None:
        self.manager._insert_row_no_history(self.row_index, self.position)


@dataclass
class AddMultipleRowsCommand:
    """Command to add multiple rows to the arrangement."""

    manager: ArrangementManager
    row_indices: list[int]

    @property
    def description(self) -> str:
        count = len(self.row_indices)
        return f"Add {count} row{'s' if count != 1 else ''}"

    def execute(self) -> None:
        for row_index in self.row_indices:
            self.manager._add_row_no_history(row_index)

    def undo(self) -> None:
        # Remove in reverse order to maintain correct positions
        for row_index in reversed(self.row_indices):
            self.manager._remove_row_no_history(row_index)


@dataclass
class RemoveMultipleRowsCommand:
    """Command to remove multiple rows from the arrangement."""

    manager: ArrangementManager
    # List of (row_index, original_position) tuples
    rows_with_positions: list[tuple[int, int]]

    @property
    def description(self) -> str:
        count = len(self.rows_with_positions)
        return f"Remove {count} row{'s' if count != 1 else ''}"

    def execute(self) -> None:
        for row_index, _ in self.rows_with_positions:
            self.manager._remove_row_no_history(row_index)

    def undo(self) -> None:
        # Restore in reverse order of removal, by original position
        for row_index, position in reversed(self.rows_with_positions):
            self.manager._insert_row_no_history(row_index, position)


@dataclass
class ReorderRowsCommand:
    """Command to reorder rows (e.g., via drag-drop)."""

    manager: ArrangementManager
    old_order: list[int]
    new_order: list[int]

    @property
    def description(self) -> str:
        return "Reorder rows"

    def execute(self) -> None:
        self.manager._set_arrangement_no_history(self.new_order)

    def undo(self) -> None:
        self.manager._set_arrangement_no_history(self.old_order)


@dataclass
class ClearRowsCommand:
    """Command to clear all rows (memento-style, stores full state)."""

    manager: ArrangementManager
    previous_state: list[int] = field(default_factory=list)

    @property
    def description(self) -> str:
        count = len(self.previous_state)
        return f"Clear {count} row{'s' if count != 1 else ''}"

    def execute(self) -> None:
        self.manager._clear_no_history()

    def undo(self) -> None:
        self.manager._set_arrangement_no_history(self.previous_state)


# =============================================================================
# Grid Arrangement Commands (for GridArrangementDialog)
# =============================================================================


@dataclass
class AddTileCommand:
    """Command to add a single tile to the grid arrangement."""

    manager: GridArrangementManager
    tile: TilePosition

    @property
    def description(self) -> str:
        return f"Add tile ({self.tile.row}, {self.tile.col})"

    def execute(self) -> None:
        self.manager._add_tile_no_history(self.tile)

    def undo(self) -> None:
        self.manager._remove_tile_no_history(self.tile)


@dataclass
class InsertTileCommand:
    """Command to insert a single tile at a specific position."""

    manager: GridArrangementManager
    tile: TilePosition
    index: int

    @property
    def description(self) -> str:
        return f"Insert tile ({self.tile.row}, {self.tile.col}) at index {self.index + 1}"

    def execute(self) -> None:
        self.manager.insert_tile(self.tile, self.index)

    def undo(self) -> None:
        self.manager.remove_tile(self.tile)


@dataclass
class RemoveTileCommand:
    """Command to remove a single tile from the grid arrangement."""

    manager: GridArrangementManager
    tile: TilePosition
    position: int = -1  # Position in _arranged_tiles

    @property
    def description(self) -> str:
        return f"Remove tile ({self.tile.row}, {self.tile.col})"

    def execute(self) -> None:
        self.manager._remove_tile_no_history(self.tile)

    def undo(self) -> None:
        self.manager._insert_tile_no_history(self.tile, self.position)


@dataclass
class AddMultipleTilesCommand:
    """Command to add multiple tiles to the grid arrangement."""

    manager: GridArrangementManager
    tiles: list[TilePosition]

    @property
    def description(self) -> str:
        count = len(self.tiles)
        return f"Add {count} tile{'s' if count != 1 else ''}"

    def execute(self) -> None:
        for tile in self.tiles:
            self.manager._add_tile_no_history(tile)

    def undo(self) -> None:
        for tile in reversed(self.tiles):
            self.manager._remove_tile_no_history(tile)


@dataclass
class RemoveMultipleTilesCommand:
    """Command to remove multiple tiles from the grid arrangement."""

    manager: GridArrangementManager
    tiles_with_positions: list[tuple[TilePosition, int]]

    @property
    def description(self) -> str:
        count = len(self.tiles_with_positions)
        return f"Remove {count} tile{'s' if count != 1 else ''}"

    def execute(self) -> None:
        for tile, _ in self.tiles_with_positions:
            self.manager._remove_tile_no_history(tile)

    def undo(self) -> None:
        for tile, position in reversed(self.tiles_with_positions):
            self.manager._insert_tile_no_history(tile, position)


@dataclass
class AddRowTilesCommand:
    """Command to add all tiles from a row."""

    manager: GridArrangementManager
    row: int
    tiles_added: list[TilePosition] = field(default_factory=list)

    @property
    def description(self) -> str:
        return f"Add row {self.row}"

    def execute(self) -> None:
        for tile in self.tiles_added:
            self.manager._add_tile_no_history(tile)

    def undo(self) -> None:
        for tile in reversed(self.tiles_added):
            self.manager._remove_tile_no_history(tile)


@dataclass
class RemoveRowTilesCommand:
    """Command to remove all tiles from a row."""

    manager: GridArrangementManager
    row: int
    tiles_with_positions: list[tuple[TilePosition, int]] = field(default_factory=list)

    @property
    def description(self) -> str:
        return f"Remove row {self.row}"

    def execute(self) -> None:
        for tile, _ in self.tiles_with_positions:
            self.manager._remove_tile_no_history(tile)

    def undo(self) -> None:
        for tile, position in reversed(self.tiles_with_positions):
            self.manager._insert_tile_no_history(tile, position)


@dataclass
class AddColumnTilesCommand:
    """Command to add all tiles from a column."""

    manager: GridArrangementManager
    col: int
    tiles_added: list[TilePosition] = field(default_factory=list)

    @property
    def description(self) -> str:
        return f"Add column {self.col}"

    def execute(self) -> None:
        for tile in self.tiles_added:
            self.manager._add_tile_no_history(tile)

    def undo(self) -> None:
        for tile in reversed(self.tiles_added):
            self.manager._remove_tile_no_history(tile)


@dataclass
class RemoveColumnTilesCommand:
    """Command to remove all tiles from a column."""

    manager: GridArrangementManager
    col: int
    tiles_with_positions: list[tuple[TilePosition, int]] = field(default_factory=list)

    @property
    def description(self) -> str:
        return f"Remove column {self.col}"

    def execute(self) -> None:
        for tile, _ in self.tiles_with_positions:
            self.manager._remove_tile_no_history(tile)

    def undo(self) -> None:
        for tile, position in reversed(self.tiles_with_positions):
            self.manager._insert_tile_no_history(tile, position)


@dataclass
class AddGroupCommand:
    """Command to add a tile group to the arrangement."""

    manager: GridArrangementManager
    group: TileGroup

    @property
    def description(self) -> str:
        name = self.group.name or self.group.id
        return f"Add group '{name}'"

    def execute(self) -> None:
        self.manager._add_group_no_history(self.group)

    def undo(self) -> None:
        self.manager._remove_group_no_history(self.group.id)


@dataclass
class RemoveGroupCommand:
    """Command to remove a tile group from the arrangement."""

    manager: GridArrangementManager
    group: TileGroup
    order_position: int = -1  # Position in _arrangement_order

    @property
    def description(self) -> str:
        name = self.group.name or self.group.id
        return f"Remove group '{name}'"

    def execute(self) -> None:
        self.manager._remove_group_no_history(self.group.id)

    def undo(self) -> None:
        self.manager._add_group_at_position_no_history(self.group, self.order_position)


@dataclass
class ReorderGridCommand:
    """Command to reorder the grid arrangement order."""

    manager: GridArrangementManager
    old_order: list[tuple[ArrangementType, str]]
    new_order: list[tuple[ArrangementType, str]]

    @property
    def description(self) -> str:
        return "Reorder arrangement"

    def execute(self) -> None:
        self.manager._set_arrangement_order_no_history(self.new_order)

    def undo(self) -> None:
        self.manager._set_arrangement_order_no_history(self.old_order)


@dataclass
class ClearGridCommand:
    """Command to clear all grid arrangements (memento-style)."""

    manager: GridArrangementManager
    previous_tiles: list[TilePosition] = field(default_factory=list)
    previous_groups: dict[str, TileGroup] = field(default_factory=dict)
    previous_tile_to_group: dict[TilePosition, str] = field(default_factory=dict)
    previous_order: list[tuple[ArrangementType, str]] = field(default_factory=list)

    @property
    def description(self) -> str:
        count = len(self.previous_tiles)
        return f"Clear all ({count} tile{'s' if count != 1 else ''})"

    def execute(self) -> None:
        self.manager._clear_no_history()

    def undo(self) -> None:
        self.manager._restore_state_no_history(
            self.previous_tiles,
            self.previous_groups,
            self.previous_tile_to_group,
            self.previous_order,
        )


@dataclass
class CanvasMoveItemsCommand:
    """Command to move an item within the arrangement canvas."""

    manager: GridArrangementManager
    source_pos: tuple[int, int]
    target_pos: tuple[int, int]
    # We might overwrite something at target, so we need to store it
    overwritten_item: tuple[ArrangementType, str] | None = None
    
    @property
    def description(self) -> str:
        return f"Move item to ({self.target_pos[0]}, {self.target_pos[1]})"

    def execute(self) -> None:
        # Save overwritten item if any (only on first execute, theoretically)
        # But for robust undo/redo, we should capture it before execution if not provided.
        # Here we assume the caller provides it or we check it now.
        if self.overwritten_item is None:
            self.overwritten_item = self.manager.get_item_at(*self.target_pos)
            
        self.manager.move_grid_item(self.source_pos, self.target_pos)

    def undo(self) -> None:
        # Move back
        self.manager.move_grid_item(self.target_pos, self.source_pos)
        
        # Restore overwritten item at target if any
        if self.overwritten_item:
            arr_type, key = self.overwritten_item
            self.manager.set_item_at(self.target_pos[0], self.target_pos[1], arr_type, key)


@dataclass
class CanvasPlaceItemsCommand:
    """Command to place a new item on the arrangement canvas (from source)."""

    manager: GridArrangementManager
    target_pos: tuple[int, int]
    item_type: ArrangementType
    item_key: str
    overwritten_item: tuple[ArrangementType, str] | None = None

    @property
    def description(self) -> str:
        return f"Place item at ({self.target_pos[0]}, {self.target_pos[1]})"

    def execute(self) -> None:
        if self.overwritten_item is None:
            self.overwritten_item = self.manager.get_item_at(*self.target_pos)
            
        self.manager.set_item_at(self.target_pos[0], self.target_pos[1], self.item_type, self.item_key)

    def undo(self) -> None:
        # Remove placed item
        self.manager.remove_item_at(self.target_pos[0], self.target_pos[1])
        
        # Restore overwritten item if any
        if self.overwritten_item:
            arr_type, key = self.overwritten_item
            self.manager.set_item_at(self.target_pos[0], self.target_pos[1], arr_type, key)


@dataclass
class CanvasRemoveItemCommand:
    """Command to remove an item from the arrangement canvas."""

    manager: GridArrangementManager
    target_pos: tuple[int, int]
    removed_item: tuple[ArrangementType, str] | None = None

    @property
    def description(self) -> str:
        return f"Remove item at ({self.target_pos[0]}, {self.target_pos[1]})"

    def execute(self) -> None:
        if self.removed_item is None:
            self.removed_item = self.manager.get_item_at(*self.target_pos)
            
        self.manager.remove_item_at(self.target_pos[0], self.target_pos[1])

    def undo(self) -> None:
        if self.removed_item:
            arr_type, key = self.removed_item
            self.manager.set_item_at(self.target_pos[0], self.target_pos[1], arr_type, key)

