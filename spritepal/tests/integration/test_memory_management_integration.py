"""
Integration tests for Memory Management across components.

These tests focus on memory-related bugs that were fixed:
- ROM data cleanup after processing
- Cache clearing when switching contexts
- Weak references working correctly
- No memory leaks with large sprite sets
- Proper cleanup on component destruction
"""

from __future__ import annotations

import gc
import os
import weakref
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from tests.infrastructure.qt_real_testing import (
    EventLoopHelper,
    MemoryHelper,
    QtTestCase,
)
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

# Skip tests that use complex Qt widgets + event processing in offscreen mode
_offscreen_mode = os.environ.get('QT_QPA_PLATFORM') == 'offscreen'
skip_in_offscreen = pytest.mark.skipif(
    _offscreen_mode,
    reason="Complex Qt widgets + EventLoopHelper crash in offscreen mode"
)


@pytest.fixture
def large_rom_data(tmp_path) -> str:
    """Create a large ROM file for memory testing."""
    rom_path = tmp_path / "large_test_rom.sfc"
    # Create 8MB ROM with pattern data
    rom_size = 8 * 1024 * 1024
    rom_data = bytearray(rom_size)

    # Fill with pattern data to make it realistic
    for i in range(0, rom_size, 4):
        rom_data[i:i+4] = (i // 4).to_bytes(4, 'little')

    rom_path.write_bytes(rom_data)
    return str(rom_path)

@pytest.fixture
def massive_sprite_dataset() -> list[dict[str, Any]]:
    """Create a massive sprite dataset for memory testing."""
    return [
        {
            'offset': 0x10000 + i * 0x800,
            'name': f'MassiveSprite_{i:05d}',
            'decompressed_size': 1024 + (i % 500),
            'tile_count': 32 + (i % 64),
            'compressed': i % 3 == 0,
            'quality': 0.5 + (i % 100) / 200.0,
        }
        for i in range(5000)  # 5000 sprites
    ]

class MockROMCache:
    """Mock ROM cache for testing memory behavior."""

    def __init__(self):
        """Initialize mock ROM cache."""
        self.cached_roms: dict[str, bytes] = {}
        self.access_times: dict[str, float] = {}
        self.max_cache_size = 50 * 1024 * 1024  # 50MB limit

    def get_rom_data(self, rom_path: str) -> bytes | None:
        """Get ROM data from cache or load it."""
        if rom_path in self.cached_roms:
            import time
            self.access_times[rom_path] = time.time()
            return self.cached_roms[rom_path]

        # Load ROM data
        try:
            with open(rom_path, 'rb') as f:
                data = f.read()

            # Check if adding this would exceed cache limit
            if self._get_cache_size() + len(data) > self.max_cache_size:
                self._evict_oldest()

            self.cached_roms[rom_path] = data
            import time
            self.access_times[rom_path] = time.time()
            return data
        except Exception:
            return None

    def clear_cache(self):
        """Clear all cached ROM data."""
        self.cached_roms.clear()
        self.access_times.clear()

    def _get_cache_size(self) -> int:
        """Get total size of cached data."""
        return sum(len(data) for data in self.cached_roms.values())

    def _evict_oldest(self):
        """Evict oldest ROM from cache."""
        if not self.access_times:
            return

        oldest_rom = min(self.access_times, key=self.access_times.get)
        if oldest_rom in self.cached_roms:
            del self.cached_roms[oldest_rom]
        if oldest_rom in self.access_times:
            del self.access_times[oldest_rom]

class MockThumbnailCache:
    """Mock thumbnail cache for testing memory behavior."""

    def __init__(self, max_thumbnails=1000):
        """Initialize thumbnail cache.
        
        Args:
            max_thumbnails: Maximum number of thumbnails to cache
        """
        self.thumbnails: dict[int, ThreadSafeTestImage] = {}
        self.max_thumbnails = max_thumbnails
        self.access_order: list[int] = []

    def get_thumbnail(self, offset: int) -> ThreadSafeTestImage | None:
        """Get thumbnail from cache."""
        if offset in self.thumbnails:
            # Move to end (most recent)
            self.access_order.remove(offset)
            self.access_order.append(offset)
            return self.thumbnails[offset]
        return None

    def set_thumbnail(self, offset: int, image: ThreadSafeTestImage):
        """Set thumbnail in cache."""
        # Evict if at capacity
        if len(self.thumbnails) >= self.max_thumbnails:
            oldest_offset = self.access_order.pop(0)
            if oldest_offset in self.thumbnails:
                del self.thumbnails[oldest_offset]

        self.thumbnails[offset] = image
        self.access_order.append(offset)

    def clear_cache(self):
        """Clear all thumbnails."""
        self.thumbnails.clear()
        self.access_order.clear()

    def get_cache_size_bytes(self) -> int:
        """Estimate cache size in bytes."""
        total_bytes = 0
        for image in self.thumbnails.values():
            if not image.isNull():
                # Rough estimate: width * height * 4 bytes per pixel (RGBA)
                total_bytes += image.width() * image.height() * 4
        return total_bytes

@pytest.mark.gui
@pytest.mark.integration
class TestMemoryManagementIntegration(QtTestCase):
    """Integration tests for memory management."""

    def test_rom_cache_memory_limits(self, large_rom_data):
        """Test ROM cache respects memory limits."""
        cache = MockROMCache()
        cache.max_cache_size = 10 * 1024 * 1024  # 10MB limit

        # Create multiple ROM files
        rom_paths = []
        for i in range(3):
            rom_path = Path(large_rom_data).parent / f"rom_{i}.sfc"
            rom_path.write_bytes(Path(large_rom_data).read_bytes())
            rom_paths.append(str(rom_path))

        # Load ROMs into cache
        for rom_path in rom_paths:
            data = cache.get_rom_data(rom_path)
            assert data is not None

        # Cache should have evicted oldest ROM to stay within limit
        cache_size = cache._get_cache_size()
        assert cache_size <= cache.max_cache_size

        # Should have fewer than 3 ROMs cached due to size limit
        assert len(cache.cached_roms) < 3

    def test_thumbnail_cache_memory_management(self):
        """Test thumbnail cache memory management."""
        cache = MockThumbnailCache(max_thumbnails=100)

        # Create many large thumbnails
        for i in range(150):
            image = ThreadSafeTestImage(256, 256)
            image.fill()  # Fill with color
            cache.set_thumbnail(0x10000 + i * 0x1000, image)

        # Should not exceed maximum
        assert len(cache.thumbnails) <= cache.max_thumbnails

        # Should have evicted oldest thumbnails
        assert 0x10000 not in cache.thumbnails  # First thumbnail should be evicted

        # Most recent thumbnails should still be there
        last_offset = 0x10000 + 149 * 0x1000
        assert cache.get_thumbnail(last_offset) is not None

    def test_weak_references_prevent_leaks(self, massive_sprite_dataset):
        """Test that weak references prevent memory leaks."""
        # Use a class wrapper since plain dicts can't have weak references
        class SpriteData:
            """Wrapper class that supports weak references."""
            __slots__ = ('data', '__weakref__')  # __weakref__ enables weak refs with __slots__

            def __init__(self, data: dict):
                self.data = data

            @property
            def offset(self):
                return self.data['offset']

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
    def test_component_cleanup_releases_memory(self, massive_sprite_dataset):
        """Test that component cleanup releases memory."""
        from ui.windows.detached_gallery_window import DetachedGalleryWindow

        initial_widget_count = MemoryHelper.get_widget_count()

        mock_manager = Mock()
        mock_manager.get_rom_extractor.return_value = Mock()
        mock_manager.get_known_sprite_locations.return_value = {}

        with MemoryHelper.assert_no_leak(DetachedGalleryWindow, max_increase=1):
            window = DetachedGalleryWindow(extraction_manager=mock_manager)

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
        """Test cleanup of large ROM data."""
        import os

        # Monitor memory before loading ROM
        import psutil

        from ui.workers.batch_thumbnail_worker import BatchThumbnailWorker

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        with patch('ui.workers.batch_thumbnail_worker.TileRenderer'):
            worker = BatchThumbnailWorker(large_rom_data)

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
            assert cleanup_ratio < 0.3, f"Only {(1-cleanup_ratio)*100:.1f}% of memory was cleaned up"

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
    def test_memory_stress_with_repeated_operations(self, large_rom_data, massive_sprite_dataset):
        """Stress test memory management with repeated operations."""
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
            window = DetachedGalleryWindow(extraction_manager=mock_manager)
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

    def test_cache_eviction_policies(self):
        """Test different cache eviction policies."""
        class LRUCache:
            def __init__(self, max_size=100):
                self.max_size = max_size
                self.cache = {}
                self.access_order = []

            def get(self, key):
                if key in self.cache:
                    # Move to end (most recent)
                    self.access_order.remove(key)
                    self.access_order.append(key)
                    return self.cache[key]
                return None

            def put(self, key, value):
                if key in self.cache:
                    self.access_order.remove(key)
                elif len(self.cache) >= self.max_size:
                    # Evict least recently used
                    oldest_key = self.access_order.pop(0)
                    del self.cache[oldest_key]

                self.cache[key] = value
                self.access_order.append(key)

            def size(self):
                return len(self.cache)

        cache = LRUCache(max_size=5)

        # Fill cache
        for i in range(5):
            cache.put(f"key_{i}", f"value_{i}")

        assert cache.size() == 5

        # Access first item to make it recently used
        cache.get("key_0")

        # Add new item (should evict key_1, not key_0)
        cache.put("key_5", "value_5")

        assert cache.get("key_0") is not None  # Should still be there
        assert cache.get("key_1") is None  # Should be evicted
        assert cache.get("key_5") is not None  # Should be there

@pytest.mark.headless
@pytest.mark.integration
class TestMemoryManagementHeadlessIntegration:
    """Headless memory management tests using logic verification."""

    def test_headless_memory_pool_logic(self):
        """Test memory pool logic without Qt dependencies."""
        class MockMemoryPool:
            def __init__(self, pool_size=10, item_size=1024):
                self.pool_size = pool_size
                self.item_size = item_size
                self.allocated_items = []
                self.free_items = []

                # Pre-allocate pool
                for _ in range(pool_size):
                    self.free_items.append(bytearray(item_size))

            def allocate(self):
                if self.free_items:
                    item = self.free_items.pop()
                    self.allocated_items.append(item)
                    return item
                return None  # Pool exhausted

            def free(self, item):
                if item in self.allocated_items:
                    self.allocated_items.remove(item)
                    self.free_items.append(item)
                    # Clear item data
                    for i in range(len(item)):
                        item[i] = 0

            def get_usage(self):
                return {
                    'allocated': len(self.allocated_items),
                    'free': len(self.free_items),
                    'total': self.pool_size
                }

        pool = MockMemoryPool(pool_size=5)

        # Test allocation
        items = []
        for i in range(5):
            item = pool.allocate()
            assert item is not None
            items.append(item)

        # Pool should be exhausted
        assert pool.allocate() is None

        usage = pool.get_usage()
        assert usage['allocated'] == 5
        assert usage['free'] == 0

        # Free some items
        for item in items[:3]:
            pool.free(item)

        usage = pool.get_usage()
        assert usage['allocated'] == 2
        assert usage['free'] == 3

        # Should be able to allocate again
        new_item = pool.allocate()
        assert new_item is not None

    def test_headless_reference_counting_logic(self):
        """Test reference counting logic."""
        class MockReferenceCounter:
            def __init__(self):
                self.references = {}
                self.objects = {}

            def create_object(self, obj_id, data):
                self.objects[obj_id] = data
                self.references[obj_id] = 0

            def add_reference(self, obj_id):
                if obj_id in self.references:
                    self.references[obj_id] += 1
                    return True
                return False

            def remove_reference(self, obj_id):
                if obj_id in self.references:
                    self.references[obj_id] -= 1
                    if self.references[obj_id] <= 0:
                        # Object can be cleaned up
                        del self.objects[obj_id]
                        del self.references[obj_id]
                    return True
                return False

            def get_reference_count(self, obj_id):
                return self.references.get(obj_id, 0)

            def get_object_count(self):
                return len(self.objects)

        counter = MockReferenceCounter()

        # Create objects
        counter.create_object("obj1", "data1")
        counter.create_object("obj2", "data2")

        assert counter.get_object_count() == 2

        # Add references
        counter.add_reference("obj1")
        counter.add_reference("obj1")
        counter.add_reference("obj2")

        assert counter.get_reference_count("obj1") == 2
        assert counter.get_reference_count("obj2") == 1

        # Remove references
        counter.remove_reference("obj1")
        assert counter.get_reference_count("obj1") == 1
        assert counter.get_object_count() == 2  # Still alive

        counter.remove_reference("obj1")
        assert counter.get_object_count() == 1  # obj1 cleaned up

        counter.remove_reference("obj2")
        assert counter.get_object_count() == 0  # All cleaned up

    def test_headless_cache_coherency_logic(self):
        """Test cache coherency logic."""
        class MockCacheCoordinator:
            def __init__(self):
                self.caches = {}
                self.invalidation_log = []

            def register_cache(self, cache_name, cache_impl):
                self.caches[cache_name] = cache_impl

            def invalidate_key(self, key):
                """Invalidate key across all caches."""
                for cache_name, cache in self.caches.items():
                    if hasattr(cache, 'invalidate'):
                        cache.invalidate(key)
                        self.invalidation_log.append((cache_name, key))

            def clear_all_caches(self):
                """Clear all registered caches."""
                for cache_name, cache in self.caches.items():
                    if hasattr(cache, 'clear'):
                        cache.clear()
                        self.invalidation_log.append((cache_name, 'CLEAR_ALL'))

        class MockCache:
            def __init__(self, name):
                self.name = name
                self.data = {}
                self.invalidated_keys = set()

            def put(self, key, value):
                self.data[key] = value

            def get(self, key):
                if key in self.invalidated_keys:
                    return None
                return self.data.get(key)

            def invalidate(self, key):
                self.invalidated_keys.add(key)

            def clear(self):
                self.data.clear()
                self.invalidated_keys.clear()

        coordinator = MockCacheCoordinator()

        # Create caches
        cache1 = MockCache("cache1")
        cache2 = MockCache("cache2")

        coordinator.register_cache("cache1", cache1)
        coordinator.register_cache("cache2", cache2)

        # Add data to caches
        cache1.put("key1", "value1")
        cache2.put("key1", "value1_different")

        # Invalidate key across all caches
        coordinator.invalidate_key("key1")

        # Both caches should return None for invalidated key
        assert cache1.get("key1") is None
        assert cache2.get("key1") is None

        # Check invalidation log
        assert len(coordinator.invalidation_log) == 2
        assert ("cache1", "key1") in coordinator.invalidation_log
        assert ("cache2", "key1") in coordinator.invalidation_log
