"""
Fake ThumbnailWorkerController for fast, deterministic testing.

Implements the same signal interface as ThumbnailWorkerController without:
- Threading overhead
- ROM file I/O
- Actual thumbnail generation

Use this instead of MagicMock for tests that need real signal emission.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap


class FakeThumbnailController(QObject):
    """
    Type-safe fake for ThumbnailWorkerController.

    Allows pre-seeding thumbnail results for deterministic testing.
    Emits real Qt signals so tests can use qtbot.waitSignal().

    Example usage:
        fake = FakeThumbnailController()
        # Pre-seed a 32x32 red thumbnail for offset 0x1B0000
        fake.seed_thumbnail(0x1B0000, create_test_pixmap(32, 32, Qt.red))

        with qtbot.waitSignal(fake.thumbnail_ready):
            fake.queue_thumbnail(0x1B0000)

        assert 0x1B0000 in fake.get_queued_offsets()
    """

    # Signals matching real ThumbnailWorkerController
    thumbnail_ready = Signal(int, QPixmap)
    """Emitted when thumbnail is ready. Args: offset (int), pixmap (QPixmap)."""

    progress = Signal(int, int)
    """Progress signal. Args: completed_count, total_count."""

    error = Signal(str)
    """Emitted on error. Args: error_message."""

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        # Pre-seeded thumbnails keyed by offset
        self._seeded_thumbnails: dict[int, QPixmap] = {}
        self._seeded_error: str | None = None

        # Track queue operations for assertions
        self._queued_offsets: list[int] = []
        self._batch_requests: list[tuple[list[int], int, int]] = []

        # Call tracking
        self._start_worker_calls: int = 0
        self._stop_worker_calls: int = 0
        self._queue_thumbnail_calls: int = 0
        self._queue_batch_calls: int = 0

        # State
        self._is_running: bool = False
        self._rom_path: str | None = None

    def seed_thumbnail(self, offset: int, pixmap: QPixmap) -> None:
        """
        Pre-seed a thumbnail result for an offset.

        Args:
            offset: ROM offset
            pixmap: QPixmap to return when this offset is queued
        """
        self._seeded_thumbnails[offset] = pixmap

    def seed_thumbnails(self, thumbnails: dict[int, QPixmap]) -> None:
        """
        Pre-seed multiple thumbnail results.

        Args:
            thumbnails: Dict mapping offset -> QPixmap
        """
        self._seeded_thumbnails.update(thumbnails)

    def seed_error(self, error_message: str) -> None:
        """
        Pre-seed an error to be emitted on any queue operation.

        Args:
            error_message: Error message to emit
        """
        self._seeded_error = error_message

    def start_worker(self, rom_path: str, rom_extractor: Any) -> None:
        """
        Simulate starting the worker.

        Args:
            rom_path: Path to ROM file (stored for reference)
            rom_extractor: ROM extractor (ignored in fake)
        """
        self._start_worker_calls += 1
        self._rom_path = rom_path
        self._is_running = True

    def stop_worker(self) -> None:
        """Simulate stopping the worker."""
        self._stop_worker_calls += 1
        self._is_running = False

    def queue_thumbnail(self, offset: int, size: int = 384, priority: int = 0) -> None:
        """
        Queue a thumbnail for generation.

        If a pre-seeded thumbnail exists for this offset, emits it immediately.
        Otherwise just tracks the request.

        Args:
            offset: ROM offset
            size: Thumbnail size (ignored in fake)
            priority: Priority (ignored in fake)
        """
        self._queue_thumbnail_calls += 1
        self._queued_offsets.append(offset)

        if self._seeded_error:
            self.error.emit(self._seeded_error)
            return

        if offset in self._seeded_thumbnails:
            pixmap = self._seeded_thumbnails[offset]
            self.thumbnail_ready.emit(offset, pixmap)
            # Emit progress (1 of 1)
            self.progress.emit(1, 1)

    def queue_batch(self, offsets: list[int], size: int = 384, priority_start: int = 0) -> None:
        """
        Queue multiple thumbnails for generation.

        Emits pre-seeded thumbnails immediately for any matching offsets.

        Args:
            offsets: List of ROM offsets
            size: Thumbnail size for all (ignored in fake)
            priority_start: Starting priority (ignored in fake)
        """
        self._queue_batch_calls += 1
        self._batch_requests.append((offsets.copy(), size, priority_start))

        if self._seeded_error:
            self.error.emit(self._seeded_error)
            return

        total = len(offsets)
        completed = 0
        for offset in offsets:
            self._queued_offsets.append(offset)
            if offset in self._seeded_thumbnails:
                pixmap = self._seeded_thumbnails[offset]
                self.thumbnail_ready.emit(offset, pixmap)
                completed += 1
                self.progress.emit(completed, total)

    def clear_queue(self) -> None:
        """Clear the pending queue."""
        self._queued_offsets.clear()

    def is_running(self) -> bool:
        """Check if worker is running."""
        return self._is_running

    def cleanup(self) -> None:
        """Clean up the controller and stop worker."""
        self.stop_worker()

    # ============ Test helper methods ============

    def get_queued_offsets(self) -> list[int]:
        """Get list of all offsets that were queued."""
        return self._queued_offsets.copy()

    def get_batch_requests(self) -> list[tuple[list[int], int, int]]:
        """Get list of all batch requests (offsets, size, priority_start)."""
        return self._batch_requests.copy()

    def verify_called(
        self,
        start_worker: int | None = None,
        stop_worker: int | None = None,
        queue_thumbnail: int | None = None,
        queue_batch: int | None = None,
    ) -> None:
        """
        Assert expected call counts.

        Args:
            start_worker: Expected number of start_worker() calls
            stop_worker: Expected number of stop_worker() calls
            queue_thumbnail: Expected number of queue_thumbnail() calls
            queue_batch: Expected number of queue_batch() calls

        Raises:
            AssertionError: If actual calls don't match expected
        """
        if start_worker is not None:
            assert self._start_worker_calls == start_worker, (
                f"Expected {start_worker} start_worker() calls, got {self._start_worker_calls}"
            )
        if stop_worker is not None:
            assert self._stop_worker_calls == stop_worker, (
                f"Expected {stop_worker} stop_worker() calls, got {self._stop_worker_calls}"
            )
        if queue_thumbnail is not None:
            assert self._queue_thumbnail_calls == queue_thumbnail, (
                f"Expected {queue_thumbnail} queue_thumbnail() calls, got {self._queue_thumbnail_calls}"
            )
        if queue_batch is not None:
            assert self._queue_batch_calls == queue_batch, (
                f"Expected {queue_batch} queue_batch() calls, got {self._queue_batch_calls}"
            )

    def reset(self) -> None:
        """Reset all state for reuse in multiple tests."""
        self._seeded_thumbnails.clear()
        self._seeded_error = None
        self._queued_offsets.clear()
        self._batch_requests.clear()
        self._start_worker_calls = 0
        self._stop_worker_calls = 0
        self._queue_thumbnail_calls = 0
        self._queue_batch_calls = 0
        self._is_running = False
        self._rom_path = None


def create_test_pixmap(width: int = 32, height: int = 32, color: int = 0xFF0000) -> QPixmap:
    """
    Create a simple test QPixmap for seeding thumbnails.

    Args:
        width: Pixmap width
        height: Pixmap height
        color: Fill color as RGB int (default red: 0xFF0000)

    Returns:
        QPixmap filled with the specified color
    """
    from PySide6.QtGui import QColor

    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor.fromRgb(color))
    return QPixmap.fromImage(image)
