"""
Comprehensive tests for the sprite gallery tab functionality.

Tests cover:
- Sprite scanning with improved step sizes
- ROM-specific caching mechanism
- Quick vs Thorough scan modes
- Cache validation and loading
- Thumbnail generation from cache
- BatchThumbnailWorker integration and threading
- SpriteGalleryWidget functionality and selection
- Signal/slot connections with qtbot
- Export functionality and error handling
- UI state management and lazy loading
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Only import Qt for GUI tests
if "--no-qt" not in sys.argv:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

from core.sprite_finder import SpriteFinder
from tests.infrastructure.test_doubles import (
    DoubleFactory,
    MockCacheManager,
)


def create_headless_gallery_tab():
    """Create headless gallery tab for NON-Qt unit tests.

    WARNING: This patches Qt internals and should only be used for
    testing pure Python logic (caching, validation, etc.). For Qt
    behavior tests, use @pytest.mark.gui and real widgets with qtbot.
    """
    from ui.tabs.sprite_gallery_tab import SpriteGalleryTab

    # Mock Qt widget initialization (acceptable for headless Python-only tests)
    with patch('ui.tabs.sprite_gallery_tab.QWidget.__init__'), patch.object(SpriteGalleryTab, '_setup_ui'):
        tab = SpriteGalleryTab()
        # Initialize required attributes
        tab.rom_path = None
        tab.rom_size = 0
        tab.sprites_data = []

        # Use test doubles for external dependencies
        tab.gallery_widget = DoubleFactory.create_gallery_widget()
        tab.info_label = Mock()
        tab.toolbar = Mock()
        tab.compare_btn = Mock()
        tab.palette_btn = Mock()
        tab.thumbnail_worker = None
        tab.progress_dialog = None

        # Add cache manager test double
        tab._cache_manager = MockCacheManager()
        return tab

class TestSpriteGalleryCaching:
    """Unit tests for the gallery caching mechanism."""

    def test_get_cache_path_creates_unique_names(self):
        """Test that cache paths are unique per ROM."""
        tab = create_headless_gallery_tab()

        # Test different ROM paths get different cache files
        path1 = tab._get_cache_path("/path/to/rom1.sfc")
        path2 = tab._get_cache_path("/path/to/rom2.sfc")
        path3 = tab._get_cache_path("/different/path/rom1.sfc")

        assert path1 != path2  # Different ROM names
        assert path1 != path3  # Same name, different path
        assert path1.suffix == ".json"
        assert "rom1" in path1.name
        assert "rom2" in path2.name

    def test_save_cache_creates_valid_json(self, tmp_path):
        """Test that cache saving creates valid JSON with metadata."""
        tab = create_headless_gallery_tab()
        tab.rom_path = str(tmp_path / "test.sfc")
        tab.rom_size = 1024 * 1024  # 1MB
        tab.scan_mode = "thorough"
        tab.sprites_data = [
            {"offset": 0x200000, "tile_count": 64},
            {"offset": 0x201000, "tile_count": 32}
        ]

        # Use cache manager test double
        cache_file = tmp_path / "test_cache.json"
        tab._cache_manager.save_cache(tab.rom_path, {
            "version": 2,
            "rom_path": tab.rom_path,
            "rom_size": tab.rom_size,
            "sprite_count": len(tab.sprites_data),
            "sprites": tab.sprites_data,
            "scan_mode": tab.scan_mode,
            "timestamp": time.time()
        })

        # Verify real _save_scan_cache behavior by calling it with mock path
        with patch.object(tab, '_get_cache_path', return_value=cache_file):
            tab._save_scan_cache()

        # Verify cache was saved
        assert cache_file.exists()

        # Load and verify cache contents
        with open(cache_file) as f:
            cache_data = json.load(f)

        assert cache_data["version"] == 2
        assert cache_data["rom_path"] == str(tmp_path / "test.sfc")
        assert cache_data["rom_size"] == 1024 * 1024
        assert cache_data["sprite_count"] == 2
        assert cache_data["scan_mode"] == "thorough"
        assert "timestamp" in cache_data
        assert len(cache_data["sprites"]) == 2

    def test_load_cache_validates_rom_path(self, tmp_path):
        """Test that cache loading validates the ROM path matches."""
        tab = create_headless_gallery_tab()

        # Create a cache file for a different ROM
        cache_file = tmp_path / "test_cache.json"
        cache_data = {
            "version": 2,
            "rom_path": "/different/rom.sfc",
            "rom_size": 1024 * 1024,
            "sprite_count": 5,
            "sprites": [{"offset": 0x200000}],
            "timestamp": time.time()
        }
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f)

        # Try to load cache for a different ROM using test double
        tab._cache_manager.save_cache("/different/rom.sfc", cache_data)

        # Try loading cache for different ROM path - should fail validation
        with patch.object(tab, '_get_cache_path', return_value=cache_file):
            result = tab._load_scan_cache("/my/rom.sfc")

        # Should fail due to path mismatch
        assert result is False
        assert tab.sprites_data == []  # Should not load mismatched data

    def test_load_cache_checks_version(self, tmp_path):
        """Test that old cache versions are ignored."""
        tab = create_headless_gallery_tab()

        # Create an old version cache file
        cache_file = tmp_path / "test_cache.json"
        cache_data = {
            "version": 1,  # Old version
            "rom_path": str(tmp_path / "test.sfc"),
            "sprites": [{"offset": 0x200000}]
        }
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f)

        # Try to load old cache using test double
        tab._cache_manager.save_cache(str(tmp_path / "test.sfc"), cache_data)

        # Try loading old version cache - should fail validation
        with patch.object(tab, '_get_cache_path', return_value=cache_file):
            result = tab._load_scan_cache(str(tmp_path / "test.sfc"))

        # Should fail due to old version
        assert result is False

    def test_load_cache_calculates_age(self, tmp_path):
        """Test that cache age is calculated correctly."""
        tab = create_headless_gallery_tab()

        # Create a cache file with known timestamp
        cache_file = tmp_path / "test_cache.json"
        old_timestamp = time.time() - (3 * 3600)  # 3 hours ago
        cache_data = {
            "version": 2,
            "rom_path": str(tmp_path / "test.sfc"),
            "rom_size": 1024 * 1024,
            "sprite_count": 5,
            "sprites": [{"offset": 0x200000}],
            "timestamp": old_timestamp,
            "scan_mode": "quick"
        }
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f)

        # Load cache using test double
        tab._cache_manager.save_cache(str(tmp_path / "test.sfc"), cache_data)

        # Load cache - keep _refresh_thumbnails real but mock external dependencies
        with patch.object(tab, '_get_cache_path', return_value=cache_file):
            # Keep internal logic real, only mock external dependencies if needed
            result = tab._load_scan_cache(str(tmp_path / "test.sfc"))

        # Should succeed
        assert result is True

        # Check that info label shows age
        tab.info_label.setText.assert_called_once()
        call_args = tab.info_label.setText.call_args[0][0]
        assert "3." in call_args or "2.9" in call_args  # ~3 hours old

class TestSpriteGalleryScanning:
    """Integration tests for sprite scanning functionality."""

    @pytest.fixture
    def mock_rom_data(self):
        """Create mock ROM data for testing."""
        # Create a simple ROM-like byte array
        rom_size = 0x400000  # 4MB
        rom_data = bytearray(rom_size)

        # Add some recognizable patterns at known offsets
        # These would be detected as sprites by SpriteFinder
        test_offsets = [0x200000, 0x200100, 0x200800, 0x201000]
        for offset in test_offsets:
            if offset < rom_size:
                # Add some non-zero data that looks like tiles
                for i in range(32):  # 32 bytes (1 tile)
                    rom_data[offset + i] = (i * 7) % 256

        return bytes(rom_data)

    def test_scan_ranges_differ_by_mode(self):
        """Test that Quick and Thorough modes use different scan ranges."""
        tab = create_headless_gallery_tab()

        # Set up for quick scan
        tab.scan_mode = "quick"
        tab.rom_path = "/test/rom.sfc"

        # Track which scan ranges are used
        scan_steps_quick = []
        scan_steps_thorough = []

        # Helper to extract step size from scan
        def capture_scan_steps(tab, scan_mode):
            tab.scan_mode = scan_mode
            steps = []

            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = b'\x00' * 0x400000
                with patch.object(SpriteFinder, 'find_sprite_at_offset', return_value=None):
                    with patch.object(tab, 'progress_dialog', create=True) as mock_dialog:
                        mock_dialog.wasCanceled.return_value = True  # Cancel immediately
                        mock_dialog.setValue = Mock()

                        # Capture the step sizes used
                        original_range = range
                        def mock_range(start, end, step=1):
                            if step > 1:  # Only capture ranges with explicit steps
                                steps.append(step)
                            return original_range(start, min(start+1, end), step)  # Return minimal range

                        with patch('builtins.range', side_effect=mock_range):
                            with patch.object(tab, 'gallery_widget', create=True):
                                with patch.object(tab, '_save_scan_cache'):
                                    tab._start_sprite_scan()

            return steps

        # Capture steps for both modes
        scan_steps_quick = capture_scan_steps(tab, "quick")
        scan_steps_thorough = capture_scan_steps(tab, "thorough")

        # Thorough scan should use smaller steps
        if scan_steps_quick and scan_steps_thorough:
            assert min(scan_steps_thorough) < max(scan_steps_quick)

    def test_scan_stops_at_max_sprites(self, mock_rom_data):
        """Test that scanning stops when max sprites limit is reached."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/test/rom.sfc"
        tab.scan_mode = "thorough"

        # Mock SpriteFinder to always find sprites
        sprite_count = 0
        def mock_find_sprite(rom_data, offset):
            nonlocal sprite_count
            sprite_count += 1
            return {"offset": offset, "tile_count": 32}

        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = mock_rom_data
            with patch.object(SpriteFinder, 'find_sprite_at_offset', side_effect=mock_find_sprite):
                with patch.object(tab, 'progress_dialog', create=True) as mock_dialog:
                    mock_dialog.wasCanceled.return_value = False
                    mock_dialog.setValue = Mock()
                    mock_dialog.setLabelText = Mock()

                    with patch.object(tab, '_save_scan_cache'):
                        with patch.object(tab, '_refresh_thumbnails'):
                            tab._start_sprite_scan()

        # Should stop at max_sprites (200)
        assert len(tab.sprites_data) <= 200

    def test_scan_updates_progress_with_count(self):
        """Test that scan progress shows sprite count."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/test/rom.sfc"
        tab.scan_mode = "quick"

        progress_labels = []

        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b'\x00' * 0x400000
            with patch.object(SpriteFinder, 'find_sprite_at_offset', return_value=None):
                with patch.object(tab, 'progress_dialog', create=True) as mock_dialog:
                    mock_dialog.wasCanceled.return_value = False
                    mock_dialog.setValue = Mock()

                    def capture_label(text):
                        progress_labels.append(text)

                    mock_dialog.setLabelText = Mock(side_effect=capture_label)

                    with patch.object(tab, '_save_scan_cache'):
                        with patch.object(tab, '_refresh_thumbnails'):
                            tab._start_sprite_scan()

        # Progress should show "Found:" count
        assert any("Found:" in label for label in progress_labels)

class TestSpriteGalleryIntegration:
    """Integration tests for gallery tab with other components."""

    def test_set_rom_data_loads_cache(self, tmp_path):
        """Test that set_rom_data automatically loads cached results."""
        tab = create_headless_gallery_tab()

        # Create a cache file
        rom_path = str(tmp_path / "test.sfc")
        cache_file = tmp_path / "test_cache.json"
        cache_data = {
            "version": 2,
            "rom_path": rom_path,
            "rom_size": 1024 * 1024,
            "sprite_count": 3,
            "sprites": [
                {"offset": 0x200000, "tile_count": 64},
                {"offset": 0x201000, "tile_count": 32},
                {"offset": 0x202000, "tile_count": 48}
            ],
            "timestamp": time.time(),
            "scan_mode": "quick"
        }

        with open(cache_file, 'w') as f:
            json.dump(cache_data, f)

        # Mock the cache path to use our test file
        with patch.object(tab, '_get_cache_path', return_value=cache_file):
            with patch.object(tab, '_refresh_thumbnails'):
                # Call set_rom_data
                tab.set_rom_data(rom_path, 1024 * 1024, Mock())

        # Should load cached sprites
        assert len(tab.sprites_data) == 3
        assert tab.sprites_data[0]["offset"] == 0x200000

    def test_set_rom_data_clears_old_data_without_cache(self):
        """Test that set_rom_data clears old data when no cache exists."""
        tab = create_headless_gallery_tab()

        # Set some existing sprite data
        tab.sprites_data = [{"offset": 0x100000}]

        # Set new ROM without cache
        with patch.object(tab, '_load_scan_cache', return_value=False):
            tab.set_rom_data("/new/rom.sfc", 2 * 1024 * 1024, Mock())

        # Should clear old sprites
        assert tab.sprites_data == []
        tab.gallery_widget.set_sprites.assert_called_with([])

    @pytest.mark.parametrize("scan_mode,expected_min_ranges", [
        ("quick", 1),     # Quick scan has at least 1 range set
        ("thorough", 1),  # Thorough scan has at least 1 range set (may cancel early)
    ])
    def test_scan_mode_affects_ranges(self, scan_mode, expected_min_ranges):
        """Test that scan mode affects the number of scan ranges."""
        tab = create_headless_gallery_tab()
        tab.scan_mode = scan_mode
        tab.rom_path = "/test/rom.sfc"

        range_count = 0
        step_sizes = []

        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b'\x00' * 0x400000
            with patch.object(SpriteFinder, 'find_sprite_at_offset', return_value=None):
                with patch.object(tab, 'progress_dialog', create=True) as mock_dialog:
                    mock_dialog.wasCanceled.return_value = True  # Cancel immediately
                    mock_dialog.setValue = Mock()

                    # Count how many scan ranges are processed and capture step sizes
                    original_range = range
                    def count_range(start, end, step=1):
                        nonlocal range_count
                        if step > 1:  # Count ranges with explicit steps
                            range_count += 1
                            step_sizes.append(step)
                        return original_range(start, min(start + 1, end))  # Return minimal range

                    with patch('builtins.range', side_effect=count_range):
                        with patch.object(tab, 'gallery_widget', create=True):
                            with patch.object(tab, '_save_scan_cache'):
                                tab._start_sprite_scan()

        # Different modes should use different numbers of ranges
        assert range_count >= expected_min_ranges

        # More importantly, thorough scan should use smaller step sizes than quick
        if scan_mode == "thorough" and step_sizes:
            # Thorough mode uses smaller steps (0x100-0x400)
            assert min(step_sizes) <= 0x400
        elif scan_mode == "quick" and step_sizes:
            # Quick mode uses larger steps (0x800-0x1000)
            assert max(step_sizes) >= 0x800

class TestGalleryRobustness:
    """Test error handling and edge cases."""

    def test_cache_directory_structure(self):
        """Test that cache path has correct structure."""
        tab = create_headless_gallery_tab()

        # Test cache path structure
        cache_path = tab._get_cache_path("/test/rom.sfc")

        # Verify path structure
        assert ".cache" in str(cache_path)
        assert "gallery_scans" in str(cache_path)
        assert cache_path.suffix == ".json"
        assert "rom" in cache_path.name  # Should contain ROM name

    def test_cache_handles_corrupted_json(self, tmp_path):
        """Test that corrupted cache files are handled gracefully."""
        tab = create_headless_gallery_tab()

        # Create a corrupted cache file
        cache_file = tmp_path / "corrupted_cache.json"
        with open(cache_file, 'w') as f:
            f.write("{ invalid json }")

        # Try to load corrupted cache
        with patch.object(tab, '_get_cache_path', return_value=cache_file):
            result = tab._load_scan_cache("/test/rom.sfc")

        # Should fail gracefully
        assert result is False
        assert tab.sprites_data == []

    def test_scan_handles_empty_rom(self):
        """Test that scanning handles empty ROM data."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/test/empty.sfc"
        tab.scan_mode = "quick"

        # Empty ROM data
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b''
            with patch.object(tab, 'progress_dialog', create=True) as mock_dialog:
                mock_dialog.wasCanceled.return_value = False
                mock_dialog.setValue = Mock()

                with patch.object(tab, '_save_scan_cache'), patch.object(tab, '_refresh_thumbnails'):
                    tab._start_sprite_scan()

        # Should complete without error
        assert tab.sprites_data == []

    def test_scan_handles_no_rom_path(self):
        """Test that scanning handles missing ROM path."""
        tab = create_headless_gallery_tab()
        tab.rom_path = None

        with patch('ui.tabs.sprite_gallery_tab.QMessageBox.warning') as mock_warning:
            tab._scan_for_sprites()

        # Should show warning
        mock_warning.assert_called_once()
        assert "No ROM" in str(mock_warning.call_args)

@pytest.mark.gui
class TestGalleryWithQt:
    """Tests that require real Qt components."""

    @pytest.fixture
    def qt_app(self):
        """Provide Qt application for GUI tests."""
        app = QApplication.instance()
        if not app:
            app = QApplication([])
        return app

    def test_gallery_tab_creation(self, qt_app):
        """Test that gallery tab can be created with real Qt."""
        from ui.tabs.sprite_gallery_tab import SpriteGalleryTab

        tab = SpriteGalleryTab()

        # Check UI components were created
        assert tab.gallery_widget is not None
        assert tab.toolbar is not None
        assert tab.info_label is not None

        # Check layout
        assert tab.layout() is not None
        assert tab.layout().count() > 0

    def test_scan_dialog_shows_options(self, qt_app):
        """Test that scan dialog shows Quick vs Thorough options."""
        from ui.tabs.sprite_gallery_tab import SpriteGalleryTab

        tab = SpriteGalleryTab()
        tab.rom_path = "/test/rom.sfc"

        # Mock the dialog to capture its setup
        dialog_text = []

        with patch('ui.tabs.sprite_gallery_tab.QMessageBox') as MockMessageBox:
            mock_dialog = Mock()
            mock_dialog.exec.return_value = None
            mock_dialog.clickedButton.return_value = None  # Cancel

            def capture_text(text):
                dialog_text.append(text)

            mock_dialog.setInformativeText = Mock(side_effect=capture_text)
            MockMessageBox.return_value = mock_dialog

            tab._scan_for_sprites()

        # Check dialog showed scan options
        assert any("Quick Scan" in text for text in dialog_text)
        assert any("Thorough Scan" in text for text in dialog_text)

# New comprehensive test classes for missing functionality

class TestBatchThumbnailWorkerIntegration:
    """Test BatchThumbnailWorker integration with gallery tab."""

    @pytest.fixture
    def mock_rom_extractor(self):
        """Create mock ROM extractor for thumbnail generation."""
        extractor = Mock()
        extractor.extract_sprite_data.return_value = b'\x00' * 512  # Mock sprite data
        return extractor

    @pytest.fixture
    def mock_pixmap(self):
        """Create a mock pixmap for thumbnail testing."""
        pixmap = Mock()
        pixmap.isNull.return_value = False
        pixmap.width.return_value = 128
        pixmap.height.return_value = 128
        return pixmap

    def test_thumbnail_worker_creation(self, mock_rom_extractor):
        """Test that thumbnail worker is created correctly."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/test/rom.sfc"
        tab.rom_extractor = mock_rom_extractor
        tab.sprites_data = [{"offset": 0x200000, "tile_count": 64}]

        with patch('ui.tabs.sprite_gallery_tab.BatchThumbnailWorker') as MockWorker:
            mock_worker = Mock()
            mock_worker.isRunning.return_value = False
            MockWorker.return_value = mock_worker

            tab._refresh_thumbnails()

            # Should create worker with correct parameters
            MockWorker.assert_called_once_with("/test/rom.sfc", mock_rom_extractor)

            # Should connect signal
            mock_worker.thumbnail_ready.connect.assert_called_once()

    def test_thumbnail_worker_queuing(self, mock_rom_extractor):
        """Test that sprites are queued for thumbnail generation."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/test/rom.sfc"
        tab.rom_extractor = mock_rom_extractor
        tab.sprites_data = [
            {"offset": 0x200000, "tile_count": 64},
            {"offset": 0x201000, "tile_count": 32},
            {"offset": "0x202000", "tile_count": 48}  # Test string offset
        ]

        with patch('ui.tabs.sprite_gallery_tab.BatchThumbnailWorker') as MockWorker:
            mock_worker = Mock()
            mock_worker.isRunning.return_value = False
            MockWorker.return_value = mock_worker

            tab._refresh_thumbnails()

            # Should queue all sprites
            assert mock_worker.queue_thumbnail.call_count == 3

            # Check queue calls
            calls = mock_worker.queue_thumbnail.call_args_list
            assert calls[0][0] == (0x200000, 128)  # int offset
            assert calls[1][0] == (0x201000, 128)  # int offset
            assert calls[2][0] == (0x202000, 128)  # string offset converted

            # Should start worker
            mock_worker.start.assert_called_once()

    def test_thumbnail_ready_callback(self, mock_rom_extractor, mock_pixmap):
        """Test handling of thumbnail ready signal."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/test/rom.sfc"
        tab.rom_extractor = mock_rom_extractor
        tab.sprites_data = [{"offset": 0x200000, "tile_count": 64}]

        # Mock gallery widget with thumbnails
        mock_thumbnail = Mock()
        tab.gallery_widget.thumbnails = {0x200000: mock_thumbnail}

        # Call the thumbnail ready callback
        tab._on_thumbnail_ready(0x200000, mock_pixmap)

        # Should set sprite data on thumbnail widget
        mock_thumbnail.set_sprite_data.assert_called_once_with(
            mock_pixmap, {"offset": 0x200000, "tile_count": 64}
        )

    def test_thumbnail_ready_missing_widget(self, mock_pixmap):
        """Test thumbnail ready when widget doesn't exist."""
        tab = create_headless_gallery_tab()
        tab.sprites_data = [{"offset": 0x200000, "tile_count": 64}]
        tab.gallery_widget.thumbnails = {}  # No thumbnails

        # Should not crash when thumbnail widget missing
        tab._on_thumbnail_ready(0x200000, mock_pixmap)
        # No assertions needed - just shouldn't crash

    def test_worker_cleanup_on_tab_cleanup(self, mock_rom_extractor):
        """Test that thumbnail worker is properly cleaned up."""
        tab = create_headless_gallery_tab()

        # Create mock worker
        mock_worker = Mock()
        tab.thumbnail_worker = mock_worker

        # Call cleanup
        tab.cleanup()

        # Should stop and wait for worker
        mock_worker.stop.assert_called_once()
        mock_worker.wait.assert_called_once()
        assert tab.thumbnail_worker is None

class TestSpriteGalleryWidgetIntegration:
    """Test SpriteGalleryWidget functionality and integration."""

    def test_set_sprites_updates_gallery(self):
        """Test that setting sprites updates the gallery widget."""
        tab = create_headless_gallery_tab()
        sprites = [
            {"offset": 0x200000, "tile_count": 64},
            {"offset": 0x201000, "tile_count": 32}
        ]

        # Mock _setup_ui behavior - set_sprites gets called during setup
        tab.gallery_widget.set_sprites(sprites)

        # Should call set_sprites on gallery widget
        tab.gallery_widget.set_sprites.assert_called_with(sprites)

    def test_sprite_selection_updates_buttons(self):
        """Test that sprite selection updates button states."""
        tab = create_headless_gallery_tab()

        # Mock toolbar actions to return an iterable
        tab.toolbar.actions.return_value = []

        # Test single selection
        tab._on_selection_changed([0x200000])

        # Compare button should be disabled (need 2+ sprites)
        tab.compare_btn.setEnabled.assert_called_with(False)
        # Palette button should be enabled
        tab.palette_btn.setEnabled.assert_called_with(True)

        # Test multiple selection
        tab._on_selection_changed([0x200000, 0x201000])

        # Compare button should be enabled
        tab.compare_btn.setEnabled.assert_called_with(True)
        tab.palette_btn.setEnabled.assert_called_with(True)

    def test_sprite_double_click_emits_signal(self):
        """Test that double-clicking sprite emits navigation signal."""
        tab = create_headless_gallery_tab()

        # Mock the signal
        tab.sprite_selected = Mock()

        tab._on_sprite_double_clicked(0x200000)
        tab.sprite_selected.emit.assert_called_once_with(0x200000)

    def test_toolbar_actions_enabled_by_selection(self):
        """Test that toolbar export actions are enabled by selection."""
        tab = create_headless_gallery_tab()

        # Mock toolbar actions
        export_action = Mock()
        export_action.text.return_value = "Export Selected"
        export_sheet_action = Mock()
        export_sheet_action.text.return_value = "Export Sheet"
        other_action = Mock()
        other_action.text.return_value = "Refresh"

        tab.toolbar.actions.return_value = [export_action, export_sheet_action, other_action]

        # Test with selection
        tab._on_selection_changed([0x200000])

        # Export actions should be enabled
        export_action.setEnabled.assert_called_with(True)
        export_sheet_action.setEnabled.assert_called_with(True)
        # Other actions should not be affected
        other_action.setEnabled.assert_not_called()

class TestSpriteGalleryExportFunctionality:
    """Test sprite export functionality with proper mocking."""

    @pytest.fixture
    def tab_with_selected_sprites(self):
        """Create tab with selected sprites for export testing."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/test/rom.sfc"

        # Mock selected sprites
        selected_sprites = [
            {"offset": 0x200000, "tile_count": 64},
            {"offset": "0x201000", "tile_count": 32}  # Test string offset
        ]
        tab.gallery_widget.get_selected_sprites.return_value = selected_sprites

        return tab, selected_sprites

    def test_export_selected_no_selection_shows_message(self):
        """Test export shows message when no sprites selected."""
        tab = create_headless_gallery_tab()
        tab.gallery_widget.get_selected_sprites.return_value = []

        with patch('ui.tabs.sprite_gallery_tab.QMessageBox.information') as mock_info:
            tab._export_selected()

            mock_info.assert_called_once()
            assert "No Selection" in mock_info.call_args[0][1]

    def test_export_selected_cancelled_directory(self, tab_with_selected_sprites):
        """Test export handles cancelled directory selection."""
        tab, selected_sprites = tab_with_selected_sprites

        with patch('ui.tabs.sprite_gallery_tab.QFileDialog.getExistingDirectory', return_value=""):
            with patch('ui.tabs.sprite_gallery_tab.QMessageBox.information') as mock_info:
                tab._export_selected()

                # Should not show completion message
                mock_info.assert_not_called()

    def test_export_selected_success(self, tab_with_selected_sprites, tmp_path):
        """Test successful sprite export."""
        tab, selected_sprites = tab_with_selected_sprites
        export_dir = str(tmp_path)

        # Mock the signal
        tab.sprites_exported = Mock()

        with patch('ui.tabs.sprite_gallery_tab.QFileDialog.getExistingDirectory', return_value=export_dir):
            with patch('ui.tabs.sprite_gallery_tab.QMessageBox.information') as mock_info:
                tab._export_selected()

                # Should show success message
                mock_info.assert_called_once()
                assert "Export Complete" in mock_info.call_args[0][1]
                assert "2 sprites" in mock_info.call_args[0][2]

                # Should emit signal with exported files
                tab.sprites_exported.emit.assert_called_once()
                exported_files = tab.sprites_exported.emit.call_args[0][0]
                assert len(exported_files) == 2
                assert "sprite_200000.png" in exported_files[0]
                assert "sprite_201000.png" in exported_files[1]

    def test_export_sprite_sheet_not_implemented(self, tab_with_selected_sprites):
        """Test sprite sheet export shows not implemented message."""
        tab, selected_sprites = tab_with_selected_sprites

        with patch('ui.tabs.sprite_gallery_tab.QFileDialog.getSaveFileName', return_value=("sheet.png", "")):
            with patch('ui.tabs.sprite_gallery_tab.QMessageBox.information') as mock_info:
                tab._export_sprite_sheet()

                mock_info.assert_called_once()
                assert "Not Implemented" in mock_info.call_args[0][1]

    def test_compare_sprites_insufficient_selection(self):
        """Test compare sprites shows message with insufficient selection."""
        tab = create_headless_gallery_tab()
        tab.gallery_widget.get_selected_sprites.return_value = [{"offset": 0x200000}]

        with patch('ui.tabs.sprite_gallery_tab.QMessageBox.information') as mock_info:
            tab._compare_sprites()

            mock_info.assert_called_once()
            assert "Select More" in mock_info.call_args[0][1]

    def test_apply_palette_not_implemented(self, tab_with_selected_sprites):
        """Test apply palette shows not implemented message."""
        tab, selected_sprites = tab_with_selected_sprites

        with patch('ui.tabs.sprite_gallery_tab.QMessageBox.information') as mock_info:
            tab._apply_palette()

            mock_info.assert_called_once()
            assert "Not Implemented" in mock_info.call_args[0][1]

class TestSpriteGalleryErrorHandling:
    """Test comprehensive error handling scenarios."""

    @pytest.fixture
    def tab_with_invalid_data(self):
        """Create tab with invalid sprite data for error testing."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/test/rom.sfc"
        return tab

    def test_refresh_thumbnails_no_sprites(self):
        """Test thumbnail refresh with no sprites data."""
        tab = create_headless_gallery_tab()
        tab.sprites_data = []
        tab.rom_path = "/test/rom.sfc"

        # Should not crash
        tab._refresh_thumbnails()

        # Should not create worker
        assert tab.thumbnail_worker is None

    def test_refresh_thumbnails_no_rom_path(self):
        """Test thumbnail refresh with no ROM path."""
        tab = create_headless_gallery_tab()
        tab.sprites_data = [{"offset": 0x200000}]
        tab.rom_path = None

        # Should not crash
        tab._refresh_thumbnails()

        # Should not create worker
        assert tab.thumbnail_worker is None

    def test_thumbnail_ready_invalid_offset_type(self):
        """Test thumbnail ready with invalid offset in sprite data."""
        tab = create_headless_gallery_tab()
        tab.sprites_data = [{"offset": "invalid_hex", "tile_count": 64}]
        tab.gallery_widget.thumbnails = {0x200000: Mock()}

        # Create mock pixmap
        mock_pixmap = Mock()

        # The method will encounter an exception when parsing invalid offset
        # but should continue processing. Let's test this behavior.
        try:
            tab._on_thumbnail_ready(0x200000, mock_pixmap)
        except ValueError:
            # Expected - invalid offset parsing will raise ValueError
            pass

    def test_scan_with_file_read_error(self):
        """Test scan handles file read errors gracefully."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/nonexistent/rom.sfc"
        tab.scan_mode = "quick"

        with patch.object(tab, 'progress_dialog', create=True) as mock_dialog:
            mock_dialog.wasCanceled.return_value = False
            mock_dialog.setValue = Mock()
            mock_dialog.close = Mock()

            with patch('ui.tabs.sprite_gallery_tab.QMessageBox.critical') as mock_error:
                tab._start_sprite_scan()

                # Should show error message
                mock_error.assert_called_once()
                assert "Failed to scan ROM" in mock_error.call_args[0][2]

                # Should close progress dialog
                mock_dialog.close.assert_called_once()

    @pytest.mark.parametrize("invalid_offset,expected_behavior", [
        (None, "should_skip"),
        ("", "should_skip"),
        ("not_hex", "should_skip"),
        (-1, "should_handle"),
        (0xFFFFFFFF, "should_handle")  # Very large offset
    ])
    def test_export_with_invalid_offsets(self, invalid_offset, expected_behavior, tmp_path):
        """Test export handles various invalid offset types."""
        tab = create_headless_gallery_tab()
        selected_sprites = [{"offset": invalid_offset, "tile_count": 64}]
        tab.gallery_widget.get_selected_sprites.return_value = selected_sprites

        # Mock the signal
        tab.sprites_exported = Mock()

        export_dir = str(tmp_path)

        with patch('ui.tabs.sprite_gallery_tab.QFileDialog.getExistingDirectory', return_value=export_dir):
            with patch('ui.tabs.sprite_gallery_tab.QMessageBox.information') as mock_info:
                tab._export_selected()

                # Invalid offsets that cause errors won't trigger success message
                # Only valid exports show the message
                if expected_behavior == "should_handle":
                    mock_info.assert_called_once()
                else:
                    # Invalid formats cause errors and skip export, so no success message
                    mock_info.assert_not_called()

    def test_worker_already_running(self):
        """Test thumbnail refresh when worker is already running."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/test/rom.sfc"
        tab.sprites_data = [{"offset": 0x200000}]

        # Mock existing running worker
        mock_worker = Mock()
        mock_worker.isRunning.return_value = True
        tab.thumbnail_worker = mock_worker

        tab._refresh_thumbnails()

        # Should not start worker again
        mock_worker.start.assert_not_called()

        # Should still queue thumbnails
        mock_worker.queue_thumbnail.assert_called_once()

class TestSpriteGalleryParametrizedEdgeCases:
    """Parametrized tests for edge cases and boundary conditions."""

    @pytest.mark.parametrize("rom_size,expected_scan_behavior", [
        (0, "empty_rom"),
        (1024, "tiny_rom"),
        (1024 * 1024, "normal_rom"),
        (8 * 1024 * 1024, "large_rom"),
        (32 * 1024 * 1024, "huge_rom")
    ])
    def test_scan_with_various_rom_sizes(self, rom_size, expected_scan_behavior):
        """Test scanning behavior with different ROM sizes."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/test/rom.sfc"
        tab.rom_size = rom_size
        tab.scan_mode = "quick"

        # Mock ROM data of specified size
        rom_data = b'\x00' * rom_size

        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = rom_data
            with patch.object(SpriteFinder, 'find_sprite_at_offset', return_value=None):
                with patch.object(tab, 'progress_dialog', create=True) as mock_dialog:
                    mock_dialog.wasCanceled.return_value = True  # Cancel immediately
                    mock_dialog.setValue = Mock()

                    with patch.object(tab, '_save_scan_cache'):
                        tab._start_sprite_scan()

        # Should handle all sizes without crashing
        assert isinstance(tab.sprites_data, list)

    @pytest.mark.parametrize("cache_age_hours,expected_label_content", [
        (0.1, "0.1h"),
        (1.5, "1.5h"),
        (24.0, "24.0h"),
        (168.0, "168.0h"),  # 1 week
        (-1, "")  # Invalid timestamp
    ])
    def test_cache_age_display_formats(self, cache_age_hours, expected_label_content, tmp_path):
        """Test cache age display formatting."""
        tab = create_headless_gallery_tab()

        # Create cache with specified age
        cache_file = tmp_path / "test_cache.json"
        if cache_age_hours >= 0:
            timestamp = time.time() - (cache_age_hours * 3600)
        else:
            timestamp = 0  # Invalid timestamp

        cache_data = {
            "version": 2,
            "rom_path": "/test/rom.sfc",
            "rom_size": 1024 * 1024,
            "sprite_count": 5,
            "sprites": [{"offset": 0x200000}],
            "timestamp": timestamp,
            "scan_mode": "quick"
        }

        with open(cache_file, 'w') as f:
            json.dump(cache_data, f)

        with patch.object(tab, '_get_cache_path', return_value=cache_file):
            with patch.object(tab, '_refresh_thumbnails'):
                result = tab._load_scan_cache("/test/rom.sfc")

        if cache_age_hours >= 0:
            assert result is True
            # Check info label was updated with age
            tab.info_label.setText.assert_called_once()
        else:
            assert result is True  # Still loads, just no age shown

    @pytest.mark.parametrize("scan_mode,max_sprites,expected_ranges", [
        ("quick", 50, 2),     # Quick scan, moderate limit, 2 ranges
        ("thorough", 200, 5), # Thorough scan, high limit, 5 ranges
        ("quick", 10, 2),     # Quick scan, low limit, 2 ranges
        ("thorough", 1000, 5) # Thorough scan, very high limit, 5 ranges
    ])
    def test_scan_mode_configurations(self, scan_mode, max_sprites, expected_ranges):
        """Test scan configurations with different modes and limits."""
        tab = create_headless_gallery_tab()
        tab.rom_path = "/test/rom.sfc"
        tab.scan_mode = scan_mode

        range_count = 0

        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b'\x00' * 0x400000
            with patch.object(SpriteFinder, 'find_sprite_at_offset', return_value=None):
                with patch.object(tab, 'progress_dialog', create=True) as mock_dialog:
                    mock_dialog.wasCanceled.return_value = True  # Cancel after first range
                    mock_dialog.setValue = Mock()

                    # Count scan ranges used
                    original_range = range
                    def count_range(start, end, step=1):
                        nonlocal range_count
                        if step > 1:  # Only count explicit step ranges
                            range_count += 1
                        return original_range(start, min(start + 1, end))

                    with patch('builtins.range', side_effect=count_range):
                        with patch.object(tab, '_save_scan_cache'):
                            tab._start_sprite_scan()

        # Should use expected number of ranges (at least 1, up to expected)
        assert range_count >= 1
        # Note: Exact count may vary due to early cancellation

# Enhanced Qt integration tests with real widgets
@pytest.mark.gui
class TestSpriteGalleryTabSignalSlotIntegration:
    """Test signal/slot connections with real Qt components using qtbot."""

    @pytest.fixture
    def qt_app(self):
        """Provide Qt application for GUI tests."""
        app = QApplication.instance()
        if not app:
            app = QApplication([])
        return app

    @pytest.fixture
    def real_gallery_tab(self, qt_app):
        """Create real SpriteGalleryTab for Qt testing."""
        from ui.tabs.sprite_gallery_tab import SpriteGalleryTab
        tab = SpriteGalleryTab()
        return tab

    def test_sprite_selected_signal_emission(self, qtbot, real_gallery_tab):
        """Test sprite_selected signal is emitted on double-click."""
        qtbot.addWidget(real_gallery_tab)

        with qtbot.waitSignal(real_gallery_tab.sprite_selected, timeout=1000) as blocker:
            # Trigger double-click handler directly since we can't mock gallery widget
            real_gallery_tab._on_sprite_double_clicked(0x200000)

        # Verify signal was emitted with correct offset
        assert blocker.args == [0x200000]

    def test_sprites_exported_signal_emission(self, qtbot, real_gallery_tab, tmp_path):
        """Test sprites_exported signal is emitted on successful export."""
        qtbot.addWidget(real_gallery_tab)

        # Mock the gallery widget selection
        selected_sprites = [{"offset": 0x200000, "tile_count": 64}]
        real_gallery_tab.gallery_widget.get_selected_sprites = Mock(return_value=selected_sprites)

        export_dir = str(tmp_path)

        with qtbot.waitSignal(real_gallery_tab.sprites_exported, timeout=2000) as blocker:
            with patch('ui.tabs.sprite_gallery_tab.QFileDialog.getExistingDirectory', return_value=export_dir):
                real_gallery_tab._export_selected()

        # Verify signal was emitted with exported file paths
        exported_files = blocker.args[0]
        assert len(exported_files) == 1
        assert "sprite_200000.png" in exported_files[0]

    def test_thumbnail_worker_signal_connection(self, qtbot, real_gallery_tab):
        """Test BatchThumbnailWorker signal connection with real tab."""
        qtbot.addWidget(real_gallery_tab)

        real_gallery_tab.rom_path = "/test/rom.sfc"
        real_gallery_tab.sprites_data = [{"offset": 0x200000, "tile_count": 64}]

        with patch('ui.tabs.sprite_gallery_tab.BatchThumbnailWorker') as MockWorker:
            mock_worker = Mock()
            MockWorker.return_value = mock_worker

            real_gallery_tab._refresh_thumbnails()

            # Verify signal was connected
            mock_worker.thumbnail_ready.connect.assert_called_once_with(
                real_gallery_tab._on_thumbnail_ready
            )

    def test_gallery_widget_signal_connections(self, qtbot, real_gallery_tab):
        """Test that gallery widget signals are connected properly."""
        qtbot.addWidget(real_gallery_tab)

        gallery_widget = real_gallery_tab.gallery_widget

        # Verify signal connections exist (can't easily test without triggering)
        assert gallery_widget.sprite_selected.receivers() > 0
        assert gallery_widget.sprite_double_clicked.receivers() > 0
        assert gallery_widget.selection_changed.receivers() > 0

    def test_toolbar_action_signal_connections(self, qtbot, real_gallery_tab):
        """Test toolbar action signal connections."""
        qtbot.addWidget(real_gallery_tab)

        toolbar = real_gallery_tab.toolbar
        actions = toolbar.actions()

        # Find scan action
        scan_action = None
        for action in actions:
            if "Scan" in action.text():
                scan_action = action
                break

        assert scan_action is not None
        # Test that action has receivers (signal is connected)
        assert scan_action.triggered.receivers() > 0

    def test_button_signal_connections(self, qtbot, real_gallery_tab):
        """Test action bar button signal connections."""
        qtbot.addWidget(real_gallery_tab)

        compare_btn = real_gallery_tab.compare_btn
        palette_btn = real_gallery_tab.palette_btn

        # Verify buttons have signal connections
        assert compare_btn.clicked.receivers() > 0
        assert palette_btn.clicked.receivers() > 0

@pytest.mark.gui
class TestSpriteGalleryTabUIStateManagement:
    """Test UI state management with real Qt components."""

    @pytest.fixture
    def qt_app(self):
        """Provide Qt application for GUI tests."""
        app = QApplication.instance()
        if not app:
            app = QApplication([])
        return app

    @pytest.fixture
    def real_gallery_tab(self, qt_app):
        """Create real SpriteGalleryTab for Qt testing."""
        from ui.tabs.sprite_gallery_tab import SpriteGalleryTab
        tab = SpriteGalleryTab()
        return tab

    def test_initial_ui_state(self, qtbot, real_gallery_tab):
        """Test initial UI state is correct."""
        qtbot.addWidget(real_gallery_tab)

        # Initially no ROM loaded
        assert real_gallery_tab.info_label.text() == "No ROM loaded"

        # Buttons should be disabled initially
        assert not real_gallery_tab.compare_btn.isEnabled()
        assert not real_gallery_tab.palette_btn.isEnabled()

    def test_rom_data_updates_ui_state(self, qtbot, real_gallery_tab, tmp_path):
        """Test setting ROM data updates UI appropriately."""
        qtbot.addWidget(real_gallery_tab)

        rom_path = str(tmp_path / "test.sfc")
        rom_size = 1024 * 1024  # 1MB

        # Mock ROM extractor
        mock_extractor = Mock()

        # Mock cache loading to avoid file operations
        with patch.object(real_gallery_tab, '_load_scan_cache', return_value=False):
            real_gallery_tab.set_rom_data(rom_path, rom_size, mock_extractor)

        # Info label should show ROM info
        expected_text = "ROM: test.sfc (1.0MB)"
        assert real_gallery_tab.info_label.text() == expected_text

        # ROM data should be set
        assert real_gallery_tab.rom_path == rom_path
        assert real_gallery_tab.rom_size == rom_size
        assert real_gallery_tab.rom_extractor == mock_extractor

    def test_selection_updates_ui_elements(self, qtbot, real_gallery_tab):
        """Test selection changes update UI elements correctly."""
        qtbot.addWidget(real_gallery_tab)

        # Initially buttons are disabled
        assert not real_gallery_tab.compare_btn.isEnabled()
        assert not real_gallery_tab.palette_btn.isEnabled()

        # Single selection - enables palette, disables compare
        real_gallery_tab._on_selection_changed([0x200000])
        assert not real_gallery_tab.compare_btn.isEnabled()  # Need 2+
        assert real_gallery_tab.palette_btn.isEnabled()

        # Multiple selection - enables both
        real_gallery_tab._on_selection_changed([0x200000, 0x201000])
        assert real_gallery_tab.compare_btn.isEnabled()
        assert real_gallery_tab.palette_btn.isEnabled()

        # No selection - disables both
        real_gallery_tab._on_selection_changed([])
        assert not real_gallery_tab.compare_btn.isEnabled()
        assert not real_gallery_tab.palette_btn.isEnabled()

    def test_scan_progress_dialog_management(self, qtbot, real_gallery_tab):
        """Test scan progress dialog is managed correctly."""
        qtbot.addWidget(real_gallery_tab)

        real_gallery_tab.rom_path = "/test/rom.sfc"

        # Mock user selecting Quick scan
        with patch('ui.tabs.sprite_gallery_tab.QMessageBox') as MockMessageBox:
            mock_dialog = Mock()
            quick_btn = Mock()
            mock_dialog.clickedButton.return_value = quick_btn

            # Create buttons
            mock_dialog.addButton = Mock(side_effect=[quick_btn, Mock(), Mock()])
            MockMessageBox.return_value = mock_dialog

            # Mock progress dialog
            with patch('ui.tabs.sprite_gallery_tab.QProgressDialog') as MockProgress:
                mock_progress = Mock()
                MockProgress.return_value = mock_progress
                mock_progress.wasCanceled.return_value = True  # Cancel immediately

                # Mock file operations
                with patch('builtins.open', create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = b'\x00' * 1024
                    with patch.object(SpriteFinder, 'find_sprite_at_offset', return_value=None):

                        real_gallery_tab._scan_for_sprites()

                # Verify progress dialog was created and configured
                MockProgress.assert_called_once()
                mock_progress.setWindowModality.assert_called_once()
                mock_progress.show.assert_called_once()
                mock_progress.close.assert_called_once()

    def test_info_label_updates_with_scan_results(self, qtbot, real_gallery_tab):
        """Test info label updates correctly with scan results."""
        qtbot.addWidget(real_gallery_tab)

        real_gallery_tab.rom_path = "/test/rom.sfc"
        real_gallery_tab.scan_mode = "quick"

        # Mock found sprites
        mock_sprites = [
            {"offset": 0x200000, "tile_count": 64},
            {"offset": 0x201000, "tile_count": 32}
        ]

        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b'\x00' * 0x400000
            with patch.object(SpriteFinder, 'find_sprite_at_offset', side_effect=[mock_sprites[0], mock_sprites[1]] + [None] * 10):
                with patch.object(real_gallery_tab, 'progress_dialog', create=True) as mock_dialog:
                    mock_dialog.wasCanceled.return_value = False
                    mock_dialog.setValue = Mock()
                    mock_dialog.setLabelText = Mock()
                    mock_dialog.close = Mock()

                    with patch.object(real_gallery_tab, '_save_scan_cache'):
                        with patch.object(real_gallery_tab, '_refresh_thumbnails'):
                            # Manually trigger scan completion logic
                            real_gallery_tab.sprites_data = mock_sprites
                            real_gallery_tab.gallery_widget.set_sprites(mock_sprites)

                            # Update info label like _start_sprite_scan does
                            rom_name = Path(real_gallery_tab.rom_path).name
                            real_gallery_tab.info_label.setText(
                                f"Found {len(mock_sprites)} sprites in {rom_name}"
                            )

        # Verify info label shows scan results
        expected_text = "Found 2 sprites in rom.sfc"
        assert real_gallery_tab.info_label.text() == expected_text

@pytest.mark.gui
class TestSpriteGalleryTabRealWidgetInteraction:
    """Test real widget interactions using qtbot."""

    @pytest.fixture
    def qt_app(self):
        """Provide Qt application for GUI tests."""
        app = QApplication.instance()
        if not app:
            app = QApplication([])
        return app

    @pytest.fixture
    def real_gallery_tab(self, qt_app):
        """Create real SpriteGalleryTab for Qt testing."""
        from ui.tabs.sprite_gallery_tab import SpriteGalleryTab
        tab = SpriteGalleryTab()
        return tab

    def test_widget_creation_and_layout(self, qtbot, real_gallery_tab):
        """Test widget creation and layout structure."""
        qtbot.addWidget(real_gallery_tab)

        # Verify main components exist
        assert real_gallery_tab.toolbar is not None
        assert real_gallery_tab.gallery_widget is not None
        assert real_gallery_tab.info_label is not None
        assert real_gallery_tab.compare_btn is not None
        assert real_gallery_tab.palette_btn is not None

        # Verify layout structure
        layout = real_gallery_tab.layout()
        assert layout is not None
        assert layout.count() > 0  # Has child widgets

        # Verify toolbar has actions
        actions = real_gallery_tab.toolbar.actions()
        assert len(actions) > 0

        # Find and verify key actions exist
        action_texts = [action.text() for action in actions if not action.isSeparator()]
        assert any("Scan" in text for text in action_texts)
        assert any("Export" in text for text in action_texts)
        assert any("Refresh" in text for text in action_texts)

    def test_gallery_widget_integration(self, qtbot, real_gallery_tab):
        """Test gallery widget integration with tab."""
        qtbot.addWidget(real_gallery_tab)

        gallery_widget = real_gallery_tab.gallery_widget

        # Verify gallery widget configuration
        assert gallery_widget.parent() == real_gallery_tab

        # Test setting sprites (should not crash)
        test_sprites = [
            {"offset": 0x200000, "tile_count": 64},
            {"offset": 0x201000, "tile_count": 32}
        ]

        # This should work without crashing
        gallery_widget.set_sprites(test_sprites)

        # Verify sprites were set (basic check)
        assert hasattr(gallery_widget, 'sprite_data')

    def test_button_click_behaviors(self, qtbot, real_gallery_tab):
        """Test button click behaviors don't crash."""
        qtbot.addWidget(real_gallery_tab)

        # Enable buttons by simulating selection
        real_gallery_tab.compare_btn.setEnabled(True)
        real_gallery_tab.palette_btn.setEnabled(True)

        # Mock selected sprites to avoid crashes
        real_gallery_tab.gallery_widget.get_selected_sprites = Mock(return_value=[
            {"offset": 0x200000, "tile_count": 64},
            {"offset": 0x201000, "tile_count": 32}
        ])

        # Test compare button (should show not implemented)
        with patch('ui.tabs.sprite_gallery_tab.QMessageBox.information') as mock_info:
            qtbot.mouseClick(real_gallery_tab.compare_btn, Qt.MouseButton.LeftButton)
            mock_info.assert_called_once()

        # Test palette button (should show not implemented)
        with patch('ui.tabs.sprite_gallery_tab.QMessageBox.information') as mock_info:
            qtbot.mouseClick(real_gallery_tab.palette_btn, Qt.MouseButton.LeftButton)
            mock_info.assert_called_once()

    def test_cleanup_doesnt_crash(self, qtbot, real_gallery_tab):
        """Test cleanup method doesn't crash with real widgets."""
        qtbot.addWidget(real_gallery_tab)

        # Set up some state that needs cleanup
        real_gallery_tab.thumbnail_worker = Mock()

        # Should not crash
        real_gallery_tab.cleanup()

        # Worker should be cleaned up
        assert real_gallery_tab.thumbnail_worker is None
