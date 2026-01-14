"""
Integration tests for sprite gallery functionality.
Tests the complete gallery system including detached windows and thumbnails.

REAL COMPONENT TESTING:
- Uses RealComponentFactory for ROMExtractor with MockHAL
- Tests actual component behavior, not mock behavior
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy

from tests.fixtures.timeouts import signal_timeout
from tests.infrastructure.real_component_factory import RealComponentFactory
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage
from ui.tabs.sprite_gallery_tab import SpriteGalleryTab
from ui.windows.detached_gallery_window import DetachedGalleryWindow

# Use function-scoped app_context for proper test isolation
# (migrated from session_app_context to fix shared state and thread cleanup issues)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("app_context"),
]


@pytest.fixture
def real_factory(tmp_path, app_context, isolated_data_repository):
    """Create RealComponentFactory for integration tests."""
    # context_guaranteed=True because app_context fixture guarantees context exists
    with RealComponentFactory(context_guaranteed=True, data_repository=isolated_data_repository) as factory:
        yield factory


@pytest.fixture
def gallery_tab(qtbot, real_factory):
    """Create a gallery tab for testing with real components."""
    tab = SpriteGalleryTab()
    qtbot.addWidget(tab)

    # Setup ROM data
    tab.rom_path = "test_rom.smc"
    tab.rom_size = 4 * 1024 * 1024

    # Use real extractor with mock HAL for speed
    tab.rom_extractor = real_factory.create_rom_extractor(use_mock_hal=True)

    yield tab

    # Cleanup worker threads before widget destruction
    tab.cleanup()


@pytest.fixture
def test_sprites():
    """Create test sprite data."""
    sprites = []
    for i in range(17):
        sprites.append(
            {
                "offset": i * 0x1000,
                "decompressed_size": 2048,
                "tile_count": 64,
                "compressed": i % 3 == 0,
            }
        )
    return sprites


@pytest.fixture
def gallery_with_sprites(gallery_tab, test_sprites):
    """Gallery tab with sprites loaded."""
    gallery_tab.sprites_data = test_sprites
    gallery_tab.gallery_widget.set_sprites(test_sprites)

    # Generate mock thumbnails using the gallery widget's API
    for sprite in test_sprites:
        offset = sprite["offset"]
        # Using ThreadSafeTestImage instead of QPixmap for thread safety
        pixmap = ThreadSafeTestImage(128, 128)
        pixmap.fill(Qt.GlobalColor.darkGray)
        # Use the correct API: set_thumbnail on the gallery widget
        gallery_tab.gallery_widget.set_thumbnail(offset, pixmap)

    yield gallery_tab

    # Cleanup worker threads before widget destruction
    gallery_tab.cleanup()


class TestSpriteGalleryTab:
    """Test the main sprite gallery tab."""

    @pytest.mark.gui
    def test_gallery_initialization(self, gallery_tab):
        """Test that gallery tab initializes correctly."""
        assert gallery_tab.gallery_widget is not None
        assert gallery_tab.toolbar is not None
        assert gallery_tab.info_label is not None
        assert gallery_tab.detached_window is None

    @pytest.mark.gui
    def test_set_sprites(self, gallery_tab, test_sprites, qtbot):
        """Test setting sprites in the gallery."""
        gallery_tab.sprites_data = test_sprites
        gallery_tab.gallery_widget.set_sprites(test_sprites)

        # Wait for layout update
        qtbot.waitUntil(lambda: len(gallery_tab.gallery_widget.thumbnails) == 17, timeout=signal_timeout())

        # Check thumbnails were created
        assert len(gallery_tab.gallery_widget.thumbnails) == 17

        # Check status label
        status_text = gallery_tab.gallery_widget.status_label.text()
        assert "17 sprites" in status_text

    @pytest.mark.gui
    def test_thumbnail_generation(self, gallery_with_sprites):
        """Test that thumbnails are generated with pixmaps."""
        gallery = gallery_with_sprites.gallery_widget

        # Check all thumbnails have pixmaps via the model
        valid_count = 0
        for offset in gallery.thumbnails:
            pixmap = gallery.model.get_sprite_pixmap(offset)
            if pixmap and not pixmap.isNull():
                valid_count += 1

        assert valid_count == 17, f"Expected 17 valid pixmaps, got {valid_count}"


class TestDetachedGalleryWindow:
    """Test the detached gallery window functionality."""

    @pytest.mark.gui
    def test_open_detached_gallery(self, gallery_with_sprites, qtbot, managers_initialized):
        """Test opening the detached gallery window."""
        tab = gallery_with_sprites

        # Open detached gallery
        tab._open_detached_gallery()

        # Wait for window to appear
        qtbot.waitUntil(lambda: tab.detached_window is not None, timeout=signal_timeout())

        # Check window was created
        assert tab.detached_window is not None
        assert isinstance(tab.detached_window, DetachedGalleryWindow)

        # Check window is visible
        assert tab.detached_window.isVisible()

        # Close window
        tab.detached_window.close()

    @pytest.mark.gui
    def test_detached_window_signals(self, gallery_with_sprites, qtbot, managers_initialized):
        """Test that detached window signals are connected properly."""
        tab = gallery_with_sprites

        # Connect to sprite_selected signal
        selected_sprites = []
        tab.sprite_selected.connect(lambda offset: selected_sprites.append(offset))

        # Open detached gallery
        tab._open_detached_gallery()
        qtbot.waitUntil(lambda: tab.detached_window is not None, timeout=signal_timeout())

        detached_gallery = tab.detached_window.gallery_widget

        # Simulate sprite selection in detached window
        if detached_gallery.thumbnails:
            first_offset = next(iter(detached_gallery.thumbnails.keys()))
            detached_gallery.sprite_selected.emit(first_offset)

            # Check signal was propagated
            assert len(selected_sprites) == 1
            assert selected_sprites[0] == first_offset

        # Close window
        tab.detached_window.close()

    @pytest.mark.gui
    def test_detached_window_close_cleanup(self, gallery_with_sprites, qtbot, managers_initialized):
        """Test that closing detached window cleans up properly."""
        tab = gallery_with_sprites

        # Open detached gallery
        tab._open_detached_gallery()
        qtbot.waitUntil(lambda: tab.detached_window is not None, timeout=signal_timeout())

        assert tab.detached_window is not None

        # Close window
        tab.detached_window.close()
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        # Trigger the close handler
        tab._on_detached_closed()

        # Check cleanup
        assert tab.detached_window is None


class TestGalleryCaching:
    """Test gallery scan result caching."""

    @pytest.mark.gui
    def test_cache_save(self, gallery_with_sprites, tmp_path, monkeypatch):
        """Test saving scan results to cache."""
        tab = gallery_with_sprites

        # Mock cache path to use tmp directory
        def mock_cache_path(self, rom_path=None):
            return tmp_path / "test_cache.json"

        monkeypatch.setattr(SpriteGalleryTab, "_get_cache_path", mock_cache_path)

        # Save cache
        tab._save_scan_cache()

        # Check cache file exists
        cache_file = tmp_path / "test_cache.json"
        assert cache_file.exists()

        # Load and verify cache content
        import json

        with cache_file.open() as f:
            cache_data = json.load(f)

        assert cache_data["sprite_count"] == 17
        assert len(cache_data["sprites"]) == 17
        assert cache_data["rom_path"] == "test_rom.smc"

    @pytest.mark.gui
    def test_cache_load(self, gallery_tab, test_sprites, tmp_path, monkeypatch):
        """Test loading scan results from cache."""

        # Mock cache path
        def mock_cache_path(self, rom_path=None):
            return tmp_path / "test_cache.json"

        monkeypatch.setattr(SpriteGalleryTab, "_get_cache_path", mock_cache_path)

        # Create cache file
        import json

        cache_data = {
            "version": 2,
            "rom_path": "test_rom.smc",
            "rom_size": 4 * 1024 * 1024,
            "sprite_count": len(test_sprites),
            "sprites": test_sprites,
            "scan_mode": "quick",
            "timestamp": 0,
        }

        cache_file = tmp_path / "test_cache.json"
        with cache_file.open("w") as f:
            json.dump(cache_data, f)

        # Load cache
        result = gallery_tab._load_scan_cache("test_rom.smc")

        assert result == True
        assert len(gallery_tab.sprites_data) == 17
        assert len(gallery_tab.gallery_widget.thumbnails) == 17


@pytest.mark.gui
class TestGalleryIntegration:
    """Full integration tests using real components."""

    def test_complete_workflow(self, qtbot, managers_initialized, real_factory):
        """Test complete workflow from loading to detached window with real components."""
        # Create gallery tab
        tab = SpriteGalleryTab()
        qtbot.addWidget(tab)

        # Set ROM data with real extractor
        real_extractor = real_factory.create_rom_extractor(use_mock_hal=True)
        tab.set_rom_data("test_rom.smc", 4 * 1024 * 1024, real_extractor)

        # Create and set sprites
        sprites = []
        for i in range(10):
            sprites.append(
                {
                    "offset": i * 0x1000,
                    "decompressed_size": 1024,
                    "tile_count": 32,
                    "compressed": i % 2 == 0,
                }
            )

        tab.sprites_data = sprites
        tab.gallery_widget.set_sprites(sprites)

        # Generate thumbnails using the gallery widget's API
        for sprite in sprites:
            offset = sprite["offset"]
            # Using ThreadSafeTestImage instead of QPixmap for thread safety
            pixmap = ThreadSafeTestImage(128, 128)
            pixmap.fill(Qt.GlobalColor.darkCyan)
            tab.gallery_widget.set_thumbnail(offset, pixmap)

        # Verify main gallery
        assert len(tab.gallery_widget.thumbnails) == 10

        # Open detached window
        tab._open_detached_gallery()
        qtbot.waitUntil(lambda: tab.detached_window is not None, timeout=signal_timeout())

        # Verify detached window
        assert tab.detached_window is not None
        assert len(tab.detached_window.gallery_widget.thumbnails) == 10

        # NOTE: Thumbnails are not automatically copied in virtual scrolling implementation
        # The detached gallery loads thumbnails on demand
        # So we just verify the detached gallery was created with the right sprite count

        # Clean up - tab.cleanup() handles closing detached window and stopping workers
        # Don't call close() separately as it can cause double-cleanup issues
        tab.cleanup()
        # Process any pending events synchronously to prevent segfaults from dangling references
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()
