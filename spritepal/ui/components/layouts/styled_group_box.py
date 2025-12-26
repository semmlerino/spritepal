"""
Styled group box component with consistent theming

Provides a standardized group box widget with consistent styling and behavior,
exactly replicating the group box patterns from existing dialogs.
"""

from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLayout, QVBoxLayout, QWidget

from ui.styles import get_panel_style


class StyledGroupBox(QGroupBox):
    """
    Group box with consistent styling and theming.

    Features:
    - Pre-configured with standardized styling
    - Support for different panel types (default, primary, secondary)
    - Consistent border, padding, and title styling
    - Easy layout and widget management

    Exactly replicates the group box styling from existing dialogs.
    """

    def __init__(
        self,
        title: str = "",
        panel_type: str = "default",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)

        self._panel_type = panel_type

        # Apply consistent styling
        self.setStyleSheet(get_panel_style(panel_type))

    def set_panel_type(self, panel_type: str):
        """
        Update the panel type and refresh styling.

        Args:
            panel_type: Panel style type - "default", "primary", "secondary"
        """
        self._panel_type = panel_type
        self.setStyleSheet(get_panel_style(panel_type))

    def get_panel_type(self) -> str:
        """Get the current panel type"""
        return self._panel_type

    def set_layout_with_margins(self, layout: QLayout, margins: tuple[int, int, int, int] = (12, 12, 12, 12)):
        """
        Set layout with consistent margins.

        Args:
            layout: Layout to set
            margins: Tuple of (left, top, right, bottom) margins
        """
        layout.setContentsMargins(*margins)
        self.setLayout(layout)

    def add_widget_with_layout(self, widget: QWidget, layout_type: str = "vertical"):
        """
        Add a single widget with automatic layout creation.

        Args:
            widget: Widget to add
            layout_type: Type of layout - "vertical", "horizontal"
        """

        if layout_type == "vertical":
            layout = QVBoxLayout()
        elif layout_type == "horizontal":
            layout = QHBoxLayout()
        else:
            raise ValueError(f"Unknown layout type: {layout_type}")

        layout.addWidget(widget)
        self.set_layout_with_margins(layout)
