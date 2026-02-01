"""Tests for CaptureResultRepository."""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core.mesen_integration.click_extractor import CaptureResult
from core.repositories.capture_result_repository import CaptureResultRepository


@pytest.fixture
def capture_json(tmp_path: Path) -> Path:
    """Create a minimal capture JSON file."""
    # Build 4bpp tile data: all pixels = palette index 0
    tile_bytes = [0x00] * 32
    tile_hex = "".join(f"{b:02x}" for b in tile_bytes)

    capture_data = {
        "schema_version": "1.0",
        "frame": 100,
        "obsel": {"raw": 0},
        "visible_count": 1,
        "entries": [
            {
                "id": 1,
                "x": 0,
                "y": 0,
                "tile": 0,
                "width": 8,
                "height": 8,
                "palette": 0,
                "priority": 0,
                "flip_h": False,
                "flip_v": False,
                "name_table": 0,
                "tile_page": 0,
                "tiles": [
                    {
                        "tile_index": 0,
                        "vram_addr": 0,
                        "pos_x": 0,
                        "pos_y": 0,
                        "data_hex": tile_hex,
                    }
                ],
            }
        ],
        "palettes": {"0": [[0, 0, 0]] * 16},
    }
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(capture_data))
    return path


@pytest.fixture
def repository() -> CaptureResultRepository:
    """Create a repository instance."""
    return CaptureResultRepository()


class TestCaptureResultRepository:
    """Tests for CaptureResultRepository."""

    def test_get_or_parse_returns_capture_result(self, repository: CaptureResultRepository, capture_json: Path) -> None:
        """Test that get_or_parse returns a valid CaptureResult."""
        result = repository.get_or_parse(capture_json)

        assert isinstance(result, CaptureResult)
        assert result.frame == 100
        assert len(result.entries) == 1

    def test_cache_hit_returns_same_object(self, repository: CaptureResultRepository, capture_json: Path) -> None:
        """Test that repeated calls return the same cached object."""
        result1 = repository.get_or_parse(capture_json)
        result2 = repository.get_or_parse(capture_json)

        # Should be the exact same object (identity check)
        assert result1 is result2
        assert repository.cache_size() == 1

    def test_mtime_change_invalidates_cache(self, repository: CaptureResultRepository, capture_json: Path) -> None:
        """Test that file modification invalidates cache."""
        result1 = repository.get_or_parse(capture_json)
        original_frame = result1.frame

        # Modify file (change mtime)
        original_mtime = capture_json.stat().st_mtime
        new_mtime = original_mtime + 1.0
        data = json.loads(capture_json.read_text())
        data["frame"] = 200
        capture_json.write_text(json.dumps(data))
        os.utime(capture_json, (new_mtime, new_mtime))

        result2 = repository.get_or_parse(capture_json)

        # Should be a different object with updated data
        assert result2 is not result1
        assert result2.frame == 200
        assert original_frame == 100

    def test_get_if_cached_returns_none_when_not_cached(
        self, repository: CaptureResultRepository, capture_json: Path
    ) -> None:
        """Test get_if_cached returns None for uncached path."""
        result = repository.get_if_cached(capture_json)
        assert result is None

    def test_get_if_cached_returns_result_when_cached(
        self, repository: CaptureResultRepository, capture_json: Path
    ) -> None:
        """Test get_if_cached returns cached result."""
        # Prime the cache
        expected = repository.get_or_parse(capture_json)

        result = repository.get_if_cached(capture_json)
        assert result is expected

    def test_get_if_cached_returns_none_when_stale(
        self, repository: CaptureResultRepository, capture_json: Path
    ) -> None:
        """Test get_if_cached returns None when cache is stale."""
        # Prime the cache
        repository.get_or_parse(capture_json)

        # Modify file mtime
        original_mtime = capture_json.stat().st_mtime
        os.utime(capture_json, (original_mtime + 1, original_mtime + 1))

        result = repository.get_if_cached(capture_json)
        assert result is None

    def test_invalidate_removes_entry(self, repository: CaptureResultRepository, capture_json: Path) -> None:
        """Test invalidate removes cache entry."""
        repository.get_or_parse(capture_json)
        assert repository.cache_size() == 1

        removed = repository.invalidate(capture_json)

        assert removed is True
        assert repository.cache_size() == 0
        assert repository.get_if_cached(capture_json) is None

    def test_invalidate_returns_false_for_uncached(
        self, repository: CaptureResultRepository, capture_json: Path
    ) -> None:
        """Test invalidate returns False for uncached path."""
        removed = repository.invalidate(capture_json)
        assert removed is False

    def test_invalidate_all_clears_cache(self, repository: CaptureResultRepository, tmp_path: Path) -> None:
        """Test invalidate_all clears entire cache."""
        # Create multiple capture files
        for i in range(3):
            path = tmp_path / f"capture_{i}.json"
            data = {
                "schema_version": "1.0",
                "frame": i,
                "obsel": {"raw": 0},
                "visible_count": 0,
                "entries": [],
                "palettes": {},
            }
            path.write_text(json.dumps(data))
            repository.get_or_parse(path)

        assert repository.cache_size() == 3

        count = repository.invalidate_all()

        assert count == 3
        assert repository.cache_size() == 0

    def test_thread_safety(self, repository: CaptureResultRepository, capture_json: Path) -> None:
        """Test concurrent access from multiple threads."""
        results: list[CaptureResult] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                result = repository.get_or_parse(capture_json)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Run 10 concurrent threads
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10

        # All results should be the same cached object
        first = results[0]
        for result in results[1:]:
            assert result is first

    def test_concurrent_access_with_executor(self, repository: CaptureResultRepository, capture_json: Path) -> None:
        """Test concurrent access using ThreadPoolExecutor."""
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(repository.get_or_parse, capture_json) for _ in range(20)]
            results = [f.result() for f in futures]

        # All should be same object
        first = results[0]
        assert all(r is first for r in results)
        assert repository.cache_size() == 1
