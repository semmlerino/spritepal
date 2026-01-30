"""
Sprite thumbnail service for async thumbnail generation and caching.

Manages thumbnail worker lifecycle, provides fallback strategies for
thumbnail generation, and handles library thumbnail loading.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from PIL import Image
from PySide6.QtCore import QObject
from PySide6.QtGui import QImage, QPixmap

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor
    from core.sprite_library import LibrarySprite, SpriteLibrary
    from ui.workers.batch_thumbnail_worker import ThumbnailWorkerController

logger = get_logger(__name__)


@runtime_checkable
class ThumbnailViewProtocol(Protocol):
    """Protocol for views that display thumbnails."""

    def set_thumbnail(self, offset: int, pixmap: QPixmap, source_type: str) -> None:
        """Set thumbnail for a sprite in the view.

        Args:
            offset: ROM offset of the sprite.
            pixmap: Thumbnail image.
            source_type: Source type filter ("rom", "mesen", "library").
        """
        ...


@runtime_checkable
class ThumbnailDataProviderProtocol(Protocol):
    """Protocol for data providers that supply thumbnail generation context.

    The controller implements this protocol to provide ROM and tile data
    for thumbnail generation without tight coupling.
    """

    @property
    def rom_path(self) -> str:
        """Path to the currently loaded ROM."""
        ...

    @property
    def rom_extractor(self) -> ROMExtractor | None:
        """ROM extractor for HAL decompression."""
        ...

    @property
    def current_tile_offset(self) -> int:
        """Currently selected tile offset."""
        ...

    @property
    def current_tile_data(self) -> bytes | None:
        """Currently decompressed tile data."""
        ...


class SpriteThumbnailService(QObject):
    """
    Service for sprite thumbnail generation and caching.

    Responsibilities:
    - Manage ThumbnailWorkerController lifecycle
    - Queue thumbnail generation requests
    - Generate library thumbnails with fallback strategies
    - Load saved library thumbnails
    - Convert PIL images to QPixmap

    This service extracts thumbnail-related methods from ROMWorkflowController
    to reduce complexity and improve testability.
    """

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        data_provider: ThumbnailDataProviderProtocol | None = None,
        sprite_library: SpriteLibrary | None = None,
    ) -> None:
        """Initialize the thumbnail service.

        Args:
            parent: Parent QObject for memory management.
            data_provider: Provider of ROM/editor state for thumbnail generation.
            sprite_library: Sprite library for thumbnail path resolution.
        """
        super().__init__(parent)
        self._data_provider = data_provider
        self._sprite_library = sprite_library
        self._thumbnail_controller: ThumbnailWorkerController | None = None
        self._view_adapter: ThumbnailViewProtocol | None = None

    def set_data_provider(self, provider: ThumbnailDataProviderProtocol | None) -> None:
        """Set the data provider for thumbnail generation context."""
        self._data_provider = provider

    def set_sprite_library(self, library: SpriteLibrary | None) -> None:
        """Set the sprite library for thumbnail path resolution."""
        self._sprite_library = library

    def set_view_adapter(self, adapter: ThumbnailViewProtocol | None) -> None:
        """Set the view adapter for thumbnail display updates."""
        self._view_adapter = adapter

    def setup_worker(self, rom_path: str, rom_extractor: ROMExtractor | None) -> None:
        """Create thumbnail worker after ROM is loaded.

        Args:
            rom_path: Path to the loaded ROM.
            rom_extractor: ROM extractor for decompression.
        """
        # Import here to avoid circular imports at module level
        from ui.workers.batch_thumbnail_worker import ThumbnailWorkerController

        if self._thumbnail_controller:
            self._thumbnail_controller.cleanup()

        if not rom_extractor:
            return

        self._thumbnail_controller = ThumbnailWorkerController(self)
        self._thumbnail_controller.start_worker(rom_path, rom_extractor)

        # Connect ready signal to handler
        if self._thumbnail_controller.worker:
            self._thumbnail_controller.worker.thumbnail_ready.connect(self._on_thumbnail_ready)
            logger.debug("Thumbnail worker connected for asset browser")

    def _on_thumbnail_ready(self, offset: int, thumbnail: QImage) -> None:
        """Handle thumbnail ready from worker.

        Worker-generated thumbnails apply only to "rom" and "mesen" items.
        Library items use their saved thumbnails and should not be overwritten.

        Args:
            offset: ROM offset of the sprite.
            thumbnail: Generated thumbnail image.
        """
        if self._view_adapter:
            pixmap = QPixmap.fromImage(thumbnail)
            # Apply to ROM and Mesen items only - library items have saved thumbnails
            self._view_adapter.set_thumbnail(offset, pixmap, source_type="rom")
            self._view_adapter.set_thumbnail(offset, pixmap, source_type="mesen")
            logger.debug(f"Thumbnail set for offset 0x{offset:06X} (rom/mesen only)")

    def request_thumbnail(self, offset: int) -> None:
        """Request thumbnail generation for a single offset.

        Args:
            offset: ROM offset to generate thumbnail for.
        """
        if self._thumbnail_controller:
            self._thumbnail_controller.queue_thumbnail(offset)

    def request_batch(self, offsets: list[int]) -> None:
        """Request thumbnails for multiple offsets.

        Args:
            offsets: List of ROM offsets to generate thumbnails for.
        """
        if not self._thumbnail_controller or not offsets:
            return

        self._thumbnail_controller.queue_batch(offsets)
        logger.debug("Queued %d thumbnails for refresh", len(offsets))

    def invalidate_offset(self, offset: int) -> None:
        """Invalidate cached thumbnail for an offset (e.g., after edit).

        Args:
            offset: ROM offset whose thumbnail should be invalidated.
        """
        if self._thumbnail_controller:
            self._thumbnail_controller.invalidate_offset(offset)

    def clear_cache(self) -> None:
        """Clear in-memory thumbnail cache in the worker."""
        if self._thumbnail_controller and self._thumbnail_controller.worker:
            self._thumbnail_controller.worker.clear_cache()
            logger.debug("Cleared thumbnail worker in-memory cache")

    def generate_library_thumbnail(
        self,
        offset: int,
        *,
        edited_pixels: tuple[Image.Image, list[int]] | None = None,
    ) -> Image.Image | None:
        """Generate PIL Image thumbnail for library storage.

        When in edit mode and generating thumbnail for the currently edited sprite,
        uses the edited pixel data instead of the original ROM data.

        For other cases, attempts three strategies in order:
        1. Use current_tile_data if offset matches (already decompressed from preview)
        2. Attempt HAL decompression
        3. Fall back to raw ROM bytes

        Args:
            offset: ROM offset to generate thumbnail for.
            edited_pixels: Optional tuple of (PIL Image mode P, flat palette) for
                edited sprite data. If provided, uses this instead of ROM data.

        Returns:
            PIL Image thumbnail, or None if generation failed.
        """
        if not self._data_provider:
            return None

        rom_path = self._data_provider.rom_path
        if not rom_path:
            return None

        # Strategy 0: Use edited pixels if provided
        if edited_pixels is not None:
            try:
                img, flat_palette = edited_pixels
                # Ensure we have a proper palette image
                if img.mode != "P":
                    logger.debug("Edited pixels not in palette mode, skipping")
                else:
                    img = img.copy()
                    img.putpalette(flat_palette)
                    # Create thumbnail
                    thumb_size = (64, 64)
                    img.thumbnail(thumb_size, Image.Resampling.NEAREST)
                    logger.debug("Using edited pixels for library thumbnail: 0x%06X", offset)
                    return img
            except Exception as e:
                logger.debug("Failed to use edited pixels for thumbnail: %s", e)
                # Fall through to other strategies

        data_to_render: bytes | None = None

        # Strategy 1: Use current decompressed data if available
        if self._data_provider.current_tile_offset == offset and self._data_provider.current_tile_data:
            data_to_render = self._data_provider.current_tile_data
            logger.debug("Using current_tile_data for thumbnail: 0x%06X", offset)

        # Strategy 2: Attempt HAL decompression
        rom_extractor = self._data_provider.rom_extractor
        if not data_to_render and rom_extractor:
            try:
                with open(rom_path, "rb") as f:
                    f.seek(offset)
                    chunk = f.read(0x10000)  # Read up to 64KB for decompression

                if chunk:
                    _, decompressed_data, _ = rom_extractor.find_compressed_sprite(chunk, 0, expected_size=None)
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
                with open(rom_path, "rb") as f:
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

    def load_library_thumbnail(self, sprite: LibrarySprite) -> QPixmap | None:
        """Load thumbnail from library.

        Args:
            sprite: The library sprite to load thumbnail for.

        Returns:
            QPixmap of the thumbnail, or None if not available.
        """
        if not self._sprite_library:
            return None

        path = self._sprite_library.get_thumbnail_path(sprite)
        if path and path.exists():
            return QPixmap(str(path))
        return None

    def restore_library_thumbnails(self, rom_path: str) -> int:
        """Restore library thumbnails from saved files after refresh.

        Library sprites use saved thumbnail files rather than the thumbnail worker,
        so they must be explicitly restored after refresh clears browser state.

        Args:
            rom_path: Path to the ROM file for hash matching.

        Returns:
            Number of thumbnails restored.
        """
        if not self._view_adapter or not rom_path or not self._sprite_library:
            return 0

        rom_hash = self._sprite_library.compute_rom_hash(rom_path)
        restored = 0
        for sprite in self._sprite_library.sprites:
            if sprite.rom_hash == rom_hash:
                thumbnail = self.load_library_thumbnail(sprite)
                if thumbnail:
                    self._view_adapter.set_thumbnail(sprite.rom_offset, thumbnail, source_type="library")
                    restored += 1

        if restored > 0:
            logger.debug("Restored %d library thumbnails after refresh", restored)

        return restored

    def cleanup(self) -> None:
        """Clean up resources (stop worker, release references)."""
        if self._thumbnail_controller:
            self._thumbnail_controller.cleanup()
            self._thumbnail_controller = None

    @staticmethod
    def pil_to_qpixmap(pil_image: Image.Image) -> QPixmap:
        """Convert PIL Image to QPixmap.

        Args:
            pil_image: PIL Image to convert.

        Returns:
            QPixmap representation of the image.
        """
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
