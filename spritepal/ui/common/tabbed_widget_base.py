"""
Base class for tabbed widgets with consistent styling and behavior.

Provides a foundation for creating organized, tab-based interfaces that follow
UI/UX principles like progressive disclosure and clear visual hierarchy.
"""
from __future__ import annotations

try:
    from typing_extensions import override
except ImportError:
    from typing_extensions import override

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.styles.theme import COLORS

from .spacing_constants import (
    FONT_SIZE_NORMAL,
    TAB_CONTENT_PADDING,
    TAB_MAX_WIDTH,
    TAB_MIN_WIDTH,
)


class TabbedWidgetBase(QWidget):
    """
    Base class for tabbed widgets with consistent styling.

    Features:
    - Consistent tab styling following SpritePal design
    - Automatic tab management and signal routing
    - Responsive layout with proper size constraints
    - Accessibility support with proper focus handling
    """

    # Signals
    tab_changed = Signal(int)  # Emitted when active tab changes

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._tab_widget: QTabWidget | None = None
        self._tabs: list[QWidget] = []

        self._setup_ui()
        self._setup_styling()

    def _setup_ui(self) -> None:
        """Set up the basic UI structure."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create tab widget
        self._tab_widget = QTabWidget(self)
        self._tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self._tab_widget.setTabsClosable(False)
        self._tab_widget.setMovable(False)
        self._tab_widget.setUsesScrollButtons(True)

        # Connect signals
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self._tab_widget)

        # Set size policies
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._tab_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def _setup_styling(self) -> None:
        """Apply consistent styling to the tab widget."""
        if self._tab_widget is None:
            return

        # Modern tab styling that matches SpritePal's dark theme
        if self._tab_widget:
            self._tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLORS["border"]};
                background-color: {COLORS["preview_background"]};
                border-radius: 4px;
                margin-top: -1px;
            }}

            QTabWidget::tab-bar {{
                alignment: left;
            }}

            QTabBar::tab {{
                background-color: {COLORS["input_background"]};
                color: {COLORS["text_muted"]};
                border: 1px solid {COLORS["border"]};
                border-bottom: none;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: {FONT_SIZE_NORMAL};
                font-weight: normal;
                min-width: 80px;
            }}

            QTabBar::tab:selected {{
                background-color: {COLORS["preview_background"]};
                color: {COLORS["highlight"]};
                border-bottom: 1px solid {COLORS["preview_background"]};
                font-weight: bold;
            }}

            QTabBar::tab:hover:!selected {{
                background-color: rgba(68, 136, 221, 0.1);
                color: {COLORS["highlight"]};
            }}

            QTabBar::tab:first {{
                margin-left: 0;
            }}

            QTabBar::tab:only-one {{
                margin: 0;
            }}
        """)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change events."""
        self.tab_changed.emit(index)
        self._on_tab_activated(index)

    def _on_tab_activated(self, index: int) -> None:
        """Override this method to handle tab activation in subclasses."""

    def add_tab(self, widget: QWidget, title: str, tooltip: str = "") -> int:
        """
        Add a tab to the widget.

        Args:
            widget: The widget to add as tab content
            title: The tab title
            tooltip: Optional tooltip for the tab

        Returns:
            The index of the added tab
        """
        if self._tab_widget is None:
            return -1

        # Wrap the widget in a container with proper padding
        container = self._create_tab_container(widget)

        # Add to tab widget
        index = self._tab_widget.addTab(container, title)

        if tooltip:
            self._tab_widget.setTabToolTip(index, tooltip)

        # Store reference
        self._tabs.append(container)

        return index

    def _create_tab_container(self, content_widget: QWidget) -> QWidget:
        """
        Create a properly styled container for tab content.

        Args:
            content_widget: The actual content widget

        Returns:
            A container widget with proper padding and layout
        """
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(
            TAB_CONTENT_PADDING,
            TAB_CONTENT_PADDING,
            TAB_CONTENT_PADDING,
            TAB_CONTENT_PADDING
        )
        layout.setSpacing(TAB_CONTENT_PADDING)

        # Add content widget
        layout.addWidget(content_widget)

        # Set size constraints
        container.setMinimumWidth(TAB_MIN_WIDTH)
        container.setMaximumWidth(TAB_MAX_WIDTH)
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        return container

    def remove_tab(self, index: int) -> None:
        """Remove a tab by index."""
        if self._tab_widget is None or not (0 <= index < len(self._tabs)):
            return

        self._tab_widget.removeTab(index)
        self._tabs.pop(index)

    def set_current_tab(self, index: int) -> None:
        """Set the currently active tab."""
        if self._tab_widget is not None and 0 <= index < self._tab_widget.count():
            self._tab_widget.setCurrentIndex(index)

    def current_tab_index(self) -> int:
        """Get the index of the currently active tab."""
        return self._tab_widget.currentIndex() if self._tab_widget is not None else -1

    def current_tab_widget(self) -> QWidget | None:
        """Get the currently active tab widget."""
        if self._tab_widget is None:
            return None

        index = self._tab_widget.currentIndex()
        if 0 <= index < len(self._tabs):
            return self._tabs[index]

        return None

    def tab_count(self) -> int:
        """Get the number of tabs."""
        return self._tab_widget.count() if self._tab_widget is not None else 0

    def set_tab_enabled(self, index: int, enabled: bool) -> None:
        """Enable or disable a tab."""
        if self._tab_widget is not None and 0 <= index < self._tab_widget.count():
            self._tab_widget.setTabEnabled(index, enabled)

    def set_tab_visible(self, index: int, visible: bool) -> None:
        """Show or hide a tab."""
        if self._tab_widget is not None and 0 <= index < self._tab_widget.count():
            self._tab_widget.setTabVisible(index, visible)

    def set_tab_text(self, index: int, text: str) -> None:
        """Set the text of a tab."""
        if self._tab_widget is not None and 0 <= index < self._tab_widget.count():
            self._tab_widget.setTabText(index, text)

    def set_tab_tooltip(self, index: int, tooltip: str) -> None:
        """Set the tooltip of a tab."""
        if self._tab_widget is not None and 0 <= index < self._tab_widget.count():
            self._tab_widget.setTabToolTip(index, tooltip)

    @override
    def sizeHint(self):
        """Provide appropriate size hint for the tabbed widget."""
        if self._tab_widget is not None:
            return self._tab_widget.sizeHint()
        return super().sizeHint()

    @override
    def minimumSizeHint(self):
        """Provide minimum size hint for the tabbed widget."""
        if self._tab_widget is not None:
            return self._tab_widget.minimumSizeHint()
        return super().minimumSizeHint()
