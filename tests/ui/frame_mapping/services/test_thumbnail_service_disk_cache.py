"""Integration tests for disk cache integration with thumbnail service.

Tests verify that ThumbnailDiskCache is properly integrated with
create_quantized_thumbnail and AsyncThumbnailLoader for performance optimization.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image
from PySide6.QtCore import QObject
from pytestqt.qtbot import QtBot

from core.frame_mapping_project import SheetPalette
from ui.frame_mapping.services.thumbnail_service import (
    AsyncThumbnailLoader,
    clear_all_thumbnail_caches,
    create_quantized_thumbnail,
    get_disk_cache,
)

if TYPE_CHECKING:
    from core.app_context import AppContext


def _create_test_image(tmp_path: Path, name: str, color: tuple[int, int, int, int]) -> Path:
    """Create a test image file.

    Args:
        tmp_path: Temporary directory
        name: Image filename (e.g., "test.png")
        color: RGBA color tuple

    Returns:
        Path to created image
    """
    image_path = tmp_path / name
    img = Image.new("RGBA", (64, 64), color)
    img.save(image_path)
    return image_path


def _create_test_palette(
    colors: list[tuple[int, int, int]] | None = None,
    mappings: dict[tuple[int, int, int], int] | None = None,
    background_color: tuple[int, int, int] | None = None,
    background_tolerance: int = 30,
) -> SheetPalette:
    """Create a test SheetPalette.

    Args:
        colors: List of 16 RGB colors (defaults to grayscale gradient)
        mappings: Color mappings dict (defaults to empty)
        background_color: Background color for removal (defaults to None)
        background_tolerance: Tolerance for background removal (defaults to 30)

    Returns:
        SheetPalette instance
    """
    if colors is None:
        # Create a grayscale gradient palette (16 colors)
        colors = [(i * 17, i * 17, i * 17) for i in range(16)]

    if mappings is None:
        mappings = {}

    return SheetPalette(
        colors=colors,
        color_mappings=mappings,
        background_color=background_color,
        background_tolerance=background_tolerance,
    )


class TestDiskCacheIntegrationHit:
    """Test disk cache accelerates repeated thumbnail loads."""

    def test_disk_cache_hit_after_memory_clear(self, tmp_path: Path, app_context: AppContext) -> None:
        """Verify disk cache accelerates repeated thumbnail loads."""
        # Create test image
        image_path = _create_test_image(tmp_path, "test.png", (255, 0, 0, 255))

        # Create dummy SheetPalette
        palette = _create_test_palette()

        # Load thumbnail (cache miss) - goes to disk
        thumb1 = create_quantized_thumbnail(image_path, palette)
        assert thumb1 is not None

        # Verify disk cache has entry
        stats_before = get_disk_cache().get_stats()
        assert stats_before["entries"] >= 1

        # Clear in-memory caches (but not disk)
        from ui.frame_mapping.services.thumbnail_service import _cached_quantized_thumbnail_bytes, _pixmap_cache

        _cached_quantized_thumbnail_bytes.cache_clear()
        _pixmap_cache.clear()

        # Load same thumbnail (disk cache hit)
        thumb2 = create_quantized_thumbnail(image_path, palette)
        assert thumb2 is not None

        # Verify thumbnails are identical
        assert thumb1.size() == thumb2.size()

        # Verify disk cache still has entries
        stats_after = get_disk_cache().get_stats()
        assert stats_after["entries"] >= 1


class TestDiskCacheInvalidationOnPaletteChange:
    """Test palette changes create new cache entries."""

    def test_palette_change_creates_new_entry(self, tmp_path: Path, app_context: AppContext) -> None:
        """Verify palette changes create new cache entries."""
        # Create test image
        image_path = _create_test_image(tmp_path, "test.png", (128, 128, 128, 255))

        # Create palette A (grayscale)
        palette_a = _create_test_palette(colors=[(i * 17, i * 17, i * 17) for i in range(16)])

        # Generate thumbnail with palette A
        clear_all_thumbnail_caches()  # Start fresh
        thumb1 = create_quantized_thumbnail(image_path, palette_a)
        assert thumb1 is not None

        # Get disk cache stats
        stats1 = get_disk_cache().get_stats()
        entries1 = stats1["entries"]

        # Create palette B (different colors - reddish tint)
        palette_b = _create_test_palette(colors=[(i * 17 + 10, i * 17, i * 17) for i in range(16)])

        # Generate thumbnail with palette B
        thumb2 = create_quantized_thumbnail(image_path, palette_b)
        assert thumb2 is not None

        # Get disk cache stats - verify 2 entries (new cache key)
        stats2 = get_disk_cache().get_stats()
        entries2 = stats2["entries"]
        assert entries2 >= entries1 + 1, f"Expected at least {entries1 + 1} entries, got {entries2}"


class TestDiskCacheInvalidationOnMtimeChange:
    """Test file modifications invalidate cache."""

    def test_mtime_change_creates_new_entry(self, tmp_path: Path, app_context: AppContext) -> None:
        """Verify file modifications invalidate cache."""
        # Create test image
        image_path = _create_test_image(tmp_path, "test.png", (0, 255, 0, 255))
        palette = _create_test_palette()

        # Generate thumbnail
        clear_all_thumbnail_caches()  # Start fresh
        thumb1 = create_quantized_thumbnail(image_path, palette)
        assert thumb1 is not None

        # Verify cache entry created
        stats1 = get_disk_cache().get_stats()
        entries1 = stats1["entries"]
        assert entries1 >= 1

        # Wait briefly to ensure mtime changes
        time.sleep(0.1)

        # Modify image file (change color)
        modified_img = Image.new("RGBA", (64, 64), (0, 128, 255, 255))
        modified_img.save(image_path)

        # Ensure mtime changed
        time.sleep(0.1)

        # Clear in-memory caches to force disk lookup
        from ui.frame_mapping.services.thumbnail_service import _cached_quantized_thumbnail_bytes, _pixmap_cache

        _cached_quantized_thumbnail_bytes.cache_clear()
        _pixmap_cache.clear()

        # Generate thumbnail again
        thumb2 = create_quantized_thumbnail(image_path, palette)
        assert thumb2 is not None

        # Verify cache entry count increased (old entry still present, new entry added)
        stats2 = get_disk_cache().get_stats()
        entries2 = stats2["entries"]
        assert entries2 >= entries1 + 1, f"Expected at least {entries1 + 1} entries after mtime change, got {entries2}"


class TestAsyncLoaderUsesDiskCache:
    """Test AsyncThumbnailLoader integrates with disk cache."""

    def test_async_loader_populates_disk_cache(
        self, tmp_path: Path, app_context: AppContext, qtbot: QtBot
    ) -> None:
        """Verify AsyncThumbnailLoader populates disk cache.

        The async worker thread uses the disk cache for both reading and writing,
        enabling faster loads on subsequent application starts.
        """
        # Create multiple test images
        images = [_create_test_image(tmp_path, f"frame_{i}.png", (i * 30, 0, 0, 255)) for i in range(3)]

        palette = _create_test_palette()

        # Clear all caches to start fresh
        clear_all_thumbnail_caches()

        # Verify disk cache is empty
        stats_before = get_disk_cache().get_stats()
        assert stats_before["entries"] == 0

        # Create loader with a QObject parent to avoid GC issues
        parent = QObject()
        loader = AsyncThumbnailLoader(parent)

        # Track received thumbnails
        received_thumbnails: dict[str, bool] = {}

        def on_thumbnail_ready(frame_id: str, pixmap: object) -> None:
            received_thumbnails[frame_id] = True

        loader.thumbnail_ready.connect(on_thumbnail_ready)

        # Load thumbnails via AsyncThumbnailLoader
        requests = [(f"frame_{i}", images[i]) for i in range(len(images))]

        # Set up signal waiter BEFORE calling load_thumbnails to avoid race condition
        with qtbot.waitSignal(loader.finished, timeout=5000):
            loader.load_thumbnails(requests, palette)

        # Verify all thumbnails received
        assert len(received_thumbnails) == len(images)

        # Verify disk cache now has entries (async loader populates it)
        stats_after = get_disk_cache().get_stats()
        assert stats_after["entries"] == len(images), (
            f"Expected {len(images)} disk cache entries, got {stats_after['entries']}"
        )

        # Clean up loader
        loader.cancel()
        loader.deleteLater()
        parent.deleteLater()

    def test_async_loader_uses_in_memory_cache(self, tmp_path: Path, app_context: AppContext, qtbot: QtBot) -> None:
        """Verify AsyncThumbnailLoader checks in-memory pixmap cache.

        AsyncThumbnailLoader checks the in-memory _pixmap_cache before spawning
        worker threads. Cache hits emit immediately without background work.
        """
        # Create test images
        images = [_create_test_image(tmp_path, f"img_{i}.png", (0, i * 50, 0, 255)) for i in range(2)]

        palette = _create_test_palette()

        # Clear all caches
        clear_all_thumbnail_caches()

        # First load - populate in-memory cache
        parent1 = QObject()
        loader1 = AsyncThumbnailLoader(parent1)
        requests = [(f"img_{i}", images[i]) for i in range(len(images))]

        with qtbot.waitSignal(loader1.finished, timeout=5000):
            loader1.load_thumbnails(requests, palette)

        # Clean up first loader
        loader1.cancel()
        loader1.deleteLater()
        parent1.deleteLater()

        # In-memory pixmap cache should be populated
        # (AsyncThumbnailLoader populates _pixmap_cache on thumbnail_ready)

        # Second load - should hit in-memory pixmap cache and emit immediately
        parent2 = QObject()
        loader2 = AsyncThumbnailLoader(parent2)
        received_count = 0

        def on_thumb_ready(_frame_id: str, _pixmap: object) -> None:
            nonlocal received_count
            received_count += 1

        loader2.thumbnail_ready.connect(on_thumb_ready)

        with qtbot.waitSignal(loader2.finished, timeout=5000):
            loader2.load_thumbnails(requests, palette)

        # Verify thumbnails loaded (from in-memory cache)
        assert received_count == len(images)

        # Clean up second loader
        loader2.cancel()
        loader2.deleteLater()
        parent2.deleteLater()


class TestClearAllCachesIncludesDisk:
    """Test clear_all_thumbnail_caches clears disk cache."""

    def test_clear_all_includes_disk(self, tmp_path: Path, app_context: AppContext) -> None:
        """Verify clear_all_thumbnail_caches() clears disk cache."""
        # Create test image
        image_path = _create_test_image(tmp_path, "clear_test.png", (100, 100, 200, 255))
        palette = _create_test_palette()

        # Generate thumbnail
        clear_all_thumbnail_caches()  # Start fresh
        thumb = create_quantized_thumbnail(image_path, palette)
        assert thumb is not None

        # Verify disk cache has entries
        stats_before = get_disk_cache().get_stats()
        assert stats_before["entries"] >= 1

        # Call clear_all_thumbnail_caches()
        clear_all_thumbnail_caches()

        # Verify disk cache empty
        stats_after = get_disk_cache().get_stats()
        assert stats_after["entries"] == 0, f"Expected 0 entries after clear, got {stats_after['entries']}"
        assert stats_after["total_size"] == 0, f"Expected 0 bytes after clear, got {stats_after['total_size']}"


class TestBackgroundRemovalIntegration:
    """Test disk cache handles background removal settings."""

    def test_background_color_creates_separate_entry(self, tmp_path: Path, app_context: AppContext) -> None:
        """Verify background removal settings affect cache key."""
        # Create test image with mixed colors (not pure white)
        # Use a non-solid image to ensure background removal has visible effect
        img = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
        # Add a red square in the middle that won't be removed
        for x in range(20, 44):
            for y in range(20, 44):
                img.putpixel((x, y), (255, 0, 0, 255))
        image_path = tmp_path / "bg_test.png"
        img.save(image_path)

        # Create palette without background removal
        palette_no_bg = _create_test_palette(background_color=None)

        # Generate thumbnail without background removal
        clear_all_thumbnail_caches()
        thumb1 = create_quantized_thumbnail(image_path, palette_no_bg)
        assert thumb1 is not None

        stats1 = get_disk_cache().get_stats()
        entries1 = stats1["entries"]
        assert entries1 >= 1

        # Clear in-memory caches to force disk cache path
        from ui.frame_mapping.services.thumbnail_service import _cached_quantized_thumbnail_bytes, _pixmap_cache

        _cached_quantized_thumbnail_bytes.cache_clear()
        _pixmap_cache.clear()

        # Create palette with background removal
        palette_with_bg = _create_test_palette(
            background_color=(255, 255, 255),
            background_tolerance=30,
        )

        # Generate thumbnail with background removal
        thumb2 = create_quantized_thumbnail(image_path, palette_with_bg)
        assert thumb2 is not None

        # Verify separate cache entry created
        stats2 = get_disk_cache().get_stats()
        entries2 = stats2["entries"]
        assert entries2 >= entries1 + 1, f"Expected at least {entries1 + 1} entries, got {entries2}"

    def test_background_tolerance_creates_separate_entry(self, tmp_path: Path, app_context: AppContext) -> None:
        """Verify background tolerance changes affect cache key."""
        # Create test image
        image_path = _create_test_image(tmp_path, "tolerance_test.png", (200, 200, 200, 255))

        # Create palette with tolerance=10
        palette_tol10 = _create_test_palette(
            background_color=(200, 200, 200),
            background_tolerance=10,
        )

        # Generate thumbnail
        clear_all_thumbnail_caches()
        thumb1 = create_quantized_thumbnail(image_path, palette_tol10)
        assert thumb1 is not None

        stats1 = get_disk_cache().get_stats()
        entries1 = stats1["entries"]
        assert entries1 >= 1

        # Clear in-memory caches to force disk cache path
        from ui.frame_mapping.services.thumbnail_service import _cached_quantized_thumbnail_bytes, _pixmap_cache

        _cached_quantized_thumbnail_bytes.cache_clear()
        _pixmap_cache.clear()

        # Create palette with tolerance=50
        palette_tol50 = _create_test_palette(
            background_color=(200, 200, 200),
            background_tolerance=50,
        )

        # Generate thumbnail with different tolerance
        thumb2 = create_quantized_thumbnail(image_path, palette_tol50)
        assert thumb2 is not None

        # Verify separate cache entry created
        stats2 = get_disk_cache().get_stats()
        entries2 = stats2["entries"]
        assert entries2 >= entries1 + 1, f"Expected at least {entries1 + 1} entries, got {entries2}"
