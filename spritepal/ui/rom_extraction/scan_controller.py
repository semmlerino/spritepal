"""
Scan controller for ROM extraction panel.

This module manages the sprite scanning workflow including cache coordination,
scan dialog creation, and result formatting.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import QObject, Signal
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

from ui.styles.components import get_cache_status_style
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ROMCacheProtocol

logger = get_logger(__name__)


class ScanController(QObject):
    """
    Manages sprite scanning workflow and cache coordination.

    This class handles:
    - Scan cache checking and saving
    - Scan dialog creation and management
    - Result formatting for display
    """

    # Signals
    cache_status_changed = Signal(str, str)  # status, style_class
    cache_hit = Signal(list)  # cached sprites
    scan_requested = Signal(str, int)  # rom_path, step size

    def __init__(
        self,
        cache: ROMCacheProtocol | None = None,
        parent: QObject | None = None,
    ) -> None:
        """
        Initialize the scan controller.

        Args:
            cache: ROM cache for storing/retrieving scan results
            parent: Parent QObject
        """
        super().__init__(parent)
        self._cache = cache
        self._current_rom_path: str | None = None
        self._scan_params: dict[str, Any] = {}

        logger.debug("ScanController initialized")

    def set_cache(self, cache: ROMCacheProtocol) -> None:
        """Set the ROM cache for scan result storage."""
        self._cache = cache

    # ========== Cache Operations ==========

    def check_cache(
        self,
        rom_path: str,
        scan_params: dict[str, Any] | None = None,
    ) -> tuple[bool, list[dict[str, Any]]]:
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
            # Protocol expects dict[str, int] for scan_params
            cache_params = cast(dict[str, int], scan_params) if scan_params else {}
            cached = self._cache.get_partial_scan_results(rom_path, cache_params)
            if cached:
                self.cache_status_changed.emit("Cache hit", "cache-hit")
                # Extract the sprites list from the cached result dict
                sprites = cached.get("found_sprites", [])
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
        sprites: list[dict[str, Any]],
        scan_params: dict[str, Any] | None = None,
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
            # Protocol expects dict[str, int] for scan_params
            cache_params = cast(dict[str, int], scan_params) if scan_params else {}
            self._cache.save_partial_scan_results(
                rom_path,
                cache_params,
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

    def get_cache_key(self, rom_path: str, scan_params: dict[str, Any] | None = None) -> str:
        """Generate a cache key for the given ROM and scan parameters."""
        params_str = str(sorted((scan_params or {}).items()))
        key_data = f"{rom_path}:{params_str}"
        return hashlib.md5(key_data.encode()).hexdigest()[:12]

    # ========== Result Formatting ==========

    def format_sprite_info(self, sprite: dict[str, Any]) -> str:
        """
        Format a sprite dictionary for display.

        Args:
            sprite: Sprite data dictionary

        Returns:
            Formatted string for display
        """
        offset = sprite.get("offset", 0)
        size = sprite.get("size", 0)
        name = sprite.get("name", "Unknown")

        # Format offset as hex
        offset_str = f"0x{offset:06X}"

        # Format size in KB if large enough
        if size >= 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} bytes"

        return f"{name} @ {offset_str} ({size_str})"

    def format_scan_summary(
        self,
        sprites: list[dict[str, Any]],
        scan_time: float | None = None,
        from_cache: bool = False,
    ) -> str:
        """
        Format a summary of scan results.

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
        total_size = sum(s.get("size", 0) for s in sprites)
        if total_size > 0:
            if total_size >= 1024 * 1024:
                size_str = f"{total_size / (1024 * 1024):.1f} MB"
            elif total_size >= 1024:
                size_str = f"{total_size / 1024:.1f} KB"
            else:
                size_str = f"{total_size} bytes"
            lines.append(f"Total size: {size_str}")

        return "\n".join(lines)

    # ========== Dialog Creation ==========

    def create_scan_dialog(
        self,
        parent: QWidget | None = None,
        title: str = "Sprite Scanner",
    ) -> QDialog:
        """
        Create a scan progress dialog.

        Args:
            parent: Parent widget
            title: Dialog title

        Returns:
            Configured QDialog for scan progress
        """
        dialog = QDialog(parent)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(500)
        dialog.setMinimumHeight(400)

        layout = QVBoxLayout(dialog)

        # Cache status label
        cache_label = QLabel("Checking cache...")
        cache_label.setObjectName("cache_status_label")
        cache_label.setStyleSheet(get_cache_status_style("checking"))
        layout.addWidget(cache_label)

        # Progress bar
        progress = QProgressBar()
        progress.setObjectName("progress_bar")
        progress.setRange(0, 100)
        progress.setValue(0)
        layout.addWidget(progress)

        # Results text area
        results = QTextEdit()
        results.setObjectName("results_text")
        results.setReadOnly(True)
        layout.addWidget(results)

        # Button box
        button_box = QDialogButtonBox()
        button_box.setObjectName("button_box")

        apply_btn = QPushButton("Apply Selected")
        apply_btn.setEnabled(False)
        button_box.addButton(apply_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        button_box.addButton(QDialogButtonBox.StandardButton.Cancel)

        layout.addWidget(button_box)

        # Store references
        dialog.cache_status_label = cache_label  # type: ignore[attr-defined]
        dialog.progress_bar = progress  # type: ignore[attr-defined]
        dialog.results_text = results  # type: ignore[attr-defined]
        dialog.button_box = button_box  # type: ignore[attr-defined]
        dialog.apply_btn = apply_btn  # type: ignore[attr-defined]

        return dialog

    def update_dialog_progress(
        self,
        dialog: QDialog,
        current: int,
        total: int,
        message: str | None = None,
    ) -> None:
        """Update the progress bar in a scan dialog."""
        progress_bar = dialog.findChild(QProgressBar, "progress_bar")
        if progress_bar:
            percent = int((current / total) * 100) if total > 0 else 0
            progress_bar.setValue(percent)

        if message:
            results_text = dialog.findChild(QTextEdit, "results_text")
            if results_text:
                results_text.append(message)

    def update_dialog_cache_status(
        self,
        dialog: QDialog,
        status: str,
        style_class: str = "default",
    ) -> None:
        """Update the cache status label in a scan dialog."""
        cache_label = dialog.findChild(QLabel, "cache_status_label")
        if cache_label:
            cache_label.setText(status)
            cache_label.setStyleSheet(get_cache_status_style(style_class))
