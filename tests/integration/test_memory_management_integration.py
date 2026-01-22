"""
Integration tests for Memory Management across components.

These tests focus on memory-related bugs that were fixed:
- ROM data cleanup after processing
- Cache clearing when switching contexts
- Weak references working correctly
- No memory leaks with large sprite sets
- Proper cleanup on component destruction

NOTE: Tests using fictional mock classes (MockROMCache, MockThumbnailCache,
MockMemoryPool, MockReferenceCounter, MockCacheCoordinator) have been removed.
Those tests provided false confidence by testing mocks rather than production code.
"""

from __future__ import annotations

import gc

# Skip tests that use complex Qt widgets + event processing in offscreen mode
import os
import weakref
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from tests.infrastructure.qt_real_testing import (
    EventLoopHelper,
    MemoryHelper,
    QtTestCase,
)
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

_offscreen_mode = os.environ.get("QT_QPA_PLATFORM") == "offscreen"
skip_in_offscreen = pytest.mark.skipif(
    _offscreen_mode, reason="Complex Qt widgets + EventLoopHelper crash in offscreen mode"
)

# Module-level marker - tests don't use managers
pytestmark = pytest.mark.allows_registry_state(reason="Integration tests manage own lifecycle")


@pytest.fixture
def large_rom_data(tmp_path) -> str:
    """Create a large ROM file for memory testing."""
    rom_path = tmp_path / "large_test_rom.sfc"
    # Create 8MB ROM with pattern data
    rom_size = 8 * 1024 * 1024
    rom_data = bytearray(rom_size)

    # Fill with pattern data to make it realistic
    for i in range(0, rom_size, 4):
        rom_data[i : i + 4] = (i // 4).to_bytes(4, "little")

    rom_path.write_bytes(rom_data)
    return str(rom_path)


@pytest.fixture
def massive_sprite_dataset() -> list[dict[str, Any]]:
    """Create a massive sprite dataset for memory testing."""
    return [
        {
            "offset": 0x10000 + i * 0x800,
            "name": f"MassiveSprite_{i:05d}",
            "decompressed_size": 1024 + (i % 500),
            "tile_count": 32 + (i % 64),
            "compressed": i % 3 == 0,
            "quality": 0.5 + (i % 100) / 200.0,
        }
        for i in range(5000)  # 5000 sprites
    ]


@pytest.fixture
def mock_settings_manager():
    """Create mock settings manager for DetachedGalleryWindow."""
    manager = Mock()
    manager.get.return_value = ""
    manager.set.return_value = None
    manager.set_last_used_directory.return_value = None
    return manager


@pytest.fixture
def mock_rom_cache():
    """Create mock ROM cache for DetachedGalleryWindow."""
    cache = Mock()
    cache.get_cached_sprite.return_value = None
    cache.cache_sprite.return_value = None
    return cache


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.usefixtures("session_app_context")
@pytest.mark.shared_state_safe
class TestMemoryManagementIntegration(QtTestCase):
    """Integration tests for memory management using real components."""

    def test_weak_references_prevent_leaks(self, massive_sprite_dataset):
        """Test that weak references prevent memory leaks."""

        # Use a class wrapper since plain dicts can't have weak references
        class SpriteData:
            """Wrapper class that supports weak references."""

            __slots__ = ("data", "__weakref__")  # __weakref__ enables weak refs with __slots__

            def __init__(self, data: dict):
                self.data = data

            @property
            def offset(self):
                return self.data["offset"]

        class SpriteRegistry:
            def __init__(self):
                self.sprite_refs: dict[int, weakref.ref] = {}
                self.strong_refs: dict[int, SpriteData] = {}  # For comparison

            def register_sprite_weak(self, sprite_data: SpriteData):
                offset = sprite_data.offset
                self.sprite_refs[offset] = weakref.ref(sprite_data)

            def register_sprite_strong(self, sprite_data: SpriteData):
                offset = sprite_data.offset
                self.strong_refs[offset] = sprite_data

            def get_live_weak_count(self) -> int:
                return len([ref for ref in self.sprite_refs.values() if ref() is not None])

            def get_strong_count(self) -> int:
                return len(self.strong_refs)

        registry = SpriteRegistry()

        # Register sprites with weak references (wrapped in SpriteData)
        for sprite in massive_sprite_dataset[:1000]:
            sprite_obj = SpriteData(sprite.copy())  # Create wrapped copy for weak ref test
            registry.register_sprite_weak(sprite_obj)

        # Register same sprites with strong references
        for sprite in massive_sprite_dataset[:1000]:
            registry.register_sprite_strong(SpriteData(sprite.copy()))

        # Force garbage collection
        gc.collect()

        # Weak references should allow garbage collection
        live_weak_count = registry.get_live_weak_count()
        strong_count = registry.get_strong_count()

        # Weak refs should have fewer live objects (some garbage collected)
        # Strong refs should keep all objects alive
        assert live_weak_count <= strong_count
        assert strong_count == 1000  # All strong refs alive

    @skip_in_offscreen
    def test_component_cleanup_releases_memory(
        self,
        massive_sprite_dataset,
        mock_settings_manager,
        mock_rom_cache,
    ):
        """Test that component cleanup releases memory using real DetachedGalleryWindow."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        initial_widget_count = MemoryHelper.get_widget_count()

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        with MemoryHelper.assert_no_leak(DetachedGalleryWindow, max_increase=1):
            window = DetachedGalleryWindow(
                extraction_manager=mock_manager,
                settings_manager=mock_settings_manager,
                rom_cache=mock_rom_cache,
            )

            # Load massive sprite dataset
            window.set_sprites(massive_sprite_dataset)

            # Process UI updates
            EventLoopHelper.process_events(100)

            # Close and cleanup
            window.close()

        # Widget count should return to baseline
        final_widget_count = MemoryHelper.get_widget_count()
        widget_increase = final_widget_count - initial_widget_count

        assert widget_increase <= 2, f"Widget count increased by {widget_increase}"

    @skip_in_offscreen
    def test_large_rom_data_cleanup(self, large_rom_data):
        """Test cleanup of large ROM data using real BatchThumbnailWorker."""
        import os

        # Monitor memory before loading ROM
        import psutil

        from ui.workers.batch_thumbnail_worker import BatchThumbnailWorker

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        mock_rom_extractor = MagicMock()
        with patch("ui.workers.batch_thumbnail_worker.TileRenderer"):
            worker = BatchThumbnailWorker(large_rom_data, mock_rom_extractor)

            # Start worker to load ROM data
            worker.start()
            EventLoopHelper.process_events(100)

            # Check memory increase
            peak_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = peak_memory - initial_memory

            # Should have loaded ROM data (8MB+)
            assert memory_increase >= 5  # At least 5MB increase

            # Clean up worker
            worker.cleanup()

            # Force garbage collection
            gc.collect()
            EventLoopHelper.process_events(100)
            gc.collect()

            # Memory should be released
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_after_cleanup = final_memory - initial_memory

            # Should have released most memory
            cleanup_ratio = memory_after_cleanup / memory_increase if memory_increase > 0 else 0
            assert cleanup_ratio < 0.3, f"Only {(1 - cleanup_ratio) * 100:.1f}% of memory was cleaned up"

    @skip_in_offscreen
    def test_pixmap_memory_management(self):
        """Test QPixmap memory management in caches."""
        # Create many large pixmaps
        pixmaps = []
        pixmap_refs = []

        for i in range(100):
            # Using ThreadSafeTestImage instead of QPixmap for thread safety

            pixmap = ThreadSafeTestImage(512, 512)
            pixmap.fill()
            pixmaps.append(pixmap)
            pixmap_refs.append(weakref.ref(pixmap))

        # All pixmaps should be alive
        live_count = len([ref for ref in pixmap_refs if ref() is not None])
        assert live_count == 100

        # Clear strong references
        pixmaps.clear()

        # Force garbage collection
        gc.collect()
        EventLoopHelper.process_events(100)
        gc.collect()

        # Most pixmaps should be garbage collected
        live_count_after = len([ref for ref in pixmap_refs if ref() is not None])
        assert live_count_after < live_count * 0.1, "Pixmaps were not properly garbage collected"

    @skip_in_offscreen
    @pytest.mark.slow
    def test_memory_stress_with_repeated_operations(
        self,
        large_rom_data,
        massive_sprite_dataset,
        mock_settings_manager,
        mock_rom_cache,
    ):
        """Stress test memory management with repeated operations using real components."""
        import os

        import psutil

        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        peak_memory = initial_memory

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        # Perform many operations that could leak memory
        for cycle in range(10):
            # Create window
            window = DetachedGalleryWindow(
                extraction_manager=mock_manager,
                settings_manager=mock_settings_manager,
                rom_cache=mock_rom_cache,
            )
            window._set_rom_file(large_rom_data)

            # Load large sprite set
            batch_size = 500
            start_idx = (cycle * batch_size) % len(massive_sprite_dataset)
            end_idx = start_idx + batch_size
            sprite_batch = massive_sprite_dataset[start_idx:end_idx]

            window.set_sprites(sprite_batch)
            EventLoopHelper.process_events(50)

            # Check memory
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            peak_memory = max(peak_memory, current_memory)

            # Clean up window
            window.close()

            # Force cleanup
            gc.collect()
            EventLoopHelper.process_events(50)

        # Final cleanup
        gc.collect()
        EventLoopHelper.process_events(100)
        gc.collect()

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        total_increase = final_memory - initial_memory
        peak_increase = peak_memory - initial_memory

        # Memory growth should be reasonable
        assert total_increase < 100, f"Total memory increase: {total_increase:.1f} MB"
        assert peak_increase < 200, f"Peak memory increase: {peak_increase:.1f} MB"

    def test_circular_reference_prevention(self):
        """Test prevention of circular references that could cause leaks."""

        class Parent:
            def __init__(self, name):
                self.name = name
                self.children: list[Child] = []

            def add_child(self, child):
                child.parent = self  # Potential circular reference
                self.children.append(child)

        class Child:
            def __init__(self, name):
                self.name = name
                self.parent = None

        class SafeParent:
            def __init__(self, name):
                self.name = name
                self.children: list[Child] = []

            def add_child(self, child):
                child.parent = weakref.ref(self)  # Use weak reference
                self.children.append(child)

        # Test circular references (will leak)
        parent_refs = []
        for i in range(10):
            parent = Parent(f"parent_{i}")
            parent_refs.append(weakref.ref(parent))

            for j in range(5):
                child = Child(f"child_{i}_{j}")
                parent.add_child(child)

        # Clear strong references
        del parent  # Only last parent reference

        gc.collect()

        # Many parents may still be alive due to circular references
        circular_live_count = len([ref for ref in parent_refs if ref() is not None])

        # Test safe references (should not leak)
        safe_parent_refs = []
        for i in range(10):
            parent = SafeParent(f"safe_parent_{i}")
            safe_parent_refs.append(weakref.ref(parent))

            for j in range(5):
                child = Child(f"safe_child_{i}_{j}")
                parent.add_child(child)

        # Clear strong references
        del parent  # Only last parent reference

        gc.collect()

        # Safe parents should be garbage collected
        safe_live_count = len([ref for ref in safe_parent_refs if ref() is not None])

        # Safe implementation should have fewer live objects
        assert safe_live_count <= circular_live_count
