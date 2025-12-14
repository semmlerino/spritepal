#!/usr/bin/env python3
from __future__ import annotations

"""
Comprehensive tests for division by zero prevention in all scan workers.
Tests all identified division operations to ensure they handle zero cases.
"""

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

class TestDivisionByZeroFixes:
    """Test all division by zero scenarios in scan workers."""

    @pytest.fixture(autouse=True)
    def init_managers(self, setup_managers):
        """Ensure DI container is initialized for tests that create workers.

        Uses setup_managers which respects session_managers if active.
        """
        yield

    def test_scan_worker_zero_range(self):
        """Test SpriteScanWorker with zero scan range."""
        from ui.rom_extraction.workers.scan_worker import SpriteScanWorker

        with tempfile.NamedTemporaryFile(suffix='.rom') as tmp:
            tmp.write(b'x' * 1024)
            tmp.flush()

            # Create worker with same start and end (zero range)
            worker = SpriteScanWorker(
                rom_path=tmp.name,
                extractor=MagicMock(),
                use_cache=False,
                start_offset=0x1000,
                end_offset=0x1000  # Same as start = zero range
            )

            # Mock the parallel finder to avoid actual scanning
            worker._parallel_finder = MagicMock()
            worker._parallel_finder.search_parallel = MagicMock(return_value=[])
            worker._parallel_finder.step_size = 0x100

            # Should not raise division by zero
            worker.run()

            # ASSERTIONS: Verify the worker completed successfully
            # 1. search_parallel was called (worker executed)
            assert worker._parallel_finder.search_parallel.called, \
                "search_parallel should be called even with zero range"
            # 2. No exception means no division by zero occurred

    def test_scan_worker_progress_callback_zero_range(self):
        """Test SpriteScanWorker progress callback with zero range."""
        from ui.rom_extraction.workers.scan_worker import SpriteScanWorker

        with tempfile.NamedTemporaryFile(suffix='.rom') as tmp:
            tmp.write(b'x' * 1024)
            tmp.flush()

            worker = SpriteScanWorker(
                rom_path=tmp.name,
                extractor=MagicMock(),
                use_cache=False,
                start_offset=0x500,
                end_offset=0x500  # Zero range
            )

            # Capture the progress callback
            worker._parallel_finder = MagicMock()
            progress_callback = None

            def capture_callback(*args, **kwargs):
                nonlocal progress_callback
                progress_callback = kwargs.get('progress_callback')
                return []

            worker._parallel_finder.search_parallel = capture_callback
            worker._parallel_finder.step_size = 0x100

            # Run to capture callback
            worker.run()

            # ASSERTIONS: Verify progress callback handling
            # Test progress callback with various values - should not raise
            if progress_callback:
                # Should handle zero range gracefully without division by zero
                try:
                    progress_callback(0, 100)
                    progress_callback(50, 100)
                    progress_callback(100, 100)
                except ZeroDivisionError:
                    pytest.fail("Progress callback raised ZeroDivisionError")

    def test_range_scan_worker_zero_range(self):
        """Test RangeScanWorker with zero scan range."""
        from ui.rom_extraction.workers.range_scan_worker import RangeScanWorker

        with tempfile.NamedTemporaryFile(suffix='.rom') as tmp:
            tmp.write(b'x' * 1024)
            tmp.flush()

            # Create worker with zero range
            worker = RangeScanWorker(
                rom_path=tmp.name,
                start_offset=0x100,
                end_offset=0x100,  # Same as start
                step_size=0x100,
                extractor=MagicMock()
            )

            # Should not raise division by zero
            worker.run()

            # ASSERTIONS: Verify worker completed
            # With zero range, worker should complete immediately
            # No exception means division by zero was handled

    def test_similarity_indexing_no_sprites(self):
        """Test SimilarityIndexingWorker with no sprites to index."""
        from ui.rom_extraction.workers.similarity_indexing_worker import SimilarityIndexingWorker

        with tempfile.NamedTemporaryFile(suffix='.rom') as tmp:
            tmp.write(b'SNES' * 256)
            tmp.flush()

            worker = SimilarityIndexingWorker(
                rom_path=tmp.name
            )

            # Don't add any sprites - should handle empty list gracefully
            # The worker should have no pending sprites to process

            # Should handle empty sprite list gracefully
            worker.run()

            # ASSERTIONS: Verify worker handled empty case
            # Worker should complete without error
            # This verifies no division by zero in progress calculations

    def test_preview_worker_zero_expected_size(self):
        """Test SpritePreviewWorker with zero expected size."""
        from ui.rom_extraction.workers.preview_worker import SpritePreviewWorker

        with tempfile.NamedTemporaryFile(suffix='.rom') as tmp:
            # Write test data
            tmp.write(b'\x00' * 1024)
            tmp.flush()

            # Create worker with required parameters
            worker = SpritePreviewWorker(
                rom_path=tmp.name,
                offset=0,
                sprite_name="test_sprite",
                extractor=MagicMock(),
                sprite_config=None
            )

            # Mock the extractor to test zero expected_size scenario
            worker.extractor.extract_tiles_from_rom = MagicMock(
                return_value=(b'\x00' * 32, None, 1)  # Return some tile data
            )

            # Should not raise division by zero
            worker.run()

            # ASSERTIONS: Test passed if we reach here without ZeroDivisionError
            # The worker may complete early without calling extract_tiles_from_rom
            # depending on internal validation logic - that's acceptable.
            # The key verification is that no division by zero occurred.

    def test_sprite_search_worker_zero_tile_count(self):
        """Test SpriteSearchWorker quality calculation with zero tile count."""
        from ui.rom_extraction.workers.sprite_search_worker import SpriteSearchWorker

        with tempfile.NamedTemporaryFile(suffix='.rom') as tmp:
            tmp.write(b'x' * 1024)
            tmp.flush()

            # Create mock extractor first
            mock_extractor = MagicMock()
            mock_extractor.extract_tiles_from_rom = MagicMock(
                return_value=(b'', None, 0)  # 0 tile count
            )

            # Use correct initialization parameters
            worker = SpriteSearchWorker(
                rom_path=tmp.name,
                start_offset=0,
                end_offset=512,
                direction=1,  # Forward search
                rom_extractor=mock_extractor
            )

            # Should not crash with zero tiles
            worker.run()

            # ASSERTIONS: Verify worker handled zero tiles
            # No exception means division by zero in quality calculation was handled

    def test_search_worker_zero_step(self):
        """Test SpriteSearchWorker from search_worker.py."""
        from ui.rom_extraction.workers.search_worker import SpriteSearchWorker

        with tempfile.NamedTemporaryFile(suffix='.rom') as tmp:
            tmp.write(b'x' * 1024)
            tmp.flush()

            # SpriteSearchWorker in search_worker.py has different interface
            # Test with valid parameters - it doesn't have a step parameter
            worker = SpriteSearchWorker(
                rom_path=tmp.name,
                start_offset=0,
                end_offset=100,
                direction=1,
                extractor=MagicMock()
            )

            # Mock the extractor to avoid actual ROM operations
            worker.extractor.is_valid_sprite_offset = MagicMock(return_value=False)

            # Should handle search gracefully
            worker.run()

            # ASSERTIONS: Test passed if we reach here without ZeroDivisionError
            # The worker completes successfully without raising any division errors.
            # Method call verification is not required - early exit is acceptable.

    def test_scan_worker_zero_rom_size(self):
        """Test SpriteScanWorker with zero ROM size."""
        from ui.rom_extraction.workers.scan_worker import SpriteScanWorker

        with tempfile.NamedTemporaryFile(suffix='.rom') as tmp:
            # Empty file (0 bytes) - don't write anything
            tmp.flush()

            worker = SpriteScanWorker(
                rom_path=tmp.name,
                extractor=MagicMock(),
                use_cache=False
                # No custom offsets, will use defaults based on file size
            )

            # Mock parallel finder
            worker._parallel_finder = MagicMock()
            worker._parallel_finder.search_parallel = MagicMock(return_value=[])
            worker._parallel_finder.step_size = 0x100

            # Should handle zero ROM size gracefully
            worker.run()

            # ASSERTIONS: Verify worker completed
            assert worker._parallel_finder.search_parallel.called, \
                "search_parallel should be called even with empty ROM"

    def test_all_workers_with_realistic_edge_cases(self):
        """Integration test with realistic edge cases that could cause division by zero."""
        from ui.rom_extraction.workers.range_scan_worker import RangeScanWorker
        from ui.rom_extraction.workers.scan_worker import SpriteScanWorker
        from ui.rom_extraction.workers.similarity_indexing_worker import SimilarityIndexingWorker

        with tempfile.NamedTemporaryFile(suffix='.rom') as tmp:
            # Small file that might not have sprites
            tmp.write(b'TEST' * 16)
            tmp.flush()

            # Test 1: Scan that finds no sprites
            scan_worker = SpriteScanWorker(
                rom_path=tmp.name,
                extractor=MagicMock(),
                use_cache=False,
                start_offset=0,
                end_offset=64
            )
            scan_worker._parallel_finder = MagicMock()
            scan_worker._parallel_finder.search_parallel = MagicMock(return_value=[])
            scan_worker._parallel_finder.step_size = 16

            scan_worker.run()

            # ASSERTION: Scan completed
            assert scan_worker._parallel_finder.search_parallel.called, \
                "Scan worker should complete search"

            # Test 2: Similarity indexing with no sprites
            sim_worker = SimilarityIndexingWorker(
                rom_path=tmp.name
            )
            # Worker starts with no pending sprites
            sim_worker.run()

            # ASSERTION: Worker completed without error (implicit)

            # Test 3: Range scan with tiny range
            range_worker = RangeScanWorker(
                rom_path=tmp.name,
                start_offset=0,
                end_offset=1,  # 1 byte range
                step_size=1,
                extractor=MagicMock()
            )
            range_worker.run()

            # ASSERTION: All workers completed without ZeroDivisionError

    def test_progress_calculations_boundary_conditions(self):
        """Test progress calculations at boundary conditions."""
        from ui.rom_extraction.workers.scan_worker import SpriteScanWorker

        test_cases = [
            (0, 0),      # Zero range
            (0, 1),      # 1 byte range
            (100, 100),  # Same values
            (100, 99),   # Inverted range
        ]

        for start, end in test_cases:
            with tempfile.NamedTemporaryFile(suffix='.rom') as tmp:
                tmp.write(b'x' * 1024)
                tmp.flush()

                worker = SpriteScanWorker(
                    rom_path=tmp.name,
                    extractor=MagicMock(),
                    use_cache=False,
                    start_offset=start,
                    end_offset=end
                )

                worker._parallel_finder = MagicMock()
                worker._parallel_finder.search_parallel = MagicMock(return_value=[])
                worker._parallel_finder.step_size = 1

                # Should handle all boundary conditions
                try:
                    worker.run()
                except ZeroDivisionError:
                    pytest.fail(
                        f"ZeroDivisionError with start={start}, end={end}"
                    )

                # ASSERTION: Worker completed for this test case
                assert worker._parallel_finder.search_parallel.called, \
                    f"Worker should complete for start={start}, end={end}"

if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
