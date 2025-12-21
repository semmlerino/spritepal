"""
Tab coordination and switching logic for MainWindow
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QTabWidget

if TYPE_CHECKING:
    from ui.extraction_panel import ExtractionPanel
    from ui.managers.output_settings_manager import OutputSettingsManager
    from ui.managers.toolbar_manager import ToolbarManager
    from ui.rom_extraction_panel import ROMExtractionPanel

class TabCoordinatorActionsProtocol(Protocol):
    """Protocol defining the interface for tab coordinator actions"""

    def get_rom_extraction_params(self) -> dict[str, Any] | None:  # pyright: ignore[reportExplicitAny] - Extraction configuration
        """Get ROM extraction parameters"""
        ...

    def is_vram_extraction_ready(self) -> bool:
        """Check if VRAM extraction is ready"""
        ...

    def is_grayscale_mode(self) -> bool:
        """Check if in grayscale mode"""
        ...

    def get_extraction_mode_index(self) -> int:
        """Get current extraction mode index"""
        ...

class TabCoordinator(QObject):
    """Coordinates tab switching and state synchronization"""

    # Signals
    tab_changed = Signal(int)  # tab index

    def __init__(
        self,
        extraction_tabs: QTabWidget,
        rom_extraction_panel: ROMExtractionPanel,
        extraction_panel: ExtractionPanel,
        output_settings_manager: OutputSettingsManager,
        toolbar_manager: ToolbarManager,
        actions_handler: TabCoordinatorActionsProtocol
    ) -> None:
        """Initialize tab coordinator

        Args:
            extraction_tabs: Tab widget containing extraction tabs
            rom_extraction_panel: ROM extraction panel widget
            extraction_panel: VRAM extraction panel widget
            output_settings_manager: Output settings manager
            toolbar_manager: Toolbar manager
            actions_handler: Handler for tab coordination actions
        """
        super().__init__()
        self.extraction_tabs = extraction_tabs
        self.rom_extraction_panel = rom_extraction_panel
        self.extraction_panel = extraction_panel
        self.output_settings_manager = output_settings_manager
        self.toolbar_manager = toolbar_manager
        self.actions_handler = actions_handler

        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect tab change signals"""
        self.extraction_tabs.currentChanged.connect(self._on_extraction_tab_changed)

    def _on_extraction_tab_changed(self, index: int) -> None:
        """Handle tab change between VRAM and ROM extraction

        Args:
            index: New tab index (0=ROM, 1=VRAM)
        """
        if index == 0:
            self._configure_rom_extraction_tab()
        else:
            self._configure_vram_extraction_tab()

        # Emit signal for other components
        self.tab_changed.emit(index)

    def _configure_rom_extraction_tab(self) -> None:
        """Configure UI for ROM extraction tab"""
        # Check extraction readiness
        params = self.actions_handler.get_rom_extraction_params()
        if params is not None:
            self.toolbar_manager.set_extract_enabled(True)
        else:
            self.toolbar_manager.set_extract_enabled(False, "Load a ROM file")

        # Sync output name from ROM panel to main output field
        if params and params.get("output_base"):
            self.output_settings_manager.set_output_name(params["output_base"])

        # Configure output settings for ROM mode
        self.output_settings_manager.set_rom_extraction_mode()

    def _configure_vram_extraction_tab(self) -> None:
        """Configure UI for VRAM extraction tab"""
        # Check extraction readiness based on mode
        ready = self.actions_handler.is_vram_extraction_ready()
        if ready:
            self.toolbar_manager.set_extract_enabled(True)
        else:
            self.toolbar_manager.set_extract_enabled(False, "Load VRAM file")

        # Update output info label
        is_grayscale_mode = self.actions_handler.is_grayscale_mode()
        self.output_settings_manager.update_output_info_label(
            is_vram_tab=True,
            is_grayscale_mode=is_grayscale_mode
        )

        # Update checkbox states based on mode
        self.output_settings_manager.set_extraction_mode_options(is_grayscale_mode)

        # Configure output settings for VRAM mode
        self.output_settings_manager.set_vram_extraction_mode()

    def get_current_tab_index(self) -> int:
        """Get current active tab index"""
        return self.extraction_tabs.currentIndex()

    def is_rom_tab_active(self) -> bool:
        """Check if ROM extraction tab is active"""
        return self.get_current_tab_index() == 0

    def is_vram_tab_active(self) -> bool:
        """Check if VRAM extraction tab is active"""
        return self.get_current_tab_index() == 1

    def switch_to_rom_tab(self) -> None:
        """Switch to ROM extraction tab"""
        if self.extraction_tabs:
            self.extraction_tabs.setCurrentIndex(0)

    def switch_to_vram_tab(self) -> None:
        """Switch to VRAM extraction tab"""
        if self.extraction_tabs:
            self.extraction_tabs.setCurrentIndex(1)
