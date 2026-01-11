"""Tests for HAL decompression bomb prevention.

Bug: `decompress_from_rom()` reads entire decompressed file into memory
BEFORE checking size, allowing potential DoS via memory exhaustion.

Expected behavior: Check file size BEFORE reading to prevent bomb.
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.hal_compression import HALCompressionError, HALCompressor


@pytest.fixture
def hal_compressor(tmp_path) -> HALCompressor:
    """Create HALCompressor with mocked exhal path."""
    compressor = HALCompressor()
    # Point to a fake exhal - we'll mock subprocess.run anyway
    compressor.exhal_path = "/usr/bin/true"  # Any executable that exists
    return compressor


@pytest.fixture
def mock_rom_file(tmp_path) -> str:
    """Create a dummy ROM file large enough for offset validation."""
    rom_path = tmp_path / "test.smc"
    # Create a ROM file large enough for offset validation (64KB)
    rom_path.write_bytes(b"\x00" * (64 * 1024))
    return str(rom_path)


class TestDecompressionSizeLimitBeforeRead:
    """Tests for checking file size BEFORE reading into memory."""

    def test_decompression_respects_size_limit(
        self, hal_compressor: HALCompressor, mock_rom_file: str, tmp_path
    ) -> None:
        """Decompression should check size BEFORE reading data."""
        # Create an oversized output file (100KB, exceeds 64KB limit)
        oversized_data = b"\x00" * (100 * 1024)

        def mock_subprocess_run(cmd, **kwargs):
            """Mock exhal to create oversized output file."""
            # cmd format: [exhal_path, rom_path, offset_hex, output_path]
            output_path = cmd[3]
            Path(output_path).write_bytes(oversized_data)

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            # Disable pool to force subprocess fallback
            hal_compressor._pool = None

            with pytest.raises(HALCompressionError) as exc_info:
                hal_compressor.decompress_from_rom(mock_rom_file, 0x1000)

            # Error should mention size limit
            error_msg = str(exc_info.value).lower()
            assert "64" in error_msg or "limit" in error_msg or "bomb" in error_msg, (
                f"Error should mention size limit: {exc_info.value}"
            )

    def test_decompression_accepts_data_within_limit(
        self, hal_compressor: HALCompressor, mock_rom_file: str, tmp_path
    ) -> None:
        """Data within 64KB limit should be accepted."""
        # Create a valid-sized output file (1KB)
        valid_data = b"\x00" * 1024

        def mock_subprocess_run(cmd, **kwargs):
            output_path = cmd[3]
            Path(output_path).write_bytes(valid_data)

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            hal_compressor._pool = None

            data = hal_compressor.decompress_from_rom(mock_rom_file, 0x1000)

            assert len(data) == 1024

    def test_custom_size_limit_is_respected(self, hal_compressor: HALCompressor, mock_rom_file: str) -> None:
        """Custom max_decompressed_size parameter should be respected."""
        # Create output file that's 10KB
        test_data = b"\x00" * (10 * 1024)

        def mock_subprocess_run(cmd, **kwargs):
            output_path = cmd[3]
            Path(output_path).write_bytes(test_data)

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            hal_compressor._pool = None

            # With custom limit of 5KB, 10KB file should be rejected
            with pytest.raises(HALCompressionError):
                hal_compressor.decompress_from_rom(mock_rom_file, 0x1000, max_decompressed_size=5 * 1024)

            # With custom limit of 20KB, 10KB file should be accepted
            data = hal_compressor.decompress_from_rom(mock_rom_file, 0x1000, max_decompressed_size=20 * 1024)
            assert len(data) == 10 * 1024


class TestOversizedFileCleanup:
    """Tests for cleanup of oversized temp files."""

    def test_size_check_cleans_up_oversized_file(
        self, hal_compressor: HALCompressor, mock_rom_file: str, tmp_path
    ) -> None:
        """Temp file should be deleted even when size check fails."""
        oversized_data = b"\x00" * (100 * 1024)
        created_temp_file = None

        def mock_subprocess_run(cmd, **kwargs):
            nonlocal created_temp_file
            output_path = cmd[3]
            created_temp_file = output_path
            Path(output_path).write_bytes(oversized_data)

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            hal_compressor._pool = None

            with pytest.raises(HALCompressionError):
                hal_compressor.decompress_from_rom(mock_rom_file, 0x1000)

            # Verify temp file was cleaned up
            assert created_temp_file is not None
            assert not Path(created_temp_file).exists(), f"Oversized temp file should be deleted: {created_temp_file}"


class TestDefaultSizeLimit:
    """Tests for default 64KB size limit."""

    def test_default_limit_is_64kb(self, hal_compressor: HALCompressor, mock_rom_file: str) -> None:
        """Default size limit should be 64KB (65536 bytes)."""
        # Create output file at exactly 64KB - should succeed
        valid_data = b"\x00" * 65536

        def mock_subprocess_run(cmd, **kwargs):
            output_path = cmd[3]
            Path(output_path).write_bytes(valid_data)

            result = MagicMock()
            result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            hal_compressor._pool = None

            data = hal_compressor.decompress_from_rom(mock_rom_file, 0x1000)
            assert len(data) == 65536

    def test_exceeding_64kb_by_one_byte_fails(self, hal_compressor: HALCompressor, mock_rom_file: str) -> None:
        """Exceeding 64KB limit by even 1 byte should fail."""
        # Create output file at 64KB + 1 byte
        oversized_data = b"\x00" * 65537

        def mock_subprocess_run(cmd, **kwargs):
            output_path = cmd[3]
            Path(output_path).write_bytes(oversized_data)

            result = MagicMock()
            result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            hal_compressor._pool = None

            with pytest.raises(HALCompressionError):
                hal_compressor.decompress_from_rom(mock_rom_file, 0x1000)
