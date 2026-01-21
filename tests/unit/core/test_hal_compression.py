"""
Tests for HAL compression logic and subprocess handling.
"""

from __future__ import annotations

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from core.hal_compression import HALCompressionError, HALCompressor

pytestmark = [
    pytest.mark.headless,
    pytest.mark.unit,
]


class TestHALTimeout:
    """Tests for subprocess timeout protection."""

    def test_timeout_parameter_in_subprocess(self):
        """Verify subprocess.run is called with timeout parameter."""
        compressor = HALCompressor()

        with (
            patch("subprocess.run") as mock_run,
            tempfile.NamedTemporaryFile(suffix=".sfc", delete=False) as tmp_rom,
        ):
            # Create a minimal ROM file
            tmp_rom.write(b"\x00" * 1024)
            tmp_rom.flush()

            # Configure mock to simulate successful decompression
            mock_run.return_value = MagicMock(returncode=0)

            try:
                # This will fail because output file is empty, but we're testing
                # that timeout is passed to subprocess.run
                compressor.decompress_from_rom(tmp_rom.name, 0)
            except Exception:
                pass  # Expected to fail, we're just checking the call

            # Verify timeout was passed
            assert mock_run.called
            call_kwargs = mock_run.call_args.kwargs
            assert "timeout" in call_kwargs
            assert call_kwargs["timeout"] == 30

    def test_timeout_raises_hal_error(self):
        """Verify TimeoutExpired is converted to HALCompressionError."""
        import subprocess

        compressor = HALCompressor()

        with (
            patch("subprocess.run") as mock_run,
            tempfile.NamedTemporaryFile(suffix=".sfc", delete=False) as tmp_rom,
        ):
            tmp_rom.write(b"\x00" * 1024)
            tmp_rom.flush()

            # Simulate timeout
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="exhal", timeout=30)

            with pytest.raises(HALCompressionError) as exc_info:
                compressor.decompress_from_rom(tmp_rom.name, 0)

            assert "timed out" in str(exc_info.value).lower()
