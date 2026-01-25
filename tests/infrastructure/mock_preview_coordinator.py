"""
Mock PreviewCoordinator for testing.

This is a proper signal-enabled test double that mimics the SmartPreviewCoordinator
interface without spawning actual workers or threads.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.services.signal_payloads import PreviewData


class MockPreviewCoordinator(QObject):
    """
    Signal-enabled mock for SmartPreviewCoordinator.

    Exposes the same signals as the real coordinator, allowing tests to:
    1. Trigger preview completion via emit_success()
    2. Trigger preview errors via emit_error()
    3. Verify which offsets were requested
    """

    # Signal signatures match SmartPreviewCoordinator
    preview_ready = Signal(object)  # PreviewData
    preview_cached = Signal(object)  # PreviewData
    preview_error = Signal(str)  # Error message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.request_manual_preview_called = False
        self.request_full_preview_called = False
        self.last_requested_offset = -1
        self._request_history: list[tuple[str, int]] = []

    def set_rom_data_provider(self, provider) -> None:
        """No-op for mock."""
        pass

    def set_force_compression_type(self, compression_type) -> None:
        """No-op for mock."""
        pass

    def get_force_compression_type(self):
        """Return None for mock."""
        pass

    def invalidate_preview_cache(self) -> None:
        """No-op for mock."""
        pass

    def request_manual_preview(self, offset: int) -> None:
        """Record that a manual preview was requested."""
        self.request_manual_preview_called = True
        self.last_requested_offset = offset
        self._request_history.append(("manual", offset))

    def request_full_preview(self, offset: int) -> None:
        """Record that a full preview was requested."""
        self.request_full_preview_called = True
        self.last_requested_offset = offset
        self._request_history.append(("full", offset))

    def cleanup(self) -> None:
        """No-op for mock."""
        pass

    # ============ Test helper methods ============

    def emit_success(
        self,
        offset: int,
        tile_data: bytes | None = None,
        width: int = 8,
        height: int = 8,
        sprite_name: str = "Test Sprite",
        compressed_size: int = 32,
        slack_size: int = 0,
        hal_succeeded: bool = True,
        header_bytes: bytes = b"",
    ) -> None:
        """
        Emit a successful preview_ready signal.

        Args:
            offset: The ROM offset this preview is for
            tile_data: 4bpp tile data (defaults to zeros matching width*height tiles)
            width: Width in tiles
            height: Height in tiles
            sprite_name: Display name for the sprite
            compressed_size: Original compressed size in bytes
            slack_size: Available slack bytes for injection
            hal_succeeded: Whether HAL decompression succeeded
            header_bytes: HAL header bytes for re-injection
        """
        if tile_data is None:
            # Default: 32 bytes per 8x8 tile
            tile_data = b"\x00" * (width * height * 32)

        self.preview_ready.emit(
            PreviewData(
                tile_data=tile_data,
                width=width,
                height=height,
                sprite_name=sprite_name,
                compressed_size=compressed_size,
                slack_size=slack_size,
                actual_offset=offset,
                hal_succeeded=hal_succeeded,
                header_bytes=header_bytes,
            )
        )

    def emit_error(self, message: str) -> None:
        """Emit a preview_error signal."""
        self.preview_error.emit(message)

    def reset(self) -> None:
        """Reset all tracking state for reuse in multiple tests."""
        self.request_manual_preview_called = False
        self.request_full_preview_called = False
        self.last_requested_offset = -1
        self._request_history.clear()

    def get_request_history(self) -> list[tuple[str, int]]:
        """Return list of (request_type, offset) tuples."""
        return self._request_history.copy()
