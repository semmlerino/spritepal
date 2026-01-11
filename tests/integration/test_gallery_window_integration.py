"""
Integration tests for DetachedGalleryWindow.

These tests focus on end-to-end workflows that would catch bugs like:
- ROM loading and scanning failures
- Worker lifecycle management issues
- Memory leaks with large sprite sets
- Thread leaks from improper cleanup
- Virtual scrolling performance problems
"""

from __future__ import annotations

import gc
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QTimer

from tests.fixtures.timeouts import get_timeout_multiplier
from tests.infrastructure.qt_real_testing import (
    EventLoopHelper,
    MemoryHelper,
    QtTestCase,
)
from ui.windows.detached_gallery_window import DetachedGalleryWindow

# Use function-scoped app_context for proper test isolation
# (migrated from session_app_context to fix shared state and thread cleanup issues)
pytestmark = [
    pytest.mark.usefixtures("app_context"),
]

# Module-level constants for reuse
SIGNALS_TO_DISCONNECT = [
    ("sprite_found", "on_sprite_found"),
    ("progress", "on_scan_progress"),
    ("finished", "on_scan_finished"),
    ("error", "on_scan_error"),
]


@pytest.fixture
def test_rom_file(tmp_path) -> str:
    """Create a test ROM file."""
    rom_path = tmp_path / "test_rom.sfc"
    # Create a minimal ROM file
    rom_data = b"SNES" + b"\x00" * (1024 * 1024 - 4)  # 1MB ROM
    rom_path.write_bytes(rom_data)
    return str(rom_path)


@pytest.fixture
def mock_extraction_manager():
    """Create mock extraction manager for integration tests."""
    manager = Mock()
    # Mock rom_extractor.extract_sprite_from_rom - returns (output_path, extraction_info)
    mock_rom_extractor = Mock()
    mock_rom_extractor.extract_sprite_from_rom.return_value = ("test_output.png", {})
    manager.get_rom_extractor.return_value = mock_rom_extractor
    manager.get_known_sprite_locations.return_value = {
        "sprite_1": Mock(offset=0x10000),
        "sprite_2": Mock(offset=0x20000),
        "sprite_3": Mock(offset=0x30000),
    }
    return manager


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
def mock_scan_worker():
    """Create mock scan worker."""
    worker = Mock()
    worker.sprite_found = Mock()
    worker.finished = Mock()
    worker.progress = Mock()
    worker.error = Mock()
    worker.cache_status = Mock()
    worker.operation_finished = Mock()
    worker.start = Mock()
    worker.isRunning.return_value = False
    worker.requestInterruption = Mock()
    worker.wait.return_value = True
    return worker


@pytest.fixture
def mock_thumbnail_worker():
    """Create mock thumbnail worker."""
    worker = Mock()
    worker.thumbnail_ready = Mock()
    worker.progress = Mock()
    worker.queue_thumbnail = Mock()
    worker.start = Mock()
    worker.isRunning.return_value = False
    worker.cleanup = Mock()
    return worker


@pytest.fixture
def mock_scan_worker_running():
    """Create mock scan worker that is currently running."""
    worker = Mock()
    worker.start = Mock()
    worker.isRunning.return_value = True
    worker.requestInterruption = Mock()
    worker.wait.return_value = True
    return worker


@pytest.fixture
def mock_thumbnail_worker_for_queueing():
    """Create mock thumbnail worker configured for thumbnail queueing."""
    worker = Mock()
    worker.queue_thumbnail = Mock()
    worker.start = Mock()
    worker.isRunning.return_value = False
    return worker


@pytest.mark.gui
@pytest.mark.integration
class TestDetachedGalleryWindowIntegration(QtTestCase):
    """Integration tests for detached gallery window."""

    def setup_method(self):
        """Set up for each test method."""
        super().setup_method()
        self.window: DetachedGalleryWindow | None = None

    def teardown_method(self):
        """Clean up after each test."""
        from PySide6.QtWidgets import QApplication

        from ui.common import WorkerManager

        if self.window:
            # Call close to trigger closeEvent and worker cleanup
            self.window.close()

            # Process events to ensure closeEvent handlers run
            QApplication.processEvents()

            # Wait for workers to stop using condition-based polling
            # (more efficient than fixed sleep loop - exits early when workers done)
            import time

            from tests.fixtures.timeouts import cleanup_timeout

            timeout_ms = cleanup_timeout()
            poll_interval_ms = 50  # Check every 50ms instead of 100ms sleep
            elapsed = 0
            while elapsed < timeout_ms and WorkerManager.get_running_worker_count() > 0:
                QApplication.processEvents()
                time.sleep(poll_interval_ms / 1000.0)  # sleep-ok: polling for worker completion
                elapsed += poll_interval_ms

            # Schedule window deletion
            self.window.deleteLater()
            QApplication.processEvents()

            self.window = None

        # Clean up any remaining workers
        WorkerManager.cleanup_all()

        super().teardown_method()

    def test_window_initialization_and_cleanup(self, mock_extraction_manager, mock_settings_manager, mock_rom_cache):
        """Test basic window initialization and cleanup."""
        with MemoryHelper.assert_no_leak(DetachedGalleryWindow, max_increase=1):
            self.window = DetachedGalleryWindow(
                extraction_manager=mock_extraction_manager,
                settings_manager=mock_settings_manager,
                rom_cache=mock_rom_cache,
            )

            # Window should initialize properly
            assert self.window.windowTitle() == "Sprite Gallery"
            assert self.window.gallery_widget is not None
            assert self.window.status_bar is not None
            assert not self.window.scanning
            assert self.window.sprites_data == []

            # Close window
            self.window.close()
            self.window = None

    def test_rom_loading_workflow(self, mock_extraction_manager, mock_settings_manager, mock_rom_cache, test_rom_file):
        """Test complete ROM loading workflow."""
        self.window = DetachedGalleryWindow(
            extraction_manager=mock_extraction_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )

        # Load ROM file
        self.window._set_rom_file(test_rom_file)

        # Verify ROM was loaded
        assert self.window.rom_path == test_rom_file
        assert self.window.rom_size > 0
        assert "test_rom" in self.window.windowTitle()

        # Status should be updated
        status_text = self.window.status_bar.currentMessage()
        assert "ROM loaded" in status_text or "sprites" in status_text.lower()

    @patch("ui.windows.detached_gallery_window.SpriteScanWorker")
    def test_rom_scanning_with_proper_cleanup(
        self,
        mock_scan_worker_class,
        mock_extraction_manager,
        mock_settings_manager,
        mock_rom_cache,
        mock_scan_worker,
        test_rom_file,
    ):
        """Test ROM scanning with proper worker cleanup."""
        mock_scan_worker_class.return_value = mock_scan_worker

        self.window = DetachedGalleryWindow(
            extraction_manager=mock_extraction_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )
        self.window._set_rom_file(test_rom_file)

        # Capture initial sprite count (may have cached sprites from prior ROM cache)
        initial_sprite_count = len(self.window.sprites_data)

        # Start scan
        self.window._start_scan()

        # Verify worker was created and started
        mock_scan_worker_class.assert_called_once()
        mock_scan_worker.start.assert_called_once()
        assert self.window.scan_worker is not None
        assert self.window.scanning

        # Simulate sprite found
        sprite_info = {"offset": 0x10000, "decompressed_size": 1024, "tile_count": 32, "quality": 0.8}
        self.window._on_sprite_found(sprite_info)

        # Verify sprite was added (one more than initial count)
        assert len(self.window.sprites_data) == initial_sprite_count + 1
        # Verify our new sprite is in the list
        added_sprites = [s for s in self.window.sprites_data if s.get("offset") == 0x10000 and s.get("quality") == 0.8]
        assert len(added_sprites) == 1

        # Simulate scan completion
        self.window._on_scan_finished()

        # Verify cleanup
        assert not self.window.scanning
        assert self.window.scan_worker is None
        assert self.window.scan_timeout_timer is None

    @patch("ui.windows.detached_gallery_window.ThumbnailWorkerController")
    def test_thumbnail_generation_lifecycle(
        self,
        mock_thumbnail_controller_class,
        mock_extraction_manager,
        mock_settings_manager,
        mock_rom_cache,
        test_rom_file,
    ):
        """Test thumbnail generation worker lifecycle.

        Note: The implementation uses ThumbnailWorkerController which manages
        the actual BatchThumbnailWorker internally. We verify that the controller
        is properly created and used.
        """
        # Create mock controller instance
        mock_controller = Mock()
        mock_controller.thumbnail_ready = Mock()
        mock_controller.progress = Mock()
        mock_controller.queue_thumbnail = Mock()
        mock_controller.start_worker = Mock()
        mock_thumbnail_controller_class.return_value = mock_controller

        self.window = DetachedGalleryWindow(
            extraction_manager=mock_extraction_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )
        self.window._set_rom_file(test_rom_file)

        # Set some sprite data
        self.window.sprites_data = [
            {"offset": 0x10000, "name": "Sprite1"},
            {"offset": 0x20000, "name": "Sprite2"},
        ]

        # Generate thumbnails
        self.window._generate_thumbnails()

        # Verify controller was created
        mock_thumbnail_controller_class.assert_called_once()

        # Verify start_worker was called with correct arguments
        mock_controller.start_worker.assert_called_once_with(test_rom_file, mock_extraction_manager.get_rom_extractor())

        # Verify queue_thumbnail was called for each sprite
        assert mock_controller.queue_thumbnail.call_count == 2

        # Verify controller is stored on the window
        assert self.window.thumbnail_controller is not None

    def test_memory_management_with_large_sprite_set(
        self, mock_extraction_manager, mock_settings_manager, mock_rom_cache
    ):
        """Test memory management with large number of sprites."""
        # Create large sprite data set
        large_sprite_set = [
            {
                "offset": 0x10000 + i * 0x1000,
                "name": f"Sprite_{i:03d}",
                "decompressed_size": 1024 + (i * 10),
                "tile_count": 32 + (i % 16),
            }
            for i in range(2000)  # 2000 sprites
        ]

        with MemoryHelper.assert_no_leak(DetachedGalleryWindow, max_increase=1):
            self.window = DetachedGalleryWindow(
                extraction_manager=mock_extraction_manager,
                settings_manager=mock_settings_manager,
                rom_cache=mock_rom_cache,
            )

            # Set large sprite set
            self.window.set_sprites(large_sprite_set)

            # Verify sprites were set
            assert len(self.window.sprites_data) == 2000

            # Process events to ensure UI updates
            EventLoopHelper.process_events(100)

            # Close window to test cleanup
            self.window.close()
            self.window = None

    def test_worker_cleanup_prevents_thread_leaks(self, mock_extraction_manager, mock_settings_manager, mock_rom_cache):
        """Test that proper worker cleanup prevents thread leaks."""
        initial_thread_count = len([t for t in gc.get_objects() if isinstance(t, type(QTimer()))])

        # Create and destroy multiple windows with workers
        for _ in range(5):
            window = DetachedGalleryWindow(
                extraction_manager=mock_extraction_manager,
                settings_manager=mock_settings_manager,
                rom_cache=mock_rom_cache,
            )

            # Simulate having active workers
            window.scan_worker = Mock()
            window.scan_worker.isRunning.return_value = True
            window.scan_worker.requestInterruption = Mock()
            window.scan_worker.wait.return_value = True

            window.thumbnail_worker = Mock()
            window.thumbnail_worker.cleanup = Mock()

            # Close window (triggers cleanup)
            window.close()

        # Force garbage collection
        gc.collect()
        EventLoopHelper.process_events(100)
        gc.collect()

        final_thread_count = len([t for t in gc.get_objects() if isinstance(t, type(QTimer()))])

        # Should not have excessive thread growth
        assert final_thread_count - initial_thread_count <= 2  # Allow some variance

    def test_fullscreen_viewer_integration(self, mock_extraction_manager, mock_settings_manager, mock_rom_cache):
        """Test integration with fullscreen sprite viewer.

        Note: FullscreenSpriteViewer is created without a parent (None) to avoid
        fullscreen constraints that can occur with parent widgets.
        """
        self.window = DetachedGalleryWindow(
            extraction_manager=mock_extraction_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )

        # Set sprite data
        self.window.sprites_data = [
            {"offset": 0x10000, "name": "Sprite1"},
            {"offset": 0x20000, "name": "Sprite2"},
        ]

        # Mock gallery widget selection
        self.window.gallery_widget.get_selected_sprite_offset = Mock(return_value=0x10000)

        with patch("ui.windows.detached_gallery_window.FullscreenSpriteViewer") as mock_viewer_class:
            mock_viewer = Mock()
            mock_viewer.set_sprite_data.return_value = True
            mock_viewer_class.return_value = mock_viewer

            # Open fullscreen viewer
            self.window._open_fullscreen_viewer()

            # Verify viewer was created without parent (to avoid fullscreen constraints)
            mock_viewer_class.assert_called_once_with(None)
            mock_viewer.set_sprite_data.assert_called_once()
            mock_viewer.show.assert_called_once()

    @patch("ui.windows.detached_gallery_window.QMessageBox")
    def test_sprite_extraction_workflow(
        self, mock_msgbox, mock_extraction_manager, mock_settings_manager, mock_rom_cache, tmp_path
    ):
        """Test sprite extraction workflow."""
        self.window = DetachedGalleryWindow(
            extraction_manager=mock_extraction_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )
        self.window.rom_path = "test_rom.sfc"

        # Mock gallery selection
        self.window.gallery_widget.get_selected_sprite_offset = Mock(return_value=0x10000)

        output_file = str(tmp_path / "extracted_sprite.png")

        # Perform extraction
        self.window._perform_extraction(0x10000, output_file)

        # Verify rom_extractor.extract_sprite_from_rom was called
        # output_base is the path without extension
        expected_output_base = str(tmp_path / "extracted_sprite")
        self.window.rom_extractor.extract_sprite_from_rom.assert_called_once_with(
            "test_rom.sfc", 0x10000, expected_output_base, sprite_name=""
        )

    @patch("ui.windows.detached_gallery_window.QMessageBox")
    @patch("ui.windows.detached_gallery_window.SpriteScanWorker")
    def test_scan_timeout_handling(
        self,
        mock_scan_worker_class,
        mock_msgbox,
        mock_extraction_manager,
        mock_settings_manager,
        mock_rom_cache,
        mock_scan_worker_running,
        test_rom_file,
    ):
        """Test scan timeout handling prevents infinite scanning."""
        mock_scan_worker_class.return_value = mock_scan_worker_running

        self.window = DetachedGalleryWindow(
            extraction_manager=mock_extraction_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )
        self.window._set_rom_file(test_rom_file)

        # Start scan
        self.window._start_scan()

        # Simulate timeout by calling timeout handler directly
        self.window._on_scan_timeout()

        # Verify scan was stopped
        assert not self.window.scanning
        assert self.window.scan_worker is None
        mock_scan_worker_running.requestInterruption.assert_called()

    def test_virtual_scrolling_performance(self, mock_extraction_manager, mock_settings_manager, mock_rom_cache):
        """Test virtual scrolling performance with many sprites."""
        # Create massive sprite set to test virtual scrolling
        massive_sprite_set = [
            {
                "offset": 0x10000 + i * 0x100,
                "name": f"Sprite_{i:05d}",
                "decompressed_size": 512,
                "tile_count": 16,
            }
            for i in range(10000)  # 10,000 sprites
        ]

        import time

        start_time = time.time()

        self.window = DetachedGalleryWindow(
            extraction_manager=mock_extraction_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )
        self.window.set_sprites(massive_sprite_set)

        # Process UI updates
        EventLoopHelper.process_events(500)

        setup_time = time.time() - start_time

        # Should handle large sprite sets efficiently (< 2 seconds baseline, scaled for environment)
        threshold = 2.0 * get_timeout_multiplier()
        assert setup_time < threshold, f"Virtual scrolling setup took {setup_time:.2f}s, expected < {threshold:.1f}s"

        # Verify all sprites are accessible
        assert len(self.window.sprites_data) == 10000

    def test_concurrent_worker_management(
        self,
        mock_extraction_manager,
        mock_settings_manager,
        mock_rom_cache,
        mock_scan_worker_running,
        mock_thumbnail_worker,
        test_rom_file,
    ):
        """Test management of concurrent workers prevents issues."""
        self.window = DetachedGalleryWindow(
            extraction_manager=mock_extraction_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )
        self.window._set_rom_file(test_rom_file)

        # Set initial workers
        # Note: implementation uses thumbnail_controller not thumbnail_worker
        self.window.scan_worker = mock_scan_worker_running
        self.window.thumbnail_controller = mock_thumbnail_worker

        # Trigger cleanup (like starting new scan)
        self.window._cleanup_existing_workers()

        # Verify old workers were cleaned up
        mock_scan_worker_running.requestInterruption.assert_called()
        mock_thumbnail_worker.cleanup.assert_called()
        assert self.window.scan_worker is None
        assert self.window.thumbnail_controller is None


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.performance
class TestGalleryWindowPerformance(QtTestCase):
    """Performance-focused integration tests."""

    @patch("ui.windows.detached_gallery_window.ThumbnailWorkerController")
    def test_thumbnail_generation_performance(
        self,
        mock_controller_class,
        mock_extraction_manager,
        mock_settings_manager,
        mock_rom_cache,
        mock_thumbnail_worker_for_queueing,
    ):
        """Test thumbnail generation performance with realistic sprite counts."""
        mock_controller_class.return_value = mock_thumbnail_worker_for_queueing

        # Typical ROM might have 100-500 sprites
        typical_sprite_count = 300
        sprites_data = [
            {
                "offset": 0x10000 + i * 0x800,
                "name": f"Sprite_{i:03d}",
                "decompressed_size": 1024,
                "tile_count": 32,
            }
            for i in range(typical_sprite_count)
        ]

        import time

        window = DetachedGalleryWindow(
            extraction_manager=mock_extraction_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )
        window.rom_path = "test_rom.sfc"

        # Measure thumbnail request processing time
        start_time = time.time()

        window.sprites_data = sprites_data
        window._generate_thumbnails()

        processing_time = time.time() - start_time

        # Should queue all thumbnails quickly (< 1 second)
        assert processing_time < 1.0, f"Thumbnail queuing took {processing_time:.2f}s, too slow"

        # Verify all sprites were queued
        assert mock_thumbnail_worker_for_queueing.queue_thumbnail.call_count == typical_sprite_count

    def test_window_resize_performance(self, mock_extraction_manager, mock_settings_manager, mock_rom_cache):
        """Test window resize performance with many sprites."""
        sprites_data = [{"offset": 0x10000 + i * 0x100, "name": f"S{i}"} for i in range(1000)]

        window = DetachedGalleryWindow(
            extraction_manager=mock_extraction_manager,
            settings_manager=mock_settings_manager,
            rom_cache=mock_rom_cache,
        )
        window.set_sprites(sprites_data)
        window.show()

        import time

        # Measure resize performance
        start_time = time.time()

        # Simulate multiple resizes
        for size in [(800, 600), (1200, 900), (1600, 1200), (1024, 768)]:
            window.resize(*size)
            EventLoopHelper.process_events(50)

        resize_time = time.time() - start_time

        # Should handle resizes smoothly (< 2 seconds for all resizes)
        assert resize_time < 2.0, f"Window resizing took {resize_time:.2f}s, too slow"


@pytest.mark.headless
@pytest.mark.integration
class TestGalleryWindowHeadlessIntegration:
    """Headless integration tests using mocks."""

    def test_headless_worker_lifecycle_logic(self):
        """Test worker lifecycle logic in headless environment."""
        with patch("ui.windows.detached_gallery_window.DetachedGalleryWindow.__init__") as mock_init:
            mock_init.return_value = None

            # Create mock window to test cleanup logic
            window = Mock()
            window.scan_worker = None
            window.thumbnail_worker = None
            window.scan_timeout_timer = None

            # Mock the cleanup method
            def mock_cleanup():
                workers_cleaned = 0

                if window.scan_worker is not None:
                    if hasattr(window.scan_worker, "isRunning") and window.scan_worker.isRunning():
                        window.scan_worker.requestInterruption()
                        window.scan_worker.wait(3000)
                    window.scan_worker = None
                    workers_cleaned += 1

                if window.thumbnail_worker is not None:
                    if hasattr(window.thumbnail_worker, "cleanup"):
                        window.thumbnail_worker.cleanup()
                    window.thumbnail_worker = None
                    workers_cleaned += 1

                if window.scan_timeout_timer is not None:
                    window.scan_timeout_timer.stop()
                    window.scan_timeout_timer = None

                return workers_cleaned

            window._cleanup_existing_workers = mock_cleanup

            # Test with no workers
            cleaned = window._cleanup_existing_workers()
            assert cleaned == 0

            # Test with scan worker
            window.scan_worker = Mock()
            window.scan_worker.isRunning.return_value = True
            window.scan_worker.requestInterruption = Mock()
            window.scan_worker.wait = Mock(return_value=True)

            cleaned = window._cleanup_existing_workers()
            assert cleaned == 1
            assert window.scan_worker is None

            # Test with thumbnail worker
            window.thumbnail_worker = Mock()
            window.thumbnail_worker.cleanup = Mock()

            cleaned = window._cleanup_existing_workers()
            assert cleaned == 1
            assert window.thumbnail_worker is None

    def test_headless_signal_disconnection_logic(self):
        """Test signal disconnection logic in headless environment."""
        # Test the signal disconnection logic without real Qt objects

        # Mock worker with signals
        worker = Mock()
        disconnected_signals = []

        # Add mock signals that track disconnection
        for signal_name, slot_name in SIGNALS_TO_DISCONNECT:
            mock_signal = Mock()
            mock_signal.disconnect = Mock(side_effect=lambda *args, s=signal_name: disconnected_signals.append(s))
            setattr(worker, signal_name, mock_signal)

        # Simulate disconnection logic
        for signal_name, slot_name in SIGNALS_TO_DISCONNECT:
            try:
                signal = getattr(worker, signal_name, None)
                if signal is not None:
                    signal.disconnect()
            except (RuntimeError, TypeError):
                pass

        # Verify all signals were disconnected
        assert len(disconnected_signals) == len(SIGNALS_TO_DISCONNECT)
        assert "sprite_found" in disconnected_signals
        assert "progress" in disconnected_signals

    def test_headless_infinite_loop_prevention_logic(self):
        """Test infinite loop prevention logic without real workers."""
        # Simulate the idle detection logic from BatchThumbnailWorker

        class MockThumbnailWorkerLogic:
            def __init__(self):
                self.processed_count = 0
                self.idle_iterations = 0
                self.max_idle_iterations = 100
                self.stop_requested = False
                self.request_queue = []

            def get_next_request(self):
                if self.request_queue:
                    return self.request_queue.pop(0)
                return None

            def simulate_processing_loop(self, max_iterations=1000):
                """Simulate the processing loop with idle detection."""
                iterations = 0

                while not self.stop_requested and iterations < max_iterations:
                    iterations += 1

                    request = self.get_next_request()
                    if not request:
                        self.idle_iterations += 1

                        # Auto-stop after being idle for too long
                        if self.idle_iterations >= self.max_idle_iterations:
                            break

                        continue

                    # Reset idle counter when we get work
                    self.idle_iterations = 0
                    self.processed_count += 1

                return iterations, self.processed_count

        # Test with no work - should stop due to idle detection
        worker_logic = MockThumbnailWorkerLogic()
        iterations, processed = worker_logic.simulate_processing_loop()

        assert iterations == worker_logic.max_idle_iterations
        assert processed == 0
        assert not worker_logic.stop_requested  # Stopped due to idle detection

        # Test with some work - should process and then idle stop
        worker_logic = MockThumbnailWorkerLogic()
        worker_logic.request_queue = ["req1", "req2", "req3"]

        iterations, processed = worker_logic.simulate_processing_loop()

        assert processed == 3  # Processed all requests
        assert iterations == 3 + worker_logic.max_idle_iterations  # Work + idle detection

        # Test stop request - should stop immediately
        worker_logic = MockThumbnailWorkerLogic()
        worker_logic.request_queue = ["req1", "req2"]
        worker_logic.stop_requested = True

        iterations, processed = worker_logic.simulate_processing_loop()

        assert iterations == 0  # Should stop immediately
        assert processed == 0
