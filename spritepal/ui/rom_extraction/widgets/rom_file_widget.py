"""ROM file selector widget for ROM extraction"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout

from ui.styles.theme import COLORS
from utils.logging_config import get_logger

# from utils.rom_cache import get_rom_cache # Removed due to DI
from .base_widget import BaseExtractionWidget

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ROMCacheProtocol

logger = get_logger(__name__)

# UI Spacing Constants (imported from centralized module)
from ui.common.spacing_constants import (
    CONTROL_PANEL_BUTTON_WIDTH,
    EXTRACTION_BUTTON_MIN_HEIGHT as BUTTON_MIN_HEIGHT,
    SPACING_COMPACT_MEDIUM as SPACING_MEDIUM,
)


class ROMFileWidget(BaseExtractionWidget):
    """Widget for selecting and displaying ROM file information"""

    # Signals
    browse_clicked = Signal()  # Emitted when browse button clicked
    cache_status_changed = Signal(dict)  # Emitted when cache status changes
    partial_scan_detected = Signal(dict)  # Emitted when partial scan cache found

    def __init__(self, parent: Any | None = None, rom_cache: ROMCacheProtocol | None = None):
        super().__init__(parent)
        self._rom_path = ""
        self._cache_status = {"has_cache": False, "cache_type": None}

        # Inject rom_cache or use fallback
        if rom_cache is None:
            from core.di_container import inject
            from core.protocols.manager_protocols import ROMCacheProtocol
            self._rom_cache = inject(ROMCacheProtocol)
        else:
            self._rom_cache = rom_cache

        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface"""
        rom_layout = QVBoxLayout()
        rom_layout.setSpacing(SPACING_MEDIUM)
        rom_layout.setContentsMargins(0, 0, 0, 0)  # Group box CSS provides padding

        # ROM path row with simple horizontal layout
        rom_row = QHBoxLayout()
        rom_row.setSpacing(SPACING_MEDIUM)

        self.rom_path_edit = QLineEdit()
        self.rom_path_edit.setPlaceholderText("Select ROM file...")
        self.rom_path_edit.setReadOnly(True)
        self.rom_path_edit.setMinimumWidth(250)
        rom_row.addWidget(self.rom_path_edit, 1)  # Stretch factor 1

        self.browse_rom_btn = QPushButton("Browse...")
        self.browse_rom_btn.setMinimumHeight(BUTTON_MIN_HEIGHT)
        self.browse_rom_btn.setFixedWidth(CONTROL_PANEL_BUTTON_WIDTH)
        _ = self.browse_rom_btn.clicked.connect(self.browse_clicked.emit)
        rom_row.addWidget(self.browse_rom_btn)

        rom_layout.addLayout(rom_row)

        # ROM info display (shows ROM details after loading)
        self.rom_info_label = QLabel()
        self.rom_info_label.setWordWrap(True)
        rom_layout.addWidget(self.rom_info_label)

        # Loading progress bar (hidden by default)
        self.loading_progress = QProgressBar()
        self.loading_progress.setRange(0, 0)  # Indeterminate mode
        self.loading_progress.setTextVisible(False)
        self.loading_progress.setMaximumHeight(4)
        self.loading_progress.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: {COLORS["input_background"]};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS["border_focus"]};
                border-radius: 2px;
            }}
        """)
        self.loading_progress.hide()
        rom_layout.addWidget(self.loading_progress)

        self._setup_widget_with_group("ROM File", rom_layout)

    def _set_empty_state_guidance(self) -> None:
        """Show simple guidance when no ROM is loaded, with detailed tooltip"""
        if self.rom_info_label:
            self.rom_info_label.setText(
                f'<span style="color: {COLORS["text_muted"]};">Select ROM file to begin</span>'
            )
            self.rom_info_label.setToolTip(
                "Getting Started:\n"
                "1. Click Browse to select a SNES ROM file\n"
                "2. Choose a preset sprite or explore manually\n"
                "3. Click Extract to begin"
            )

    def set_rom_path(self, path: str):
        """Set the ROM path display"""
        self._rom_path = path
        if self.rom_path_edit:
            self.rom_path_edit.setText(path)
        # Check cache status when ROM is set
        if path:
            self._check_cache_status()

    def set_info_text(self, html: str):
        """Set the ROM info display text (supports HTML)"""
        # Append cache status if available
        if self._cache_status["has_cache"]:
            cache_html = self._get_cache_status_html()
            # Insert cache status before the closing tags if they exist
            if "</span>" in html:
                parts = html.rsplit("</span>", 1)
                html = parts[0] + "</span><br>" + cache_html + (parts[1] if len(parts) > 1 else "")
            else:
                html += "<br>" + cache_html
        if self.rom_info_label:
            self.rom_info_label.setText(html)
            self.rom_info_label.setToolTip("")  # Clear getting started tooltip

    def show_loading(self, message: str = "Loading ROM header..."):
        """Show loading indicator with optional message.

        Args:
            message: Loading message to display
        """
        if hasattr(self, "loading_progress"):
            self.loading_progress.show()
        if self.rom_info_label:
            self.rom_info_label.setText(f'<span style="color: {COLORS["info"]};">{message}</span>')

    def hide_loading(self):
        """Hide loading indicator."""
        if hasattr(self, "loading_progress"):
            self.loading_progress.hide()

    def clear(self):
        """Clear the ROM selection"""
        self._rom_path = ""
        self._cache_status = {"has_cache": False, "cache_type": None}
        if self.rom_path_edit:
            self.rom_path_edit.clear()
        if self.rom_info_label:
            self.rom_info_label.setText("")
            self.rom_info_label.setToolTip("")

    def _check_cache_status(self):
        """Check cache status for the current ROM"""
        if not self._rom_path or not self._rom_cache.cache_enabled:
            self._cache_status = {"has_cache": False, "cache_type": None}
            return

        # Check for different types of cache
        has_sprite_cache = False
        has_scan_cache = False
        partial_scan_data = None
        sprite_locations = None
        partial_scan = None

        try:
            # Check sprite locations cache
            sprite_locations = self._rom_cache.get_sprite_locations(self._rom_path)
            if sprite_locations:
                has_sprite_cache = True

            # Check for partial scan cache (must match SpriteScanWorker params)
            scan_params = {
                "start_offset": 0xC0000,
                "end_offset": 0xF0000,
                "alignment": 0x100
            }
            partial_scan = self._rom_cache.get_partial_scan_results(self._rom_path, scan_params)
            if partial_scan:
                has_scan_cache = True
                partial_scan_data = partial_scan

                # Emit partial scan signal if scan is incomplete
                if not partial_scan.get("completed", False):
                    self.partial_scan_detected.emit(partial_scan)

        except Exception as e:
            # Log the error but don't crash the UI
            logger.warning(f"Cache check failed: {e}")

        self._cache_status = {
            "has_cache": has_sprite_cache or has_scan_cache,
            "has_sprite_cache": has_sprite_cache,
            "has_scan_cache": has_scan_cache,
            "sprite_count": len(sprite_locations) if sprite_locations else 0,
            "partial_scan_data": partial_scan_data
        }

        # Emit signal if cache status changed
        self.cache_status_changed.emit(self._cache_status)

    def _get_cache_status_html(self) -> str:
        """Generate HTML for cache status indicator"""
        if not self._cache_status["has_cache"]:
            return ""

        cache_parts = []

        if self._cache_status.get("has_sprite_cache"):
            count = self._cache_status.get("sprite_count", 0)
            cache_parts.append(f'<span style="color: {COLORS["border_focus"]};">💾 {count} sprites cached</span>')

        if self._cache_status.get("has_scan_cache"):
            cache_parts.append(f'<span style="color: {COLORS["success"]};">📊 Partial scan cached</span>')

        return " | ".join(cache_parts) if cache_parts else ""

    def get_cache_status(self) -> dict[str, Any]:
        """Get the current cache status"""
        return self._cache_status.copy()

    def refresh_cache_status(self):
        """Refresh cache status and update display"""
        if self._rom_path:
            self._check_cache_status()
            # Re-set the info text to update cache display
            current_text = self.rom_info_label.text()
            # Remove old cache info if present
            if "💾" in current_text or "📊" in current_text:
                # Find where cache info starts
                parts = current_text.split("<br>")
                # Remove cache parts
                parts = [p for p in parts if "💾" not in p and "📊" not in p]
                current_text = "<br>".join(parts)
            # Set text again to add updated cache info
            self.set_info_text(current_text)
