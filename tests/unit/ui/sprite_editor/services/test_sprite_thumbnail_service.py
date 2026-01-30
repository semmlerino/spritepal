"""Unit tests for SpriteThumbnailService.

Tests the thumbnail service extracted from ROMWorkflowController.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from PySide6.QtGui import QPixmap

from ui.sprite_editor.services.sprite_thumbnail_service import (
    SpriteThumbnailService,
    ThumbnailDataProviderProtocol,
    ThumbnailViewProtocol,
)

if TYPE_CHECKING:
    from pathlib import Path


class MockDataProvider:
    """Mock implementation of ThumbnailDataProviderProtocol."""

    def __init__(
        self,
        rom_path: str = "/path/to/rom.sfc",
        rom_extractor: MagicMock | None = None,
        current_tile_offset: int = -1,
        current_tile_data: bytes | None = None,
    ) -> None:
        self._rom_path = rom_path
        self._rom_extractor = rom_extractor
        self._current_tile_offset = current_tile_offset
        self._current_tile_data = current_tile_data

    @property
    def rom_path(self) -> str:
        return self._rom_path

    @property
    def rom_extractor(self) -> MagicMock | None:
        return self._rom_extractor

    @property
    def current_tile_offset(self) -> int:
        return self._current_tile_offset

    @property
    def current_tile_data(self) -> bytes | None:
        return self._current_tile_data


class MockViewAdapter:
    """Mock implementation of ThumbnailViewProtocol."""

    def __init__(self) -> None:
        self.set_thumbnail_calls: list[tuple[int, QPixmap, str]] = []

    def set_thumbnail(self, offset: int, pixmap: QPixmap, source_type: str) -> None:
        self.set_thumbnail_calls.append((offset, pixmap, source_type))


class TestSpriteThumbnailServiceInit:
    """Tests for SpriteThumbnailService initialization."""

    def test_init_with_no_dependencies(self) -> None:
        """Service can be initialized with no dependencies."""
        service = SpriteThumbnailService()
        assert service._data_provider is None
        assert service._sprite_library is None
        assert service._thumbnail_controller is None
        assert service._view_adapter is None

    def test_init_with_data_provider(self) -> None:
        """Service accepts data provider at init."""
        provider = MockDataProvider()
        service = SpriteThumbnailService(data_provider=provider)
        assert service._data_provider is provider

    def test_set_view_adapter(self) -> None:
        """View adapter can be set after init."""
        service = SpriteThumbnailService()
        adapter = MockViewAdapter()
        service.set_view_adapter(adapter)
        assert service._view_adapter is adapter


class TestSpriteThumbnailServiceRequests:
    """Tests for thumbnail request methods."""

    def test_request_thumbnail_no_controller(self) -> None:
        """request_thumbnail is no-op when no controller."""
        service = SpriteThumbnailService()
        # Should not raise
        service.request_thumbnail(0x10000)

    def test_request_thumbnail_with_controller(self) -> None:
        """request_thumbnail delegates to controller."""
        service = SpriteThumbnailService()
        mock_controller = MagicMock()
        service._thumbnail_controller = mock_controller

        service.request_thumbnail(0x10000)
        mock_controller.queue_thumbnail.assert_called_once_with(0x10000)

    def test_request_batch_no_controller(self) -> None:
        """request_batch is no-op when no controller."""
        service = SpriteThumbnailService()
        # Should not raise
        service.request_batch([0x10000, 0x20000])

    def test_request_batch_empty_list(self) -> None:
        """request_batch is no-op for empty list."""
        service = SpriteThumbnailService()
        mock_controller = MagicMock()
        service._thumbnail_controller = mock_controller

        service.request_batch([])
        mock_controller.queue_batch.assert_not_called()

    def test_request_batch_with_offsets(self) -> None:
        """request_batch delegates to controller."""
        service = SpriteThumbnailService()
        mock_controller = MagicMock()
        service._thumbnail_controller = mock_controller

        offsets = [0x10000, 0x20000, 0x30000]
        service.request_batch(offsets)
        mock_controller.queue_batch.assert_called_once_with(offsets)

    def test_invalidate_offset(self) -> None:
        """invalidate_offset delegates to controller."""
        service = SpriteThumbnailService()
        mock_controller = MagicMock()
        service._thumbnail_controller = mock_controller

        service.invalidate_offset(0x10000)
        mock_controller.invalidate_offset.assert_called_once_with(0x10000)

    def test_clear_cache(self) -> None:
        """clear_cache delegates to worker."""
        service = SpriteThumbnailService()
        mock_controller = MagicMock()
        mock_worker = MagicMock()
        mock_controller.worker = mock_worker
        service._thumbnail_controller = mock_controller

        service.clear_cache()
        mock_worker.clear_cache.assert_called_once()


@pytest.mark.usefixtures("qapp")
class TestPilToQPixmap:
    """Tests for static pil_to_qpixmap conversion.

    Note: These tests require QApplication (qapp fixture) because QPixmap
    creation requires the Qt GUI event loop to be initialized.
    """

    def test_converts_rgba_image(self) -> None:
        """RGBA image is converted to QPixmap."""
        img = Image.new("RGBA", (8, 8), (255, 0, 0, 128))
        pixmap = SpriteThumbnailService.pil_to_qpixmap(img)

        assert isinstance(pixmap, QPixmap)
        assert pixmap.width() == 8
        assert pixmap.height() == 8

    def test_converts_rgb_image(self) -> None:
        """RGB image is converted (via RGBA) to QPixmap."""
        img = Image.new("RGB", (16, 16), (0, 255, 0))
        pixmap = SpriteThumbnailService.pil_to_qpixmap(img)

        assert isinstance(pixmap, QPixmap)
        assert pixmap.width() == 16
        assert pixmap.height() == 16

    def test_converts_palette_image(self) -> None:
        """Palette (P mode) image is converted to QPixmap."""
        img = Image.new("P", (8, 8))
        img.putpalette([i % 256 for i in range(768)])  # Full palette (values 0-255)
        pixmap = SpriteThumbnailService.pil_to_qpixmap(img)

        assert isinstance(pixmap, QPixmap)
        assert pixmap.width() == 8
        assert pixmap.height() == 8


class TestGenerateLibraryThumbnail:
    """Tests for generate_library_thumbnail method."""

    def test_returns_none_without_data_provider(self) -> None:
        """Returns None when no data provider is set."""
        service = SpriteThumbnailService()
        result = service.generate_library_thumbnail(0x10000)
        assert result is None

    def test_returns_none_without_rom_path(self) -> None:
        """Returns None when data provider has no rom_path."""
        provider = MockDataProvider(rom_path="")
        service = SpriteThumbnailService(data_provider=provider)
        result = service.generate_library_thumbnail(0x10000)
        assert result is None

    def test_uses_edited_pixels_when_provided(self) -> None:
        """Uses provided edited pixels instead of ROM data."""
        provider = MockDataProvider()
        service = SpriteThumbnailService(data_provider=provider)

        # Create a palette image with edited pixels
        img = Image.new("P", (16, 16))
        img.putpalette([i % 256 for i in range(768)])
        flat_palette = [i % 256 for i in range(768)]

        result = service.generate_library_thumbnail(
            0x10000, edited_pixels=(img, flat_palette)
        )

        assert result is not None
        assert isinstance(result, Image.Image)

    def test_uses_current_tile_data_when_offset_matches(self, tmp_path: Path) -> None:
        """Uses current_tile_data when offset matches."""
        # Create a temp ROM file
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 0x20000)

        # 4 tiles worth of data (32 bytes per tile)
        tile_data = b"\x00" * 128

        provider = MockDataProvider(
            rom_path=str(rom_path),
            current_tile_offset=0x10000,
            current_tile_data=tile_data,
        )
        service = SpriteThumbnailService(data_provider=provider)

        # Patch at the source module since the import is inline
        with patch("core.tile_renderer.TileRenderer") as mock_renderer_class:
            mock_renderer = MagicMock()
            mock_renderer.render_tiles.return_value = Image.new("P", (64, 32))
            mock_renderer_class.return_value = mock_renderer

            result = service.generate_library_thumbnail(0x10000)

            # Should use the cached tile_data, not read from ROM
            mock_renderer.render_tiles.assert_called_once()
            assert result is not None


@pytest.mark.usefixtures("qapp")
class TestLoadLibraryThumbnail:
    """Tests for load_library_thumbnail method.

    Note: These tests require QApplication (qapp fixture) because QPixmap
    creation requires the Qt GUI event loop to be initialized.
    """

    def test_returns_none_without_library(self) -> None:
        """Returns None when no sprite library is set."""
        service = SpriteThumbnailService()
        mock_sprite = MagicMock()
        result = service.load_library_thumbnail(mock_sprite)
        assert result is None

    def test_returns_none_when_no_thumbnail_path(self) -> None:
        """Returns None when sprite has no thumbnail path."""
        mock_library = MagicMock()
        mock_library.get_thumbnail_path.return_value = None

        service = SpriteThumbnailService(sprite_library=mock_library)
        mock_sprite = MagicMock()

        result = service.load_library_thumbnail(mock_sprite)
        assert result is None

    def test_returns_pixmap_when_thumbnail_exists(self, tmp_path: Path) -> None:
        """Returns QPixmap when thumbnail file exists."""
        # Create a test thumbnail file
        thumb_path = tmp_path / "thumb.png"
        img = Image.new("RGB", (64, 64), (128, 128, 128))
        img.save(thumb_path)

        mock_library = MagicMock()
        mock_library.get_thumbnail_path.return_value = thumb_path

        service = SpriteThumbnailService(sprite_library=mock_library)
        mock_sprite = MagicMock()

        result = service.load_library_thumbnail(mock_sprite)
        assert isinstance(result, QPixmap)
        assert result.width() == 64
        assert result.height() == 64


@pytest.mark.usefixtures("qapp")
class TestRestoreLibraryThumbnails:
    """Tests for restore_library_thumbnails method.

    Note: These tests require QApplication (qapp fixture) because QPixmap
    creation requires the Qt GUI event loop to be initialized.
    """

    def test_returns_zero_without_dependencies(self) -> None:
        """Returns 0 when dependencies are missing."""
        service = SpriteThumbnailService()
        result = service.restore_library_thumbnails("/path/to/rom.sfc")
        assert result == 0

    def test_returns_zero_without_view(self) -> None:
        """Returns 0 when view adapter is not set."""
        mock_library = MagicMock()
        service = SpriteThumbnailService(sprite_library=mock_library)
        result = service.restore_library_thumbnails("/path/to/rom.sfc")
        assert result == 0

    def test_restores_matching_sprites(self, tmp_path: Path) -> None:
        """Restores thumbnails for sprites matching ROM hash."""
        # Create test thumbnail
        thumb_path = tmp_path / "thumb.png"
        img = Image.new("RGB", (64, 64))
        img.save(thumb_path)

        # Create mock sprite with matching ROM hash
        mock_sprite = MagicMock()
        mock_sprite.rom_hash = "abc123"
        mock_sprite.rom_offset = 0x10000

        # Create mock library
        mock_library = MagicMock()
        mock_library.compute_rom_hash.return_value = "abc123"
        mock_library.sprites = [mock_sprite]
        mock_library.get_thumbnail_path.return_value = thumb_path

        # Create service with all dependencies
        view_adapter = MockViewAdapter()
        service = SpriteThumbnailService(sprite_library=mock_library)
        service.set_view_adapter(view_adapter)

        result = service.restore_library_thumbnails("/path/to/rom.sfc")

        assert result == 1
        assert len(view_adapter.set_thumbnail_calls) == 1
        offset, _, source_type = view_adapter.set_thumbnail_calls[0]
        assert offset == 0x10000
        assert source_type == "library"


class TestCleanup:
    """Tests for cleanup method."""

    def test_cleanup_without_controller(self) -> None:
        """Cleanup is safe when no controller exists."""
        service = SpriteThumbnailService()
        # Should not raise
        service.cleanup()
        assert service._thumbnail_controller is None

    def test_cleanup_calls_controller_cleanup(self) -> None:
        """Cleanup calls controller.cleanup() and clears reference."""
        service = SpriteThumbnailService()
        mock_controller = MagicMock()
        service._thumbnail_controller = mock_controller

        service.cleanup()

        mock_controller.cleanup.assert_called_once()
        assert service._thumbnail_controller is None
