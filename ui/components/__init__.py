"""
SpritePal UI Components

Reusable dialog architecture components for consistent UI development.
"""

from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QTabWidget, QWidget

# Import all components from subdirectories
from .base.dialog_base import DialogBase
from .inputs.file_selector import FileSelector
from .inputs.form_row import (
    FormRow,
    create_horizontal_form_row,
    create_vertical_form_row,
)
from .inputs.hex_offset_input import HexOffsetInput


class TabbedDialog(DialogBase):
    """
    Dialog with a QTabWidget as main content area.

    Provides proper tab management functionality while maintaining
    DialogBase's initialization safety patterns.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str | None = None,
        modal: bool = True,
        min_size: tuple[int | None, int | None] | None = None,
        size: tuple[int, int] | None = None,
        with_status_bar: bool = False,
        with_button_box: bool = True,
        tab_position: QTabWidget.TabPosition = QTabWidget.TabPosition.North,
        **kwargs: Any,  # pyright: ignore[reportExplicitAny] - compatibility kwargs
    ) -> None:
        """
        Initialize tabbed dialog.

        Args:
            parent: Parent widget (optional)
            title: Window title (optional)
            modal: Whether dialog should be modal (default: True)
            min_size: Minimum size as (width, height) tuple, None for no limit
            size: Fixed size as (width, height) tuple (optional)
            with_status_bar: Whether to add a status bar
            with_button_box: Whether to add a standard button box (default: True)
            tab_position: Position of tabs (default: Qt.TabPosition.North)
            **kwargs: Additional keyword arguments passed to DialogBase
        """
        # Step 1: Declare instance variables FIRST
        self._tab_position = tab_position
        self._main_tab_widget: QTabWidget | None = None

        # Step 2: Call parent init
        super().__init__(
            parent=parent,
            title=title,
            modal=modal,
            min_size=min_size,
            size=size,
            with_status_bar=with_status_bar,
            with_button_box=with_button_box,
            **kwargs,
        )

    @override
    def _setup_ui(self) -> None:
        """Set up the tabbed UI structure."""
        # Create main tab widget and replace content widget
        self._main_tab_widget = QTabWidget(self)
        self._main_tab_widget.setTabPosition(self._tab_position)

        # Replace content widget with tab widget
        self.main_layout.removeWidget(self.content_widget)
        self.content_widget.deleteLater()

        # Insert tab widget in same position as content widget
        # Insert before button box if it exists
        if self.button_box is not None:
            insert_index = self.main_layout.indexOf(self.button_box)
            self.main_layout.insertWidget(insert_index, self._main_tab_widget)
        else:
            self.main_layout.addWidget(self._main_tab_widget)

        # Update content widget reference for compatibility
        self.content_widget = self._main_tab_widget

        # Update public alias used by DialogBase and tests
        self.tab_widget = self._main_tab_widget
        # Also update private reference for DialogBase compatibility
        self._tab_widget = self._main_tab_widget

    @override
    def add_tab(self, widget: QWidget, label: str) -> None:
        """
        Add a tab to the dialog.

        Args:
            widget: The widget to add as a tab
            label: The tab label
        """
        if self._main_tab_widget is None:
            raise RuntimeError("TabbedDialog not properly initialized - tab widget is None")

        self._main_tab_widget.addTab(widget, label)

    def add_tab_with_index(self, widget: QWidget, label: str) -> int:
        """
        Add a tab to the dialog and return the index.

        Args:
            widget: The widget to add as a tab
            label: The tab label

        Returns:
            The index of the added tab
        """
        if self._main_tab_widget is None:
            raise RuntimeError("TabbedDialog not properly initialized - tab widget is None")

        return self._main_tab_widget.addTab(widget, label)

    def remove_tab(self, index: int) -> None:
        """
        Remove a tab from the dialog.

        Args:
            index: Index of tab to remove
        """
        if self._main_tab_widget is not None:
            self._main_tab_widget.removeTab(index)

    @override
    def set_current_tab(self, index: int) -> None:
        """
        Set the current tab.

        Args:
            index: Tab index to switch to
        """
        if self._main_tab_widget is not None:
            self._main_tab_widget.setCurrentIndex(index)

    @override
    def get_current_tab_index(self) -> int:
        """
        Get the current tab index.

        Returns:
            Current tab index, or -1 if no tabs exist
        """
        if self._main_tab_widget is not None:
            return self._main_tab_widget.currentIndex()
        return -1


class SplitterDialog(DialogBase):
    """
    Dialog with a QSplitter as main content area.

    Provides proper splitter management functionality while maintaining
    DialogBase's initialization safety patterns.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str | None = None,
        modal: bool = True,
        min_size: tuple[int | None, int | None] | None = None,
        size: tuple[int, int] | None = None,
        with_status_bar: bool = False,
        with_button_box: bool = True,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        splitter_handle_width: int = 8,
        **kwargs: Any,  # pyright: ignore[reportExplicitAny] - compatibility kwargs
    ) -> None:
        """
        Initialize splitter dialog.

        Args:
            parent: Parent widget (optional)
            title: Window title (optional)
            modal: Whether dialog should be modal (default: True)
            min_size: Minimum size as (width, height) tuple, None for no limit
            size: Fixed size as (width, height) tuple (optional)
            with_status_bar: Whether to add a status bar
            with_button_box: Whether to add a standard button box (default: True)
            orientation: Splitter orientation (default: Qt.Orientation.Horizontal)
            splitter_handle_width: Handle width for splitter (default: 8)
            **kwargs: Additional keyword arguments passed to DialogBase
        """
        # Step 1: Declare instance variables FIRST
        self._splitter_orientation = orientation
        self._splitter_handle_width = splitter_handle_width
        self._main_splitter: QSplitter | None = None

        # Step 2: Call parent init (pass None for orientation to prevent auto-creation)
        super().__init__(
            parent=parent,
            title=title,
            modal=modal,
            min_size=min_size,
            size=size,
            with_status_bar=with_status_bar,
            with_button_box=with_button_box,
            orientation=None,  # Don't auto-create, we'll create our own
            splitter_handle_width=splitter_handle_width,
            **kwargs,
        )

    @override
    def _setup_ui(self) -> None:
        """Set up the splitter UI structure."""
        # Create main splitter and replace content widget
        self._main_splitter = QSplitter(self._splitter_orientation)
        self._main_splitter.setHandleWidth(self._splitter_handle_width)

        # Replace content widget with splitter
        self.main_layout.removeWidget(self.content_widget)
        self.content_widget.deleteLater()

        # Insert splitter in same position as content widget
        # Insert before button box if it exists
        if self.button_box is not None:
            insert_index = self.main_layout.indexOf(self.button_box)
            self.main_layout.insertWidget(insert_index, self._main_splitter)
        else:
            self.main_layout.addWidget(self._main_splitter)

        # Update content widget reference for compatibility
        self.content_widget = self._main_splitter

        # Update main_splitter reference for DialogBase compatibility
        self.main_splitter = self._main_splitter

    def add_pane(self, widget: QWidget) -> int:
        """
        Add a pane (widget) to the splitter.

        Args:
            widget: The widget to add as a pane

        Returns:
            The index of the added pane
        """
        if self._main_splitter is None:
            raise RuntimeError("SplitterDialog not properly initialized - splitter is None")

        self._main_splitter.addWidget(widget)
        return self._main_splitter.count() - 1

    def set_orientation(self, orientation: Qt.Orientation) -> None:
        """
        Set the splitter orientation.

        Args:
            orientation: Qt.Orientation value (Horizontal or Vertical)
        """
        if self._main_splitter is not None:
            self._main_splitter.setOrientation(orientation)
            self._splitter_orientation = orientation

    def set_sizes(self, sizes: list[int]) -> None:
        """
        Set the sizes of the splitter panes.

        Args:
            sizes: List of sizes for each pane
        """
        if self._main_splitter is not None:
            self._main_splitter.setSizes(sizes)

    @override
    def add_panel(self, widget: QWidget, stretch_factor: int = 1) -> None:
        """
        Add a panel to the splitter (alias for add_pane for compatibility).

        Args:
            widget: The widget to add
            stretch_factor: Stretch factor for the widget (applied after adding)
        """
        pane_index = self.add_pane(widget)
        if self._main_splitter is not None:
            self._main_splitter.setStretchFactor(pane_index, stretch_factor)


__all__ = [
    "DialogBase",
    "FileSelector",
    "FormRow",
    "HexOffsetInput",
    "SplitterDialog",
    "TabbedDialog",
    "create_horizontal_form_row",
    "create_vertical_form_row",
]
