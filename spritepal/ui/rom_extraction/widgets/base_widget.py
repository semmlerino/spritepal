"""Base widget class for ROM extraction widgets"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QGroupBox, QLayout, QSizePolicy, QVBoxLayout, QWidget

from ui.common.spacing_constants import SPACING_COMPACT_SMALL, SPACING_SMALL
from ui.styles.theme import COLORS


class BaseExtractionWidget(QWidget):
    """Base class for extraction panel widgets with common functionality.

    Subclasses should call _setup_widget_with_group() in _setup_ui() for
    consistent layout pattern:

    def _setup_ui(self):
        inner_layout = QHBoxLayout()
        inner_layout.setSpacing(SPACING_MEDIUM)
        # ... add widgets to inner_layout ...
        self._setup_widget_with_group("Group Title", inner_layout)
    """

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)

    def _setup_widget_with_group(self, title: str, inner_layout: QLayout) -> None:
        """Set up the widget with a standard outer layout and group box.

        Args:
            title: The group box title
            inner_layout: The layout containing the widget's content
        """
        # Create outer layout
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Create group box with inner layout
        group = self._create_group_box(title)
        group.setLayout(inner_layout)
        outer_layout.addWidget(group)

        self.setLayout(outer_layout)

    def _create_group_box(self, title: str) -> QGroupBox:
        """Create a group box with minimal styling (no borders for cleaner look).

        Internal layouts should use setContentsMargins(0,0,0,0) since
        the group box CSS provides all necessary padding.
        """
        group = QGroupBox(title)
        # Minimal styling - no borders to reduce visual noise
        # Only the title provides section separation
        group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                color: {COLORS["text_secondary"]};
                margin-top: {SPACING_COMPACT_SMALL}px;
                padding-top: {SPACING_SMALL}px;
                padding-left: 0px;
                padding-right: 0px;
                padding-bottom: {SPACING_COMPACT_SMALL}px;
                border: none;
                background-color: transparent;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 0px;
                padding: 0 {SPACING_COMPACT_SMALL}px 0 0px;
            }}
        """)
        group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        return group
