"""
Component Factory for Manual Offset Dialog

Handles creation, dependency injection, and lifecycle management of all dialog components.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ui.dialogs.manual_offset.components import (
    LayoutManagerComponent,
    ROMCacheComponent,
    SignalRouterComponent,
    TabManagerComponent,
    WorkerCoordinatorComponent,
)

if TYPE_CHECKING:
    from .manual_offset_dialog_core import ManualOffsetDialogCore

from utils.logging_config import get_logger

logger = get_logger(__name__)

class ComponentFactory:
    """
    Factory for creating and wiring dialog components.

    This factory handles the creation of all components, dependency injection,
    and proper wiring to ensure components work together correctly.
    """

    def __init__(self, dialog: ManualOffsetDialogCore) -> None:
        """Initialize the component factory."""
        self.dialog = dialog

    def create_all_components(self) -> dict[str, Any]:
        """
        Create all dialog components.

        Returns:
            Dictionary mapping component names to component instances
        """
        logger.debug("Creating all dialog components")

        components: dict[str, Any] = {
            'signal_router': SignalRouterComponent(self.dialog),
            'tab_manager': TabManagerComponent(self.dialog),  # type: ignore[arg-type]
            'layout_manager': LayoutManagerComponent(self.dialog),
            'worker_coordinator': WorkerCoordinatorComponent(self.dialog),
            'rom_cache': ROMCacheComponent(self.dialog)  # type: ignore[arg-type]
        }

        logger.debug(f"Created {len(components)} components")
        return components

    def wire_components(self, components: dict[str, Any]) -> None:
        """Wire components together with proper dependencies."""
        logger.debug("Wiring components together")

        signal_router = components['signal_router']
        tab_manager = components['tab_manager']
        worker_coordinator = components['worker_coordinator']

        # Connect signal router to other components
        signal_router.connect_to_tabs(tab_manager)
        signal_router.connect_to_workers(worker_coordinator)

        # Connect tab events to signal router
        if tab_manager.browse_tab and hasattr(tab_manager.browse_tab, 'offset_changed'):
            tab_manager.browse_tab.offset_changed.connect(signal_router.emit_offset_changed)

        # Connect tab widget changes for dynamic sizing
        if tab_manager.tab_widget:
            tab_manager.tab_widget.currentChanged.connect(
                lambda index: components['layout_manager'].update_for_tab(
                    index, self.dialog.width()
                )
            )

        # Connect worker events to signal router
        # This would connect preview ready signals, etc.

        logger.debug("Component wiring complete")
