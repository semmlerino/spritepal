"""
Core Composed Implementation of Manual Offset Dialog

This module provides the composed implementation that replaces the monolithic
UnifiedManualOffsetDialog with a clean, component-based architecture.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget
from typing_extensions import override

from ui.components.base.composed.migration_adapter import DialogBaseMigrationAdapter
from ui.dialogs.manual_offset.components import (
    LayoutManagerComponent,
    ROMCacheComponent,
    SignalRouterComponent,
    TabManagerComponent,
    WorkerCoordinatorComponent,
)

from .component_factory import ComponentFactory

if TYPE_CHECKING:
    from core.managers.extraction_manager import ExtractionManager

from utils.logging_config import get_logger

logger = get_logger(__name__)

class ManualOffsetDialogCore(DialogBaseMigrationAdapter):
    """
    Core composed implementation of the Manual Offset Dialog.

    This class coordinates all the composed components to provide the full
    functionality of the original UnifiedManualOffsetDialog while using
    composition instead of inheritance.
    """

    # External signals for ROM extraction panel integration
    offset_changed = Signal(int)
    sprite_found = Signal(int, str)  # offset, name
    validation_failed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        """Initialize the composed manual offset dialog."""
        logger.debug("Creating ManualOffsetDialogCore instance")

        # Initialize component references (will be set up later)
        self._signal_router: SignalRouterComponent | None = None
        self._tab_manager: TabManagerComponent | None = None
        self._layout_manager: LayoutManagerComponent | None = None
        self._worker_coordinator: WorkerCoordinatorComponent | None = None
        self._rom_cache: ROMCacheComponent | None = None
        self._component_factory: ComponentFactory | None = None

        # Business logic state
        self.rom_path: str = ""
        self.rom_size: int = 0x400000
        self.extraction_manager: ExtractionManager | None = None

        # Note: UI component references are exposed as properties that
        # delegate to the appropriate components. They don't need to be
        # initialized here as they're dynamically retrieved from components.

        # Initialize base dialog with enhanced sizing for composed implementation
        super().__init__(
            parent=parent,
            title="Manual Offset Control - SpritePal",
            modal=False,
            size=(1100, 700),          # Larger default size for better UX
            min_size=(900, 600),       # Higher minimum for modern displays
            with_status_bar=False,
            orientation=Qt.Orientation.Horizontal,
            splitter_handle_width=12   # More prominent splitter handle
        )

        # Set up components after base initialization
        self._setup_components()
        self._connect_signals()

    @override
    def _setup_ui(self):
        """Override DialogBase _setup_ui to use our component-based setup."""
        # This is called by DialogBase.__init__
        # We don't set up UI here because we need components initialized first
        # The actual UI setup happens in _setup_components after base init
        pass

    def _setup_components(self):
        """Set up all dialog components."""
        logger.debug("Setting up dialog components")

        # Create component factory
        self._component_factory = ComponentFactory(self)

        # Create all components through factory
        components = self._component_factory.create_all_components()

        # Store component references
        self._signal_router = components['signal_router']
        self._tab_manager = components['tab_manager']
        self._layout_manager = components['layout_manager']
        self._worker_coordinator = components['worker_coordinator']
        self._rom_cache = components['rom_cache']

        # Wire components together
        self._component_factory.wire_components(components)

        # Set up UI structure now that components are ready
        self._setup_ui_structure()

    def _setup_ui_structure(self):
        """Set up the dialog UI structure."""
        # Create left and right panels
        left_panel = self._tab_manager.create_left_panel() if self._tab_manager else None
        right_panel = self._worker_coordinator.create_right_panel() if self._worker_coordinator else None

        # Configure splitter through layout manager
        if self._layout_manager and self.main_splitter and left_panel and right_panel:
            self._layout_manager.configure_splitter(
                self.main_splitter,
                left_panel,
                right_panel
            )

        # Add panels to dialog with better proportions (2:3 instead of 1:3)
        if left_panel:
            self.add_panel(left_panel, stretch_factor=2)
        if right_panel:
            self.add_panel(right_panel, stretch_factor=3)

        # Set up custom buttons
        if self._tab_manager and self.button_box:
            self._tab_manager.setup_custom_buttons(self.button_box)

        # Note: UI components are accessible via properties that delegate
        # to the appropriate components, so no need to update references here

        # Apply initial layout fixes
        if self._layout_manager:
            self._layout_manager.fix_empty_space_issue()

    def _connect_signals(self):
        """Connect component signals to external signals."""
        if self._signal_router:
            # Route internal signals to external signals
            self._signal_router.offset_changed.connect(self.offset_changed.emit)
            self._signal_router.sprite_found.connect(self.sprite_found.emit)
            self._signal_router.validation_failed.connect(self.validation_failed.emit)

    # Public API methods for backward compatibility

    def set_rom_data(self, rom_path: str, rom_size: int, extraction_manager: ExtractionManager) -> None:
        """Set ROM data for the dialog."""
        self.rom_path = rom_path
        self.rom_size = rom_size
        self.extraction_manager = extraction_manager

        # Update components with ROM data
        if self._tab_manager:
            self._tab_manager.set_rom_data(rom_path, rom_size, extraction_manager)
        if self._worker_coordinator:
            self._worker_coordinator.set_rom_data(rom_path, rom_size, extraction_manager)
        if self._rom_cache:
            self._rom_cache.initialize_rom(rom_path, rom_size)

        logger.debug(f"ROM data set: {rom_path} ({rom_size} bytes)")

    def set_offset(self, offset: int) -> bool:
        """Set current offset."""
        if self._tab_manager:
            return self._tab_manager.set_offset(offset)
        return False

    def get_current_offset(self) -> int:
        """Get current offset."""
        if self._tab_manager:
            return self._tab_manager.get_current_offset()
        return 0x200000

    def add_found_sprite(self, offset: int, quality: float = 1.0) -> None:
        """Add found sprite to history."""
        if self._tab_manager:
            self._tab_manager.add_found_sprite(offset, quality)

    # Properties for backward compatibility - expose component properties
    @property
    @override
    def tab_widget(self):
        """Get the tab widget from tab manager."""
        if self._tab_manager:
            return self._tab_manager.tab_widget
        return None

    @property
    def browse_tab(self):
        """Get the browse tab from tab manager."""
        if self._tab_manager:
            return self._tab_manager.browse_tab
        return None

    @property
    def smart_tab(self):
        """Get the smart tab from tab manager."""
        if self._tab_manager:
            return self._tab_manager.smart_tab
        return None

    @property
    def history_tab(self):
        """Get the history tab from tab manager."""
        if self._tab_manager:
            return self._tab_manager.history_tab
        return None

    @property
    def gallery_tab(self):
        """Get the gallery tab from tab manager."""
        if self._tab_manager:
            return self._tab_manager.gallery_tab
        return None

    @property
    def preview_widget(self):
        """Get the preview widget from worker coordinator."""
        if self._worker_coordinator:
            return self._worker_coordinator.preview_widget
        return None

    @property
    def status_panel(self):
        """Get the status panel from tab manager."""
        if self._tab_manager:
            return self._tab_manager.status_panel
        return None

    @property
    def mini_rom_map(self):
        """Get the mini ROM map from worker coordinator."""
        if self._worker_coordinator:
            return self._worker_coordinator.mini_rom_map
        return None

    def cleanup(self):
        """Clean up resources to prevent memory leaks."""
        logger.debug("Cleaning up ManualOffsetDialogCore")

        # Clean up components
        if self._worker_coordinator:
            self._worker_coordinator.cleanup()
        if self._rom_cache:
            self._rom_cache.cleanup()
        if self._tab_manager:
            self._tab_manager.cleanup()
        if self._signal_router:
            self._signal_router.cleanup()

        # Clear references
        self.extraction_manager = None
        self._component_factory = None

        # Call parent cleanup
        if hasattr(super(), 'cleanup'):
            super().cleanup()  # type: ignore[misc]

    @override
    def showEvent(self, event: Any):
        """Handle show event."""
        super().showEvent(event)
        if self._layout_manager:
            self._layout_manager.on_dialog_show()

    @override
    def resizeEvent(self, event: Any):
        """Handle resize event."""
        super().resizeEvent(event)
        if self._layout_manager and self.isVisible():
            self._layout_manager.handle_resize(event.size().width())

    @override
    def hideEvent(self, event: Any):
        """Handle hide event."""
        if self._worker_coordinator:
            self._worker_coordinator.cleanup_workers()
        super().hideEvent(event)
