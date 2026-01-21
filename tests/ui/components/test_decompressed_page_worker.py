"""
Unit tests for the DecompressedPageWorker.

Tests the background worker that attempts HAL decompression at grid positions
to show actual sprites instead of raw compressed bytes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtGui import QImage

from tests.fixtures.timeouts import worker_timeout
from ui.workers.decompressed_page_worker import (
    CELL_SIZE,
    DecompressedPageWorker,
)


class TestDecompressedPageWorkerInit:
    """Test DecompressedPageWorker initialization."""

    def test_init_stores_parameters(self) -> None:
        """Test that constructor stores all parameters."""
        rom_data = b"\x00" * 1000
        mock_injector = MagicMock()
        palette = [[0, 0, 0]] * 16

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=5,
            offset=0x1000,
            cols=4,
            rows=4,
            step_size=256,
            palette=palette,
        )

        assert worker._page_number == 5
        assert worker._offset == 0x1000
        assert worker._cols == 4
        assert worker._rows == 4
        assert worker._step_size == 256
        assert worker._palette == palette

    def test_properties(self) -> None:
        """Test property accessors."""
        rom_data = b"\x00" * 1000
        mock_injector = MagicMock()

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=3,
            offset=0x500,
            cols=8,
            rows=8,
            step_size=128,
        )

        assert worker.page_number == 3
        assert worker.offset == 0x500
        assert worker.step_size == 128


class TestDecompressedPageWorkerRendering:
    """Test DecompressedPageWorker rendering methods."""

    def test_placeholder_image_dimensions(self, qtbot) -> None:
        """Test that placeholder images have correct dimensions."""
        rom_data = b"\x00" * 1000
        mock_injector = MagicMock()

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=0,
            offset=0,
            cols=4,
            rows=4,
            step_size=256,
        )

        placeholder = worker._create_placeholder_image()

        assert placeholder.width() == CELL_SIZE
        assert placeholder.height() == CELL_SIZE
        assert not placeholder.isNull()

    def test_compose_grid_dimensions(self, qtbot) -> None:
        """Test that composed grid has correct dimensions."""
        rom_data = b"\x00" * 1000
        mock_injector = MagicMock()
        cols, rows = 4, 3

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=0,
            offset=0,
            cols=cols,
            rows=rows,
            step_size=256,
        )

        # Create placeholder images for all cells
        placeholders = [worker._create_placeholder_image() for _ in range(cols * rows)]

        composite = worker._compose_grid(placeholders)

        assert composite.width() == cols * CELL_SIZE
        assert composite.height() == rows * CELL_SIZE
        assert not composite.isNull()

    def test_try_decompress_cell_out_of_bounds(self, qtbot) -> None:
        """Test that out-of-bounds offsets return placeholder."""
        rom_data = b"\x00" * 100
        mock_injector = MagicMock()

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=0,
            offset=0,
            cols=4,
            rows=4,
            step_size=256,
        )

        # Offset beyond ROM size
        result = worker._try_decompress_cell(1000)

        assert result.width() == CELL_SIZE
        assert result.height() == CELL_SIZE

    def test_try_decompress_cell_failure(self, qtbot) -> None:
        """Test that decompression failures return placeholder."""
        rom_data = b"\x00" * 1000
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.side_effect = ValueError("Not valid HAL data")

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=0,
            offset=0,
            cols=4,
            rows=4,
            step_size=256,
        )

        result = worker._try_decompress_cell(0)

        assert result.width() == CELL_SIZE
        assert result.height() == CELL_SIZE

    def test_try_decompress_cell_empty_data(self, qtbot) -> None:
        """Test that empty decompression results return placeholder."""
        rom_data = b"\x00" * 1000
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"", 0)

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=0,
            offset=0,
            cols=4,
            rows=4,
            step_size=256,
        )

        result = worker._try_decompress_cell(0)

        assert result.width() == CELL_SIZE
        assert result.height() == CELL_SIZE


class TestDecompressedPageWorkerSignals:
    """Test DecompressedPageWorker signal emissions."""

    def test_page_ready_signal_emitted(self, qtbot) -> None:
        """Test that page_ready signal is emitted on completion."""
        # Create minimal ROM data and mock injector that returns empty data
        rom_data = b"\x00" * 1000
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"", 0)

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=0,
            offset=0,
            cols=2,  # Small grid for fast test
            rows=2,
            step_size=256,
        )

        # Wait for page_ready signal
        with qtbot.waitSignal(worker.page_ready, timeout=worker_timeout()) as blocker:
            worker.start()

        # Verify signal was emitted with correct arguments
        page_number, image, offset, palette_hash = blocker.args
        assert page_number == 0
        assert offset == 0
        assert isinstance(image, QImage)
        assert not image.isNull()

    def test_worker_can_be_cancelled(self, qtbot) -> None:
        """Test that worker responds to cancellation."""
        rom_data = b"\x00" * 10000
        mock_injector = MagicMock()
        # Make decompression slow by delaying
        mock_injector.find_compressed_sprite.return_value = (0, b"", 0)

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=0,
            offset=0,
            cols=10,  # Larger grid
            rows=10,
            step_size=256,
        )

        worker.start()
        worker.cancel()

        # Worker should finish (either completing or being cancelled)
        worker.wait(worker_timeout())
        assert not worker.isRunning()


class TestDecompressedPageWorkerPaletteHash:
    """Test palette hash computation in DecompressedPageWorker."""

    def test_palette_hash_with_palette(self, qtbot) -> None:
        """Test that palette hash is computed when palette provided."""
        rom_data = b"\x00" * 1000
        mock_injector = MagicMock()
        palette = [[i, i, i] for i in range(16)]

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=0,
            offset=0,
            cols=4,
            rows=4,
            step_size=256,
            palette=palette,
        )

        # Hash should be non-zero for non-None palette
        assert worker.palette_hash != 0

    def test_palette_hash_without_palette(self, qtbot) -> None:
        """Test that palette hash is zero when no palette provided."""
        rom_data = b"\x00" * 1000
        mock_injector = MagicMock()

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=0,
            offset=0,
            cols=4,
            rows=4,
            step_size=256,
            palette=None,
        )

        assert worker.palette_hash == 0


class TestDecompressedPageWorkerIntegration:
    """Integration tests for DecompressedPageWorker with mock tile renderer."""

    def test_render_with_valid_tile_data(self, qtbot) -> None:
        """Test rendering when decompression returns valid tile data."""
        rom_data = b"\x00" * 1000
        mock_injector = MagicMock()

        # Return 32 bytes (one valid 4bpp tile)
        valid_tile = bytes(32)
        mock_injector.find_compressed_sprite.return_value = (32, valid_tile, 0)

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=0,
            offset=0,
            cols=2,
            rows=2,
            step_size=256,
        )

        # Should complete successfully
        with qtbot.waitSignal(worker.page_ready, timeout=worker_timeout()):
            worker.start()

    def test_mixed_success_failure_cells(self, qtbot) -> None:
        """Test grid with some successful and some failed decompressions."""
        rom_data = b"\x00" * 1000
        mock_injector = MagicMock()

        # Alternate between success and failure
        call_count = [0]

        def alternate_response(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                return (32, bytes(32), 0)  # Valid tile
            else:
                raise ValueError("Invalid data")

        mock_injector.find_compressed_sprite.side_effect = alternate_response

        worker = DecompressedPageWorker(
            rom_data=rom_data,
            rom_injector=mock_injector,
            page_number=0,
            offset=0,
            cols=2,
            rows=2,
            step_size=256,
        )

        # Should complete successfully despite some failures
        with qtbot.waitSignal(worker.page_ready, timeout=worker_timeout()):
            worker.start()
