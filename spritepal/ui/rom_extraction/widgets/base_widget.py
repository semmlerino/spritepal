"""Base widget class for ROM extraction widgets"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QGroupBox, QSizePolicy, QWidget

from ui.common.spacing_constants import SPACING_COMPACT_SMALL, SPACING_SMALL
from ui.styles.theme import COLORS


class BaseExtractionWidget(QWidget):
    """Base class for extraction panel widgets with common functionality"""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)

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
