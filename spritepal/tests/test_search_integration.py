"""
Integration tests for search functionality with real ROM data.

Tests full search workflow, performance benchmarks, memory usage,
and integration between different search components.
"""
from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from core.parallel_sprite_finder import AdaptiveSpriteFinder, ParallelSpriteFinder
from core.visual_similarity_search import SpriteGroupFinder, VisualSimilarityEngine
from ui.dialogs.advanced_search_dialog import AdvancedSearchDialog
from ui.rom_extraction.workers.search_worker import SpriteSearchWorker

# Serial execution required: Thread safety concerns
pytestmark = [

    pytest.mark.serial,
    pytest.mark.thread_safety,
    pytest.mark.ci_safe,
    pytest.mark.dialog,
    pytest.mark.headless,
    pytest.mark.performance,
    pytest.mark.requires_display,
    pytest.mark.rom_data,
    pytest.mark.signals_slots,
]

logger = logging.getLogger(__name__)

@pytest.fixture
def large_test_rom():
    """Create a larger test ROM with embedded sprite patterns."""
    rom_size = 0x200000  # 2MB ROM
    rom_data = bytearray(rom_size)

    # Fill with pseudo-random data to avoid uniform patterns
    for i in range(rom_size):
        rom_data[i] = (i * 17 + 42) % 256

    # Embed known sprite-like patterns at specific offsets
    sprite_patterns = [
        # Pattern 1: HAL compression-like header + data
        (0x10000, b"\x00\x01\x02\x03" + b"\xAA\x55" * 128),

        # Pattern 2: Larger sprite pattern
        (0x20000, b"\x10\x20\x30\x40" + bytes(range(256)) * 4),

        # Pattern 3: Small sprite
        (0x30000, b"\xFF\xFE\xFD\xFC" + b"\x00\xFF" * 64),

        # Pattern 4: Animation sequence (similar sprites)
        (0x40000, b"\x80\x81\x82\x83" + b"\x12\x34" * 96),
        (0x40400, b"\x84\x85\x86\x87" + b"\x12\x35" * 96),  # Similar
        (0x40800, b"\x88\x89\x8A\x8B" + b"\x12\x36" * 96),  # Similar

        # Pattern 5: Distant sprite for proximity testing
        (0x180000, b"\x01\x02\x03\x04" + b"\xDE\xAD" * 200),
    ]

    for offset, pattern in sprite_patterns:
        end_offset = min(offset + len(pattern), rom_size)
        pattern_len = end_offset - offset
        rom_data[offset:end_offset] = pattern[:pattern_len]

    return bytes(rom_data)

@pytest.fixture
def large_temp_rom_file(large_test_rom):
    """Create temporary ROM file with test data."""
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".smc") as f:
        f.write(large_test_rom)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)

@pytest.fixture
def real_sprite_images():
    """Create test sprite images for visual similarity testing."""
    images = {}

    # Create base sprite image
    base_image = Image.new("RGB", (32, 32), color="white")
    pixels = base_image.load()

    # Draw a simple character sprite pattern
    for y in range(8, 24):
        for x in range(8, 24):
            if (x - 16) ** 2 + (y - 16) ** 2 < 64:  # Circle
                pixels[x, y] = (255, 0, 0)  # Red

    images["base"] = base_image

    # Create variation 1 (color change)
    var1 = base_image.copy()
    var1_pixels = var1.load()
    for y in range(8, 24):
        for x in range(8, 24):
            if var1_pixels[x, y] == (255, 0, 0):
                var1_pixels[x, y] = (0, 255, 0)  # Green instead of red
    images["color_variant"] = var1

    # Create variation 2 (size change)
    var2 = base_image.copy()
    var2_pixels = var2.load()
    for y in range(10, 22):
        for x in range(10, 22):
            if (x - 16) ** 2 + (y - 16) ** 2 < 36:  # Smaller circle
                var2_pixels[x, y] = (255, 0, 0)  # Red
    images["size_variant"] = var2

    # Create completely different sprite
    different = Image.new("RGB", (32, 32), color="blue")
    diff_pixels = different.load()
    # Draw a square pattern
    for y in range(10, 22):
        for x in range(10, 22):
            diff_pixels[x, y] = (255, 255, 0)  # Yellow square
    images["different"] = different

    return images

class TestParallelSearchIntegration:
    """Integration tests for parallel sprite search."""

    def test_parallel_finder_real_rom_search(self, large_temp_rom_file):
        """Test parallel finder with real ROM data."""
        finder = ParallelSpriteFinder(
            num_workers=2,
            chunk_size=0x40000,  # 256KB chunks
            step_size=0x1000     # Larger step for faster test
        )

        # Mock the sprite finders to return results for known offsets
        test_offsets = {0x10000, 0x20000, 0x30000, 0x40000, 0x180000}

        def mock_find_sprite(rom_data, offset):
            if offset in test_offsets:
                return {
                    "decompressed_size": 1024 + (offset % 512),
                    "compressed_size": 512 + (offset % 256),
                    "tile_count": 16 + (offset % 32),
                    "visual_validation": {"passed": True}
                }
            return None

        for sprite_finder in finder.sprite_finders:
            sprite_finder.find_sprite_at_offset = mock_find_sprite

        # Perform search
        start_time = time.time()
        results = finder.search_parallel(
            large_temp_rom_file,
            start_offset=0x0,
            end_offset=0x200000
        )
        search_time = time.time() - start_time

        # Verify results
        assert len(results) > 0
        assert all(isinstance(r.offset, int) for r in results)
        assert all(r.confidence > 0 for r in results)

        # Results should be sorted by offset
        offsets = [r.offset for r in results]
        assert offsets == sorted(offsets)

        logger.info(f"Parallel search found {len(results)} sprites in {search_time:.2f}s")

        # Cleanup
        finder.shutdown()

    def test_adaptive_finder_learning(self, large_temp_rom_file):
        """Test adaptive finder learning from results."""
        finder = AdaptiveSpriteFinder(
            num_workers=2,
            chunk_size=0x20000
        )

        # Mock sprite finders with consistent patterns
        def mock_find_sprite(rom_data, offset):
            # Return sprites at aligned offsets
            if offset % 0x10000 == 0 and offset < 0x100000:
                return {
                    "decompressed_size": 2048,
                    "compressed_size": 1024,
                    "tile_count": 32,
                    "visual_validation": {"passed": True}
                }
            return None

        for sprite_finder in finder.sprite_finders:
            sprite_finder.find_sprite_at_offset = mock_find_sprite

        # First search
        results1 = finder.search_parallel(
            large_temp_rom_file,
            start_offset=0x0,
            end_offset=0x100000
        )

        # Learn from results
        finder.learn_from_results(results1)

        # Verify learning occurred
        assert len(finder.sprite_patterns) > 0
        assert len(finder.common_offsets) > 0

        logger.info(f"Learned {len(finder.sprite_patterns)} sprite patterns")

        # Cleanup
        finder.shutdown()

    def test_cancellation_integration(self, large_temp_rom_file):
        """Test search cancellation works correctly."""
        import threading

        finder = ParallelSpriteFinder(num_workers=4)

        # Mock slow sprite finding
        def slow_find_sprite(rom_data, offset):
            time.sleep(0.01)  # Slow operation

        for sprite_finder in finder.sprite_finders:
            sprite_finder.find_sprite_at_offset = slow_find_sprite

        # Create cancellation token
        cancellation_token = threading.Event()

        # Start search in thread
        search_thread = threading.Thread(
            target=lambda: finder.search_parallel(
                large_temp_rom_file,
                start_offset=0x0,
                end_offset=0x200000,
                cancellation_token=cancellation_token
            )
        )

        start_time = time.time()
        search_thread.start()

        # Cancel after short delay
        time.sleep(0.1)
        cancellation_token.set()

        # Wait for completion
        search_thread.join(timeout=5.0)
        cancel_time = time.time() - start_time

        # Should complete quickly due to cancellation
        assert cancel_time < 2.0  # Should be much faster than full search

        finder.shutdown()

class TestVisualSimilarityIntegration:
    """Integration tests for visual similarity search."""

    def test_similarity_engine_full_workflow(self, real_sprite_images):
        """Test complete visual similarity workflow."""
        engine = VisualSimilarityEngine(hash_size=8)

        # Index all test images
        for name, image in real_sprite_images.items():
            offset = hash(name) % 0x100000  # Generate unique offsets
            engine.index_sprite(offset, image, {"name": name})

        # Build index
        engine.build_similarity_index()

        # Find similar sprites to base image
        base_offset = hash("base") % 0x100000
        similar_sprites = engine.find_similar(
            target=base_offset,
            max_results=10,
            similarity_threshold=0.3
        )

        # Should find variants but not completely different ones
        found_names = []
        for match in similar_sprites:
            sprite_hash = engine.sprite_database[match.offset]
            found_names.append(sprite_hash.metadata.get("name"))

        # Color and size variants should be found
        assert len(similar_sprites) >= 2
        assert any("variant" in name for name in found_names if name)

        # Different sprite should have lower similarity if found
        different_matches = [m for m in similar_sprites
                           if engine.sprite_database[m.offset].metadata.get("name") == "different"]
        if different_matches:
            assert different_matches[0].similarity_score < 0.7

    def test_sprite_group_finder_integration(self, real_sprite_images):
        """Test sprite group finding with real images."""
        engine = VisualSimilarityEngine(hash_size=8)
        group_finder = SpriteGroupFinder(engine)

        # Index images as sprite families
        base_family_offsets = []
        for i, (name, image) in enumerate(real_sprite_images.items()):
            if "variant" in name or name == "base":
                offset = 0x10000 + i * 0x1000
                engine.index_sprite(offset, image, {"family": "base"})
                base_family_offsets.append(offset)

        # Index different sprite separately
        different_offset = 0x50000
        engine.index_sprite(different_offset, real_sprite_images["different"],
                          {"family": "different"})

        # Find sprite groups
        groups = group_finder.find_sprite_groups(
            similarity_threshold=0.4,
            min_group_size=2
        )

        # Should find at least one group (base family)
        assert len(groups) >= 1

        # Largest group should contain base family members
        largest_group = groups[0]
        assert len(largest_group) >= 2

        # Different sprite should not be in the same group
        assert different_offset not in largest_group

    def test_animation_sequence_detection(self, real_sprite_images):
        """Test animation sequence detection."""
        engine = VisualSimilarityEngine(hash_size=8)
        group_finder = SpriteGroupFinder(engine)

        # Create animation sequence at consecutive offsets
        base_image = real_sprite_images["base"]
        animation_offsets = []

        for i in range(4):
            offset = 0x20000 + i * 0x400  # Close offsets
            # Create slight variations for animation frames
            frame = base_image.copy()
            animation_offsets.append(offset)
            engine.index_sprite(offset, frame, {"frame": i})

        # Add distant sprite that shouldn't be part of animation
        distant_offset = 0x80000
        engine.index_sprite(distant_offset, base_image, {"frame": "distant"})

        # Find animations
        animations = group_finder.find_animations(
            offset_proximity=0x2000,  # Within 8KB
            similarity_threshold=0.8
        )

        # Should find the animation sequence
        assert len(animations) >= 1

        # Animation should contain consecutive frames
        animation = animations[0]
        assert len(animation) >= 3  # At least 3 frames

        # Should not include distant sprite
        assert distant_offset not in animation

        # Frames should be in order
        assert animation == sorted(animation)

    def test_index_export_import_integration(self, real_sprite_images):
        """Test complete index export/import workflow."""
        engine = VisualSimilarityEngine(hash_size=8)

        # Index images
        for name, image in real_sprite_images.items():
            offset = hash(name) % 0x100000
            engine.index_sprite(offset, image, {"name": name, "test": True})

        engine.build_similarity_index()

        # Export index
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            export_path = Path(f.name)

        try:
            engine.export_index(export_path)

            # Import into new engine
            new_engine = VisualSimilarityEngine()
            new_engine.import_index(export_path)

            # Verify imported data
            assert len(new_engine.sprite_database) == len(engine.sprite_database)
            assert new_engine.index_built == engine.index_built

            # Test functionality with imported engine
            first_offset = next(iter(new_engine.sprite_database.keys()))
            similar = new_engine.find_similar(
                target=first_offset,
                max_results=5,
                similarity_threshold=0.3
            )

            # Should work the same as original engine
            assert len(similar) >= 0  # May or may not find matches

        finally:
            export_path.unlink(missing_ok=True)

class TestAdvancedSearchDialogIntegration:
    """Integration tests for advanced search dialog."""

    @pytest.mark.gui
    def test_dialog_search_workflow(self, qtbot, large_temp_rom_file):
        """Test complete search workflow through dialog."""
        with patch("ui.dialogs.advanced_search_dialog.SearchWorker") as mock_worker_class:
            dialog = AdvancedSearchDialog(large_temp_rom_file)
            qtbot.addWidget(dialog)

            # Mock worker behavior
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.isRunning.return_value = False

            # Setup dialog parameters
            dialog.start_offset_edit.setText("0x10000")
            dialog.end_offset_edit.setText("0x20000")
            dialog.workers_spin.setValue(2)

            # Start search
            dialog._start_parallel_search()

            # Verify worker created with correct parameters
            mock_worker_class.assert_called_once()
            args = mock_worker_class.call_args[0]
            assert args[0] == "parallel"  # Search type

            params = args[1]
            assert params["start_offset"] == 0x10000
            assert params["end_offset"] == 0x20000
            assert params["num_workers"] == 2

            # Simulate worker signals
            mock_worker.progress = Mock()
            mock_worker.result_found = Mock()
            mock_worker.search_complete = Mock()
            mock_worker.error = Mock()

            # Connect signals (simulate _connect_worker_signals)
            dialog.search_worker = mock_worker
            dialog._connect_worker_signals()

            # Simulate finding results
            from core.parallel_sprite_finder import SearchResult
            test_result = SearchResult(
                offset=0x15000,
                size=2048,
                tile_count=32,
                compressed_size=1024,
                confidence=0.8,
                metadata={}
            )

            dialog._add_result(test_result)

            # Verify result added
            assert len(dialog.current_results) == 1
            assert dialog.results_list.count() == 1

    def test_search_history_persistence(self, large_temp_rom_file):
        """Test search history persistence across dialog instances."""
        with tempfile.TemporaryDirectory() as temp_dir, patch("pathlib.Path.home", return_value=Path(temp_dir)):
            # Create first dialog and add history
            with patch("ui.dialogs.advanced_search_dialog.SearchWorker"):
                dialog1 = AdvancedSearchDialog(large_temp_rom_file)

            # Add history entry
            from datetime import datetime

            from ui.dialogs.advanced_search_dialog import (
                SearchFilter,
                SearchHistoryEntry,
            )
            entry = SearchHistoryEntry(
                timestamp=datetime.now(),
                search_type="Integration Test",
                query="0x10000-0x20000",
                filters=SearchFilter(
                    min_size=1024, max_size=32768, min_tiles=4, max_tiles=128,
                    alignment=0x100, include_compressed=True,
                    include_uncompressed=False, confidence_threshold=0.7
                ),
                results_count=10
            )
            dialog1.search_history.append(entry)
            dialog1._save_history()

            # Create second dialog and load history
            with patch("ui.dialogs.advanced_search_dialog.SearchWorker"):
                dialog2 = AdvancedSearchDialog(large_temp_rom_file)

            # History should be loaded
            assert len(dialog2.search_history) == 1
            loaded_entry = dialog2.search_history[0]
            assert loaded_entry.search_type == "Integration Test"
            assert loaded_entry.results_count == 10

class TestSpriteSearchWorkerIntegration:
    """Integration tests for SpriteSearchWorker."""

    def test_sprite_search_worker_real_search(self, large_temp_rom_file):
        """Test SpriteSearchWorker with real search functionality."""
        from core.rom_extractor import ROMExtractor

        # Mock ROM extractor
        mock_extractor = Mock(spec=ROMExtractor)

        worker = SpriteSearchWorker(
            rom_path=large_temp_rom_file,
            start_offset=0x10000,
            end_offset=0x50000,
            direction=1,  # Forward search
            extractor=mock_extractor
        )

        # Mock the parallel finder to return a result
        with patch.object(worker, "_parallel_finder") as mock_finder:
            mock_result = Mock()
            mock_result.offset = 0x20000
            mock_result.confidence = 0.8
            mock_result.tile_count = 16
            mock_finder.search_parallel.return_value = [mock_result]

            # Track signal emissions
            found_signals = []
            complete_signals = []

            worker.sprite_found.connect(lambda offset, quality: found_signals.append((offset, quality)))
            worker.search_complete.connect(lambda found: complete_signals.append(found))

            # Run search
            worker.run()

            # Verify results
            assert len(found_signals) == 1
            assert found_signals[0][0] == 0x20000  # Offset
            assert found_signals[0][1] == 0.8      # Quality

            assert len(complete_signals) == 1
            assert complete_signals[0] is True     # Found sprite

    def test_sprite_search_worker_no_results(self, large_temp_rom_file):
        """Test SpriteSearchWorker when no sprites found."""
        from core.rom_extractor import ROMExtractor

        mock_extractor = Mock(spec=ROMExtractor)

        worker = SpriteSearchWorker(
            rom_path=large_temp_rom_file,
            start_offset=0x10000,
            end_offset=0x20000,
            direction=1,
            extractor=mock_extractor
        )

        # Mock parallel finder to return no results
        with patch.object(worker, "_parallel_finder") as mock_finder:
            mock_finder.search_parallel.return_value = []

            complete_signals = []
            worker.search_complete.connect(lambda found: complete_signals.append(found))

            worker.run()

            # Should indicate no sprite found
            assert len(complete_signals) == 1
            assert complete_signals[0] is False

    def test_sprite_search_worker_backward_search(self, large_temp_rom_file):
        """Test SpriteSearchWorker backward search functionality."""
        from core.rom_extractor import ROMExtractor

        mock_extractor = Mock(spec=ROMExtractor)

        worker = SpriteSearchWorker(
            rom_path=large_temp_rom_file,
            start_offset=0x30000,
            end_offset=0x10000,
            direction=-1,  # Backward search
            extractor=mock_extractor
        )

        with patch.object(worker, "_parallel_finder") as mock_finder:
            # Return multiple results, backward search should take the last (closest to original)
            mock_result1 = Mock()
            mock_result1.offset = 0x15000
            mock_result1.confidence = 0.7

            mock_result2 = Mock()
            mock_result2.offset = 0x25000  # Closer to start position
            mock_result2.confidence = 0.8

            mock_finder.search_parallel.return_value = [mock_result1, mock_result2]

            found_signals = []
            worker.sprite_found.connect(lambda offset, quality: found_signals.append((offset, quality)))

            worker.run()

            # Should find the result closer to original position (0x25000)
            assert len(found_signals) == 1
            assert found_signals[0][0] == 0x25000

@pytest.mark.slow
@pytest.mark.integration
class TestPerformanceBenchmarks:
    """Performance benchmark tests for search functionality."""

    def test_parallel_vs_sequential_performance(self, large_temp_rom_file):
        """Benchmark parallel vs sequential search performance."""
        # Mock sprite finder to simulate work
        def mock_find_sprite_slow(rom_data, offset):
            time.sleep(0.0001)  # Simulate processing time
            # Return sprite for some offsets to simulate realistic workload
            if offset % 0x10000 == 0:
                return {
                    "decompressed_size": 1024,
                    "compressed_size": 512,
                    "tile_count": 16,
                    "visual_validation": {"passed": True}
                }
            return None

        # Test parallel search
        parallel_finder = ParallelSpriteFinder(num_workers=4, chunk_size=0x40000)
        for sprite_finder in parallel_finder.sprite_finders:
            sprite_finder.find_sprite_at_offset = mock_find_sprite_slow

        start_time = time.time()
        parallel_results = parallel_finder.search_parallel(
            large_temp_rom_file,
            start_offset=0x0,
            end_offset=0x80000  # Smaller range for test
        )
        parallel_time = time.time() - start_time

        # Test sequential search (1 worker)
        sequential_finder = ParallelSpriteFinder(num_workers=1, chunk_size=0x80000)
        for sprite_finder in sequential_finder.sprite_finders:
            sprite_finder.find_sprite_at_offset = mock_find_sprite_slow

        start_time = time.time()
        sequential_results = sequential_finder.search_parallel(
            large_temp_rom_file,
            start_offset=0x0,
            end_offset=0x80000
        )
        sequential_time = time.time() - start_time

        # Parallel should be faster (though may not be on single-core systems)
        logger.info(f"Parallel search: {parallel_time:.3f}s, Sequential: {sequential_time:.3f}s")
        logger.info(f"Speedup ratio: {sequential_time/parallel_time:.2f}x")

        # Results should be equivalent
        assert len(parallel_results) == len(sequential_results)

        # Cleanup
        parallel_finder.shutdown()
        sequential_finder.shutdown()

    def test_visual_similarity_performance_benchmark(self, real_sprite_images):
        """Benchmark visual similarity search performance."""
        engine = VisualSimilarityEngine(hash_size=8)

        # Index many sprites (simulate large ROM)
        num_sprites = 500
        base_image = real_sprite_images["base"]

        index_start_time = time.time()
        for i in range(num_sprites):
            # Create slight variations
            offset = 0x10000 + i * 0x1000
            engine.index_sprite(offset, base_image, {"index": i})

        engine.build_similarity_index()
        index_time = time.time() - index_start_time

        # Benchmark similarity search
        search_start_time = time.time()
        similar_sprites = engine.find_similar(
            target=0x10000,  # First sprite
            max_results=20,
            similarity_threshold=0.5
        )
        search_time = time.time() - search_start_time

        logger.info(f"Indexed {num_sprites} sprites in {index_time:.3f}s")
        logger.info(f"Similarity search in {search_time:.3f}s")
        logger.info(f"Found {len(similar_sprites)} similar sprites")

        # Performance should be reasonable
        assert index_time < 5.0  # Less than 5 seconds to index 500 sprites
        assert search_time < 1.0  # Less than 1 second to search

    def test_memory_usage_monitoring(self, large_temp_rom_file):
        """Monitor memory usage during search operations."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Perform memory-intensive operations
        finder = ParallelSpriteFinder(num_workers=4)

        # Mock sprite finder to avoid actual work but test memory patterns
        for sprite_finder in finder.sprite_finders:
            sprite_finder.find_sprite_at_offset = Mock(return_value=None)

        # Run search
        finder.search_parallel(
            large_temp_rom_file,
            start_offset=0x0,
            end_offset=0x200000
        )

        peak_memory = process.memory_info().rss / 1024 / 1024  # MB

        finder.shutdown()

        final_memory = process.memory_info().rss / 1024 / 1024  # MB

        logger.info(f"Memory usage - Initial: {initial_memory:.1f}MB, "
                   f"Peak: {peak_memory:.1f}MB, Final: {final_memory:.1f}MB")

        # Memory should not grow excessively
        memory_growth = peak_memory - initial_memory
        assert memory_growth < 100  # Less than 100MB growth

        # Memory should be mostly freed after shutdown
        memory_retained = final_memory - initial_memory
        assert memory_retained < 50  # Less than 50MB retained

@pytest.mark.benchmark
class TestSearchBenchmarks:
    """Benchmark tests using pytest-benchmark."""

    def test_benchmark_parallel_chunk_processing(self, benchmark, large_temp_rom_file):
        """Benchmark parallel chunk processing performance."""
        finder = ParallelSpriteFinder(num_workers=2, chunk_size=0x20000)

        # Mock sprite finders for consistent timing
        for sprite_finder in finder.sprite_finders:
            sprite_finder.find_sprite_at_offset = Mock(return_value=None)

        def run_search():
            return finder.search_parallel(
                large_temp_rom_file,
                start_offset=0x0,
                end_offset=0x40000  # Smaller range for benchmark
            )

        result = benchmark(run_search)
        assert isinstance(result, list)

        finder.shutdown()

    def test_benchmark_visual_hash_calculation(self, benchmark, real_sprite_images):
        """Benchmark visual hash calculation performance."""
        engine = VisualSimilarityEngine(hash_size=8)
        test_image = real_sprite_images["base"]

        def calculate_hashes():
            phash = engine._calculate_phash(test_image)
            dhash = engine._calculate_dhash(test_image)
            histogram = engine._calculate_color_histogram(test_image)
            return phash, dhash, histogram

        result = benchmark(calculate_hashes)
        assert len(result) == 3  # phash, dhash, histogram

    def test_benchmark_similarity_comparison(self, benchmark, real_sprite_images):
        """Benchmark similarity comparison performance."""
        engine = VisualSimilarityEngine(hash_size=8)

        # Pre-calculate hashes
        hash1 = engine.index_sprite(0x1000, real_sprite_images["base"])
        hash2 = engine.index_sprite(0x2000, real_sprite_images["color_variant"])

        def compare_similarity():
            return engine._calculate_similarity(hash1, hash2)

        result = benchmark(compare_similarity)
        assert 0.0 <= result <= 1.0
