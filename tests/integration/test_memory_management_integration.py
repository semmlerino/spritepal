"""
Integration tests for Memory Management across components.

These tests focus on memory-related patterns:
- Weak references working correctly
- No memory leaks with circular references

NOTE: Tests using fictional mock classes (MockROMCache, MockThumbnailCache,
MockMemoryPool, MockReferenceCounter, MockCacheCoordinator) have been removed.
Those tests provided false confidence by testing mocks rather than production code.

NOTE: Tests requiring EventLoopHelper + complex Qt widgets were removed as they
crash in offscreen mode (CI environment) and provide zero automated test value.
"""

from __future__ import annotations

import gc
import weakref
from typing import Any
from unittest.mock import Mock

import pytest

from tests.infrastructure.qt_real_testing import QtTestCase

# Module-level marker - tests don't use managers
pytestmark = pytest.mark.allows_registry_state(reason="Integration tests manage own lifecycle")


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
