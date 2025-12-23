"""
Tests for HAL compression parsing.

This module tests the _parse_hal_compressed_size() method in ROMInjector
to verify it correctly parses HAL compression streams and calculates
compressed block sizes.

HAL Compression Format Reference (from exhal compress.c):
- No header - starts directly with command bytes
- Command encoding:
  - If (cmd & 0xE0) == 0xE0: Long command
    - command = (cmd >> 2) & 0x07
    - length = (((cmd & 0x03) << 8) | next_byte) + 1
  - Else: Short command
    - command = cmd >> 5
    - length = (cmd & 0x1F) + 1
- Commands:
  - 0: Raw bytes (length bytes follow in stream)
  - 1: 8-bit RLE (1 byte follows)
  - 2: 16-bit RLE (2 bytes follow)
  - 3: Sequence RLE (1 byte follows)
  - 4,7: Forward backref (2 bytes offset follow)
  - 5: Rotated backref (2 bytes offset follow)
  - 6: Backward backref (2 bytes offset follow)
- 0xFF terminates the stream
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from core.rom_injector import ROMInjector

if TYPE_CHECKING:
    from collections.abc import Generator


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def injector() -> ROMInjector:
    """Create ROMInjector instance for testing."""
    return ROMInjector()


@pytest.fixture
def exhal_binary() -> Path | None:
    """Find exhal binary if available."""
    import shutil

    path = shutil.which("exhal")
    return Path(path) if path else None


# =============================================================================
# HAL Stream Test Data Builder
# =============================================================================


class HALStreamBuilder:
    """Builder for constructing valid HAL compression streams for testing."""

    def __init__(self) -> None:
        self._data: bytearray = bytearray()
        self._terminated: bool = False

    def raw_bytes(self, data: bytes, long_form: bool = False) -> HALStreamBuilder:
        """Add raw bytes command (command 0).

        Args:
            data: The raw bytes to encode
            long_form: If True, use long command format even for short data
        """
        length = len(data)
        if length == 0:
            return self

        if long_form or length > 32:
            # Long format: 0xE0 | ((length - 1) >> 8), (length - 1) & 0xFF
            # Actually: command bits = 0, so 0xE0 | (cmd << 2) | (length >> 8)
            # = 0xE0 | 0 | ((length - 1) >> 8)
            len_minus_1 = length - 1
            cmd_byte = 0xE0 | ((len_minus_1 >> 8) & 0x03)
            self._data.append(cmd_byte)
            self._data.append(len_minus_1 & 0xFF)
        else:
            # Short format: (command << 5) | (length - 1) = (0 << 5) | (length - 1)
            self._data.append((length - 1) & 0x1F)

        self._data.extend(data)
        return self

    def rle_8bit(self, byte_val: int, count: int, long_form: bool = False) -> HALStreamBuilder:
        """Add 8-bit RLE command (command 1).

        Args:
            byte_val: The byte value to repeat
            count: Number of times to repeat (1-1024)
            long_form: If True, use long command format
        """
        if count == 0:
            return self

        if long_form or count > 32:
            # Long format for command 1
            len_minus_1 = count - 1
            cmd_byte = 0xE0 | (1 << 2) | ((len_minus_1 >> 8) & 0x03)
            self._data.append(cmd_byte)
            self._data.append(len_minus_1 & 0xFF)
        else:
            # Short format: (1 << 5) | (count - 1)
            self._data.append(0x20 | ((count - 1) & 0x1F))

        self._data.append(byte_val & 0xFF)
        return self

    def rle_16bit(self, word_val: int, count: int, long_form: bool = False) -> HALStreamBuilder:
        """Add 16-bit RLE command (command 2).

        Args:
            word_val: The 16-bit word value to repeat
            count: Number of 16-bit words to output
            long_form: If True, use long command format
        """
        if count == 0:
            return self

        if long_form or count > 32:
            len_minus_1 = count - 1
            cmd_byte = 0xE0 | (2 << 2) | ((len_minus_1 >> 8) & 0x03)
            self._data.append(cmd_byte)
            self._data.append(len_minus_1 & 0xFF)
        else:
            self._data.append(0x40 | ((count - 1) & 0x1F))

        # 16-bit word in little-endian
        self._data.append(word_val & 0xFF)
        self._data.append((word_val >> 8) & 0xFF)
        return self

    def sequence_rle(self, start_byte: int, count: int, long_form: bool = False) -> HALStreamBuilder:
        """Add sequence RLE command (command 3).

        Outputs: start_byte, start_byte+1, start_byte+2, ...

        Args:
            start_byte: Starting byte value
            count: Number of sequential bytes
            long_form: If True, use long command format
        """
        if count == 0:
            return self

        if long_form or count > 32:
            len_minus_1 = count - 1
            cmd_byte = 0xE0 | (3 << 2) | ((len_minus_1 >> 8) & 0x03)
            self._data.append(cmd_byte)
            self._data.append(len_minus_1 & 0xFF)
        else:
            self._data.append(0x60 | ((count - 1) & 0x1F))

        self._data.append(start_byte & 0xFF)
        return self

    def backref(
        self, offset: int, count: int, command: int = 4, long_form: bool = False
    ) -> HALStreamBuilder:
        """Add backref command (commands 4-7).

        Args:
            offset: Offset in decompressed data to copy from
            count: Number of bytes to copy
            command: Backref type (4=forward, 5=rotated, 6=backward, 7=forward)
            long_form: If True, use long command format
        """
        if count == 0:
            return self

        if command not in (4, 5, 6, 7):
            raise ValueError(f"Invalid backref command: {command}")

        # Command 7 short format (0xE0-0xFF) overlaps with long command prefix,
        # so command 7 must always use long format
        use_long = long_form or count > 32 or command == 7

        if use_long:
            len_minus_1 = count - 1
            cmd_byte = 0xE0 | (command << 2) | ((len_minus_1 >> 8) & 0x03)
            self._data.append(cmd_byte)
            self._data.append(len_minus_1 & 0xFF)
        else:
            self._data.append((command << 5) | ((count - 1) & 0x1F))

        # 2-byte offset in little-endian
        self._data.append(offset & 0xFF)
        self._data.append((offset >> 8) & 0xFF)
        return self

    def terminate(self) -> HALStreamBuilder:
        """Add stream terminator (0xFF)."""
        self._data.append(0xFF)
        self._terminated = True
        return self

    def build(self) -> bytes:
        """Build the final HAL stream."""
        return bytes(self._data)

    def build_with_terminator(self) -> bytes:
        """Build the stream with automatic terminator."""
        if not self._terminated:
            self._data.append(0xFF)
            self._terminated = True
        return bytes(self._data)

    @property
    def current_size(self) -> int:
        """Get current stream size without terminator."""
        return len(self._data)


# =============================================================================
# Basic Command Parsing Tests
# =============================================================================


class TestShortCommands:
    """Test short command format parsing (5-bit length)."""

    def test_raw_bytes_minimal(self, injector: ROMInjector) -> None:
        """Test parsing minimal raw bytes command (1 byte)."""
        # Command 0, length 1: 0x00 | 0 = 0x00, followed by 1 byte, then 0xFF
        stream = bytes([0x00, 0xAB, 0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 3  # command + data + terminator

    def test_raw_bytes_max_short(self, injector: ROMInjector) -> None:
        """Test parsing max short raw bytes command (32 bytes)."""
        # Command 0, length 32: 0x00 | 31 = 0x1F
        data = bytes(range(32))
        stream = bytes([0x1F]) + data + bytes([0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 1 + 32 + 1  # command + data + terminator

    def test_8bit_rle(self, injector: ROMInjector) -> None:
        """Test parsing 8-bit RLE command."""
        # Command 1, length 10: (1 << 5) | 9 = 0x29, followed by 1 byte
        stream = bytes([0x29, 0x42, 0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 3

    def test_16bit_rle(self, injector: ROMInjector) -> None:
        """Test parsing 16-bit RLE command."""
        # Command 2, length 5: (2 << 5) | 4 = 0x44, followed by 2 bytes
        stream = bytes([0x44, 0x12, 0x34, 0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 4

    def test_sequence_rle(self, injector: ROMInjector) -> None:
        """Test parsing sequence RLE command."""
        # Command 3, length 8: (3 << 5) | 7 = 0x67, followed by 1 byte
        stream = bytes([0x67, 0x00, 0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 3

    def test_forward_backref(self, injector: ROMInjector) -> None:
        """Test parsing forward backref command (4)."""
        # Command 4, length 16: (4 << 5) | 15 = 0x8F, followed by 2-byte offset
        stream = bytes([0x8F, 0x00, 0x00, 0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 4

    def test_backward_backref(self, injector: ROMInjector) -> None:
        """Test parsing backward backref command (6)."""
        # Command 6, length 4: (6 << 5) | 3 = 0xC3, followed by 2-byte offset
        stream = bytes([0xC3, 0x10, 0x00, 0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 4


class TestLongCommands:
    """Test long command format parsing (10-bit length)."""

    def test_raw_bytes_long_format(self, injector: ROMInjector) -> None:
        """Test parsing long format raw bytes (> 32 bytes)."""
        # Long command 0: 0xE0 | (cmd << 2) | (len >> 8) = 0xE0 | 0 | 0 = 0xE0
        # Length 100: stored as (100-1) = 99 = 0x63
        data = bytes(100)
        stream = bytes([0xE0, 0x63]) + data + bytes([0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 2 + 100 + 1  # cmd+len + data + terminator

    def test_8bit_rle_long_format(self, injector: ROMInjector) -> None:
        """Test parsing long format 8-bit RLE."""
        # Long command 1: 0xE0 | (1 << 2) | 0 = 0xE4
        # Length 256: stored as (256-1) = 255 = 0xFF
        stream = bytes([0xE4, 0xFF, 0x42, 0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 4

    def test_16bit_rle_long_format(self, injector: ROMInjector) -> None:
        """Test parsing long format 16-bit RLE."""
        # Long command 2: 0xE0 | (2 << 2) | 0 = 0xE8
        # Length 64: stored as 63 = 0x3F
        stream = bytes([0xE8, 0x3F, 0x12, 0x34, 0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 5

    def test_backref_long_format(self, injector: ROMInjector) -> None:
        """Test parsing long format backref."""
        # Long command 4: 0xE0 | (4 << 2) | 1 = 0xF1
        # Length 300: stored as 299, high bits in cmd byte: (299 >> 8) = 1
        # Low byte: 299 & 0xFF = 43 = 0x2B
        stream = bytes([0xF1, 0x2B, 0x00, 0x01, 0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 5

    def test_max_length_long_format(self, injector: ROMInjector) -> None:
        """Test parsing maximum length in long format (1024 bytes)."""
        # Max length is 1024 (stored as 1023 = 0x3FF)
        # Command 1 (8-bit RLE): 0xE0 | (1 << 2) | 3 = 0xE7
        # Length byte: 0xFF
        stream = bytes([0xE7, 0xFF, 0x00, 0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 4


# =============================================================================
# Builder-based Tests
# =============================================================================


class TestWithBuilder:
    """Tests using HALStreamBuilder for complex streams."""

    def test_simple_rle_sequence(self, injector: ROMInjector) -> None:
        """Test parsing simple RLE followed by raw bytes."""
        stream = (
            HALStreamBuilder()
            .rle_8bit(0x00, 16)  # 16 zeros
            .raw_bytes(b"HELLO")  # 5 literal bytes
            .rle_8bit(0xFF, 8)  # 8 0xFF bytes
            .build_with_terminator()
        )

        rom_data = bytes(50) + stream + bytes(50)
        offset = 50

        size = injector._parse_hal_compressed_size(rom_data, offset)

        # Expected: 2 + 6 + 2 + 1 = 11 bytes
        # rle_8bit(16): cmd + byte = 2
        # raw_bytes(5): cmd + 5 bytes = 6
        # rle_8bit(8): cmd + byte = 2
        # terminator: 1
        assert size == 2 + 6 + 2 + 1

    def test_mixed_commands(self, injector: ROMInjector) -> None:
        """Test parsing stream with multiple command types."""
        stream = (
            HALStreamBuilder()
            .raw_bytes(bytes(range(10)))  # 10 raw bytes
            .rle_16bit(0x1234, 8)  # 8 16-bit words
            .sequence_rle(0x40, 20)  # 20 sequential bytes
            .backref(0, 32, command=4)  # Forward backref
            .build_with_terminator()
        )

        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        # raw_bytes(10): 1 + 10 = 11
        # rle_16bit(8): 1 + 2 = 3
        # sequence_rle(20): 1 + 1 = 2
        # backref(32): 1 + 2 = 3
        # terminator: 1
        assert size == 11 + 3 + 2 + 3 + 1

    def test_long_and_short_mixed(self, injector: ROMInjector) -> None:
        """Test parsing mix of long and short format commands."""
        stream = (
            HALStreamBuilder()
            .rle_8bit(0x42, 10)  # Short format (10 < 32)
            .rle_8bit(0x00, 100, long_form=True)  # Long format
            .raw_bytes(bytes(5))  # Short format
            .build_with_terminator()
        )

        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        # rle_8bit short: 1 + 1 = 2
        # rle_8bit long: 2 + 1 = 3
        # raw_bytes short: 1 + 5 = 6
        # terminator: 1
        assert size == 2 + 3 + 6 + 1


# =============================================================================
# Edge Cases and Boundary Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_stream_only_terminator(self, injector: ROMInjector) -> None:
        """Test parsing stream with only terminator."""
        stream = bytes([0xFF])
        rom_data = bytes(100) + stream + bytes(100)
        offset = 100

        size = injector._parse_hal_compressed_size(rom_data, offset)

        assert size == 1

    def test_offset_at_start_of_rom(self, injector: ROMInjector) -> None:
        """Test parsing at offset 0."""
        stream = bytes([0x20, 0x42, 0xFF])  # Simple 8-bit RLE
        rom_data = stream + bytes(100)

        size = injector._parse_hal_compressed_size(rom_data, 0)

        assert size == 3

    def test_offset_near_end_of_rom(self, injector: ROMInjector) -> None:
        """Test parsing near end of ROM data."""
        stream = bytes([0x20, 0x42, 0xFF])
        rom_data = bytes(100) + stream

        size = injector._parse_hal_compressed_size(rom_data, 100)

        assert size == 3

    def test_truncated_stream_no_terminator(self, injector: ROMInjector) -> None:
        """Test handling stream that runs into end of data without terminator."""
        # Stream with command but no terminator
        stream = bytes([0x20, 0x42])  # 8-bit RLE, but no terminator
        rom_data = stream

        size = injector._parse_hal_compressed_size(rom_data, 0)

        # Should return the size consumed (reaches end)
        assert size == 2

    def test_truncated_long_command(self, injector: ROMInjector) -> None:
        """Test handling truncated long command."""
        # Long command header but missing length byte
        stream = bytes([0xE4])  # Long command 1, but missing second byte
        rom_data = stream

        size = injector._parse_hal_compressed_size(rom_data, 0)

        # Should return size consumed
        assert size == 1

    def test_64kb_limit(self, injector: ROMInjector) -> None:
        """Test that parsing stops at 64KB limit."""
        # Create a stream that could theoretically extend beyond 64KB
        # (no terminator within 64KB)
        rom_data = bytes(0x20000)  # 128KB of zeros
        # Zeros are valid as command 0 with length 1

        size = injector._parse_hal_compressed_size(rom_data, 0)

        # Should stop at 64KB limit
        assert size <= 0x10000

    def test_all_backref_types(self, injector: ROMInjector) -> None:
        """Test all backref command types (4, 5, 6, 7)."""
        for cmd in (4, 5, 6, 7):
            stream = HALStreamBuilder().backref(0, 10, command=cmd).build_with_terminator()

            rom_data = bytes(100) + stream + bytes(100)
            offset = 100

            size = injector._parse_hal_compressed_size(rom_data, offset)

            # Commands 4-6: short format = 1 (cmd) + 2 (offset) + 1 (term) = 4
            # Command 7: must use long format = 2 (cmd+len) + 2 (offset) + 1 (term) = 5
            expected_size = 5 if cmd == 7 else 4
            assert size == expected_size, f"Failed for backref command {cmd}"


# =============================================================================
# Real HAL Binary Comparison Tests
# =============================================================================


@pytest.mark.real_hal
class TestRealHALComparison:
    """Tests that compare parser output against real exhal binary.

    These tests require the exhal binary to be available.
    Skip with: pytest -m "not real_hal"
    """

    @pytest.fixture
    def temp_files(self, tmp_path: Path) -> Generator[tuple[Path, Path, Path], None, None]:
        """Create temporary files for HAL operations."""
        input_file = tmp_path / "input.bin"
        compressed_file = tmp_path / "compressed.bin"
        decompressed_file = tmp_path / "decompressed.bin"
        yield input_file, compressed_file, decompressed_file

    def _compress_with_inhal(
        self,
        input_data: bytes,
        input_file: Path,
        compressed_file: Path,
    ) -> bytes | None:
        """Compress data using real inhal binary.

        Returns compressed data or None if inhal not available.
        """
        import shutil

        inhal_path = shutil.which("inhal")
        if not inhal_path:
            pytest.skip("inhal binary not found")
            return None

        # Write input data
        input_file.write_bytes(input_data)

        # Run inhal
        result = subprocess.run(
            [inhal_path, str(input_file), str(compressed_file)],
            capture_output=True,
            timeout=10,
        )

        if result.returncode != 0:
            pytest.fail(f"inhal failed: {result.stderr.decode()}")
            return None

        return compressed_file.read_bytes()

    def _decompress_with_exhal(
        self,
        rom_data: bytes,
        offset: int,
        rom_file: Path,
        output_file: Path,
    ) -> tuple[bytes, int] | None:
        """Decompress data using real exhal binary.

        Returns (decompressed_data, compressed_size) or None.
        """
        import shutil

        exhal_path = shutil.which("exhal")
        if not exhal_path:
            pytest.skip("exhal binary not found")
            return None

        # Write ROM data
        rom_file.write_bytes(rom_data)

        # Run exhal
        result = subprocess.run(
            [exhal_path, str(rom_file), str(hex(offset)), str(output_file)],
            capture_output=True,
            timeout=10,
        )

        if result.returncode != 0:
            return None

        decompressed = output_file.read_bytes()

        # Parse compressed size from exhal output (if available)
        # exhal typically reports the size, we need to parse it
        return decompressed, -1  # Size not available from exhal output

    def test_simple_rle_pattern(
        self,
        injector: ROMInjector,
        temp_files: tuple[Path, Path, Path],
    ) -> None:
        """Test parser matches exhal for simple RLE pattern."""
        input_file, compressed_file, _ = temp_files

        # Create simple repeating pattern
        input_data = bytes([0x42] * 256)

        compressed = self._compress_with_inhal(input_data, input_file, compressed_file)
        if compressed is None:
            return

        # Embed compressed data in "ROM"
        rom_data = bytes(0x1000) + compressed + bytes(0x1000)
        offset = 0x1000

        # Parse with our implementation
        parsed_size = injector._parse_hal_compressed_size(rom_data, offset)

        # Compare: our parsed size should match actual compressed size
        assert parsed_size == len(compressed)

    def test_mixed_pattern(
        self,
        injector: ROMInjector,
        temp_files: tuple[Path, Path, Path],
    ) -> None:
        """Test parser matches exhal for mixed pattern data."""
        input_file, compressed_file, _ = temp_files

        # Create mixed pattern: some repeating, some varied
        input_data = (
            bytes([0x00] * 32)
            + bytes(range(256))
            + bytes([0xFF] * 64)
            + bytes([0x12, 0x34] * 50)
        )

        compressed = self._compress_with_inhal(input_data, input_file, compressed_file)
        if compressed is None:
            return

        rom_data = bytes(0x1000) + compressed + bytes(0x1000)
        offset = 0x1000

        parsed_size = injector._parse_hal_compressed_size(rom_data, offset)

        assert parsed_size == len(compressed)

    def test_random_like_pattern(
        self,
        injector: ROMInjector,
        temp_files: tuple[Path, Path, Path],
    ) -> None:
        """Test parser matches exhal for pseudo-random data."""
        input_file, compressed_file, _ = temp_files

        # Create pseudo-random pattern (not truly random for reproducibility)
        import hashlib

        input_data = hashlib.sha256(b"test seed").digest() * 32  # 1024 bytes

        compressed = self._compress_with_inhal(input_data, input_file, compressed_file)
        if compressed is None:
            return

        rom_data = bytes(0x1000) + compressed + bytes(0x1000)
        offset = 0x1000

        parsed_size = injector._parse_hal_compressed_size(rom_data, offset)

        assert parsed_size == len(compressed)


# =============================================================================
# Regression Tests
# =============================================================================


class TestKnownPatterns:
    """Test known HAL patterns that have caused issues in the past."""

    def test_pattern_starting_with_e0_range(self, injector: ROMInjector) -> None:
        """Test patterns where first byte is in 0xE0-0xFF range.

        These bytes trigger long command parsing.
        """
        # 0xE0 is long command 0, length byte follows
        stream = bytes([0xE0, 0x03, 0x11, 0x22, 0x33, 0x44, 0xFF])
        rom_data = bytes(100) + stream + bytes(100)

        size = injector._parse_hal_compressed_size(rom_data, 100)

        # Long cmd 0, length 4: 2 bytes header + 4 bytes data + 1 terminator
        assert size == 7

    def test_pattern_with_ff_in_data(self, injector: ROMInjector) -> None:
        """Test pattern with 0xFF in raw data (not terminator)."""
        # Raw bytes containing 0xFF should not terminate stream
        stream = bytes([0x02, 0xFF, 0x00, 0xFF, 0xFF])  # 3 raw bytes including 0xFF, then terminator
        rom_data = bytes(100) + stream + bytes(100)

        size = injector._parse_hal_compressed_size(rom_data, 100)

        # cmd (1) + 3 raw bytes + terminator (1)
        assert size == 5

    def test_sequential_terminator_look_alike(self, injector: ROMInjector) -> None:
        """Test that 0xFF in non-command position doesn't terminate."""
        # Build stream with 0xFF values in data positions
        stream = (
            HALStreamBuilder()
            .rle_8bit(0xFF, 5)  # Output 5 0xFF bytes (but command byte != 0xFF)
            .raw_bytes(bytes([0xFF, 0xFF]))  # 2 literal 0xFF bytes
            .build_with_terminator()
        )

        rom_data = bytes(100) + stream + bytes(100)

        size = injector._parse_hal_compressed_size(rom_data, 100)

        # rle: 2, raw(2): 3, terminator: 1 = 6
        assert size == 2 + 3 + 1
