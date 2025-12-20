"""
Comprehensive Integration Tests for Complete UI Workflows.

These tests cover end-to-end user workflows that would catch the bugs we fixed:
- Complete ROM loading -> scanning -> thumbnail generation -> fullscreen viewing cycle
- Gallery window lifecycle with proper cleanup
- Worker management across multiple operations
- Performance with realistic user scenarios
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QPixmap

from tests.infrastructure.qt_real_testing import (
    EventLoopHelper,
    MemoryHelper,
    QtTestCase,
)
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

# Required for DI container setup
pytestmark = [
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="UI workflows may spawn worker threads"),
]


@pytest.fixture
def complete_test_rom(tmp_path) -> str:
    """Create a complete test ROM with realistic data."""
    rom_path = tmp_path / "complete_test.sfc"
    rom_size = 2 * 1024 * 1024  # 2MB ROM
    rom_data = bytearray(rom_size)

    # Add header
    rom_data[0:4] = b'SNES'

    # Add sprite data at various locations
    sprite_offsets = [
        0x10000, 0x15000, 0x20000, 0x25000, 0x30000,
        0x40000, 0x50000, 0x60000, 0x70000, 0x80000
    ]

    for i, offset in enumerate(sprite_offsets):
        # Add tile data (32 bytes per tile, 16 tiles per sprite)
        for tile in range(16):
            tile_offset = offset + tile * 32
            if tile_offset + 32 <= len(rom_data):
                # Create recognizable pattern
                pattern = bytes([(i + tile + j) % 256 for j in range(32)])
                rom_data[tile_offset:tile_offset + 32] = pattern

    rom_path.write_bytes(rom_data)
    return str(rom_path)

@pytest.fixture
def realistic_sprite_data() -> list[dict[str, Any]]:
    """Create realistic sprite data matching what a ROM scan would find."""
    return [
        {
            'offset': 0x10000,
            'name': 'Player_Idle',
            'decompressed_size': 512,
            'tile_count': 16,
            'compressed': False,
            'quality': 0.9,
        },
        {
            'offset': 0x15000,
            'name': 'Player_Run',
            'decompressed_size': 768,
            'tile_count': 24,
            'compressed': True,
            'quality': 0.85,
        },
        {
            'offset': 0x20000,
            'name': 'Enemy_Goomba',
            'decompressed_size': 256,
            'tile_count': 8,
            'compressed': False,
            'quality': 0.8,
        },
        {
            'offset': 0x25000,
            'name': 'Power_Up_Mushroom',
            'decompressed_size': 128,
            'tile_count': 4,
            'compressed': False,
            'quality': 0.95,
        },
        {
            'offset': 0x30000,
            'name': 'Background_Tile_Set',
            'decompressed_size': 2048,
            'tile_count': 64,
            'compressed': True,
            'quality': 0.7,
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

    @patch('ui.windows.detached_gallery_window.SpriteScanWorker')
    @patch('ui.workers.batch_thumbnail_worker.BatchThumbnailWorker')
    def test_complete_rom_to_fullscreen_workflow(
        self,
        mock_thumbnail_worker_class,
        mock_scan_worker_class,
        complete_test_rom,
        realistic_sprite_data,
    ):
        # DI setup provided by session_managers via pytestmark at module level
        """Test complete workflow: ROM load -> scan -> thumbnails -> fullscreen view."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        # Setup mock extraction manager
        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        # Mock scan worker
        mock_scan_worker = Mock()
        mock_scan_worker.sprite_found = Mock()
        mock_scan_worker.finished = Mock()
        mock_scan_worker.progress = Mock()
        mock_scan_worker.error = Mock()
        mock_scan_worker.cache_status = Mock()
        mock_scan_worker.operation_finished = Mock()
        mock_scan_worker.start = Mock()
        mock_scan_worker.isRunning.return_value = False
        mock_scan_worker_class.return_value = mock_scan_worker

        # Mock thumbnail worker with Qt signals
        mock_thumbnail_worker = Mock()
        mock_thumbnail_worker.thumbnail_ready = Mock()
        mock_thumbnail_worker.progress = Mock()
        mock_thumbnail_worker.queue_thumbnail = Mock()
        mock_thumbnail_worker.run = Mock()  # run() is called by thread, not start()
        mock_thumbnail_worker.finished = Mock()  # Qt signal
        mock_thumbnail_worker.error = Mock()  # Qt signal
        mock_thumbnail_worker.isRunning.return_value = False
        mock_thumbnail_worker.cleanup = Mock()
        mock_thumbnail_worker.deleteLater = Mock()  # Qt method
        mock_thumbnail_worker.moveToThread = Mock()  # Qt method
        mock_thumbnail_worker_class.return_value = mock_thumbnail_worker

        workflow_steps = []

        # Step 1: Create gallery window
        self.gallery_window = DetachedGalleryWindow(extraction_manager=mock_manager)
        workflow_steps.append("gallery_created")

        assert self.gallery_window.windowTitle() == "Sprite Gallery"
        assert not self.gallery_window.scanning

        # Step 2: Load ROM
        self.gallery_window._set_rom_file(complete_test_rom)
        workflow_steps.append("rom_loaded")

        assert self.gallery_window.rom_path == complete_test_rom
        assert "complete_test" in self.gallery_window.windowTitle()

        # Step 3: Start ROM scan
        self.gallery_window._start_scan()
        workflow_steps.append("scan_started")

        assert self.gallery_window.scanning
        mock_scan_worker.start.assert_called_once()

        # Step 4: Simulate sprites being found during scan
        for sprite in realistic_sprite_data:
            self.gallery_window._on_sprite_found(sprite)
        workflow_steps.append("sprites_found")

        assert len(self.gallery_window.sprites_data) == len(realistic_sprite_data)

        # Step 5: Complete scan (this automatically triggers thumbnail generation)
        self.gallery_window._on_scan_finished()
        workflow_steps.append("scan_completed")
        workflow_steps.append("thumbnails_started")  # Thumbnails start automatically

        assert not self.gallery_window.scanning

        # Step 6: Verify thumbnail generation was triggered automatically
        # Verify worker was created and thumbnails were queued
        mock_thumbnail_worker_class.assert_called_once()  # Worker was created
        assert mock_thumbnail_worker.queue_thumbnail.call_count == len(realistic_sprite_data)

        # Step 7: Simulate thumbnail completion
        for sprite in realistic_sprite_data:
            image = ThreadSafeTestImage(64, 64)
            image.fill()
            self.gallery_window._on_thumbnail_ready(sprite['offset'], image)
        workflow_steps.append("thumbnails_completed")

        # Step 8: Open fullscreen viewer
        self.gallery_window.gallery_widget.get_selected_sprite_offset = Mock(
            return_value=realistic_sprite_data[0]['offset']
        )

        with patch('ui.windows.detached_gallery_window.FullscreenSpriteViewer') as mock_viewer_class:
            mock_viewer = Mock()
            mock_viewer.set_sprite_data.return_value = True
            mock_viewer_class.return_value = mock_viewer

            self.gallery_window._open_fullscreen_viewer()
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
            "fullscreen_opened"
        ]

        assert workflow_steps == expected_steps

    def test_gallery_window_lifecycle_memory_safety(
        self,
        complete_test_rom,
        realistic_sprite_data
    ):
        """Test gallery window lifecycle with memory safety checks."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        with MemoryHelper.assert_no_leak(DetachedGalleryWindow, max_increase=1):
            # Create window
            self.gallery_window = DetachedGalleryWindow(extraction_manager=mock_manager)

            # Load ROM and sprites
            self.gallery_window._set_rom_file(complete_test_rom)
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
            realistic_sprite_data,
            realistic_sprite_data[0]['offset'],
            "test_rom.sfc",
            Mock()
        )

        assert success
        assert self.fullscreen_viewer.current_index == 0

        navigation_sequence = []

        def track_navigation(offset):
            navigation_sequence.append(offset)

        self.fullscreen_viewer.sprite_changed.connect(track_navigation)

        # Test navigation sequence: right, right, left, ESC
        test_keys = [
            ('right', Qt.Key.Key_Right),
            ('right', Qt.Key.Key_Right),
            ('left', Qt.Key.Key_Left),
            ('info_toggle', Qt.Key.Key_I),
            ('smooth_toggle', Qt.Key.Key_S),
        ]

        for action, key in test_keys:
            key_event = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                key,
                Qt.KeyboardModifier.NoModifier
            )
            self.fullscreen_viewer.keyPressEvent(key_event)
            EventLoopHelper.process_events(100)

        # Should have navigated through sprites
        assert len(navigation_sequence) >= 3

        # Test info overlay toggle (starts True, toggles to False)
        assert not self.fullscreen_viewer.show_info  # Should be False after toggle

        # Test smooth scaling toggle (starts True, toggles to False)
        assert not self.fullscreen_viewer.smooth_scaling  # Should be False after toggle

    @patch('ui.workers.batch_thumbnail_worker.BatchThumbnailWorker')
    def test_large_rom_performance_workflow(
        self,
        mock_thumbnail_worker_class,
        tmp_path
    ):
        """Test performance with large ROM and many sprites."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        # Create large ROM
        large_rom = tmp_path / "large_rom.sfc"
        rom_size = 4 * 1024 * 1024  # 4MB
        rom_data = bytearray(rom_size)

        # Add patterns throughout
        for i in range(0, rom_size, 1024):
            rom_data[i:i+4] = (i // 1024).to_bytes(4, 'little')

        large_rom.write_bytes(rom_data)

        # Create large sprite dataset
        large_sprite_set = [
            {
                'offset': 0x10000 + i * 0x800,
                'name': f'Sprite_{i:04d}',
                'decompressed_size': 512 + (i % 512),
                'tile_count': 16 + (i % 32),
                'compressed': i % 4 == 0,
                'quality': 0.5 + (i % 50) / 100.0,
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
        self.gallery_window = DetachedGalleryWindow(extraction_manager=mock_manager)
        self.gallery_window._set_rom_file(str(large_rom))

        setup_time = time.time() - start_time

        # Load large sprite set
        start_load = time.time()
        self.gallery_window.set_sprites(large_sprite_set)
        load_time = time.time() - start_load

        # Generate thumbnails
        start_thumbnails = time.time()
        self.gallery_window._generate_thumbnails()
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
        realistic_sprite_data
    ):
        """Test handling of concurrent operations."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        self.gallery_window = DetachedGalleryWindow(extraction_manager=mock_manager)
        self.gallery_window._set_rom_file(complete_test_rom)

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

    @patch('ui.windows.detached_gallery_window.QMessageBox.critical')
    @patch('ui.dialogs.UserErrorDialog.display_error')  # Patched at definition since lazy import
    def test_error_recovery_workflow(
        self,
        mock_show_error,
        mock_critical,
        complete_test_rom,
        realistic_sprite_data,
    ):
        """Test error recovery in workflows."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        self.gallery_window = DetachedGalleryWindow(extraction_manager=mock_manager)

        # Test invalid ROM file
        invalid_rom = "/nonexistent/path/invalid.sfc"

        # Should handle gracefully without crashing
        try:
            self.gallery_window._set_rom_file(invalid_rom)
        except Exception:
            pass  # Expected to fail

        # Window should still be functional
        assert self.gallery_window.rom_path is None or self.gallery_window.rom_path == invalid_rom

        # Load valid ROM after error
        self.gallery_window._set_rom_file(complete_test_rom)
        assert self.gallery_window.rom_path == complete_test_rom

        # Test scan error handling
        self.gallery_window._on_scan_error("Test scan error")

        # Should reset scanning state
        assert not self.gallery_window.scanning
        assert self.gallery_window.scan_worker is None

@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.performance
class TestUIWorkflowPerformanceIntegration(QtTestCase):
    """Performance-focused UI workflow tests."""

    def test_rapid_rom_switching_performance(self, tmp_path):
        """Test performance when rapidly switching between ROMs."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        # Create multiple ROM files
        rom_files = []
        for i in range(5):
            rom_path = tmp_path / f"rom_{i}.sfc"
            rom_data = bytearray(1024 * 1024)  # 1MB each

            # Add unique patterns
            for j in range(0, len(rom_data), 4):
                rom_data[j:j+4] = (i * 1000 + j // 4).to_bytes(4, 'little')

            rom_path.write_bytes(rom_data)
            rom_files.append(str(rom_path))

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        window = DetachedGalleryWindow(extraction_manager=mock_manager)

        start_time = time.time()

        # Rapidly switch between ROMs
        for rom_file in rom_files * 2:  # Load each ROM twice
            window._set_rom_file(rom_file)
            EventLoopHelper.process_events(10)

        total_time = time.time() - start_time

        # Should handle rapid switching efficiently
        avg_time_per_switch = total_time / (len(rom_files) * 2)
        assert avg_time_per_switch < 0.5, f"ROM switching too slow: {avg_time_per_switch:.2f}s per ROM"

    def test_ui_responsiveness_during_processing(self):
        """Test UI remains responsive during background processing."""
        from ui.widgets.fullscreen_sprite_viewer import FullscreenSpriteViewer

        # Create large sprite dataset
        large_sprite_set = [
            {'offset': 0x10000 + i * 0x100, 'name': f'S{i}'}
            for i in range(2000)
        ]

        # Note: FullscreenSpriteViewer expects QWidget|None as parent, not Mock
        # Pass None and test without parent-dependent gallery features
        viewer = self.create_widget(FullscreenSpriteViewer, None)

        # Set large dataset
        start_time = time.time()
        success = viewer.set_sprite_data(
            large_sprite_set,
            large_sprite_set[0]['offset'],
            "test_rom.sfc",
            Mock()
        )
        setup_time = time.time() - start_time

        assert success
        assert setup_time < 1.0, f"Large dataset setup took {setup_time:.2f}s"

        # Test navigation responsiveness
        navigation_times = []

        for _ in range(20):  # Test 20 rapid navigations
            start_nav = time.time()

            key_event = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Right,
                Qt.KeyboardModifier.NoModifier
            )
            viewer.keyPressEvent(key_event)
            EventLoopHelper.process_events(10)

            nav_time = time.time() - start_nav
            navigation_times.append(nav_time)

        # Navigation should be consistently fast
        avg_nav_time = sum(navigation_times) / len(navigation_times)
        max_nav_time = max(navigation_times)

        assert avg_nav_time < 0.1, f"Average navigation too slow: {avg_nav_time:.3f}s"
        assert max_nav_time < 0.2, f"Slowest navigation too slow: {max_nav_time:.3f}s"

@pytest.mark.headless
@pytest.mark.integration
class TestUIWorkflowsHeadlessIntegration:
    """Headless workflow tests using logic verification."""

    def test_headless_workflow_state_machine(self):
        """Test UI workflow state machine logic."""
        class WorkflowStateMachine:
            def __init__(self):
                self.state = "initial"
                self.transitions = {
                    "initial": ["rom_loading"],
                    "rom_loading": ["rom_loaded", "rom_error"],
                    "rom_loaded": ["scanning", "sprite_loading"],
                    "rom_error": ["rom_loading"],
                    "scanning": ["scan_complete", "scan_error"],
                    "scan_error": ["scanning", "rom_loaded"],
                    "scan_complete": ["thumbnail_generation", "sprite_selection"],
                    "thumbnail_generation": ["thumbnails_complete"],
                    "thumbnails_complete": ["sprite_selection", "fullscreen_view"],
                    "sprite_selection": ["fullscreen_view", "sprite_extraction"],
                    "fullscreen_view": ["sprite_selection"],
                    "sprite_extraction": ["sprite_selection"],
                }
                self.state_history = [self.state]

            def transition_to(self, new_state):
                if new_state in self.transitions.get(self.state, []):
                    self.state = new_state
                    self.state_history.append(new_state)
                    return True
                return False

            def get_valid_transitions(self):
                return self.transitions.get(self.state, [])

            def is_valid_workflow(self):
                # Check if we can reach fullscreen_view or sprite_extraction
                return ("fullscreen_view" in self.state_history or
                        "sprite_extraction" in self.state_history)

        workflow = WorkflowStateMachine()

        # Test valid workflow path
        assert workflow.transition_to("rom_loading")
        assert workflow.transition_to("rom_loaded")
        assert workflow.transition_to("scanning")
        assert workflow.transition_to("scan_complete")
        assert workflow.transition_to("thumbnail_generation")
        assert workflow.transition_to("thumbnails_complete")
        assert workflow.transition_to("sprite_selection")
        assert workflow.transition_to("fullscreen_view")

        assert workflow.is_valid_workflow()

        # Test invalid transitions
        workflow2 = WorkflowStateMachine()
        assert not workflow2.transition_to("fullscreen_view")  # Can't jump directly
        assert workflow2.state == "initial"

        # Test error recovery
        workflow3 = WorkflowStateMachine()
        workflow3.transition_to("rom_loading")
        workflow3.transition_to("rom_error")
        workflow3.transition_to("rom_loading")  # Retry
        workflow3.transition_to("rom_loaded")

        assert workflow3.state == "rom_loaded"

    def test_headless_resource_lifecycle_logic(self):
        """Test resource lifecycle management logic."""
        class ResourceManager:
            def __init__(self):
                self.resources = {}
                self.resource_types = {
                    'rom_data': {'max_size': 10 * 1024 * 1024, 'cleanup_priority': 1},
                    'thumbnails': {'max_count': 1000, 'cleanup_priority': 2},
                    'cache': {'max_size': 50 * 1024 * 1024, 'cleanup_priority': 3},
                }
                self.total_memory = 0
                self.max_total_memory = 100 * 1024 * 1024  # 100MB limit

            def allocate_resource(self, resource_type, resource_id, size):
                if resource_type not in self.resource_types:
                    return False

                # Check if allocation would exceed limits
                if self.total_memory + size > self.max_total_memory:
                    self._cleanup_by_priority()

                if self.total_memory + size <= self.max_total_memory:
                    self.resources[resource_id] = {
                        'type': resource_type,
                        'size': size,
                        'allocated_at': len(self.resources)
                    }
                    self.total_memory += size
                    return True

                return False

            def free_resource(self, resource_id):
                if resource_id in self.resources:
                    resource = self.resources[resource_id]
                    self.total_memory -= resource['size']
                    del self.resources[resource_id]
                    return True
                return False

            def _cleanup_by_priority(self):
                # Sort resources by cleanup priority and age
                cleanup_candidates = []
                for res_id, resource in self.resources.items():
                    priority = self.resource_types[resource['type']]['cleanup_priority']
                    cleanup_candidates.append((priority, resource['allocated_at'], res_id))

                cleanup_candidates.sort()  # Sort by priority, then age

                # Free oldest, lowest priority resources
                freed_memory = 0
                target_free = self.max_total_memory * 0.25  # Free 25%

                for _, _, res_id in cleanup_candidates:
                    if freed_memory >= target_free:
                        break
                    resource = self.resources[res_id]
                    freed_memory += resource['size']
                    self.free_resource(res_id)

            def get_memory_usage(self):
                return {
                    'total': self.total_memory,
                    'max': self.max_total_memory,
                    'utilization': self.total_memory / self.max_total_memory
                }

        manager = ResourceManager()

        # Allocate resources
        assert manager.allocate_resource('rom_data', 'rom1', 8 * 1024 * 1024)
        assert manager.allocate_resource('thumbnails', 'thumb_cache', 20 * 1024 * 1024)
        assert manager.allocate_resource('cache', 'general_cache', 30 * 1024 * 1024)

        usage = manager.get_memory_usage()
        assert usage['utilization'] < 1.0  # Should be under limit

        # Try to allocate resource that would exceed limit
        large_allocation = 50 * 1024 * 1024
        manager.allocate_resource('cache', 'large_cache', large_allocation)

        # Should trigger cleanup and succeed or fail gracefully
        final_usage = manager.get_memory_usage()
        assert final_usage['utilization'] <= 1.0  # Should not exceed limit

    def test_headless_concurrent_operation_logic(self):
        """Test concurrent operation management logic."""
        import threading

        class ConcurrentOperationManager:
            def __init__(self, max_concurrent=3):
                self.max_concurrent = max_concurrent
                self.active_operations = {}
                self.operation_queue = []
                self.lock = threading.Lock()
                self.next_id = 0

            def submit_operation(self, operation_type, duration=1.0):
                with self.lock:
                    operation_id = f"{operation_type}_{self.next_id}"
                    self.next_id += 1

                    if len(self.active_operations) < self.max_concurrent:
                        # Start immediately
                        self.active_operations[operation_id] = {
                            'type': operation_type,
                            'duration': duration,
                            'started_at': self.next_id
                        }
                        return operation_id
                    else:
                        # Queue for later
                        self.operation_queue.append({
                            'id': operation_id,
                            'type': operation_type,
                            'duration': duration
                        })
                        return None  # Queued

            def complete_operation(self, operation_id):
                with self.lock:
                    if operation_id in self.active_operations:
                        del self.active_operations[operation_id]

                        # Start next queued operation
                        if self.operation_queue:
                            next_op = self.operation_queue.pop(0)
                            self.active_operations[next_op['id']] = {
                                'type': next_op['type'],
                                'duration': next_op['duration'],
                                'started_at': self.next_id
                            }
                            return next_op['id']

                return None

            def get_status(self):
                with self.lock:
                    return {
                        'active_count': len(self.active_operations),
                        'queued_count': len(self.operation_queue),
                        'active_operations': list(self.active_operations.keys()),
                        'can_accept_more': len(self.active_operations) < self.max_concurrent
                    }

        manager = ConcurrentOperationManager(max_concurrent=2)

        # Submit operations up to limit
        op1 = manager.submit_operation('scan_rom', 2.0)
        op2 = manager.submit_operation('generate_thumbnails', 1.5)
        op3 = manager.submit_operation('extract_sprite', 0.5)  # Should be queued

        status = manager.get_status()
        assert status['active_count'] == 2
        assert status['queued_count'] == 1
        assert op1 is not None
        assert op2 is not None
        assert op3 is None  # Was queued

        # Complete operation
        next_op = manager.complete_operation(op1)
        assert next_op is not None  # Next operation started

        status = manager.get_status()
        assert status['active_count'] == 2  # Still at max
        assert status['queued_count'] == 0  # Queue emptied
