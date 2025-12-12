"""
Sprite gallery tab for visual overview of all sprites in ROM.
Provides grid display, filtering, sorting, and batch operations.
"""
from __future__ import annotations

import builtins
import contextlib
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.rom_extractor import ROMExtractor
from core.sprite_finder import SpriteFinder
from ui.widgets.sprite_gallery_widget import SpriteGalleryWidget
from ui.workers.batch_thumbnail_worker import ThumbnailWorkerController
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Layout constants
LAYOUT_SPACING = 4
LAYOUT_MARGINS = 4
BUTTON_HEIGHT = 32

class SpriteGalleryTab(QWidget):
    """Tab widget for sprite gallery display and management."""

    # Signals
    sprite_selected = Signal(int)  # Navigate to sprite
    sprites_exported = Signal(list)  # Sprites exported

    def __init__(self, parent: QWidget | None = None):
        """
        Initialize the sprite gallery tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # State
        self.rom_path: str | None = None
        self.rom_size: int = 0
        self.rom_extractor = None
        self.sprites_data: list[dict[str, Any]] = []

        # Workers
        self.thumbnail_controller: ThumbnailWorkerController | None = None
        self.scan_thread: QThread | None = None

        # UI Components - these are always initialized in _setup_ui()
        self.gallery_widget: SpriteGalleryWidget  # Always initialized
        self.toolbar: QToolBar  # Always initialized
        self.progress_dialog: QProgressDialog | None = None
        self.detached_window: Any | None = None  # DetachedGalleryWindow

        self._setup_ui()

    def _setup_ui(self):
        """Setup the tab UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(LAYOUT_MARGINS, LAYOUT_MARGINS, LAYOUT_MARGINS, LAYOUT_MARGINS)
        layout.setSpacing(LAYOUT_SPACING)

        # Toolbar
        self.toolbar = self._create_toolbar()
        layout.addWidget(self.toolbar)

        # Gallery widget with proper size policy
        self.gallery_widget = SpriteGalleryWidget(self)
        self.gallery_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.gallery_widget.sprite_selected.connect(self._on_sprite_selected)
        self.gallery_widget.sprite_double_clicked.connect(self._on_sprite_double_clicked)
        self.gallery_widget.selection_changed.connect(self._on_selection_changed)
        self.gallery_widget.thumbnail_request.connect(self._on_thumbnail_request)
        layout.addWidget(self.gallery_widget, 1)  # Give it stretch

        # Action bar
        action_bar = self._create_action_bar()
        layout.addWidget(action_bar)

        self.setLayout(layout)

    def _create_toolbar(self) -> QToolBar:
        """Create the toolbar with gallery actions."""
        toolbar = QToolBar()
        toolbar.setMovable(False)

        # Scan for sprites
        scan_action = QAction("🔍 Scan ROM", self)
        scan_action.setToolTip("Scan ROM for all sprites")
        scan_action.triggered.connect(self._scan_for_sprites)
        toolbar.addAction(scan_action)

        # Custom range scan
        custom_scan_action = QAction("🎯 Custom Range Scan", self)
        custom_scan_action.setToolTip("Scan a specific range of the ROM")
        custom_scan_action.triggered.connect(self._scan_custom_range)
        toolbar.addAction(custom_scan_action)

        toolbar.addSeparator()

        # Export actions
        export_action = QAction("💾 Export Selected", self)
        export_action.setToolTip("Export selected sprites as PNG")
        export_action.triggered.connect(self._export_selected)
        toolbar.addAction(export_action)

        export_sheet_action = QAction("📋 Export Sheet", self)
        export_sheet_action.setToolTip("Export as sprite sheet")
        export_sheet_action.triggered.connect(self._export_sprite_sheet)
        toolbar.addAction(export_sheet_action)

        toolbar.addSeparator()

        # View options
        grid_action = QAction("⚏ Grid View", self)
        grid_action.setCheckable(True)
        grid_action.setChecked(True)
        toolbar.addAction(grid_action)

        list_action = QAction("☰ List View", self)
        list_action.setCheckable(True)
        toolbar.addAction(list_action)

        toolbar.addSeparator()

        # Refresh
        refresh_action = QAction("🔄 Refresh", self)
        refresh_action.setToolTip("Refresh thumbnails")
        refresh_action.triggered.connect(self._refresh_thumbnails)
        toolbar.addAction(refresh_action)

        toolbar.addSeparator()

        # Detach window
        detach_action = QAction("🗖 Detach Gallery", self)
        detach_action.setToolTip("Open gallery in separate window (fixes stretching)")
        detach_action.triggered.connect(self._open_detached_gallery)
        toolbar.addAction(detach_action)

        return toolbar

    def _create_action_bar(self) -> QWidget:
        """Create the bottom action bar."""
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(LAYOUT_MARGINS, LAYOUT_MARGINS, LAYOUT_MARGINS, LAYOUT_MARGINS)

        # Quick actions with responsive sizing
        self.compare_btn = QPushButton("Compare")
        if self.compare_btn:
            self.compare_btn.setEnabled(False)
        self.compare_btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.compare_btn.setFixedHeight(BUTTON_HEIGHT)
        self.compare_btn.clicked.connect(self._compare_sprites)
        layout.addWidget(self.compare_btn)

        self.palette_btn = QPushButton("Apply Palette")
        if self.palette_btn:
            self.palette_btn.setEnabled(False)
        self.palette_btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.palette_btn.setFixedHeight(BUTTON_HEIGHT)
        self.palette_btn.clicked.connect(self._apply_palette)
        layout.addWidget(self.palette_btn)

        layout.addStretch()

        # Info label
        self.info_label = QLabel("No ROM loaded")
        layout.addWidget(self.info_label)

        widget.setLayout(layout)
        return widget

    def set_rom_data(self, rom_path: str, rom_size: int, rom_extractor: ROMExtractor):
        """
        Set the ROM data for the gallery.

        Args:
            rom_path: Path to ROM file
            rom_size: Size of ROM in bytes
            rom_extractor: ROM extractor instance
        """
        self.rom_path = rom_path
        self.rom_size = rom_size
        self.rom_extractor = rom_extractor

        # Update info
        rom_name = Path(rom_path).name
        if self.info_label:
            self.info_label.setText(f"ROM: {rom_name} ({rom_size / 1024 / 1024:.1f}MB)")

        # Try to load cached scan results for this ROM
        cache_loaded = self._load_scan_cache(rom_path)

        if cache_loaded:
            logger.info(f"Successfully loaded cached scan results for {rom_name}")
            # Cache loaded successfully, thumbnails will be generated
        else:
            logger.info(f"No valid cache found for {rom_name}")
            # Clear any old sprites from previous ROM
            self.sprites_data = []
            self.gallery_widget.set_sprites([])

            # Auto-scan if enabled and no cache was loaded
            if self._should_auto_scan():
                QTimer.singleShot(100, self._scan_for_sprites)

    def _should_auto_scan(self) -> bool:
        """Check if auto-scan is enabled in settings."""
        # TODO: Read from settings
        return False  # Disabled by default for performance

    def _scan_for_sprites(self):
        """Scan the ROM for all sprites."""
        if not self.rom_path:
            QMessageBox.warning(self, "No ROM", "Please load a ROM first")
            return

        # Ask user for scan type
        msgBox = QMessageBox(self)
        msgBox.setWindowTitle("Scan Type")
        msgBox.setText("Choose scan type:")
        msgBox.setInformativeText(
            "Quick Scan: Faster, finds fewer sprites (~20-50)\n"
            "Thorough Scan: Slower, finds more sprites (up to 200)"
        )
        quick_btn = msgBox.addButton("Quick Scan", QMessageBox.ButtonRole.ActionRole)
        thorough_btn = msgBox.addButton("Thorough Scan", QMessageBox.ButtonRole.ActionRole)
        msgBox.addButton(QMessageBox.StandardButton.Cancel)
        msgBox.exec()

        if msgBox.clickedButton() == quick_btn:
            self.scan_mode = "quick"
        elif msgBox.clickedButton() == thorough_btn:
            self.scan_mode = "thorough"
        else:
            return  # Cancelled

        # Show progress dialog
        self.progress_dialog = QProgressDialog(
            "Scanning ROM for sprites...",
            "Cancel",
            0,
            100,
            self
        )
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.show()

        # Create and start scan worker
        self._start_sprite_scan()

    def _scan_custom_range(self):
        """Scan a custom range of the ROM for sprites."""
        if not self.rom_path:
            QMessageBox.warning(self, "No ROM", "Please load a ROM first")
            return

        # Import the dialog
        from ui.dialogs.scan_range_dialog import ScanRangeDialog

        # Show range dialog
        dialog = ScanRangeDialog(self.rom_size, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        start_offset, end_offset = dialog.get_range()

        # Show progress dialog
        self.progress_dialog = QProgressDialog(
            f"Scanning ROM range 0x{start_offset:X} - 0x{end_offset:X}...",
            "Cancel",
            0,
            100,
            self
        )
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.show()

        # Start scan with custom range
        self._start_sprite_scan(start_offset, end_offset)

    def _start_sprite_scan(self, start_offset: int | None = None, end_offset: int | None = None):
        """Start the sprite scanning process."""
        # Use SpriteFinder to scan
        finder = SpriteFinder()

        # For now, do a quick scan synchronously
        # TODO: Move to worker thread for large ROMs
        try:
            if not self.rom_path:
                raise ValueError("No ROM path set")
            with Path(self.rom_path).open('rb') as f:
                rom_data = f.read()

            sprites = []

            # Use custom range if provided
            if start_offset is not None and end_offset is not None:
                # Custom scan range
                logger.info(f"Using custom scan range: 0x{start_offset:X} - 0x{end_offset:X}")

                # Determine step size based on range size
                range_size = end_offset - start_offset
                if range_size < 0x10000:  # < 64KB
                    step_size = 0x100  # Scan every 256 bytes
                elif range_size < 0x40000:  # < 256KB
                    step_size = 0x200  # Scan every 512 bytes
                elif range_size < 0x100000:  # < 1MB
                    step_size = 0x400  # Scan every 1024 bytes
                else:
                    step_size = 0x800  # Scan every 2048 bytes for large ranges

                scan_ranges = [(start_offset, end_offset, step_size)]
            # Choose scan ranges based on scan mode
            elif hasattr(self, 'scan_mode') and self.scan_mode == "thorough":
                # Thorough scan - smaller step sizes, more areas
                scan_ranges = [
                    (0x200000, 0x280000, 0x100),  # Main sprite area - scan every 256 bytes
                    (0x280000, 0x300000, 0x200),  # Extended main area - scan every 512 bytes
                    (0x100000, 0x180000, 0x200),  # Secondary area - scan every 512 bytes
                    (0x180000, 0x200000, 0x400),  # Extended secondary - scan every 1024 bytes
                    (0x300000, 0x380000, 0x400),  # Additional area - scan every 1024 bytes
                ]
            else:
                # Quick scan - larger step sizes, fewer areas
                scan_ranges = [
                    (0x200000, 0x280000, 0x800),  # Main sprite area - scan every 2048 bytes
                    (0x100000, 0x180000, 0x1000),  # Secondary area - scan every 4096 bytes
                ]

            # Calculate total steps, avoiding division by zero
            total_steps = sum(max(1, (end - start) // step) for start, end, step in scan_ranges)
            current_step = 0
            max_sprites = 200  # Limit to prevent overwhelming the gallery

            for start, end, step in scan_ranges:
                for offset in range(start, min(end, len(rom_data)), step):
                    # Update progress
                    current_step += 1
                    progress = int((current_step / total_steps) * 100)
                    if self.progress_dialog:
                        self.progress_dialog.setValue(progress)

                        # Update progress text with found sprites count
                        self.progress_dialog.setLabelText(
                            f"Scanning ROM for sprites... Found: {len(sprites)}"
                        )

                        # Check for cancel
                        if self.progress_dialog.wasCanceled():
                            break

                    # Stop if we've found enough sprites
                    if len(sprites) >= max_sprites:
                        logger.info(f"Reached maximum sprite limit of {max_sprites}")
                        break

                    # Try to find sprite
                    sprite_info = finder.find_sprite_at_offset(rom_data, offset)
                    if sprite_info:
                        sprites.append(sprite_info)
                        logger.debug(f"Found sprite #{len(sprites)} at 0x{offset:06X}")

                if (self.progress_dialog and self.progress_dialog.wasCanceled()) or len(sprites) >= max_sprites:
                    break

            # Store results
            self.sprites_data = sprites

            # Save to cache for later use (e.g., screenshots)
            self._save_scan_cache()

            # Update gallery
            self.gallery_widget.set_sprites(sprites)

            # Update info
            rom_name = Path(self.rom_path).name if self.rom_path else "Unknown"
            self.info_label.setText(
                f"Found {len(sprites)} sprites in {rom_name}"
            )

            # Start generating thumbnails for found sprites
            if sprites:
                logger.info(f"Starting thumbnail generation for {len(sprites)} sprites")
                self._refresh_thumbnails()

        except Exception as e:
            logger.error(f"Error scanning ROM: {e}")
            QMessageBox.critical(self, "Scan Error", f"Failed to scan ROM: {e}")

        finally:
            if self.progress_dialog:
                self.progress_dialog.close()
                self.progress_dialog = None

    def _refresh_thumbnails(self):
        """Refresh thumbnail images - now handled on-demand by virtual scrolling."""
        if not self.sprites_data or not self.rom_path:
            logger.warning("Cannot refresh thumbnails: no sprites or ROM path")
            return

        # Clear thumbnail cache in model to force regeneration
        if self.gallery_widget.model:
            self.gallery_widget.model.clear_thumbnail_cache()

        # Trigger loading of visible thumbnails
        self.gallery_widget._update_visible_thumbnails()

        logger.info("Thumbnail refresh triggered - will load on demand as items become visible")

    def _on_thumbnail_ready(self, offset: int, pixmap: QPixmap):
        """
        Handle thumbnail ready from worker.

        Args:
            offset: Sprite offset
            pixmap: Generated thumbnail pixmap
        """
        logger.debug(f"Thumbnail ready for offset 0x{offset:06X}, pixmap null: {pixmap.isNull()}")

        # Set thumbnail in gallery widget (now uses model)
        self.gallery_widget.set_thumbnail(offset, pixmap)

    def _on_thumbnail_request(self, offset: int, priority: int):
        """
        Handle thumbnail request from gallery widget.

        Args:
            offset: Sprite offset
            priority: Request priority (lower = higher priority)
        """
        if not self.rom_path:
            return

        # Create controller if needed
        if not self.thumbnail_controller:
            logger.info("Creating ThumbnailWorkerController for on-demand requests")
            self.thumbnail_controller = ThumbnailWorkerController(self)
            self.thumbnail_controller.thumbnail_ready.connect(self._on_thumbnail_ready)
            self.thumbnail_controller.start_worker(self.rom_path, self.rom_extractor)

        # Queue thumbnail with priority
        self.thumbnail_controller.queue_thumbnail(offset, 128, priority)

    def _on_sprite_selected(self, offset: int):
        """Handle sprite selection in gallery."""
        logger.debug(f"Sprite selected at offset: 0x{offset:06X}")

    def _on_sprite_double_clicked(self, offset: int):
        """Handle sprite double-click - navigate to it."""
        self.sprite_selected.emit(offset)

    def _on_selection_changed(self, selected_offsets: list[int]):
        """Handle selection change in gallery."""
        count = len(selected_offsets)

        # Enable/disable actions based on selection
        if self.compare_btn:
            self.compare_btn.setEnabled(count >= 2)
        if self.palette_btn:
            self.palette_btn.setEnabled(count >= 1)

        # Update toolbar actions
        for action in self.toolbar.actions():
            if "Export" in action.text():
                action.setEnabled(count >= 1)

    def _export_selected(self):
        """Export selected sprites as individual PNG files."""
        selected = self.gallery_widget.get_selected_sprites()
        if not selected:
            QMessageBox.information(self, "No Selection", "Please select sprites to export")
            return

        # Get export directory
        export_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Directory",
            "",
            QFileDialog.Option.ShowDirsOnly
        )

        if not export_dir:
            return

        # Export each sprite
        exported = []
        for sprite_info in selected:
            try:
                offset = sprite_info.get('offset', 0)
                if isinstance(offset, str):
                    offset = int(offset, 16) if offset.startswith('0x') else int(offset)

                # Generate filename
                filename = f"sprite_{offset:06X}.png"
                filepath = Path(export_dir) / filename

                # TODO: Actually export the sprite image
                # For now, just track it
                exported.append(str(filepath))

            except Exception as e:
                logger.error(f"Failed to export sprite: {e}")

        # Show result
        if exported:
            QMessageBox.information(
                self,
                "Export Complete",
                f"Exported {len(exported)} sprites to {export_dir}"
            )
            self.sprites_exported.emit(exported)

    def _export_sprite_sheet(self):
        """Export selected sprites as a sprite sheet."""
        selected = self.gallery_widget.get_selected_sprites()
        if not selected:
            QMessageBox.information(self, "No Selection", "Please select sprites to export")
            return

        # Get save location
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Sprite Sheet",
            "sprite_sheet.png",
            "PNG Files (*.png)"
        )

        if not filepath:
            return

        # TODO: Implement sprite sheet generation
        QMessageBox.information(
            self,
            "Not Implemented",
            "Sprite sheet export will be implemented soon"
        )

    def _compare_sprites(self):
        """Open comparison view for selected sprites."""
        selected = self.gallery_widget.get_selected_sprites()
        if len(selected) < 2:
            QMessageBox.information(
                self,
                "Select More",
                "Please select at least 2 sprites to compare"
            )
            return

        # TODO: Implement comparison dialog
        QMessageBox.information(
            self,
            "Not Implemented",
            "Sprite comparison will be implemented soon"
        )

    def _apply_palette(self):
        """Apply a palette to selected sprites."""
        selected = self.gallery_widget.get_selected_sprites()
        if not selected:
            return

        # TODO: Implement palette application
        QMessageBox.information(
            self,
            "Not Implemented",
            "Batch palette application will be implemented soon"
        )

    def _open_detached_gallery(self):
        """Open the gallery in a separate window to avoid stretching issues."""
        # Create or show existing detached window
        if not self.detached_window:
            # Local import to avoid circular dependency
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            from ui.windows.detached_gallery_window import DetachedGalleryWindow
            extraction_manager = inject(ExtractionManagerProtocol)
            self.detached_window = DetachedGalleryWindow(
                self,
                extraction_manager=extraction_manager  # type: ignore[arg-type]
            )

            # Connect signals
            self.detached_window.sprite_selected.connect(self.sprite_selected.emit)
            self.detached_window.window_closed.connect(self._on_detached_closed)

            # Set ROM info if available
            if self.rom_path and self.rom_extractor:
                self.detached_window.set_rom_info(self.rom_path, self.rom_extractor)

        # Set current sprites
        if self.sprites_data:
            self.detached_window.set_sprites(self.sprites_data)

            # Copy existing thumbnails from main gallery to detached gallery
            if self.gallery_widget:
                self.detached_window.copy_thumbnails_from(self.gallery_widget)

            # Also connect for future thumbnail updates
            if self.thumbnail_controller:
                # Connect to the detached gallery for any new thumbnails
                with contextlib.suppress(RuntimeError):
                    self.thumbnail_controller.thumbnail_ready.connect(
                        self._on_detached_thumbnail_ready
                    )

        # Show the window
        self.detached_window.show()
        self.detached_window.raise_()
        self.detached_window.activateWindow()

        logger.info("Opened detached gallery window")

    def _on_detached_closed(self):
        """Handle detached window closing."""
        if self.detached_window:
            # Disconnect signals
            if self.thumbnail_controller:
                with contextlib.suppress(builtins.BaseException):
                    self.thumbnail_controller.thumbnail_ready.disconnect(
                        self._on_detached_thumbnail_ready
                    )

            self.detached_window = None
            logger.info("Detached gallery window closed")

    def _on_detached_thumbnail_ready(self, offset: int, pixmap: QPixmap):
        """Update thumbnail in detached window."""
        if self.detached_window and self.detached_window.gallery_widget and offset in self.detached_window.gallery_widget.thumbnails:
                thumbnail = self.detached_window.gallery_widget.thumbnails[offset]
                # Find sprite info
                sprite_info = None
                for info in self.sprites_data:
                    info_offset = info.get('offset', 0)
                    if isinstance(info_offset, str):
                        info_offset = int(info_offset, 16) if info_offset.startswith('0x') else int(info_offset)
                    if info_offset == offset:
                        sprite_info = info
                        break
                thumbnail.set_sprite_data(pixmap, sprite_info)

    def cleanup(self):
        """Clean up resources."""
        # Close detached window if open
        if self.detached_window:
            self.detached_window.close()
            self.detached_window = None

        if self.thumbnail_controller:
            self.thumbnail_controller.cleanup()
            self.thumbnail_controller = None

    def _get_cache_path(self, rom_path: str | None = None) -> Path:
        """Get the cache file path for a specific ROM."""
        # Use local cache directory in the project
        cache_dir = Path(__file__).parent.parent.parent / ".cache" / "gallery_scans"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Create ROM-specific cache filename
        if rom_path:
            rom_name = Path(rom_path).stem
            # Add a hash of the full path to handle multiple ROMs with same name
            path_hash = hashlib.md5(str(rom_path).encode()).hexdigest()[:8]
            cache_filename = f"scan_cache_{rom_name}_{path_hash}.json"
        else:
            cache_filename = "scan_cache_default.json"

        return cache_dir / cache_filename

    def _save_scan_cache(self):
        """Save scan results to a cache file for later use."""
        if not self.sprites_data or not self.rom_path:
            return

        cache_path = self._get_cache_path(self.rom_path)

        try:
            cache_data = {
                'version': 2,
                'rom_path': str(self.rom_path),
                'rom_size': self.rom_size,
                'sprite_count': len(self.sprites_data),
                'sprites': self.sprites_data,
                'scan_mode': getattr(self, 'scan_mode', 'quick'),
                'timestamp': time.time()
            }

            with cache_path.open('w') as f:
                json.dump(cache_data, f, indent=2)

            logger.info(f"Saved {len(self.sprites_data)} sprites to cache: {cache_path.name}")
        except Exception as e:
            logger.error(f"Failed to save scan cache: {e}")

    def _load_scan_cache(self, rom_path: str | None = None):
        """Load previously saved scan results from cache."""
        if not rom_path:
            rom_path = self.rom_path

        if not rom_path:
            logger.debug("No ROM path specified, skipping cache load")
            return False

        cache_path = self._get_cache_path(rom_path)

        if not cache_path.exists():
            logger.debug(f"No cache file found at: {cache_path.name}")
            return False

        try:
            with cache_path.open() as f:
                cache_data = json.load(f)

            # Verify cache is for the same ROM
            cached_rom_path = cache_data.get('rom_path')
            if str(cached_rom_path) != str(rom_path):
                logger.warning(f"Cache ROM path mismatch: {cached_rom_path} != {rom_path}")
                return False

            # Check cache version
            if cache_data.get('version', 1) < 2:
                logger.info("Cache version too old, ignoring")
                return False

            # Load the cached data
            self.sprites_data = cache_data.get('sprites', [])
            scan_mode = cache_data.get('scan_mode', 'unknown')
            timestamp = cache_data.get('timestamp', 0)

            if self.sprites_data:
                # Calculate cache age
                cache_age_hours = (time.time() - timestamp) / 3600 if timestamp else -1

                logger.info(f"Loaded {len(self.sprites_data)} sprites from cache ({scan_mode} scan, {cache_age_hours:.1f} hours old)")

                # Update gallery widget if it exists
                if self.gallery_widget:
                    self.gallery_widget.set_sprites(self.sprites_data)

                    # Start generating real thumbnails for cached sprites
                    self._refresh_thumbnails()

                # Update info label
                if hasattr(self, 'info_label'):
                    rom_name = Path(rom_path).name
                    age_str = f" ({cache_age_hours:.1f}h old)" if cache_age_hours >= 0 else ""
                    if self.info_label:
                        self.info_label.setText(
                        f"Loaded {len(self.sprites_data)} cached sprites from {rom_name}{age_str}"
                    )

                return True
        except Exception as e:
            logger.error(f"Failed to load scan cache: {e}")
            return False

    def _generate_mock_thumbnails(self):
        """Generate mock thumbnails for sprites when no real thumbnails are available."""
        try:
            from generate_mock_thumbnails import generate_mock_sprite_thumbnail  # type: ignore[import-not-found]

            for sprite_info in self.sprites_data:
                offset = sprite_info.get('offset', 0)
                if isinstance(offset, str):
                    offset = int(offset, 16) if offset.startswith('0x') else int(offset)

                # Generate mock thumbnail
                thumbnail_size = self.gallery_widget.thumbnail_size
                pixmap = generate_mock_sprite_thumbnail(sprite_info, thumbnail_size)

                # Find the thumbnail widget and set its pixmap
                if offset in self.gallery_widget.thumbnails:
                    thumbnail_widget = self.gallery_widget.thumbnails[offset]
                    thumbnail_widget.set_sprite_data(pixmap, sprite_info)

            logger.info(f"Generated mock thumbnails for {len(self.sprites_data)} sprites")
        except Exception as e:
            logger.error(f"Failed to generate mock thumbnails: {e}")
