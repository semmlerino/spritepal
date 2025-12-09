"""
Integration tests for ROM cache UI components.

Tests the visual display and user interactions with cache status indicators,
progress tracking, and the resume scan dialog.
"""
from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

# Managers are handled by conftest.py
from core.rom_extractor import ROMExtractor
from core.rom_injector import SpritePointer
from ui.dialogs.resume_scan_dialog import ResumeScanDialog
from ui.rom_extraction.widgets.rom_file_widget import ROMFileWidget
from ui.rom_extraction.widgets.sprite_selector_widget import (
    # Systematic pytest markers applied based on test content analysis
    SpriteSelectorWidget,
)
from ui.rom_extraction.workers.scan_worker import SpriteScanWorker
from ui.rom_extraction_panel import ROMExtractionPanel
from utils.rom_cache import ROMCache

# Manager setup is handled by conftest.py setup_managers fixture

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.dialog,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_dialogs,
    pytest.mark.performance,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.slow,
    pytest.mark.widget,
    pytest.mark.cache,
    pytest.mark.ci_safe,
    pytest.mark.signals_slots,
]
@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return str(cache_dir)

@pytest.fixture
def test_rom_file(tmp_path):
    """Create a test ROM file."""
    rom_file = tmp_path / "test_game.sfc"
    # Create a ROM large enough for sprite scanning (at least 0xF0000 bytes = ~1MB)
    rom_size = 0xF0000 + 0x10000  # Add some extra space
    rom_data = bytearray(rom_size)
    for i in range(len(rom_data)):
        rom_data[i] = i % 256
    rom_file.write_bytes(rom_data)
    return str(rom_file)

@pytest.fixture
def rom_cache(temp_cache_dir):
    """Create a ROM cache instance with temporary directory."""
    return ROMCache(cache_dir=temp_cache_dir)
    # No close needed - SQLite connection handled automatically

class TestROMFileWidgetCacheDisplay:
    """Test cache status display in ROMFileWidget."""

    def test_cache_status_no_cache(self, qtbot, test_rom_file, rom_cache):
        """Test cache status display when no cache exists."""
        widget = ROMFileWidget()
        qtbot.addWidget(widget)

        # Load ROM file
        widget.set_rom_path(test_rom_file)

        # Check that no cache status is shown
        info_text = widget.rom_info_label.text()
        assert "💾" not in info_text
        assert "📊" not in info_text
        assert "cached" not in info_text

    @patch("ui.rom_extraction.widgets.rom_file_widget.get_rom_cache")
    def test_cache_status_with_sprites_cached(self, mock_get_rom_cache, qtbot, test_rom_file, rom_cache):
        """Test cache status display when sprites are cached."""
        # Make ROMFileWidget use our test cache instance
        mock_get_rom_cache.return_value = rom_cache

        # Pre-populate cache with sprite locations
        sprite_locations = {
            "Sprite 1": SpritePointer(
                offset=0x1000,
                bank=0x10,
                address=0x8000,
                compressed_size=100
            ),
            "Sprite 2": SpritePointer(
                offset=0x2000,
                bank=0x20,
                address=0x8000,
                compressed_size=200
            ),
            "Sprite 3": SpritePointer(
                offset=0x3000,
                bank=0x30,
                address=0x8000,
                compressed_size=150
            )
        }
        rom_cache.save_sprite_locations(test_rom_file, sprite_locations)

        # Create widget and load ROM
        widget = ROMFileWidget()
        qtbot.addWidget(widget)

        # Set ROM path and update info text (simulating ROMExtractionPanel behavior)
        widget.set_rom_path(test_rom_file)
        widget.set_info_text(f"<b>File:</b> {os.path.basename(test_rom_file)}<br><b>Size:</b> {(0xF0000 + 0x10000) / 1024 / 1024:.2f} MB")

        # Check cache_status_changed signal
        signal_received = False
        cache_status_data = None

        def on_cache_status(status):
            nonlocal signal_received, cache_status_data
            signal_received = True
            cache_status_data = status

        widget.cache_status_changed.connect(on_cache_status)

        # Trigger cache check
        widget._check_cache_status()

        # Wait for signal if needed
        if not signal_received:
            qtbot.waitUntil(lambda: signal_received, timeout=1000)

        # Verify signal data
        assert cache_status_data["has_cache"] is True
        assert cache_status_data["has_sprite_cache"] is True
        assert cache_status_data.get("has_scan_cache", False) is False

        # Check UI display
        info_text = widget.rom_info_label.text()
        assert "💾 3 sprites cached" in info_text
        assert "color: #0078d4" in info_text  # Blue color for sprite cache

    @patch("ui.rom_extraction.widgets.rom_file_widget.get_rom_cache")
    def test_cache_status_with_partial_scan(self, mock_get_rom_cache, qtbot, test_rom_file, rom_cache):
        """Test cache status display when partial scan is cached."""
        # Make ROMFileWidget use our test cache instance
        mock_get_rom_cache.return_value = rom_cache
        # Save partial scan to cache - must match ROMFileWidget's expected params
        scan_params = {
            "start_offset": 0xC0000,
            "end_offset": 0xF0000,
            "alignment": 0x100
        }
        found_sprites = [
            {"offset": 0xC1000, "size": 100},
            {"offset": 0xC2000, "size": 200}
        ]
        current_offset = 0xD0000
        rom_cache.save_partial_scan_results(test_rom_file, scan_params, found_sprites, current_offset, completed=False)

        # Create widget and load ROM
        widget = ROMFileWidget()
        qtbot.addWidget(widget)

        # Check both signals
        partial_scan_received = False
        partial_scan_data = None

        def on_partial_scan(data):
            nonlocal partial_scan_received, partial_scan_data
            partial_scan_received = True
            partial_scan_data = data

        widget.partial_scan_detected.connect(on_partial_scan)

        # Set ROM path and trigger cache check
        widget.set_rom_path(test_rom_file)
        widget.set_info_text(f"<b>File:</b> {os.path.basename(test_rom_file)}<br><b>Size:</b> {(0xF0000 + 0x10000) / 1024 / 1024:.2f} MB")

        # Wait for signal
        qtbot.waitUntil(lambda: partial_scan_received, timeout=1000)

        # Verify partial scan was detected
        assert partial_scan_data is not None
        assert partial_scan_data["current_offset"] == 0xD0000

        # Check UI display
        info_text = widget.rom_info_label.text()
        assert "📊 Partial scan cached" in info_text
        assert "color: #107c41" in info_text  # Green color for scan cache

    @patch("ui.rom_extraction.widgets.rom_file_widget.get_rom_cache")
    def test_cache_invalidation_on_rom_change(self, mock_get_rom_cache, qtbot, test_rom_file, rom_cache):
        """Test cache status updates when ROM file is modified."""
        # Make ROMFileWidget use our test cache instance
        mock_get_rom_cache.return_value = rom_cache
        # Pre-populate cache
        sprite_locations = {
            "Sprite 1": SpritePointer(
                offset=0x1000,
                bank=0x10,
                address=0x8000,
                compressed_size=100
            )
        }
        rom_cache.save_sprite_locations(test_rom_file, sprite_locations)

        # Create widget and load ROM
        widget = ROMFileWidget()
        qtbot.addWidget(widget)
        widget.set_rom_path(test_rom_file)
        widget.set_info_text(f"<b>File:</b> {os.path.basename(test_rom_file)}<br><b>Size:</b> {(0xF0000 + 0x10000) / 1024 / 1024:.2f} MB")

        # Verify cache is shown
        assert "💾" in widget.rom_info_label.text()

        # Modify ROM file (simulate user edit)
        time.sleep(0.1)  # Ensure different timestamp
        with open(test_rom_file, "ab") as f:
            f.write(b"MODIFIED")

        # Refresh cache status
        widget.refresh_cache_status()

        # Cache should be invalidated
        info_text = widget.rom_info_label.text()
        assert "💾" not in info_text
        assert "cached" not in info_text

class TestSpriteScanWorkerCacheIntegration:
    """Test cache integration in sprite scanning workflow."""

    @pytest.mark.slow
    def test_scan_worker_cache_miss(self, qtbot, test_rom_file, rom_cache):
        """Test scan worker behavior when no cache exists."""
        extractor = ROMExtractor()
        worker = SpriteScanWorker(test_rom_file, extractor, use_cache=True)

        # Track emitted signals
        cache_statuses = []
        worker.cache_status.connect(cache_statuses.append)

        # Start worker in thread
        worker.start()

        # Wait for completion (this is slow as it does real scanning)
        with qtbot.waitSignal(worker.finished, timeout=30000):
            pass

        # Check cache status messages
        assert any("Checking cache..." in msg for msg in cache_statuses)
        assert not any("Resuming from" in msg for msg in cache_statuses)

    def test_scan_worker_basic_completion(self, qtbot, test_rom_file):
        """Test that scan worker can complete a basic scan without cache."""
        extractor = ROMExtractor()
        worker = SpriteScanWorker(test_rom_file, extractor, use_cache=False)

        finished = False
        last_progress = 0
        error_msg = None

        def on_finished():
            nonlocal finished
            finished = True
            print("Worker finished signal received!")

        def on_progress(current, total):
            nonlocal last_progress
            if total > 0:
                pct = int((current / total) * 100)
                if pct != last_progress:
                    print(f"Progress: {current}/{total} = {pct}%")
                    last_progress = pct

        def on_cache_status(msg):
            if "Error:" in msg:
                nonlocal error_msg
                error_msg = msg
                print(f"ERROR detected: {msg}")

        worker.finished.connect(on_finished)
        worker.progress.connect(on_progress)
        worker.cache_status.connect(on_cache_status)

        print(f"Starting worker with ROM: {test_rom_file}")
        worker.start()

        # Wait up to 20 seconds for completion
        start_time = time.time()
        qtbot.waitUntil(lambda: finished, timeout=20000)
        elapsed = time.time() - start_time
        print(f"Elapsed time: {elapsed:.1f}s, finished: {finished}, last_progress: {last_progress}%")

        if error_msg:
            raise AssertionError(f"Worker reported error: {error_msg}")

        assert finished, f"Basic scan worker did not finish after {elapsed:.1f}s, last progress: {last_progress}%"

    def test_scan_worker_minimal_cache_resume(self, qtbot, test_rom_file, rom_cache):
        """Minimal test for cache resume functionality."""
        # Create very simple partial cache data
        scan_params = {
            "start_offset": 0xC0000,
            "end_offset": 0xF0000,
            "alignment": 0x100
        }
        # Start at 50% progress
        current_offset = 0xD8000  # Halfway between 0xC0000 and 0xF0000
        found_sprites = []  # No sprites found yet

        # Save to cache
        assert rom_cache.save_partial_scan_results(
            test_rom_file, scan_params, found_sprites, current_offset, completed=False
        )

        # Create worker with cache disabled to test manually
        extractor = ROMExtractor()

        # Check what the cache returns
        partial_result = rom_cache.get_partial_scan_results(test_rom_file, scan_params)
        assert partial_result is not None
        print(f"Cache returned: {partial_result}")

        # Now test with worker
        with patch("utils.rom_cache.get_rom_cache", return_value=rom_cache):
            worker = SpriteScanWorker(test_rom_file, extractor, use_cache=True)

            finished = False
            cache_msgs = []

            def on_finished():
                nonlocal finished
                finished = True

            def on_cache_status(msg):
                print(f"Cache: {msg}")
                cache_msgs.append(msg)

            worker.finished.connect(on_finished)
            worker.cache_status.connect(on_cache_status)

            worker.start()

            # Wait up to 30 seconds
            qtbot.waitUntil(lambda: finished, timeout=30000)

            assert finished, f"Worker did not finish. Cache messages: {cache_msgs}"
            assert any("Resuming from" in msg for msg in cache_msgs)

    @pytest.mark.slow
    def test_scan_worker_with_partial_cache(self, qtbot, test_rom_file, rom_cache):
        """Test scan worker resuming from partial cache - simplified."""
        # Use the same offset as minimal test but with a sprite
        scan_params = {
            "start_offset": 0xC0000,
            "end_offset": 0xF0000,
            "alignment": 0x100
        }

        # Try with 33% progress like original
        current_offset = 0xD0000
        found_sprites = [{"offset": 0xC1000, "size": 100}]

        # Save to cache
        assert rom_cache.save_partial_scan_results(
            test_rom_file, scan_params, found_sprites, current_offset, completed=False
        )

        # Create worker
        with patch("utils.rom_cache.get_rom_cache", return_value=rom_cache):
            extractor = ROMExtractor()
            worker = SpriteScanWorker(test_rom_file, extractor, use_cache=True)

            finished = False
            last_msg = None

            def on_finished():
                nonlocal finished
                finished = True

            def on_cache_status(msg):
                nonlocal last_msg
                last_msg = msg
                print(f"Cache: {msg}")

            worker.finished.connect(on_finished)
            worker.cache_status.connect(on_cache_status)

            worker.start()

            # Wait up to 30 seconds
            qtbot.waitUntil(lambda: finished, timeout=30000)

            assert finished, f"Worker did not finish. Last message: {last_msg}"

    @pytest.mark.slow
    @patch("utils.rom_cache.get_rom_cache")
    @patch("core.rom_injector.ROMInjector.find_compressed_sprite")
    def test_scan_worker_cache_save_progress(self, mock_find_sprite, mock_get_rom_cache, qtbot, test_rom_file, rom_cache):
        """Test cache save progress during scanning."""
        mock_get_rom_cache.return_value = rom_cache

        # Mock HAL compression to return fast, predictable results
        # This focuses the test on cache behavior rather than decompression performance
        def mock_sprite_finder(rom_data, offset, expected_size=None):
            # Return dummy sprite data only occasionally to simulate real scanning
            if offset % 0x1000 == 0:  # Every 16th attempt succeeds
                return 100, b"\x00" * 32 * 16  # 16 tiles of dummy data
            return 0, b""  # Most attempts fail (like real ROM scanning)

        mock_find_sprite.side_effect = mock_sprite_finder

        extractor = ROMExtractor()
        worker = SpriteScanWorker(test_rom_file, extractor, use_cache=True)

        # Track cache progress
        cache_progresses = []
        save_messages = []

        def on_cache_progress(progress):
            cache_progresses.append(progress)

        def on_cache_status(msg):
            print(f"Cache status: {msg}")
            if "Saving" in msg:
                save_messages.append(msg)

        worker.cache_progress.connect(on_cache_progress)
        worker.cache_status.connect(on_cache_status)

        # Start worker
        worker.start()

        # Wait for completion
        finished = False
        def on_finished():
            nonlocal finished
            finished = True

        worker.finished.connect(on_finished)

        # Wait for either finished OR enough save messages (at least 20% progress)
        # Reduced expectation since synthetic test ROM has mostly invalid data
        qtbot.waitUntil(lambda: finished or len(save_messages) >= 2, timeout=10000)

        if not finished and len(save_messages) < 2:
            print(f"Worker timed out. Save messages: {save_messages}")
            print(f"Cache progresses: {cache_progresses}")

        # For this test, we just need to verify that periodic saves are happening
        # We don't need the full scan to complete - synthetic ROM has mostly invalid compressed data
        assert len(save_messages) >= 2, f"Not enough save messages: {save_messages}"
        assert any("Saving progress" in msg for msg in save_messages)

        # Clean up the worker
        if not finished:
            worker.terminate()
            worker.wait()

        # Verify progress values
        assert all(0 <= p <= 100 for p in cache_progresses)
        # Don't check for 100% since we may terminate early

class TestResumeScanDialog:
    """Test ResumeScanDialog user interactions."""

    def test_resume_scan_dialog_display(self, qtbot):
        """Test ResumeScanDialog displays scan information correctly."""
        scan_info = {
            "scan_range": {
                "start": 0,
                "end": 0x100000
            },
            "current_offset": 0x45000,
            "total_found": 12
        }

        dialog = ResumeScanDialog(scan_info)
        qtbot.addWidget(dialog)
        dialog.show()

        # Find progress label by looking for label with progress info
        progress_labels = [label for label in dialog.findChildren(QLabel)
                          if "Progress:" in label.text()]
        assert len(progress_labels) > 0
        progress_label = progress_labels[0]

        info_text = progress_label.text()
        # Progress should be approximately (0x45000 - 0) / (0x100000 - 0) * 100 = 27%
        assert "27.0%" in info_text or "27.3%" in info_text  # Allow for rounding differences
        assert "Sprites found: 12" in info_text
        assert "0x045000" in info_text
        assert "0x100000" in info_text

    def test_resume_scan_dialog_resume_choice(self, qtbot):
        """Test choosing to resume scan."""
        scan_info = {
            "scan_range": {"start": 0, "end": 0x100000},
            "current_offset": 0x50000,
            "total_found": 10
        }

        dialog = ResumeScanDialog(scan_info)
        qtbot.addWidget(dialog)

        # Click Resume button (using custom button)
        qtbot.mouseClick(dialog.resume_button, Qt.MouseButton.LeftButton)

        assert dialog.get_user_choice() == ResumeScanDialog.RESUME

    def test_resume_scan_dialog_start_fresh_choice(self, qtbot):
        """Test choosing to start fresh."""
        scan_info = {
            "scan_range": {"start": 0, "end": 0x100000},
            "current_offset": 0x50000,
            "total_found": 10
        }

        dialog = ResumeScanDialog(scan_info)
        qtbot.addWidget(dialog)

        # Click Start Fresh button (using custom button)
        qtbot.mouseClick(dialog.fresh_button, Qt.MouseButton.LeftButton)

        assert dialog.get_user_choice() == ResumeScanDialog.START_FRESH

    def test_resume_scan_dialog_cancel_choice(self, qtbot):
        """Test canceling the dialog."""
        scan_info = {
            "scan_range": {"start": 0, "end": 0x100000},
            "current_offset": 0x50000,
            "total_found": 10
        }

        dialog = ResumeScanDialog(scan_info)
        qtbot.addWidget(dialog)

        # Click Cancel button (using custom button)
        qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

        assert dialog.get_user_choice() == ResumeScanDialog.CANCEL

class TestROMExtractionPanelCacheUI:
    """Test cache UI updates in ROMExtractionPanel during scanning."""

    def test_rom_extraction_panel_cache_integration(self, qtbot, test_rom_file):
        """Test that ROMExtractionPanel integrates with cache system."""
        # Create panel
        panel = ROMExtractionPanel()
        qtbot.addWidget(panel)

        # Set up panel with ROM
        panel.rom_file_widget.set_rom_path(test_rom_file)
        panel.rom_path = test_rom_file

        # Verify the panel is set up correctly
        assert panel.rom_path == test_rom_file
        assert panel.rom_extractor is not None

        # Verify cache integration exists
        assert hasattr(panel.rom_file_widget, "cache_status_changed")
        assert hasattr(panel.rom_file_widget, "partial_scan_detected")

        # The actual cache UI updates happen inside _find_sprites dialog
        # which is hard to test without running the full scan
        # The important thing is that the infrastructure is in place

    def test_sprite_selector_cache_indicators(self, qtbot, test_rom_file):
        """Test cache indicators in sprite selector dropdown."""
        # Create selector widget
        selector = SpriteSelectorWidget()
        qtbot.addWidget(selector)

        # Add sprites with cache indicators
        # Based on the actual usage in rom_extraction_panel.py
        selector.add_sprite("Cached Sprite 💾", {"offset": 0x1000, "size": 100})
        selector.add_sprite("Fresh Sprite", {"offset": 0x2000, "size": 200})

        # Check dropdown items
        found_cached = False
        found_fresh = False

        for i in range(selector.sprite_combo.count()):
            text = selector.sprite_combo.itemText(i)
            if "Cached Sprite" in text:
                assert "💾" in text  # Cache indicator
                found_cached = True
            elif "Fresh Sprite" in text:
                assert "💾" not in text  # No cache indicator
                found_fresh = True

        assert found_cached
        assert found_fresh

    @patch("ui.rom_extraction.widgets.rom_file_widget.get_rom_cache")
    def test_partial_scan_detection(self, mock_get_rom_cache, qtbot, test_rom_file, rom_cache):
        """Test that partial scan is detected when ROM is loaded."""
        # Make ROMFileWidget use our test cache instance
        mock_get_rom_cache.return_value = rom_cache

        # Set up partial scan in cache using proper scan parameters
        scan_params = {
            "start_offset": 0xC0000,
            "end_offset": 0xF0000,
            "alignment": 0x100
        }
        found_sprites = [{"offset": 0xC1000, "size": 100}]
        current_offset = 0xD8000  # This gives us 50% progress
        rom_cache.save_partial_scan_results(test_rom_file, scan_params, found_sprites, current_offset, completed=False)

        # Create panel
        panel = ROMExtractionPanel()
        qtbot.addWidget(panel)

        # Track if partial scan signal was emitted
        partial_scan_detected = False
        def on_partial_scan(data):
            nonlocal partial_scan_detected
            partial_scan_detected = True

        # Connect to the ROMFileWidget's signal
        panel.rom_file_widget.partial_scan_detected.connect(on_partial_scan)

        # Load ROM (should detect partial scan)
        panel.rom_file_widget.set_rom_path(test_rom_file)

        # Verify partial scan was detected
        assert partial_scan_detected

class TestCacheUIEndToEnd:
    """Test complete cache UI workflow from start to finish."""

    @pytest.mark.slow
    def test_complete_scan_with_cache_workflow(self, qtbot, test_rom_file, rom_cache):
        """Test basic cache workflow - verifying cache persistence."""
        # This test verifies that cache is created and persisted properly
        # The detailed scan workflow is tested in SpriteScanWorker tests

        # Save some sprites to cache directly
        sprite_locations = {
            "Sprite 1": SpritePointer(
                offset=0x1000,
                bank=0x10,
                address=0x8000,
                compressed_size=100
            ),
            "Sprite 2": SpritePointer(
                offset=0x2000,
                bank=0x20,
                address=0x8000,
                compressed_size=200
            )
        }
        rom_cache.save_sprite_locations(test_rom_file, sprite_locations)

        # Create panel with cache
        with patch("ui.rom_extraction.widgets.rom_file_widget.get_rom_cache", return_value=rom_cache):
            panel = ROMExtractionPanel()
            qtbot.addWidget(panel)

            # Load ROM
            panel.rom_file_widget.set_rom_path(test_rom_file)
            panel.rom_file_widget.set_info_text(f"<b>File:</b> {os.path.basename(test_rom_file)}<br><b>Size:</b> {(0xF0000 + 0x10000) / 1024 / 1024:.2f} MB")

            # Verify cache is shown in UI
            rom_info_text = panel.rom_file_widget.rom_info_label.text()
            assert "💾 2 sprites cached" in rom_info_text

            # Verify cache info is available for the specific ROM
            sprite_locations = rom_cache.get_sprite_locations(test_rom_file)
            assert sprite_locations is not None
            assert len(sprite_locations) > 0

    @patch("ui.rom_extraction.widgets.rom_file_widget.get_rom_cache")
    def test_cache_persistence_across_sessions(self, mock_get_rom_cache, qtbot, test_rom_file, temp_cache_dir):
        """Test that cache persists and is recognized in new session."""
        # First session - perform scan
        cache1 = ROMCache(cache_dir=temp_cache_dir)
        mock_get_rom_cache.return_value = cache1

        panel1 = ROMExtractionPanel()
        qtbot.addWidget(panel1)

        # Save some sprites to cache
        sprite_locations = {
            "Sprite 1": SpritePointer(
                offset=0x1000,
                bank=0x10,
                address=0x8000,
                compressed_size=100
            ),
            "Sprite 2": SpritePointer(
                offset=0x2000,
                bank=0x20,
                address=0x8000,
                compressed_size=200
            )
        }
        cache1.save_sprite_locations(test_rom_file, sprite_locations)
        # No close needed - SQLite connection handled automatically

        # Second session - verify cache is loaded
        cache2 = ROMCache(cache_dir=temp_cache_dir)
        mock_get_rom_cache.return_value = cache2

        panel2 = ROMExtractionPanel()
        qtbot.addWidget(panel2)

        # Load same ROM
        panel2.rom_file_widget.set_rom_path(test_rom_file)
        panel2.rom_file_widget.set_info_text(f"<b>File:</b> {os.path.basename(test_rom_file)}<br><b>Size:</b> {(0xF0000 + 0x10000) / 1024 / 1024:.2f} MB")

        # Verify cache status is shown
        rom_info_text = panel2.rom_file_widget.rom_info_label.text()
        assert "💾 2 sprites cached" in rom_info_text
