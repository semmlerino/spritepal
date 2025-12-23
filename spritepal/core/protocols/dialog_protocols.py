"""
Protocol definitions for dialogs to break circular dependencies.

These protocols define the interfaces that dialogs must implement,
enabling the core layer to use dialogs without importing from the UI layer.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PySide6.QtWidgets import QDialog, QWidget

    from ui.injection_dialog import InjectionDialog


class ArrangementDialogProtocol(Protocol):
    """Protocol for arrangement dialogs (row and grid).

    This protocol has true polymorphism - RowArrangementDialog and
    GridArrangementDialog both implement it.
    """

    def set_palettes(
        self, palettes_dict: Mapping[int, object]
    ) -> None:
        """Set available palettes for the dialog."""
        ...

    def exec(self) -> int:
        """Execute the dialog modally and return result code."""
        ...

    def get_arranged_path(self) -> str | None:
        """Get the path to the arranged output file, or None if cancelled."""
        ...


class ManualOffsetDialogFactoryProtocol(Protocol):
    """
    Protocol for creating ManualOffsetDialog instances.

    This factory allows retrieval of the dialog factory without
    importing the concrete UI class, maintaining layer separation.
    """

    def create(self, parent: QWidget | None = None) -> QDialog:
        """
        Create a manual offset dialog.

        Args:
            parent: Parent widget

        Returns:
            A QDialog instance (UnifiedManualOffsetDialog)
        """
        ...


class DialogFactoryProtocol(Protocol):
    """
    Protocol for creating dialog instances.

    This factory allows the core layer to create dialogs without
    importing from the UI layer, maintaining layer separation.
    """

    def create_row_arrangement_dialog(
        self,
        sprite_path: str,
        tiles_per_row: int,
        parent: QWidget | None = None,
    ) -> ArrangementDialogProtocol:
        """
        Create a row arrangement dialog.

        Args:
            sprite_path: Path to the sprite file
            tiles_per_row: Number of tiles per row
            parent: Parent widget

        Returns:
            A dialog implementing ArrangementDialogProtocol
        """
        ...

    def create_grid_arrangement_dialog(
        self,
        sprite_path: str,
        tiles_per_row: int,
        parent: QWidget | None = None,
    ) -> ArrangementDialogProtocol:
        """
        Create a grid arrangement dialog.

        Args:
            sprite_path: Path to the sprite file
            tiles_per_row: Number of tiles per row
            parent: Parent widget

        Returns:
            A dialog implementing ArrangementDialogProtocol
        """
        ...

    def create_injection_dialog(
        self,
        parent: QWidget | None = None,
        sprite_path: str = "",
        metadata_path: str = "",
        input_vram: str = "",
    ) -> InjectionDialog:
        """
        Create an injection dialog.

        Args:
            parent: Parent widget
            sprite_path: Path to the sprite file
            metadata_path: Path to metadata file
            input_vram: Path to input VRAM file

        Returns:
            An InjectionDialog instance
        """
        ...
