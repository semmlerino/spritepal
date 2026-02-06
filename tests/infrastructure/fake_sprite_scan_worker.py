"""
Fake SpriteScanWorker for fast, deterministic testing.

Implements the same signal interface as SpriteScanWorker without:
- ROM file I/O operations
- Parallel processing overhead
- Cache interactions

Use this instead of MagicMock for tests that need real signal emission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, Signal


@dataclass(eq=False)
class FakeSpriteScanWorker(QObject):
    """
    Type-safe fake for SpriteScanWorker.

    Allows pre-seeding scan results for deterministic testing.
    Emits real Qt signals so tests can use qtbot.waitSignal().

    Example usage:
        fake_worker = FakeSpriteScanWorker()
        fake_worker.seed_sprites([
            {"offset": 0x1B0000, "quality": 0.95, "tile_count": 16},
            {"offset": 0x1B1000, "quality": 0.85, "tile_count": 8},
        ])

        with qtbot.waitSignal(fake_worker.sprites_found):
            fake_worker.start()  # Emits all seeded sprites immediately

        assert fake_worker.get_found_sprites() == seeded_sprites
    """

    # Custom signals matching real SpriteScanWorker
    sprite_found = Signal(object)
    """Emitted for each sprite found. Args: sprite_info dict."""

    sprites_found = Signal(list)
    """Emitted when scan completes with all found sprites."""

    finished = Signal()
    """Legacy compatibility signal - emitted when scan completes."""

    progress = Signal(int, str)
    """Progress signal. Args: percent (0-100), message."""

    progress_detailed = Signal(int, int)
    """Detailed progress. Args: current_offset, total_offsets."""

    error = Signal(str)
    """Emitted on error. Args: error_message."""

    warning = Signal(str)
    """Emitted for warnings. Args: warning_message."""

    operation_finished = Signal(bool, str)
    """Emitted when operation completes. Args: success, message."""

    cache_status = Signal(str)
    """Cache status updates. Args: status_message."""

    cache_progress = Signal(int)
    """Cache save progress. Args: percent (0-100)."""

    def __init__(self, parent: QObject | None = None):
        # Must call QObject.__init__ for signals to work
        # Can't use dataclass auto-init with QObject
        super().__init__(parent)

        # Pre-seeded results
        self._seeded_sprites: list[dict[str, Any]] = []
        self._seeded_error: str | None = None
        self._emit_progress: bool = True

        # Call tracking
        self._start_calls: int = 0
        self._cancel_calls: int = 0
        self._is_cancelled: bool = False

        # Fake rom_path for compatibility
        self.rom_path: str = "/fake/rom.sfc"

    def seed_sprites(self, sprites: list[dict[str, Any]]) -> None:
        """
        Pre-seed sprite results to be emitted on start().

        Args:
            sprites: List of sprite info dicts with keys like
                     'offset', 'quality', 'tile_count', etc.
        """
        self._seeded_sprites = sprites.copy()

    def seed_error(self, error_message: str) -> None:
        """
        Pre-seed an error to be emitted on start().

        Args:
            error_message: Error message to emit instead of results.
        """
        self._seeded_error = error_message

    def set_emit_progress(self, emit: bool) -> None:
        """
        Control whether progress signals are emitted.

        Args:
            emit: True to emit progress signals (default), False to skip.
        """
        self._emit_progress = emit

    def start(self) -> None:
        """
        Simulate starting the scan.

        Immediately emits pre-seeded results (sync, no threading).
        This is the key difference from the real worker - results are
        emitted synchronously for deterministic testing.
        """
        self._start_calls += 1
        self._is_cancelled = False

        if self._seeded_error:
            self.error.emit(self._seeded_error)
            self.operation_finished.emit(False, self._seeded_error)
            self.finished.emit()
            return

        # Emit progress at start
        if self._emit_progress:
            self.progress.emit(0, "Starting scan...")
            self.cache_status.emit("Checking cache...")

        # Emit each sprite individually (like real worker)
        total = len(self._seeded_sprites)
        for i, sprite_info in enumerate(self._seeded_sprites):
            if self._is_cancelled:
                self.operation_finished.emit(False, "Cancelled")
                self.finished.emit()
                return

            self.sprite_found.emit(sprite_info)

            if self._emit_progress and total > 0:
                percent = int(((i + 1) / total) * 100)
                self.progress.emit(percent, f"Found {i + 1} sprites...")
                self.progress_detailed.emit(i + 1, total)

        # Emit all at once (like real worker on completion)
        self.sprites_found.emit(self._seeded_sprites)

        # Emit completion signals
        if self._emit_progress:
            self.progress.emit(100, "Scan complete")
            self.cache_status.emit("Saving final results...")
            self.cache_progress.emit(100)

        msg = f"Scan complete. Found {len(self._seeded_sprites)} sprites."
        self.operation_finished.emit(True, msg)
        self.finished.emit()

    def run(self) -> None:
        """Alias for start() to match QThread interface."""
        self.start()

    def cancel(self) -> None:
        """Cancel the scan operation."""
        self._cancel_calls += 1
        self._is_cancelled = True

    def isRunning(self) -> bool:
        """Check if worker is running (always False for fake)."""
        return False

    def isFinished(self) -> bool:
        """Check if worker is finished (always True for fake)."""
        return True

    def quit(self) -> None:
        """Stop the worker (no-op for fake)."""
        pass

    def wait(self, timeout_ms: int = 5000) -> bool:
        """Wait for worker to finish (always immediate for fake)."""
        return True

    def requestInterruption(self) -> None:
        """Request worker interruption (marks as cancelled)."""
        self._is_cancelled = True

    def deleteLater(self) -> None:
        """Schedule deletion (no-op for fake)."""
        pass

    def __hash__(self) -> int:
        """Return hash based on object id for use in sets/dicts."""
        return hash(id(self))

    def __eq__(self, other: object) -> bool:
        """Check equality based on object identity."""
        return self is other

    def get_found_sprites(self) -> list[dict[str, Any]]:
        """Return the seeded sprites (matches real worker interface)."""
        return self._seeded_sprites.copy()

    # ============ Test helper methods ============

    def verify_called(
        self,
        start: int | None = None,
        cancel: int | None = None,
    ) -> None:
        """
        Assert expected call counts.

        Args:
            start: Expected number of start() calls (None to skip check)
            cancel: Expected number of cancel() calls (None to skip)

        Raises:
            AssertionError: If actual calls don't match expected
        """
        if start is not None:
            assert self._start_calls == start, f"Expected {start} start() calls, got {self._start_calls}"
        if cancel is not None:
            assert self._cancel_calls == cancel, f"Expected {cancel} cancel() calls, got {self._cancel_calls}"

    def reset(self) -> None:
        """Reset all state for reuse in multiple tests."""
        self._seeded_sprites.clear()
        self._seeded_error = None
        self._emit_progress = True
        self._start_calls = 0
        self._cancel_calls = 0
        self._is_cancelled = False
