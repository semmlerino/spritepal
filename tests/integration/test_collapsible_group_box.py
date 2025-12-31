"""
Test the CollapsibleGroupBox component - basic functionality only.

NOTE: Animation-related tests have been removed due to Qt segfault issues
during animation cleanup. Only basic initialization and collapse/expand
functionality is tested here.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QVBoxLayout

from ui.common.collapsible_group_box import CollapsibleGroupBox

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
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
        """Test basic collapse/expand functionality.

        Note: We verify the logical state change only, not the animation.
        The set_collapsed() method immediately updates _is_collapsed state,
        so no waiting is needed. Animation completion is visual-only and
        testing it would require entering Qt's event loop, which can cause
        crashes with background threads in CI environments.
        """
        widget = CollapsibleGroupBox("Test")
        qtbot.addWidget(widget)

        # Add some content
        content = QLabel("Test content")
        layout = QVBoxLayout()
        layout.addWidget(content)
        widget.setLayout(layout)

        # Test collapse - state changes immediately, no need to wait for animation
        widget.set_collapsed(True)
        assert widget.is_collapsed() is True

        # Test expand - state changes immediately, no need to wait for animation
        widget.set_collapsed(False)
        assert widget.is_collapsed() is False
