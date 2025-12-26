"""
Collapsible Group Box for Progressive Disclosure.

Implements a group box that can be collapsed/expanded to hide advanced options,
following the principle of progressive disclosure to reduce UI complexity.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import cast

try:
    from typing import override
except ImportError:
    from typing import override

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.styles.theme import COLORS

from .spacing_constants import (
    COLLAPSIBLE_ANIMATION_DURATION,
    FONT_SIZE_MEDIUM,
    GROUP_PADDING,
    QWIDGETSIZE_MAX,
    SPACING_SMALL,
    TOGGLE_BUTTON_SIZE,
)


def _is_headless_environment() -> bool:
    """Detect if we're running in a headless environment (CI, offscreen, no display)."""
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return True
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return True
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return True
    try:
        app = QApplication.instance()
        if app:
            qapp = cast(QApplication, app)
            screen = qapp.primaryScreen()
            if not screen or screen.geometry().width() == 0:
                return True
    except Exception:
        return True
    return False


class CollapsibleGroupBox(QFrame):
    """
    A group box that can be collapsed/expanded with smooth animation.

    Features:
    - Smooth expand/collapse animation (or instant in headless mode)
    - Customizable title and collapse button
    - Signal emission on state change
    - Proper size policies for layout integration
    - Safe operation in headless environments
    """

    # Signals
    collapsed: Signal = Signal(bool)  # Emitted when collapse state changes

    def __init__(
        self, title: str = "", collapsed: bool = False, muted: bool = False, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)

        # Declare all instance variables with type hints first
        self._is_collapsed: bool = collapsed
        self._muted: bool = muted  # Use subdued styling for optional sections
        self._animation_duration: int = COLLAPSIBLE_ANIMATION_DURATION
        self._content_widget: QWidget | None = None
        self._content_layout: QVBoxLayout | None = None
        self._animation: QPropertyAnimation | None = None
        self._title_label: QLabel
        self._toggle_button: QPushButton
        self._animation_connections: list[Callable[[], None]] = []  # Track our connections
        self._is_headless = _is_headless_environment()

        # Setup UI components first
        self._setup_ui(title)
        self._setup_animation()

        # Set initial state after UI is created
        if collapsed:
            # Set collapsed state immediately without animation for initial setup
            self._is_collapsed = True
            self._update_button_text()
            if self._content_widget is not None:
                self._content_widget.setMaximumHeight(0)
                self._content_widget.setVisible(False)

    def _setup_ui(self, title: str) -> None:
        """Set up the user interface."""
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            CollapsibleGroupBox {{
                border: 1px solid {COLORS["preview_background"]};
                border-radius: 4px;
                background-color: {COLORS["preview_background"]};
                margin: 2px;
            }}
        """)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header with title and collapse button
        header_widget = QWidget(self)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(GROUP_PADDING, GROUP_PADDING, GROUP_PADDING, GROUP_PADDING)
        header_layout.setSpacing(SPACING_SMALL)

        # Title label - use muted color for optional sections
        self._title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(int(FONT_SIZE_MEDIUM.replace("px", "")))
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        title_color = COLORS["text_muted"] if self._muted else COLORS["highlight"]
        self._title_label.setStyleSheet(f"color: {title_color};")
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        # Collapse/expand button
        self._toggle_button = QPushButton(self)
        self._toggle_button.setFixedSize(TOGGLE_BUTTON_SIZE, TOGGLE_BUTTON_SIZE)
        if self._toggle_button:
            self._toggle_button.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
                color: {COLORS["text_muted"]};
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {COLORS["highlight"]};
                background-color: rgba(68, 136, 221, 0.1);
                border-radius: 10px;
            }}
        """)
        _ = self._toggle_button.clicked.connect(self.toggle_collapsed)
        self._update_button_text()
        header_layout.addWidget(self._toggle_button)

        main_layout.addWidget(header_widget)

        # Content widget (will be animated)
        self._content_widget = QWidget(self)
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(GROUP_PADDING, 0, GROUP_PADDING, GROUP_PADDING)
        self._content_layout.setSpacing(SPACING_SMALL)

        main_layout.addWidget(self._content_widget)

        # Set size policies - use Minimum vertical so collapsed state doesn't expand
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._content_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

    def _setup_animation(self) -> None:
        """Set up the collapse/expand animation (skipped in headless mode)."""
        if self._content_widget is None or self._is_headless:
            return

        # Create real QPropertyAnimation only in non-headless mode
        self._animation = QPropertyAnimation(self._content_widget, b"maximumHeight")
        self._animation.setDuration(self._animation_duration)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def _update_button_text(self) -> None:
        """Update the toggle button text based on collapsed state."""
        if self._is_collapsed:
            self._toggle_button.setText("▶")  # Pointing right (collapsed)
            self._toggle_button.setToolTip("Expand section")
        else:
            if self._toggle_button:
                self._toggle_button.setText("▼")  # Pointing down (expanded)
            self._toggle_button.setToolTip("Collapse section")

    def toggle_collapsed(self) -> None:
        """Toggle the collapsed state with animation."""
        self.set_collapsed(not self._is_collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        """Set the collapsed state with smooth animation (or instant in headless mode)."""
        if self._is_collapsed == collapsed:
            return

        self._is_collapsed = collapsed
        self._update_button_text()

        if self._content_widget is None:
            self.collapsed.emit(collapsed)
            return

        # Headless mode: instant changes without animation
        if self._animation is None:
            if collapsed:
                self._content_widget.setVisible(False)
                self._content_widget.setMaximumHeight(0)
            else:
                self._content_widget.setVisible(True)
                self._content_widget.setMinimumHeight(0)
                self._content_widget.setMaximumHeight(QWIDGETSIZE_MAX)
            self.collapsed.emit(collapsed)
            return

        # Animated mode: use QPropertyAnimation
        self._animation.stop()

        # Disconnect our previous connections
        for connection in self._animation_connections:
            try:
                connection()
            except RuntimeError as e:
                if str(e) != "wrapped C/C++ object has been deleted":
                    raise
            except TypeError:
                pass
        self._animation_connections.clear()

        if collapsed:
            # Collapse: animate to height 0
            start_height = self._content_widget.height()
            self._animation.setStartValue(start_height)
            self._animation.setEndValue(0)

            def on_collapse_value_changed(value: int) -> None:
                if self._content_widget is not None:
                    self._content_widget.setMaximumHeight(value)

            self._animation.valueChanged.connect(on_collapse_value_changed)

            def on_collapse_finished() -> None:
                if self._is_collapsed and self._content_widget is not None:
                    self._content_widget.setVisible(False)
                    self._content_widget.setMaximumHeight(0)

            self._animation.finished.connect(on_collapse_finished)

            def disconnect_collapse_value() -> None:
                if self._animation:
                    self._animation.valueChanged.disconnect(on_collapse_value_changed)

            def disconnect_collapse_finished() -> None:
                if self._animation:
                    self._animation.finished.disconnect(on_collapse_finished)

            self._animation_connections = [disconnect_collapse_value, disconnect_collapse_finished]
        else:
            # Expand: animate to natural height
            self._content_widget.setVisible(True)
            natural_height = self._calculate_natural_height()
            if natural_height <= 0:
                natural_height = 80

            self._content_widget.setMaximumHeight(0)
            self._animation.setStartValue(0)
            self._animation.setEndValue(natural_height)

            def on_value_changed(value: int) -> None:
                if self._content_widget is not None:
                    self._content_widget.setMaximumHeight(value)

            self._animation.valueChanged.connect(on_value_changed)

            def on_finished() -> None:
                if not self._is_collapsed and self._content_widget is not None:
                    self._content_widget.setMinimumHeight(0)
                    self._content_widget.setMaximumHeight(QWIDGETSIZE_MAX)

            self._animation.finished.connect(on_finished)

            def disconnect_expand_value() -> None:
                if self._animation:
                    self._animation.valueChanged.disconnect(on_value_changed)

            def disconnect_expand_finished() -> None:
                if self._animation:
                    self._animation.finished.disconnect(on_finished)

            self._animation_connections = [disconnect_expand_value, disconnect_expand_finished]

        self._animation.start()
        self.collapsed.emit(collapsed)

    def is_collapsed(self) -> bool:
        """Check if the group box is currently collapsed."""
        return self._is_collapsed

    def set_title(self, title: str) -> None:
        """Set the title text."""
        if self._title_label:
            self._title_label.setText(title)

    def title(self) -> str:
        """Get the current title text."""
        return self._title_label.text()

    def _calculate_natural_height(self) -> int:
        """Calculate natural height of content without forcing layout updates."""
        if self._content_widget is None:
            return 0

        # First try: use the layout's size hint directly
        if self._content_layout is not None:
            layout_hint = self._content_layout.sizeHint()
            if layout_hint.height() > 0:
                return layout_hint.height()

        # Second try: calculate from child widget size hints
        total_height = 0
        if self._content_layout is not None:
            spacing = self._content_layout.spacing()
            margins = self._content_layout.contentsMargins()
            total_height += margins.top() + margins.bottom()

            child_count = 0
            for i in range(self._content_layout.count()):
                item = self._content_layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if widget is not None:
                        widget_hint = widget.sizeHint()
                        if widget_hint.height() > 0:
                            total_height += widget_hint.height()
                            child_count += 1
                elif item:
                    # item.layout() returns the layout if this item is a layout
                    layout = item.layout()
                    # Type stubs may indicate layout is never None, but it can be for widget items
                    layout_hint = layout.sizeHint()
                    if layout_hint.height() > 0:
                        total_height += layout_hint.height()
                        child_count += 1

            # Add spacing between items
            if child_count > 1:
                total_height += spacing * (child_count - 1)

            if total_height > 0:
                return total_height

        # Final fallback: use content widget's current size hint
        content_hint = self._content_widget.sizeHint()
        return max(content_hint.height(), 50)  # Minimum reasonable height

    def add_widget(self, widget: QWidget) -> None:
        """Add a widget to the collapsible content area."""
        if self._content_layout is not None:
            self._content_layout.addWidget(widget)

    def add_layout(self, layout: QLayout) -> None:
        """Add a layout to the collapsible content area."""
        if self._content_layout is not None:
            self._content_layout.addLayout(layout)

    def setContentLayout(self, layout: QLayout) -> None:
        """Set the content layout (convenience wrapper around add_layout)."""
        self.add_layout(layout)

    def add_stretch(self, stretch: int = 0) -> None:
        """Add stretch to the collapsible content area."""
        if self._content_layout is not None:
            self._content_layout.addStretch(stretch)

    def content_layout(self) -> QVBoxLayout | None:
        """Get the content layout for direct manipulation."""
        return self._content_layout

    @override
    def sizeHint(self):
        """Provide appropriate size hint considering collapsed state."""
        hint = super().sizeHint()

        if self._is_collapsed and self._content_widget is not None:
            # When collapsed, only account for header height
            header_height = 40  # Approximate header height
            hint.setHeight(header_height)

        return hint
