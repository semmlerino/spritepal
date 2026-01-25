"""
Tests for preview worker safety improvements.

Crash fix: Validate offset and file before attempting extraction.
Split from tests/integration/test_rom_extraction_regression.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from ui.rom_extraction.workers.preview_worker import SpritePreviewWorker

pytestmark = [
    pytest.mark.headless,
]


class TestPreviewWorkerSafety:
    """Test preview worker safety improvements.

    Crash fix: Validate offset and file before attempting extraction.
    """

    def test_preview_worker_invalid_offset(self, tmp_path):
        """Test preview worker with invalid offset"""
        # Mock extractor
        mock_extractor = Mock()

        # Create a valid ROM file
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"\x00" * 0x10000)  # 64KB dummy ROM

        # Create worker with invalid (negative) offset
        worker = SpritePreviewWorker(rom_path=str(rom_file), offset=-1, sprite_name="test", extractor=mock_extractor)

        # Mock the error signal
        error_messages = []
        worker.preview_error.connect(lambda msg: error_messages.append(msg))

        # Run the worker
        worker.run()

        # Verify error was emitted
        assert len(error_messages) == 1
        assert "Invalid" in error_messages[0]
        assert "negative" in error_messages[0]

    def test_preview_worker_file_not_found(self):
        """Test preview worker with non-existent ROM file"""
        mock_extractor = Mock()

        worker = SpritePreviewWorker(
            rom_path="/nonexistent/rom.sfc", offset=0x8000, sprite_name="test", extractor=mock_extractor
        )

        error_messages = []
        worker.preview_error.connect(lambda msg: error_messages.append(msg))

        worker.run()

        assert len(error_messages) == 1
        assert "ROM file not found" in error_messages[0]

    def test_preview_worker_offset_beyond_rom_size(self):
        """Test preview worker with offset beyond ROM size"""
        mock_extractor = Mock()

        # Create a small temporary ROM file
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(b"A" * 0x8000)  # 32KB ROM
            tmp_file.flush()

            try:
                worker = SpritePreviewWorker(
                    rom_path=tmp_file.name,
                    offset=0x10000,  # Offset beyond file size
                    sprite_name="test",
                    extractor=mock_extractor,
                )

                error_messages = []
                worker.preview_error.connect(lambda msg: error_messages.append(msg))

                worker.run()

                assert len(error_messages) == 1
                assert "beyond ROM size" in error_messages[0]

            finally:
                Path(tmp_file.name).unlink()
