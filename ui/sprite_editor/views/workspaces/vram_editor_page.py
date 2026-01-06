#!/usr/bin/env python3
"""
VRAM editor page containing the standard sprite editing workflow tabs.

This page provides the Extract → Edit → Inject → Multi-Palette workflow
for sprites captured from VRAM. It's one of the pages in the mode stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager

    from ..tabs import EditTab, ExtractTab, InjectTab, MultiPaletteTab


class VRAMEditorPage(QWidget):
    """VRAM workflow page with Extract/Edit/Inject/Multi-Palette tabs.

    This page provides the standard VRAM sprite editing workflow:
    - Extract: Load sprites from VRAM captures
    - Edit: Pixel editing with tool panels
    - Inject: Write edited sprites back to ROM
    - Multi-Palette: View sprites with multiple palettes
    """

    # Signals
    current_tab_changed = Signal(int)  # Tab index changed
    ready_for_inject = Signal()  # Edit tab signals ready for inject

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings_manager: ApplicationStateManager | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings_manager = settings_manager
        self._setup_ui()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Set minimum width at page root
        self.setMinimumWidth(500)

    def _setup_ui(self) -> None:
        """Create the VRAM workflow tabs."""
        # Lazy imports to avoid circular import with edit_tab → edit_workspace
        from ..tabs import EditTab, ExtractTab, InjectTab, MultiPaletteTab

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab widget for VRAM workflow
        self._tab_widget = QTabWidget()
        self._tab_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._tab_widget.currentChanged.connect(self.current_tab_changed.emit)

        # Create tabs
        self._extract_tab = ExtractTab(settings_manager=self._settings_manager)
        self._edit_tab = EditTab()
        self._inject_tab = InjectTab(settings_manager=self._settings_manager)
        self._multi_palette_tab = MultiPaletteTab()

        # Add tabs
        self._tab_widget.addTab(self._extract_tab, "Extract")
        self._tab_widget.addTab(self._edit_tab, "Edit")
        self._tab_widget.addTab(self._inject_tab, "Inject")
        self._tab_widget.addTab(self._multi_palette_tab, "Multi-Palette")

        # Hide "Pop Out Editor" button in embedded mode
        if hasattr(self._edit_tab, "detach_btn"):
            self._edit_tab.detach_btn.hide()

        # Forward ready_for_inject signal
        self._edit_tab.ready_for_inject.connect(self.ready_for_inject.emit)

        layout.addWidget(self._tab_widget, 1)

    # Tab accessors
    @property
    def tab_widget(self) -> QTabWidget:
        """Access the internal tab widget."""
        return self._tab_widget

    @property
    def extract_tab(self) -> ExtractTab:
        """Access the Extract tab."""
        return self._extract_tab

    @property
    def edit_tab(self) -> EditTab:
        """Access the Edit tab."""
        return self._edit_tab

    @property
    def inject_tab(self) -> InjectTab:
        """Access the Inject tab."""
        return self._inject_tab

    @property
    def multi_palette_tab(self) -> MultiPaletteTab:
        """Access the Multi-Palette tab."""
        return self._multi_palette_tab

    def set_current_tab(self, index: int) -> None:
        """Set the current tab by index."""
        self._tab_widget.setCurrentIndex(index)

    def current_tab_index(self) -> int:
        """Get the current tab index."""
        return self._tab_widget.currentIndex()

    def switch_to_inject_tab(self) -> None:
        """Switch to the Inject tab (index 2)."""
        self._tab_widget.setCurrentIndex(2)
