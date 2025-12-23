"""
Factory for creating dialogs used by the extraction controller.

This factory enables the core layer to create dialogs without importing
from the UI layer, maintaining layer separation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from core.protocols.dialog_protocols import ArrangementDialogProtocol
    from ui.injection_dialog import InjectionDialog


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

        return RowArrangementDialog(sprite_path, tiles_per_row, parent)  # type: ignore[return-value]

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

        return GridArrangementDialog(sprite_path, tiles_per_row, parent)  # type: ignore[return-value]

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
        from core.di_container import inject
        from core.managers.application_state_manager import ApplicationStateManager
        from core.protocols.manager_protocols import InjectionManagerProtocol
        from ui.injection_dialog import InjectionDialog

        injection_manager = inject(InjectionManagerProtocol)
        settings_manager = inject(ApplicationStateManager)
        return InjectionDialog(
            parent, sprite_path, metadata_path, input_vram,
            injection_manager=injection_manager,
            settings_manager=settings_manager,
        )
