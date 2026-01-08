#!/usr/bin/env python3
"""
Extraction Workspace - ROM and VRAM extraction tabs with action zone.

This workspace contains the extraction functionality:
- ROM Extraction tab: Extract sprites from game ROM files
- VRAM Extraction tab: Extract from emulator memory dumps

The Sprite Editor has been moved to a separate workspace.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import SPACING_COMPACT_SMALL, SPACING_SMALL
from ui.extraction_panel import ExtractionPanel
from ui.rom_extraction_panel import ROMExtractionPanel
from ui.styles.components import get_action_zone_style

# Layout constant matching main_window.py
LAYOUT_MARGINS = SPACING_SMALL  # 8px

from core.managers.application_state_manager import ApplicationStateManager
from core.managers.core_operations_manager import CoreOperationsManager
from core.services.rom_cache import ROMCache

if TYPE_CHECKING:
    from ui.rom_extraction.modules import Mesen2Module

logger = logging.getLogger(__name__)


class ExtractionWorkspace(QWidget):
    """Workspace for ROM and VRAM sprite extraction.

    This workspace provides:
    - ROM Extraction tab: Extract sprites directly from game ROM files
    - VRAM Extraction tab: Extract from emulator memory dumps (VRAM/CGRAM/OAM)
    - Action Zone: Shared buttons for extraction operations

    The Sprite Editor is now in a separate SpriteEditorWorkspace.
    """

    # Signals
    tab_changed = Signal(int)  # Emitted when tab selection changes

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        extraction_manager: CoreOperationsManager,
        state_manager: ApplicationStateManager,
        rom_cache: ROMCache,
        mesen2_module: Mesen2Module | None = None,
    ) -> None:
        super().__init__(parent)
        self._extraction_manager = extraction_manager
        self._state_manager = state_manager
        self._rom_cache = rom_cache
        self._mesen2_module = mesen2_module

        self._setup_ui()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        logger.debug("ExtractionWorkspace initialized")

    def _setup_ui(self) -> None:
        """Create the extraction workspace UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create tab widget for extraction methods (no Sprite Editor tab)
        self._extraction_tabs = QTabWidget()
        self._extraction_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._extraction_tabs.currentChanged.connect(self.tab_changed.emit)

        # ROM extraction tab (wrapped in scroll area)
        self._rom_extraction_panel = ROMExtractionPanel(
            parent=self,
            extraction_manager=self._extraction_manager,
            state_manager=self._state_manager,
            rom_cache=self._rom_cache,
            mesen2_module=self._mesen2_module,
        )

        rom_scroll = QScrollArea()
        rom_scroll.setWidgetResizable(True)
        rom_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rom_scroll.setFrameShape(QFrame.Shape.NoFrame)
        rom_scroll.setWidget(self._rom_extraction_panel)

        self._extraction_tabs.addTab(rom_scroll, "ROM Extraction")
        self._extraction_tabs.setTabToolTip(0, "Extract sprites directly from game ROM files")

        # VRAM extraction tab (wrapped in scroll area)
        self._extraction_panel = ExtractionPanel(settings_manager=self._state_manager)

        vram_scroll = QScrollArea()
        vram_scroll.setWidgetResizable(True)
        vram_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        vram_scroll.setFrameShape(QFrame.Shape.NoFrame)
        vram_scroll.setWidget(self._extraction_panel)

        self._extraction_tabs.addTab(vram_scroll, "VRAM Extraction")
        self._extraction_tabs.setTabToolTip(1, "Extract from emulator memory dumps (VRAM/CGRAM/OAM)")

        # Add tabs to layout
        main_layout.addWidget(self._extraction_tabs, 1)

        # ACTION ZONE: Fixed height, pinned to bottom
        self._action_zone = QWidget()
        self._action_zone.setObjectName("actionZone")
        self._action_zone.setStyleSheet(get_action_zone_style())
        self._action_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        action_zone_layout = QVBoxLayout(self._action_zone)
        action_zone_layout.setContentsMargins(LAYOUT_MARGINS, SPACING_COMPACT_SMALL, LAYOUT_MARGINS, LAYOUT_MARGINS)
        action_zone_layout.setSpacing(SPACING_COMPACT_SMALL)

        # Output settings and buttons will be added by managers
        main_layout.addWidget(self._action_zone)

    # Public accessors
    @property
    def extraction_tabs(self) -> QTabWidget:
        """Access the extraction tab widget."""
        return self._extraction_tabs

    @property
    def rom_extraction_panel(self) -> ROMExtractionPanel:
        """Access the ROM extraction panel."""
        return self._rom_extraction_panel

    @property
    def extraction_panel(self) -> ExtractionPanel:
        """Access the VRAM extraction panel."""
        return self._extraction_panel

    @property
    def action_zone(self) -> QWidget:
        """Access the action zone widget."""
        return self._action_zone

    def set_current_tab(self, index: int) -> None:
        """Set the current extraction tab."""
        self._extraction_tabs.setCurrentIndex(index)

    def current_tab_index(self) -> int:
        """Get the current extraction tab index."""
        return self._extraction_tabs.currentIndex()
