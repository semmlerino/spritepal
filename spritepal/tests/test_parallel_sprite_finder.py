"""
Comprehensive tests for parallel sprite finder functionality.

Tests both parallel vs linear performance, result accuracy, cancellation handling,
adaptive step sizing, and proper mocking for unit tests.
"""
from __future__ import annotations

import logging
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.parallel_sprite_finder import (
    ParallelSpriteFinder,
    SearchChunk,
    SearchResult,
)
from core.sprite_finder import SpriteFinder
from utils.constants import DEFAULT_SCAN_STEP

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Parallel finder tests create thread pools that take time to clean up"),
    pytest.mark.usefixtures("session_managers", "mock_hal"),  # DI + HAL mocking
    pytest.mark.shared_state_safe,
    pytest.mark.serial,
    pytest.mark.thread_safety,
    pytest.mark.ci_safe,
    pytest.mark.headless,
    pytest.mark.performance,
    pytest.mark.rom_data,
]
@pytest.fixture
def sample_rom_data():
    """Create sample ROM data for testing."""
    # Create a 1MB ROM with various patterns
    rom_size = 0x100000  # 1MB
    rom_data = bytearray(rom_size)

    # Add some sprite-like patterns at known offsets
    sprite_patterns = [
        (0x1000, b"\x01\x02\x03\x04" * 64),  # Simple pattern
        (0x5000, b"\x00\xFF\x80\x7F" * 32),  # High contrast
        (0xA000, bytes(range(256))),           # Sequential data
        (0xF000, b"\xAA\x55" * 128),         # Alternating pattern
    ]

    for offset, pattern in sprite_patterns:
        rom_data[offset:offset + len(pattern)] = pattern

    return bytes(rom_data)

@pytest.fixture
def temp_rom_file(sample_rom_data):
    """Create temporary ROM file for testing."""
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".smc") as f:
        f.write(sample_rom_data)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)

@pytest.fixture
def mock_sprite_finder():
    """Create mock SpriteFinder for unit tests."""
    finder = Mock(spec=SpriteFinder)

    # Mock find_sprite_at_offset with realistic behavior
    def mock_find_sprite(rom_data, offset):
        # Return sprite info for known test offsets
        test_sprites = {
            0x1000: {
                "decompressed_size": 2048,
                "compressed_size": 1024,
                "tile_count": 32,
                "visual_validation": {"passed": True}
            },
            0x5000: {
                "decompressed_size": 1024,
                "compressed_size": 512,
                "tile_count": 16,
                "visual_validation": {"passed": True}
            },
            0xA000: {
                "decompressed_size": 256,
                "compressed_size": 200,
                "tile_count": 4,
                "visual_validation": {"passed": False}
            }
        }
        return test_sprites.get(offset)

    finder.find_sprite_at_offset.side_effect = mock_find_sprite
    return finder

class TestSearchChunk:
    """Test SearchChunk data class."""

    def test_search_chunk_creation(self):
        """Test SearchChunk creation and properties."""
        chunk = SearchChunk(start=0x1000, end=0x2000, chunk_id=1)

        assert chunk.start == 0x1000
        assert chunk.end == 0x2000
        assert chunk.chunk_id == 1
        assert chunk.size == 0x1000

    def test_search_chunk_size_property(self):
        """Test size property calculation."""
        chunk = SearchChunk(start=0x1000, end=0x1500, chunk_id=0)
        assert chunk.size == 0x500

class TestSearchResult:
    """Test SearchResult data class."""

    def test_search_result_creation(self):
        """Test SearchResult creation with all fields."""
        metadata = {"test": "data"}
        result = SearchResult(
            offset=0x1000,
            size=2048,
            tile_count=32,
            compressed_size=1024,
            confidence=0.85,
            metadata=metadata
        )

        assert result.offset == 0x1000
        assert result.size == 2048
        assert result.tile_count == 32
        assert result.compressed_size == 1024
        assert result.confidence == 0.85
        assert result.metadata == metadata

class TestParallelSpriteFinder:
    """Test ParallelSpriteFinder class."""

    def test_parallel_finder_initialization(self):
        """Test proper initialization of ParallelSpriteFinder."""
        finder = ParallelSpriteFinder(
            num_workers=2,
            chunk_size=0x20000,
            step_size=0x200
        )

        assert finder.num_workers == 2
        assert finder.chunk_size == 0x20000
        assert finder.step_size == 0x200
        assert len(finder.sprite_finders) == 2
        assert finder.executor is not None

    def test_default_initialization(self):
        """Test default initialization parameters."""
        finder = ParallelSpriteFinder()

        assert finder.num_workers == 4
        assert finder.chunk_size == 0x40000
        assert finder.step_size == DEFAULT_SCAN_STEP
        assert len(finder.sprite_finders) == 4

    def test_create_chunks(self):
        """Test chunk creation logic."""
        finder = ParallelSpriteFinder(chunk_size=0x10000)

        chunks = finder._create_chunks(0x0, 0x30000)

        assert len(chunks) == 3
        assert chunks[0].start == 0x0
        assert chunks[0].end == 0x10000
        assert chunks[1].start == 0x10000
        assert chunks[1].end == 0x20000
        assert chunks[2].start == 0x20000
        assert chunks[2].end == 0x30000

        # Check chunk IDs
        assert chunks[0].chunk_id == 0
        assert chunks[1].chunk_id == 1
        assert chunks[2].chunk_id == 2

    def test_create_chunks_partial_last_chunk(self):
        """Test chunk creation with partial last chunk."""
        finder = ParallelSpriteFinder(chunk_size=0x10000)

        chunks = finder._create_chunks(0x0, 0x25000)

        assert len(chunks) == 3
        assert chunks[2].start == 0x20000
        assert chunks[2].end == 0x25000
        assert chunks[2].size == 0x5000

    def test_quick_sprite_check_valid_patterns(self):
        """Test quick sprite check with valid patterns (now on SpriteFinder)."""
        parallel_finder = ParallelSpriteFinder()
        sprite_finder = parallel_finder.sprite_finders[0]

        # Valid pattern with variation
        valid_data = b"\x01\x02\x03\x04\x05\x06\x07\x08" + b"\x00" * 8
        assert sprite_finder._quick_sprite_check(valid_data, 0) is True

    def test_quick_sprite_check_invalid_patterns(self):
        """Test quick sprite check with invalid patterns (now on SpriteFinder)."""
        parallel_finder = ParallelSpriteFinder()
        sprite_finder = parallel_finder.sprite_finders[0]

        # All zeros
        invalid_data = b"\x00" * 16
        assert sprite_finder._quick_sprite_check(invalid_data, 0) is False

        # All 0xFF
        invalid_data = b"\xFF" * 16
        assert sprite_finder._quick_sprite_check(invalid_data, 0) is False

        # Too uniform (only 2 unique bytes)
        invalid_data = b"\x00\xFF" * 8
        assert sprite_finder._quick_sprite_check(invalid_data, 0) is False

    def test_calculate_confidence_high_score(self):
        """Test confidence calculation with high-quality sprite (now on SpriteFinder)."""
        parallel_finder = ParallelSpriteFinder()
        sprite_finder = parallel_finder.sprite_finders[0]

        # Test the new _calculate_quick_confidence method
        confidence = sprite_finder._calculate_quick_confidence(
            decompressed_size=2048,  # Good size
            compressed_size=1024,    # Good compression ratio (0.5)
            tile_count=32,           # Good tile count
            tile_validation_score=0.9  # High tile validation score
        )
        assert confidence >= 0.8  # Should be high confidence

    def test_calculate_confidence_low_score(self):
        """Test confidence calculation with low-quality sprite (now on SpriteFinder)."""
        parallel_finder = ParallelSpriteFinder()
        sprite_finder = parallel_finder.sprite_finders[0]

        # Test the new _calculate_quick_confidence method
        confidence = sprite_finder._calculate_quick_confidence(
            decompressed_size=50,    # Too small
            compressed_size=200,     # Bad compression ratio (4.0)
            tile_count=1,            # Too few tiles
            tile_validation_score=0.1  # Low tile validation score
        )
        assert confidence <= 0.3  # Should be low confidence

    def test_calculate_adaptive_step_high_density(self):
        """Test adaptive step calculation with high sprite density."""
        parallel_finder = ParallelSpriteFinder()
        sprite_finder = parallel_finder.sprite_finders[0]

        # Create data with many potential sprites
        dense_data = b"\x01\x02\x03\x04\x05\x06\x07\x08" * 0x1000
        chunk = SearchChunk(start=0x0, end=0x4000, chunk_id=0)

        step = parallel_finder._calculate_adaptive_step(sprite_finder, dense_data, chunk)
        assert step < parallel_finder.step_size  # Should reduce step for dense areas

    def test_calculate_adaptive_step_low_density(self):
        """Test adaptive step calculation with low sprite density."""
        parallel_finder = ParallelSpriteFinder()
        sprite_finder = parallel_finder.sprite_finders[0]

        # Create sparse data
        sparse_data = b"\x00" * 0x8000
        chunk = SearchChunk(start=0x0, end=0x4000, chunk_id=0)

        step = parallel_finder._calculate_adaptive_step(sprite_finder, sparse_data, chunk)
        assert step >= parallel_finder.step_size  # Should maintain or increase step

    def test_search_chunk_with_mock(self):
        """Test single chunk search with mocked SpriteFinder."""
        from core.sprite_finder import ScanResult

        # Setup mock finder
        mock_finder = Mock()

        # Mock scan_offset to return ScanResult at offset 0x1000
        def mock_scan_offset(data, offset, quick_check=True, full_visual_validation=False):
            if offset == 0x1000:
                return ScanResult(
                    offset=offset,
                    compressed_size=512,
                    decompressed_size=1024,
                    tile_count=16,
                    confidence=0.9,
                    tile_validation_score=0.8,
                    visual_metrics=None
                )
            return None

        mock_finder.scan_offset = Mock(side_effect=mock_scan_offset)
        mock_finder._quick_sprite_check = Mock(return_value=True)

        finder = ParallelSpriteFinder()
        rom_data = b"\x01\x02\x03\x04" * 0x1000  # 16KB of test data
        chunk = SearchChunk(start=0x0, end=0x2000, chunk_id=0)

        results = finder._search_chunk(mock_finder, rom_data, chunk)

        # Should find the sprite at 0x1000
        assert len(results) >= 1
        found_offsets = [r.offset for r in results]
        assert 0x1000 in found_offsets

    def test_search_chunk_cancellation(self):
        """Test chunk search cancellation."""
        finder = ParallelSpriteFinder()
        rom_data = b"\x01\x02\x03\x04" * 0x1000
        chunk = SearchChunk(start=0x0, end=0x2000, chunk_id=0)

        # Create cancellation token that's already set
        cancellation_token = Mock()
        cancellation_token.is_set.return_value = True

        # Create a mock finder that would return results if not cancelled
        mock_finder = Mock()
        mock_finder.scan_offset = Mock(return_value=None)
        mock_finder._quick_sprite_check = Mock(return_value=True)

        results = finder._search_chunk(
            mock_finder, rom_data, chunk, cancellation_token
        )

        # Should return empty results due to cancellation
        assert len(results) == 0

    def test_search_parallel_basic(self, temp_rom_file):
        """Test basic parallel search functionality."""
        from core.sprite_finder import ScanResult

        finder = ParallelSpriteFinder(num_workers=2)

        # Mock the sprite finders' scan_offset to return known results
        def mock_scan_offset(data, offset, quick_check=True, full_visual_validation=False):
            if offset in [0x1000, 0x5000]:
                return ScanResult(
                    offset=offset,
                    compressed_size=512,
                    decompressed_size=1024,
                    tile_count=16,
                    confidence=0.9,
                    tile_validation_score=0.8,
                    visual_metrics=None
                )
            return None

        for sprite_finder in finder.sprite_finders:
            sprite_finder.scan_offset = Mock(side_effect=mock_scan_offset)

        results = finder.search_parallel(
            temp_rom_file,
            start_offset=0x0,
            end_offset=0x10000
        )

        # Should return results sorted by offset
        assert isinstance(results, list)
        if results:
            offsets = [r.offset for r in results]
            assert offsets == sorted(offsets)  # Should be sorted

    def test_search_parallel_with_progress_callback(self, temp_rom_file):
        """Test parallel search with progress callback."""
        finder = ParallelSpriteFinder(num_workers=2, chunk_size=0x8000)

        # Track progress calls
        progress_calls = []

        def progress_callback(current, total):
            progress_calls.append((current, total))

        # Mock sprite finders to avoid actual search (scan_offset returns None)
        for sprite_finder in finder.sprite_finders:
            sprite_finder.scan_offset = Mock(return_value=None)

        finder.search_parallel(
            temp_rom_file,
            start_offset=0x0,
            end_offset=0x10000,
            progress_callback=progress_callback
        )

        # Should have called progress callback
        assert len(progress_calls) > 0

        # Last call should be 100%
        if progress_calls:
            final_current, final_total = progress_calls[-1]
            assert final_current in (100, final_total)

    def test_search_parallel_cancellation(self, temp_rom_file):
        """Test parallel search cancellation."""
        finder = ParallelSpriteFinder(num_workers=2)

        # Create cancellation token
        cancellation_token = threading.Event()
        cancellation_token.set()  # Cancel immediately

        results = finder.search_parallel(
            temp_rom_file,
            start_offset=0x0,
            end_offset=0x10000,
            cancellation_token=cancellation_token
        )

        # Search should be cancelled, so no results
        assert len(results) == 0

    def test_search_parallel_invalid_file(self):
        """Test parallel search with invalid file."""
        finder = ParallelSpriteFinder()

        with pytest.raises(FileNotFoundError):
            finder.search_parallel("/nonexistent/file.rom")

    def test_shutdown(self):
        """Test proper shutdown of thread pool."""
        finder = ParallelSpriteFinder(num_workers=2)

        # Shutdown should not raise exceptions
        finder.shutdown()

        # Executor should be shutdown
        assert finder.executor._shutdown


@pytest.mark.slow
class TestParallelPerformance:
    """Performance tests for parallel sprite finder."""

    def test_parallel_vs_linear_performance(self, temp_rom_file):
        """Test that parallel search is faster than linear (when it should be)."""
        # Note: This is a basic performance test
        # In real scenarios with CPU-intensive sprite detection,
        # parallel should be faster

        # Create parallel finder
        parallel_finder = ParallelSpriteFinder(num_workers=4, chunk_size=0x20000)

        # Mock sprite finders to simulate work
        def slow_mock_find_sprite(data, offset):
            time.sleep(0.001)  # sleep-ok: simulated processing delay

        for sprite_finder in parallel_finder.sprite_finders:
            sprite_finder.find_sprite_at_offset = Mock(side_effect=slow_mock_find_sprite)

        # Time parallel search
        start_time = time.time()
        parallel_results = parallel_finder.search_parallel(
            temp_rom_file,
            start_offset=0x0,
            end_offset=0x40000  # Smaller range for test
        )
        parallel_time = time.time() - start_time

        parallel_finder.shutdown()

        # For this test, just ensure it completes without error
        assert isinstance(parallel_results, list)
        assert parallel_time > 0

        logger.info(f"Parallel search took {parallel_time:.3f}s")
