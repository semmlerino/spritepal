"""
Manual Offset Dialog Layout Manager

This module provides specialized layout management for the Manual Offset Dialog,
handling dialog-specific requirements like dynamic splitter ratios and tab-specific
layout configurations.

This extends the general layout utilities from ui.common.layout_manager with
dialog-specific functionality.

Key responsibilities:
- Dialog-specific layout constants
- Dynamic splitter ratio management based on active tab
- Manual offset dialog-specific size constraints
- Tab-specific layout adjustments
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QSizePolicy, QSplitter, QTabWidget, QVBoxLayout, QWidget

from ui.styles.theme import COLORS

if TYPE_CHECKING:
    class DialogProtocol(Protocol):
        """Protocol for dialogs that use LayoutManager."""
        main_splitter: QSplitter | None
        tab_widget: QTabWidget | None
        def width(self) -> int: ...

# Layout constants for consistent spacing
LAYOUT_SPACING = 8
LAYOUT_MARGINS = 8
COMPACT_SPACING = 4
COMPACT_MARGINS = 5
BUTTON_HEIGHT = 32
SPLITTER_HANDLE_WIDTH = 8

# Size constraints
MIN_LEFT_PANEL_WIDTH = 350
MAX_LEFT_PANEL_WIDTH = 500
MIN_RIGHT_PANEL_WIDTH = 400
MAX_MINI_MAP_HEIGHT = 60
MIN_MINI_MAP_HEIGHT = 40
MIN_TAB_HEIGHT = 300

# Tab-specific layout ratios
TAB_RATIOS = {
    0: 0.35,  # Browse tab - compact controls
    1: 0.35,  # Smart tab - compact controls
    2: 0.35,  # History tab - list view
    3: 0.40,  # Gallery tab - needs more controls
}

class LayoutManager:
    """Manages layout configuration for Manual Offset Dialog."""

    # Constants accessible as instance attributes
    SPLITTER_HANDLE_WIDTH = SPLITTER_HANDLE_WIDTH
    MIN_MINI_MAP_HEIGHT = MIN_MINI_MAP_HEIGHT
    MAX_MINI_MAP_HEIGHT = MAX_MINI_MAP_HEIGHT

    if TYPE_CHECKING:
        def __init__(self, dialog: DialogProtocol) -> None:
            """
            Initialize layout manager.

            Args:
                dialog: The parent ManualOffsetDialog instance
            """
            self.dialog: DialogProtocol = dialog
            self._initial_setup_done: bool = False
            self._current_ratio: float = 0.35
    else:
        def __init__(self, dialog: QWidget) -> None:
            """
            Initialize layout manager.

            Args:
                dialog: The parent ManualOffsetDialog instance
            """
            self.dialog = dialog
            self._initial_setup_done = False

    def setup_left_panel_layout(self, panel: QWidget, tab_widget: QWidget,
                               status_widget: QWidget, rom_map: QWidget) -> None:
        """
        Configure left panel layout to eliminate empty space.

        Args:
            panel: The left panel widget
            tab_widget: The tab widget container
            status_widget: The collapsible status panel
            rom_map: The mini ROM map widget
        """
        layout = panel.layout()
        if not isinstance(layout, QVBoxLayout):
            return

        # Clear any existing stretch items
        while layout.count() > 0:
            item = layout.takeAt(0)
            if item.widget():
                # Re-add widgets, skip stretch items
                pass

        # Configure layout spacing
        layout.setSpacing(COMPACT_SPACING)
        layout.setContentsMargins(COMPACT_MARGINS, COMPACT_MARGINS,
                                 COMPACT_MARGINS, COMPACT_MARGINS)

        # Add widgets with proper stretch factors
        # Tab widget should expand to fill available space
        tab_widget.setSizePolicy(QSizePolicy.Policy.Preferred,
                                QSizePolicy.Policy.Expanding)
        tab_widget.setMinimumHeight(MIN_TAB_HEIGHT)
        layout.addWidget(tab_widget, 1)  # Give it stretch to expand

        # Status panel - fixed size
        status_widget.setSizePolicy(QSizePolicy.Policy.Preferred,
                                   QSizePolicy.Policy.Maximum)
        layout.addWidget(status_widget, 0)  # No stretch

        # Mini ROM map - fixed height
        rom_map.setMaximumHeight(MAX_MINI_MAP_HEIGHT)
        rom_map.setMinimumHeight(MIN_MINI_MAP_HEIGHT)
        rom_map.setSizePolicy(QSizePolicy.Policy.Preferred,
                            QSizePolicy.Policy.Fixed)
        layout.addWidget(rom_map, 0)  # No stretch

        # DO NOT add stretch at the end - let tab widget expand

    def setup_right_panel_layout(self, panel: QWidget, preview_widget: QWidget,
                                title_label: QLabel | None = None) -> None:
        """
        Configure right panel layout for preview.

        Args:
            panel: The right panel widget
            preview_widget: The sprite preview widget
            title_label: Optional title label
        """
        layout = panel.layout()
        if not isinstance(layout, QVBoxLayout):
            return

        # Configure layout spacing
        layout.setSpacing(LAYOUT_SPACING)
        layout.setContentsMargins(COMPACT_MARGINS, COMPACT_MARGINS,
                                 COMPACT_MARGINS, COMPACT_MARGINS)

        # Clear existing items
        while layout.count() > 0:
            layout.takeAt(0)

        # Add title if provided
        if title_label:
            title_label.setSizePolicy(QSizePolicy.Policy.Preferred,
                                     QSizePolicy.Policy.Maximum)
            layout.addWidget(title_label, 0)

        # Preview widget should fill all available space
        preview_widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                                    QSizePolicy.Policy.Expanding)
        layout.addWidget(preview_widget, 1)  # Give it all stretch

    def configure_splitter(self, splitter: QSplitter, left_panel: QWidget,
                         right_panel: QWidget) -> None:
        """
        Configure main splitter with proper size policies.

        Args:
            splitter: The main splitter widget
            left_panel: The left panel widget
            right_panel: The right panel widget
        """
        # Set splitter properties
        splitter.setHandleWidth(SPLITTER_HANDLE_WIDTH)
        splitter.setChildrenCollapsible(False)

        # Configure panel size policies
        left_panel.setSizePolicy(QSizePolicy.Policy.Preferred,
                                QSizePolicy.Policy.Expanding)
        left_panel.setMinimumWidth(MIN_LEFT_PANEL_WIDTH)
        left_panel.setMaximumWidth(MAX_LEFT_PANEL_WIDTH)

        right_panel.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
        right_panel.setMinimumWidth(MIN_RIGHT_PANEL_WIDTH)

        # Set stretch factors - right panel gets more stretch
        splitter.setStretchFactor(0, 1)  # Left panel - less stretch
        splitter.setStretchFactor(1, 3)  # Right panel - more stretch

    def update_for_tab(self, tab_index: int, dialog_width: int) -> None:
        """
        Update splitter sizes based on active tab.

        Args:
            tab_index: Index of the active tab
            dialog_width: Current dialog width
        """
        if not self.dialog.main_splitter:
            return

        # Get ratio for this tab
        ratio = TAB_RATIOS.get(tab_index, 0.35)

        # Calculate sizes
        left_width = int(dialog_width * ratio)
        left_width = max(MIN_LEFT_PANEL_WIDTH,
                        min(left_width, MAX_LEFT_PANEL_WIDTH))
        right_width = dialog_width - left_width

        # Apply sizes
        self.dialog.main_splitter.setSizes([left_width, right_width])

        # Store ratio for resize events
        self._current_ratio = ratio

    def handle_resize(self, new_width: int) -> None:
        """
        Handle dialog resize maintaining proportions.

        Args:
            new_width: New dialog width
        """
        if not self.dialog.main_splitter:
            return

        # Use stored ratio or calculate from current sizes
        if hasattr(self, '_current_ratio'):
            ratio = self._current_ratio
        else:
            sizes = self.dialog.main_splitter.sizes()
            total = sum(sizes)
            ratio = sizes[0] / total if total > 0 else 0.35

        # Calculate new sizes
        left_width = int(new_width * ratio)
        left_width = max(MIN_LEFT_PANEL_WIDTH,
                        min(left_width, MAX_LEFT_PANEL_WIDTH))
        right_width = new_width - left_width

        # Apply sizes
        self.dialog.main_splitter.setSizes([left_width, right_width])

    def create_section_title(self, text: str) -> QLabel:
        """
        Create a styled section title label.

        Args:
            text: Title text

        Returns:
            Styled QLabel
        """
        title = QLabel(text)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {COLORS['highlight']}; padding: 2px 4px; border-radius: 3px;")
        title.setSizePolicy(QSizePolicy.Policy.Preferred,
                          QSizePolicy.Policy.Maximum)
        return title

    def apply_standard_layout(self, layout: QVBoxLayout, spacing_type: str = 'normal') -> None:
        """
        Apply standard layout settings based on spacing type.

        Args:
            layout: The layout to configure
            spacing_type: Either 'normal', 'compact', or other spacing mode
        """
        if spacing_type == 'compact':
            layout.setSpacing(COMPACT_SPACING)
            layout.setContentsMargins(COMPACT_MARGINS, COMPACT_MARGINS,
                                    COMPACT_MARGINS, COMPACT_MARGINS)
        else:
            layout.setSpacing(LAYOUT_SPACING)
            layout.setContentsMargins(LAYOUT_MARGINS, LAYOUT_MARGINS,
                                    LAYOUT_MARGINS, LAYOUT_MARGINS)

    def remove_all_stretches(self, layout: QVBoxLayout) -> None:
        """
        Remove all stretch spacer items from a layout.

        Args:
            layout: The layout to clean of stretch items
        """
        for i in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(i)
            if item and not item.widget():
                # This is likely a stretch item or spacer
                layout.takeAt(i)

    def on_dialog_show(self) -> None:
        """Handle dialog show event - perform initial setup."""
        if not self._initial_setup_done:
            # Set initial splitter ratio
            if self.dialog.tab_widget:
                current_tab = self.dialog.tab_widget.currentIndex()
                self.update_for_tab(current_tab, self.dialog.width())
            self._initial_setup_done = True

    def fix_empty_space_issue(self) -> None:
        """
        Fix the empty space issue in the left panel.
        This is the main fix that should be called after UI setup.
        """
        # Find the left panel
        if not self.dialog.main_splitter or self.dialog.main_splitter.count() < 2:
            return

        left_panel = self.dialog.main_splitter.widget(0)
        if not left_panel:
            return

        layout = left_panel.layout()
        if not isinstance(layout, QVBoxLayout):
            return

        # Remove any stretch items at the end
        for i in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(i)
            if item and not item.widget():
                # This is likely a stretch item
                layout.takeAt(i)

        # Ensure tab widget has proper stretch
        if self.dialog.tab_widget:
            # Find tab widget in layout
            for i in range(layout.count()):
                if layout.itemAt(i).widget() == self.dialog.tab_widget:
                    # Remove and re-add with stretch
                    layout.takeAt(i)
                    self.dialog.tab_widget.setSizePolicy(
                        QSizePolicy.Policy.Preferred,
                        QSizePolicy.Policy.Expanding
                    )
                    layout.insertWidget(i, self.dialog.tab_widget, 1)  # Add with stretch
                    break
