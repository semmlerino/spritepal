"""Cache status controller for manual offset dialog.

Handles cache statistics tracking, status display, and cache management.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMessageBox, QWidget

if TYPE_CHECKING:
    from core.services.rom_cache import ROMCache
    from ui.common.collapsible_group_box import CollapsibleGroupBox

logger = logging.getLogger(__name__)


class CacheStatusController(QObject):
    """Manages cache status display and statistics for the manual offset dialog.

    Responsibilities:
    - Tracks cache hit/miss statistics for the session
    - Updates status display with cache information
    - Provides context menu for cache management
    - Handles cache clearing with confirmation

    Signals:
        status_updated: Emitted when cache status display should be updated.
            Args: status_text (str)
        cache_cleared: Emitted after cache has been cleared.
        stats_reset: Emitted when session stats are reset.
    """

    status_updated = Signal(str)
    cache_cleared = Signal()
    stats_reset = Signal()

    def __init__(
        self,
        rom_cache: ROMCache,
        parent_widget: QWidget,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the cache status controller.

        Args:
            rom_cache: ROM cache protocol instance for cache operations.
            parent_widget: Widget to use as parent for dialogs and menus.
            parent: QObject parent for ownership.
        """
        super().__init__(parent)
        self._rom_cache = rom_cache
        self._parent_widget = parent_widget
        self._status_collapsible: CollapsibleGroupBox | None = None
        self._adjacent_offsets_cache: set[int] = set()
        self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}

    @property
    def cache_stats(self) -> dict[str, int]:
        """Get the current cache statistics."""
        return self._cache_stats

    @property
    def adjacent_offsets_cache(self) -> set[int]:
        """Get the set of preloaded adjacent offsets."""
        return self._adjacent_offsets_cache

    def set_status_widget(self, collapsible: CollapsibleGroupBox | None) -> None:
        """Set the status widget for context menu attachment.

        Args:
            collapsible: The CollapsibleGroupBox to attach context menu to.
        """
        self._status_collapsible = collapsible
        if collapsible is not None:
            self._setup_context_menu()

    def initialize_for_rom(self, rom_path: str) -> None:
        """Initialize cache state for a new ROM.

        Resets session statistics and clears preloaded offsets.

        Args:
            rom_path: Path to the ROM file being opened.
        """
        try:
            # Reset cache stats for new ROM
            self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
            self._adjacent_offsets_cache.clear()

            # Log cache status
            if self._rom_cache.cache_enabled:
                logger.debug(f"ROM cache initialized for {Path(rom_path).name}")
            else:
                logger.debug("ROM cache is disabled")

            self.stats_reset.emit()

        except Exception as e:
            logger.warning(f"Error initializing ROM cache: {e}")

    def record_cache_hit(self) -> None:
        """Record a cache hit and update stats."""
        self._cache_stats["hits"] += 1

    def record_cache_miss(self) -> None:
        """Record a cache miss and update stats."""
        self._cache_stats["misses"] += 1

    def increment_total_requests(self) -> None:
        """Increment the total requests counter."""
        self._cache_stats["total_requests"] += 1

    def get_status_text(self) -> str:
        """Get cache status text for display.

        Returns:
            Status text showing cache state and hit rate.
        """
        if not self._rom_cache.cache_enabled:
            return "[Cache: Disabled]"

        total = self._cache_stats["total_requests"]
        hits = self._cache_stats["hits"]

        if total > 0:
            hit_rate = (hits / total) * 100
            return f"[Cache: {hit_rate:.0f}% hit rate]"

        return "[Cache: Ready]"

    def build_tooltip(self) -> str:
        """Build detailed cache tooltip.

        Returns:
            Multi-line tooltip text with cache details.
        """
        if not self._rom_cache.cache_enabled:
            return "ROM caching is disabled"

        try:
            stats = self._rom_cache.get_cache_stats()
            cache_info = [
                f"Cache Directory: {stats.get('cache_dir', 'Unknown')}",
                f"Total Cache Files: {stats.get('total_files', 0)}",
                f"Cache Size: {stats.get('total_size_bytes', 0)} bytes",
                "",
                "Session Stats:",
                f"  Total Requests: {self._cache_stats['total_requests']}",
                f"  Cache Hits: {self._cache_stats['hits']}",
                f"  Cache Misses: {self._cache_stats['misses']}",
            ]

            if self._cache_stats["total_requests"] > 0:
                hit_rate = (self._cache_stats["hits"] / self._cache_stats["total_requests"]) * 100
                cache_info.append(f"  Hit Rate: {hit_rate:.1f}%")

            return "\n".join(cache_info)

        except Exception as e:
            return f"Cache tooltip error: {e}"

    def update_status_display(self) -> None:
        """Update cache status in the UI.

        Updates the collapsible widget title with cache status if set.
        Emits status_updated signal with current status text.
        """
        try:
            cache_status = self.get_status_text()

            # Update status panel if collapsed box exists
            if self._status_collapsible and self._rom_cache.cache_enabled:
                # Update collapsible title to show cache status
                current_title = self._status_collapsible.title()
                if "[Cache:" not in current_title:
                    new_title = f"{current_title} {cache_status}"
                    self._status_collapsible.set_title(new_title)

            self.status_updated.emit(cache_status)

        except Exception as e:
            logger.debug(f"Error updating cache status display: {e}")

    def _setup_context_menu(self) -> None:
        """Set up context menu for cache management."""
        if self._status_collapsible is None:
            return

        try:
            # Enable context menu on the status collapsible widget
            self._status_collapsible.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._status_collapsible.customContextMenuRequested.connect(self._show_context_menu)

        except Exception as e:
            logger.debug(f"Error setting up cache context menu: {e}")

    def _show_context_menu(self, position: object) -> None:
        """Show cache management context menu.

        Args:
            position: QPoint position for menu display.
        """
        from PySide6.QtCore import QPoint

        if not self._rom_cache.cache_enabled:
            return

        try:
            menu = QMenu(self._parent_widget)

            # Cache statistics action
            stats_action = QAction("Show Cache Statistics", self._parent_widget)
            stats_action.triggered.connect(self.show_statistics_dialog)
            menu.addAction(stats_action)

            # Clear cache action
            clear_action = QAction("Clear Cache", self._parent_widget)
            clear_action.triggered.connect(self.clear_with_confirmation)
            menu.addAction(clear_action)

            # Show at cursor position
            if isinstance(position, QPoint):
                global_pos = (
                    self._status_collapsible.mapToGlobal(position)
                    if self._status_collapsible
                    else self._parent_widget.mapToGlobal(position)
                )
                menu.exec(global_pos)

        except Exception as e:
            logger.debug(f"Error showing cache context menu: {e}")

    def show_statistics_dialog(self) -> None:
        """Show detailed cache statistics dialog."""
        try:
            stats = self._rom_cache.get_cache_stats()
            session_stats = self._cache_stats

            # Format cache size
            size_bytes_val = stats.get("total_size_bytes", 0)
            size_bytes = int(size_bytes_val) if isinstance(size_bytes_val, int | float) else 0
            if size_bytes > 1024 * 1024:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
            elif size_bytes > 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes} bytes"

            message = f"""Cache Statistics:

Directory: {stats.get("cache_dir", "Unknown")}
Total Files: {stats.get("total_files", 0)}
Total Size: {size_str}
Sprite Location Caches: {stats.get("sprite_location_caches", 0)}
ROM Info Caches: {stats.get("rom_info_caches", 0)}
Scan Progress Caches: {stats.get("scan_progress_caches", 0)}

Session Statistics:
Total Requests: {session_stats["total_requests"]}
Cache Hits: {session_stats["hits"]}
Cache Misses: {session_stats["misses"]}"""

            if session_stats["total_requests"] > 0:
                hit_rate = (session_stats["hits"] / session_stats["total_requests"]) * 100
                message += f"\nHit Rate: {hit_rate:.1f}%"

            QMessageBox.information(self._parent_widget, "ROM Cache Statistics", message)

        except Exception as e:
            QMessageBox.warning(self._parent_widget, "Error", f"Failed to retrieve cache statistics: {e}")

    def clear_with_confirmation(self) -> None:
        """Clear cache with user confirmation."""
        try:
            reply = QMessageBox.question(
                self._parent_widget,
                "Clear Cache",
                "Are you sure you want to clear the ROM cache?\n\nThis will remove all cached data and may slow down future operations.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                removed_count = self._rom_cache.clear_cache()
                QMessageBox.information(
                    self._parent_widget,
                    "Cache Cleared",
                    f"Successfully cleared {removed_count} cache files.",
                )

                # Reset session stats
                self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
                self._adjacent_offsets_cache.clear()

                # Update status display
                self.update_status_display()
                self.cache_cleared.emit()

        except Exception as e:
            QMessageBox.warning(self._parent_widget, "Error", f"Failed to clear cache: {e}")

    def cleanup(self) -> None:
        """Clean up resources.

        Call this before the parent dialog is destroyed.
        """
        self._cache_stats.clear()
        self._adjacent_offsets_cache.clear()
        self._status_collapsible = None
        logger.debug("CacheStatusController cleaned up")
