"""
Factory for creating dialogs used by the extraction controller.

This factory enables the core layer to create dialogs without importing
from the UI layer, maintaining layer separation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from core.protocols.dialog_protocols import (
        ArrangementDialogProtocol,
        InjectionDialogProtocol,
    )


class ControllerDialogFactory:
    """
    Factory for creating dialogs used by the extraction controller.

    This factory provides a way for the core layer to create UI dialogs
    without directly importing from the UI layer. It uses local imports
    within methods to defer the actual UI imports until dialog creation time.
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
            A RowArrangementDialog instance
        """
        from ui.row_arrangement_dialog import RowArrangementDialog

        return RowArrangementDialog(sprite_path, tiles_per_row, parent)

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
            A GridArrangementDialog instance
        """
        from ui.grid_arrangement_dialog import GridArrangementDialog

        return GridArrangementDialog(sprite_path, tiles_per_row, parent)

    def create_injection_dialog(
        self,
        parent: QWidget | None = None,
        sprite_path: str = "",
        metadata_path: str = "",
        input_vram: str = "",
    ) -> InjectionDialogProtocol:
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
        from core.di_container import inject
        from core.protocols.manager_protocols import InjectionManagerProtocol
        from ui.injection_dialog import InjectionDialog

        injection_manager = inject(InjectionManagerProtocol)
        return InjectionDialog(
            parent, sprite_path, metadata_path, input_vram,
            injection_manager=injection_manager  # type: ignore[arg-type]
        )


# Global accessor for the factory (for non-DI contexts)
_controller_dialog_factory: ControllerDialogFactory | None = None


def get_controller_dialog_factory() -> ControllerDialogFactory:
    """
    Get a global instance of the ControllerDialogFactory.

    This should primarily be used in legacy code or if injection is not feasible.
    For new code, prefer injecting the factory via the DI container.
    """
    global _controller_dialog_factory
    if _controller_dialog_factory is None:
        _controller_dialog_factory = ControllerDialogFactory()
    return _controller_dialog_factory
