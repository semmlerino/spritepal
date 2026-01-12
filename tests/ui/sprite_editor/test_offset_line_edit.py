
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


class TestSMCHeaderOffsetHandling:
    """Tests for SMC header offset handling during Mesen2 format parsing.

    REGRESSION: These tests verify that the widget correctly subtracts the SMC
    header offset when parsing Mesen2 "FILE OFFSET: 0x..." format inputs.
    """

    def test_mesen2_format_with_smc_header_subtracts_offset(
        self, widget: OffsetLineEdit, qtbot: QtBot
    ) -> None:
        """
        Contract: When SMC header offset is set, parsing "FILE OFFSET: 0x..."
        should subtract the header offset to get the ROM offset.

        This mimics the scenario where:
        1. User loads SMC-headered ROM (512-byte header)
        2. Controller calls set_header_offset(512)
        3. User pastes Mesen2 output "FILE OFFSET: 0x3C6EF1" (file offset)
        4. Widget should return 0x3C6EF1 - 512 = 0x3C6CF1 (ROM offset)
        """
        # Configure header offset (512 bytes for SMC)
        widget.set_header_offset(512)

        # Parse Mesen2 format with file offset
        file_offset = 0x3C6EF1
        expected_rom_offset = file_offset - 512  # 0x3C6CF1

        with qtbot.waitSignal(
            widget.offset_changed, check_params_cb=lambda val: val == expected_rom_offset
        ):
            widget.setText(f"FILE OFFSET: 0x{file_offset:06X}")

        assert widget.offset() == expected_rom_offset

    def test_mesen2_format_with_zero_header_passes_through(
        self, widget: OffsetLineEdit, qtbot: QtBot
    ) -> None:
        """
        Contract: When SMC header offset is 0 (headerless ROM), parsing
        "FILE OFFSET: 0x..." should return the offset unchanged.
        """
        # Configure zero header offset (headerless ROM)
        widget.set_header_offset(0)

        # Parse Mesen2 format with file offset
        file_offset = 0x3C6EF1

        with qtbot.waitSignal(
            widget.offset_changed, check_params_cb=lambda val: val == file_offset
        ):
            widget.setText(f"FILE OFFSET: 0x{file_offset:06X}")

        assert widget.offset() == file_offset

    def test_mesen2_format_header_offset_cannot_go_negative(
        self, widget: OffsetLineEdit, qtbot: QtBot
    ) -> None:
        """
        Contract: If file offset < header offset, result should be clamped to 0.
        """
        # Configure header offset larger than file offset
        widget.set_header_offset(512)

        # Parse Mesen2 format with small file offset (in header region)
        file_offset = 0x100  # 256 bytes, less than 512-byte header

        with qtbot.waitSignal(
            widget.offset_changed, check_params_cb=lambda val: val == 0
        ):
            widget.setText(f"FILE OFFSET: 0x{file_offset:03X}")

        assert widget.offset() == 0  # Clamped to 0, not negative

    def test_plain_hex_input_not_affected_by_header_offset(
        self, widget: OffsetLineEdit, qtbot: QtBot
    ) -> None:
        """
        Contract: Plain hex input (e.g., "0x3C6EF1") should NOT be adjusted
        for header offset, as it's assumed to be a ROM offset already.
        """
        # Configure header offset
        widget.set_header_offset(512)

        # Parse plain hex format (NOT Mesen2 format)
        rom_offset = 0x3C6EF1

        with qtbot.waitSignal(
            widget.offset_changed, check_params_cb=lambda val: val == rom_offset
        ):
            widget.setText(f"0x{rom_offset:06X}")

        # Plain hex should NOT have header subtracted
        assert widget.offset() == rom_offset
