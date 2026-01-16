"""
Recent Captures Widget for Mesen2 sprite offset discovery.

Displays a list of recently discovered ROM offsets from Mesen2's sprite_rom_finder.lua,
allowing users to quickly jump to discovered sprites without manual copy-paste.
"""

from __future__ import annotations

import logging
from typing import override

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from core.mesen_integration.log_watcher import CapturedOffset
from ui.common.spacing_constants import SPACING_SMALL, SPACING_TINY
from ui.common.widget_helpers import create_styled_label
from ui.styles import get_panel_style
from ui.styles.theme import COLORS

logger = logging.getLogger(__name__)


class CaptureThumbnailDelegate(QStyledItemDelegate):
    """Delegate for rendering thumbnails in the captures list."""

    THUMBNAIL_SIZE = 96
    ITEM_PADDING = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the thumbnail delegate."""
        super().__init__(parent)
        self._placeholder_bg = QColor(COLORS["darker_gray"])
        self._placeholder_grid = QColor(COLORS["border"])

    @override
    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        """Paint the list item with thumbnail."""
        # Let default paint handle selection/hover effects
        super().paint(painter, option, index)

        # Get item data
        item_data = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(item_data, dict):
            return

        painter.save()

        # Calculate thumbnail rectangle (left side of item)
        item_rect = option.rect  # type: ignore[attr-defined]
        thumbnail_rect = QRect(
            item_rect.x() + self.ITEM_PADDING,
            item_rect.y() + self.ITEM_PADDING,
            self.THUMBNAIL_SIZE,
            self.THUMBNAIL_SIZE,
        )

        # Draw thumbnail or placeholder
        thumbnail = item_data.get("thumbnail")
        if thumbnail and isinstance(thumbnail, QPixmap) and not thumbnail.isNull():
            # Scale to fit
            scaled = thumbnail.scaled(
                thumbnail_rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Center in rectangle
            x = thumbnail_rect.x() + (thumbnail_rect.width() - scaled.width()) // 2
            y = thumbnail_rect.y() + (thumbnail_rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            # Draw placeholder
            self._draw_placeholder(painter, thumbnail_rect)

        painter.restore()

    def _draw_placeholder(self, painter: QPainter, rect: QRect) -> None:
        """Draw a placeholder for items without thumbnails."""
        # Fill background
        painter.fillRect(rect, self._placeholder_bg)

        # Draw border
        painter.setPen(QPen(self._placeholder_grid, 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        # Draw grid pattern
        grid_size = 8
        for x in range(rect.x(), rect.right(), grid_size):
            painter.drawLine(x, rect.y(), x, rect.bottom())
        for y in range(rect.y(), rect.bottom(), grid_size):
            painter.drawLine(rect.x(), y, rect.right(), y)

    @override
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        """Return size hint for the item."""
        base_size = super().sizeHint(option, index)
        # Ensure enough height for thumbnail + padding
        min_height = self.THUMBNAIL_SIZE + 2 * self.ITEM_PADDING
        return QSize(base_size.width(), max(base_size.height(), min_height))


class RecentCapturesWidget(QWidget):
    """
    Widget displaying recently discovered sprite ROM offsets from Mesen2.

    Shows a list of offsets with timestamps. Users can:
    - Single-click to select and preview offset
    - Double-click to jump directly to offset in ROM browser
    - Right-click for context menu (copy, save to library)

    Signals:
        offset_selected: Emitted when user selects an offset.
                        Args: (offset: int)
        offset_activated: Emitted when user double-clicks an offset.
                         Args: (offset: int)
        save_to_library_requested: Emitted when user requests to save offset.
                                   Args: (offset: int)
    """

    offset_selected = Signal(int)
    offset_activated = Signal(int)
    save_to_library_requested = Signal(int)
    thumbnail_requested = Signal(int)  # Emitted when a capture needs a thumbnail

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(get_panel_style())

        self._captures: list[CapturedOffset] = []
        self._max_items: int = 20
        self._smc_offset: int = 0  # SMC header offset for normalizing Mesen FILE offsets

        self._setup_ui()
        self._connect_signals()

    def set_smc_offset(self, offset: int) -> None:
        """Set the SMC header offset and re-normalize existing captures.

        When the SMC offset changes (e.g., loading a new ROM), all existing
        captures must be re-normalized because their stored ROM offsets are
        based on the old SMC offset.

        Args:
            offset: SMC header size in bytes (typically 0 or 512).
        """
        if self._smc_offset == offset:
            return  # No change needed

        old_smc_offset = self._smc_offset
        self._smc_offset = offset
        logger.debug("SMC offset changed from %d to %d bytes", old_smc_offset, offset)

        # Re-normalize all existing captures with the new SMC offset
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            item_data = item.data(Qt.ItemDataRole.UserRole)

            if isinstance(item_data, dict):
                # Get the original FILE offset (never changes)
                file_offset = item_data.get("file_offset")

                # If file_offset is not stored (backward compat), try to get it from "offset"
                if file_offset is None:
                    # Old item format - "offset" contains ROM offset from old SMC context
                    # We can't recover the FILE offset, so we'll use current "offset" as approximation
                    # This is a fallback for backward compatibility
                    file_offset = item_data.get("offset")
                    if file_offset is not None:
                        # Denormalize to FILE offset using old SMC offset
                        if old_smc_offset > 0:
                            file_offset = file_offset + old_smc_offset

                if file_offset is not None:
                    # Re-normalize to ROM offset with new SMC offset
                    rom_offset = self._normalize_offset(file_offset)

                    # Update stored offsets
                    item_data["file_offset"] = file_offset
                    item_data["rom_offset"] = rom_offset
                    item_data["offset"] = rom_offset  # Keep backward compat field in sync
                    item.setData(Qt.ItemDataRole.UserRole, item_data)

                    # Update tooltip with new ROM offset
                    item.setToolTip(
                        f"ROM Offset: 0x{rom_offset:06X}\n"
                        f"Mesen FILE: 0x{file_offset:06X}\n"
                        f"Frame: N/A\n"
                        f"SMC Offset: {self._smc_offset} bytes"
                    )

                    logger.debug(
                        "Re-normalized capture: FILE 0x%06X -> ROM 0x%06X (SMC: %d bytes)",
                        file_offset,
                        rom_offset,
                        self._smc_offset,
                    )

        # Re-request all thumbnails with corrected offsets
        # This ensures thumbnails use the new normalized offsets
        self.request_all_thumbnails()

    def _normalize_offset(self, offset: int) -> int:
        """Normalize a Mesen FILE offset to a ROM offset (headerless).

        Args:
            offset: Raw offset from Mesen (FILE offset).

        Returns:
            Normalized ROM offset.
        """
        if self._smc_offset <= 0 or offset < self._smc_offset:
            return offset
        return offset - self._smc_offset

    def _setup_ui(self) -> None:
        """Initialize the widget UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)
        layout.setSpacing(SPACING_TINY)

        # Header with title and status indicator
        header_layout = QHBoxLayout()
        header_layout.setSpacing(SPACING_TINY)

        title_label = create_styled_label("Mesen2 Captures", style="section", parent=self)
        header_layout.addWidget(title_label)

        self._status_indicator = QLabel(parent=self)
        self._status_indicator.setFixedSize(8, 8)
        self._update_status_indicator(watching=False)
        header_layout.addWidget(self._status_indicator)

        header_layout.addStretch()

        self._clear_btn = QPushButton("Clear", parent=self)
        self._clear_btn.setFixedWidth(50)
        self._clear_btn.setToolTip("Clear all captured offsets")
        header_layout.addWidget(self._clear_btn)

        layout.addLayout(header_layout)

        # List widget for captures
        self._list_widget = QListWidget(parent=self)
        self._list_widget.setAlternatingRowColors(True)
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_widget.setMinimumHeight(100)

        # Set custom delegate for thumbnail rendering
        self._delegate = CaptureThumbnailDelegate(self._list_widget)
        self._list_widget.setItemDelegate(self._delegate)

        # Style the list - add left padding for thumbnail area
        thumbnail_padding = CaptureThumbnailDelegate.THUMBNAIL_SIZE + 2 * CaptureThumbnailDelegate.ITEM_PADDING + 8
        self._list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLORS["background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                font-family: monospace;
                font-size: 12px;
            }}
            QListWidget::item {{
                padding: 4px 8px 4px {thumbnail_padding}px;
            }}
            QListWidget::item:selected {{
                background-color: {COLORS["accent"]};
                color: {COLORS["background"]};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {COLORS["panel_background"]};
            }}
        """)

        layout.addWidget(self._list_widget)

        # Empty state message
        self._empty_label = QLabel("No captures yet.\nStart Mesen2 with sprite_rom_finder.lua", parent=self)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        self._update_empty_state()

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._list_widget.itemClicked.connect(self._on_item_clicked)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self._clear_btn.clicked.connect(self.clear)

    def add_capture(self, capture: CapturedOffset, request_thumbnail: bool = True) -> None:
        """
        Add a new captured offset to the list.

        Args:
            capture: The captured offset from LogWatcher.
            request_thumbnail: If True, emit thumbnail_requested signal.
        """
        # Insert at beginning (most recent first)
        self._captures.insert(0, capture)

        # Store both FILE and ROM offsets
        # Mesen reports FILE offsets; we need ROM offsets for decompression
        file_offset = capture.offset
        rom_offset = self._normalize_offset(file_offset)

        # Create list item with dict data for delegate
        item = QListWidgetItem()
        item_data = {
            "file_offset": file_offset,  # Original FILE offset from Mesen
            "rom_offset": rom_offset,  # Normalized ROM offset for decompression
            "offset": rom_offset,  # Keep for backward compatibility
            "thumbnail": None,  # Will be set later via set_thumbnail
        }
        item.setData(Qt.ItemDataRole.UserRole, item_data)

        # Format: "0x3C6EF1  12:34:56" - display shows original Mesen FILE offset
        time_str = capture.timestamp.strftime("%H:%M:%S")
        frame_str = f" (f{capture.frame})" if capture.frame else ""
        item.setText(f"{capture.offset_hex}  {time_str}{frame_str}")
        item.setToolTip(
            f"ROM Offset: 0x{rom_offset:06X}\nMesen FILE: {capture.offset_hex}\nFrame: {capture.frame or 'N/A'}\n{capture.raw_line}"
        )

        self._list_widget.insertItem(0, item)

        # Trim excess items
        while self._list_widget.count() > self._max_items:
            self._list_widget.takeItem(self._list_widget.count() - 1)
            if len(self._captures) > self._max_items:
                self._captures.pop()

        self._update_empty_state()
        logger.debug("Added capture: %s (ROM: 0x%06X)", capture.offset_hex, rom_offset)

        # Request thumbnail generation with normalized ROM offset
        if request_thumbnail:
            self.thumbnail_requested.emit(rom_offset)

    def load_persistent(self, captures: list[CapturedOffset]) -> None:
        """
        Load persistent captures from file.

        This is called on startup to restore the last 5 clicked sprites
        from previous Mesen2 sessions.

        Args:
            captures: List of captured offsets to load.
        """
        if not captures:
            return

        logger.debug("Loading %d persistent captures", len(captures))

        # Add each capture (they're already sorted by recency)
        for capture in captures:
            # Avoid duplicates
            if any(c.offset == capture.offset for c in self._captures):
                continue
            self.add_capture(capture)

    def set_watching(self, watching: bool) -> None:
        """Update the status indicator to show whether log is being watched."""
        self._update_status_indicator(watching)

    def clear(self) -> None:
        """Clear all captured offsets."""
        self._list_widget.clear()
        self._captures.clear()
        self._update_empty_state()
        logger.debug("Cleared captures list")

    def get_selected_offset(self) -> int | None:
        """Get the currently selected offset, if any."""
        current_item = self._list_widget.currentItem()
        if current_item is not None:  # type: ignore[reportUnnecessaryComparison]
            data = current_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                return data.get("offset")
            # Legacy: direct int storage
            return data
        return None

    def set_thumbnail(self, offset: int, thumbnail: QPixmap) -> None:
        """
        Set or update the thumbnail for a capture.

        Args:
            offset: ROM offset to match
            thumbnail: Thumbnail pixmap to display
        """
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item is None:  # type: ignore[reportUnnecessaryComparison]
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("offset") == offset:
                data["thumbnail"] = thumbnail
                item.setData(Qt.ItemDataRole.UserRole, data)
                # Force repaint
                self._list_widget.viewport().update()
                logger.debug("Set thumbnail for offset 0x%06X", offset)
                return

    def request_all_thumbnails(self) -> None:
        """Request thumbnails for all current captures using normalized ROM offsets."""
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item is None:  # type: ignore[reportUnnecessaryComparison]
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                rom_offset = data.get("offset")
                if rom_offset is not None:
                    self.thumbnail_requested.emit(rom_offset)

    def get_capture_count(self) -> int:
        """Get the number of captured offsets."""
        return self._list_widget.count()

    def has_capture(self, offset: int) -> bool:
        """Check if a specific offset is already in the list.

        Args:
            offset: The offset to check.

        Returns:
            True if present, False otherwise.
        """
        return any(c.offset == offset for c in self._captures)

    def update_capture_offset(self, old_rom_offset: int, new_rom_offset: int) -> bool:
        """Update a capture's offset after HAL alignment adjustment.

        When the preview worker discovers a sprite at an adjusted offset
        (e.g., due to HAL compression alignment), this method updates both
        the display text and internal data to reflect the corrected offset.

        Args:
            old_rom_offset: Original ROM offset (headerless) before alignment
            new_rom_offset: Adjusted ROM offset (headerless) after alignment

        Returns:
            True if an item was found and updated, False otherwise.
        """
        # Find the capture with matching ROM offset in the list widget
        # Items are in reverse order (most recent first), matching self._captures order
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            item_data = item.data(Qt.ItemDataRole.UserRole)

            if isinstance(item_data, dict) and item_data.get("rom_offset") == old_rom_offset:
                # Found the item to update
                # Update the stored ROM offset in item data
                item_data["rom_offset"] = new_rom_offset
                item_data["offset"] = new_rom_offset  # Keep backward compat field in sync
                # FILE offset stays unchanged - it's the original capture point
                item.setData(Qt.ItemDataRole.UserRole, item_data)

                # Also update the underlying _captures list
                # Note: _captures is in reverse order (most recent at index 0)
                captures_index = self._list_widget.count() - 1 - i
                if captures_index < len(self._captures):
                    file_offset = self._captures[captures_index].offset
                    # Create updated CapturedOffset (frozen dataclass, so must replace)
                    updated_capture = CapturedOffset(
                        offset=new_rom_offset,  # Update FILE offset to the adjusted value
                        frame=self._captures[captures_index].frame,
                        timestamp=self._captures[captures_index].timestamp,
                        raw_line=self._captures[captures_index].raw_line,
                        rom_checksum=self._captures[captures_index].rom_checksum,
                    )
                    self._captures[captures_index] = updated_capture

                # Update display text: replace old ROM offset hex with new
                old_hex = f"0x{old_rom_offset:06X}"
                new_hex = f"0x{new_rom_offset:06X}"
                current_text = item.text()
                # Try exact replacement first (case-sensitive)
                if old_hex in current_text:
                    new_text = current_text.replace(old_hex, new_hex)
                elif old_hex.lower() in current_text.lower():
                    # Case-insensitive replacement
                    import re

                    new_text = re.sub(re.escape(old_hex), new_hex, current_text, flags=re.IGNORECASE)
                else:
                    # Offset not found in display text (display shows FILE offset, not ROM)
                    # In this case, don't change the display text
                    new_text = current_text
                item.setText(new_text)

                # Update tooltip with new ROM offset
                item_data_dict = item.data(Qt.ItemDataRole.UserRole)
                file_offset = item_data_dict.get("file_offset", 0)
                item.setToolTip(
                    f"ROM Offset: 0x{new_rom_offset:06X}\n"
                    f"Mesen FILE: 0x{file_offset:06X}\n"
                    f"Frame: N/A\n"  # Frame is not tracked through alignment adjustment
                    f"(Adjusted from 0x{old_rom_offset:06X})"
                )

                logger.debug("Updated capture ROM offset: 0x%06X -> 0x%06X", old_rom_offset, new_rom_offset)
                return True

        return False

    def _update_status_indicator(self, watching: bool) -> None:
        """Update the status indicator color."""
        color = COLORS["success"] if watching else COLORS["text_secondary"]
        self._status_indicator.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 4px;
            }}
        """)
        self._status_indicator.setToolTip("Watching log file" if watching else "Not watching")

    def _update_empty_state(self) -> None:
        """Show/hide empty state message based on list contents."""
        has_items = self._list_widget.count() > 0
        self._list_widget.setVisible(has_items)
        self._empty_label.setVisible(not has_items)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle single-click on list item."""
        data = item.data(Qt.ItemDataRole.UserRole)
        offset = data.get("offset") if isinstance(data, dict) else data
        if offset is not None:
            self.offset_selected.emit(offset)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on list item."""
        data = item.data(Qt.ItemDataRole.UserRole)
        offset = data.get("offset") if isinstance(data, dict) else data
        if offset is not None:
            self.offset_activated.emit(offset)

    def _show_context_menu(self, position: QPoint) -> None:
        """Show context menu for list item."""
        item = self._list_widget.itemAt(position)
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        offset = data.get("offset") if isinstance(data, dict) else data
        if offset is None:
            return

        menu = QMenu(self)

        copy_action = QAction("Copy Offset", self)
        copy_action.triggered.connect(lambda: self._copy_offset(offset))
        menu.addAction(copy_action)

        jump_action = QAction("Jump to Offset", self)
        jump_action.triggered.connect(lambda: self.offset_activated.emit(offset))
        menu.addAction(jump_action)

        menu.addSeparator()

        save_action = QAction("Save to Library...", self)
        save_action.triggered.connect(lambda: self.save_to_library_requested.emit(offset))
        menu.addAction(save_action)

        menu.exec(self._list_widget.mapToGlobal(position))

    def _copy_offset(self, offset: int) -> None:
        """Copy offset to clipboard."""
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:  # type: ignore[reportUnnecessaryComparison]
            clipboard.setText(f"0x{offset:06X}")
            logger.debug("Copied offset to clipboard: 0x%06X", offset)
