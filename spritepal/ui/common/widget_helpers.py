"""
Shared widget creation helpers to avoid duplication across UI components.

Provides factory functions for commonly used widget patterns.
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QWidget

from ui.styles import get_section_label_style
from ui.styles.theme import COLORS

LabelStyle = Literal["title", "section"]


def create_styled_label(
    text: str,
    style: LabelStyle = "section",
    parent: QWidget | None = None,
) -> QLabel:
    """
    Create a styled label with consistent appearance.

    Args:
        text: The label text to display
        style: The label style:
            - "title": Bold, larger (11pt), highlight color - for major section headers in tabs
            - "section": Standard section label style - for panel section headers
        parent: Optional parent widget

    Returns:
        QLabel configured with the requested styling
    """
    label = QLabel(text, parent)

    if style == "title":
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        label.setFont(title_font)
        label.setStyleSheet(f"color: {COLORS['highlight']}; padding: 2px 4px; border-radius: 3px;")
    else:  # "section"
        label.setStyleSheet(get_section_label_style())

    return label
