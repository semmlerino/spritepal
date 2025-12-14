"""
Help icon button component for contextual help.

Provides a small "?" button that displays detailed help text
in a tooltip or What's This popup.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWhatsThis,
    QWidget,
)

from ui.styles.theme import COLORS


class HelpIconButton(QToolButton):
    """
    A small help icon button that shows detailed help on click.

    Can display help in two modes:
    - Tooltip mode: Shows brief help on hover
    - What's This mode: Shows detailed HTML help in a popup on click

    Args:
        short_text: Brief tooltip text (shown on hover)
        detailed_text: Detailed HTML help (shown on click)
        parent: Parent widget

    Example:
        help_btn = HelpIconButton(
            short_text="Filter by sprite data size",
            detailed_text="<h3>Size Filter</h3><p>Detailed explanation...</p>",
        )
        layout.addWidget(QLabel("Size:"))
        layout.addWidget(help_btn)
    """

    def __init__(
        self,
        short_text: str = "",
        detailed_text: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._short_text = short_text
        self._detailed_text = detailed_text

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Configure the button appearance."""
        self.setText("?")
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)

        # Styling
        self.setStyleSheet(
            f"""
            QToolButton {{
                background-color: transparent;
                border: 1px solid {COLORS["text_muted"]};
                border-radius: 9px;
                font-size: 11px;
                font-weight: bold;
                color: {COLORS["text_muted"]};
            }}
            QToolButton:hover {{
                background-color: {COLORS["border"]};
                border-color: {COLORS["text_muted"]};
                color: {COLORS["text_primary"]};
            }}
            QToolButton:pressed {{
                background-color: {COLORS["border"]};
            }}
            """
        )

        # Set tooltip for quick reference
        if self._short_text:
            self.setToolTip(self._short_text)

        # Connect click to show detailed help
        if self._detailed_text:
            self.clicked.connect(self._show_help)

    def _show_help(self) -> None:
        """Show the detailed help popup."""
        if self._detailed_text:
            QWhatsThis.showText(
                self.mapToGlobal(self.rect().bottomLeft()),
                self._detailed_text,
                self,
            )

    def set_short_text(self, text: str) -> None:
        """Update the tooltip text."""
        self._short_text = text
        self.setToolTip(text)

    def set_detailed_text(self, text: str) -> None:
        """Update the detailed help text."""
        self._detailed_text = text


class HelpLabel(QWidget):
    """
    A label with an integrated help icon button.

    Combines a text label with a help button in a compact layout.

    Args:
        text: Label text
        short_help: Brief tooltip for the help button
        detailed_help: Detailed HTML help for the popup
        parent: Parent widget

    Example:
        label = HelpLabel(
            text="Offset:",
            short_help="Memory location in hex format",
            detailed_help="<h3>Hex Offset</h3>...",
        )
        layout.addWidget(label)
    """

    def __init__(
        self,
        text: str,
        short_help: str = "",
        detailed_help: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create horizontal container
        from PySide6.QtWidgets import QHBoxLayout

        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(4)

        # Label
        self.label = QLabel(text)
        h_layout.addWidget(self.label)

        # Help button (only if help text provided)
        if short_help or detailed_help:
            self.help_button = HelpIconButton(short_help, detailed_help)
            h_layout.addWidget(self.help_button)

        h_layout.addStretch()
        layout.addLayout(h_layout)

    def set_text(self, text: str) -> None:
        """Update the label text."""
        self.label.setText(text)


class InfoBanner(QFrame):
    """
    A collapsible information banner for contextual guidance.

    Displays a helpful message that users can dismiss but return to via a "?" button.

    Args:
        message: The help message to display
        parent: Parent widget
    """

    def __init__(self, message: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._message = message
        self._collapsed = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the banner UI."""
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Plain)
        self.setStyleSheet(
            f"""
            InfoBanner {{
                background-color: {COLORS["focus_background"]};
                border: 1px solid {COLORS["cache_checking_border"]};
                border-radius: 4px;
                padding: 8px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Message label
        self.message_label = QLabel(self._message)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(self.message_label)

    def set_message(self, message: str) -> None:
        """Update the banner message."""
        self._message = message
        self.message_label.setText(message)
