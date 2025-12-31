"""Sprite search coordinator for manual offset dialog.

Handles sprite search and ROM scanning operations with worker management.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QMutex, QMutexLocker, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.common import WorkerManager
from ui.rom_extraction.workers import SpriteSearchWorker
from ui.rom_extraction.workers.scan_worker import SpriteScanWorker

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache

logger = logging.getLogger(__name__)


class SpriteSearchCoordinator(QObject):
    """Coordinates sprite search and ROM scanning operations.

    Responsibilities:
    - Manages navigation search workers (find next/prev sprite)
    - Manages full ROM scan workers
    - Handles progress dialog for scans
    - Emits signals for found sprites and status updates

    Signals:
        sprite_found: Emitted when a sprite is found during navigation search.
            Args: offset (int), quality (float)
        search_complete: Emitted when navigation search completes.
            Args: found (bool)
        scan_complete: Emitted when full ROM scan completes.
            Args: sprites (list[dict])
        status_message: Emitted for status bar updates.
            Args: message (str)
        offset_requested: Emitted to request offset change.
            Args: offset (int)
    """

    sprite_found = Signal(int, float)  # offset, quality
    search_complete = Signal(bool)  # found
    scan_complete = Signal(list)  # sprites
    status_message = Signal(str)
    offset_requested = Signal(int)

    def __init__(
        self,
        parent_widget: QWidget,
        rom_cache: ROMCache,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the sprite search coordinator.

        Args:
            parent_widget: Widget to use as parent for dialogs.
            rom_cache: ROM cache protocol instance for scan caching.
            parent: QObject parent for ownership.
        """
        super().__init__(parent)
        self._parent_widget = parent_widget
        self._rom_cache = rom_cache
        self._manager_mutex = QMutex()

        # Worker references
        self._search_worker: SpriteSearchWorker | None = None
        self._scan_worker: SpriteScanWorker | None = None
        self._scan_progress_dialog: QProgressDialog | None = None

        # ROM data (set via set_rom_data)
        self._rom_path: str = ""
        self._rom_size: int = 0
        self._rom_extractor: ROMExtractor | None = None

    def set_rom_data(
        self,
        rom_path: str,
        rom_size: int,
        rom_extractor: ROMExtractor | None,
    ) -> None:
        """Set ROM data for search operations.

        Args:
            rom_path: Path to the ROM file.
            rom_size: Size of the ROM in bytes.
            rom_extractor: ROM extractor instance.
        """
        self._rom_path = rom_path
        self._rom_size = rom_size
        self._rom_extractor = rom_extractor

    def has_rom_data(self) -> bool:
        """Check if ROM data is available for searching."""
        return bool(self._rom_path and self._rom_size > 0)

    def find_sprite(self, current_offset: int, forward: bool) -> None:
        """Find next or previous sprite from current offset.

        Args:
            current_offset: Current ROM offset to search from.
            forward: True to search forward, False to search backward.
        """
        if not self.has_rom_data():
            return

        # Clean up existing search worker
        WorkerManager.cleanup_worker_attr(self, "_search_worker")

        # Create search worker with appropriate direction
        with QMutexLocker(self._manager_mutex):
            if self._rom_extractor is not None:
                limit = self._rom_size if forward else 0
                direction = 1 if forward else -1
                self._search_worker = SpriteSearchWorker(
                    self._rom_path,
                    current_offset,
                    limit,
                    direction,
                    self._rom_extractor,
                    parent=self._parent_widget,
                )
                self._search_worker.sprite_found.connect(self._on_search_sprite_found)
                self._search_worker.search_complete.connect(self._on_search_complete)
                self._search_worker.start()

                status = "next" if forward else "previous"
                self.status_message.emit(f"Searching for {status} sprite...")

    def scan_for_sprites(self) -> None:
        """Scan ROM for HAL-compressed sprites using a background worker."""
        logger.info(f"scan_for_sprites called, rom_path={self._rom_path}")

        if not self._rom_path:
            logger.warning("No ROM loaded for sprite scanning")
            QMessageBox.warning(self._parent_widget, "No ROM", "Please load a ROM first.")
            return

        logger.info(f"Starting sprite scan for ROM: {self._rom_path}")

        # Clean up any existing scan worker
        WorkerManager.cleanup_worker_attr(self, "_scan_worker")

        # Create progress dialog
        self._scan_progress_dialog = QProgressDialog(
            "Scanning ROM for sprites...", "Cancel", 0, 100, self._parent_widget
        )
        self._scan_progress_dialog.setWindowTitle("Sprite Scanner")
        self._scan_progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._scan_progress_dialog.setMinimumDuration(0)
        self._scan_progress_dialog.canceled.connect(self.cancel_scan)
        self._scan_progress_dialog.show()

        # Create and start worker
        self._scan_worker = SpriteScanWorker(self._rom_path, step=0x1000, rom_cache=self._rom_cache)
        self._scan_worker.progress_detailed.connect(self._on_scan_progress)
        self._scan_worker.sprites_found.connect(self._on_scan_complete)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def cancel_scan(self) -> None:
        """Cancel the sprite scan operation."""
        logger.info("Sprite scan cancelled by user")
        if self._scan_worker is not None:
            self._scan_worker.cancel()
        WorkerManager.cleanup_worker_attr(self, "_scan_worker", timeout=1000)

    def _on_search_sprite_found(self, offset: int, quality: float) -> None:
        """Handle sprite found during navigation search."""
        self.sprite_found.emit(offset, quality)
        self.status_message.emit(f"Found sprite at 0x{offset:06X} (quality: {quality:.2f})")

    def _on_search_complete(self, found: bool) -> None:
        """Handle search completion."""
        self.search_complete.emit(found)
        if not found:
            self.status_message.emit("No sprites found in search direction")

    def _on_scan_progress(self, current: int, total: int) -> None:
        """Handle scan progress updates from worker."""
        if self._scan_progress_dialog is not None and total > 0:
            percent = int((current / total) * 100)
            self._scan_progress_dialog.setValue(percent)

    def _on_scan_complete(self, found_sprites: list[dict[str, object]]) -> None:
        """Handle sprite scan completion."""
        logger.info(f"Sprite scan complete: found {len(found_sprites)} sprites")

        # Close progress dialog
        if self._scan_progress_dialog is not None:
            self._scan_progress_dialog.close()
            self._scan_progress_dialog = None

        # Clean up worker
        if self._scan_worker is not None:
            self._scan_worker.deleteLater()
            self._scan_worker = None

        # Emit signal and show results
        self.scan_complete.emit(found_sprites)

        if found_sprites:
            self._show_scan_results(found_sprites)
        else:
            QMessageBox.information(
                self._parent_widget,
                "No Sprites Found",
                "No HAL-compressed sprites were found in the ROM.",
            )

    def _on_scan_error(self, message: str, exception: Exception) -> None:
        """Handle sprite scan error."""
        logger.error(f"Sprite scan error: {message}", exc_info=exception)

        # Close progress dialog
        if self._scan_progress_dialog is not None:
            self._scan_progress_dialog.close()
            self._scan_progress_dialog = None

        # Clean up worker
        if self._scan_worker is not None:
            self._scan_worker.deleteLater()
            self._scan_worker = None

        QMessageBox.critical(self._parent_widget, "Scan Error", f"Error scanning ROM: {message}")

    def _show_scan_results(self, sprites: list[dict[str, object]]) -> None:
        """Show sprite scan results in a dialog."""
        # Create results dialog
        dialog = QDialog(self._parent_widget)
        dialog.setWindowTitle(f"Found {len(sprites)} Sprites")
        dialog.setMinimumSize(600, 400)

        layout = QVBoxLayout(dialog)

        # Info label
        info_label = QLabel(f"Found {len(sprites)} HAL-compressed sprites in the ROM:")
        layout.addWidget(info_label)

        # Create list widget for results
        list_widget = QListWidget()

        for sprite in sprites:
            offset = sprite["offset"]
            tile_count = sprite["tile_count"]
            size = sprite["decompressed_size"]
            quality = sprite.get("quality", 0)

            # Create item text
            text = f"0x{offset:06X} - {tile_count} tiles ({size} bytes) - Quality: {quality:.1%}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, offset)
            list_widget.addItem(item)

        list_widget.itemDoubleClicked.connect(lambda item: self._jump_to_sprite(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(list_widget)

        # Buttons
        button_box = QDialogButtonBox()

        jump_button = QPushButton("Jump to Selected")
        jump_button.clicked.connect(lambda: self._jump_to_selected_sprite(list_widget))
        button_box.addButton(jump_button, QDialogButtonBox.ButtonRole.ActionRole)

        close_button = button_box.addButton(QDialogButtonBox.StandardButton.Close)
        close_button.clicked.connect(dialog.close)

        layout.addWidget(button_box)

        dialog.exec()

    def _jump_to_sprite(self, offset: int) -> None:
        """Jump to a specific sprite offset."""
        logger.info(f"Jumping to sprite at 0x{offset:06X}")
        self.offset_requested.emit(offset)

    def _jump_to_selected_sprite(self, list_widget: QListWidget) -> None:
        """Jump to the selected sprite in the list."""
        item = list_widget.currentItem()
        if item:
            offset = item.data(Qt.ItemDataRole.UserRole)
            self._jump_to_sprite(offset)

    def cleanup(self) -> None:
        """Clean up resources.

        Call this before the parent dialog is destroyed.
        """
        # Cleanup search worker
        WorkerManager.cleanup_worker_attr(self, "_search_worker")

        # Cleanup scan worker
        WorkerManager.cleanup_worker_attr(self, "_scan_worker", timeout=1000)

        # Close progress dialog
        if self._scan_progress_dialog is not None:
            self._scan_progress_dialog.close()
            self._scan_progress_dialog = None

        logger.debug("SpriteSearchCoordinator cleaned up")
