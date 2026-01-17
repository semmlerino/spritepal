"""
File watcher for Mesen2 sprite_rom_finder.lua log output.

Monitors mesen2_exchange/sprite_rom_finder.log for new ROM offset discoveries
and emits signals when offsets are found.

Output directory resolution order:
1. SPRITEPAL_MESEN_OUTPUT_DIR environment variable (if set and non-empty)
2. Settings value from ApplicationStateManager.get_mesen_output_dir() (if non-empty)
3. Project default: {project_root}/mesen2_exchange/
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

logger = logging.getLogger(__name__)

# Pattern to match "FILE OFFSET: 0xNNNNNN" in log output
OFFSET_PATTERN = re.compile(r"FILE OFFSET:\s*0x([0-9A-Fa-f]{6})")

# Pattern to match frame info for context
FRAME_PATTERN = re.compile(r"frame=(\d+)")

# Pattern to match ROM checksum for identity validation
CHECKSUM_PATTERN = re.compile(r"ROM_CHECKSUM:\s*0x([0-9A-Fa-f]{4})")


@dataclass(frozen=True)
class CapturedOffset:
    """A ROM offset discovered from Mesen2 log."""

    offset: int
    frame: int | None
    timestamp: datetime
    raw_line: str
    rom_checksum: int | None = None  # SNES internal checksum for ROM identity validation

    @property
    def offset_hex(self) -> str:
        """Offset as hex string (e.g., '0x3C6EF1')."""
        return f"0x{self.offset:06X}"

    @property
    def checksum_hex(self) -> str | None:
        """ROM checksum as hex string (e.g., '0xA1B2'), or None if unavailable."""
        if self.rom_checksum is None:
            return None
        return f"0x{self.rom_checksum:04X}"


class LogWatcher(QObject):
    """
    Watches sprite_rom_finder.log for new ROM offset discoveries.

    Emits signals when new offsets are found, allowing the UI to update
    a "Recent Captures" list without manual clipboard operations.

    Signals:
        offset_discovered: Emitted when a new offset is found in the log.
                          Args: (CapturedOffset)
        offset_rediscovered: Emitted when an existing offset is re-captured.
                            Args: (CapturedOffset) - updated with new timestamp/frame
        watch_started: Emitted when file watching begins.
        watch_stopped: Emitted when file watching stops.
        error_occurred: Emitted on errors. Args: (error_message: str)
    """

    offset_discovered = Signal(object)  # CapturedOffset (new offset)
    offset_rediscovered = Signal(object)  # CapturedOffset (re-capture of existing)
    watch_started = Signal()
    watch_stopped = Signal()
    error_occurred = Signal(str)

    # Polling interval in milliseconds (for WSL/Windows cross-filesystem compatibility)
    POLL_INTERVAL_MS = 500

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._watcher.directoryChanged.connect(self._on_directory_changed)

        # Polling timer as fallback (inotify doesn't work across WSL/Windows)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_file)
        self._last_mtime: float = 0.0

        self._log_path: Path | None = None
        self._offset_file: Path | None = None  # Simple last_offset.txt file
        self._clicks_file: Path | None = None  # Persistent recent_clicks.json
        self._watching_dir: Path | None = None
        self._last_position: int = 0
        self._last_offset_mtime: float = 0.0  # For polling last_offset.txt
        self._seen_offsets: set[int] = set()
        self._recent_captures: list[CapturedOffset] = []
        self._max_recent: int = 50

    @property
    def log_path(self) -> Path | None:
        """Current log file path being watched."""
        return self._log_path

    @property
    def is_watching(self) -> bool:
        """True if currently watching a log file."""
        return self._log_path is not None and len(self._watcher.files()) > 0

    @property
    def recent_captures(self) -> list[CapturedOffset]:
        """List of recently captured offsets (most recent first)."""
        return list(self._recent_captures)

    def get_capture_by_offset(self, offset: int) -> CapturedOffset | None:
        """Get a capture by offset from recent captures.

        Args:
            offset: ROM offset to look up

        Returns:
            The CapturedOffset if found, None otherwise
        """
        for capture in self._recent_captures:
            if capture.offset == offset:
                return capture
        return None

    def get_capture_by_file_offset(self, file_offset: int) -> CapturedOffset | None:
        """Get a capture by FILE offset (raw Mesen output).

        The FILE offset is the original offset reported by Mesen, which includes
        any SMC header. This is the immutable identity of the capture.

        Args:
            file_offset: FILE offset to look up (raw Mesen offset)

        Returns:
            The CapturedOffset if found, None otherwise
        """
        for capture in self._recent_captures:
            if capture.offset == file_offset:
                return capture
        return None

    def get_capture_by_rom_offset(self, rom_offset: int, smc_header_offset: int = 0) -> CapturedOffset | None:
        """Get a capture by ROM offset (converts to FILE offset internally).

        Use this method when you have a ROM offset (headerless) and need to
        find the corresponding capture, which stores FILE offsets.

        Args:
            rom_offset: ROM offset to look up (headerless)
            smc_header_offset: SMC header size (typically 0x200 or 0)

        Returns:
            The CapturedOffset if found, None otherwise
        """
        # Convert ROM offset to FILE offset
        file_offset = rom_offset + smc_header_offset
        return self.get_capture_by_file_offset(file_offset)

    def _resolve_output_directory(self, output_dir: Path | str | None = None) -> Path:
        """Resolve the Mesen2 output directory.

        Resolution order:
        1. SPRITEPAL_MESEN_OUTPUT_DIR environment variable (if set and non-empty)
        2. output_dir parameter (if provided and non-empty)
        3. Project default: {project_root}/mesen2_exchange/

        Args:
            output_dir: Optional directory passed by caller (e.g., from settings)

        Returns:
            Resolved Path to the output directory
        """
        # 1. Check environment variable first
        env_dir = os.environ.get("SPRITEPAL_MESEN_OUTPUT_DIR", "").strip()
        if env_dir:
            resolved = Path(env_dir)
            logger.debug("Using output directory from SPRITEPAL_MESEN_OUTPUT_DIR: %s", resolved)
            return resolved

        # 2. Use provided output_dir if non-empty
        if output_dir:
            dir_str = str(output_dir).strip()
            if dir_str:
                resolved = Path(dir_str)
                logger.debug("Using output directory from parameter: %s", resolved)
                return resolved

        # 3. Fall back to project default
        project_root = Path(__file__).parent.parent.parent
        resolved = project_root / "mesen2_exchange"
        logger.debug("Using default output directory: %s", resolved)
        return resolved

    def start_watching(self, log_path: Path | str | None = None, *, output_dir: Path | str | None = None) -> bool:
        """
        Start watching the Mesen2 log file.

        Args:
            log_path: Full path to sprite_rom_finder.log. If None, resolves using
                     output_dir or environment variable.
            output_dir: Base directory containing log files. If None and log_path
                       is None, checks SPRITEPAL_MESEN_OUTPUT_DIR env var first,
                       then falls back to project's mesen2_exchange/ directory.

        Returns:
            True if watching started successfully, False otherwise.
        """
        if log_path is None:
            # Resolution order: env var > output_dir param > project default
            resolved_dir = self._resolve_output_directory(output_dir)
            log_path = resolved_dir / "sprite_rom_finder.log"

        log_path = Path(log_path)

        # Stop watching previous file if any
        self.stop_watching()

        self._log_path = log_path
        self._offset_file = log_path.parent / "last_offset.txt"
        self._clicks_file = log_path.parent / "recent_clicks.json"
        self._watching_dir = log_path.parent
        self._seen_offsets.clear()
        self._last_offset_mtime = 0.0

        # Watch the directory so we detect file creation
        if self._watching_dir.exists():
            self._watcher.addPath(str(self._watching_dir))
            logger.debug("Watching directory: %s", self._watching_dir)
        else:
            # Log warning - directory doesn't exist
            logger.warning(
                "Mesen2 output directory does not exist: %s\n"
                "Captures from Mesen2 will not be detected until this directory is created.",
                self._watching_dir,
            )

        if log_path.exists():
            stat = log_path.stat()
            self._last_position = stat.st_size  # Start from end
            self._last_mtime = stat.st_mtime
            if not self._watcher.addPath(str(log_path)):
                logger.warning("QFileSystemWatcher failed, using polling only: %s", log_path)
            else:
                logger.info("Started watching: %s", log_path)
        else:
            self._last_position = 0
            self._last_mtime = 0.0
            logger.info("Waiting for log file to be created: %s", log_path)

        # Always start polling as fallback (inotify doesn't work across WSL/Windows)
        self._poll_timer.start(self.POLL_INTERVAL_MS)
        logger.debug("Started polling every %d ms", self.POLL_INTERVAL_MS)

        self.watch_started.emit()
        return True

    def stop_watching(self) -> None:
        """Stop watching the current log file."""
        self._poll_timer.stop()
        if self._watching_dir is not None:
            self._watcher.removePath(str(self._watching_dir))
            self._watching_dir = None
        if self._log_path is not None:
            self._watcher.removePath(str(self._log_path))
            logger.info("Stopped watching: %s", self._log_path)
            self._log_path = None
            self.watch_stopped.emit()

    def _on_directory_changed(self, path: str) -> None:
        """Handle directory change - check if log file was created."""
        if self._log_path is None:
            return

        # If log file now exists and we weren't watching it, start watching
        if self._log_path.exists() and str(self._log_path) not in self._watcher.files():
            self._last_position = 0  # Read from start for new file
            self._watcher.addPath(str(self._log_path))
            logger.info("Log file appeared, now watching: %s", self._log_path)
            # Read any existing content
            self._on_file_changed(str(self._log_path))

    def scan_existing(self) -> list[CapturedOffset]:
        """
        Scan the existing log file for all offsets (not just new ones).

        Returns:
            List of all offsets found in the log file.
        """
        if self._log_path is None or not self._log_path.exists():
            return []

        captures: list[CapturedOffset] = []
        try:
            with self._log_path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    capture = self._parse_line(line)
                    if capture is not None:
                        captures.append(capture)
        except OSError as e:
            logger.error("Error scanning log file: %s", e)
            self.error_occurred.emit(f"Read error: {e}")

        return captures

    def load_persistent_clicks(self) -> list[CapturedOffset]:
        """
        Load persistent recent clicks from recent_clicks.json.

        This file is written by sprite_rom_finder.lua and contains
        the last 5 clicked sprites across Mesen2 sessions.

        Returns:
            List of captured offsets from the persistent file.
        """
        if self._clicks_file is None or not self._clicks_file.exists():
            return []

        captures: list[CapturedOffset] = []
        try:
            content = self._clicks_file.read_text(encoding="utf-8")
            data = json.loads(content)

            for item in data:
                if not isinstance(item, dict):
                    continue
                offset = item.get("offset")
                if offset is None:
                    continue

                frame = item.get("frame")
                timestamp_unix = item.get("timestamp")
                rom_checksum = item.get("rom_checksum")  # Optional for backward compat

                # Convert Unix timestamp to datetime
                if timestamp_unix:
                    timestamp = datetime.fromtimestamp(timestamp_unix, tz=UTC)
                else:
                    timestamp = datetime.now(tz=UTC)

                captures.append(
                    CapturedOffset(
                        offset=offset,
                        frame=frame,
                        timestamp=timestamp,
                        raw_line=f"persistent: 0x{offset:06X}",
                        rom_checksum=rom_checksum,
                    )
                )

        except (OSError, json.JSONDecodeError) as e:
            logger.debug("Error loading persistent clicks: %s", e)

        return captures

    def clear_history(self) -> None:
        """Clear the list of seen offsets and recent captures."""
        self._seen_offsets.clear()
        self._recent_captures.clear()
        logger.debug("Cleared offset history")

    def _update_recent_capture(self, new_capture: CapturedOffset) -> None:
        """Update an existing capture with new timestamp/frame and move it to the top.

        This is called when a previously-seen offset is re-captured. The old capture
        is removed and the new capture (with updated frame info) is inserted at the top.
        """
        # Find and remove the existing capture with the same offset
        self._recent_captures = [c for c in self._recent_captures if c.offset != new_capture.offset]
        # Insert the new capture at the top
        self._recent_captures.insert(0, new_capture)

        # Trim to max size
        if len(self._recent_captures) > self._max_recent:
            self._recent_captures = self._recent_captures[: self._max_recent]

    def cleanup(self) -> None:
        """Cleanup resources."""
        self.stop_watching()

    def _poll_file(self) -> None:
        """Poll both the log file and last_offset.txt for changes."""
        # Check the simple offset file first (more reliable)
        self._check_offset_file()

        # Also check the main log file
        if self._log_path is None:
            return

        if not self._log_path.exists():
            return

        try:
            stat = self._log_path.stat()
            current_mtime = stat.st_mtime
            current_size = stat.st_size

            # Check if file was modified
            if current_mtime > self._last_mtime or current_size != self._last_position:
                self._last_mtime = current_mtime

                # Handle log rotation (file got smaller)
                if current_size < self._last_position:
                    logger.info("Log file appears rotated, reading from start")
                    self._last_position = 0

                if current_size > self._last_position:
                    self._read_new_content(self._log_path, current_size)

        except OSError as e:
            logger.debug("Poll error (may be transient): %s", e)

    def _check_offset_file(self) -> None:
        """Check last_offset.txt for new offsets (simpler, more reliable)."""
        if self._offset_file is None or not self._offset_file.exists():
            return

        try:
            stat = self._offset_file.stat()
            if stat.st_mtime <= self._last_offset_mtime:
                return  # No change

            self._last_offset_mtime = stat.st_mtime

            # Read the simple file
            content = self._offset_file.read_text(encoding="utf-8", errors="replace")
            capture = self._parse_line(content)

            if capture is None:
                return

            if capture.offset not in self._seen_offsets:
                # New offset - add to seen set and emit offset_discovered
                self._seen_offsets.add(capture.offset)
                self._recent_captures.insert(0, capture)

                if len(self._recent_captures) > self._max_recent:
                    self._recent_captures = self._recent_captures[: self._max_recent]

                logger.info("Discovered offset from last_offset.txt: %s", capture.offset_hex)
                self.offset_discovered.emit(capture)
            else:
                # Re-capture of existing offset - update and emit offset_rediscovered
                self._update_recent_capture(capture)
                logger.info("Rediscovered offset from last_offset.txt: %s", capture.offset_hex)
                self.offset_rediscovered.emit(capture)

        except OSError as e:
            logger.debug("Offset file poll error: %s", e)

    def _on_file_changed(self, path: str) -> None:
        """Handle file change notification from QFileSystemWatcher."""
        if self._log_path is None:
            return

        log_path = Path(path)
        if not log_path.exists():
            # File was deleted - try to re-add when it reappears
            logger.warning("Log file was deleted: %s", path)
            return

        try:
            current_size = log_path.stat().st_size

            # Handle log rotation (file got smaller)
            if current_size < self._last_position:
                logger.info("Log file appears rotated, reading from start")
                self._last_position = 0

            if current_size > self._last_position:
                self._read_new_content(log_path, current_size)

            # Re-add file to watcher (some platforms remove it after change)
            if str(log_path) not in self._watcher.files():
                self._watcher.addPath(str(log_path))

        except OSError as e:
            logger.error("Error reading log file: %s", e)
            self.error_occurred.emit(f"Read error: {e}")

    def _read_new_content(self, log_path: Path, current_size: int) -> None:
        """Read new content from log file and parse for offsets."""
        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(self._last_position)
            new_content = f.read()

        self._last_position = current_size

        for line in new_content.splitlines():
            capture = self._parse_line(line)
            if capture is None:
                continue

            if capture.offset not in self._seen_offsets:
                # New offset - add to seen set and emit offset_discovered
                self._seen_offsets.add(capture.offset)
                self._recent_captures.insert(0, capture)

                # Trim to max size
                if len(self._recent_captures) > self._max_recent:
                    self._recent_captures = self._recent_captures[: self._max_recent]

                logger.info("Discovered offset: %s", capture.offset_hex)
                self.offset_discovered.emit(capture)
            else:
                # Re-capture of existing offset - update and emit offset_rediscovered
                self._update_recent_capture(capture)
                logger.info("Rediscovered offset: %s", capture.offset_hex)
                self.offset_rediscovered.emit(capture)

    def _parse_line(self, line: str) -> CapturedOffset | None:
        """Parse a log line for ROM offset."""
        match = OFFSET_PATTERN.search(line)
        if match is None:
            return None

        offset = int(match.group(1), 16)

        # Try to extract frame number for context
        frame_match = FRAME_PATTERN.search(line)
        frame = int(frame_match.group(1)) if frame_match else None

        # Try to extract ROM checksum for identity validation
        checksum_match = CHECKSUM_PATTERN.search(line)
        rom_checksum = int(checksum_match.group(1), 16) if checksum_match else None

        return CapturedOffset(
            offset=offset,
            frame=frame,
            timestamp=datetime.now(tz=UTC),
            raw_line=line.strip(),
            rom_checksum=rom_checksum,
        )
