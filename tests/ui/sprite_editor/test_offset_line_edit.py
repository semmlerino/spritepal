#!/usr/bin/env python3
"""
Tests for OffsetLineEdit widget.

Tests SA-1 address conversion, format parsing, and bounds validation.
"""

from __future__ import annotations

from typing import Any

import pytest

from ui.sprite_editor.views.widgets.offset_line_edit import OffsetLineEdit
from utils.constants import RomMappingType

QtBot = Any  # pyright: ignore[reportExplicitAny]


class TestOffsetLineEditSA1Conversion:
    """Tests for SA-1 address conversion in OffsetLineEdit."""

    def test_sa1_linear_bank_c0(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test SA-1 $C0:NNNN maps to start of ROM."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)
        widget.set_mapping_type(RomMappingType.SA1)

        # $C0:8000 should map to 0x008000 (bank 0, addr $8000)
        assert widget._parse_offset("$C0:8000") == 0x008000

        # $C0:0000 should map to 0x000000
        assert widget._parse_offset("$C0:0000") == 0x000000

    def test_sa1_linear_bank_c1(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test SA-1 $C1:NNNN maps to bank 1."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)
        widget.set_mapping_type(RomMappingType.SA1)

        # $C1:0000 should map to 0x010000 (bank 1, addr $0000)
        assert widget._parse_offset("$C1:0000") == 0x010000

        # $C1:ABCD should map to 0x01ABCD
        assert widget._parse_offset("$C1:ABCD") == 0x01ABCD

    def test_sa1_linear_bank_c2(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test SA-1 $C2:NNNN maps to bank 2."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)
        widget.set_mapping_type(RomMappingType.SA1)

        # $C2:4567 should map to 0x024567 (bank 2, addr $4567)
        assert widget._parse_offset("$C2:4567") == 0x024567

    def test_sa1_linear_bank_ff(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test SA-1 $FF:NNNN maps to bank 63 (last linear bank)."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)
        widget.set_mapping_type(RomMappingType.SA1)

        # $FF:0000 should map to 0x3F0000 (bank 63)
        assert widget._parse_offset("$FF:0000") == 0x3F0000

    def test_lorom_conversion_unchanged(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test LoROM mode uses standard conversion."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)
        widget.set_mapping_type(RomMappingType.LOROM)

        # $C0:8000 in LoROM should use snes_to_pc formula, not linear
        # LoROM formula: ((bank & 0x7F) << 15) | (addr & 0x7FFF)
        # $C0:8000 -> (0x40 << 15) | 0x0000 = 0x200000
        result = widget._parse_offset("$C0:8000")
        assert result == 0x200000

    def test_sa1_non_linear_bank_uses_lorom(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test SA-1 banks outside $C0-$FF use LoROM formula."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)
        widget.set_mapping_type(RomMappingType.SA1)

        # $00:8000 is not in $C0-$FF range, should use LoROM formula
        result = widget._parse_offset("$00:8000")
        # LoROM: (0x00 << 15) | 0x0000 = 0x000000
        assert result == 0x000000

    def test_default_is_lorom(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test default mapping type is LoROM."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)

        # Default should be LoROM, so $C0:8000 uses LoROM formula
        result = widget._parse_offset("$C0:8000")
        assert result == 0x200000  # LoROM result


class TestOffsetLineEditFormatParsing:
    """Tests for various input format parsing."""

    def test_mesen_file_offset_format(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test Mesen2 FILE OFFSET format parsing."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)

        assert widget._parse_offset("FILE OFFSET: 0x3C6EF1") == 0x3C6EF1

    def test_mesen_file_offset_with_header(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test Mesen2 FILE OFFSET format with SMC header adjustment."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)
        widget.set_header_offset(512)  # SMC header

        # File offset 0x1200 with 512 byte header becomes ROM offset 0x1000
        assert widget._parse_offset("FILE OFFSET: 0x1200") == 0x1000

    def test_hex_prefix_0x(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test hex with 0x prefix."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)

        assert widget._parse_offset("0x1234") == 0x1234

    def test_hex_prefix_dollar(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test hex with $ prefix."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)

        assert widget._parse_offset("$1234") == 0x1234

    def test_plain_hex(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test plain hex without prefix."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)

        assert widget._parse_offset("ABCD") == 0xABCD

    def test_empty_returns_zero(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test empty string returns 0."""
        widget = OffsetLineEdit()
        qtbot.addWidget(widget)

        assert widget._parse_offset("") == 0
