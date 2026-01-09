#!/usr/bin/env python3
"""
Asset Browser Controller for the Sprite Editor.
Manages sprite asset browsing, persistence, and thumbnail coordination.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QImage, QPixmap

from core.mesen_integration.log_watcher import CapturedOffset

if TYPE_CHECKING:
    from ui.workers.batch_thumbnail_worker import BatchThumbnailWorker

    from ..views.widgets.sprite_asset_browser import SpriteAssetBrowser

logger = logging.getLogger(__name__)


class AssetBrowserController(QObject):
    """
    Controller for sprite asset browser widget.

    Manages asset state, persistence via QSettings, Mesen2 capture integration,
    and thumbnail loading coordination.
    """

    # Signals
    thumbnailRequested = Signal(int, str)  # offset, source_type - request thumbnail loading
    assetsChanged = Signal()  # assets list modified
    captureAdded = Signal(int, str)  # offset, name - when Mesen2 capture added
    # Signal relay: SpriteAssetBrowser.sprite_selected → this.spriteSelected
    # Consumed by: ROMWorkflowController._on_sprite_selected()
    spriteSelected = Signal(int, str)
    # Signal relay: SpriteAssetBrowser.sprite_activated → this.spriteActivated
    # Consumed by: ROMWorkflowController._on_sprite_activated() (triggers editor open)
    spriteActivated = Signal(int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the asset browser controller."""
        super().__init__(parent)

        # View reference
        self._browser: SpriteAssetBrowser | None = None

        # Asset metadata storage
        self._assets: dict[tuple[int, str], AssetMetadata] = {}  # (offset, source_type) -> metadata

        # Current ROM hash for namespacing settings
        self._rom_hash: str = ""

        # QSettings instance for persistence
        self._settings = QSettings()

        # Thumbnail worker reference (for direct integration)
        self._thumbnail_worker: BatchThumbnailWorker | None = None

    def set_browser(self, browser: SpriteAssetBrowser) -> None:
        """
        Set the browser widget and connect signals.

        Args:
            browser: SpriteAssetBrowser widget instance
        """
        self._browser = browser

        # Connect browser signals
        browser.sprite_selected.connect(self._on_sprite_selected)
        browser.sprite_activated.connect(self._on_sprite_activated)
        browser.rename_requested.connect(self._on_rename_requested)
        browser.delete_requested.connect(self._on_delete_requested)

    def set_thumbnail_worker(self, worker: BatchThumbnailWorker) -> None:
        """
        Set the thumbnail worker for direct thumbnail generation.

        Args:
            worker: BatchThumbnailWorker instance
        """
        self._thumbnail_worker = worker
        if worker:
            # Connect worker's thumbnail_ready signal to our handler
            worker.thumbnail_ready.connect(self._on_worker_thumbnail_ready)

    def _on_worker_thumbnail_ready(self, offset: int, thumbnail: QImage) -> None:
        """
        Handle thumbnail ready from worker (direct integration path).

        Args:
            offset: ROM offset
            thumbnail: Generated thumbnail image
        """
        # Call the existing handler
        self.on_thumbnail_loaded(offset, thumbnail)

    def set_rom_hash(self, rom_hash: str) -> None:
        """
        Set the current ROM hash for namespacing settings.

        Args:
            rom_hash: Hash or identifier for the current ROM
        """
        self._rom_hash = rom_hash
        logger.debug("ROM hash set to: %s", rom_hash)

        # Load saved names for this ROM
        self.load_saved_names()

    def load_saved_names(self) -> None:
        """Load saved asset names from QSettings for the current ROM."""
        if not self._rom_hash:
            logger.debug("No ROM hash set, skipping name loading")
            return

        settings_key = f"asset_names/{self._rom_hash}"
        self._settings.beginGroup(settings_key)

        try:
            keys = self._settings.childKeys()
            for key in keys:
                # Key format: "offset_sourcetype" (e.g., "123456_rom")
                parts = key.rsplit("_", 1)
                if len(parts) != 2:
                    continue

                try:
                    offset = int(parts[0])
                    source_type = parts[1]
                    name = self._settings.value(key)

                    if isinstance(name, str):
                        # Update metadata if asset exists
                        asset_key = (offset, source_type)
                        if asset_key in self._assets:
                            self._assets[asset_key].name = name
                            logger.debug("Loaded name for %s: %s", asset_key, name)
                except ValueError:
                    continue

        finally:
            self._settings.endGroup()

    def save_asset_name(self, offset: int, source_type: str, name: str) -> None:
        """
        Save asset name to persistent storage.

        Args:
            offset: ROM offset
            source_type: Source type ('rom', 'mesen', 'local')
            name: Asset name
        """
        if not self._rom_hash:
            logger.warning("Cannot save asset name without ROM hash")
            return

        settings_key = f"asset_names/{self._rom_hash}/{offset}_{source_type}"
        self._settings.setValue(settings_key, name)
        self._settings.sync()

        logger.debug("Saved asset name: %s = %s", settings_key, name)

    def add_rom_sprite(self, name: str, offset: int, thumbnail: QPixmap | None = None) -> None:
        """
        Add a ROM sprite to the browser.

        Args:
            name: Sprite name (or default name if not custom)
            offset: ROM offset
            thumbnail: Optional thumbnail pixmap
        """
        source_type = "rom"
        asset_key = (offset, source_type)

        # Check if we have a saved custom name
        saved_name = self._get_saved_name(offset, source_type)
        display_name = saved_name if saved_name else name

        # Store metadata
        self._assets[asset_key] = AssetMetadata(
            name=display_name,
            offset=offset,
            source_type=source_type,
            has_thumbnail=(thumbnail is not None),
        )

        # Add to widget
        if self._browser:
            self._browser.add_rom_sprite(display_name, offset, thumbnail)

            # Request thumbnail if not provided
            if thumbnail is None:
                self.request_thumbnail(offset, source_type)

        self.assetsChanged.emit()

    def add_mesen_capture(self, capture: CapturedOffset) -> None:
        """
        Add a Mesen2 capture to the browser.

        Args:
            capture: CapturedOffset instance from log watcher
        """
        offset = capture.offset
        source_type = "mesen"
        asset_key = (offset, source_type)

        # Check if already added
        if asset_key in self._assets:
            logger.debug("Capture already exists: 0x%06X", offset)
            return

        # Check for saved custom name
        saved_name = self._get_saved_name(offset, source_type)

        # Generate default name from timestamp if no saved name
        if saved_name:
            display_name = saved_name
        else:
            timestamp_str = capture.timestamp.strftime("%H:%M:%S")
            display_name = f"Capture 0x{offset:06X} ({timestamp_str})"

        # Store metadata
        self._assets[asset_key] = AssetMetadata(
            name=display_name,
            offset=offset,
            source_type=source_type,
            has_thumbnail=False,
        )

        # Add to widget (no thumbnail initially)
        if self._browser:
            self._browser.add_mesen_capture(display_name, offset, thumbnail=None)

            # Request thumbnail
            self.request_thumbnail(offset, source_type)

        logger.info("Added Mesen2 capture: %s at 0x%06X", display_name, offset)
        self.captureAdded.emit(offset, display_name)
        self.assetsChanged.emit()

    def add_local_file(self, name: str, path: str, thumbnail: QPixmap | None = None) -> None:
        """
        Add a local file to the browser.

        Args:
            name: File name
            path: File path
            thumbnail: Optional thumbnail pixmap
        """
        # For local files, we use path as the key (not offset)
        # Store in assets dict with offset=-1 as placeholder
        source_type = "local"
        asset_key = (-1, path)

        self._assets[asset_key] = AssetMetadata(
            name=name,
            offset=-1,
            source_type=source_type,
            has_thumbnail=(thumbnail is not None),
        )

        # Add to widget
        if self._browser:
            self._browser.add_local_file(name, path, thumbnail)

        self.assetsChanged.emit()

    def rename_asset(self, offset: int, source_type: str, new_name: str) -> None:
        """
        Rename an asset and persist to storage.

        Args:
            offset: ROM offset
            source_type: Source type
            new_name: New asset name
        """
        asset_key = (offset, source_type)

        if asset_key not in self._assets:
            logger.warning("Cannot rename non-existent asset: %s", asset_key)
            return

        # Update metadata
        self._assets[asset_key].name = new_name

        # Save to persistent storage
        self.save_asset_name(offset, source_type, new_name)

        logger.info("Renamed asset 0x%06X (%s) to: %s", offset, source_type, new_name)

    def get_asset_name(self, offset: int, source_type: str = "rom") -> str | None:
        """
        Get the name of an asset.

        Args:
            offset: ROM offset
            source_type: Source type (default: 'rom')

        Returns:
            Asset name or None if not found
        """
        asset_key = (offset, source_type)
        metadata = self._assets.get(asset_key)
        return metadata.name if metadata else None

    def request_thumbnail(self, offset: int, source_type: str = "rom") -> None:
        """
        Request thumbnail loading for an asset.

        If thumbnail worker is set, queues request directly.
        Otherwise, emits thumbnailRequested signal for external providers.

        Args:
            offset: ROM offset
            source_type: Source type (default: 'rom')
        """
        logger.debug("Requesting thumbnail for 0x%06X (%s)", offset, source_type)

        # If worker is available, queue directly
        if self._thumbnail_worker:
            self._thumbnail_worker.queue_thumbnail(offset, size=128, priority=0)
        else:
            # Fall back to signal-based approach
            self.thumbnailRequested.emit(offset, source_type)

    def on_thumbnail_loaded(self, offset: int, thumbnail: QImage) -> None:
        """
        Handle thumbnail loaded from external provider.

        Args:
            offset: ROM offset
            thumbnail: Loaded thumbnail image
        """
        # Convert QImage to QPixmap
        pixmap = QPixmap.fromImage(thumbnail)

        # Update widget
        if self._browser:
            self._browser.set_thumbnail(offset, pixmap)

        # Update metadata
        for metadata in self._assets.values():
            if metadata.offset == offset:
                metadata.has_thumbnail = True
                break

        logger.debug("Thumbnail loaded for 0x%06X", offset)

    def get_all_assets(self) -> dict[str, list[dict[str, object]]]:
        """
        Get all assets organized by category.

        Returns:
            Dict with keys "rom", "mesen", "local", each containing a list of asset dicts.
            Asset dicts have keys: name, offset (or path for local), thumbnail
        """
        assets_by_category: dict[str, list[dict[str, object]]] = {
            "rom": [],
            "mesen": [],
            "local": [],
        }

        for (offset, source_type), metadata in self._assets.items():
            if source_type == "rom":
                assets_by_category["rom"].append(
                    {
                        "name": metadata.name,
                        "offset": offset,
                        "thumbnail": None,  # Thumbnails managed separately
                    }
                )
            elif source_type == "mesen":
                assets_by_category["mesen"].append(
                    {
                        "name": metadata.name,
                        "offset": offset,
                        "thumbnail": None,
                    }
                )
            elif source_type == "local" or offset == -1:
                # Local files use path as key
                assets_by_category["local"].append(
                    {
                        "name": metadata.name,
                        "path": source_type if offset == -1 else "",
                        "thumbnail": None,
                    }
                )

        return assets_by_category

    def clear_category(self, category: str) -> None:
        """
        Clear all assets from a category.

        Args:
            category: Category name (use SpriteAssetBrowser.CATEGORY_* constants)
        """
        # Determine source type from category
        source_type_map = {
            "ROM Sprites": "rom",
            "Mesen2 Captures": "mesen",
            "Local Files": "local",
        }
        source_type = source_type_map.get(category)

        if source_type:
            # Remove assets with matching source type
            keys_to_remove = [key for key in self._assets if key[1] == source_type]
            for key in keys_to_remove:
                del self._assets[key]

        # Clear in widget
        if self._browser:
            self._browser.clear_category(category)

        logger.debug("Cleared category: %s", category)
        self.assetsChanged.emit()

    def clear_all(self) -> None:
        """Clear all assets from all categories."""
        self._assets.clear()

        if self._browser:
            self._browser.clear_all()

        logger.debug("Cleared all assets")
        self.assetsChanged.emit()

    def get_asset_count(self) -> dict[str, int]:
        """
        Get count of assets by source type.

        Returns:
            Dict mapping source type to count
        """
        counts: dict[str, int] = {"rom": 0, "mesen": 0, "local": 0}

        for _, source_type in self._assets:
            if source_type in counts:
                counts[source_type] += 1

        return counts

    def _get_saved_name(self, offset: int, source_type: str) -> str | None:
        """
        Get saved custom name from QSettings.

        Args:
            offset: ROM offset
            source_type: Source type

        Returns:
            Saved name or None
        """
        if not self._rom_hash:
            return None

        settings_key = f"asset_names/{self._rom_hash}/{offset}_{source_type}"
        value = self._settings.value(settings_key)

        return value if isinstance(value, str) else None

    # Signal handlers

    def _on_sprite_selected(self, offset: int, source_type: str) -> None:
        """Relay sprite selection from browser widget to external listeners.

        Signal chain: SpriteAssetBrowser.sprite_selected → this → ROMWorkflowController
        """
        self.spriteSelected.emit(offset, source_type)

    def _on_sprite_activated(self, offset: int, source_type: str) -> None:
        """Relay sprite activation (double-click) from browser widget.

        Signal chain: SpriteAssetBrowser.sprite_activated → this → ROMWorkflowController
        This triggers opening the sprite in the editor.
        """
        self.spriteActivated.emit(offset, source_type)

    def _on_rename_requested(self, offset: int, new_name: str) -> None:
        """
        Handle rename request from widget.

        Args:
            offset: ROM offset
            new_name: New asset name
        """
        # Determine source type from assets dict
        source_type = None
        for off, src in self._assets:
            if off == offset:
                source_type = src
                break

        if source_type:
            self.rename_asset(offset, source_type, new_name)

    def _on_delete_requested(self, offset: int, source_type: str) -> None:
        """
        Handle delete request from widget.

        Args:
            offset: ROM offset (or -1 for local files)
            source_type: Source type or file path for local files
        """
        if offset == -1:
            # Local file - source_type is actually the path
            asset_key = (-1, source_type)
            if asset_key in self._assets:
                del self._assets[asset_key]
                logger.info("Deleted local file: %s", source_type)
        else:
            # ROM or Mesen sprite
            asset_key = (offset, source_type)
            if asset_key in self._assets:
                del self._assets[asset_key]
                logger.info("Deleted asset: 0x%06X (%s)", offset, source_type)

        self.assetsChanged.emit()


class AssetMetadata:
    """Metadata for a sprite asset."""

    def __init__(
        self,
        name: str,
        offset: int,
        source_type: str,
        has_thumbnail: bool = False,
    ) -> None:
        """
        Initialize asset metadata.

        Args:
            name: Asset name
            offset: ROM offset
            source_type: Source type ('rom', 'mesen', 'local')
            has_thumbnail: Whether thumbnail has been loaded
        """
        self.name = name
        self.offset = offset
        self.source_type = source_type
        self.has_thumbnail = has_thumbnail
        self.created_at = datetime.now()
