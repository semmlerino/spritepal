
"""Tests for OffsetLineEdit widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.sprite_editor.views.widgets.offset_line_edit import OffsetLineEdit

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


pytestmark = pytest.mark.gui


@pytest.fixture
def widget(qtbot: QtBot) -> OffsetLineEdit:
    """Create default OffsetLineEdit widget."""
    w = OffsetLineEdit()
    qtbot.addWidget(w)
    return w


class TestOffsetLineEditParsing:
    """Tests for offset parsing."""

    def test_parse_valid_hex(self, widget: OffsetLineEdit, qtbot: QtBot) -> None:
        """Parse valid hex strings."""
        with qtbot.waitSignal(widget.offset_changed, check_params_cb=lambda val: val == 0x1234):
            widget.setText("0x1234")
            
        assert widget.offset() == 0x1234

    def test_parse_invalid(self, widget: OffsetLineEdit) -> None:
        """Invalid text should not change valid offset but might change styling."""
        widget.set_offset(0x1000)
        widget.setText("invalid")
        # Offset remains last valid
        assert widget.offset() == 0x1000
        # Background should indicate error (implementation detail, but good to check if public behavior)
        # Note: StyleSheet checking is brittle, relying on behavior instead.


class TestOffsetLineEditRecursionFix:
    """Tests specifically for the recursion fix (programmatic updates)."""

    def test_set_offset_does_not_emit_signal(self, widget: OffsetLineEdit, qtbot: QtBot) -> None:
        """Verify that set_offset does NOT emit offset_changed signal."""
        # Using qtbot.assertNotEmitted context manager
        with qtbot.assertNotEmitted(widget.offset_changed):
            widget.set_offset(0x5678)
            
        assert widget.offset() == 0x5678
        assert widget.text() == "0x005678"

    def test_programmatic_update_styling(self, widget: OffsetLineEdit) -> None:
        """Verify styling is updated even when signals are blocked."""
        # Set bounds
        widget.set_rom_bounds(0x1000)
        
        # set_offset within bounds
        widget.set_offset(0x0500)
        assert widget.styleSheet() == ""
        
        # set_offset out of bounds
        widget.set_offset(0x2000)
        assert "background-color" in widget.styleSheet()
