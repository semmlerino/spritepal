"""Unit tests for ThumbnailDiskCache."""

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from ui.frame_mapping.services.thumbnail_disk_cache import ThumbnailDiskCache

# Minimal valid PNG header + IEND chunk (smallest valid PNG)
VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"  # PNG signature
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"  # IHDR
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"  # IDAT
    b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND
)


def create_metadata(path: str = "/test/source.png") -> dict[str, Any]:
    """Create realistic metadata structure."""
    return {
        "path": path,
        "mtime": 1234567890,
        "size": 1024,
        "palette_hash": 123456789,
    }


def test_cache_hit_returns_bytes(tmp_path: Path) -> None:
    """Verify cache returns stored PNG bytes."""
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=1)
    cache_key = "test_key"

    # Store data
    cache.put(cache_key, VALID_PNG_BYTES, create_metadata())

    # Retrieve data
    result = cache.get(cache_key)

    assert result is not None
    assert result == VALID_PNG_BYTES


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    """Verify cache returns None for missing key."""
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=1)

    result = cache.get("nonexistent_key")

    assert result is None


def test_put_stores_thumbnail_and_metadata(tmp_path: Path) -> None:
    """Verify put() writes PNG file and updates metadata."""
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=1)
    cache_key = "test_thumbnail"
    metadata = create_metadata("/source/image.png")

    # Put data
    cache.put(cache_key, VALID_PNG_BYTES, metadata)

    # Verify PNG file exists
    png_path = tmp_path / f"{cache_key}.png"
    assert png_path.exists()
    assert png_path.read_bytes() == VALID_PNG_BYTES

    # Force metadata flush
    cache._flush_metadata()

    # Verify metadata.json contains entry
    metadata_path = tmp_path / "metadata.json"
    assert metadata_path.exists()

    with open(metadata_path) as f:
        loaded_metadata = json.load(f)

    assert cache_key in loaded_metadata["entries"]
    entry = loaded_metadata["entries"][cache_key]
    assert entry["path"] == "/source/image.png"
    assert entry["mtime"] == 1234567890
    assert entry["size"] == 1024
    assert entry["palette_hash"] == 123456789
    assert entry["file_size"] == len(VALID_PNG_BYTES)

    # Verify total_size updated
    assert loaded_metadata["total_size"] == len(VALID_PNG_BYTES)


def test_eviction_removes_lru_entries(tmp_path: Path) -> None:
    """Verify LRU eviction when size limit exceeded."""
    # Create cache with small max_size (1KB = 1024 bytes)
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=1)
    cache.max_size = 1024  # Override to 1KB for testing

    # Create entries that will exceed limit
    # Make them large enough to exceed 80% threshold
    entry1_bytes = VALID_PNG_BYTES + b"\x00" * 200
    entry2_bytes = VALID_PNG_BYTES + b"\x00" * 200
    entry3_bytes = VALID_PNG_BYTES + b"\x00" * 200
    entry4_bytes = VALID_PNG_BYTES + b"\x00" * 200

    # Put entries with small delays to ensure different timestamps
    cache.put("entry1", entry1_bytes, create_metadata("/path1.png"))
    time.sleep(0.01)

    cache.put("entry2", entry2_bytes, create_metadata("/path2.png"))
    time.sleep(0.01)

    cache.put("entry3", entry3_bytes, create_metadata("/path3.png"))
    time.sleep(0.01)

    cache.put("entry4", entry4_bytes, create_metadata("/path4.png"))

    # Verify all entries exist
    assert cache.get("entry1") is not None
    assert cache.get("entry2") is not None
    assert cache.get("entry3") is not None
    assert cache.get("entry4") is not None

    # Access entry2 and entry4 to update their last_access
    time.sleep(0.01)
    cache.get("entry2")
    time.sleep(0.01)
    cache.get("entry4")

    # Check size before eviction
    stats_before = cache.get_stats()
    assert stats_before["entries"] == 4

    # Manually trigger eviction to 50% of max size to ensure some are removed
    target_size = int(cache.max_size * 0.5)
    cache.evict_lru(target_size)

    # Verify cache size is below target
    stats = cache.get_stats()
    assert stats["total_size"] <= target_size

    # Verify entry1 and entry3 (oldest, not recently accessed) were removed
    # These should be the first to go based on LRU
    entry1_result = cache.get("entry1")
    entry3_result = cache.get("entry3")

    # At least one of the non-accessed entries should be removed
    removed_count = (entry1_result is None) + (entry3_result is None)
    assert removed_count >= 1


def test_concurrent_put_get_thread_safe(tmp_path: Path) -> None:
    """Verify thread safety with concurrent workers using threading.Thread."""
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=10)
    num_threads = 10
    operations_per_thread = 20
    results: dict[int, list[bytes | None]] = {i: [] for i in range(num_threads)}
    errors: list[Exception] = []

    def worker(thread_id: int) -> None:
        """Worker thread that performs put/get operations."""
        try:
            for i in range(operations_per_thread):
                key = f"thread_{thread_id}_item_{i}"
                data = VALID_PNG_BYTES + bytes([thread_id, i])

                # Put data
                cache.put(key, data, create_metadata(f"/thread{thread_id}/item{i}.png"))

                # Get data back
                retrieved = cache.get(key)
                results[thread_id].append(retrieved)

        except Exception as e:
            errors.append(e)

    # Spawn threads
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]

    # Start all threads
    for t in threads:
        t.start()

    # Wait for completion
    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive(), f"Thread {t.name} did not complete"

    # Verify no crashes/exceptions
    assert len(errors) == 0, f"Errors occurred: {errors}"

    # Verify all operations completed
    for thread_id in range(num_threads):
        assert len(results[thread_id]) == operations_per_thread
        # Verify at least some retrievals were successful
        successful = sum(1 for r in results[thread_id] if r is not None)
        assert successful > 0

    # Verify metadata integrity
    cache._flush_metadata()
    metadata_path = tmp_path / "metadata.json"
    assert metadata_path.exists()

    with open(metadata_path) as f:
        metadata = json.load(f)

    # Verify structure is intact
    assert "entries" in metadata
    assert "total_size" in metadata
    assert isinstance(metadata["entries"], dict)
    assert isinstance(metadata["total_size"], int)


def test_metadata_corruption_recovery(tmp_path: Path) -> None:
    """Verify cache rebuilds metadata on corruption."""
    # Create cache and put some entries
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=1)
    cache.put("entry1", VALID_PNG_BYTES, create_metadata("/path1.png"))
    cache.put("entry2", VALID_PNG_BYTES + b"\x00" * 100, create_metadata("/path2.png"))
    cache._flush_metadata()

    # Corrupt metadata.json
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("{ invalid json !@#$")

    # Create new cache instance (should rebuild)
    cache2 = ThumbnailDiskCache(tmp_path, max_size_mb=1)

    # Verify cache still works
    assert not cache2._disabled

    # Verify entries were rebuilt from PNG files
    stats = cache2.get_stats()
    assert stats["entries"] == 2
    assert stats["total_size"] > 0

    # Verify we can retrieve data
    result1 = cache2.get("entry1")
    assert result1 == VALID_PNG_BYTES

    result2 = cache2.get("entry2")
    assert result2 == VALID_PNG_BYTES + b"\x00" * 100


def test_stale_entry_cleanup_on_init(tmp_path: Path) -> None:
    """Verify init removes entries for deleted source files."""
    # Create a temporary source file
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    source_file = source_dir / "exists.png"
    source_file.write_bytes(VALID_PNG_BYTES)

    # Create cache and put entries
    cache = ThumbnailDiskCache(tmp_path / "cache", max_size_mb=1)
    cache.put("valid_entry", VALID_PNG_BYTES, create_metadata(str(source_file)))
    cache.put("stale_entry", VALID_PNG_BYTES, create_metadata(str(source_dir / "nonexistent.png")))
    cache._flush_metadata()

    # Verify both entries exist initially
    assert cache.get("valid_entry") is not None
    assert cache.get("stale_entry") is not None

    # Create new cache instance (should cleanup stale entries)
    cache2 = ThumbnailDiskCache(tmp_path / "cache", max_size_mb=1)

    # Verify stale entry removed
    assert cache2.get("stale_entry") is None

    # Verify valid entry remains
    assert cache2.get("valid_entry") is not None

    # Verify PNG file for stale entry was deleted
    stale_png = tmp_path / "cache" / "stale_entry.png"
    assert not stale_png.exists()

    # Verify metadata updated
    cache2._flush_metadata()
    metadata_path = tmp_path / "cache" / "metadata.json"
    with open(metadata_path) as f:
        metadata = json.load(f)

    assert "stale_entry" not in metadata["entries"]
    assert "valid_entry" in metadata["entries"]


def test_disk_full_graceful_degradation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify cache disables on disk full, logs warning."""
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=1)

    # Verify cache is initially enabled
    assert not cache._disabled

    # Store the original open function
    original_open = open

    def mock_open_disk_full(*args: Any, **kwargs: Any) -> Any:
        """Mock open() to raise disk full error for write operations."""
        mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")
        if "w" in mode or "a" in mode:
            raise OSError("No space left on device")
        return original_open(*args, **kwargs)

    # Monkeypatch open to simulate disk full
    monkeypatch.setattr("builtins.open", mock_open_disk_full)

    # Try to put entry (should fail gracefully)
    cache.put("test_key", VALID_PNG_BYTES, create_metadata())

    # Verify cache disabled
    assert cache._disabled

    # Verify warning logged
    assert "Failed to write cache file" in caplog.text

    # Verify subsequent operations are no-ops
    result = cache.get("test_key")
    assert result is None

    # Another put should be a no-op
    cache.put("another_key", VALID_PNG_BYTES, create_metadata())
    assert cache.get("another_key") is None


def test_clear_removes_all_files(tmp_path: Path) -> None:
    """Verify clear() deletes all PNG files and metadata."""
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=1)

    # Put multiple entries
    cache.put("entry1", VALID_PNG_BYTES, create_metadata("/path1.png"))
    cache.put("entry2", VALID_PNG_BYTES + b"\x00" * 100, create_metadata("/path2.png"))
    cache.put("entry3", VALID_PNG_BYTES + b"\x00" * 200, create_metadata("/path3.png"))
    cache._flush_metadata()

    # Verify files exist
    assert (tmp_path / "entry1.png").exists()
    assert (tmp_path / "entry2.png").exists()
    assert (tmp_path / "entry3.png").exists()
    assert (tmp_path / "metadata.json").exists()

    # Call clear()
    cache.clear()

    # Verify all PNG files deleted
    assert not (tmp_path / "entry1.png").exists()
    assert not (tmp_path / "entry2.png").exists()
    assert not (tmp_path / "entry3.png").exists()

    # Verify metadata.json deleted
    assert not (tmp_path / "metadata.json").exists()

    # Verify metadata dict reset
    stats = cache.get_stats()
    assert stats["entries"] == 0
    assert stats["total_size"] == 0

    # Verify gets return None
    assert cache.get("entry1") is None
    assert cache.get("entry2") is None
    assert cache.get("entry3") is None


def test_get_stats_returns_cache_info(tmp_path: Path) -> None:
    """Verify get_stats() returns correct statistics."""
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=5)

    # Initially empty
    stats = cache.get_stats()
    assert stats["total_size"] == 0
    assert stats["entries"] == 0
    assert stats["max_size"] == 5 * 1024 * 1024
    assert stats["disabled"] is False

    # Add some entries
    cache.put("entry1", VALID_PNG_BYTES, create_metadata())
    cache.put("entry2", VALID_PNG_BYTES + b"\x00" * 100, create_metadata())

    # Check updated stats
    stats = cache.get_stats()
    assert stats["entries"] == 2
    assert stats["total_size"] == len(VALID_PNG_BYTES) + len(VALID_PNG_BYTES + b"\x00" * 100)
    assert stats["max_size"] == 5 * 1024 * 1024
    assert stats["disabled"] is False


def test_cache_updates_existing_entry(tmp_path: Path) -> None:
    """Verify updating an existing cache key replaces the entry."""
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=1)
    cache_key = "update_test"

    # Put initial data
    initial_data = VALID_PNG_BYTES
    cache.put(cache_key, initial_data, create_metadata("/initial.png"))

    # Verify initial data
    result = cache.get(cache_key)
    assert result == initial_data

    initial_stats = cache.get_stats()
    initial_size = initial_stats["total_size"]

    # Update with new data
    new_data = VALID_PNG_BYTES + b"\x00" * 200
    cache.put(cache_key, new_data, create_metadata("/updated.png"))

    # Verify updated data
    result = cache.get(cache_key)
    assert result == new_data

    # Verify total_size adjusted correctly
    stats = cache.get_stats()
    expected_size = initial_size - len(initial_data) + len(new_data)
    assert stats["total_size"] == expected_size

    # Verify only one entry exists
    assert stats["entries"] == 1


def test_cache_survives_missing_png_file(tmp_path: Path) -> None:
    """Verify cache handles case where PNG file is deleted externally."""
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=1)
    cache_key = "missing_file"

    # Put data
    cache.put(cache_key, VALID_PNG_BYTES, create_metadata())
    cache._flush_metadata()

    # Manually delete the PNG file
    png_path = tmp_path / f"{cache_key}.png"
    png_path.unlink()

    # Try to get (should return None and clean up metadata)
    result = cache.get(cache_key)
    assert result is None

    # Verify entry removed from metadata
    cache._flush_metadata()
    metadata_path = tmp_path / "metadata.json"
    with open(metadata_path) as f:
        metadata = json.load(f)

    assert cache_key not in metadata["entries"]


def test_cache_handles_empty_metadata_path(tmp_path: Path) -> None:
    """Verify cache handles entries with empty source path."""
    cache = ThumbnailDiskCache(tmp_path, max_size_mb=1)

    # Put entry with empty path
    cache.put("empty_path", VALID_PNG_BYTES, {"path": "", "mtime": 0, "size": 0, "palette_hash": 0})

    # Force flush metadata to disk
    cache._flush_metadata()

    # Verify entry exists in first cache
    result1 = cache.get("empty_path")
    assert result1 == VALID_PNG_BYTES

    # Create new cache instance - should load existing metadata
    cache2 = ThumbnailDiskCache(tmp_path, max_size_mb=1)

    # Should not be cleaned up as stale (empty path means no source validation)
    result = cache2.get("empty_path")
    assert result == VALID_PNG_BYTES
