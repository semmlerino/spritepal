"""
Status Panel for Manual Offset Dialog

Displays detection status, progress information, scanning progress, and cache status.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from ui.common.spacing_constants import SPACING_COMPACT_SMALL, SPACING_SMALL, SPACING_TINY
from ui.common.widget_helpers import create_styled_label
from ui.styles import get_muted_text_style, get_panel_style
from ui.styles.theme import COLORS

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from core.services.rom_cache import ROMCache


class StatusPanel(QWidget):
    """Panel for displaying status information and progress"""

    def __init__(
        self, parent: QWidget | None = None, *, settings_manager: ApplicationStateManager, rom_cache: ROMCache
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(get_panel_style())

        # Assign dependencies
        self.settings_manager = settings_manager
        self.rom_cache = rom_cache

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the status panel UI with improved readability"""
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)
        layout.setSpacing(SPACING_TINY)

        # CRITICAL FIX: Set proper parent for all child widgets to prevent Qt lifecycle bugs
        status_label = create_styled_label("Status", style="section", parent=self)
        layout.addWidget(status_label)

        self.detection_info = QLabel("Ready", parent=self)
        self.detection_info.setWordWrap(True)
        if self.detection_info:
            self.detection_info.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")  # Readable text
        layout.addWidget(self.detection_info)

        # Progress bar (initially hidden) - set proper parent
        self.scan_progress = QProgressBar(parent=self)
        self.scan_progress.setVisible(False)
        self.scan_progress.setMaximumHeight(16)  # Thinner progress bar
        layout.addWidget(self.scan_progress)

        # Cache status section
        self._setup_cache_status(layout)

        self.setLayout(layout)

    def update_status(self, message: str) -> None:
        """Update the status message"""
        if self.detection_info:
            self.detection_info.setText(message)

    def show_progress(self, minimum: int = 0, maximum: int = 100) -> None:
        """Show and configure the progress bar"""
        self.scan_progress.setRange(minimum, maximum)
        self.scan_progress.setValue(minimum)
        self.scan_progress.setVisible(True)

    def hide_progress(self) -> None:
        """Hide the progress bar"""
        self.scan_progress.setVisible(False)

    def update_progress(self, value: int) -> None:
        """Update the progress bar value"""
        if self.scan_progress.isVisible():
            self.scan_progress.setValue(value)

    def get_progress_bar(self) -> QProgressBar:
        """Get reference to the progress bar for external management"""
        return self.scan_progress

    def _setup_cache_status(self, layout: QVBoxLayout) -> None:
        """Set up cache status indicators"""
        try:
            settings_manager = self.settings_manager

            # Only show cache indicators if enabled in settings
            if not settings_manager.get("cache", "show_indicators", True):
                return
        except Exception:
            # If settings manager isn't available, default to showing cache indicators
            # This allows the dialog to work without full manager initialization
            pass

        # Cache status widget - CRITICAL FIX: Set proper parent for all widgets
        self.cache_status_widget = QWidget(parent=self)
        cache_layout = QHBoxLayout()
        cache_layout.setContentsMargins(0, SPACING_TINY, 0, 0)
        cache_layout.setSpacing(SPACING_COMPACT_SMALL)

        # Cache status label - set proper parent
        cache_label = QLabel("Cache:", parent=self.cache_status_widget)
        cache_label.setStyleSheet("font-weight: bold; font-size: 12px;")  # Readable font
        cache_layout.addWidget(cache_label)

        # Cache icon - set proper parent
        self.cache_icon_label = QLabel(parent=self.cache_status_widget)
        self.cache_icon_label.setStyleSheet("font-size: 12px;")  # Readable icon
        cache_layout.addWidget(self.cache_icon_label)

        # Cache info label - set proper parent
        self.cache_info_label = QLabel(parent=self.cache_status_widget)
        self.cache_info_label.setStyleSheet(get_muted_text_style() + " font-size: 11px;")  # Readable text
        cache_layout.addWidget(self.cache_info_label)

        # Add stretch to push content to left
        cache_layout.addStretch()

        self.cache_status_widget.setLayout(cache_layout)
        layout.addWidget(self.cache_status_widget)

        # Initialize cache status
        self._update_cache_status()

    def _update_cache_status(self) -> None:
        """Update cache status indicator"""
        # Ensure widget exists (standard check)
        if not self.cache_status_widget:
            return

        cache_enabled = True

        try:
            settings_manager = self.settings_manager
            cache_enabled = settings_manager.get_cache_enabled()

            if cache_enabled:
                try:
                    rom_cache = self.rom_cache
                    stats = rom_cache.get_cache_stats()

                    # Update icon
                    if self.cache_icon_label:
                        self.cache_icon_label.setText("✓")
                    if self.cache_icon_label:
                        self.cache_icon_label.setStyleSheet(f"color: {COLORS['success']}; font-weight: bold;")

                    # Update info
                    total_files = stats.get("total_files", 0)
                    size_bytes = stats.get("total_size_bytes", 0)
                    # Ensure size_bytes is an int for arithmetic
                    if isinstance(size_bytes, int):
                        size_mb = size_bytes / (1024 * 1024)
                    else:
                        size_mb = 0.0

                    if self.cache_info_label:
                        self.cache_info_label.setText(f"{total_files} items, {size_mb:.1f}MB")

                    # Update tooltip
                    sprite_caches = stats.get("sprite_location_caches", 0)
                    rom_caches = stats.get("rom_info_caches", 0)
                    scan_caches = stats.get("scan_progress_caches", 0)

                    tooltip = "ROM Cache Statistics:\n"
                    tooltip += f"Total items: {total_files}\n"
                    tooltip += f"- Sprite locations: {sprite_caches}\n"
                    tooltip += f"- ROM info: {rom_caches}\n"
                    tooltip += f"- Scan progress: {scan_caches}\n"
                    tooltip += f"Total size: {size_mb:.1f} MB"

                    self.cache_status_widget.setToolTip(tooltip)

                except Exception:
                    # Error getting stats
                    if self.cache_icon_label:
                        self.cache_icon_label.setText("⚠")
                    if self.cache_icon_label:
                        self.cache_icon_label.setStyleSheet(f"color: {COLORS['warning']}; font-weight: bold;")
                    if self.cache_info_label:
                        self.cache_info_label.setText("Error")
                    self.cache_status_widget.setToolTip("Error reading cache statistics")
            else:
                # Cache disabled
                if self.cache_icon_label:
                    self.cache_icon_label.setText("✗")
                if self.cache_icon_label:
                    self.cache_icon_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-weight: bold;")
                if self.cache_info_label:
                    self.cache_info_label.setText("Disabled")
                self.cache_status_widget.setToolTip("ROM caching is disabled")
        except Exception:
            # Import failed or settings manager error
            pass

    def update_cache_status(self) -> None:
        """Public method to update cache status (called externally)"""
        self._update_cache_status()
