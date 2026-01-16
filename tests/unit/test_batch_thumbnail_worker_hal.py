"""Tests for batch thumbnail worker HAL decompression alignment.

These tests verify that the thumbnail worker uses the same HAL decompression
approach as the preview worker, ensuring thumbnails match editor content.
"""

from unittest.mock import MagicMock, patch

import pytest

from ui.workers.batch_thumbnail_worker import BatchThumbnailWorker, ThumbnailRequest


class TestBatchThumbnailWorkerHALAlignment:
    """Test that thumbnail worker uses same HAL decompression path as preview worker."""

    def test_thumbnail_passes_actual_offset_to_find_compressed_sprite(self, tmp_path):
        """
        Thumbnail worker should pass actual ROM offset (not 0) to find_compressed_sprite.

        This test verifies that when generating thumbnails for sprites at a specific
        ROM offset, the worker passes that actual offset to find_compressed_sprite
        rather than offset=0 within a chunk.

        The current buggy code reads a 64KB chunk starting at the offset, then
        passes offset=0 within that chunk. This causes HAL decompression to fail
        due to compression ratio validation, falling back to raw data display.

        Expected: FAIL before fix (currently passes offset=0)
        """
        # Create mock ROM with SMC header (512 bytes) + ROM data
        smc_header = b"\x00" * 512
        # Create some ROM content (at least 64KB + some extra to be realistic)
        rom_content = bytes(range(256)) * 300  # ~76KB of patterned data
        rom_data = smc_header + rom_content

        # Write to temp file
        rom_file = tmp_path / "test.smc"
        rom_file.write_bytes(rom_data)

        # Create mocks
        mock_extractor = MagicMock()
        mock_injector = MagicMock()
        mock_extractor.rom_injector = mock_injector

        # Configure find_compressed_sprite to return valid decompressed data
        # (32 bytes = 1 tile, so rendering will succeed)
        mock_injector.find_compressed_sprite.return_value = (100, b"\x01" * 32, 0)

        # Create worker - patch TileRenderer to avoid actual rendering
        with patch("ui.workers.batch_thumbnail_worker.TileRenderer") as mock_renderer_class:
            mock_renderer = MagicMock()
            mock_renderer_class.return_value = mock_renderer
            # Return a mock PIL Image that will be converted
            mock_image = MagicMock()
            mock_image.mode = "P"
            mock_image.size = (8, 8)
            mock_renderer.render_tiles.return_value = mock_image

            worker = BatchThumbnailWorker(
                rom_path=str(rom_file),
                rom_extractor=mock_extractor,
            )

            # Manually load ROM data (normally done in run() thread)
            worker._load_rom_data()

            # Test offset: 0x100 (256 in decimal) - a typical ROM offset
            test_offset = 0x100

            # Generate thumbnail
            request = ThumbnailRequest(offset=test_offset, size=96)

            # Patch _pil_to_qimage to return a valid QImage mock
            with patch.object(worker, "_pil_to_qimage") as mock_pil_to_qimage:
                mock_qimage = MagicMock()
                mock_qimage.isNull.return_value = False
                mock_qimage.scaled.return_value = mock_qimage
                mock_pil_to_qimage.return_value = mock_qimage

                worker._generate_thumbnail(request)

            # Clean up ROM resources
            worker._clear_rom_data()

        # Verify find_compressed_sprite was called
        assert mock_injector.find_compressed_sprite.called, (
            "find_compressed_sprite should be called for HAL decompression"
        )

        call_args = mock_injector.find_compressed_sprite.call_args
        # Args are (data, offset, expected_size=None)
        positional_args = call_args[0]
        offset_arg = positional_args[1]  # Second positional arg: offset

        # KEY ASSERTION: The offset should be the actual ROM offset, not 0
        # This assertion will FAIL with the current buggy code that passes offset=0
        assert offset_arg == test_offset, (
            f"Expected ROM offset {test_offset} (0x{test_offset:X}), "
            f"got {offset_arg} (0x{offset_arg:X}). "
            "Offset 0 indicates chunk-based access bug where HAL decompression "
            "receives a 64KB chunk with offset=0 instead of full ROM with actual offset."
        )

    def test_thumbnail_passes_full_rom_data_not_chunk(self, tmp_path):
        """
        Thumbnail worker should pass full ROM data (not a 64KB chunk) to find_compressed_sprite.

        The preview worker passes the entire ROM (minus SMC header) to find_compressed_sprite,
        allowing HAL decompression to properly validate compression ratios. The thumbnail
        worker should do the same.

        Expected: FAIL before fix (currently passes a 64KB chunk)
        """
        # Create mock ROM with SMC header (512 bytes) + larger ROM content
        smc_header = b"\x00" * 512
        # Create ROM content larger than 64KB to distinguish full ROM from chunk
        rom_content = bytes(range(256)) * 500  # ~125KB of patterned data
        rom_data = smc_header + rom_content

        # Write to temp file
        rom_file = tmp_path / "test.smc"
        rom_file.write_bytes(rom_data)

        # Create mocks
        mock_extractor = MagicMock()
        mock_injector = MagicMock()
        mock_extractor.rom_injector = mock_injector

        # Configure find_compressed_sprite to return valid decompressed data
        mock_injector.find_compressed_sprite.return_value = (100, b"\x01" * 32, 0)

        # Create worker
        with patch("ui.workers.batch_thumbnail_worker.TileRenderer") as mock_renderer_class:
            mock_renderer = MagicMock()
            mock_renderer_class.return_value = mock_renderer
            mock_image = MagicMock()
            mock_image.mode = "P"
            mock_image.size = (8, 8)
            mock_renderer.render_tiles.return_value = mock_image

            worker = BatchThumbnailWorker(
                rom_path=str(rom_file),
                rom_extractor=mock_extractor,
            )

            # Manually load ROM data
            worker._load_rom_data()

            # Use an offset that would result in a 64KB chunk if chunk-based access is used
            test_offset = 0x100
            request = ThumbnailRequest(offset=test_offset, size=96)

            with patch.object(worker, "_pil_to_qimage") as mock_pil_to_qimage:
                mock_qimage = MagicMock()
                mock_qimage.isNull.return_value = False
                mock_qimage.scaled.return_value = mock_qimage
                mock_pil_to_qimage.return_value = mock_qimage

                worker._generate_thumbnail(request)

            worker._clear_rom_data()

        # Verify find_compressed_sprite was called
        assert mock_injector.find_compressed_sprite.called

        call_args = mock_injector.find_compressed_sprite.call_args
        data_arg = call_args[0][0]  # First positional arg: ROM data

        # KEY ASSERTION: The data should be the full ROM (minus SMC header)
        # not a 64KB chunk. The current buggy code passes a chunk of max 64KB.
        #
        # We check that the data size matches the full ROM content size,
        # not a smaller chunk.
        expected_min_size = len(rom_content)  # Full ROM content without SMC header

        # The data passed should be at least as large as the full ROM content
        # (it might be a memoryview of the full mmap, which is fine)
        assert len(data_arg) >= expected_min_size, (
            f"Expected full ROM data (at least {expected_min_size} bytes), "
            f"got only {len(data_arg)} bytes. "
            f"A 64KB ({0x10000} byte) chunk indicates the bug where thumbnail worker "
            "reads a chunk instead of using the full ROM like preview worker does."
        )
