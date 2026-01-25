"""
Integration tests for Qt widget styling.

Tests real Qt widgets with theme styles applied.
Headless constant/CSS tests are in tests/unit/ui/styles/test_theme_constants.py
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.styles.components import (
    get_button_style,
    get_dark_preview_style,
    get_input_style,
    get_panel_style,
)
from ui.styles.theme import (
    COLORS,
    get_theme_style,
)

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.allows_registry_state(reason="UI tests may trigger Qt auto-registration"),
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.gui,
]


class TestQtIntegration:
    """Test theme application to real Qt widgets."""

    def test_theme_application_to_widgets(self, qtbot) -> None:
        """Style sheets should be applicable to real widgets without errors."""
        container = QWidget()
        qtbot.addWidget(container)
        layout = QVBoxLayout(container)

        widgets = [
            QPushButton("Button"),
            QLineEdit("Input"),
            QGroupBox("Panel"),
        ]

        for w in widgets:
            layout.addWidget(w)

        # Apply styles
        container.setStyleSheet(get_theme_style())
        widgets[0].setStyleSheet(get_button_style("primary"))
        widgets[1].setStyleSheet(get_input_style("text"))
        widgets[2].setStyleSheet(get_panel_style("default"))

        container.show()
        qtbot.waitExposed(container)

        # Verify application
        assert len(widgets[0].styleSheet()) > 0
        assert COLORS["primary"] in widgets[0].styleSheet()

    def test_palette_integration(self) -> None:
        """QPalette should be customizable with theme colors."""
        palette = QPalette()
        color = QColor(COLORS["primary"])
        palette.setColor(QPalette.ColorRole.Highlight, color)
        assert palette.color(QPalette.ColorRole.Highlight).name().lower() == COLORS["primary"].lower()

    def test_preview_label_styling(self, qtbot) -> None:
        """Preview labels should accept dark preview styling."""
        label = QLabel()
        qtbot.addWidget(label)
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.red)
        label.setPixmap(pixmap)

        style = get_dark_preview_style()
        label.setStyleSheet(style)

        assert label.pixmap() is not None
        assert COLORS["preview_background"] in label.styleSheet()
