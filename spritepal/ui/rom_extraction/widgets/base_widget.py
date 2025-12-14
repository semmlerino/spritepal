"""Base widget class for ROM extraction widgets"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QGroupBox, QSizePolicy, QWidget

from ui.styles.theme import COLORS


class BaseExtractionWidget(QWidget):
    """Base class for extraction panel widgets with common functionality"""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)

    def _create_group_box(self, title: str) -> QGroupBox:
        """Create a group box with consistent styling"""
        group = QGroupBox(title)
        group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                margin-top: 8px;
                padding-top: 10px;
                padding-left: 8px;
                padding-right: 8px;
                padding-bottom: 8px;
                border: 1px solid {COLORS["border"]};
                border-radius: 5px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 6px 0 6px;
            }}
        """)
        group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        return group
