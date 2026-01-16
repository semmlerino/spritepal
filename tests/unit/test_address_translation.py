"""
SNES Address Translation Tests - Critical for ROM injection pipeline.

Tests for address parsing, SNES/SA-1/HiROM/LoROM translation, and mapping type detection.
These tests catch off-by-one errors in address calculations that would silently corrupt sprite data.

Extracted from test_constants_validation.py during test consolidation.
"""

from __future__ import annotations

import pytest

from utils import constants

pytestmark = [pytest.mark.headless, pytest.mark.no_manager_setup]


class TestSNESAddressParsing:
    """Test SNES address parsing and normalization functions."""

    def test_parse_snes_banked_with_dollar_prefix(self):
        """Test parsing Mesen-style SNES address with $ prefix."""
        val, fmt = constants.parse_address_string("$98:8000")
        assert val == 0x988000
        assert fmt == "snes_banked"

    def test_parse_snes_banked_without_prefix(self):
        """Test parsing SNES bank:offset without $ prefix."""
        val, fmt = constants.parse_address_string("98:8000")
        assert val == 0x988000
        assert fmt == "snes_banked"

    def test_parse_snes_banked_lowercase(self):
        """Test parsing lowercase SNES address."""
        val, fmt = constants.parse_address_string("$98:b000")
        assert val == 0x98B000
        assert fmt == "snes_banked"

    def test_parse_snes_combined_with_dollar(self):
        """Test parsing combined SNES address with $ prefix."""
        val, fmt = constants.parse_address_string("$988000")
        assert val == 0x988000
        assert fmt == "snes"

    def test_parse_hex_with_0x_prefix(self):
        """Test parsing standard hex with 0x prefix."""
        val, fmt = constants.parse_address_string("0x0C3000")
        assert val == 0x0C3000
        assert fmt == "hex"

    def test_parse_hex_without_prefix_with_hex_chars(self):
        """Test parsing hex without prefix when it contains a-f."""
        val, fmt = constants.parse_address_string("C3000")
        assert val == 0xC3000
        assert fmt == "hex"

    def test_parse_decimal(self):
        """Test parsing pure decimal number."""
        val, fmt = constants.parse_address_string("123456")
        assert val == 123456
        assert fmt == "decimal"

    def test_parse_empty_raises_error(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="Empty"):
            constants.parse_address_string("")

    def test_parse_whitespace_only_raises_error(self):
        """Test that whitespace-only string raises ValueError."""
        with pytest.raises(ValueError, match="Empty"):
            constants.parse_address_string("   ")

    def test_parse_invalid_bank_raises_error(self):
        """Test that bank > 0xFF raises ValueError."""
        with pytest.raises(ValueError, match="exceeds"):
            constants.parse_address_string("$1FF:8000")

    def test_parse_invalid_address_raises_error(self):
        """Test that address > 0xFFFF raises ValueError."""
        with pytest.raises(ValueError, match="exceeds"):
            constants.parse_address_string("$98:1FFFF")

    def test_parse_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        val, fmt = constants.parse_address_string("  0x8000  ")
        assert val == 0x8000
        assert fmt == "hex"

    def test_is_snes_address_high_address(self):
        """Test is_snes_address detects addresses > 0x7FFFFF."""
        assert constants.is_snes_address(0x808000) is True
        assert constants.is_snes_address(0x988000) is True

    def test_is_snes_address_lorom_pattern(self):
        """Test is_snes_address detects LoROM pattern."""
        # Bank 0x01, address 0x8000 - looks like SNES
        assert constants.is_snes_address(0x018000) is True
        # Just 0x8000 with no bank - file offset
        assert constants.is_snes_address(0x8000) is False

    def test_is_snes_address_file_offset(self):
        """Test is_snes_address returns False for file offsets."""
        assert constants.is_snes_address(0x0C3000) is False
        assert constants.is_snes_address(0x200000) is False

    def test_snes_to_file_offset_basic(self):
        """Test LoROM address conversion."""
        # $80:8000 -> bank 0 (mirrored), addr 0x8000 -> file 0x0000
        assert constants.snes_to_file_offset(0x808000) == 0x0000

    def test_snes_to_file_offset_bank_mirror(self):
        """Test bank mirroring (0x80-0xFF -> 0x00-0x7F)."""
        # $98:8000 -> bank 0x18, addr 0x8000 -> file 0xC0000
        offset = constants.snes_to_file_offset(0x988000)
        assert offset == 0xC0000

    def test_snes_to_file_offset_with_smc_header(self):
        """Test conversion with SMC header adjustment."""
        offset = constants.snes_to_file_offset(0x808000, has_smc_header=True)
        assert offset == 512  # 0x0000 + 512

    def test_normalize_address_snes(self):
        """Test normalize_address with SNES address."""
        # 2MB ROM without SMC header
        offset = constants.normalize_address(0x988000, 0x200000)
        assert offset == 0xC0000

    def test_normalize_address_file_offset(self):
        """Test normalize_address with file offset (passthrough)."""
        offset = constants.normalize_address(0x50000, 0x200000)
        assert offset == 0x50000

    def test_normalize_address_with_smc_header(self):
        """Test normalize_address detects SMC header from size."""
        # ROM size 0x200200 = 2MB + 512 bytes (has SMC header)
        # File offset should add 512
        offset = constants.normalize_address(0x50000, 0x200200)
        assert offset == 0x50200  # 0x50000 + 512


class TestSA1AddressTranslation:
    """Test SA-1 address translation (Kirby Super Star, Super Mario RPG, etc.)

    These tests are CRITICAL - SA-1 address mapping is documented in:
    docs/mesen2/03_GAME_MAPPING_KIRBY_SA1.md
    """

    def test_sa1_to_file_offset_basic(self):
        """Test SA-1 address translation with documented example from SPRITE_LEARNINGS.

        From docs/mesen2/03_GAME_MAPPING_KIRBY_SA1.md:
        Mesen2 $3D2238 -> ROM $0D2238
        """
        assert constants.sa1_to_file_offset(0x3D2238) == 0x0D2238

    def test_sa1_to_file_offset_examples(self):
        """Test additional SA-1 examples from learnings doc."""
        # Mesen2 $57D800 -> ROM $27D800
        assert constants.sa1_to_file_offset(0x57D800) == 0x27D800
        # Mesen2 $580000 -> ROM $280000
        assert constants.sa1_to_file_offset(0x580000) == 0x280000

    def test_sa1_to_file_offset_with_smc_header(self):
        """Test SA-1 with SMC header."""
        offset = constants.sa1_to_file_offset(0x3D2238, has_smc_header=True)
        assert offset == 0x0D2238 + 512

    def test_sa1_address_below_base(self):
        """Test SA-1 with address below base offset (treated as direct file offset)."""
        # Address < 0x300000 should pass through as-is
        offset = constants.sa1_to_file_offset(0x100000)
        assert offset == 0x100000

    def test_normalize_address_with_sa1_mapping(self):
        """Test normalize_address with SA-1 mapping type."""
        offset = constants.normalize_address(
            0x3D2238,
            0x400000,  # 4MB ROM
            mapping_type=constants.RomMappingType.SA1,
        )
        assert offset == 0x0D2238


class TestHiROMAddressTranslation:
    """Test HiROM address translation."""

    def test_hirom_to_file_offset_basic(self):
        """Test HiROM address translation."""
        assert constants.hirom_to_file_offset(0xC08000) == 0x8000

    def test_hirom_to_file_offset_bank_c0(self):
        """Test HiROM bank $C0."""
        offset = constants.hirom_to_file_offset(0xC00000)
        assert offset == 0x0

    def test_hirom_to_file_offset_with_smc_header(self):
        """Test HiROM with SMC header."""
        offset = constants.hirom_to_file_offset(0xC08000, has_smc_header=True)
        assert offset == 0x8000 + 512

    def test_normalize_address_with_hirom_mapping(self):
        """Test normalize_address with HiROM mapping type."""
        offset = constants.normalize_address(
            0xC08000,
            0x200000,  # 2MB ROM
            mapping_type=constants.RomMappingType.HIROM,
        )
        assert offset == 0x8000


class TestMappingTypeDetection:
    """Test ROM mapping type detection from header bytes."""

    def test_detect_sa1_mapping_min(self):
        """Test SA-1 detection from rom_type byte (minimum value)."""
        mapping = constants.detect_mapping_type(0x34, 0x7FC0)
        assert mapping == constants.RomMappingType.SA1

    def test_detect_sa1_mapping_mid(self):
        """Test SA-1 detection from rom_type byte (middle value)."""
        mapping = constants.detect_mapping_type(0x35, 0x7FC0)
        assert mapping == constants.RomMappingType.SA1

    def test_detect_sa1_mapping_max(self):
        """Test SA-1 detection from rom_type byte (maximum value)."""
        mapping = constants.detect_mapping_type(0x36, 0x7FC0)
        assert mapping == constants.RomMappingType.SA1

    def test_detect_hirom_mapping(self):
        """Test HiROM detection from header offset."""
        mapping = constants.detect_mapping_type(0x21, 0xFFC0)
        assert mapping == constants.RomMappingType.HIROM

    def test_detect_exhirom_mapping(self):
        """Test ExHiROM detection from header offset."""
        mapping = constants.detect_mapping_type(0x21, 0x40FFC0)
        assert mapping == constants.RomMappingType.HIROM

    def test_detect_lorom_mapping_default(self):
        """Test LoROM as default."""
        mapping = constants.detect_mapping_type(0x20, 0x7FC0)
        assert mapping == constants.RomMappingType.LOROM

    def test_detect_lorom_non_sa1_at_lorom_header(self):
        """Test non-SA1 type at LoROM header location."""
        mapping = constants.detect_mapping_type(0x30, 0x7FC0)
        assert mapping == constants.RomMappingType.LOROM


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
