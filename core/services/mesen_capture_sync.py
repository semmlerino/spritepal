"""
Mesen capture synchronization service.

Coordinates Mesen2 capture discovery and browser synchronization.
Extracted from ROMWorkflowController to reduce complexity.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from core.mesen_integration.log_watcher import CapturedOffset
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.mesen_integration.log_watcher import LogWatcher

logger = get_logger(__name__)


class AssetBrowserProtocol(Protocol):
    """Protocol for asset browser interactions."""

    def has_mesen_capture(self, offset: int, *, frame: int | None = None) -> bool:
        """Check if a capture exists at the given offset."""
        ...

    def add_mesen_capture(
        self,
        name: str,
        offset: int,
        *,
        frame: int | None = None,
        update_if_exists: bool = False,
    ) -> None:
        """Add a Mesen capture to the browser."""
        ...


class MessageServiceProtocol(Protocol):
    """Protocol for message display."""

    def show_message(self, message: str) -> None:
        """Display a message to the user."""
        ...


# Callback type for thumbnail requests
ThumbnailRequestCallback = Callable[[int], None]


class ViewAssetBrowserAdapter:
    """Adapter to wrap a ROMWorkflowPage view as an AssetBrowserProtocol."""

    def __init__(self, view: object) -> None:
        """Initialize adapter with a ROMWorkflowPage view."""
        # Type is 'object' to avoid circular imports; we access attributes dynamically
        self._view: object = view

    def has_mesen_capture(self, offset: int, *, frame: int | None = None) -> bool:
        """Check if a capture exists at the given offset."""
        if self._view is None:
            return False
        # Access view.asset_browser.has_mesen_capture dynamically
        asset_browser = getattr(self._view, "asset_browser", None)
        if asset_browser is None:
            return False
        has_capture_fn = getattr(asset_browser, "has_mesen_capture", None)
        if has_capture_fn is None:
            return False
        return bool(has_capture_fn(offset, frame=frame))

    def add_mesen_capture(
        self,
        name: str,
        offset: int,
        *,
        frame: int | None = None,
        update_if_exists: bool = False,
    ) -> None:
        """Add a Mesen capture to the browser."""
        if self._view is None:
            return
        # Access view.add_mesen_capture dynamically
        add_capture_fn = getattr(self._view, "add_mesen_capture", None)
        if add_capture_fn is not None:
            add_capture_fn(name, offset, frame=frame, update_if_exists=update_if_exists)


class MesenCaptureSync:
    """
    Manages Mesen capture discovery and browser synchronization.

    Responsibilities:
    - Connects to LogWatcher signals for capture discovery
    - Validates capture ROM checksums
    - Normalizes Mesen offsets (SMC header handling)
    - Deduplicates captures
    - Syncs captures to the asset browser

    This service is stateless regarding the browser - it uses callbacks
    to interact with the browser and thumbnail system.
    """

    def __init__(
        self,
        *,
        on_thumbnail_request: ThumbnailRequestCallback | None = None,
        message_service: MessageServiceProtocol | None = None,
    ) -> None:
        """Initialize the capture sync service.

        Args:
            on_thumbnail_request: Callback to request thumbnail generation for an offset.
            message_service: Optional service for displaying messages to the user.
        """
        self._log_watcher: LogWatcher | None = None
        self._asset_browser: AssetBrowserProtocol | None = None
        self._on_thumbnail_request = on_thumbnail_request
        self._message_service = message_service

        # ROM state (set by controller)
        self._smc_header_offset: int = 0
        self._loaded_rom_checksum: int | None = None

        # Track offset adjustments to prevent duplicate captures after resync
        # Maps original ROM offset -> adjusted ROM offset
        self._adjusted_offsets: dict[int, int] = {}

        # Queue for captures discovered before browser is ready
        self._pending_captures: list[CapturedOffset] = []

    def set_asset_browser(self, browser: AssetBrowserProtocol | None) -> None:
        """Set the asset browser for capture display.

        When a browser is set, any pending captures are processed.
        """
        self._asset_browser = browser
        if browser is not None:
            self._process_pending_captures()

    def set_rom_state(
        self,
        *,
        smc_header_offset: int = 0,
        rom_checksum: int | None = None,
    ) -> None:
        """Update ROM-related state.

        Args:
            smc_header_offset: SMC header size (512 or 0).
            rom_checksum: SNES internal checksum for capture validation.
        """
        self._smc_header_offset = smc_header_offset
        self._loaded_rom_checksum = rom_checksum

    def set_message_service(self, service: MessageServiceProtocol | None) -> None:
        """Set the message service for user notifications."""
        self._message_service = service

    def connect(self, log_watcher: LogWatcher | None) -> None:
        """Connect to LogWatcher signals for capture discovery.

        Args:
            log_watcher: The LogWatcher to connect to, or None to disconnect.
        """
        if self._log_watcher is not None:
            # Disconnect from old watcher
            try:
                self._log_watcher.offset_discovered.disconnect(self._on_offset_discovered)
                self._log_watcher.offset_rediscovered.disconnect(self._on_offset_rediscovered)
            except RuntimeError:
                pass  # Already disconnected

        self._log_watcher = log_watcher

        if log_watcher is not None:
            log_watcher.offset_discovered.connect(self._on_offset_discovered)
            log_watcher.offset_rediscovered.connect(self._on_offset_rediscovered)
            # Start watching if not already
            log_watcher.start_watching()

    def sync_from_log_watcher(self) -> None:
        """Sync all captures from log watcher to the asset browser.

        Called when entering the sprite editor workspace to ensure all
        discovered captures are visible in the asset browser.
        """
        if self._asset_browser is None:
            logger.warning("sync_from_log_watcher: no asset browser set")
            return
        if self._log_watcher is None:
            logger.warning("sync_from_log_watcher: no log_watcher")
            return

        captures = self._log_watcher.recent_captures
        logger.info(
            "sync_from_log_watcher: found %d captures in log_watcher",
            len(captures),
        )

        # Sync all current session captures
        for capture in captures:
            logger.debug("  syncing capture: 0x%06X", capture.offset)
            self._add_capture_to_browser(capture)

        # Also sync persistent clicks
        persistent = self._log_watcher.load_persistent_clicks()
        logger.info(
            "sync_from_log_watcher: found %d persistent clicks",
            len(persistent),
        )
        for capture in persistent:
            logger.debug("  syncing persistent: 0x%06X", capture.offset)
            self._add_capture_to_browser(capture)

    def normalize_offset(self, offset: int) -> int:
        """Convert Mesen FILE OFFSET (file-based) to ROM offset (headerless).

        Args:
            offset: The file offset from Mesen.

        Returns:
            The normalized ROM offset with SMC header subtracted.
        """
        if self._smc_header_offset <= 0:
            return offset
        if offset < self._smc_header_offset:
            return offset
        normalized = offset - self._smc_header_offset
        logger.debug(
            "[CAPTURE] Normalized Mesen FILE OFFSET 0x%06X -> 0x%06X (SMC header %d bytes)",
            offset,
            normalized,
            self._smc_header_offset,
        )
        return normalized

    def get_capture_name(self, capture: CapturedOffset) -> str:
        """Generate display name for captured sprite.

        Args:
            capture: The captured offset data.

        Returns:
            A formatted display name for the capture.
        """
        rom_offset = self.normalize_offset(capture.offset)
        if capture.frame is not None:
            return f"0x{rom_offset:06X} (F{capture.frame})"
        else:
            # Fallback to timestamp if no frame
            timestamp_str = capture.timestamp.strftime("%H:%M:%S")
            return f"0x{rom_offset:06X} ({timestamp_str})"

    def record_offset_adjustment(self, original_offset: int, adjusted_offset: int) -> None:
        """Record an offset adjustment to prevent duplicate captures.

        When an offset is adjusted (e.g., HAL alignment), record the mapping
        so that resyncs don't create duplicate entries.

        Args:
            original_offset: The original ROM offset.
            adjusted_offset: The adjusted ROM offset.
        """
        self._adjusted_offsets[original_offset] = adjusted_offset

    def clear_pending_captures(self) -> None:
        """Clear the pending captures queue."""
        self._pending_captures.clear()

    # === Internal Methods ===

    def _on_offset_discovered(self, capture: object) -> None:
        """Handle new offset discovered from Mesen2 log."""
        if not isinstance(capture, CapturedOffset):
            return

        # Queue if browser not ready yet
        if self._asset_browser is None:
            self._pending_captures.append(capture)
            logger.debug("Queued capture 0x%06X (browser not ready)", capture.offset)
            return

        # Process immediately
        self._add_capture_to_browser(capture)

    def _on_offset_rediscovered(self, capture: object) -> None:
        """Handle re-capture of existing offset from Mesen2 log.

        This is called when the user clicks on the same sprite again.
        The existing entry is updated (moved to top with new timestamp/frame).
        """
        if not isinstance(capture, CapturedOffset):
            return

        # Queue if browser not ready yet
        if self._asset_browser is None:
            # For rediscoveries, we still queue them - they'll be processed in order
            self._pending_captures.append(capture)
            logger.debug("Queued rediscovered capture 0x%06X (browser not ready)", capture.offset)
            return

        # Process immediately with update flag
        self._update_capture_in_browser(capture)

    def _validate_capture_rom_match(self, capture: CapturedOffset) -> bool:
        """Check if capture's ROM checksum matches the currently loaded ROM.

        Returns True if:
        - Checksums match
        - Capture has no checksum (legacy capture, backward compatible)
        - No ROM is loaded yet

        Returns False (with warning) if checksums differ, indicating the capture
        may be from a different ROM than the one currently loaded.
        """
        if capture.rom_checksum is None:
            # Legacy capture without checksum - allow silently
            return True
        if self._loaded_rom_checksum is None:
            # No ROM loaded yet - can't validate
            return True
        if capture.rom_checksum == self._loaded_rom_checksum:
            return True

        # Checksum mismatch - show warning
        if self._message_service:
            self._message_service.show_message(
                f"Warning: Capture 0x{capture.offset:06X} may be from a different ROM "
                f"(capture: 0x{capture.rom_checksum:04X}, loaded: 0x{self._loaded_rom_checksum:04X})"
            )
        logger.warning(
            "ROM checksum mismatch for capture 0x%06X: capture=0x%04X, loaded=0x%04X",
            capture.offset,
            capture.rom_checksum,
            self._loaded_rom_checksum,
        )
        return False

    def _add_capture_to_browser(self, capture: CapturedOffset) -> None:
        """Add a capture to the browser with thumbnail."""
        if self._asset_browser is None:
            return

        # Validate ROM identity
        if not self._validate_capture_rom_match(capture):
            # Mismatched ROM - don't add to browser to avoid confusion/corruption
            return

        rom_offset = self.normalize_offset(capture.offset)

        # Check if this offset was already adjusted - skip if the adjusted version exists
        # This prevents duplicates when resync re-normalizes the original offset
        if rom_offset in self._adjusted_offsets:
            adjusted = self._adjusted_offsets[rom_offset]
            if self._asset_browser.has_mesen_capture(adjusted, frame=capture.frame):
                logger.debug(
                    "Skipping already-adjusted capture 0x%06X -> 0x%06X (frame=%s)",
                    rom_offset,
                    adjusted,
                    capture.frame,
                )
                return

        name = self.get_capture_name(capture)
        # Pass frame for proper deduplication (same offset, different frames should both appear)
        self._asset_browser.add_mesen_capture(name, rom_offset, frame=capture.frame)

        # Request thumbnail if callback is set
        if self._on_thumbnail_request is not None:
            self._on_thumbnail_request(rom_offset)

    def _update_capture_in_browser(self, capture: CapturedOffset) -> None:
        """Update an existing capture in the browser (move to top with new data).

        This handles re-clicking the same sprite - the old entry is removed
        and a new one is added at the top with updated timestamp/frame.
        """
        if self._asset_browser is None:
            return

        # Validate ROM identity
        if not self._validate_capture_rom_match(capture):
            # Mismatched ROM - don't update browser
            return

        rom_offset = self.normalize_offset(capture.offset)
        name = self.get_capture_name(capture)

        # Update existing (remove and re-add at top)
        self._asset_browser.add_mesen_capture(name, rom_offset, frame=capture.frame, update_if_exists=True)

        # Re-request thumbnail (user may want fresh thumbnail)
        if self._on_thumbnail_request is not None:
            self._on_thumbnail_request(rom_offset)

        logger.debug("Updated capture in browser: 0x%06X", rom_offset)

    def _process_pending_captures(self) -> None:
        """Process any captures that were queued before browser was ready."""
        if not self._pending_captures:
            return

        logger.info("Processing %d pending captures", len(self._pending_captures))
        pending = self._pending_captures.copy()
        self._pending_captures.clear()

        for capture in pending:
            self._add_capture_to_browser(capture)
