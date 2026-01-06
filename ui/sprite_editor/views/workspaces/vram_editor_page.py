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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.components.navigation.workflow_nav_bar import WorkflowNavBar

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
        # Minimum width removed to allow flexible resizing

    def _setup_ui(self) -> None:
        """Create the VRAM workflow UI."""
        # Lazy imports to avoid circular import with edit_tab → edit_workspace
        from ..tabs import EditTab, ExtractTab, InjectTab, MultiPaletteTab

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Navigation Bar
        steps = ["Extract", "Edit", "Inject", "Multi-Palette"]
        self._nav_bar = WorkflowNavBar(steps)
        self._nav_bar.step_selected.connect(self._on_step_selected)
        layout.addWidget(self._nav_bar)

        # 2. Content Stack
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Create tabs
        self._extract_tab = ExtractTab(settings_manager=self._settings_manager)
        self._edit_tab = EditTab()
        self._inject_tab = InjectTab(settings_manager=self._settings_manager)
        self._multi_palette_tab = MultiPaletteTab()

        # Add tabs
        self._stack.addWidget(self._extract_tab)
        self._stack.addWidget(self._edit_tab)
        self._stack.addWidget(self._inject_tab)
        self._stack.addWidget(self._multi_palette_tab)

        # Hide "Pop Out Editor" button in embedded mode
        if hasattr(self._edit_tab, "detach_btn"):
            self._edit_tab.detach_btn.hide()

        # Forward ready_for_inject signal
        self._edit_tab.ready_for_inject.connect(self.ready_for_inject.emit)

        layout.addWidget(self._stack, 1)

    def _on_step_selected(self, index: int) -> None:
        """Handle step selection from nav bar."""
        self.set_current_tab(index)

    # Tab accessors
    @property
    def tab_widget(self) -> QStackedWidget:
        """Access the internal stack widget (deprecated name)."""
        return self._stack

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
        self._stack.setCurrentIndex(index)
        self._nav_bar.set_current_step(index)
        self.current_tab_changed.emit(index)

    def current_tab_index(self) -> int:
        """Get the current tab index."""
        return self._stack.currentIndex()

    def switch_to_inject_tab(self) -> None:
        """Switch to the Inject tab (index 2)."""
        self.set_current_tab(2)
