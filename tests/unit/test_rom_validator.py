"""
Tests for ROM validator
"""

from __future__ import annotations

import struct

import pytest

from core.rom_validator import ROMHeader, ROMValidator
from utils.constants import (
    ROM_CHECKSUM_COMPLEMENT_MASK,
    ROM_HEADER_OFFSET_EXHIROM,
    ROM_HEADER_OFFSET_HIROM,
    ROM_HEADER_OFFSET_LOROM,
    ROM_TYPE_SA1_MAX,
    ROM_TYPE_SA1_MIN,
)
from utils.rom_exceptions import (
    InvalidROMError,
    ROMChecksumError,
    ROMHeaderError,
    ROMSizeError,
)

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_manager_setup,
]


def create_valid_snes_header(
    title: str = "TEST ROM",
    rom_type: int = 0x00,
    checksum: int = 0x1234,
) -> bytes:
    """Create a valid SNES ROM header (32 bytes)."""
    header = bytearray(32)
    # Title (21 bytes, padded with spaces)
    title_bytes = title.encode("ascii")[:21].ljust(21, b" ")
    header[0:21] = title_bytes
    # ROM type at offset 21
    header[21] = rom_type
    # ROM size at offset 23 (0x0C = 4MB)
    header[23] = 0x0C
    # Checksum complement at offset 28-29
    complement = checksum ^ ROM_CHECKSUM_COMPLEMENT_MASK
    struct.pack_into("<H", header, 28, complement)
    # Checksum at offset 30-31
    struct.pack_into("<H", header, 30, checksum)
    return bytes(header)


def create_rom_with_header(
    header_offset: int,
    title: str = "TEST ROM",
    rom_type: int = 0x00,
    smc_header: bool = False,
    total_size: int = 0x100000,  # 1MB default
) -> bytes:
    """Create a ROM file with header at specified offset.

    Args:
        header_offset: Where the SNES header should be placed (relative to ROM start)
        title: ROM title
        rom_type: ROM type byte (for SA-1 detection, etc.)
        smc_header: If True, prepends 512-byte SMC header and total_size includes it
        total_size: Total size including SMC header if present
    """
    # If SMC header requested, account for it
    if smc_header:
        # SMC header is 512 bytes prepended to the ROM
        smc_data = bytearray(512)
        rom_size = total_size - 512
        rom = bytearray(rom_size)
    else:
        smc_data = bytearray()
        rom = bytearray(total_size)

    header = create_valid_snes_header(title, rom_type)

    # Place SNES header at the specified offset within the ROM data (not including SMC)
    if header_offset + 32 <= len(rom):
        rom[header_offset : header_offset + 32] = header

    return bytes(smc_data) + bytes(rom)


def create_valid_rom_header(
    title="TEST ROM",
    checksum=0x1234,
    region=1,
    rom_type=0x21,
    rom_size=0x0C,
    sram_size=0x00,
    developer=0x01,
    version=0x00,
):
    """Create a valid SNES ROM header (32 bytes)"""
    header = bytearray(32)

    # Title (21 bytes)
    title_bytes = title.encode("ascii")[:21]
    header[0 : len(title_bytes)] = title_bytes

    # ROM makeup byte
    header[21] = rom_type
    # ROM type (usually 0x02 for ROM+SRAM+Battery)
    header[22] = 0x02
    # ROM size
    header[23] = rom_size
    # SRAM size
    header[24] = sram_size
    # Country/Region code
    header[25] = region
    # Developer ID
    header[26] = developer
    # Version number
    header[27] = version

    # Checksum complement (must XOR to 0xFFFF with checksum)
    checksum_complement = checksum ^ 0xFFFF
    struct.pack_into("<H", header, 28, checksum_complement)
    struct.pack_into("<H", header, 30, checksum)

    return bytes(header)


def create_test_rom(
    size=0x200000, has_smc_header=False, header_location=0x7FC0, header_data=None, calculate_checksum=True
):
    """Create a test ROM with specified properties"""
    # Create ROM data
    rom_data = bytearray(size)

    # Fill with some pattern so it's not all zeros
    for i in range(0, size, 256):
        rom_data[i : i + 256] = bytes(range(256))

    # Add header
    if header_data is None:
        header_data = create_valid_rom_header()

    if header_location < len(rom_data) - 32:
        rom_data[header_location : header_location + 32] = header_data

    # Calculate and update checksum if requested
    if calculate_checksum:
        checksum = sum(rom_data) & 0xFFFF

        # Update checksum in header
        checksum_complement = checksum ^ 0xFFFF
        struct.pack_into("<H", rom_data, header_location + 28, checksum_complement)
        struct.pack_into("<H", rom_data, header_location + 30, checksum)

    # Add SMC header if requested
    if has_smc_header:
        smc_header = b"\x00" * 512
        rom_data = smc_header + rom_data

    return bytes(rom_data)


class TestROMValidator:
    """Test ROM validation functionality"""

    def test_validate_rom_file_not_exists(self):
        """Test validation with non-existent file"""
        is_valid, error = ROMValidator.validate_rom_file("/nonexistent/rom.sfc")

        assert not is_valid
        assert error is not None
        assert "exist" in error.lower()

    def test_validate_rom_file_empty(self, tmp_path):
        """Test validation with empty file"""
        rom_path = tmp_path / "empty.sfc"
        rom_path.write_bytes(b"")

        is_valid, error = ROMValidator.validate_rom_file(str(rom_path))

        assert not is_valid
        assert error is not None
        assert "small" in error.lower() or "empty" in error.lower()

    def test_validate_rom_file_valid_sizes(self, tmp_path):
        """Test validation with all valid ROM sizes"""
        for rom_size in ROMValidator.VALID_ROM_SIZES:
            rom_path = tmp_path / f"test_{rom_size}.sfc"
            rom_data = create_test_rom(size=rom_size)
            rom_path.write_bytes(rom_data)

            is_valid, error = ROMValidator.validate_rom_file(str(rom_path))

            assert is_valid
            assert error is None

    def test_validate_rom_file_with_smc_header(self, tmp_path):
        """Test validation with SMC header"""
        rom_path = tmp_path / "test_smc.sfc"
        rom_data = create_test_rom(size=0x200000, has_smc_header=True)
        rom_path.write_bytes(rom_data)

        is_valid, error = ROMValidator.validate_rom_file(str(rom_path))

        assert is_valid
        assert error is None

    def test_validate_rom_file_invalid_size(self, tmp_path):
        """Test validation with file too small to be a valid ROM."""
        rom_path = tmp_path / "invalid_size.sfc"
        # Too small (under 512KB minimum)
        rom_path.write_bytes(b"\x00" * 1000)

        is_valid, error = ROMValidator.validate_rom_file(str(rom_path))

        assert not is_valid
        assert error is not None
        assert "small" in error.lower() or "size" in error.lower()

    def test_validate_rom_header_lorom(self, tmp_path):
        """Test header validation for LoROM (header at 0x7FC0)"""
        rom_path = tmp_path / "lorom.sfc"
        rom_data = create_test_rom(header_location=0x7FC0)
        rom_path.write_bytes(rom_data)

        header, smc_offset = ROMValidator.validate_rom_header(str(rom_path))

        assert header.title == "TEST ROM"
        # Checksum will be calculated, just verify it exists
        assert isinstance(header.checksum, int)
        assert header.rom_type_offset == 0x7FC0
        assert smc_offset == 0

    def test_validate_rom_header_hirom(self, tmp_path):
        """Test header validation for HiROM (header at 0xFFC0)"""
        rom_path = tmp_path / "hirom.sfc"
        rom_data = create_test_rom(header_location=0xFFC0)
        rom_path.write_bytes(rom_data)

        header, smc_offset = ROMValidator.validate_rom_header(str(rom_path))

        assert header.title == "TEST ROM"
        assert header.rom_type_offset == 0xFFC0
        assert smc_offset == 0

    def test_validate_rom_header_with_smc(self, tmp_path):
        """Test header validation with SMC header"""
        rom_path = tmp_path / "smc_header.sfc"
        rom_data = create_test_rom(has_smc_header=True, header_location=0x7FC0)
        rom_path.write_bytes(rom_data)

        header, smc_offset = ROMValidator.validate_rom_header(str(rom_path))

        assert header.title == "TEST ROM"
        assert smc_offset == 512  # SMC header size

    def test_validate_rom_header_invalid(self, tmp_path):
        """Test header validation with invalid header"""
        rom_path = tmp_path / "invalid_header.sfc"
        # Create ROM with bad checksum complement
        bad_header = bytearray(create_valid_rom_header())
        bad_header[28] = 0xFF  # Break checksum complement
        bad_header[29] = 0xFF
        # Don't calculate checksum so the header remains invalid
        rom_data = create_test_rom(header_data=bytes(bad_header), calculate_checksum=False)
        rom_path.write_bytes(rom_data)

        with pytest.raises(ROMHeaderError) as exc_info:
            ROMValidator.validate_rom_header(str(rom_path))

        assert "Could not find valid SNES ROM header" in str(exc_info.value)

    def test_validate_rom_header_non_ascii_title(self, tmp_path):
        """Test header with non-ASCII characters in title"""
        rom_path = tmp_path / "non_ascii.sfc"
        # Create header with some non-ASCII bytes
        header_data = bytearray(create_valid_rom_header())
        header_data[10:15] = b"\xff\xfe\xfd\xfc\xfb"  # Non-ASCII
        rom_data = create_test_rom(header_data=bytes(header_data))
        rom_path.write_bytes(rom_data)

        header, _ = ROMValidator.validate_rom_header(str(rom_path))

        # Should handle non-ASCII gracefully
        assert isinstance(header.title, str)

    def test_verify_rom_checksum_valid(self, tmp_path):
        """Test checksum verification with valid checksum"""
        rom_path = tmp_path / "valid_checksum.sfc"
        rom_data = create_test_rom(calculate_checksum=True)
        rom_path.write_bytes(rom_data)

        header, _ = ROMValidator.validate_rom_header(str(rom_path))

        # Should not raise
        result = ROMValidator.verify_rom_checksum(str(rom_path), header)
        assert result is True

    def test_verify_rom_checksum_invalid(self, tmp_path):
        """Test checksum verification with invalid checksum"""
        rom_path = tmp_path / "invalid_checksum.sfc"
        # Create ROM but don't calculate correct checksum
        rom_data = create_test_rom(calculate_checksum=False)
        rom_path.write_bytes(rom_data)

        header, _ = ROMValidator.validate_rom_header(str(rom_path))

        # Strict mode (default) should raise
        with pytest.raises(ROMChecksumError) as exc_info:
            ROMValidator.verify_rom_checksum(str(rom_path), header)
        assert "ROM checksum mismatch" in str(exc_info.value)

        # Lenient mode should return False and not raise
        result = ROMValidator.verify_rom_checksum(str(rom_path), header, lenient=True)
        assert result is False

    def test_verify_rom_checksum_odd_length(self, tmp_path):
        """Test checksum with odd-length ROM data"""
        rom_path = tmp_path / "odd_length.sfc"
        # Create ROM with odd size (0x200000 is 2MB, +1 byte)
        rom_data = create_test_rom(size=0x200001)
        rom_path.write_bytes(rom_data)

        header, _ = ROMValidator.validate_rom_header(str(rom_path))

        # Should handle odd length and detect mismatch (since create_test_rom doesn't
        # perfectly calculate checksum for non-power-of-2 sizes in its simple implementation)
        # The key is that it doesn't crash with IndexError
        result = ROMValidator.verify_rom_checksum(str(rom_path), header, lenient=True)
        assert isinstance(result, bool)

    def test_identify_rom_version_known_game(self):
        """Test ROM version identification for known game"""
        header = ROMHeader(
            title="KIRBY SUPER STAR",
            rom_type=0x21,
            rom_size=0x0C,
            sram_size=0x00,
            checksum=0x8A5C,  # USA version
            checksum_complement=0x8A5C ^ 0xFFFF,
            header_offset=0,
            rom_type_offset=0x7FC0,
            region=1,
        )

        version = ROMValidator.identify_rom_version(header)

        assert version == "USA"

    def test_identify_rom_version_by_region(self):
        """Test ROM version identification by region code"""
        header = ROMHeader(
            title="UNKNOWN GAME",
            rom_type=0x21,
            rom_size=0x0C,
            sram_size=0x00,
            checksum=0x9999,
            checksum_complement=0x9999 ^ 0xFFFF,
            header_offset=0,
            rom_type_offset=0x7FC0,
            region=2,  # Europe
        )

        version = ROMValidator.identify_rom_version(header)

        assert version == "Europe"

    def test_identify_rom_version_unknown(self):
        """Test ROM version identification for unknown game/region"""
        header = ROMHeader(
            title="UNKNOWN GAME",
            rom_type=0x21,
            rom_size=0x0C,
            sram_size=0x00,
            checksum=0x9999,
            checksum_complement=0x9999 ^ 0xFFFF,
            header_offset=0,
            rom_type_offset=0x7FC0,
            region=99,  # Invalid region
        )

        version = ROMValidator.identify_rom_version(header)

        assert version is None

    def test_identify_rom_version_case_insensitive(self):
        """Test ROM title matching is case insensitive"""
        header = ROMHeader(
            title="kirby super star",  # lowercase
            rom_type=0x21,
            rom_size=0x0C,
            sram_size=0x00,
            checksum=0x8A5C,
            checksum_complement=0x8A5C ^ 0xFFFF,
            header_offset=0,
            rom_type_offset=0x7FC0,
            region=1,
        )

        version = ROMValidator.identify_rom_version(header)

        assert version == "USA"

    def test_validate_rom_for_injection_success(self, tmp_path):
        """Test complete ROM validation for injection"""
        rom_path = tmp_path / "valid_rom.sfc"
        rom_data = create_test_rom(size=0x400000)  # 4MB ROM
        rom_path.write_bytes(rom_data)

        sprite_offset = 0x200000  # Valid offset within ROM

        header, smc_offset = ROMValidator.validate_rom_for_injection(str(rom_path), sprite_offset)

        assert header.title == "TEST ROM"
        assert smc_offset == 0

    def test_validate_rom_for_injection_invalid_file(self):
        """Test injection validation with invalid file"""
        with pytest.raises(InvalidROMError) as exc_info:
            ROMValidator.validate_rom_for_injection("/nonexistent/rom.sfc", 0x100000)

        assert "exist" in str(exc_info.value).lower()

    def test_validate_rom_for_injection_bad_header(self, tmp_path):
        """Test injection validation with bad header"""
        rom_path = tmp_path / "bad_header.sfc"
        # Create ROM with invalid header
        rom_data = b"\x00" * 0x200000  # All zeros, no valid header
        rom_path.write_bytes(rom_data)

        with pytest.raises(ROMHeaderError):
            ROMValidator.validate_rom_for_injection(str(rom_path), 0x100000)

    def test_validate_rom_for_injection_offset_too_large(self, tmp_path):
        """Test injection validation with offset beyond ROM size"""
        rom_path = tmp_path / "small_rom.sfc"
        rom_data = create_test_rom(size=0x200000)  # 2MB ROM
        rom_path.write_bytes(rom_data)

        sprite_offset = 0x300000  # Beyond ROM size

        with pytest.raises(ROMSizeError) as exc_info:
            ROMValidator.validate_rom_for_injection(str(rom_path), sprite_offset)

        assert "beyond ROM size" in str(exc_info.value)

    def test_validate_rom_for_injection_with_smc_header(self, tmp_path):
        """Test injection validation accounts for SMC header in size check"""
        rom_path = tmp_path / "smc_rom.sfc"
        rom_data = create_test_rom(size=0x200000, has_smc_header=True)
        rom_path.write_bytes(rom_data)

        # Offset that would be valid without header, but beyond actual ROM
        sprite_offset = 0x1FFFF0

        # Should succeed because offset is within actual ROM data
        header, smc_offset = ROMValidator.validate_rom_for_injection(str(rom_path), sprite_offset)

        assert smc_offset == 512  # SMC header detected


# ============================================================================
# ROM Variant Tests (Migrated from audit fixes)
# ============================================================================


class TestROMHeaderVariants:
    """Tests for header detection edge cases."""

    def test_lorom_header_detection(self, tmp_path):
        """Standard LoROM header at 0x7FC0."""
        rom_path = tmp_path / "lorom.sfc"
        rom_data = create_rom_with_header(ROM_HEADER_OFFSET_LOROM, title="LOROM TEST")
        rom_path.write_bytes(rom_data)

        header, smc_offset = ROMValidator.validate_rom_header(str(rom_path))

        assert header.title.strip() == "LOROM TEST"
        assert smc_offset == 0
        assert header.rom_type_offset == ROM_HEADER_OFFSET_LOROM

    def test_hirom_header_detection(self, tmp_path):
        """HiROM header at 0xFFC0."""
        rom_path = tmp_path / "hirom.sfc"
        rom_data = create_rom_with_header(ROM_HEADER_OFFSET_HIROM, title="HIROM TEST")
        rom_path.write_bytes(rom_data)

        header, smc_offset = ROMValidator.validate_rom_header(str(rom_path))

        assert header.title.strip() == "HIROM TEST"
        assert smc_offset == 0
        assert header.rom_type_offset == ROM_HEADER_OFFSET_HIROM

    def test_exhirom_header_detection(self, tmp_path):
        """ExHiROM header at 0x40FFC0 for large ROMs."""
        rom_path = tmp_path / "exhirom.sfc"
        # Need >4MB ROM for ExHiROM check
        rom_data = create_rom_with_header(
            ROM_HEADER_OFFSET_EXHIROM,
            title="EXHIROM TEST",
            total_size=0x500000,  # 5MB
        )
        rom_path.write_bytes(rom_data)

        header, smc_offset = ROMValidator.validate_rom_header(str(rom_path))

        assert header.title.strip() == "EXHIROM TEST"
        assert header.rom_type_offset == ROM_HEADER_OFFSET_EXHIROM

    def test_sa1_chip_detection(self, tmp_path, caplog):
        """SA-1 chip games (like Kirby Super Star) are detected."""
        rom_path = tmp_path / "sa1.sfc"
        rom_data = create_rom_with_header(
            ROM_HEADER_OFFSET_LOROM,
            title="KIRBY SUPER STAR",
            rom_type=ROM_TYPE_SA1_MIN,  # SA-1 chip indicator
        )
        rom_path.write_bytes(rom_data)

        header, _ = ROMValidator.validate_rom_header(str(rom_path))

        assert header.title.strip() == "KIRBY SUPER STAR"
        assert ROM_TYPE_SA1_MIN <= header.rom_type <= ROM_TYPE_SA1_MAX
        # Check that SA-1 was logged
        assert any("[SA-1]" in r.message for r in caplog.records)

    def test_smc_header_stripped(self, tmp_path):
        """512-byte SMC header correctly removed."""
        rom_path = tmp_path / "smc.sfc"

        # Create ROM with SMC header - total size must be (ROM size + 512) where
        # (ROM size + 512) % 1024 == 512 to trigger SMC detection
        # Use 1MB + 512 = 1049088 bytes total
        rom_data = create_rom_with_header(
            ROM_HEADER_OFFSET_LOROM,
            title="SMC TEST",
            smc_header=True,
            total_size=0x100000 + 512,  # 1MB ROM + 512 byte SMC header
        )

        rom_path.write_bytes(rom_data)

        header, smc_offset = ROMValidator.validate_rom_header(str(rom_path))

        assert header.title.strip() == "SMC TEST"
        assert smc_offset == 512


class TestSMCHeaderValidation:
    """SMC header content validation."""

    def test_valid_smc_header_passes(self, tmp_path):
        """Valid SMC header with mostly zeros passes validation."""
        rom_path = tmp_path / "valid_smc.sfc"

        # Create ROM with SMC header - total size triggers SMC detection
        rom_data = create_rom_with_header(
            ROM_HEADER_OFFSET_LOROM,
            title="VALID SMC",
            smc_header=True,
            total_size=0x100000 + 512,  # 1MB ROM + 512 byte SMC header
        )

        rom_path.write_bytes(rom_data)

        # Should not raise or warn about invalid SMC
        header, smc_offset = ROMValidator.validate_rom_header(str(rom_path))
        assert smc_offset == 512
        assert header.title.strip() == "VALID SMC"

    def test_invalid_smc_header_warned(self, tmp_path, caplog):
        """Non-standard SMC header triggers warning."""
        rom_path = tmp_path / "bad_smc.sfc"

        # Create base ROM data without SMC header
        rom_size = 0x100000  # 1MB
        rom_data = bytearray(rom_size)

        # Place valid SNES header at LoROM offset within ROM data
        header = create_valid_snes_header("BAD SMC TEST")
        rom_data[ROM_HEADER_OFFSET_LOROM : ROM_HEADER_OFFSET_LOROM + 32] = header

        # Create SMC header with lots of non-zero bytes (suspicious)
        # This should trigger the content validation warning
        bad_smc = bytes(range(256)) + bytes(range(256))  # 512 bytes, all non-zero

        # Combine: bad SMC header + ROM data
        # Total size = 512 + 1MB = triggers SMC detection
        full_data = bad_smc + bytes(rom_data)
        rom_path.write_bytes(full_data)

        # Should log warning about suspicious SMC header but still find ROM header
        header_result, smc_offset = ROMValidator.validate_rom_header(str(rom_path))

        assert smc_offset == 512
        assert any("content validation failed" in r.message.lower() for r in caplog.records)