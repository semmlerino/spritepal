"""
Row arrangement state management
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class ArrangementManager(QObject):
    """Manages the state of arranged sprite rows"""

    # Signals
    arrangement_changed = Signal()  # Emitted when arrangement changes
    row_added = Signal(int)  # Emitted when a row is added
    row_removed = Signal(int)  # Emitted when a row is removed
    arrangement_cleared = Signal()  # Emitted when arrangement is cleared

    def __init__(self) -> None:
        super().__init__()
        self._arranged_rows: list[int] = []

    def add_row(self, row_index: int) -> bool:
        """Add a row to the arrangement

        Args:
            row_index: Index of the row to add

        Returns:
            True if row was added, False if already present
        """
        if row_index not in self._arranged_rows:
            self._arranged_rows.append(row_index)
            self.row_added.emit(row_index)
            self.arrangement_changed.emit()
            return True
        return False

    def remove_row(self, row_index: int) -> bool:
        """Remove a row from the arrangement

        Args:
            row_index: Index of the row to remove

        Returns:
            True if row was removed, False if not present
        """
        if row_index in self._arranged_rows:
            self._arranged_rows.remove(row_index)
            self.row_removed.emit(row_index)
            self.arrangement_changed.emit()
            return True
        return False

    def add_multiple_rows(self, row_indices: list[int]) -> int:
        """Add multiple rows to the arrangement

        Args:
            row_indices: List of row indices to add

        Returns:
            Number of rows actually added
        """
        added_count = 0
        for row_index in row_indices:
            if row_index not in self._arranged_rows:
                self._arranged_rows.append(row_index)
                added_count += 1

        if added_count > 0:
            self.arrangement_changed.emit()

        return added_count

    def remove_multiple_rows(self, row_indices: list[int]) -> int:
        """Remove multiple rows from the arrangement

        Args:
            row_indices: List of row indices to remove

        Returns:
            Number of rows actually removed
        """
        removed_count = 0
        for row_index in row_indices:
            if row_index in self._arranged_rows:
                self._arranged_rows.remove(row_index)
                removed_count += 1

        if removed_count > 0:
            self.arrangement_changed.emit()

        return removed_count

    def reorder_rows(self, new_order: list[int]) -> None:
        """Set a new order for the arranged rows

        Args:
            new_order: New list of row indices in desired order
        """
        self._arranged_rows = new_order.copy()
        self.arrangement_changed.emit()

    def clear(self) -> None:
        """Clear all arranged rows"""
        if self._arranged_rows:
            self._arranged_rows.clear()
        self.arrangement_cleared.emit()
        self.arrangement_changed.emit()

    def get_arranged_indices(self) -> list[int]:
        """Get the current list of arranged row indices

        Returns:
            Copy of the arranged rows list
        """
        return self._arranged_rows.copy()

    def get_arranged_count(self) -> int:
        """Get the number of arranged rows

        Returns:
            Number of rows in arrangement
        """
        return len(self._arranged_rows)

    def is_row_arranged(self, row_index: int) -> bool:
        """Check if a row is in the arrangement

        Args:
            row_index: Index of the row to check

        Returns:
            True if row is arranged, False otherwise
        """
        return row_index in self._arranged_rows

    # =========================================================================
    # Internal methods for undo/redo commands
    # These methods modify state and emit signals but are not called directly
    # by user actions - they are called by ArrangementCommand instances.
    # =========================================================================

    def _add_row_no_history(self, row_index: int) -> bool:
        """Add a row without triggering undo history tracking.

        Called by command execution, not directly by user actions.

        Args:
            row_index: Index of the row to add

        Returns:
            True if row was added, False if already present
        """
        if row_index not in self._arranged_rows:
            self._arranged_rows.append(row_index)
            self.row_added.emit(row_index)
            self.arrangement_changed.emit()
            return True
        return False

    def _remove_row_no_history(self, row_index: int) -> bool:
        """Remove a row without triggering undo history tracking.

        Called by command execution, not directly by user actions.

        Args:
            row_index: Index of the row to remove

        Returns:
            True if row was removed, False if not present
        """
        if row_index in self._arranged_rows:
            self._arranged_rows.remove(row_index)
            self.row_removed.emit(row_index)
            self.arrangement_changed.emit()
            return True
        return False

    def _insert_row_no_history(self, row_index: int, position: int) -> bool:
        """Insert a row at a specific position without triggering undo history.

        Called by command undo to restore a row at its original position.

        Args:
            row_index: Index of the row to insert
            position: Position in the arrangement list to insert at

        Returns:
            True if row was inserted, False if already present
        """
        if row_index not in self._arranged_rows:
            # Clamp position to valid range
            position = max(0, min(position, len(self._arranged_rows)))
            self._arranged_rows.insert(position, row_index)
            self.row_added.emit(row_index)
            self.arrangement_changed.emit()
            return True
        return False

    def _set_arrangement_no_history(self, rows: list[int]) -> None:
        """Set the entire arrangement without triggering undo history.

        Called by command execution for reorder and clear-undo operations.

        Args:
            rows: New list of row indices
        """
        self._arranged_rows = list(rows)
        self.arrangement_changed.emit()

    def _clear_no_history(self) -> None:
        """Clear all rows without triggering undo history.

        Called by command execution, not directly by user actions.
        """
        self._arranged_rows.clear()
        self.arrangement_cleared.emit()
        self.arrangement_changed.emit()

    def get_row_position(self, row_index: int) -> int:
        """Get the position of a row in the arrangement.

        Args:
            row_index: Index of the row to find

        Returns:
            Position in the arrangement, or -1 if not found
        """
        try:
            return self._arranged_rows.index(row_index)
        except ValueError:
            return -1

    def get_state_copy(self) -> list[int]:
        """Get a copy of the current arrangement state.

        Used by commands to capture state before modifications.

        Returns:
            Copy of the arranged rows list
        """
        return list(self._arranged_rows)
