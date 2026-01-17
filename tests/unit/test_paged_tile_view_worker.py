"""
Tests for PagedTileViewWorker.

Tests the background worker that renders tile grid pages.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QImage

from tests.fixtures.timeouts import worker_timeout
from ui.workers.paged_tile_view_worker import (
    BYTES_PER_TILE,
    PagedTileViewWorker,
    _compute_palette_hash,
)


class TestComputePaletteHash:
    """Test palette hash computation."""

    def test_none_palette(self) -> None:
        """Test hash of None palette."""
        assert _compute_palette_hash(None) == 0

    def test_empty_palette(self) -> None:
        """Test hash of empty palette."""
        assert _compute_palette_hash([]) == 0

    def test_standard_palette(self) -> None:
        """Test hash of standard palette."""
        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        hash1 = _compute_palette_hash(palette)
        hash2 = _compute_palette_hash(palette)
        assert hash1 == hash2
        assert hash1 != 0

    def test_different_palettes_different_hashes(self) -> None:
        """Test that different palettes produce different hashes."""
        palette1 = [[255, 0, 0] for _ in range(16)]
        palette2 = [[0, 255, 0] for _ in range(16)]
        hash1 = _compute_palette_hash(palette1)
        hash2 = _compute_palette_hash(palette2)
        assert hash1 != hash2


class TestPagedTileViewWorker:
    """Test the PagedTileViewWorker implementation."""

    @pytest.fixture
    def sample_rom_data(self) -> bytes:
        """Create sample ROM data with enough bytes for testing."""
        # Create data for 100x100 tiles = 10000 tiles * 32 bytes = 320000 bytes
        return bytes(range(256)) * 1250

    def test_worker_creation(self, sample_rom_data: bytes) -> None:
        """Test worker can be created with valid parameters."""
        worker = PagedTileViewWorker(
            rom_data=sample_rom_data,
            page_number=0,
            offset=0,
            cols=10,
            rows=10,
        )
        assert worker.page_number == 0
        assert worker.offset == 0
        assert worker.palette_hash == 0  # None palette

    def test_worker_with_palette(self, sample_rom_data: bytes) -> None:
        """Test worker with custom palette."""
        palette = [[i * 16, i * 16, i * 16] for i in range(16)]
        worker = PagedTileViewWorker(
            rom_data=sample_rom_data,
            page_number=1,
            offset=3200,
            cols=10,
            rows=10,
            palette=palette,
        )
        assert worker.page_number == 1
        assert worker.offset == 3200
        assert worker.palette_hash != 0

    def test_worker_renders_page(self, qtbot, sample_rom_data: bytes) -> None:
        """Test worker successfully renders a tile page."""
        worker = PagedTileViewWorker(
            rom_data=sample_rom_data,
            page_number=0,
            offset=0,
            cols=10,
            rows=10,
        )

        results: list[tuple[int, QImage, int, int]] = []

        def capture_result(page_num: int, image: QImage, offset: int, palette_hash: int) -> None:
            results.append((page_num, image.copy(), offset, palette_hash))

        worker.page_ready.connect(capture_result)

        with qtbot.waitSignal(worker.operation_finished, timeout=worker_timeout()):
            worker.start()

        # Verify results
        assert len(results) == 1
        page_num, image, offset, palette_hash = results[0]
        assert page_num == 0
        assert offset == 0
        assert palette_hash == 0
        # Image should be 10 cols * 8 pixels = 80 wide, 10 rows * 8 = 80 tall
        assert image.width() == 80
        assert image.height() == 80
        assert not image.isNull()

    def test_worker_renders_with_palette(self, qtbot, sample_rom_data: bytes) -> None:
        """Test worker renders with custom palette."""
        palette = [[255, 0, 0]] + [[i * 16, i * 16, i * 16] for i in range(1, 16)]
        worker = PagedTileViewWorker(
            rom_data=sample_rom_data,
            page_number=0,
            offset=0,
            cols=5,
            rows=5,
            palette=palette,
        )

        results: list[tuple[int, QImage, int, int]] = []

        def capture_result(page_num: int, image: QImage, offset: int, palette_hash: int) -> None:
            results.append((page_num, image.copy(), offset, palette_hash))

        worker.page_ready.connect(capture_result)

        with qtbot.waitSignal(worker.operation_finished, timeout=worker_timeout()):
            worker.start()

        assert len(results) == 1
        _, image, _, palette_hash = results[0]
        assert image.width() == 40  # 5 * 8
        assert image.height() == 40
        assert palette_hash != 0

    def test_worker_handles_empty_offset(self, qtbot) -> None:
        """Test worker handles offset beyond ROM data."""
        small_rom = bytes(100)  # Very small ROM
        worker = PagedTileViewWorker(
            rom_data=small_rom,
            page_number=0,
            offset=10000,  # Way beyond ROM size
            cols=10,
            rows=10,
        )

        results: list[tuple[int, QImage, int, int]] = []

        def capture_result(page_num: int, image: QImage, offset: int, palette_hash: int) -> None:
            results.append((page_num, image.copy(), offset, palette_hash))

        worker.page_ready.connect(capture_result)

        with qtbot.waitSignal(worker.operation_finished, timeout=worker_timeout()):
            worker.start()

        # Should still emit result, even if empty
        assert len(results) == 1

    def test_worker_cancellation(self, qtbot, sample_rom_data: bytes) -> None:
        """Test worker can be cancelled."""
        # Use large dimensions to ensure worker takes time
        worker = PagedTileViewWorker(
            rom_data=sample_rom_data,
            page_number=0,
            offset=0,
            cols=100,
            rows=100,
        )

        # Cancel before starting (should complete quickly)
        worker.cancel()

        with qtbot.waitSignal(worker.operation_finished, timeout=worker_timeout()):
            worker.start()

        # Worker should have been cancelled
        assert worker.is_cancelled
