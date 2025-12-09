"""
Test the CollapsibleGroupBox component - basic functionality only.

NOTE: Animation-related tests have been removed due to Qt segfault issues
during animation cleanup. Only basic initialization and collapse/expand
functionality is tested here.
"""
from __future__ import annotations

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QVBoxLayout

from ui.common.collapsible_group_box import CollapsibleGroupBox

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.widget,
    pytest.mark.ci_safe,
    pytest.mark.integration,
    pytest.mark.stability,
]

class TestCollapsibleGroupBox:
    """Test CollapsibleGroupBox widget - basic functionality"""

    def test_basic_initialization(self, qtbot):
        """Test basic widget initialization"""
        widget = CollapsibleGroupBox("Test Title")
        qtbot.addWidget(widget)

        assert widget._title_label.text() == "Test Title"
        assert widget.is_collapsed() is False  # Default expanded

    def test_collapse_expand_functionality(self, qtbot):
        """Test basic collapse/expand functionality"""
        widget = CollapsibleGroupBox("Test")
        qtbot.addWidget(widget)

        # Add some content
        content = QLabel("Test content")
        layout = QVBoxLayout()
        layout.addWidget(content)
        widget.setLayout(layout)

        # Test collapse
        widget.set_collapsed(True)
        QTest.qWait(200)  # Wait for animation
        assert widget.is_collapsed() is True

        # Test expand
        widget.set_collapsed(False)
        QTest.qWait(200)  # Wait for animation
        assert widget.is_collapsed() is False
