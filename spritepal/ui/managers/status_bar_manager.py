"""
Status bar management for MainWindow
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QHBoxLayout, QLabel, QStatusBar, QWidget

from ui.styles import get_muted_text_style
from ui.styles.theme import COLORS

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ApplicationStateManagerProtocol, ROMCacheProtocol


logger = logging.getLogger(__name__)

class StatusBarManager:
    """Manages status bar and cache indicators for MainWindow"""

    def __init__(self, status_bar: QStatusBar,
                 settings_manager: ApplicationStateManagerProtocol,
                 rom_cache: ROMCacheProtocol) -> None:
        """Initialize status bar manager

        Args:
            status_bar: The status bar widget to manage
            settings_manager: Injected ApplicationStateManagerProtocol instance
            rom_cache: Injected ROMCacheProtocol instance
        """
        self.status_bar = status_bar
        self.settings_manager = settings_manager
        self.rom_cache = rom_cache

        # Cache status widgets (initialized by setup if enabled)
        self.cache_status_widget: QWidget | None = None
        self.cache_icon_label: QLabel | None = None
        self.cache_info_label: QLabel | None = None
        self.cache_operation_badge: QLabel | None = None

    def setup_status_bar_indicators(self) -> None:
        """Set up permanent status bar indicators"""

        settings_manager = self.settings_manager

        # Only show indicators if enabled in settings
        if not settings_manager.get("cache", "show_indicators", True):
            return

        # Cache status widget
        self.cache_status_widget = QWidget()
        cache_layout = QHBoxLayout()
        cache_layout.setContentsMargins(0, 0, 0, 0)
        cache_layout.setSpacing(4)

        # Cache icon
        self.cache_icon_label = QLabel()
        self.cache_icon_label.setToolTip("ROM cache status")
        cache_layout.addWidget(self.cache_icon_label)

        # Cache info label
        self.cache_info_label = QLabel()
        if self.cache_info_label:
            self.cache_info_label.setStyleSheet(get_muted_text_style())
        cache_layout.addWidget(self.cache_info_label)

        # Cache operation badge (hidden by default)
        self.cache_operation_badge = QLabel()
        if self.cache_operation_badge:
            self.cache_operation_badge.setStyleSheet(
            f"background-color: {COLORS['info']}; color: {COLORS['text_primary']}; padding: 2px 6px; "
            "border-radius: 3px; font-size: 10px; font-weight: bold;"
        )
        self.cache_operation_badge.setVisible(False)
        cache_layout.addWidget(self.cache_operation_badge)

        self.cache_status_widget.setLayout(cache_layout)

        # Add to status bar as permanent widget
        self.status_bar.addPermanentWidget(self.cache_status_widget)

        # Update cache status
        self.update_cache_status()

    def update_cache_status(self) -> None:
        """Update cache status indicator"""

        settings_manager = self.settings_manager

        # Check if indicators are enabled and created
        if (not self.cache_status_widget or
            not settings_manager.get("cache", "show_indicators", True)):
            return

        # Check if cache is enabled
        cache_enabled = settings_manager.get_cache_enabled()

        if cache_enabled:
            # Get cache stats
            try:
                rom_cache = self.rom_cache
                stats = rom_cache.get_cache_stats()

                # Update icon (✓ for enabled, ✗ for disabled)
                if self.cache_icon_label is not None:
                    self.cache_icon_label.setText("✓ Cache:")
                    self.cache_icon_label.setStyleSheet("color: green;")

                # Update info
                total_files = stats.get("total_files", 0)
                size_bytes = stats.get("total_size_bytes", 0)
                # Ensure size_bytes is an int for arithmetic
                if isinstance(size_bytes, int):
                    size_mb = size_bytes / (1024 * 1024)
                else:
                    size_mb = 0.0

                if self.cache_info_label is not None:
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

                # cache_status_widget is guaranteed non-None by early return check
                self.cache_status_widget.setToolTip(tooltip)

            except (OSError, PermissionError) as e:
                logger.warning(f"File I/O error getting cache stats: {e}")
                if self.cache_icon_label is not None:
                    self.cache_icon_label.setText("⚠ Cache:")
            except Exception as e:
                logger.warning(f"Error getting cache stats: {e}")
                if self.cache_icon_label is not None:
                    self.cache_icon_label.setText("⚠ Cache:")
                    self.cache_icon_label.setStyleSheet("color: orange;")
                if self.cache_info_label is not None:
                    self.cache_info_label.setText("Error")
                # cache_status_widget is guaranteed non-None by early return check
                self.cache_status_widget.setToolTip("Error reading cache statistics")
        else:
            # Cache disabled
            if self.cache_icon_label is not None:
                self.cache_icon_label.setText("✗ Cache:")
                self.cache_icon_label.setStyleSheet("color: gray;")
            if self.cache_info_label is not None:
                self.cache_info_label.setText("Disabled")
            # cache_status_widget is guaranteed non-None by early return check
            self.cache_status_widget.setToolTip("ROM caching is disabled")

    def show_cache_operation_badge(self, operation: str) -> None:
        """Show cache operation badge in status bar

        Args:
            operation: Operation description (e.g., "Loading", "Saving", "Reading")
        """
        if self.cache_operation_badge is not None:
            self.cache_operation_badge.setText(operation)
            self.cache_operation_badge.setVisible(True)

    def hide_cache_operation_badge(self) -> None:
        """Hide cache operation badge"""
        if self.cache_operation_badge is not None:
            self.cache_operation_badge.setVisible(False)

    def show_message(self, message: str, timeout: int = 0) -> None:
        """Show message in status bar

        Args:
            message: Message to display
            timeout: Timeout in milliseconds (0 for permanent)
        """
        if timeout:
            self.status_bar.showMessage(message, timeout)
        else:
            self.status_bar.showMessage(message)

    def clear_message(self) -> None:
        """Clear status bar message"""
        self.status_bar.clearMessage()

    def remove_cache_indicators(self) -> None:
        """Remove cache indicators from status bar"""
        if self.cache_status_widget is not None:
            self.status_bar.removeWidget(self.cache_status_widget)
            self.cache_status_widget.deleteLater()
            self.cache_status_widget = None
            self.cache_icon_label = None
            self.cache_info_label = None
            self.cache_operation_badge = None
