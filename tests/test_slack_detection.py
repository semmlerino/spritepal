"""Tests for ROM injector slack detection functionality.

Slack detection identifies padding bytes (0xFF or 0x00) between compressed
sprites in ROM data. This is important for injection to know how much
space is available without relocating data.

Refactored from unittest.TestCase to pytest for consistency with the rest
of the test suite.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.hal_parser import HALParser
from core.rom_injector import ROMInjector


@pytest.fixture
def rom_injector():
    """Create ROMInjector with mocked dependencies."""
    injector = ROMInjector()
    injector.logger = MagicMock()
    injector.hal_compressor = MagicMock()
    injector.hal_compressor.decompress_from_rom.return_value = b"decompressed_data"
    return injector


@pytest.mark.parametrize(
    "slack_bytes,expected_slack_size,description",
    [
        pytest.param(
            b"\xff\xff\xff",
            3,
            "FF padding",
            id="ff_padding",
        ),
        pytest.param(
            b"\x00\x00",
            2,
            "zero padding",
            id="zero_padding",
        ),
        pytest.param(
            b"",
            0,
            "no slack",
            id="no_slack",
        ),
        pytest.param(
            b"\xff" * (ROMInjector.MAX_SLACK_SIZE + 50),
            ROMInjector.MAX_SLACK_SIZE,
            "exceeds limit - capped at MAX_SLACK_SIZE",
            id="exceeds_limit",
        ),
    ],
)
def test_slack_detection(
    rom_injector: ROMInjector,
    slack_bytes: bytes,
    expected_slack_size: int,
    description: str,
) -> None:
    """Verify slack detection correctly identifies padding bytes.

    Slack bytes are 0xFF or 0x00 padding between compressed sprites.
    Detection is capped at MAX_SLACK_SIZE to avoid false positives.

    Args:
        rom_injector: Fixture providing mocked ROMInjector
        slack_bytes: Padding bytes to insert after compressed data
        expected_slack_size: Expected detected slack size
        description: Test case description for debugging
    """
    # Create ROM data: [Compressed(10 bytes)][Slack][NextData(1 byte)]
    compressed_size = 10
    rom_data = bytearray(b"C" * compressed_size + slack_bytes + b"\xaa")

    with patch.object(HALParser, "parse_compressed_size", return_value=compressed_size):
        _, _, slack_size = rom_injector.find_compressed_sprite(rom_data, 0)

    assert slack_size == expected_slack_size, f"Failed for case: {description}"
