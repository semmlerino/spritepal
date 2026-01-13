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
from core.types import CompressionType
from ui.common.smart_preview_coordinator import SmartPreviewCoordinator
from ui.workers.batch_thumbnail_worker import ThumbnailWorkerController
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from PySide6.QtCore import QPoint

    from core.arrangement_persistence import ArrangementConfig
    from core.color_quantization import QuantizationResult
    from core.mesen_integration.log_watcher import LogWatcher
    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache
    from core.sprite_library import SpriteLibrary
    from ui.managers.status_bar_manager import StatusBarManager

    from ..services.arrangement_bridge import ArrangementBridge
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
    sprite_extracted = Signal(object, int)  # image, tile_count - for integration (e.g. history)
    offset_changed = Signal(int)  # Emitted when offset changes (for sync with other UI)

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
        self.rom_size: int = 0  # Actual ROM size (excluding SMC header)
        self.smc_header_offset: int = 0  # SMC header size (512 or 0)
        self._rom_mtime: float | None = None  # ROM file mtime for external modification detection
        self.current_offset: int = 0
        self._checksum_valid: bool = True
        self._loaded_rom_checksum: int | None = None  # SNES internal checksum for capture validation
        self.state: str = "preview"  # 'preview', 'edit', 'save'

        # Current sprite data
        self.current_tile_data: bytes | None = None
        self.current_width: int = 0
        self.current_height: int = 0
        self.current_sprite_name: str = ""
        self.original_compressed_size: int = 0
        self.available_slack: int = 0
        self.current_compression_type: CompressionType = CompressionType.UNKNOWN
        # Header bytes stripped during alignment (prepended back during injection to prevent color shift)
        self.current_header_bytes: bytes = b""

        # Tile arrangement state (for scattered tile layouts)
        self._current_arrangement: ArrangementBridge | None = None
        self._arrangement_config: ArrangementConfig | None = None

        # Flag for auto-opening in editor after preview completes (double-click)
        self._pending_open_in_editor: bool = False
        self._pending_open_offset: int = -1  # Track which offset triggered pending

        # Flag for preview loading state (used to disable action button)
        self._preview_pending: bool = False

        # Thumbnail worker controller
        self._thumbnail_controller: ThumbnailWorkerController | None = None

        # Queue for captures discovered before view is ready
        self._pending_captures: list[CapturedOffset] = []

        # Connect editing controller validation signal
        self._editing_controller.validationChanged.connect(self._on_validation_changed)

        # Connect palette source changes to hide warning when user loads custom palette
        self._editing_controller.paletteSourceSelected.connect(self._on_palette_source_changed)

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

    def normalize_mesen_offset(self, offset: int) -> int:
        """Convert Mesen FILE OFFSET (file-based) to ROM offset (headerless)."""
        if self.smc_header_offset <= 0:
            return offset
        if offset < self.smc_header_offset:
            return offset
        normalized = offset - self.smc_header_offset
        logger.debug(
            "[CAPTURE] Normalized Mesen FILE OFFSET 0x%06X -> 0x%06X (SMC header %d bytes)",
            offset,
            normalized,
            self.smc_header_offset,
        )
        return normalized

    def _get_capture_name(self, capture: CapturedOffset) -> str:
        """Generate display name for captured sprite."""
        rom_offset = self.normalize_mesen_offset(capture.offset)
        if capture.frame is not None:
            return f"0x{rom_offset:06X} (F{capture.frame})"
        else:
            # Fallback to timestamp if no frame
            timestamp_str = capture.timestamp.strftime("%H:%M:%S")
            return f"0x{rom_offset:06X} ({timestamp_str})"

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

    def _validate_capture_rom_match(self, capture: CapturedOffset) -> bool:
        """Check if capture's ROM checksum matches the currently loaded ROM.

        Returns True if:
        - Checksums match
        - Capture has no checksum (legacy capture, backward compatible)
        - No ROM is loaded yet

        Returns False (with warning) if checksums differ, indicating the capture
        may be from a different ROM than the one currently loaded.
        """
        if capture.rom_checksum is None:
            # Legacy capture without checksum - allow silently
            return True
        if self._loaded_rom_checksum is None:
            # No ROM loaded yet - can't validate
            return True
        if capture.rom_checksum == self._loaded_rom_checksum:
            return True

        # Checksum mismatch - show warning
        if self._message_service:
            self._message_service.show_message(
                f"Warning: Capture 0x{capture.offset:06X} may be from a different ROM "
                f"(capture: 0x{capture.rom_checksum:04X}, loaded: 0x{self._loaded_rom_checksum:04X})"
            )
        logger.warning(
            "ROM checksum mismatch for capture 0x%06X: capture=0x%04X, loaded=0x%04X",
            capture.offset,
            capture.rom_checksum,
            self._loaded_rom_checksum,
        )
        return False

    def _add_capture_to_browser(self, capture: CapturedOffset) -> None:
        """Add a capture to the browser with thumbnail."""
        if not self._view:
            return

        # Validate ROM identity (warn if mismatch but still add)
        self._validate_capture_rom_match(capture)

        rom_offset = self.normalize_mesen_offset(capture.offset)
        name = self._get_capture_name(capture)
        self._view.add_mesen_capture(name, rom_offset)

        # Request thumbnail if worker is ready
        if self._thumbnail_controller:
            self._thumbnail_controller.queue_thumbnail(rom_offset)

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
        self._view.asset_browser.item_offset_changed.connect(self._on_item_offset_changed)

        # EditWorkspace signals (save/export)
        self._view.workspace.saveToRomRequested.connect(self.prepare_injection)
        self._view.workspace.exportPngRequested.connect(self.export_png)
        self._view.workspace.saveProjectRequested.connect(self.save_sprite_project)
        self._view.workspace.loadProjectRequested.connect(self.load_sprite_project)
        self._view.workspace.importImageRequested.connect(self.show_import_dialog)
        self._view.workspace.arrangeClicked.connect(self.show_arrangement_dialog)

        # Palette panel signals
        if self._view.workspace and self._view.workspace.palette_panel:
            self._view.workspace.palette_panel.manualPaletteRequested.connect(self._on_manual_palette_requested)

        # Overlay panel signals
        if self._view.workspace and self._view.workspace.overlay_panel:
            self._view.workspace.overlay_panel.importRequested.connect(self._on_overlay_import_requested)
            self._view.workspace.overlay_panel.applyRequested.connect(self._on_apply_overlay)
            self._view.workspace.overlay_panel.cancelRequested.connect(self._on_cancel_overlay)
            self._view.workspace.overlay_panel.baseOpacityChanged.connect(self._on_base_opacity_changed)
            self._view.workspace.overlay_panel.overlayOpacityChanged.connect(self._on_overlay_opacity_changed)
            self._view.workspace.overlay_panel.positionChanged.connect(self._on_overlay_position_changed)

    def _on_sprite_selected(self, offset: int, source_type: str) -> None:
        """Handle sprite selection from asset browser."""
        self.set_offset(offset)

    def _on_sprite_activated(self, offset: int, source_type: str) -> None:
        """Handle sprite activation (double-click) - enter edit mode."""
        logger.debug(f"[DOUBLE-CLICK] _on_sprite_activated called: offset=0x{offset:06X}, source={source_type}")

        # If we already have tile data for this offset, open directly without re-requesting preview
        if self.current_offset == offset and self.current_tile_data:
            logger.debug("[DOUBLE-CLICK] Already have data for this offset, requesting full preview before opening")
            self.set_offset(offset, auto_open=True)
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
        # Returns None if persistence failed - in that case, don't update UI
        sprite = library.add_sprite(
            rom_offset=offset,
            rom_path=self.rom_path,
            name=name,
            thumbnail=pil_thumbnail,
        )

        if sprite is None:
            logger.error("Failed to save sprite to library: persistence failed for 0x%06X", offset)
            if self._message_service:
                self._message_service.show_message("Failed to save sprite to library (disk write error)")
            return

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

    def _on_item_offset_changed(self, old_offset: int, new_offset: int) -> None:
        """Re-queue thumbnail when item's offset changes due to alignment.

        This handler is automatically triggered when update_sprite_offset() changes
        a browser item's offset, ensuring the thumbnail matches the new offset.
        """
        if self._thumbnail_controller:
            self._thumbnail_controller.queue_thumbnail(new_offset)
            logger.debug("Re-queued thumbnail for aligned offset 0x%06X (was 0x%06X)", new_offset, old_offset)

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
        # Store SMC header offset and calculate actual ROM size
        # header.header_offset is 512 for SMC-headered ROMs, 0 otherwise
        self.smc_header_offset = header.header_offset
        stat_result = rom_path.stat()
        file_size = stat_result.st_size
        self.rom_size = file_size - self.smc_header_offset
        self._rom_mtime = stat_result.st_mtime  # Track for external modification detection
        self._loaded_rom_checksum = header.checksum  # Store for capture validation

        # Update view
        if self._view:
            self._view.set_rom_path(path)
            self._view.set_rom_available(True, self.rom_size)

        # Use validated header info
        title = header.title or "Unknown ROM"
        self.rom_info_updated.emit(title)
        if self._view:
            self._view.set_info(title)
            # Set ROM mapping type for correct SNES address parsing (LoROM, HiROM, SA-1)
            self._view.set_mapping_type(header.mapping_type)
            # Set SMC header offset for file-to-ROM offset conversion
            self._view.set_header_offset(self.smc_header_offset)

        # Check ROM checksum early and warn user if invalid
        self._checksum_valid = ROMValidator.verify_rom_checksum(path, header, lenient=True)
        if self._view:
            self._view.set_checksum_valid(self._checksum_valid)
            if not self._checksum_valid:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self._view,
                    "ROM Checksum Mismatch",
                    f"The ROM '{rom_path.name}' has an invalid checksum.\n\n"
                    "This usually means the ROM has been modified or patched.\n"
                    "Injecting sprites into this ROM will require confirmation to skip validation.",
                )

        if self._message_service:
            self._message_service.show_message(f"Loaded ROM: {rom_path.name}")

        # Setup thumbnail worker for asset browser
        self._setup_thumbnail_worker()

        # Load library sprites for this ROM
        self._load_library_sprites()

        # Load known sprite locations from config
        self._load_known_sprite_locations()

        # Re-populate Mesen captures after clear_asset_browser() removed them
        # This must happen AFTER _setup_thumbnail_worker() so _add_capture_to_browser()
        # can queue thumbnail requests (the queue is a no-op if worker doesn't exist)
        if self._view:
            self.sync_captures_from_log_watcher()

        # Trigger initial preview
        self.set_offset(self.current_offset)

    def sync_captures_from_log_watcher(self) -> None:
        """Sync all captures from log watcher to the asset browser.

        Called when entering the sprite editor workspace to ensure all
        discovered captures are visible in the asset browser.
        """
        if not self._view:
            logger.warning("sync_captures_from_log_watcher: no view set")
            return
        if not self.log_watcher:
            logger.warning("sync_captures_from_log_watcher: no log_watcher")
            return

        captures = self.log_watcher.recent_captures
        logger.info(
            "sync_captures_from_log_watcher: found %d captures in log_watcher",
            len(captures),
        )

        # Sync all current session captures
        for capture in captures:
            logger.debug("  syncing capture: 0x%06X", capture.offset)
            self._add_capture_to_browser(capture)

        # Also sync persistent clicks
        persistent = self.log_watcher.load_persistent_clicks()
        logger.info(
            "sync_captures_from_log_watcher: found %d persistent clicks",
            len(persistent),
        )
        for capture in persistent:
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
        logger.info(
            "ensure_and_select_capture called: offset=0x%06X, name=%s, view=%s, log_watcher=%s",
            offset,
            name,
            self._view is not None,
            self.log_watcher is not None,
        )

        if not self._view:
            logger.warning("ensure_and_select_capture: no view, returning early")
            return

        # First sync all captures from log watcher (idempotent - duplicates are skipped)
        self.sync_captures_from_log_watcher()

        # Then ensure the specific capture exists and select it
        browser = self._view.asset_browser
        browser.ensure_mesen_capture(offset, name)
        browser.select_sprite_by_offset(offset)
        logger.info("ensure_and_select_capture: completed for offset 0x%06X", offset)

    def set_offset(self, offset: int, *, auto_open: bool = False) -> None:
        """Set current ROM offset and request preview.

        Args:
            offset: ROM offset to navigate to.
            auto_open: If True, automatically open in editor when preview completes.
        """
        # Check ROM availability first
        if not self.rom_path:
            if self._message_service:
                self._message_service.show_message("ROM must be loaded first. Click '...' to load a ROM file.")
            return

        # Validate offset is within ROM bounds
        if offset < 0 or offset >= self.rom_size:
            if self._message_service:
                self._message_service.show_message(
                    f"Offset 0x{offset:06X} is out of range (ROM size: 0x{self.rom_size:06X})"
                )
            return

        # Set flag to auto-open in editor when preview completes
        if auto_open:
            self._pending_open_in_editor = True
            self._pending_open_offset = offset

        # Handle transition from edit state
        if self.state == "edit":
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

        self.current_offset = offset
        self._clear_arrangement()  # Clear arrangement when changing offset
        if self._view:
            self._view.set_offset(offset)

        # Emit change for external listeners (e.g. MainWindow toolbar)
        self.offset_changed.emit(offset)

        if self.rom_path:
            # Set loading state before requesting preview
            self._preview_pending = True
            if self._view:
                self._view.set_action_loading(True)
            # Use full decompression if we're going to open in editor (prevents 4KB truncation)
            if self._pending_open_in_editor:
                logger.debug(f"[SET_OFFSET] Using full preview for offset 0x{offset:06X} (pending open)")
                self.preview_coordinator.request_full_preview(offset)
            else:
                self.preview_coordinator.request_manual_preview(offset)

    def handle_primary_action(self) -> None:
        """Handle the state-dependent primary action button."""
        # Ignore clicks while preview is loading
        if self._preview_pending:
            return
        if self.state == "preview":
            # Always request full decompression before opening to avoid truncated previews.
            self.set_offset(self.current_offset, auto_open=True)
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
        # Warn if raw sprite (no HAL compression)
        if self.current_compression_type == CompressionType.RAW:
            logger.info("[OPEN] Opening raw sprite (no HAL compression)")
            if self._message_service:
                self._message_service.show_message("Opening raw sprite (will be injected without compression)")

        # Clear previous ROM palette sources and warnings before loading new sprite
        if self._view:
            self._view.clear_rom_palette_sources()
            self._view.hide_palette_warning()

        # Check for saved arrangement if none currently loaded
        if self._current_arrangement is None:
            self._load_existing_arrangement()

        # Use SpriteRenderer to create PIL image from 4bpp
        from ..core.palette_utils import get_default_snes_palette
        from ..services import SpriteRenderer

        renderer = SpriteRenderer()

        # Recalculate dimensions from actual tile_data to ensure correctness
        # This handles edge cases where cached dimensions came from truncated preview data
        num_tiles = len(self.current_tile_data) // 32
        if num_tiles > 0:
            TILES_PER_ROW = 16
            tile_rows = (num_tiles + TILES_PER_ROW - 1) // TILES_PER_ROW
            calculated_width = min(TILES_PER_ROW * 8, 384)
            calculated_height = min(tile_rows * 8, 384)

            # Update stored dimensions if they differ (indicates truncation issue)
            if calculated_width != self.current_width or calculated_height != self.current_height:
                logger.info(
                    f"[OPEN] Correcting dimensions from {self.current_width}x{self.current_height} "
                    f"to {calculated_width}x{calculated_height} ({num_tiles} tiles)"
                )
                self.current_width = calculated_width
                self.current_height = calculated_height

        image = renderer.render_4bpp(self.current_tile_data, self.current_width, self.current_height)

        # Convert to numpy and load into editor
        image_array = np.array(image, dtype=np.uint8)

        # Apply arrangement transformation (physical → logical) if active
        if self._current_arrangement and self._current_arrangement.has_arrangement:
            try:
                image_array = self._current_arrangement.physical_to_logical(image_array)
                logger.info("[OPEN] Applied arrangement: physical → logical transformation")
            except Exception as e:
                logger.warning("Failed to apply arrangement transformation: %s", e)
                self._clear_arrangement()

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

                        # Get semantic descriptions for palettes (if available in config)
                        descriptions = self.rom_extractor.get_palette_descriptions_from_config(
                            cast(dict[str, object], game_config)
                        )

                        # Register all palettes as switchable sources with descriptions
                        if all_palettes:
                            self._editing_controller.register_rom_palettes(
                                all_palettes,
                                active_indices=None,  # TODO: Get from OAM analysis when available
                                descriptions=descriptions,
                            )
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
            # Show warning banner and status message for fallback
            if self._view:
                self._view.show_palette_warning(
                    "Using default palette. ROM palette configuration not available for this offset."
                )
            if self._message_service and self.current_sprite_name.startswith("manual_0x"):
                self._message_service.show_message("Using default palette (ROM palette not available for this offset)")
        elif self._view:
            # Hide any previous warning when we have proper palette
            self._view.hide_palette_warning()

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
            # Enable save project button and arrange tiles when sprite is loaded for editing
            if self._view.workspace:
                self._view.workspace.set_save_project_enabled(True)
                self._view.workspace.set_arrange_enabled(True)
        self.workflow_state_changed.emit("edit")

        # Emit sprite_extracted for external listeners (e.g. history, status)
        tile_count = len(self.current_tile_data) // 32 if self.current_tile_data else 0
        self.sprite_extracted.emit(image, tile_count)

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

        # Check if ROM file was modified externally since we loaded it
        from pathlib import Path

        rom_mtime_changed = False
        if self.rom_path and self._rom_mtime is not None:
            try:
                current_mtime = Path(self.rom_path).stat().st_mtime
                rom_mtime_changed = current_mtime != self._rom_mtime
            except OSError:
                pass  # File may have been deleted - will fail on open_in_editor anyway

        if rom_mtime_changed:
            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.warning(
                self._view,
                "ROM Modified Externally",
                "The ROM file has been modified by another program since it was loaded.\n\n"
                "The cached sprite data may be out of date.\n\n"
                "Do you want to reload from the current ROM file?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Update mtime and re-extract fresh data from ROM
                self._rom_mtime = Path(self.rom_path).stat().st_mtime
                self.set_offset(self.current_offset)  # Re-extract from ROM
                if self._message_service:
                    self._message_service.show_message("Reloading sprite from modified ROM...")
                return

        # Reload the original sprite data
        logger.info("Reverting sprite to original ROM data at offset 0x%06X", self.current_offset)
        self.open_in_editor()

        if self._message_service:
            self._message_service.show_message("Sprite reverted to original ROM data")

    def show_arrangement_dialog(self) -> None:
        """Open the tile arrangement dialog.

        Allows users to rearrange scattered tiles into a contiguous layout
        for easier editing. The arrangement is persisted to a sidecar file
        so it can be reloaded across sessions.
        """
        if not self.current_tile_data:
            if self._message_service:
                self._message_service.show_message("No sprite data to arrange")
            return

        # Create a temporary PNG from the current tile data for the dialog
        import tempfile
        from pathlib import Path

        from ..services import SpriteRenderer

        renderer = SpriteRenderer()
        image = renderer.render_4bpp(self.current_tile_data, self.current_width, self.current_height)

        # Save to temp file for dialog
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            image.save(f.name, "PNG")
            temp_png = f.name

        try:
            from ui.grid_arrangement_dialog import GridArrangementDialog

            # Calculate grid dimensions from tile data
            tiles_per_row = min(16, self.current_width // 8) if self.current_width > 0 else 16

            dialog = GridArrangementDialog(temp_png, tiles_per_row, self._view)
            dialog.setWindowTitle(f"Arrange Tiles - {self.current_sprite_name}")

            if dialog.exec():
                result = dialog.arrangement_result
                if result and result.bridge.has_arrangement:
                    self._current_arrangement = result.bridge
                    self._save_arrangement_config(result.metadata)

                    if self._message_service:
                        self._message_service.show_message("Arrangement applied. Editing in logical view.")

                    # Reload in editor with arrangement applied
                    self.open_in_editor()
                elif self._message_service:
                    self._message_service.show_message("No arrangement created")

        finally:
            # Cleanup temp file
            try:
                Path(temp_png).unlink()
            except OSError:
                pass

    def _load_existing_arrangement(self) -> None:
        """Check for saved arrangement and notify user.

        Called when opening a sprite in editor. If a saved arrangement exists,
        notifies the user they can re-apply it via the Arrange Tiles button.

        Note: Full auto-reconstruction would require rebuilding the manager/processor
        state from the tile image, which is complex. For now we just detect that
        an arrangement was saved and prompt the user to re-create it.
        """
        from core.arrangement_persistence import ArrangementConfig

        if not self.rom_path or not self.current_offset:
            return

        if not ArrangementConfig.exists_for(self.rom_path, self.current_offset):
            return

        try:
            sidecar_path = ArrangementConfig.get_sidecar_path(self.rom_path, self.current_offset)
            config = ArrangementConfig.load(sidecar_path)
            self._arrangement_config = config

            # Just store config for reference; user can re-apply via dialog
            logger.info(
                "Found saved arrangement for 0x%06X (%d tiles)",
                self.current_offset,
                len(config.arrangement_order),
            )

            if self._message_service:
                self._message_service.show_message(
                    f"Saved arrangement found ({len(config.arrangement_order)} tiles). "
                    "Click 'Arrange Tiles' to re-apply."
                )

        except Exception as e:
            logger.warning("Failed to read arrangement config: %s", e)
            self._arrangement_config = None

    def _save_arrangement_config(self, metadata: dict[str, object]) -> None:
        """Save arrangement configuration to sidecar file.

        Args:
            metadata: Arrangement metadata from GridArrangementManager
        """
        from core.arrangement_persistence import ArrangementConfig

        if not self.rom_path or not self.current_offset:
            return

        try:
            config = ArrangementConfig.from_metadata(
                metadata,
                self.rom_path,
                self.current_offset,
                self.current_sprite_name,
            )

            sidecar_path = ArrangementConfig.get_sidecar_path(self.rom_path, self.current_offset)
            config.save(sidecar_path)
            self._arrangement_config = config

            logger.info("Saved arrangement to %s", sidecar_path)

        except Exception as e:
            logger.warning("Failed to save arrangement: %s", e)
            if self._message_service:
                self._message_service.show_message(f"Warning: Failed to save arrangement: {e}")

    def _clear_arrangement(self) -> None:
        """Clear current arrangement state."""
        self._current_arrangement = None
        self._arrangement_config = None

    def show_import_dialog(self) -> None:
        """Open the image import dialog to import an external image.

        Only available when in edit state with a sprite loaded.
        Shows the ImageImportDialog which handles color quantization.
        """
        if self.state != "edit":
            if self._message_service:
                self._message_service.show_message("Open a sprite in editor first")
            return

        # Get current image size for target dimensions
        data = self._editing_controller.get_image_data()
        if data is None:
            if self._message_service:
                self._message_service.show_message("No sprite loaded")
            return

        target_size = (data.shape[1], data.shape[0])  # (width, height)

        from ui.dialogs.image_import_dialog import ImageImportDialog

        dialog = ImageImportDialog(self._view, target_size=target_size)
        dialog.import_requested.connect(self._on_import_accepted)
        dialog.exec()

    def _on_import_accepted(self, result: "QuantizationResult") -> None:
        """Handle accepted import from the image import dialog.

        Args:
            result: The quantization result containing indexed data and palette.
        """
        success = self._editing_controller.import_image(
            result.indexed_data,
            result.palette,
            source_path="",
        )
        if success and self._message_service:
            self._message_service.show_message("Image imported successfully")

    # --- Overlay handlers ---

    def _on_overlay_import_requested(self) -> None:
        """Open file dialog to select overlay image."""
        if self.state != "edit":
            if self._message_service:
                self._message_service.show_message("Open a sprite in editor first")
            return

        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Import Overlay Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*)",
        )
        if not file_path:
            return

        # Load image preserving alpha
        overlay = QImage(file_path)
        if overlay.isNull():
            logger.warning("Failed to load overlay: %s", file_path)
            if self._message_service:
                self._message_service.show_message("Failed to load overlay image")
            return

        # Convert to ARGB32 for consistent handling
        overlay = overlay.convertToFormat(QImage.Format.Format_ARGB32)

        if not self._view or not self._view.workspace:
            return

        # Set on canvas
        canvas = self._view.workspace.get_canvas()
        if canvas:
            canvas.set_overlay_image(overlay)
            self._view.workspace.overlay_panel.set_overlay_active(True)
            # Connect overlay moved signal to update panel position
            canvas.overlayMoved.connect(self._on_overlay_moved_from_canvas)
            if self._message_service:
                self._message_service.show_message("Overlay loaded - drag or use arrow keys to position")

    def _on_overlay_moved_from_canvas(self, x: int, y: int) -> None:
        """Update overlay panel position display when canvas reports movement."""
        if self._view and self._view.workspace:
            self._view.workspace.overlay_panel.update_position(x, y)

    def _on_apply_overlay(self) -> None:
        """Merge overlay onto sprite image."""
        if not self._view:
            return

        canvas = self._view.workspace.get_canvas()
        if not canvas or not canvas.has_overlay():
            return

        # Get current sprite data
        current_data = self._editing_controller.get_image_data()
        if current_data is None:
            return
        current_data = current_data.copy()
        current_palette = self._editing_controller.get_current_colors()

        # Get overlay data from canvas
        overlay_image = canvas._overlay_image
        overlay_position = canvas.get_overlay_position()

        if overlay_image is None:
            return

        # Merge overlay onto sprite
        merged = self._merge_overlay_to_indexed(
            current_data,
            current_palette,
            overlay_image,
            overlay_position,
        )

        # Apply via import command (supports undo)
        success = self._editing_controller.import_image(
            merged,
            current_palette,
            source_path="overlay",
        )

        if success:
            # Clear overlay
            canvas.clear_overlay()
            self._view.workspace.overlay_panel.set_overlay_active(False)
            self._view.workspace.overlay_panel.reset()
            if self._message_service:
                self._message_service.show_message("Overlay applied successfully")

    def _merge_overlay_to_indexed(
        self,
        sprite_data: np.ndarray,
        palette: list[tuple[int, int, int]],
        overlay: QImage,
        position: "QPoint",
    ) -> np.ndarray:
        """Merge RGBA overlay onto indexed sprite data.

        For each non-transparent overlay pixel:
        - Find closest palette color
        - Write that index to sprite data

        Args:
            sprite_data: 2D numpy array of palette indices
            palette: List of RGB tuples
            overlay: QImage in ARGB32 format
            position: Overlay offset from top-left

        Returns:
            Modified sprite data array
        """
        result = sprite_data.copy()
        height, width = result.shape

        for y in range(overlay.height()):
            for x in range(overlay.width()):
                # Target position in sprite
                sx = position.x() + x
                sy = position.y() + y

                # Skip if outside sprite bounds
                if sx < 0 or sx >= width or sy < 0 or sy >= height:
                    continue

                # Get overlay pixel
                pixel = overlay.pixelColor(x, y)

                # Skip transparent pixels
                if pixel.alpha() < 128:
                    continue

                # Find closest palette color (excluding index 0 = transparent)
                best_idx = 1
                best_dist = float("inf")
                for i, (r, g, b) in enumerate(palette[1:], start=1):
                    dist = (pixel.red() - r) ** 2 + (pixel.green() - g) ** 2 + (pixel.blue() - b) ** 2
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = i

                result[sy, sx] = best_idx

        return result

    def _on_cancel_overlay(self) -> None:
        """Cancel overlay import."""
        if not self._view:
            return

        canvas = self._view.workspace.get_canvas()
        if canvas:
            canvas.clear_overlay()
        self._view.workspace.overlay_panel.set_overlay_active(False)
        self._view.workspace.overlay_panel.reset()
        if self._message_service:
            self._message_service.show_message("Overlay cancelled")

    def _on_base_opacity_changed(self, value: int) -> None:
        """Handle base sprite opacity change from panel."""
        if not self._view:
            return
        canvas = self._view.workspace.get_canvas()
        if canvas:
            canvas.set_base_opacity(value)

    def _on_overlay_opacity_changed(self, value: int) -> None:
        """Handle overlay opacity change from panel."""
        if not self._view:
            return
        canvas = self._view.workspace.get_canvas()
        if canvas:
            canvas.set_overlay_opacity(value)

    def _on_overlay_position_changed(self, x: int, y: int) -> None:
        """Handle overlay position change from panel spinboxes."""
        if not self._view:
            return
        canvas = self._view.workspace.get_canvas()
        if canvas:
            from PySide6.QtCore import QPoint

            canvas.set_overlay_position(QPoint(x, y))

    def prepare_injection(self) -> None:
        """Transition from editing to save confirmation with size comparison."""
        # For RAW sprites, show a warning about no compression being applied
        if self.current_compression_type == CompressionType.RAW:
            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self._view,
                "Raw Sprite Injection",
                "This sprite was extracted as raw tile data (no HAL compression).\n\n"
                "It will be injected without compression. The sprite size must exactly\n"
                "match the original, or adjacent ROM data may be overwritten.\n\n"
                "Proceed with raw injection?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
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

        # Pre-save validation check (should already be disabled if invalid, but safety check)
        if not self._editing_controller.is_valid_for_rom():
            errors = self._editing_controller.get_validation_errors()
            if self._message_service:
                self._message_service.show_message(f"Cannot save: {'; '.join(errors)}")
            return

        # Reverse arrangement transformation (logical → physical) if active
        if self._current_arrangement and self._current_arrangement.has_arrangement:
            try:
                data = self._current_arrangement.logical_to_physical(data)
                logger.info("[SAVE] Applied reverse arrangement: logical → physical transformation")
            except Exception as e:
                logger.error("Failed to reverse arrangement transformation: %s", e)
                if self._message_service:
                    self._message_service.show_message(f"Error: Failed to restore tile positions: {e}")
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

            # Generate output path with _modified suffix
            from core.rom_injector import ROMInjector

            output_path = ROMInjector.get_modified_rom_path(self.rom_path)

            # Perform injection to modified copy (original ROM remains untouched)
            # First attempt (standard validation)
            success, message = self.rom_extractor.inject_sprite_to_rom(
                sprite_path=temp_png,
                rom_path=self.rom_path,
                output_path=output_path,
                sprite_offset=self.current_offset,
                create_backup=False,
                compression_type=self.current_compression_type,
                header_bytes=self.current_header_bytes,  # Restore stripped bytes to prevent color shift
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
                        output_path=output_path,
                        sprite_offset=self.current_offset,
                        create_backup=False,
                        ignore_checksum=True,
                        compression_type=self.current_compression_type,
                        header_bytes=self.current_header_bytes,
                    )

            # Handle failure due to sprite size too large (HAL: "Compressed", RAW: "Tile")
            if not success and ("too large" in message):
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
                        self._message_service.show_message("Force injecting...")
                    success, message = self.rom_extractor.inject_sprite_to_rom(
                        sprite_path=temp_png,
                        rom_path=self.rom_path,
                        output_path=output_path,
                        sprite_offset=self.current_offset,
                        create_backup=False,
                        force=True,
                        compression_type=self.current_compression_type,
                        header_bytes=self.current_header_bytes,
                    )

            # Cleanup temp file
            try:
                Path(temp_png).unlink()
            except OSError:
                pass

            if success:
                # Update our knowledge of checksum validity after successful injection
                self._checksum_valid = True

                if self._view:
                    self._view.set_checksum_valid(True)
                    # Invalidate thumbnail cache so it regenerates with updated sprite
                    self._view.asset_browser.clear_thumbnail(self.current_offset)
                if self.preview_coordinator:
                    self.preview_coordinator.invalidate_preview_cache(self.current_offset)

                if self._message_service:
                    self._message_service.show_message(f"Successfully saved to: {output_path}")
                # Show success in view
                from PySide6.QtWidgets import QMessageBox

                output_filename = Path(output_path).name
                QMessageBox.information(
                    self._view,
                    "Save Successful",
                    f"Sprite injected successfully at 0x{self.current_offset:06X}.\n\n"
                    f"Modified ROM saved to:\n{output_filename}\n\n{message}",
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

    def save_sprite_project(self) -> None:
        """Save current sprite as a .spritepal project file."""
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog, QMessageBox

        from core.sprite_project import SpriteProject, SpriteProjectError

        # Check if we have sprite data to save
        tile_data = self.current_tile_data
        if tile_data is None:
            if self._message_service:
                self._message_service.show_message("No sprite loaded to save")
            return

        # Get palette from editing controller
        palette_model = self._editing_controller.palette_model
        if not palette_model.colors:
            if self._message_service:
                self._message_service.show_message("No palette available")
            return

        # Get ROM info for metadata
        rom_title = ""
        rom_checksum = ""
        if self.rom_path and self.rom_extractor:
            try:
                header = self.rom_extractor.read_rom_header(self.rom_path)
                rom_title = header.title
                rom_checksum = f"0x{header.checksum:04X}"
            except Exception:
                rom_title = Path(self.rom_path).stem

        # Create the project
        project = SpriteProject(
            name=self.current_sprite_name or f"sprite_0x{self.current_offset:06X}",
            width=self.current_width,
            height=self.current_height,
            tile_data=tile_data,
            tile_count=len(tile_data) // 32,
            palette_colors=list(palette_model.colors),
            palette_name=palette_model.name,
            palette_index=palette_model.index,
            original_rom_offset=self.current_offset,
            original_compressed_size=self.original_compressed_size,
            header_bytes=self.current_header_bytes,
            compression_type=self.current_compression_type.value,
            rom_title=rom_title,
            rom_checksum=rom_checksum,
        )

        # Generate preview
        project.update_preview()

        # Show save dialog
        default_name = f"{project.name}.spritepal"
        file_path, _ = QFileDialog.getSaveFileName(
            self._view,
            "Save Sprite Project",
            default_name,
            "SpritePal Projects (*.spritepal);;All Files (*)",
        )

        if not file_path:
            return

        try:
            project.save(Path(file_path))
            if self._message_service:
                self._message_service.show_message(f"Project saved: {file_path}")
            QMessageBox.information(self._view, "Project Saved", f"Sprite project saved to:\n{file_path}")
        except SpriteProjectError as e:
            logger.exception("Failed to save sprite project")
            if self._message_service:
                self._message_service.show_message(f"Save failed: {e}")
            QMessageBox.critical(self._view, "Save Failed", f"Failed to save project:\n{e}")

    def load_sprite_project(self) -> None:
        """Load a .spritepal project file for editing/injection."""
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog, QMessageBox

        from core.sprite_project import SpriteProject, SpriteProjectError

        # Check for unsaved changes
        if self._editing_controller.has_unsaved_changes():
            result = QMessageBox.question(
                self._view,
                "Unsaved Changes",
                "You have unsaved changes. Load a new project anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return

        # Show open dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Load Sprite Project",
            "",
            "SpritePal Projects (*.spritepal);;All Files (*)",
        )

        if not file_path:
            return

        try:
            project = SpriteProject.load(Path(file_path))
        except SpriteProjectError as e:
            logger.exception("Failed to load sprite project")
            if self._message_service:
                self._message_service.show_message(f"Load failed: {e}")
            QMessageBox.critical(self._view, "Load Failed", f"Failed to load project:\n{e}")
            return

        # Check ROM checksum mismatch
        if self.rom_path and project.rom_checksum and self.rom_extractor:
            try:
                current_header = self.rom_extractor.read_rom_header(self.rom_path)
                current_checksum = f"0x{current_header.checksum:04X}"
                if current_checksum != project.rom_checksum:
                    QMessageBox.warning(
                        self._view,
                        "ROM Mismatch",
                        f"This project was created from a different ROM.\n\n"
                        f"Project ROM: {project.rom_title}\n"
                        f"Project checksum: {project.rom_checksum}\n\n"
                        f"Current ROM checksum: {current_checksum}\n\n"
                        "Injection may not work correctly.",
                    )
            except Exception:
                pass  # Ignore header read errors

        # Apply project data to controller state
        self.current_tile_data = project.tile_data
        self.current_width = project.width
        self.current_height = project.height
        self.current_sprite_name = project.name
        self.original_compressed_size = project.original_compressed_size
        self.current_header_bytes = project.header_bytes
        self.current_offset = project.original_rom_offset

        # Set compression type
        try:
            self.current_compression_type = CompressionType(project.compression_type)
        except ValueError:
            self.current_compression_type = CompressionType.HAL

        # Load into editing controller
        self._load_tile_data_into_editor(project.tile_data, project.width, project.height)

        # Apply palette
        self._editing_controller.set_palette(project.palette_colors, project.palette_name)
        self._editing_controller.palette_model.index = project.palette_index

        # Update state
        self.state = "edit"
        self.workflow_state_changed.emit("edit")

        # Enable save project button
        if self._view and self._view.workspace:
            self._view.workspace.set_save_project_enabled(True)

        if self._message_service:
            self._message_service.show_message(f"Loaded project: {project.name}")

    def _load_tile_data_into_editor(self, tile_data: bytes, width: int, height: int) -> None:
        """Load raw tile data into the editing controller."""
        from core.tile_utils import decode_4bpp_tile

        # Decode tiles to pixel indices
        num_tiles = len(tile_data) // 32
        tiles_per_row = width // 8 if width >= 8 else 1

        # Create numpy array for pixel data
        pixels = np.zeros((height, width), dtype=np.uint8)

        for tile_idx in range(num_tiles):
            tile_x = (tile_idx % tiles_per_row) * 8
            tile_y = (tile_idx // tiles_per_row) * 8

            tile_bytes = tile_data[tile_idx * 32 : (tile_idx + 1) * 32]
            tile_pixels = decode_4bpp_tile(tile_bytes)

            for py in range(8):
                for px in range(8):
                    x = tile_x + px
                    y = tile_y + py
                    if x < width and y < height:
                        pixels[y, x] = tile_pixels[py][px]

        # Load into editing controller
        self._editing_controller.load_image(pixels)

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
        header_bytes: bytes = b"",
    ) -> None:
        """Handle preview ready from coordinator."""
        # Use current offset if actual_offset not provided
        if actual_offset == -1:
            actual_offset = self.current_offset

        # Check if offset was adjusted during preview (e.g. alignment correction)
        offset_adjusted = actual_offset != self.current_offset
        if offset_adjusted:
            old_offset = self.current_offset  # Capture before update
            offset_delta = actual_offset - old_offset
            logger.info(
                f"[PREVIEW] Offset adjusted from 0x{old_offset:06X} to 0x{actual_offset:06X} (delta: {offset_delta:+d})"
            )
            # Keep pending auto-open aligned with the adjusted offset.
            if self._pending_open_in_editor and self._pending_open_offset not in (-1, actual_offset):
                self._pending_open_offset = actual_offset
            # Update current offset to match reality
            self.current_offset = actual_offset
            # Update UI
            if self._view:
                self._view.set_offset(actual_offset)
                # Update asset browser item offset - this emits item_offset_changed signal
                # which automatically re-queues thumbnail for the new offset
                self._view.asset_browser.update_sprite_offset(old_offset, actual_offset)
                if self._message_service:
                    self._message_service.show_message(
                        f"Aligned to valid sprite at 0x{actual_offset:06X} (adjusted by {offset_delta:+d} bytes)"
                    )

        logger.debug(
            f"[PREVIEW] _on_preview_ready called: {len(tile_data)} bytes, {width}x{height}, "
            f"pending_open={self._pending_open_in_editor}, offset=0x{actual_offset:06X}, hal={hal_succeeded}, "
            f"header_bytes={len(header_bytes)}"
        )
        self.current_tile_data = tile_data
        self.current_width = width
        self.current_height = height
        self.current_sprite_name = sprite_name
        self.original_compressed_size = compressed_size
        self.available_slack = slack_size
        # Track compression type for injection
        self.current_compression_type = CompressionType.HAL if hal_succeeded else CompressionType.RAW
        # Store header bytes for restoration during injection (prevents color shift bug)
        self.current_header_bytes = header_bytes

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
                # Raw sprite - can be edited and injected without compression
                msg = f"Raw sprite data at 0x{actual_offset:06X} ({len(tile_data)} bytes, no HAL compression)"

            if self._message_service:
                self._message_service.show_message(msg)

        # Auto-open in editor if triggered by double-click
        logger.debug(f"[PREVIEW] Checking flag: _pending_open_in_editor={self._pending_open_in_editor}")
        if self._pending_open_in_editor:
            # Only auto-open if offset matches (prevents stale opens after errors/navigation)
            if self._pending_open_offset in (-1, actual_offset):
                self._pending_open_in_editor = False
                self._pending_open_offset = -1

                # Warn user about raw sprites (they can still edit/inject but without compression)
                if not hal_succeeded:
                    logger.info(f"[PREVIEW] Raw sprite at 0x{actual_offset:06X}, allowing edit")
                    if self._message_service:
                        self._message_service.show_message(
                            f"Opening raw sprite at 0x{actual_offset:06X} (will be injected without compression)"
                        )

                # Validation: Warn if size is not a multiple of 32 bytes (SNES tile size)
                if len(tile_data) % 32 != 0:
                    from PySide6.QtWidgets import QMessageBox

                    reply = QMessageBox.warning(
                        self._view,
                        "Unusual Sprite Size",
                        f"Decompressed data is {len(tile_data)} bytes, which is not a multiple of 32.\n"
                        "This may not be valid 4bpp tile data.\n\n"
                        "Open in editor anyway?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if reply == QMessageBox.StandardButton.No:
                        return

                logger.debug("[PREVIEW] Flag is True and offset matches, calling open_in_editor()")
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

    def _on_validation_changed(self, is_valid: bool, errors: list[str]) -> None:
        """Handle validation state change from editing controller.

        Updates the UI to show validation warnings and enable/disable save button.

        Args:
            is_valid: Whether the current image meets ROM constraints
            errors: List of validation error messages
        """
        if not self._view:
            return

        # Update the workspace's save button state
        if self._view.workspace:
            self._view.workspace.set_save_enabled(is_valid)

        # Show/hide validation warning in status bar
        if errors:
            error_text = "; ".join(errors)
            if self._message_service:
                self._message_service.show_message(f"ROM Warning: {error_text}")
            logger.debug("ROM validation failed: %s", error_text)
        elif self.state == "edit":
            # Clear warning when valid and in edit mode
            if self._message_service:
                self._message_service.show_message("Ready to save to ROM")

    def _on_palette_source_changed(self, source_type: str, palette_index: int) -> None:
        """Handle palette source change from editing controller.

        When user loads a custom palette file, hide the 'Using default palette' warning
        since the user has explicitly chosen their palette.

        Args:
            source_type: Type of palette source ('file', 'rom', 'mesen', 'default', 'preset')
            palette_index: Index of the palette within the source
        """
        # Hide palette warning when user explicitly loads a palette file
        if source_type == "file" and self._view:
            self._view.hide_palette_warning()
            if self._message_service:
                self._message_service.show_message("Custom palette loaded")

    def _on_manual_palette_requested(self) -> None:
        """Handle request to manually specify a palette offset.

        Shows a dialog for the user to enter a ROM offset where sprite
        palette data is located. Extracts and registers the palette.
        """
        if not self.rom_path or not self._view:
            if self._message_service:
                self._message_service.show_message("Load a ROM first before selecting a manual palette")
            return

        from ui.dialogs import ManualPaletteOffsetDialog

        dialog = ManualPaletteOffsetDialog(self._view, rom_size=self.rom_size)
        dialog.palette_offset_selected.connect(self._apply_manual_palette)
        dialog.exec()

    def _apply_manual_palette(self, offset: int, start_index: int, count: int) -> None:
        """Apply a manually specified palette from ROM.

        Args:
            offset: ROM offset where palette data starts
            start_index: First palette index (e.g., 8 for sprites)
            count: Number of palettes to load
        """
        if not self.rom_path or not self.rom_extractor:
            return

        try:
            # Extract palettes from the specified offset
            end_index = start_index + count - 1
            all_palettes = self.rom_extractor.extract_palette_range(self.rom_path, offset, start_index, end_index)

            if not all_palettes:
                if self._message_service:
                    self._message_service.show_message(f"No palette data found at offset 0x{offset:X}")
                return

            # Clear previous ROM palette sources
            if self._view and self._view.workspace and self._view.workspace.palette_panel:
                self._view.workspace.palette_panel.palette_source_selector.clear_rom_sources()

            # Register the extracted palettes
            if self._editing_controller:
                descriptions: dict[int, str] = {i: f"Manual Palette {i}" for i in all_palettes}
                self._editing_controller.register_rom_palettes(
                    all_palettes,
                    descriptions=descriptions,
                    active_indices=[],
                )

                # Select the first extracted palette
                first_index = min(all_palettes.keys())
                self._editing_controller.set_palette_source("rom", first_index)

                logger.info(
                    f"Manual palette loaded: offset=0x{offset:X}, "
                    f"indices={start_index}-{end_index}, found {len(all_palettes)} palettes"
                )

                if self._message_service:
                    self._message_service.show_message(f"Loaded {len(all_palettes)} palettes from offset 0x{offset:X}")

            # Hide the default palette warning since we now have a palette
            if self._view:
                self._view.hide_palette_warning()

        except Exception as e:
            logger.exception(f"Failed to extract manual palette from 0x{offset:X}")
            if self._message_service:
                self._message_service.show_message(f"Failed to load palette: {e}")

    def cleanup(self) -> None:
        """Clean up resources."""
        self.preview_coordinator.cleanup()
        if self._thumbnail_controller:
            self._thumbnail_controller.cleanup()
            self._thumbnail_controller = None
