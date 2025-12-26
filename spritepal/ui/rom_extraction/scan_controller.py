"""
Scan controller for ROM extraction panel.

This module manages the sprite scanning workflow including cache coordination,
scan dialog creation, and result formatting.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.types import SpriteInfo
from ui.rom_extraction.workers import SpriteScanWorker
from ui.styles.components import get_cache_status_style
from utils.constants import ROM_SCAN_START_DEFAULT, ROM_SIZE_4MB
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache

logger = get_logger(__name__)


def compute_scan_params(
    rom_path: str,
    start_offset: int | None = None,
    end_offset: int | None = None,
    step: int | None = None,
) -> dict[str, int]:
    """Compute scan parameters from ROM size.

    This function ensures consistency between cache key generation and
    actual scan execution by centralizing parameter computation.

    Args:
        rom_path: Path to the ROM file
        start_offset: Optional custom start offset (defaults to 0x40000)
        end_offset: Optional custom end offset (defaults to min(rom_size, 0x400000))
        step: Optional step size (defaults to 0x100 for alignment)

    Returns:
        Dict with keys: start_offset, end_offset, alignment
    """
    if start_offset is not None and end_offset is not None:
        return {
            "start_offset": start_offset,
            "end_offset": end_offset,
            "alignment": step if step is not None else 0x100,
        }

    rom_size = Path(rom_path).stat().st_size
    return {
        "start_offset": ROM_SCAN_START_DEFAULT,
        "end_offset": min(rom_size, ROM_SIZE_4MB),
        "alignment": step if step is not None else 0x100,
    }


class ScanDialog(QDialog):
    """Dialog for sprite scanning with typed attributes."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Typed attributes that will be set during initialization
        self.cache_status_label: QLabel
        self.progress_bar: QProgressBar
        self.results_text: QTextEdit
        self.button_box: QDialogButtonBox
        self.apply_btn: QPushButton | None
        # Cache reference set at runtime during scan initialization
        self.rom_cache: ROMCache | None = None


class ScanContext:
    """Context object for sharing data between scan event handlers."""

    def __init__(self) -> None:
        self.found_offsets: list[SpriteInfo] = []
        self.selected_offset: int | None = None


class ScanController(QObject):
    """
    Manages sprite scanning workflow and cache coordination.

    This class handles the complete scan workflow:
    - Scan dialog creation and management
    - Cache checking and saving
    - Worker lifecycle management
    - Result formatting for display
    """

    # Signals
    cache_status_changed = Signal(str, str)  # status, style_class
    scan_started = Signal()  # Notify that scanning began
    scan_progress = Signal(int, int)  # current, total
    sprite_found = Signal(object)  # sprite_info dict (use object to avoid PySide6 copy warning)
    scan_complete = Signal(list)  # all found_offsets
    scan_cancelled = Signal()  # User cancelled or error
    sprite_selected = Signal(int)  # Selected offset to apply

    def __init__(
        self,
        cache: ROMCache | None = None,
        state_manager: ApplicationStateManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        """
        Initialize the scan controller.

        Args:
            cache: ROM cache for storing/retrieving scan results
            state_manager: Application state manager for state transitions
            parent: Parent QObject
        """
        super().__init__(parent)
        self._cache = cache
        self._state_manager = state_manager
        self._current_rom_path: str | None = None
        self._scan_params: Mapping[str, int] = {}

        # Workflow state
        self._scan_worker: SpriteScanWorker | None = None
        self._current_dialog: ScanDialog | None = None
        self._scan_context: ScanContext | None = None

        logger.debug("ScanController initialized")

    def set_cache(self, cache: ROMCache) -> None:
        """Set the ROM cache for scan result storage."""
        self._cache = cache

    def set_state_manager(self, state_manager: ApplicationStateManager) -> None:
        """Set the application state manager."""
        self._state_manager = state_manager

    @property
    def is_scanning(self) -> bool:
        """Whether a scan is currently in progress."""
        return self._scan_worker is not None and self._scan_worker.isRunning()

    # ========== Main Entry Point ==========

    def start_scan(
        self,
        rom_path: str,
        extractor: ROMExtractor,
        parent_widget: QWidget,
    ) -> None:
        """
        Start the sprite scanning workflow.

        This is the single entry point for scanning. It:
        1. Checks state manager for permission to scan
        2. Creates and shows the dialog
        3. Checks cache / prompts for resume
        4. Creates worker and connects signals
        5. Emits sprite_selected when user applies result

        Args:
            rom_path: Path to the ROM file to scan
            extractor: ROM extractor for decompression
            parent_widget: Parent widget for the dialog
        """
        from ui.dialogs import UserErrorDialog

        if not rom_path:
            return

        # Check if we can start scanning
        if self._state_manager and not self._state_manager.can_scan:
            logger.warning("Cannot start scan - another operation is in progress")
            return

        # Transition to scanning state
        if self._state_manager and not self._state_manager.start_scanning():
            logger.error("Failed to transition to scanning state")
            return

        try:
            self._current_rom_path = rom_path
            dialog = self._create_scan_dialog(parent_widget)
            self._current_dialog = dialog
            self._setup_scan_worker(dialog, rom_path, extractor)

            self.scan_started.emit()
            dialog.exec()
        except Exception as e:
            logger.exception("Error in sprite scanning")
            if self._state_manager:
                self._state_manager.finish_scanning(success=False, error=str(e))
            UserErrorDialog.display_error(parent_widget, "Failed to scan for sprites", f"Technical details: {e!s}")

    def cancel(self) -> None:
        """Cancel the current scan operation."""
        if self._scan_worker:
            self._scan_worker.cancel()
        if self._current_dialog:
            self._current_dialog.reject()
        self.scan_cancelled.emit()

    def cleanup(self) -> None:
        """Clean up worker resources."""
        from ui.common import WorkerManager

        if self._scan_worker:
            self._scan_worker.blockSignals(True)
        WorkerManager.cleanup_worker_attr(self, "_scan_worker")
        self._current_dialog = None
        self._scan_context = None

    # ========== Dialog Creation ==========

    def _create_scan_dialog(self, parent: QWidget | None = None) -> ScanDialog:
        """Create and configure the sprite scanning dialog.

        Args:
            parent: Parent widget

        Returns:
            Configured ScanDialog instance
        """
        dialog = ScanDialog(parent)
        dialog.setWindowTitle("Find Sprites")
        dialog.setMinimumSize(600, 400)

        # Build dialog UI
        layout = QVBoxLayout()

        # Create UI components
        cache_status_label = self._create_cache_status_label()
        progress_bar = self._create_progress_bar()
        results_text = self._create_results_text()
        button_box = self._create_button_box()

        # Add to layout
        layout.addWidget(cache_status_label)
        layout.addWidget(progress_bar)
        layout.addWidget(results_text)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        # Store references for later access
        dialog.cache_status_label = cache_status_label
        dialog.progress_bar = progress_bar
        dialog.results_text = results_text
        dialog.button_box = button_box
        dialog.apply_btn = button_box.button(QDialogButtonBox.StandardButton.Apply)

        return dialog

    def _create_cache_status_label(self) -> QLabel:
        """Create the cache status label."""
        label = QLabel("Checking cache...")
        label.setStyleSheet(get_cache_status_style("checking"))
        return label

    def _create_progress_bar(self) -> QProgressBar:
        """Create the progress bar."""
        progress_bar = QProgressBar()
        progress_bar.setTextVisible(True)
        return progress_bar

    def _create_results_text(self) -> QTextEdit:
        """Create the results text area."""
        results_text = QTextEdit()
        results_text.setReadOnly(True)
        results_text.setPlainText("Starting sprite scan...\n\n")
        return results_text

    def _create_button_box(self) -> QDialogButtonBox:
        """Create the button box with Close and Apply buttons."""
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close | QDialogButtonBox.StandardButton.Apply)
        apply_btn = button_box.button(QDialogButtonBox.StandardButton.Apply)
        if apply_btn:
            apply_btn.setText("Use Selected Offset")
            apply_btn.setEnabled(False)
        return button_box

    # ========== Worker Setup ==========

    def _setup_scan_worker(
        self,
        dialog: ScanDialog,
        rom_path: str,
        extractor: ROMExtractor,
    ) -> None:
        """Set up the scan worker and connect signals.

        Args:
            dialog: The scan dialog containing UI elements
            rom_path: Path to the ROM file
            extractor: ROM extractor for decompression
        """
        from core.app_context import get_app_context
        from ui.common import WorkerManager

        # Clean up any existing scan worker
        WorkerManager.cleanup_worker_attr(self, "_scan_worker")

        # Check cache and get user preference
        use_cache = self._check_scan_cache(dialog, rom_path)
        if use_cache is None:
            # User cancelled
            dialog.reject()
            return

        # Get rom_cache from self._cache or AppContext
        rom_cache = self._cache if self._cache is not None else get_app_context().rom_cache

        # Create scan worker
        self._scan_worker = SpriteScanWorker(rom_path, extractor, use_cache=use_cache, parent=self, rom_cache=rom_cache)

        # Create scan context to pass data between handlers
        self._scan_context = ScanContext()

        # Connect worker signals
        self._connect_scan_signals(dialog)

        # Connect dialog signals
        self._connect_dialog_signals(dialog)

        # Start scanning
        self._scan_worker.start()

    def _check_scan_cache(self, dialog: ScanDialog, rom_path: str) -> bool | None:
        """Check for cached scan results and get user preference.

        Args:
            dialog: The scan dialog
            rom_path: Path to the ROM file

        Returns:
            True to use cache, False to start fresh, None if cancelled
        """
        from core.app_context import get_app_context
        from ui.dialogs import ResumeScanDialog

        rom_cache = get_app_context().rom_cache

        # Compute scan parameters from ROM size (matches SpriteScanWorker)
        scan_params = compute_scan_params(rom_path)

        partial_cache = rom_cache.get_partial_scan_results(rom_path, scan_params)

        # Store cache reference for later use
        dialog.rom_cache = rom_cache

        if partial_cache and not partial_cache.get("completed", False):
            # Show resume dialog
            parent_widget = dialog.parent() if dialog.parent() else dialog
            user_choice = ResumeScanDialog.show_resume_dialog(dict(partial_cache), cast(QWidget, parent_widget))

            if user_choice == ResumeScanDialog.CANCEL:
                return None
            if user_choice == ResumeScanDialog.START_FRESH:
                self._update_cache_status(dialog, "fresh", "Starting fresh scan (ignoring cache)")
                return False
            # RESUME
            self._update_cache_status(dialog, "resuming", "\U0001f4ca Resuming from cached progress...")
            return True
        self._update_cache_status(dialog, "fresh", "No cache found - starting fresh scan")
        return True

    def _update_cache_status(self, dialog: ScanDialog, status: str, text: str) -> None:
        """Update the cache status label.

        Args:
            dialog: The scan dialog
            status: Status type for styling
            text: Status text to display
        """
        dialog.cache_status_label.setText(text)
        dialog.cache_status_label.setStyleSheet(get_cache_status_style(status))

    # ========== Signal Connections ==========

    def _connect_scan_signals(self, dialog: ScanDialog) -> None:
        """Connect scan worker signals to handlers.

        Args:
            dialog: The scan dialog
        """
        if self._scan_worker:
            self._scan_worker.progress_detailed.connect(lambda c, t: self._on_scan_progress(dialog, c, t))
            self._scan_worker.sprite_found.connect(lambda info: self._on_sprite_found(dialog, info))
            self._scan_worker.finished.connect(lambda: self._on_scan_complete(dialog))
            self._scan_worker.cache_status.connect(lambda status: self._on_cache_status(dialog, status))
            self._scan_worker.cache_progress.connect(lambda progress: self._on_cache_progress(dialog, progress))

    def _connect_dialog_signals(self, dialog: ScanDialog) -> None:
        """Connect dialog button signals.

        Args:
            dialog: The scan dialog
        """
        # Connect dialog finished signal
        dialog.finished.connect(lambda result: self._on_dialog_finished(dialog, result))

        # Connect button box signals
        dialog.button_box.rejected.connect(dialog.reject)

        if dialog.apply_btn:
            dialog.apply_btn.clicked.connect(lambda: self._on_apply_clicked(dialog))

    # ========== Signal Handlers ==========

    def _on_scan_progress(self, dialog: ScanDialog, current: int, total: int) -> None:
        """Handle scan progress update."""
        dialog.progress_bar.setValue(int((current / total) * 100))
        dialog.progress_bar.setFormat(f"Scanning... {current}/{total}")
        self.scan_progress.emit(current, total)

    def _on_sprite_found(self, dialog: ScanDialog, sprite_info: SpriteInfo) -> None:
        """Handle sprite found during scan."""
        if self._scan_context is None:
            return

        self._scan_context.found_offsets.append(sprite_info)

        # Update results text
        text = self._format_sprite_info_detailed(sprite_info)
        current_text = dialog.results_text.toPlainText()
        dialog.results_text.setPlainText(current_text + text)

        # Enable apply button after first find
        if len(self._scan_context.found_offsets) == 1 and dialog.apply_btn:
            dialog.apply_btn.setEnabled(True)

        self.sprite_found.emit(sprite_info)

    def _on_scan_complete(self, dialog: ScanDialog) -> None:
        """Handle scan completion."""
        if self._scan_context is None:
            return

        dialog.progress_bar.setValue(100)
        dialog.progress_bar.setFormat("Scan complete")

        # Update results text
        summary_text = self._format_scan_summary_detailed(self._scan_context.found_offsets)
        current_text = dialog.results_text.toPlainText()
        dialog.results_text.setPlainText(current_text + summary_text)

        if self._scan_context.found_offsets:
            # Save results to cache
            self._save_scan_results_to_cache(dialog, self._scan_context.found_offsets)
        # No sprites found
        elif dialog.apply_btn:
            dialog.apply_btn.setEnabled(False)

        self.scan_complete.emit(self._scan_context.found_offsets)

    def _on_cache_status(self, dialog: ScanDialog, status: str) -> None:
        """Handle cache status update."""
        dialog.cache_status_label.setText(f"\U0001f4be {status}")

        # Update style based on status
        if "Saving" in status:
            style_type = "saving"
        elif "Resuming" in status:
            style_type = "resuming"
        else:
            style_type = "checking"

        dialog.cache_status_label.setStyleSheet(get_cache_status_style(style_type))

    def _on_cache_progress(self, dialog: ScanDialog, progress: int) -> None:
        """Handle cache progress update."""
        if progress > 0:
            dialog.cache_status_label.setText(f"\U0001f4be Saving progress ({progress}%)...")

    def _on_apply_clicked(self, dialog: ScanDialog) -> None:
        """Handle Apply button click."""
        if self._scan_context and self._scan_context.found_offsets:
            # Use the best quality offset
            self._scan_context.selected_offset = self._scan_context.found_offsets[0]["offset"]
            dialog.accept()

    def _on_dialog_finished(self, dialog: ScanDialog, result: int) -> None:
        """Handle dialog close."""
        from ui.common import WorkerManager

        # Disconnect signals BEFORE cleanup to prevent crashes from queued signals
        if self._scan_worker:
            self._scan_worker.blockSignals(True)
            # Disconnect lambda signals to prevent accessing deleted dialog
            try:
                self._scan_worker.progress_detailed.disconnect()
                self._scan_worker.sprite_found.disconnect()
                self._scan_worker.finished.disconnect()
                self._scan_worker.cache_status.disconnect()
                self._scan_worker.cache_progress.disconnect()
            except (RuntimeError, TypeError):
                pass  # Already disconnected

        # NOW safe to cleanup
        WorkerManager.cleanup_worker_attr(self, "_scan_worker")

        # Transition back to idle state
        if self._state_manager:
            self._state_manager.finish_scanning()

        # Handle accepted dialog with selected offset
        if (
            result == QDialog.DialogCode.Accepted
            and self._scan_context is not None
            and self._scan_context.selected_offset is not None
        ):
            self.sprite_selected.emit(self._scan_context.selected_offset)

        # Clear dialog reference
        self._current_dialog = None

    # ========== Cache Operations ==========

    def check_cache(
        self,
        rom_path: str,
        scan_params: dict[str, int] | None = None,
    ) -> tuple[bool, list[Mapping[str, object]]]:
        """
        Check if scan results exist in cache.

        Args:
            rom_path: Path to the ROM file
            scan_params: Parameters used for the scan

        Returns:
            Tuple of (cache_hit, cached_sprites)
        """
        if not self._cache:
            return False, []

        self._current_rom_path = rom_path
        self._scan_params = scan_params or {}

        try:
            cached = self._cache.get_partial_scan_results(rom_path, scan_params or {})
            if cached:
                self.cache_status_changed.emit("Cache hit", "cache-hit")
                # Extract the sprites list from the cached result dict
                sprites_obj = cached.get("found_sprites", [])
                sprites = cast(list[Mapping[str, object]], sprites_obj)
                return True, sprites
            self.cache_status_changed.emit("No cache", "cache-miss")
            return False, []
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
            self.cache_status_changed.emit("Cache error", "cache-error")
            return False, []

    def save_results(
        self,
        rom_path: str,
        sprites: list[Mapping[str, object]],
        scan_params: dict[str, int] | None = None,
        current_offset: int = 0,
        completed: bool = True,
    ) -> bool:
        """
        Save scan results to cache.

        Args:
            rom_path: Path to the ROM file
            sprites: List of found sprite dictionaries
            scan_params: Parameters used for the scan
            current_offset: Current scan offset position
            completed: Whether the scan is complete

        Returns:
            True if save succeeded
        """
        if not self._cache:
            logger.warning("No cache configured, cannot save results")
            return False

        try:
            self._cache.save_partial_scan_results(
                rom_path,
                scan_params or {},
                sprites,
                current_offset,
                completed,
            )
            self.cache_status_changed.emit("Results cached", "cache-saved")
            logger.info(f"Saved {len(sprites)} sprites to cache")
            return True
        except Exception as e:
            logger.error(f"Failed to save scan results: {e}")
            self.cache_status_changed.emit("Save failed", "cache-error")
            return False

    def _save_scan_results_to_cache(self, dialog: ScanDialog, found_offsets: list[SpriteInfo]) -> None:
        """Save scan results to cache."""
        self._update_cache_status(dialog, "saving", "\U0001f4be Saving results to cache...")
        # Defer actual save to next event loop iteration to allow UI update
        QTimer.singleShot(0, lambda: self._do_cache_save(dialog, found_offsets))

    def _do_cache_save(self, dialog: ScanDialog, found_offsets: list[SpriteInfo]) -> None:
        """Perform the actual cache save operation."""
        if self._current_rom_path is None:
            return

        # Convert to cache format
        sprite_locations: dict[str, Mapping[str, object]] = {}
        for sprite in found_offsets:
            name = f"scanned_0x{sprite['offset']:X}"
            sprite_locations[name] = {
                "offset": sprite["offset"],
                "compressed_size": sprite.get("compressed_size"),
                "quality": sprite.get("quality", 0.0),
            }

        # Save to cache
        if dialog.rom_cache and dialog.rom_cache.save_sprite_locations(self._current_rom_path, sprite_locations):
            self._update_cache_status(dialog, "saved", f"\u2705 Saved {len(found_offsets)} sprites to cache")
            # Update results text
            current_text = dialog.results_text.toPlainText()
            dialog.results_text.setPlainText(
                current_text + "\n\u2705 Results saved to cache for faster future scans.\n"
            )
        else:
            dialog.cache_status_label.setText("\u26a0\ufe0f Could not save to cache")
            current_text = dialog.results_text.toPlainText()
            dialog.results_text.setPlainText(current_text + "\n\u26a0\ufe0f Could not save results to cache.\n")

    def get_cache_key(self, rom_path: str, scan_params: Mapping[str, int] | None = None) -> str:
        """Generate a cache key for the given ROM and scan parameters."""
        params_str = str(sorted((scan_params or {}).items()))
        key_data = f"{rom_path}:{params_str}"
        return hashlib.md5(key_data.encode()).hexdigest()[:12]

    # ========== Result Formatting ==========

    def format_sprite_info(self, sprite: Mapping[str, object]) -> str:
        """
        Format a sprite dictionary for display (simple format).

        Args:
            sprite: Sprite data dictionary

        Returns:
            Formatted string for display
        """
        offset = cast(int, sprite.get("offset", 0))
        size = cast(int, sprite.get("size", 0))
        name = cast(str, sprite.get("name", "Unknown"))

        # Format offset as hex
        offset_str = f"0x{offset:06X}"

        # Format size in KB if large enough
        if size >= 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} bytes"

        return f"{name} @ {offset_str} ({size_str})"

    def _format_sprite_info_detailed(self, sprite_info: SpriteInfo) -> str:
        """Format sprite info for display (detailed format for scan results)."""
        text = f"Found sprite at {sprite_info['offset_hex']}:\n"
        text += f"  - Tiles: {sprite_info['tile_count']}\n"
        text += f"  - Alignment: {sprite_info['alignment']}\n"
        text += f"  - Quality: {sprite_info['quality']:.2f}\n"
        text += f"  - Size: {sprite_info['compressed_size']} bytes compressed\n"
        if "size_limit_used" in sprite_info:
            text += f"  - Size limit: {sprite_info['size_limit_used']} bytes\n"
        text += "\n"
        return text

    def format_scan_summary(
        self,
        sprites: list[Mapping[str, object]],
        scan_time: float | None = None,
        from_cache: bool = False,
    ) -> str:
        """
        Format a summary of scan results (simple format).

        Args:
            sprites: List of found sprites
            scan_time: Time taken for scan in seconds
            from_cache: Whether results were from cache

        Returns:
            Formatted summary string
        """
        count = len(sprites)
        lines = [
            f"Found {count} sprite{'s' if count != 1 else ''}",
        ]

        if from_cache:
            lines.append("(from cache)")
        elif scan_time is not None:
            lines.append(f"Scan completed in {scan_time:.1f}s")

        # Add size summary
        total_size = sum(cast(int, s.get("size", 0)) for s in sprites)
        if total_size > 0:
            if total_size >= 1024 * 1024:
                size_str = f"{total_size / (1024 * 1024):.1f} MB"
            elif total_size >= 1024:
                size_str = f"{total_size / 1024:.1f} KB"
            else:
                size_str = f"{total_size} bytes"
            lines.append(f"Total size: {size_str}")

        return "\n".join(lines)

    def _format_scan_summary_detailed(self, found_offsets: list[SpriteInfo]) -> str:
        """Format scan completion summary (detailed format for scan results)."""
        from operator import itemgetter

        text = f"\nScan complete! Found {len(found_offsets)} valid sprite locations.\n"

        if found_offsets:
            text += "\nBest quality sprites:\n"
            # Sort by quality
            sorted_sprites = sorted(found_offsets, key=itemgetter("quality"), reverse=True)

            for i, sprite in enumerate(sorted_sprites[:5]):
                size_info = ""
                if "size_limit_used" in sprite:
                    size_info = f", {sprite['size_limit_used'] / 1024:.0f}KB limit"
                text += (
                    f"{i + 1}. {sprite['offset_hex']} - Quality: {sprite['quality']:.2f}, "
                    f"{sprite['tile_count']} tiles{size_info}\n"
                )
        else:
            text += "\nNo valid sprites found in scanned range.\n"

        return text
