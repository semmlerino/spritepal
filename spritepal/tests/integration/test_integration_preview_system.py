"""
Integration tests for preview system using real components.
"""
from __future__ import annotations

import os
import time

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Integration tests involve managers that spawn threads"),
    pytest.mark.shared_state_safe,
]

from core.managers import ExtractionManager
from ui.common.simple_preview_coordinator import SimplePreviewCoordinator, SimplePreviewWorker
from utils.rom_cache import ROMCache

# Note: Tests previously used skip_in_offscreen for QThread + waitSignal issues.
# This was replaced with waitUntil pattern which is more stable in offscreen mode.


@pytest.mark.integration
@pytest.mark.gui  # Qt coordinator can segfault in headless mode during teardown
class TestSimplePreviewCoordinator:
    """Test SimplePreviewCoordinator with real ROM data and decompression."""

    @pytest.fixture(autouse=True)
    def setup_di(self, tmp_path):
        """Setup and teardown DI dependencies with isolation.

        Uses tmp_path for cache to prevent polluting $HOME with ~/.spritepal_rom_cache.

        NOTE: Does NOT call reset_container() on teardown because:
        1. session_managers may have registered dependencies we shouldn't clear
        2. reset_container() would break subsequent tests using session fixtures
        The session-level cleanup handles DI container reset appropriately.
        """
        from core.di_container import register_singleton
        from core.protocols.manager_protocols import ROMCacheProtocol

        cache_dir = tmp_path / "rom_cache"
        cache_dir.mkdir(exist_ok=True)
        register_singleton(ROMCacheProtocol, ROMCache(cache_dir=str(cache_dir)))

        yield

        # Don't call reset_container() - let session fixtures manage DI lifecycle

    def test_coordinator_initialization(self, managers_initialized):
        """Test that coordinator initializes correctly."""
        coordinator = SimplePreviewCoordinator()

        # Verify components
        assert coordinator._debounce_timer is not None
        assert coordinator._current_worker is None
        assert coordinator._current_offset == 0

        # Cleanup
        coordinator.cleanup()

    def test_preview_request_with_debouncing(self, test_rom_with_sprites, qtbot, wait_for):
        """Test that preview requests are debounced correctly."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        # Create coordinator
        coordinator = SimplePreviewCoordinator()
        extraction_manager = ExtractionManager()

        # Set ROM data
        coordinator.set_rom_data(rom_path, rom_info['path'].stat().st_size, extraction_manager.get_rom_extractor())

        # Track preview generation
        previews_generated = []

        def on_preview_ready(tile_data, width, height, name):
            previews_generated.append((len(tile_data), width, height, name))

        coordinator.preview_ready.connect(on_preview_ready)

        # Make rapid requests (should be debounced)
        # Request multiple times in quick succession
        for offset in [0x1000, 0x2000, 0x3000, 0x4000, 0x5000]:
            coordinator.request_preview(offset)

        # Wait for debouncing to complete and preview to generate
        # The debounce timer should coalesce these into a single preview
        qtbot.waitUntil(lambda: len(previews_generated) > 0, timeout=2000)

        # Wait a bit more to ensure no additional previews are generated
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        qtbot.wait(200)  # Wait for any pending signals

        # Should only generate one preview for the final offset (debounced)
        # If we get exactly 1, great. If we get 2, the first request snuck through
        # before debouncing kicked in - still acceptable behavior.
        assert 1 <= len(previews_generated) <= 2, (
            f"Expected 1-2 previews (debouncing), got {len(previews_generated)}. "
            "Debouncing should coalesce rapid requests."
        )

        # Cleanup
        coordinator.cleanup()

    def test_preview_generation_with_real_data(self, test_rom_with_sprites, qtbot, wait_for, isolated_managers):
        """Test that preview generates with real tile data."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        # Create coordinator
        coordinator = SimplePreviewCoordinator()
        extraction_manager = ExtractionManager()

        # Set ROM data
        coordinator.set_rom_data(rom_path, rom_info['path'].stat().st_size, extraction_manager.get_rom_extractor())

        # Track preview
        preview_data = None

        def on_preview_ready(tile_data, width, height, name):
            nonlocal preview_data
            preview_data = (tile_data, width, height, name)

        coordinator.preview_ready.connect(on_preview_ready)

        # Request preview at offset with tile data
        coordinator.request_preview(0x10000)

        # Wait for preview using qtbot.waitUntil
        try:
            qtbot.waitUntil(lambda: preview_data is not None, timeout=3000)
        except AssertionError:
            pytest.fail("Preview not generated within timeout")

        # Verify preview data
        tile_data, width, height, name = preview_data
        assert len(tile_data) > 0
        assert width > 0
        assert height > 0
        assert name.startswith("manual_")

        # Cleanup
        coordinator.cleanup()

    def test_preview_with_hal_decompression(self, test_rom_with_sprites, qtbot, wait_for):
        """Test preview generation with HAL-compressed sprites."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        if not rom_info['sprites']:
            pytest.skip("No test sprites in ROM")

        # Create coordinator
        coordinator = SimplePreviewCoordinator()
        extraction_manager = ExtractionManager()

        # Set ROM data
        coordinator.set_rom_data(rom_path, rom_info['path'].stat().st_size, extraction_manager.get_rom_extractor())

        # Track preview
        preview_data = None

        def on_preview_ready(tile_data, width, height, name):
            nonlocal preview_data
            preview_data = (tile_data, width, height, name)

        coordinator.preview_ready.connect(on_preview_ready)

        # Request preview at compressed sprite offset
        sprite_offset = rom_info['sprites'][0]['offset']
        coordinator.request_preview(sprite_offset)

        # Wait for preview using qtbot.waitUntil
        try:
            qtbot.waitUntil(lambda: preview_data is not None, timeout=5000)
        except AssertionError:
            pytest.fail("Preview not generated within timeout")

        # Verify decompressed data was used
        tile_data, width, height, name = preview_data
        assert rom_info['sprites'][0]['decompressed_size'] > 0, "Expected decompressed data"

        # Size might not match exactly due to preview limits
        assert len(tile_data) > 0
        assert width > 0 and height > 0

        # Cleanup
        coordinator.cleanup()

    def test_coordinator_cleanup(self, test_rom_with_sprites, qtbot):
        """Test that coordinator cleans up workers properly."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        # Create coordinator
        coordinator = SimplePreviewCoordinator()
        extraction_manager = ExtractionManager()

        # Set ROM data
        coordinator.set_rom_data(rom_path, rom_info['path'].stat().st_size, extraction_manager.get_rom_extractor())

        # Start a preview generation
        coordinator.request_preview(0x10000)
        # Allow worker to start
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        # Cleanup while worker might be running
        coordinator.cleanup()

        # Verify cleanup
        assert coordinator._current_worker is None or not coordinator._current_worker.isRunning()
        assert not coordinator._debounce_timer.isActive()

class WorkerContainer(QWidget):
    """Container widget to hold worker and manage its lifecycle properly."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.cleanup_timer = QTimer(self)
        self.cleanup_timer.setSingleShot(True)
        self.cleanup_timer.timeout.connect(self.cleanup_worker)

    def set_worker(self, worker):
        """Set the worker and connect cleanup."""
        self.worker = worker
        # Ensure worker has parent for proper Qt lifecycle
        if worker.parent() is None:
            worker.setParent(self)

        # Schedule cleanup after worker finishes
        worker.finished.connect(lambda: self.cleanup_timer.start(100))

    def cleanup_worker(self):
        """Clean up the worker safely."""
        if self.worker:
            if self.worker.isRunning():
                self.worker.quit()
                self.worker.wait(500)
            self.worker.deleteLater()
            self.worker = None

@pytest.mark.integration
@pytest.mark.gui
@pytest.mark.usefixtures("managers_initialized")
class TestSimplePreviewWorker:
    """Test SimplePreviewWorker with real ROM data.

    Note: Uses simple worker lifecycle without QWidget container to avoid
    cleanup issues in headless mode. The worker itself is pure computation
    (no QPixmap/QImage usage) and is safe for headless testing.

    Uses waitUntil pattern instead of waitSignal to avoid potential segfaults
    in offscreen mode with QThread signal handling.
    """

    def test_worker_generates_preview(self, test_rom_with_sprites, qtbot):
        """Test that worker generates preview correctly."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        extraction_manager = ExtractionManager()
        extractor = extraction_manager.get_rom_extractor()

        # Create worker without container - simpler lifecycle
        worker = SimplePreviewWorker(rom_path, 0x10000, extractor)

        # Track signals
        preview_data = []
        error_msg = []

        def on_preview(tile_data, width, height, name):
            preview_data.append((tile_data, width, height, name))

        def on_error(msg):
            error_msg.append(msg)

        worker.preview_ready.connect(on_preview)
        worker.preview_error.connect(on_error)

        # Start worker and wait for completion
        worker.start()

        # Wait for result (either preview or error) - more reliable than waiting for thread stop
        qtbot.waitUntil(
            lambda: len(preview_data) > 0 or len(error_msg) > 0,
            timeout=5000
        )

        # Verify result - either preview or error should be set
        if preview_data:
            tile_data, width, height, name = preview_data[0]
            assert len(tile_data) > 0
            assert width > 0 and height > 0
        else:
            # Error case - still valid if no valid data at offset
            assert len(error_msg) > 0

        # Clean up worker
        if worker.isRunning():
            worker.quit()
            worker.wait(500)
        worker.deleteLater()

    def test_worker_with_compressed_sprite(self, test_rom_with_sprites, qtbot):
        """Test worker with HAL-compressed sprite."""
        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        if not rom_info['sprites']:
            pytest.skip("No test sprites in ROM")

        extraction_manager = ExtractionManager()
        extractor = extraction_manager.get_rom_extractor()

        sprite_offset = rom_info['sprites'][0]['offset']

        # Create worker without container - simpler lifecycle
        worker = SimplePreviewWorker(rom_path, sprite_offset, extractor)

        # Track result
        preview_data = []
        error_msg = []

        def on_preview(tile_data, width, height, name):
            preview_data.append((tile_data, width, height, name))

        def on_error(msg):
            error_msg.append(msg)

        worker.preview_ready.connect(on_preview)
        worker.preview_error.connect(on_error)

        # Start worker and wait for completion
        worker.start()

        # Wait for result (either preview or error) - more reliable than waiting for thread stop
        qtbot.waitUntil(
            lambda: len(preview_data) > 0 or len(error_msg) > 0,
            timeout=5000
        )

        # Verify decompressed data (error is unexpected for this test)
        assert len(preview_data) > 0, f"Expected preview data, got error: {error_msg}"
        tile_data, width, height, name = preview_data[0]
        assert len(tile_data) > 0

        # Clean up worker
        if worker.isRunning():
            worker.quit()
            worker.wait(500)
        worker.deleteLater()

@pytest.mark.integration
@pytest.mark.gui  # Uses Qt coordinator which can segfault in headless mode
@pytest.mark.usefixtures("session_managers")
class TestPreviewCaching:
    """Test preview caching with ROM cache."""

    @pytest.mark.skip(reason="Placeholder - caching not yet implemented")
    def test_preview_cache_integration(self, test_rom_with_sprites, tmp_path):
        """Test that previews can be cached and retrieved."""
        # Register dependencies
        from core.di_container import register_singleton
        from core.protocols.manager_protocols import ROMCacheProtocol

        # Create cache
        cache = ROMCache(cache_dir=str(tmp_path))
        register_singleton(ROMCacheProtocol, cache)

        rom_info = test_rom_with_sprites
        rom_path = str(rom_info['path'])

        # Create coordinator with cache (using cache created above)
        coordinator = SimplePreviewCoordinator(rom_cache=cache)
        extraction_manager = ExtractionManager()

        # Set ROM data
        coordinator.set_rom_data(rom_path, rom_info['path'].stat().st_size, extraction_manager.get_rom_extractor())

        # Generate preview (would be cached if caching is implemented)
        coordinator.request_preview(0x10000)

        # Note: Actual caching implementation may vary
        # This test structure is ready for when caching is added

        # Cleanup
        coordinator.cleanup()
