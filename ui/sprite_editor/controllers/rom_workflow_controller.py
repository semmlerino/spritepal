#!/usr/bin/env python3
"""
ROM Workflow Controller for the Sprite Editor.
Coordinates ROM loading, previewing, editing, and injection.
"""

from typing import TYPE_CHECKING

import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap

from core.mesen_integration.log_watcher import CapturedOffset
from ui.common.smart_preview_coordinator import SmartPreviewCoordinator
from ui.workers.batch_thumbnail_worker import ThumbnailWorkerController
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.mesen_integration.log_watcher import LogWatcher
    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache
    from core.sprite_library import SpriteLibrary
    from ui.managers.status_bar_manager import StatusBarManager

    from ..views.workspaces.rom_workflow_page import ROMWorkflowPage
    from .editing_controller import EditingController

logger = get_logger(__name__)


class ROMWorkflowController(QObject):
    """
    Controller for the unified ROM workflow.
    States:
    - PREVIEW: Browsing ROM offsets.
    - EDIT: Sprite loaded in editor.
    - SAVE: Confirming injection back to ROM.

    Signal Flow:
        LogWatcher.offset_discovered → this._on_offset_discovered → asset browser
        SmartPreviewCoordinator.preview_ready → this._on_preview_ready → view updates
        ROMWorkflowPage.sprite_selected/activated → this handlers → set_offset/open_in_editor

    Consumers:
        - ROMWorkflowPage: Receives rom_info_updated, workflow_state_changed
        - MainWindow/StatusBar: May connect for progress/status updates
    """

    # Signals (originate here, consumed by views)
    rom_info_updated = Signal(str)  # ROM title → ROMWorkflowPage.source_bar.set_info
    workflow_state_changed = Signal(str)  # 'preview'/'edit'/'save' → view state updates

    def __init__(
        self,
        parent: QObject | None,
        editing_controller: "EditingController",
        *,
        message_service: "StatusBarManager | None" = None,
        rom_cache: "ROMCache | None" = None,
        rom_extractor: "ROMExtractor | None" = None,
        log_watcher: "LogWatcher | None" = None,
        sprite_library: "SpriteLibrary | None" = None,
    ) -> None:
        super().__init__(parent)
        self._editing_controller = editing_controller
        self._message_service: StatusBarManager | None = message_service
        self._view: ROMWorkflowPage | None = None

        # Core services - injected dependencies
        self.rom_cache = rom_cache
        self.rom_extractor = rom_extractor
        self.log_watcher = log_watcher
        self._sprite_library = sprite_library

        # Preview coordinator
        self.preview_coordinator = SmartPreviewCoordinator(self)
        self.preview_coordinator.preview_ready.connect(self._on_preview_ready)
        self.preview_coordinator.preview_error.connect(self._on_preview_error)
        self.preview_coordinator.set_rom_data_provider(self._get_rom_data_for_preview)

        # State
        self.rom_path: str = ""
        self.rom_size: int = 0
        self.current_offset: int = 0
        self.state: str = "preview"  # 'preview', 'edit', 'save'

        # Current sprite data
        self.current_tile_data: bytes | None = None
        self.current_width: int = 0
        self.current_height: int = 0
        self.current_sprite_name: str = ""
        self.original_compressed_size: int = 0
        self.available_slack: int = 0
        self.hal_decompression_succeeded: bool = False

        # Flag for auto-opening in editor after preview completes (double-click)
        self._pending_open_in_editor: bool = False
        self._pending_open_offset: int = -1  # Track which offset triggered pending

        # Flag for preview loading state (used to disable action button)
        self._preview_pending: bool = False

        # Thumbnail worker controller
        self._thumbnail_controller: ThumbnailWorkerController | None = None

        # Queue for captures discovered before view is ready
        self._pending_captures: list[CapturedOffset] = []

        # Connect LogWatcher
        self._connect_log_watcher()

    def _connect_log_watcher(self) -> None:
        """Connect LogWatcher signals to handle discovered offsets."""
        if not self.log_watcher:
            return
        self.log_watcher.offset_discovered.connect(self._on_offset_discovered)
        # Start watching if not already
        self.log_watcher.start_watching()

    def _setup_thumbnail_worker(self) -> None:
        """Create thumbnail worker after ROM is loaded."""
        if self._thumbnail_controller:
            self._thumbnail_controller.cleanup()

        if not self.rom_extractor:
            return

        self._thumbnail_controller = ThumbnailWorkerController(self)
        self._thumbnail_controller.start_worker(self.rom_path, self.rom_extractor)

        # Connect ready signal to browser update
        if self._thumbnail_controller.worker:
            self._thumbnail_controller.worker.thumbnail_ready.connect(self._on_thumbnail_ready)
            logger.debug("Thumbnail worker connected for asset browser")

    def _on_thumbnail_ready(self, offset: int, thumbnail: QImage) -> None:
        """Handle thumbnail ready from worker."""
        if self._view:
            pixmap = QPixmap.fromImage(thumbnail)
            self._view.set_thumbnail(offset, pixmap)
            logger.debug(f"Thumbnail set for offset 0x{offset:06X}")

    def set_message_service(self, service: "StatusBarManager | None") -> None:
        """Inject message service after construction (for deferred initialization)."""
        self._message_service = service

    def _get_capture_name(self, capture: CapturedOffset) -> str:
        """Generate display name for captured sprite."""
        if capture.frame is not None:
            return f"0x{capture.offset:06X} (F{capture.frame})"
        else:
            # Fallback to timestamp if no frame
            timestamp_str = capture.timestamp.strftime("%H:%M:%S")
            return f"0x{capture.offset:06X} ({timestamp_str})"

    def _on_offset_discovered(self, capture: object) -> None:
        """Handle new offset discovered from Mesen2 log."""
        if not isinstance(capture, CapturedOffset):
            return

        # Queue if view not ready yet
        if self._view is None:
            self._pending_captures.append(capture)
            logger.debug("Queued capture 0x%06X (view not ready)", capture.offset)
            return

        # Process immediately
        self._add_capture_to_browser(capture)

    def _add_capture_to_browser(self, capture: CapturedOffset) -> None:
        """Add a capture to the browser with thumbnail."""
        print(
            f"[DEBUG] _add_capture_to_browser: offset=0x{capture.offset:06X}, view={self._view is not None}", flush=True
        )
        if not self._view:
            print("[DEBUG] _add_capture_to_browser: NO VIEW, skipping", flush=True)
            return

        name = self._get_capture_name(capture)
        print(
            f"[DEBUG] _add_capture_to_browser: calling view.add_mesen_capture({name}, 0x{capture.offset:06X})",
            flush=True,
        )
        self._view.add_mesen_capture(name, capture.offset)

        # Request thumbnail if worker is ready
        if self._thumbnail_controller:
            print(f"[DEBUG] _add_capture_to_browser: queuing thumbnail for 0x{capture.offset:06X}", flush=True)
            self._thumbnail_controller.queue_thumbnail(capture.offset)

    def set_view(self, view: "ROMWorkflowPage") -> None:
        """Set the view and connect signals."""
        self._view = view
        self._connect_view_signals()

        # Initialize ROM availability state (disabled until ROM is loaded)
        if not self.rom_path:
            self._view.set_rom_available(False)

        # Load existing captures into asset browser
        if self.log_watcher:
            # First: load persistent clicks from file (cross-session)
            persistent_clicks = self.log_watcher.load_persistent_clicks()
            for capture in persistent_clicks:
                self._add_capture_to_browser(capture)

            # Second: sync current session captures (may overlap with persistent,
            # but _add_capture_to_browser handles duplicates via has_mesen_capture)
            for capture in self.log_watcher.recent_captures:
                self._add_capture_to_browser(capture)

        # Flush any pending real-time captures (discovered before view was ready)
        if self._pending_captures:
            logger.info("Flushing %d pending captures", len(self._pending_captures))
            for capture in self._pending_captures:
                self._add_capture_to_browser(capture)
            self._pending_captures.clear()

    def _connect_view_signals(self) -> None:
        """Connect view signals."""
        if not self._view:
            return

        self._view.source_bar.offset_changed.connect(self.set_offset)
        self._view.source_bar.action_clicked.connect(self.handle_primary_action)
        self._view.source_bar.browse_rom_requested.connect(self.browse_rom)

        # Asset browser signals
        self._view.sprite_selected.connect(self._on_sprite_selected)
        self._view.sprite_activated.connect(self._on_sprite_activated)
        self._view.asset_browser.save_to_library_requested.connect(self._on_save_to_library)
        self._view.asset_browser.rename_requested.connect(self._on_asset_renamed)
        self._view.asset_browser.delete_requested.connect(self._on_asset_deleted)

        # EditWorkspace signals (save/export)
        self._view.workspace.saveToRomRequested.connect(self.prepare_injection)
        self._view.workspace.exportPngRequested.connect(self.export_png)

    def _on_sprite_selected(self, offset: int, source_type: str) -> None:
        """Handle sprite selection from asset browser."""
        print(f"[DEBUG] _on_sprite_selected: offset=0x{offset:06X}, source_type={source_type}", flush=True)
        self.set_offset(offset)

    def _on_sprite_activated(self, offset: int, source_type: str) -> None:
        """Handle sprite activation (double-click) - enter edit mode."""
        logger.debug(f"[DOUBLE-CLICK] _on_sprite_activated called: offset=0x{offset:06X}, source={source_type}")

        # If we already have tile data for this offset, open directly without re-requesting preview
        if self.current_offset == offset and self.current_tile_data:
            logger.debug("[DOUBLE-CLICK] Already have data for this offset, opening directly")
            self.open_in_editor()
            return

        # If we are already waiting for this offset (preview pending), just set the flag
        if self.current_offset == offset:
            logger.debug("[DOUBLE-CLICK] Preview pending for this offset, setting flag only")
            self._pending_open_in_editor = True
            self._pending_open_offset = offset
            return

        # Set flag to auto-open in editor when preview completes
        self._pending_open_in_editor = True
        self._pending_open_offset = offset
        logger.debug("[DOUBLE-CLICK] Flag set, calling set_offset")
        self.set_offset(offset)

    def _on_save_to_library(self, offset: int, source_type: str) -> None:
        """Save sprite to library."""
        if not self.rom_path:
            logger.warning("Cannot save to library: no ROM loaded")
            if self._message_service:
                self._message_service.show_message("Cannot save to library: no ROM loaded")
            return

        if not self._sprite_library:
            logger.warning("Cannot save to library: sprite library not available")
            if self._message_service:
                self._message_service.show_message("Cannot save to library: sprite library not available")
            return

        library = self._sprite_library

        # Check if already in library
        rom_hash = library.compute_rom_hash(self.rom_path)
        existing = library.get_by_offset(offset, rom_hash)
        if existing:
            logger.info("Sprite at 0x%06X already in library", offset)
            if self._message_service:
                self._message_service.show_message(f"Sprite at 0x{offset:06X} is already in library")
            return

        # Get display name from browser
        name = self._get_display_name_for_offset(offset) or f"Sprite 0x{offset:06X}"

        # Generate thumbnail (PIL Image for library storage)
        pil_thumbnail = self._generate_library_thumbnail(offset)

        # Add to library (persistent storage)
        library.add_sprite(
            rom_offset=offset,
            rom_path=self.rom_path,
            name=name,
            thumbnail=pil_thumbnail,
        )

        # Also add to browser's Library category for immediate visibility
        if self._view:
            qpixmap = self._pil_to_qpixmap(pil_thumbnail) if pil_thumbnail else None
            self._view.add_library_sprite(name, offset, qpixmap)

        logger.info("Saved to library: %s at 0x%06X", name, offset)
        if self._message_service:
            self._message_service.show_message(f"Saved '{name}' to library")

    def _get_display_name_for_offset(self, offset: int) -> str | None:
        """Get current display name for offset from browser."""
        if not self._view:
            return None
        return self._view.asset_browser.find_display_name_by_offset(offset)

    def _generate_library_thumbnail(self, offset: int) -> Image.Image | None:
        """Generate PIL Image thumbnail for library storage.

        Attempts three strategies in order:
        1. Use current_tile_data if offset matches (already decompressed from preview)
        2. Attempt HAL decompression
        3. Fall back to raw ROM bytes
        """
        if not self.rom_path:
            return None

        data_to_render: bytes | None = None

        # Strategy 1: Use current decompressed data if available
        if self.current_offset == offset and self.current_tile_data:
            data_to_render = self.current_tile_data
            logger.debug("Using current_tile_data for thumbnail: 0x%06X", offset)

        # Strategy 2: Attempt HAL decompression
        if not data_to_render and self.rom_extractor:
            try:
                with open(self.rom_path, "rb") as f:
                    f.seek(offset)
                    chunk = f.read(0x10000)  # Read up to 64KB for decompression

                if chunk:
                    _, decompressed_data, _ = self.rom_extractor.find_compressed_sprite(chunk, 0, expected_size=None)
                    if decompressed_data:
                        data_to_render = decompressed_data
                        logger.debug(
                            "HAL decompressed %d bytes for thumbnail: 0x%06X",
                            len(decompressed_data),
                            offset,
                        )
            except Exception as e:
                logger.debug("HAL decompression failed for thumbnail at 0x%06X: %s", offset, e)

        # Strategy 3: Fall back to raw ROM bytes (original behavior)
        if not data_to_render:
            try:
                with open(self.rom_path, "rb") as f:
                    f.seek(offset)
                    data_to_render = f.read(32 * 64)  # Read up to 64 tiles worth
                logger.debug("Using raw data for thumbnail: 0x%06X", offset)
            except OSError as e:
                logger.error("Failed to read ROM for thumbnail: %s", e)
                return None

        if not data_to_render:
            return None

        # Render tiles
        try:
            from core.tile_renderer import TileRenderer

            tile_count = len(data_to_render) // 32
            if tile_count == 0:
                return None

            # Calculate grid dimensions
            width_tiles = min(8, tile_count)
            height_tiles = (tile_count + width_tiles - 1) // width_tiles

            # Render using TileRenderer (grayscale)
            renderer = TileRenderer()
            image = renderer.render_tiles(data_to_render, width_tiles, height_tiles, palette_index=None)
            return image
        except Exception as e:
            logger.error("Failed to generate thumbnail: %s", e)
            return None

    def _pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        """Convert PIL Image to QPixmap."""
        # Convert to RGBA if needed
        if pil_image.mode != "RGBA":
            pil_image = pil_image.convert("RGBA")

        data = pil_image.tobytes("raw", "RGBA")
        qimage = QImage(
            data,
            pil_image.width,
            pil_image.height,
            pil_image.width * 4,
            QImage.Format.Format_RGBA8888,
        )
        return QPixmap.fromImage(qimage)

    def _on_asset_renamed(self, offset: int, new_name: str) -> None:
        """Handle asset rename from context menu."""
        logger.info("Asset renamed: 0x%06X → %s", offset, new_name)
        # Names are stored in widget's UserRole data, which updates on edit
        # Also update library if this sprite is in the library
        if self.rom_path and self._sprite_library:
            library = self._sprite_library
            rom_hash = library.compute_rom_hash(self.rom_path)
            existing = library.get_by_offset(offset, rom_hash)
            if existing:
                library.update_sprite(existing[0].unique_id, name=new_name)
                logger.info("Updated library sprite name: %s", new_name)

    def _on_asset_deleted(self, offset: int, source_type: str) -> None:
        """Handle asset deletion from context menu."""
        logger.info("Asset deleted: 0x%06X (%s)", offset, source_type)

        # Handle persistent deletion
        if source_type == "library" and self._sprite_library and self.rom_path:
            library = self._sprite_library
            rom_hash = library.compute_rom_hash(self.rom_path)
            matches = library.get_by_offset(offset, rom_hash)
            for sprite in matches:
                library.remove_sprite(sprite.unique_id)
                logger.info("Removed persistent sprite: %s", sprite.unique_id)

        # Remove item from browser tree
        if self._view:
            self._view.asset_browser.remove_sprite_by_offset(offset)

    def _load_library_sprites(self) -> None:
        """Load sprites from library that match current ROM."""
        if not self._view or not self.rom_path or not self._sprite_library:
            return

        library = self._sprite_library
        rom_hash = library.compute_rom_hash(self.rom_path)

        count = 0
        for sprite in library.sprites:
            if sprite.rom_hash == rom_hash:
                # Add to Library category (not ROM Sprites)
                thumbnail = self._load_library_thumbnail(sprite)
                self._view.add_library_sprite(
                    sprite.name,
                    sprite.rom_offset,
                    thumbnail=thumbnail,
                )
                # Request fresh thumbnail
                if self._thumbnail_controller:
                    self._thumbnail_controller.queue_thumbnail(sprite.rom_offset)
                count += 1

        if count > 0:
            logger.info("Loaded %d library sprites for this ROM", count)

    def _load_known_sprite_locations(self) -> None:
        """Load known sprite locations from config for current ROM."""
        if not self._view or not self.rom_path or not self.rom_extractor:
            return

        try:
            locations = self.rom_extractor.get_known_sprite_locations(self.rom_path)
            if not locations:
                logger.debug("No known sprite locations found for this ROM")
                return

            count = 0
            for name, pointer in locations.items():
                # Skip internal notes/documentation entries
                if name.startswith("_"):
                    continue

                self._view.add_rom_sprite(name, pointer.offset)
                # Queue thumbnail generation
                if self._thumbnail_controller:
                    self._thumbnail_controller.queue_thumbnail(pointer.offset)
                count += 1

            if count > 0:
                logger.info("Loaded %d known sprite locations for this ROM", count)
                if self._message_service:
                    self._message_service.show_message(f"Found {count} known sprite locations")

        except Exception:
            logger.exception("Error loading known sprite locations")

    def _load_library_thumbnail(self, sprite: object) -> QPixmap | None:
        """Load thumbnail from library."""
        from core.sprite_library import LibrarySprite

        if not isinstance(sprite, LibrarySprite) or not self._sprite_library:
            return None

        library = self._sprite_library
        path = library.get_thumbnail_path(sprite)
        if path and path.exists():
            return QPixmap(str(path))
        return None

    def browse_rom(self) -> None:
        """Open file dialog to select ROM file."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Open ROM File",
            "",
            "SNES ROMs (*.sfc *.smc);;All Files (*)",
        )
        if file_path:
            self.load_rom(file_path)

    def load_rom(self, path: str) -> None:
        """Load and validate ROM file.

        Validates the ROM header before proceeding. Shows error message
        if the file is not a valid SNES ROM.
        """
        from pathlib import Path

        from core.rom_validator import ROMHeaderError, ROMValidator

        rom_path = Path(path)
        if not rom_path.exists():
            if self._message_service:
                self._message_service.show_message(f"Error: ROM file not found: {path}")
            return

        # Validate ROM file format first
        is_valid, error_msg = ROMValidator.validate_rom_file(path)
        if not is_valid:
            if self._message_service:
                self._message_service.show_message(f"Error: {error_msg}")
            return

        # Validate ROM header - this ensures it's actually a valid SNES ROM
        try:
            header, _ = ROMValidator.validate_rom_header(path)
        except ROMHeaderError as e:
            if self._message_service:
                self._message_service.show_message(f"Error: Invalid ROM - {e}")
            return

        # Clear ROM-specific state (asset browser) but preserve global Mesen capture history
        # so F6 workflow and Recent Captures widget persist across ROM loads
        if self._view:
            self._view.clear_asset_browser()

        self.rom_path = path
        self.rom_size = rom_path.stat().st_size

        # Update view
        if self._view:
            self._view.set_rom_path(path)
            self._view.set_rom_available(True, self.rom_size)

        # Use validated header info
        title = header.title or "Unknown ROM"
        self.rom_info_updated.emit(title)
        if self._view:
            self._view.set_info(title)

        if self._message_service:
            self._message_service.show_message(f"Loaded ROM: {rom_path.name}")

        # Setup thumbnail worker for asset browser
        self._setup_thumbnail_worker()

        # Load library sprites for this ROM
        self._load_library_sprites()

        # Load known sprite locations from config
        self._load_known_sprite_locations()

        # Request thumbnails for any existing assets
        if self._view and self._thumbnail_controller and self.log_watcher:
            persistent_clicks = self.log_watcher.load_persistent_clicks()
            for capture in persistent_clicks:
                self._thumbnail_controller.queue_thumbnail(capture.offset)

        # Trigger initial preview
        self.set_offset(self.current_offset)

    def sync_captures_from_log_watcher(self) -> None:
        """Sync all captures from log watcher to the asset browser.

        Called when entering the sprite editor workspace to ensure all
        discovered captures are visible in the asset browser.
        """
        print(
            f"[DEBUG] sync_captures_from_log_watcher: view={self._view is not None}, log_watcher={self.log_watcher is not None}",
            flush=True,
        )
        if not self._view:
            print("[DEBUG] sync_captures_from_log_watcher: NO VIEW", flush=True)
            logger.warning("sync_captures_from_log_watcher: no view set")
            return
        if not self.log_watcher:
            print("[DEBUG] sync_captures_from_log_watcher: NO LOG_WATCHER", flush=True)
            logger.warning("sync_captures_from_log_watcher: no log_watcher")
            return

        captures = self.log_watcher.recent_captures
        print(f"[DEBUG] sync_captures_from_log_watcher: found {len(captures)} captures", flush=True)
        logger.info(
            "sync_captures_from_log_watcher: found %d captures in log_watcher",
            len(captures),
        )

        # Sync all current session captures
        for capture in captures:
            print(f"[DEBUG]   syncing capture: 0x{capture.offset:06X}", flush=True)
            logger.debug("  syncing capture: 0x%06X", capture.offset)
            self._add_capture_to_browser(capture)

        # Also sync persistent clicks
        persistent = self.log_watcher.load_persistent_clicks()
        print(f"[DEBUG] sync_captures_from_log_watcher: found {len(persistent)} persistent clicks", flush=True)
        logger.info(
            "sync_captures_from_log_watcher: found %d persistent clicks",
            len(persistent),
        )
        for capture in persistent:
            print(f"[DEBUG]   syncing persistent: 0x{capture.offset:06X}", flush=True)
            logger.debug("  syncing persistent: 0x%06X", capture.offset)
            self._add_capture_to_browser(capture)

    def ensure_and_select_capture(self, offset: int, name: str | None = None) -> None:
        """Ensure a Mesen capture exists in the asset browser and select it.

        Called when opening a capture from RecentCapturesWidget to sync with
        the sprite editor's asset browser.

        Args:
            offset: ROM offset of the capture
            name: Display name for the capture (defaults to hex offset)
        """
        print(
            f"[DEBUG] ensure_and_select_capture: offset=0x{offset:06X}, name={name}, view={self._view is not None}, log_watcher={self.log_watcher is not None}",
            flush=True,
        )
        logger.info(
            "ensure_and_select_capture called: offset=0x%06X, name=%s, view=%s, log_watcher=%s",
            offset,
            name,
            self._view is not None,
            self.log_watcher is not None,
        )

        if not self._view:
            print("[DEBUG] ensure_and_select_capture: NO VIEW, returning early", flush=True)
            logger.warning("ensure_and_select_capture: no view, returning early")
            return

        # First sync all captures from log watcher (idempotent - duplicates are skipped)
        print("[DEBUG] ensure_and_select_capture: calling sync_captures_from_log_watcher", flush=True)
        self.sync_captures_from_log_watcher()

        # Then ensure the specific capture exists and select it
        browser = self._view.asset_browser
        print(
            f"[DEBUG] ensure_and_select_capture: calling browser.ensure_mesen_capture(0x{offset:06X}, {name})",
            flush=True,
        )
        browser.ensure_mesen_capture(offset, name)
        browser.select_sprite_by_offset(offset)
        print(f"[DEBUG] ensure_and_select_capture: COMPLETED for offset 0x{offset:06X}", flush=True)
        logger.info("ensure_and_select_capture: completed for offset 0x%06X", offset)

    def set_offset(self, offset: int, *, auto_open: bool = False) -> None:
        """Set current ROM offset and request preview.

        Args:
            offset: ROM offset to navigate to.
            auto_open: If True, automatically open in editor when preview completes.
        """
        print(
            f"[DEBUG] set_offset: offset=0x{offset:06X}, rom_path={self.rom_path}, rom_size=0x{self.rom_size:06X}",
            flush=True,
        )
        # Check ROM availability first
        if not self.rom_path:
            print("[DEBUG] set_offset: NO ROM LOADED, returning early", flush=True)
            if self._message_service:
                self._message_service.show_message("ROM must be loaded first. Click '...' to load a ROM file.")
            return
        print("[DEBUG] set_offset: passed rom_path check", flush=True)

        # Validate offset is within ROM bounds
        if offset < 0 or offset >= self.rom_size:
            print(f"[DEBUG] set_offset: OFFSET OUT OF RANGE (0x{offset:06X} >= 0x{self.rom_size:06X})", flush=True)
            if self._message_service:
                self._message_service.show_message(
                    f"Offset 0x{offset:06X} is out of range (ROM size: 0x{self.rom_size:06X})"
                )
            return
        print("[DEBUG] set_offset: passed bounds check", flush=True)

        # Set flag to auto-open in editor when preview completes
        if auto_open:
            self._pending_open_in_editor = True
            self._pending_open_offset = offset

        # Handle transition from edit state
        print(f"[DEBUG] set_offset: current state={self.state}", flush=True)
        if self.state == "edit":
            print("[DEBUG] set_offset: in edit state, checking unsaved changes", flush=True)
            # Check for unsaved changes first
            if self._editing_controller.has_unsaved_changes():
                from PySide6.QtWidgets import QMessageBox

                reply = QMessageBox.question(
                    self._view,
                    "Unsaved Changes",
                    "You have unsaved changes in the editor. Changing the offset will discard them. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    print("[DEBUG] set_offset: user cancelled, returning", flush=True)
                    # Reset to current offset
                    if self._view:
                        self._view.set_offset(self.current_offset)
                    return

            # Always transition to preview when leaving edit state
            # (whether or not there were unsaved changes)
            self.state = "preview"
            if self._view:
                self._view.set_action_text("Open in Editor")
                self._view.set_workflow_state("preview")
            self.workflow_state_changed.emit("preview")

        print("[DEBUG] set_offset: passed edit state check, proceeding", flush=True)
        self.current_offset = offset
        print(
            f"[DEBUG] set_offset: setting current_offset to 0x{offset:06X}, view={self._view is not None}", flush=True
        )
        if self._view:
            self._view.set_offset(offset)
            print(f"[DEBUG] set_offset: called view.set_offset(0x{offset:06X})", flush=True)

        if self.rom_path:
            # Set loading state before requesting preview
            self._preview_pending = True
            if self._view:
                self._view.set_action_loading(True)
            print(f"[DEBUG] set_offset: requesting preview for 0x{offset:06X}", flush=True)
            self.preview_coordinator.request_manual_preview(offset)

    def handle_primary_action(self) -> None:
        """Handle the state-dependent primary action button."""
        # Ignore clicks while preview is loading
        if self._preview_pending:
            return
        if self.state == "preview":
            self.open_in_editor()
        elif self.state == "edit":
            self.prepare_injection()
        elif self.state == "save":
            self.save_to_rom()

    def open_in_editor(self) -> None:
        """Load the current preview into the pixel editor."""
        logger.debug(f"[OPEN] open_in_editor called, tile_data={self.current_tile_data is not None}")
        if not self.current_tile_data:
            logger.debug("[OPEN] No tile data, returning early")
            if self._message_service:
                self._message_service.show_message("No sprite data to edit")
            return

        # Clear previous ROM palette sources before loading new sprite
        if self._view:
            self._view.clear_rom_palette_sources()

        # Use SpriteRenderer to create PIL image from 4bpp
        from ..core.palette_utils import get_default_snes_palette
        from ..services import SpriteRenderer

        renderer = SpriteRenderer()

        image = renderer.render_4bpp(self.current_tile_data, self.current_width, self.current_height)

        # Convert to numpy and load into editor
        image_array = np.array(image, dtype=np.uint8)

        # Try to extract all ROM palettes if possible
        palette: list[tuple[int, int, int]] | None = None
        all_palettes: dict[int, list[tuple[int, int, int]]] = {}
        detected_palette_index: int | None = None
        palette_offset: int | None = None

        if self.rom_extractor and self.rom_path:
            try:
                # 1. Get header to identify game
                header = self.rom_extractor.read_rom_header(self.rom_path)

                # 2. Get game config
                game_config = self.rom_extractor._find_game_configuration(header)

                if game_config and self.current_sprite_name:
                    from typing import cast

                    # 3. Get palette config for this sprite
                    palette_offset, palette_indices = self.rom_extractor.get_palette_config_from_sprite_config(
                        cast(dict[str, object], game_config),
                        self.current_sprite_name,
                    )

                    # 4. Extract ALL sprite palettes (8-15) if we have an offset
                    if palette_offset is not None:
                        all_palettes = self.rom_extractor.extract_palette_range(self.rom_path, palette_offset, 8, 15)

                        # Register all palettes as switchable sources
                        if all_palettes:
                            self._editing_controller.register_rom_palettes(all_palettes)
                            logger.info(f"Registered {len(all_palettes)} ROM palettes as sources")

                        # Determine which palette to use initially
                        if palette_indices:
                            # Use first available from config
                            detected_palette_index = palette_indices[0]
                        elif all_palettes:
                            # Fall back to first available (usually 8)
                            detected_palette_index = min(all_palettes.keys())

                        # Get the actual palette colors
                        if detected_palette_index and detected_palette_index in all_palettes:
                            palette = all_palettes[detected_palette_index]
                            logger.info(
                                f"Auto-selected ROM palette {detected_palette_index} for {self.current_sprite_name}"
                            )

            except Exception as e:
                logger.warning(f"Failed to extract ROM palettes: {e}")

        # Fallback to default SNES-style palette
        if palette is None:
            palette = get_default_snes_palette()
            logger.debug("Using default SNES palette")
            # Inform user about default palette for manual offsets
            if self._message_service and self.current_sprite_name.startswith("manual_0x"):
                self._message_service.show_message("Using default palette (ROM palette not available for this offset)")

        logger.debug(f"[OPEN] Loading image into editor: {image_array.shape}")
        self._editing_controller.load_image(image_array, palette)

        # Auto-select the palette source in dropdown if we detected one
        if detected_palette_index and all_palettes:
            self._editing_controller.set_palette_source("rom", detected_palette_index)
            if self._message_service:
                palette_count = len(all_palettes)
                self._message_service.show_message(
                    f"Using ROM Palette {detected_palette_index} ({palette_count} palettes available in dropdown)"
                )

        # Change state
        self.state = "edit"
        if self._view:
            self._view.set_action_text("Save to ROM")
            self._view.set_workflow_state("edit")
        self.workflow_state_changed.emit("edit")
        logger.debug("[OPEN] Sprite loaded in editor, state changed to 'edit'")

    def revert_to_original(self) -> None:
        """Revert the current sprite to its original ROM data.

        Shows a confirmation dialog if there are unsaved changes,
        then reloads the sprite from the original tile data.
        """
        # Check if we're in edit state with data to revert
        if self.state != "edit" or not self.current_tile_data:
            if self._message_service:
                self._message_service.show_message("No sprite loaded to revert")
            return

        # Check for unsaved changes and confirm with user
        if self._editing_controller.has_unsaved_changes():
            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self._view,
                "Revert to Original",
                "This will discard all your edits and reload the original sprite from ROM.\n\n"
                "Are you sure you want to revert?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # Reload the original sprite data
        logger.info("Reverting sprite to original ROM data at offset 0x%06X", self.current_offset)
        self.open_in_editor()

        if self._message_service:
            self._message_service.show_message("Sprite reverted to original ROM data")

    def prepare_injection(self) -> None:
        """Transition from editing to save confirmation with size comparison."""
        # Block injection if HAL decompression failed (raw fallback was used)
        if not self.hal_decompression_succeeded:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self._view,
                "Cannot Inject",
                "This offset doesn't contain a valid HAL-compressed sprite.\n\n"
                "The preview was generated from raw ROM bytes because HAL decompression failed.\n"
                "Injecting at this offset would corrupt the ROM.\n\n"
                "Please select a valid sprite offset.",
            )
            return

        data = self._editing_controller.get_image_data()
        if data is None:
            if self._message_service:
                self._message_service.show_message("No image to inject")
            return

        # Calculate new compressed size
        try:
            from core.hal_compression import HALCompressor

            from ..services import ImageConverter

            converter = ImageConverter()

            # Convert to 4bpp tiles
            img = Image.fromarray(data, mode="P")
            img.putpalette(self._editing_controller.get_flat_palette())

            # Simple conversion for size estimation
            tiles = converter.image_to_tiles(img)

            import tempfile
            from pathlib import Path

            compressor = HALCompressor()
            with tempfile.NamedTemporaryFile(suffix=".hal", delete=False) as tmp:
                compressed_path = tmp.name

            try:
                new_size = compressor.compress_to_file(tiles, compressed_path)
            finally:
                Path(compressed_path).unlink(missing_ok=True)

            # Show confirmation dialog
            from PySide6.QtWidgets import QMessageBox

            msg = "Ready to inject edited sprite into ROM.\n\n"
            msg += f"Target Offset: 0x{self.current_offset:06X}\n"
            msg += f"Original Size: {self.original_compressed_size} bytes\n"

            # Use max 32 bytes slack by default for safety
            safe_slack = min(self.available_slack, 32)
            if self.available_slack > 0:
                msg += f"Available Space: {self.original_compressed_size + safe_slack} bytes "
                msg += f"({self.original_compressed_size} + {safe_slack} slack)\n"

            msg += f"New Size: {new_size} bytes\n\n"

            if new_size > (self.original_compressed_size + safe_slack):
                msg += "⚠️ WARNING: New sprite is LARGER than available space. "
                msg += "This WILL overwrite adjacent data and likely crash the game!\n\n"
            elif new_size > self.original_compressed_size:
                msg += "NOTE: New sprite is slightly larger than original, "
                msg += (
                    f"but fits within detected slack space ({new_size - self.original_compressed_size} bytes used).\n\n"
                )

            msg += "A backup of the ROM will be created automatically.\n"
            msg += "Proceed with injection?"

            reply = QMessageBox.question(
                self._view, "Confirm ROM Injection", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.save_to_rom()

        except Exception as e:
            logger.exception("Error during injection preparation")
            if self._message_service:
                self._message_service.show_message(f"Error: {e}")

    def save_to_rom(self) -> None:
        """Inject edited sprite back to ROM."""
        if not self.rom_extractor:
            if self._message_service:
                self._message_service.show_message("ROM extractor not initialized")
            return

        data = self._editing_controller.get_image_data()
        if data is None:
            if self._message_service:
                self._message_service.show_message("No image to save")
            return

        try:
            if self._message_service:
                self._message_service.show_message(f"Saving to ROM at 0x{self.current_offset:06X}...")

            # Create PIL image for conversion
            img = Image.fromarray(data, mode="P")
            img.putpalette(self._editing_controller.get_flat_palette())

            # Save to temp PNG for injector
            import tempfile
            from pathlib import Path

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                img.save(f.name, "PNG")
                temp_png = f.name

            # Perform injection with backup (via facade method)
            # First attempt (standard validation)
            success, message = self.rom_extractor.inject_sprite_to_rom(
                sprite_path=temp_png,
                rom_path=self.rom_path,
                output_path=self.rom_path,
                sprite_offset=self.current_offset,
                create_backup=True,
            )

            # Handle failure due to checksum mismatch
            if not success and "ROM checksum mismatch" in message:
                from PySide6.QtWidgets import QMessageBox

                reply = QMessageBox.question(
                    self._view,
                    "ROM Checksum Mismatch",
                    f"Validation failed: {message}\n\n"
                    "This usually happens with modified/patched ROMs.\n"
                    "Do you want to ignore this warning and proceed anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )

                if reply == QMessageBox.StandardButton.Yes:
                    if self._message_service:
                        self._message_service.show_message("Retrying with lenient checksum validation...")
                    success, message = self.rom_extractor.inject_sprite_to_rom(
                        sprite_path=temp_png,
                        rom_path=self.rom_path,
                        output_path=self.rom_path,
                        sprite_offset=self.current_offset,
                        create_backup=True,
                        ignore_checksum=True,
                    )

            # Handle failure due to compressed size too large
            if not success and "Compressed sprite too large" in message:
                from PySide6.QtWidgets import QMessageBox

                reply = QMessageBox.warning(
                    self._view,
                    "Sprite Too Large",
                    f"{message}\n\n"
                    "⚠️ FORCE INJECTION WARNING ⚠️\n\n"
                    "Force injecting will overwrite adjacent ROM data, which may:\n"
                    "• Corrupt other sprites or game data\n"
                    "• Cause the game to crash or glitch\n\n"
                    "A backup of your ROM will be created first.\n\n"
                    "Do you want to force inject anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,  # Default to No
                )

                if reply == QMessageBox.StandardButton.Yes:
                    if self._message_service:
                        self._message_service.show_message("Force injecting (backup created)...")
                    success, message = self.rom_extractor.inject_sprite_to_rom(
                        sprite_path=temp_png,
                        rom_path=self.rom_path,
                        output_path=self.rom_path,
                        sprite_offset=self.current_offset,
                        create_backup=True,
                        force=True,
                    )

            # Cleanup temp file
            try:
                Path(temp_png).unlink()
            except OSError:
                pass

            if success:
                if self._message_service:
                    self._message_service.show_message(f"Successfully saved: {message}")
                # Show success in view
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(
                    self._view,
                    "Save Successful",
                    f"Sprite injected successfully at 0x{self.current_offset:06X}.\n\n{message}",
                )

                # Back to edit state
                self.state = "edit"
                if self._view:
                    self._view.set_action_text("Save to ROM")
                    self._view.set_workflow_state("edit")
                    # Trigger a re-preview to verify
                    self.set_offset(self.current_offset)
            else:
                if self._message_service:
                    self._message_service.show_message(f"Injection failed: {message}")
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(self._view, "Injection Failed", f"Failed to inject sprite: {message}")

        except Exception as e:
            logger.exception("Error during ROM injection")
            if self._message_service:
                self._message_service.show_message(f"Error saving to ROM: {e}")
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self._view, "Error", f"An error occurred during injection: {e}")

    def export_png(self) -> None:
        """Export current sprite as PNG file."""
        data = self._editing_controller.get_image_data()
        if data is None:
            if self._message_service:
                self._message_service.show_message("No image to export")
            return

        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self._view,
            "Export PNG",
            f"sprite_0x{self.current_offset:06X}.png",
            "PNG Files (*.png);;All Files (*)",
        )

        if not file_path:
            return

        try:
            # Create PIL image for export
            img = Image.fromarray(data, mode="P")
            img.putpalette(self._editing_controller.get_flat_palette())
            img.save(file_path, "PNG")
            if self._message_service:
                self._message_service.show_message(f"Exported to: {file_path}")

            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self._view, "Export Successful", f"Sprite exported to:\n{file_path}")

        except Exception as e:
            logger.exception("Error during PNG export")
            if self._message_service:
                self._message_service.show_message(f"Error exporting PNG: {e}")

            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self._view, "Export Failed", f"Failed to export PNG: {e}")

    def _get_rom_data_for_preview(self) -> tuple[str, object] | None:
        """Provide ROM data for smart preview coordinator."""
        if not self.rom_path:
            return None
        return (self.rom_path, self.rom_extractor)

    def _on_preview_ready(
        self,
        tile_data: bytes,
        width: int,
        height: int,
        sprite_name: str,
        compressed_size: int,
        slack_size: int = 0,
        actual_offset: int = -1,
        hal_succeeded: bool = True,
    ) -> None:
        """Handle preview ready from coordinator."""
        # Use current offset if actual_offset not provided
        if actual_offset == -1:
            actual_offset = self.current_offset

        # Check if offset was adjusted during preview (e.g. alignment correction)
        offset_adjusted = actual_offset != self.current_offset
        if offset_adjusted:
            logger.info(
                f"[PREVIEW] Offset adjusted from 0x{self.current_offset:06X} to 0x{actual_offset:06X} "
                f"(delta: {actual_offset - self.current_offset:+d})"
            )
            # Update current offset to match reality
            self.current_offset = actual_offset
            # Update UI
            if self._view:
                self._view.set_offset(actual_offset)
                if self._message_service:
                    self._message_service.show_message(
                        f"Aligned to valid sprite at 0x{actual_offset:06X} "
                        f"(adjusted by {actual_offset - self.current_offset:+d} bytes)"
                    )

        logger.debug(
            f"[PREVIEW] _on_preview_ready called: {len(tile_data)} bytes, {width}x{height}, "
            f"pending_open={self._pending_open_in_editor}, offset=0x{actual_offset:06X}, hal={hal_succeeded}"
        )
        self.current_tile_data = tile_data
        self.current_width = width
        self.current_height = height
        self.current_sprite_name = sprite_name
        self.original_compressed_size = compressed_size
        self.available_slack = slack_size
        self.hal_decompression_succeeded = hal_succeeded

        # Clear loading state
        self._preview_pending = False
        if self._view:
            self._view.set_action_loading(False)
            self._view.set_action_text("Open in Editor")

        if self._view:
            if hal_succeeded:
                slack_info = f" (+{slack_size} slack)" if slack_size > 0 else ""
                msg = f"Sprite found! Original size: {compressed_size} bytes{slack_info}"
                if offset_adjusted:
                    msg += f" (Aligned to 0x{actual_offset:06X})"
            else:
                msg = "Raw data preview (HAL decompression failed). Cannot inject at this offset."

            if self._message_service:
                self._message_service.show_message(msg)

        # Auto-open in editor if triggered by double-click
        logger.debug(f"[PREVIEW] Checking flag: _pending_open_in_editor={self._pending_open_in_editor}")
        if self._pending_open_in_editor:
            # Only auto-open if offset matches (prevents stale opens after errors/navigation)
            if self._pending_open_offset in (-1, actual_offset):
                logger.debug("[PREVIEW] Flag is True and offset matches, calling open_in_editor()")
                self._pending_open_in_editor = False
                self._pending_open_offset = -1
                self.open_in_editor()
            else:
                # Offset mismatch means a newer request is pending - don't clear flags,
                # let the matching preview handle them when it arrives
                logger.debug(
                    f"[PREVIEW] Offset mismatch: pending=0x{self._pending_open_offset:X} "
                    f"vs actual=0x{actual_offset:X}, keeping flags for pending request"
                )

    def _on_preview_error(self, error_msg: str) -> None:
        """Handle preview error."""
        self.current_tile_data = None
        # Clear pending flags to prevent stale auto-opens after errors
        self._pending_open_in_editor = False
        self._pending_open_offset = -1
        # Clear loading state
        self._preview_pending = False
        if self._view:
            self._view.set_action_loading(False)
            self._view.set_action_text("Open in Editor")
        if self._message_service:
            self._message_service.show_message(f"Preview error: {error_msg}")

    def cleanup(self) -> None:
        """Clean up resources."""
        self.preview_coordinator.cleanup()
        if self._thumbnail_controller:
            self._thumbnail_controller.cleanup()
            self._thumbnail_controller = None
