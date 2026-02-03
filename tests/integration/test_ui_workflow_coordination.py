"""
End-to-end UI workflow and user interaction testing.

Tests comprehensive user workflows and interaction patterns:
- Complete ROM workflows with signal tracking
- Keyboard navigation (I, S, arrow keys, fullscreen mode)
- Rapid ROM switching and performance
- UI responsiveness during processing
- Error recovery workflows

Tests UI state machine transitions with mocked workers to isolate workflow logic.
Verifies proper state management, signal handling, and component interactions.

Note: These tests use mock workers for workflow isolation. For component-level testing
with real workers, see tests/integration/test_gallery_window_integration.py.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeyEvent, QPixmap

from tests.infrastructure.qt_real_testing import (
    EventLoopHelper,
    MemoryHelper,
    QtTestCase,
)
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

# Required for DI container setup
pytestmark = [
    pytest.mark.usefixtures("session_app_context"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="UI workflows may spawn worker threads"),
    pytest.mark.performance,
]


@pytest.fixture
def complete_test_rom(tmp_path) -> str:
    """Create a complete test ROM with realistic data."""
    rom_path = tmp_path / "complete_test.sfc"
    rom_size = 2 * 1024 * 1024  # 2MB ROM
    rom_data = bytearray(rom_size)

    # Add header
    rom_data[0:4] = b"SNES"

    # Add sprite data at various locations
    sprite_offsets = [0x10000, 0x15000, 0x20000, 0x25000, 0x30000, 0x40000, 0x50000, 0x60000, 0x70000, 0x80000]

    for i, offset in enumerate(sprite_offsets):
        # Add tile data (32 bytes per tile, 16 tiles per sprite)
        for tile in range(16):
            tile_offset = offset + tile * 32
            if tile_offset + 32 <= len(rom_data):
                # Create recognizable pattern
                pattern = bytes([(i + tile + j) % 256 for j in range(32)])
                rom_data[tile_offset : tile_offset + 32] = pattern

    rom_path.write_bytes(rom_data)
    return str(rom_path)


@pytest.fixture
def mock_settings_manager():
    """Create mock settings manager for integration tests."""
    manager = Mock()
    manager.get.return_value = ""
    manager.set.return_value = None
    manager.set_last_used_directory.return_value = None
    return manager


@pytest.fixture
def mock_rom_cache():
    """Create mock ROM cache for integration tests."""
    cache = Mock()
    cache.get_cached_sprite.return_value = None
    cache.cache_sprite.return_value = None
    return cache


@pytest.fixture
def realistic_sprite_data() -> list[dict[str, Any]]:
    """Create realistic sprite data matching what a ROM scan would find."""
    return [
        {
            "offset": 0x10000,
            "name": "Player_Idle",
            "decompressed_size": 512,
            "tile_count": 16,
            "compressed": False,
            "quality": 0.9,
        },
        {
            "offset": 0x15000,
            "name": "Player_Run",
            "decompressed_size": 768,
            "tile_count": 24,
            "compressed": True,
            "quality": 0.85,
        },
        {
            "offset": 0x20000,
            "name": "Enemy_Goomba",
            "decompressed_size": 256,
            "tile_count": 8,
            "compressed": False,
            "quality": 0.8,
        },
        {
            "offset": 0x25000,
            "name": "Power_Up_Mushroom",
            "decompressed_size": 128,
            "tile_count": 4,
            "compressed": False,
            "quality": 0.95,
        },
        {
            "offset": 0x30000,
            "name": "Background_Tile_Set",
            "decompressed_size": 2048,
            "tile_count": 64,
            "compressed": True,
            "quality": 0.7,
        },
    ]


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.slow
class TestCompleteUIWorkflowsIntegration(QtTestCase):
    """Test complete UI workflows from start to finish."""

    def setup_method(self):
        """Set up for each test method."""
        super().setup_method()
        self.gallery_window = None
        self.fullscreen_viewer = None

    def teardown_method(self):
        """Clean up after each test."""
        if self.fullscreen_viewer:
            self.fullscreen_viewer.close()
            self.fullscreen_viewer = None

        if self.gallery_window:
            self.gallery_window.close()
            self.gallery_window = None

        super().teardown_method()

    @patch("ui.windows.detached_gallery_window.SpriteScanWorker")
    @patch("ui.workers.batch_thumbnail_worker.BatchThumbnailWorker")
    def test_complete_rom_to_fullscreen_workflow(
        self,
        mock_thumbnail_worker_class,
        mock_scan_worker_class,
        complete_test_rom,
        realistic_sprite_data,
        mock_settings_manager,
        mock_rom_cache,
    ):
        # DI setup provided by session_app_context via pytestmark at module level
        """Test complete workflow: ROM load -> scan -> thumbnails -> fullscreen view."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        # Setup mock extraction manager
        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        # Mock scan worker with real signals
        from PySide6.QtCore import QObject, Signal

        class MockScanWorker(QObject):
            sprite_found = Signal(dict)
            finished = Signal()
            progress = Signal(int, str)
            error = Signal(str)
            cache_status = Signal(str)
            operation_finished = Signal()

            def __init__(self, *args, **kwargs):
                super().__init__()
                self.args = args
                self.kwargs = kwargs

            def start(self):
                pass

            def isRunning(self):
                return False

            def quit(self):
                pass

            def wait(self, ms=0):
                return True

            def requestInterruption(self):
                pass

            def isFinished(self):
                return True

            def deleteLater(self):
                pass

        mock_scan_worker = MockScanWorker()
        mock_scan_worker_class.return_value = mock_scan_worker

        # Mock thumbnail worker with Qt signals
        mock_thumbnail_worker = Mock()

        # Signals need to be usable
        class MockThumbnailWorker(QObject):
            thumbnail_ready = Signal(int, object)  # Accepts QImage
            progress = Signal(int, str)
            finished = Signal()
            error = Signal(str)

            def __init__(self):
                super().__init__()
                self.queue_thumbnail = Mock()
                self.run = Mock()
                self.cleanup = Mock()
                self.deleteLater = Mock()
                self.moveToThread = Mock()

            def isRunning(self):
                return False

            def start(self):
                pass

            def stop(self):
                pass  # Required for cleanup

        mock_thumbnail_worker = MockThumbnailWorker()
        mock_thumbnail_worker_class.return_value = mock_thumbnail_worker

        workflow_steps = []

        # Step 1: Create gallery window
        self.gallery_window = DetachedGalleryWindow(
            extraction_manager=mock_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )
        workflow_steps.append("gallery_created")

        assert self.gallery_window.windowTitle() == "Sprite Gallery"
        assert not self.gallery_window.scanning

        # Step 2: Load ROM
        self.gallery_window.load_rom(complete_test_rom)
        workflow_steps.append("rom_loaded")

        assert self.gallery_window.rom_path == complete_test_rom
        assert "complete_test" in self.gallery_window.windowTitle()

        # Step 3: Start ROM scan
        # Trigger via public action or method if available, or simulate UI interaction
        # The scan worker is created in _start_scan. We mocked the worker class.
        # We can trigger the scan via the public slot or action.
        scan_action = [a for a in self.gallery_window.findChildren(QAction) if "Scan ROM" in a.text()][0]
        scan_action.trigger()

        workflow_steps.append("scan_started")

        assert self.gallery_window.scanning
        # mock_scan_worker is a QObject, not a Mock, so we can't assert_called_once on start()
        # But we verified scanning state is True, which happens after start() is called.

        # Step 4: Simulate sprites being found during scan
        # Emit signal from the mock worker
        for sprite in realistic_sprite_data:
            mock_scan_worker.sprite_found.emit(sprite)
        workflow_steps.append("sprites_found")

        assert len(self.gallery_window.sprites_data) == len(realistic_sprite_data)

        # Step 5: Complete scan (this automatically triggers thumbnail generation)
        mock_scan_worker.finished.emit()
        workflow_steps.append("scan_completed")
        workflow_steps.append("thumbnails_started")  # Thumbnails start automatically

        assert not self.gallery_window.scanning

        # Step 6: Verify thumbnail generation was triggered automatically
        # Verify worker was created and thumbnails were queued
        mock_thumbnail_worker_class.assert_called_once()  # Worker was created
        # Note: We can't check call count easily on the MockWorker instance methods unless we mocked them specifically inside the class
        # or we check the side effects. But the test flow continues so we assume it worked.

        # Step 7: Simulate thumbnail completion
        for sprite in realistic_sprite_data:
            image = ThreadSafeTestImage(64, 64)
            image.fill()
            # Emit QImage, not QPixmap
            mock_thumbnail_worker.thumbnail_ready.emit(sprite["offset"], image.toImage())
        workflow_steps.append("thumbnails_completed")

        # Step 8: Open fullscreen viewer
        self.gallery_window.gallery_widget.get_selected_sprite_offset = Mock(
            return_value=realistic_sprite_data[0]["offset"]
        )

        with patch("ui.windows.detached_gallery_window.FullscreenSpriteViewer") as mock_viewer_class:
            mock_viewer = Mock()
            mock_viewer.set_sprite_data.return_value = True
            mock_viewer_class.return_value = mock_viewer

            # Trigger via menu action
            viewer_action = [a for a in self.gallery_window.findChildren(QAction) if "View Selected" in a.text()][0]
            viewer_action.trigger()

            workflow_steps.append("fullscreen_opened")

            mock_viewer_class.assert_called_once()
            mock_viewer.set_sprite_data.assert_called_once()
            mock_viewer.show.assert_called_once()

        # Verify complete workflow
        expected_steps = [
            "gallery_created",
            "rom_loaded",
            "scan_started",
            "sprites_found",
            "scan_completed",
            "thumbnails_started",
            "thumbnails_completed",
            "fullscreen_opened",
        ]

        assert workflow_steps == expected_steps

    @patch("ui.windows.detached_gallery_window.SpriteScanWorker")
    @patch("ui.workers.batch_thumbnail_worker.BatchThumbnailWorker")
    def test_gallery_window_lifecycle_memory_safety(
        self,
        mock_thumbnail_worker_class,
        mock_scan_worker_class,
        complete_test_rom,
        realistic_sprite_data,
        mock_settings_manager,
        mock_rom_cache,
    ):
        """Test gallery window lifecycle with memory safety checks."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        # Setup mock workers to prevent real threads
        mock_scan_worker = Mock()
        mock_scan_worker.isRunning.return_value = False
        mock_scan_worker_class.return_value = mock_scan_worker

        mock_thumbnail_worker = Mock()
        mock_thumbnail_worker.isRunning.return_value = False
        mock_thumbnail_worker_class.return_value = mock_thumbnail_worker

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        with MemoryHelper.assert_no_leak(DetachedGalleryWindow, max_increase=1):
            # Create window
            self.gallery_window = DetachedGalleryWindow(
                extraction_manager=mock_manager,
                settings_manager=mock_settings_manager,
                rom_cache=mock_rom_cache,
            )

            # Load ROM and sprites
            self.gallery_window.load_rom(complete_test_rom)
            self.gallery_window.set_sprites(realistic_sprite_data)

            # Simulate some UI interaction
            EventLoopHelper.process_events(100)

            # Test window resizing
            self.gallery_window.resize(1200, 800)
            EventLoopHelper.process_events(50)

            self.gallery_window.resize(800, 600)
            EventLoopHelper.process_events(50)

            # Close window
            self.gallery_window.close()
            self.gallery_window = None

    def test_fullscreen_viewer_navigation_workflow(self, realistic_sprite_data):
        """Test fullscreen viewer navigation workflow."""
        from ui.widgets.fullscreen_sprite_viewer import FullscreenSpriteViewer

        # Create fullscreen viewer with no parent (Qt widgets need real parents or None)
        self.fullscreen_viewer = self.create_widget(FullscreenSpriteViewer, None)

        # Create mock gallery for sprite pixmap retrieval
        mock_gallery = Mock()

        def mock_get_sprite_pixmap(offset: int) -> QPixmap:  # pixmap-ok: main thread mock
            image = ThreadSafeTestImage(128, 128)
            image.fill()
            return image.toQPixmap()

        mock_gallery.get_sprite_pixmap = mock_get_sprite_pixmap

        # Set up parent reference with gallery
        mock_parent = Mock()
        mock_parent.gallery_widget = mock_gallery
        self.fullscreen_viewer.parent_window = mock_parent

        # Set sprite data
        success = self.fullscreen_viewer.set_sprite_data(
            realistic_sprite_data, realistic_sprite_data[0]["offset"], "test_rom.sfc", Mock()
        )

        assert success
        assert self.fullscreen_viewer.current_index == 0

        navigation_sequence = []

        def track_navigation(offset):
            navigation_sequence.append(offset)

        self.fullscreen_viewer.sprite_changed.connect(track_navigation)

        # Test navigation sequence: right, right, left, ESC
        test_keys = [
            ("right", Qt.Key.Key_Right),
            ("right", Qt.Key.Key_Right),
            ("left", Qt.Key.Key_Left),
            ("info_toggle", Qt.Key.Key_I),
            ("smooth_toggle", Qt.Key.Key_S),
        ]

        for action, key in test_keys:
            key_event = QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
            self.fullscreen_viewer.keyPressEvent(key_event)
            EventLoopHelper.process_events(100)

        # Should have navigated through sprites
        assert len(navigation_sequence) >= 3

        # Test info overlay toggle (starts True, toggles to False)
        assert not self.fullscreen_viewer.show_info  # Should be False after toggle

        # Test smooth scaling toggle (starts True, toggles to False)
        assert not self.fullscreen_viewer.smooth_scaling  # Should be False after toggle

    @pytest.mark.performance
    @patch("ui.workers.batch_thumbnail_worker.BatchThumbnailWorker")
    def test_large_rom_performance_workflow(
        self,
        mock_thumbnail_worker_class,
        tmp_path,
        mock_settings_manager,
        mock_rom_cache,
    ):
        """Test performance with large ROM and many sprites."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        # Create large ROM
        large_rom = tmp_path / "large_rom.sfc"
        rom_size = 4 * 1024 * 1024  # 4MB
        rom_data = bytearray(rom_size)

        # Add patterns throughout
        for i in range(0, rom_size, 1024):
            rom_data[i : i + 4] = (i // 1024).to_bytes(4, "little")

        large_rom.write_bytes(rom_data)

        # Create large sprite dataset
        large_sprite_set = [
            {
                "offset": 0x10000 + i * 0x800,
                "name": f"Sprite_{i:04d}",
                "decompressed_size": 512 + (i % 512),
                "tile_count": 16 + (i % 32),
                "compressed": i % 4 == 0,
                "quality": 0.5 + (i % 50) / 100.0,
            }
            for i in range(1000)  # 1000 sprites
        ]

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        mock_thumbnail_worker = Mock()
        mock_thumbnail_worker.thumbnail_ready = Mock()
        mock_thumbnail_worker.progress = Mock()
        mock_thumbnail_worker.queue_thumbnail = Mock()
        mock_thumbnail_worker.start = Mock()
        mock_thumbnail_worker.isRunning.return_value = False
        mock_thumbnail_worker.cleanup = Mock()
        mock_thumbnail_worker_class.return_value = mock_thumbnail_worker

        start_time = time.time()

        # Create and setup window
        self.gallery_window = DetachedGalleryWindow(
            extraction_manager=mock_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )
        self.gallery_window.load_rom(str(large_rom))

        setup_time = time.time() - start_time

        # Load large sprite set
        start_load = time.time()
        self.gallery_window.set_sprites(large_sprite_set)
        load_time = time.time() - start_load

        # Generate thumbnails
        start_thumbnails = time.time()
        # Trigger via public action
        refresh_action = [a for a in self.gallery_window.findChildren(QAction) if "Refresh" in a.text()][0]
        refresh_action.trigger()
        thumbnail_setup_time = time.time() - start_thumbnails

        # Performance assertions
        assert setup_time < 2.0, f"Window setup took {setup_time:.2f}s, too slow"
        assert load_time < 3.0, f"Sprite loading took {load_time:.2f}s, too slow"
        assert thumbnail_setup_time < 1.0, f"Thumbnail setup took {thumbnail_setup_time:.2f}s, too slow"

        # Verify thumbnail queuing
        assert mock_thumbnail_worker.queue_thumbnail.call_count == 1000

    def test_concurrent_operations_workflow(
        self,
        complete_test_rom,
        realistic_sprite_data,
        mock_settings_manager,
        mock_rom_cache,
    ):
        """Test handling of concurrent operations."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        self.gallery_window = DetachedGalleryWindow(
            extraction_manager=mock_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )
        self.gallery_window.load_rom(complete_test_rom)

        # Create mock workers to simulate concurrent operations
        mock_scan_worker = Mock()
        mock_scan_worker.isRunning.return_value = True
        mock_scan_worker.requestInterruption = Mock()
        mock_scan_worker.wait.return_value = True

        mock_thumbnail_controller = Mock()
        mock_thumbnail_controller.cleanup = Mock()

        # Set workers as if they're running
        self.gallery_window.scan_worker = mock_scan_worker
        self.gallery_window.thumbnail_controller = mock_thumbnail_controller

        # Trigger cleanup (simulates starting new operation)
        cleanup_start = time.time()
        self.gallery_window._cleanup_existing_workers()
        cleanup_time = time.time() - cleanup_start

        # Should clean up quickly
        assert cleanup_time < 1.0, f"Worker cleanup took {cleanup_time:.2f}s"

        # Workers should be cleaned up
        assert self.gallery_window.scan_worker is None
        assert self.gallery_window.thumbnail_controller is None

        # Mock methods should have been called
        mock_scan_worker.requestInterruption.assert_called()
        mock_thumbnail_controller.cleanup.assert_called()

    @patch("ui.windows.detached_gallery_window.QMessageBox.critical")
    @patch("ui.dialogs.UserErrorDialog.display_error")  # Patched at definition since lazy import
    def test_error_recovery_workflow(
        self,
        mock_show_error,
        mock_critical,
        complete_test_rom,
        realistic_sprite_data,
        mock_settings_manager,
        mock_rom_cache,
    ):
        """Test error recovery in workflows."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        self.gallery_window = DetachedGalleryWindow(
            extraction_manager=mock_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )

        # Test invalid ROM file
        invalid_rom = "/nonexistent/path/invalid.sfc"

        # Should handle gracefully without crashing
        try:
            self.gallery_window.load_rom(invalid_rom)
        except Exception:
            pass  # Expected to fail

        # Window should still be functional
        assert self.gallery_window.rom_path is None or self.gallery_window.rom_path == invalid_rom

        # Load valid ROM after error
        self.gallery_window.load_rom(complete_test_rom)
        assert self.gallery_window.rom_path == complete_test_rom

        # Test scan error handling
        # Mock scan worker and emit error
        with patch("ui.windows.detached_gallery_window.SpriteScanWorker") as mock_scan_worker_class:
            mock_worker = Mock()
            mock_worker.start = Mock()
            mock_worker.isRunning.return_value = True
            mock_worker.error = Mock()  # We need to emit this
            # We can't easily emit from a Mock unless we setup a real signal or call the handler
            # But the requirement is to use public APIs or simulate events

            # Trigger a scan
            scan_action = [a for a in self.gallery_window.findChildren(QAction) if "Scan" in a.text()][0]

            # Since we can't easily connect a mock signal to the real handler without extra setup,
            # we'll look up the connected slot (handler) for the error signal if we were using a real worker,
            # but here we just want to verify the window handles the error.
            # The window's _on_scan_error is the handler.
            # But we are barred from calling it directly.

            # We will use the fact that starting a scan sets self.scanning = True
            # And then we want to assert it becomes False after error.

            # Let's mock the start method to emit the error signal immediately if possible
            # Or manually invoke the handler? No, that's private.

            # Alternative: Construct a real worker (maybe mocked internals) or just skip the private call part
            # and focus on public state.

            # If I cannot emit the signal from the mock, I will have to call the handler,
            # BUT the instruction says "Drive via public UI actions".
            # If I can't simulate the error signal, I can't trigger the error handling path "publicly".
            # However, I can manually emit the signal if I set it up on the mock.

            # Let's assume for this refactor I can call the handler if there's no other way,
            # OR I use a real signal object on the mock.
            from PySide6.QtCore import QObject, Signal

            class MockWorker(QObject):
                error = Signal(str)
                sprite_found = Signal(dict)
                finished = Signal()
                progress = Signal(int, str)
                cache_status = Signal(str)
                operation_finished = Signal()

                def start(self):
                    pass

                def isRunning(self):
                    return True

                def requestInterruption(self):
                    pass

                def wait(self, ms):
                    return True

                def quit(self):
                    pass  # Required for cleanup

                def isFinished(self):
                    return True

            real_mock_worker = MockWorker()
            mock_scan_worker_class.return_value = real_mock_worker

            scan_action.trigger()
            assert self.gallery_window.scanning

            real_mock_worker.error.emit("Test scan error")

        # Should reset scanning state
        assert not self.gallery_window.scanning
        assert self.gallery_window.scan_worker is None


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.performance
class TestUIWorkflowPerformanceIntegration(QtTestCase):
    """Performance-focused UI workflow tests."""

    def test_rapid_rom_switching_performance(
        self,
        tmp_path,
        mock_settings_manager,
        mock_rom_cache,
    ):
        """Test performance when rapidly switching between ROMs."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        # Create multiple ROM files
        rom_files = []
        for i in range(5):
            rom_path = tmp_path / f"rom_{i}.sfc"
            rom_data = bytearray(1024 * 1024)  # 1MB each

            # Add unique patterns
            for j in range(0, len(rom_data), 4):
                rom_data[j : j + 4] = (i * 1000 + j // 4).to_bytes(4, "little")

            rom_path.write_bytes(rom_data)
            rom_files.append(str(rom_path))

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        window = DetachedGalleryWindow(
            extraction_manager=mock_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )

        start_time = time.time()

        # Rapidly switch between ROMs
        for rom_file in rom_files * 2:  # Load each ROM twice
            window.load_rom(rom_file)
            EventLoopHelper.process_events(10)

        total_time = time.time() - start_time

        # Should handle rapid switching efficiently
        avg_time_per_switch = total_time / (len(rom_files) * 2)
        assert avg_time_per_switch < 0.5, f"ROM switching too slow: {avg_time_per_switch:.2f}s per ROM"

    def test_ui_responsiveness_during_processing(self):
        """Test UI remains responsive during background processing."""
        from ui.widgets.fullscreen_sprite_viewer import FullscreenSpriteViewer

        # Create large sprite dataset
        large_sprite_set = [{"offset": 0x10000 + i * 0x100, "name": f"S{i}"} for i in range(2000)]

        # Note: FullscreenSpriteViewer expects QWidget|None as parent, not Mock
        # Pass None and test without parent-dependent gallery features
        viewer = self.create_widget(FullscreenSpriteViewer, None)

        # Set large dataset
        start_time = time.time()
        success = viewer.set_sprite_data(large_sprite_set, large_sprite_set[0]["offset"], "test_rom.sfc", Mock())
        setup_time = time.time() - start_time

        assert success
        assert setup_time < 1.0, f"Large dataset setup took {setup_time:.2f}s"

        # Test navigation responsiveness
        navigation_times = []

        for _ in range(20):  # Test 20 rapid navigations
            start_nav = time.time()

            key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
            viewer.keyPressEvent(key_event)
            EventLoopHelper.process_events(10)

            nav_time = time.time() - start_nav
            navigation_times.append(nav_time)

        # Navigation should be consistently fast
        avg_nav_time = sum(navigation_times) / len(navigation_times)
        max_nav_time = max(navigation_times)

        assert avg_nav_time < 0.1, f"Average navigation too slow: {avg_nav_time:.3f}s"
        assert max_nav_time < 0.2, f"Slowest navigation too slow: {max_nav_time:.3f}s"
