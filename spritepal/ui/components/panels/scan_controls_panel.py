"""
Scan Controls Panel for Manual Offset Dialog

Handles all scanning functionality including range scanning, full ROM scanning,
pause/stop controls, and worker management.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from core.managers.extraction_manager import ExtractionManager
    from core.protocols.manager_protocols import ROMCacheProtocol, ROMExtractorProtocol

from PySide6.QtCore import QMutex, QMutexLocker, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.common import WorkerManager
from ui.components.dialogs import RangeScanDialog
from ui.components.visualization import ROMMapWidget
from ui.rom_extraction.workers import RangeScanWorker
from ui.styles import get_panel_style
from ui.styles.theme import COLORS
from utils.logging_config import get_logger

# from utils.rom_cache import get_rom_cache # Removed due to DI

logger = get_logger(__name__)

class ScanControlsPanel(QWidget):
    """Panel for controlling ROM scanning operations"""

    # Signals
    sprite_found = Signal(int, float)  # offset, quality
    scan_status_changed = Signal(str)  # status message
    progress_update = Signal(int, int)  # current_offset, progress_percentage
    scan_started = Signal()
    scan_finished = Signal()
    partial_scan_detected = Signal(dict)  # cache info for resume dialog
    sprites_detected = Signal(list)  # List of (offset, quality) tuples for region detection

    def __init__(self, parent: QWidget | None = None, rom_cache: ROMCacheProtocol | None = None):
        # Step 1: Declare all instance variables with type hints
        # State
        self.rom_path: str = ""
        self.rom_size: int = 0x400000
        self.current_offset: int = 0x200000
        self.is_scanning: bool = False
        self.found_sprites: list[tuple[int, float]] = []

        # Manager references (set by parent)
        self.extraction_manager: ExtractionManager | None = None
        self.rom_extractor: ROMExtractorProtocol | None = None
        self._manager_mutex = QMutex()  # Thread safety for manager access

        # Worker reference
        self.range_scan_worker: RangeScanWorker | None = None

        # ROM map reference (set by parent)
        self.rom_map: ROMMapWidget | None = None

        # Cache status UI
        self.cache_status_label: QLabel | None = None

        # Inject rom_cache or use fallback
        if rom_cache is None:
            from core.di_container import inject
            from core.protocols.manager_protocols import ROMCacheProtocol
            self.rom_cache = inject(ROMCacheProtocol)
        else:
            self.rom_cache = rom_cache

        # Step 2: Initialize parent
        super().__init__(parent)
        self.setStyleSheet(get_panel_style())

        # Step 3: Setup UI and connections
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Initialize the scan controls UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 6, 8, 6)  # Reduced padding
        layout.setSpacing(4)  # Tighter spacing

        label = QLabel("Enhanced Controls")
        label.setStyleSheet("font-weight: bold; font-size: 12px; margin-bottom: 4px;")  # Smaller and tighter
        layout.addWidget(label)

        # Scan controls
        scan_row = QHBoxLayout()
        self.scan_range_btn = QPushButton("Scan Range")
        self.scan_range_btn.setToolTip("Scan a range around current offset for sprites")
        scan_row.addWidget(self.scan_range_btn)

        self.scan_all_btn = QPushButton("Scan Entire ROM")
        self.scan_all_btn.setToolTip("Scan the entire ROM for sprite locations (slow)")
        scan_row.addWidget(self.scan_all_btn)
        layout.addLayout(scan_row)

        # Scan control buttons (pause/stop)
        control_row = QHBoxLayout()
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setToolTip("Pause or resume the current scan")
        self.pause_btn.setVisible(False)  # Hidden by default
        control_row.addWidget(self.pause_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setToolTip("Stop the current scan")
        self.stop_btn.setVisible(False)  # Hidden by default
        control_row.addWidget(self.stop_btn)

        control_row.addStretch()  # Push buttons to left
        layout.addLayout(control_row)

        # Cache status label
        self.cache_status_label = QLabel("")
        if self.cache_status_label:
            self.cache_status_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS["text_muted"]};
                font-size: 11px;
                padding: 4px;
                border-radius: 3px;
            }}
        """)
        self.cache_status_label.setVisible(False)  # Hidden by default
        layout.addWidget(self.cache_status_label)

        self.setLayout(layout)

    def _connect_signals(self):
        """Connect internal signals"""
        _ = self.scan_range_btn.clicked.connect(self._scan_range)
        _ = self.scan_all_btn.clicked.connect(self._scan_all)
        _ = self.pause_btn.clicked.connect(self._toggle_pause)
        _ = self.stop_btn.clicked.connect(self._stop_scan)

    def set_rom_data(self, rom_path: str, rom_size: int, extraction_manager: ExtractionManager):
        """Set ROM data for scanning operations"""
        with QMutexLocker(self._manager_mutex):
            self.rom_path = rom_path
            self.rom_size = rom_size
            self.extraction_manager = extraction_manager
            self.rom_extractor = extraction_manager.get_rom_extractor()

        # Check for cached partial scan results
        self._check_for_cached_scans()

    def _get_managers_safely(self) -> tuple[ExtractionManager | None, ROMExtractorProtocol | None]:
        """Get manager references safely with thread protection.

        WARNING: The returned references are only safe to use within the calling
        context if that context also holds the mutex. For operations that need
        managers, prefer using _with_managers_safely() instead.
        """
        with QMutexLocker(self._manager_mutex):
            return self.extraction_manager, self.rom_extractor

    def _with_managers_safely(self, operation: Callable[[ExtractionManager | None, ROMExtractorProtocol | None], Any]) -> Any:
        """Execute an operation with manager references under mutex protection.

        This prevents TOCTOU race conditions by holding the lock during the entire
        operation. For long operations, extract only necessary data under lock.

        Args:
            operation: Callable that takes (extraction_manager, rom_extractor) and returns a result

        Returns:
            The result of the operation, or None if managers are not available
        """
        with QMutexLocker(self._manager_mutex):
            if self.extraction_manager is None or self.rom_extractor is None:
                return None
            return operation(self.extraction_manager, self.rom_extractor)

    def set_rom_map(self, rom_map: ROMMapWidget):
        """Set the ROM map reference for visualization updates"""
        self.rom_map = rom_map

    def set_current_offset(self, offset: int):
        """Update the current offset for range scanning"""
        self.current_offset = offset

    def _scan_range(self):
        """Scan a range around current offset"""
        # Quick check if managers exist (safe under short lock)
        has_managers = self._with_managers_safely(lambda em, re: True)
        if not self.rom_path or not has_managers:
            self.scan_status_changed.emit("No ROM loaded")
            return

        if self.is_scanning:
            self.scan_status_changed.emit("Scan already in progress")
            return

        # Show range selection dialog
        dialog = RangeScanDialog(self.current_offset, self.rom_size, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        start_offset, end_offset = dialog.get_range()

        # Additional validation in case dialog validation was bypassed
        if not self._validate_scan_parameters(start_offset, end_offset):
            return

        # Check for cached partial scan for this range
        use_cache = self._check_scan_cache_before_start(start_offset, end_offset)
        if use_cache is None:
            # User cancelled via ResumeScanDialog
            return

        # Confirm the scan
        range_kb = (end_offset - start_offset) // 1024
        result = _ = QMessageBox.question(
            self,
            "Confirm Range Scan",
            f"Scan range 0x{start_offset:06X} - 0x{end_offset:06X} ({range_kb} KB)?\n\n"
            f"This may take a few moments depending on the range size.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        self._start_range_scan(start_offset, end_offset)

    def _scan_all(self):
        """Scan entire ROM"""
        # Quick check if managers exist (safe under short lock)
        has_managers = self._with_managers_safely(lambda em, re: True)
        if not self.rom_path or not has_managers:
            self.scan_status_changed.emit("No ROM loaded")
            return

        if self.is_scanning:
            self.scan_status_changed.emit("Scan already in progress")
            return

        # Warn about performance impact
        rom_mb = self.rom_size // (1024 * 1024)
        result = _ = QMessageBox.question(
            self,
            "Confirm Full ROM Scan",
            f"Scan entire ROM ({rom_mb} MB)?\n\n"
            f"This will scan the full ROM for sprite data and may take several minutes.\n"
            f"The UI will remain responsive during scanning.\n\n"
            f"Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No  # Default to No for safety
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        # Validate full ROM scan parameters
        start_offset, end_offset = 0, self.rom_size - 1
        if not self._validate_scan_parameters(start_offset, end_offset):
            return

        # Check for cached partial scan for full ROM
        use_cache = self._check_scan_cache_before_start(start_offset, end_offset)
        if use_cache is None:
            # User cancelled via ResumeScanDialog
            return

        # Start full ROM scan
        self._start_range_scan(start_offset, end_offset)

    def _start_range_scan(self, start_offset: int, end_offset: int):
        """Start scanning a specific range"""
        self.is_scanning = True
        if self.found_sprites:
            self.found_sprites.clear()

        # Clear existing sprites from ROM map
        if self.rom_map is not None:
            self.rom_map.clear_sprites()

        # Update status
        range_kb = (end_offset - start_offset) // 1024
        self.scan_status_changed.emit(f"Scanning {range_kb} KB range...")

        # Disable scan buttons during operation and show control buttons
        if self.scan_range_btn:
            self.scan_range_btn.setEnabled(False)
        if self.scan_all_btn:
            self.scan_all_btn.setEnabled(False)
        self.pause_btn.setVisible(True)
        self.stop_btn.setVisible(True)
        if self.pause_btn:
            self.pause_btn.setText("Pause")  # Reset pause button text

        # Emit scan started signal
        self.scan_started.emit()

        # Create range scanning worker
        self._start_range_scan_worker(start_offset, end_offset)

    def _start_range_scan_worker(self, start_offset: int, end_offset: int):
        """Start the worker thread for range scanning with enhanced error recovery"""
        # Extract necessary data under mutex protection
        rom_extractor = self._with_managers_safely(lambda em, re: re)
        if not rom_extractor:
            self.scan_status_changed.emit("ROM extractor not available")
            self._finish_scan()  # Reset UI state
            return

        # Validate ROM file accessibility
        try:
            if not self.rom_path or not Path(self.rom_path).exists():
                self.scan_status_changed.emit("ROM file not found or inaccessible")
                self._finish_scan()
                return

            # Check file permissions
            if not os.access(self.rom_path, os.R_OK):
                self.scan_status_changed.emit("Cannot read ROM file - check permissions")
                self._finish_scan()
                return
        except OSError as e:
            self.scan_status_changed.emit(f"ROM file error: {e}")
            self._finish_scan()
            return

        # Clean up existing range scan worker with enhanced error handling
        if self.range_scan_worker is not None:
            try:
                WorkerManager.cleanup_worker(self.range_scan_worker, timeout=3000)
            except RuntimeError as e:
                logger.warning(f"Error during worker cleanup: {e}")
                # Continue anyway, worker may already be cleaned up

        # Create range scan worker with proper bounds and error handling
        try:
            step_size = 0x100  # 256 byte steps for comprehensive scanning
            self.range_scan_worker = RangeScanWorker(
                self.rom_path, start_offset, end_offset, step_size, rom_extractor
            )
        except Exception as e:
            logger.exception("Failed to create range scan worker")
            self.scan_status_changed.emit(f"Cannot start scan: {e}")
            self._finish_scan()
            return

        # Connect signals with error handling
        try:
            self.range_scan_worker.sprite_found.connect(self._on_range_sprite_found)
            self.range_scan_worker.progress_update.connect(self._on_range_scan_progress)
            self.range_scan_worker.scan_complete.connect(self._on_range_scan_complete)
            self.range_scan_worker.scan_paused.connect(self._on_scan_paused)
            self.range_scan_worker.scan_resumed.connect(self._on_scan_resumed)
            self.range_scan_worker.scan_stopped.connect(self._on_scan_stopped)
            self.range_scan_worker.cache_status.connect(self._on_cache_status)
            self.range_scan_worker.cache_progress_saved.connect(self._on_cache_progress_saved)

            # Start the worker with error recovery
            self.range_scan_worker.start()

        except RuntimeError as e:
            logger.exception("Failed to start range scan worker")
            self.scan_status_changed.emit(f"Scan startup failed: {e}")
            self._finish_scan()
        except Exception as e:
            logger.exception("Unexpected error starting scan")
            self.scan_status_changed.emit(f"Unexpected scan error: {e}")
            self._finish_scan()

    def _on_range_sprite_found(self, offset: int, quality: float):
        """Handle sprite found during range scan"""
        # Add to our found sprites list
        self.found_sprites.append((offset, quality))

        # Add to ROM map visualization
        if self.rom_map is not None:
            self.rom_map.add_found_sprite(offset, quality)

        # Calculate progress percentage based on current offset
        progress_pct = int((offset / self.rom_size) * 100) if self.rom_size > 0 else 0

        # Emit progress update with both arguments
        self.progress_update.emit(offset, progress_pct)

        # Emit sprite found signal
        self.sprite_found.emit(offset, quality)

        # Update status
        count = len(self.found_sprites)
        self.scan_status_changed.emit(f"Scanning... Found {count} sprite{'s' if count != 1 else ''}")

    def _on_range_scan_progress(self, current_offset: int, progress_pct: int):
        """Handle progress updates during range scan"""
        self.progress_update.emit(current_offset, progress_pct)

    def _on_range_scan_complete(self, found: bool):
        """Handle range scan completion"""
        self._finish_scan()

        # Update final status
        sprite_count = len(self.found_sprites)
        if sprite_count > 0:
            self.scan_status_changed.emit(f"Range scan complete: {sprite_count} sprites found")
        else:
            self.scan_status_changed.emit("Range scan complete: No sprites found")

    def _toggle_pause(self):
        """Toggle pause/resume for the current scan"""
        if self.range_scan_worker is None:
            return

        if self.range_scan_worker.is_paused:
            self.range_scan_worker.resume_scan()
        else:
            self.range_scan_worker.pause_scan()

    def _stop_scan(self):
        """Stop the current scan"""
        if self.range_scan_worker is not None:
            self.range_scan_worker.stop_scan()

    def _on_scan_paused(self):
        """Handle scan paused signal"""
        if self.pause_btn:
            self.pause_btn.setText("Resume")
        self.scan_status_changed.emit("Scan paused - click Resume to continue")

    def _on_scan_resumed(self):
        """Handle scan resumed signal"""
        if self.pause_btn:
            self.pause_btn.setText("Pause")
        count = len(self.found_sprites)
        self.scan_status_changed.emit(f"Scanning... Found {count} sprite{'s' if count != 1 else ''}")

    def _on_scan_stopped(self):
        """Handle scan stopped signal"""
        self._finish_scan()

        # Update status
        sprite_count = len(self.found_sprites)
        self.scan_status_changed.emit(f"Scan stopped by user: {sprite_count} sprites found")

    def _finish_scan(self):
        """Common scan cleanup operations"""
        self.is_scanning = False

        # Re-enable scan buttons and hide control buttons
        if self.scan_range_btn:
            self.scan_range_btn.setEnabled(True)
        if self.scan_all_btn:
            self.scan_all_btn.setEnabled(True)
        self.pause_btn.setVisible(False)
        self.stop_btn.setVisible(False)

        # Emit sprites for smart mode processing if any were found
        if self.found_sprites:
            self.sprites_detected.emit(self.found_sprites)

        # Emit scan finished signal
        self.scan_finished.emit()

    def cleanup_workers(self):
        """Clean up any running worker threads with timeouts to prevent hangs"""
        WorkerManager.cleanup_worker(self.range_scan_worker, timeout=5000)
        self.range_scan_worker = None

    def get_found_sprites(self) -> list[tuple[int, float]]:
        """Get the list of found sprites"""
        return self.found_sprites.copy()

    def _validate_scan_parameters(self, start_offset: int, end_offset: int) -> bool:
        """Validate scan parameters before starting scan"""
        # Validation constants
        min_scan_size = 0x100  # 256 bytes minimum
        max_safe_scan_size = 0x400000  # 4MB for safe performance
        max_scan_size = 0x2000000  # 32MB absolute maximum

        # Basic range validation
        if start_offset < 0:
            self.scan_status_changed.emit("Invalid start offset: cannot be negative")
            return False

        if end_offset >= self.rom_size:
            self.scan_status_changed.emit(f"Invalid end offset: exceeds ROM size (0x{self.rom_size:06X})")
            return False

        if start_offset >= end_offset:
            self.scan_status_changed.emit("Invalid range: start offset must be less than end offset")
            return False

        # Size validation
        scan_size = end_offset - start_offset + 1

        if scan_size < min_scan_size:
            self.scan_status_changed.emit(f"Scan range too small: {scan_size} bytes (minimum {min_scan_size})")
            return False

        if scan_size > max_scan_size:
            self.scan_status_changed.emit(
                f"Scan range too large: {scan_size / (1024*1024):.1f} MB (maximum {max_scan_size / (1024*1024):.0f} MB)"
            )
            return False

        # Performance warning for large scans
        if scan_size > max_safe_scan_size:
            scan_mb = scan_size / (1024 * 1024)
            result = _ = QMessageBox.question(
                self,
                "Large Scan Warning",
                f"Scan size is {scan_mb:.1f} MB, which may take several minutes.\n\n"
                f"Large scans can impact system performance.\n"
                f"Continue with scan?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if result != QMessageBox.StandardButton.Yes:
                self.scan_status_changed.emit("Large scan cancelled by user")
                return False

        return True

    def is_scan_active(self) -> bool:
        """Check if a scan is currently active"""
        return self.is_scanning

    def _check_for_cached_scans(self) -> None:
        """Check for cached partial scan results and emit signal if found"""
        if not self.rom_path:
            return

        try:
            rom_cache = self.rom_cache
            if not rom_cache.cache_enabled:
                return

            # Check common scan parameter combinations that might have cached results
            common_scan_params = [
                # Range scan parameters (around current offset)
                {
                    "start_offset": max(0, self.current_offset - 0x10000),  # 64KB before current
                    "end_offset": min(self.rom_size, self.current_offset + 0x10000),  # 64KB after current
                    "step": 0x100,
                    "quality_threshold": 0.5,
                    "min_sprite_size": 512,
                    "max_sprite_size": 32768
                },
                # Full ROM scan parameters
                {
                    "start_offset": 0,
                    "end_offset": self.rom_size,
                    "step": 0x100,
                    "quality_threshold": 0.5,
                    "min_sprite_size": 512,
                    "max_sprite_size": 32768
                }
            ]

            # Check each parameter set for cached results
            for scan_params in common_scan_params:
                cached_progress = rom_cache.get_partial_scan_results(self.rom_path, cast(dict[str, int], scan_params))
                if cached_progress and not cached_progress.get("completed", False):
                    # Found incomplete cached scan - emit signal for parent to handle
                    logger.info(f"Found cached partial scan for ROM: {Path(self.rom_path).name}")
                    self._update_cache_status(f"Found cached scan with {len(cached_progress.get('found_sprites', []))} sprites")
                    self.partial_scan_detected.emit(cached_progress)
                    return

            # Check for completed scans to show status
            for scan_params in common_scan_params:
                cached_progress = rom_cache.get_partial_scan_results(self.rom_path, cast(dict[str, int], scan_params))
                if cached_progress and cached_progress.get("completed", False):
                    sprite_count = len(cached_progress.get("found_sprites", []))
                    if sprite_count > 0:
                        self._update_cache_status(f"Cache: {sprite_count} sprites found previously")
                        return

            # Clear status if no relevant cache found
            self._clear_cache_status()

        except Exception as e:
            logger.warning(f"Error checking for cached scans: {e}")
            self._clear_cache_status()

    def _update_cache_status(self, message: str, status_type: str = "default") -> None:
        """Update the cache status label with different styling based on type"""
        if self.cache_status_label is None:
            return

        if self.cache_status_label:
            self.cache_status_label.setText(message)
        self.cache_status_label.setVisible(True)

        # Different styles for different cache operations (dark theme compatible)
        if "resumed" in message.lower() or "resuming" in message.lower():
            # Cache resume - blue theme (dark)
            style = f"""
                QLabel {{
                    background-color: {COLORS["cache_checking_bg"]};
                    color: {COLORS["cache_checking_text"]};
                    border: 1px solid {COLORS["cache_checking_border"]};
                    border-radius: 3px;
                    padding: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """
        elif "saved" in message.lower() or "progress" in message.lower():
            # Cache save - orange theme (dark)
            style = f"""
                QLabel {{
                    background-color: {COLORS["cache_fresh_bg"]};
                    color: {COLORS["cache_fresh_text"]};
                    border: 1px solid {COLORS["cache_fresh_border"]};
                    border-radius: 3px;
                    padding: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """
        elif "complete" in message.lower():
            # Completion - green theme (dark)
            style = f"""
                QLabel {{
                    background-color: {COLORS["cache_resuming_bg"]};
                    color: {COLORS["cache_resuming_text"]};
                    border: 1px solid {COLORS["cache_resuming_border"]};
                    border-radius: 3px;
                    padding: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """
        else:
            # Default - gray theme (dark)
            style = f"""
                QLabel {{
                    background-color: {COLORS["panel_background"]};
                    color: {COLORS["text_muted"]};
                    border: 1px solid {COLORS["border"]};
                    border-radius: 3px;
                    padding: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """

        if self.cache_status_label:
            self.cache_status_label.setStyleSheet(style)

    def _clear_cache_status(self) -> None:
        """Clear the cache status label"""
        if self.cache_status_label is not None:
            self.cache_status_label.setVisible(False)

    def _check_scan_cache_before_start(self, start_offset: int, end_offset: int) -> bool | None:
        """
        Check for cached partial scan for the specified range and show ResumeScanDialog if needed.

        Returns:
            True: Use cache (resume scan)
            False: Don't use cache (fresh scan)
            None: User cancelled
        """
        # Local import to avoid circular dependency
        from ui.dialogs import ResumeScanDialog

        try:
            rom_cache = self.rom_cache
            if not rom_cache.cache_enabled:
                return False  # No cache, proceed with fresh scan

            # Create scan parameters for this range
            scan_params = {
                "start_offset": start_offset,
                "end_offset": end_offset,
                "step": 0x100,
                "quality_threshold": 0.5,
                "min_sprite_size": 512,
                "max_sprite_size": 32768
            }

            # Check for cached partial scan
            cached_progress = rom_cache.get_partial_scan_results(self.rom_path, cast(dict[str, int], scan_params))
            if cached_progress and not cached_progress.get("completed", False):
                # Found incomplete cached scan - show ResumeScanDialog
                user_choice = ResumeScanDialog.show_resume_dialog(cached_progress, self)

                if user_choice == ResumeScanDialog.RESUME:
                    # User wants to resume
                    self._update_cache_status("Resuming from cached progress...")
                    return True
                if user_choice == ResumeScanDialog.START_FRESH:
                    # User wants fresh scan - clear the cache
                    rom_cache.clear_scan_progress_cache(self.rom_path, cast(dict[str, int], scan_params))
                    self._update_cache_status("Starting fresh scan (cache cleared)")
                    return False
                # User cancelled
                return None

            # No cached scan found, proceed with fresh scan
            return False

        except Exception as e:
            logger.warning(f"Error checking scan cache: {e}")
            return False  # Continue with fresh scan on error

    def _on_cache_status(self, status_message: str) -> None:
        """Handle cache status updates from worker"""
        self._update_cache_status(status_message)
        self.scan_status_changed.emit(status_message)

    def _on_cache_progress_saved(self, current_offset: int, sprites_found: int, progress_pct: int) -> None:
        """Handle cache progress save notifications from worker"""
        cache_message = f"Progress saved: {progress_pct}% complete, {sprites_found} sprites found"
        self._update_cache_status(cache_message)
        logger.debug(f"Cache progress saved at offset 0x{current_offset:06X}: {sprites_found} sprites ({progress_pct}%)")
