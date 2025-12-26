"""
Styled splitter component with consistent configuration

Provides a standardized splitter widget with consistent styling and behavior,
exactly replicating the splitter patterns from existing dialogs.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QWidget

# No longer need Optional import for Python 3.10+
from ui.styles import get_splitter_style


class StyledSplitter(QSplitter):
    """
    Splitter with consistent styling and configuration.

    Features:
    - Pre-configured with standardized styling
    - Consistent handle width and behavior
    - Helper methods for common splitter operations
    - Automatic stretch factor management

    Exactly replicates the splitter styling and behavior from existing dialogs.
    """

    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        handle_width: int = 8,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(orientation, parent)

        self._handle_width = handle_width

        # Apply consistent styling
        self.setHandleWidth(handle_width)
        self.setStyleSheet(get_splitter_style(handle_width))

    def add_widget(self, widget: QWidget, stretch_factor: int = 1) -> int:
        """
        Add a widget with specified stretch factor.

        Args:
            widget: Widget to add to the splitter
            stretch_factor: Stretch factor for the widget (default: 1)

        Returns:
            Index of the added widget
        """
        self.addWidget(widget)
        index = self.count() - 1  # Get the index of the just-added widget
        self.setStretchFactor(index, stretch_factor)
        return index

    def add_widgets(self, widgets: list[QWidget], stretch_factors: list[int] | None = None):
        """
        Add multiple widgets with optional stretch factors.

        Args:
            widgets: List of widgets to add
            stretch_factors: list[Any] of stretch factors (defaults to 1 for each)
        """
        if stretch_factors is None:
            stretch_factors = [1] * len(widgets)
        elif len(stretch_factors) != len(widgets):
            raise ValueError("Number of stretch factors must match number of widgets")

        for widget, stretch_factor in zip(widgets, stretch_factors, strict=False):
            self.add_widget(widget, stretch_factor)

    def set_panel_ratios(self, ratios: list[int]):
        """
        Set the size ratios for splitter panels.

        Args:
            ratios: List of ratios for each panel
        """
        if len(ratios) != self.count():
            raise ValueError(f"Expected {self.count()} ratios, got {len(ratios)}")

        for i, ratio in enumerate(ratios):
            self.setStretchFactor(i, ratio)

    def create_nested_splitter(
        self, orientation: Qt.Orientation, handle_width: int | None = None, stretch_factor: int = 1
    ) -> StyledSplitter:
        """
        Create and add a nested splitter.

        Args:
            orientation: Orientation for the nested splitter
            handle_width: Handle width (defaults to parent's handle width)
            stretch_factor: Stretch factor for the nested splitter

        Returns:
            The created nested splitter
        """
        if handle_width is None:
            handle_width = self._handle_width

        nested_splitter = StyledSplitter(orientation, handle_width)
        self.add_widget(nested_splitter, stretch_factor)
        return nested_splitter

    def get_handle_width(self) -> int:
        """Get the current handle width"""
        return self._handle_width

    def set_handle_width(self, width: int):
        """
        Update the handle width and refresh styling.

        Args:
            width: New handle width in pixels
        """
        self._handle_width = width
        self.setHandleWidth(width)
        self.setStyleSheet(get_splitter_style(width))
