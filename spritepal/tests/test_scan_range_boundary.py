"""
Test to verify that ROM scanning correctly includes the end offset boundary.
This test validates the fix for the off-by-one error in scan range iteration.
"""
from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest

from core.parallel_sprite_finder import ParallelSpriteFinder
from core.rom_extractor import ROMExtractor

pytestmark = [
    pytest.mark.unit,
    pytest.mark.headless,
    pytest.mark.rom_data,
]

class TestScanRangeBoundary:
    """Test that scan ranges are inclusive of the end offset."""

    def test_rom_extractor_includes_end_offset(self):
        """Test that ROMExtractor.scan_for_sprites includes the end offset."""
        extractor = ROMExtractor()

        # Create mock ROM data with sprites at specific offsets
        rom_size = 0xF0100  # Just past 0xF0000
        mock_rom_data = b'\x00' * rom_size

        found_offsets = []

        def mock_try_extract(rom_data, offset):
            """Track which offsets are checked."""
            found_offsets.append(offset)
            # Return sprite info for specific offsets
            if offset in [0xEFF00, 0xF0000]:  # Last two positions with step 0x100
                return {
                    'offset': offset,
                    'tile_count': 16,
                    'compressed_size': 512,
                    'alignment': 'perfect'
                }
            return None

        # Need to patch the full scan method flow
        with patch('builtins.open', mock_open(read_data=mock_rom_data)):
            with patch.object(extractor, '_validate_rom_data', return_value=mock_rom_data):
                with patch.object(extractor, '_load_cached_scan', return_value=None):
                    with patch.object(extractor, '_get_resume_state', return_value=([], 0xEFE00)):
                        with patch('core.rom_extractor.get_rom_cache') as mock_cache:
                            mock_cache.return_value = Mock(save_partial_scan_results=Mock())
                            with patch.object(extractor, '_try_extract_sprite_at_offset', side_effect=mock_try_extract):
                                # Scan from 0xEFE00 to 0xF0000 with step 0x100
                                results = extractor.scan_for_sprites(
                                    'test.rom',
                                    start_offset=0xEFE00,
                                    end_offset=0xF0000,
                                    step=0x100
                                )

        # Verify that 0xF0000 was actually checked
        assert 0xF0000 in found_offsets, f"End offset 0xF0000 was not scanned! Offsets checked: {[hex(o) for o in found_offsets]}"
        assert 0xEFF00 in found_offsets, "Second-to-last offset should be checked"

        # Verify we found sprites at both positions
        assert len(results) == 2, f"Should find 2 sprites but found {len(results)}"
        result_offsets = [r['offset'] for r in results]
        assert 0xEFF00 in result_offsets
        assert 0xF0000 in result_offsets

    def test_parallel_finder_includes_chunk_boundaries(self):
        """Test that ParallelSpriteFinder includes chunk end boundaries."""
        finder = ParallelSpriteFinder(num_workers=1, chunk_size=0x1000, step_size=0x100)

        # Create mock ROM data
        rom_size = 0x2000
        mock_rom_data = b'\x00' * rom_size

        checked_offsets = []

        def mock_find_sprite(rom_data, offset):
            """Track which offsets are checked."""
            checked_offsets.append(offset)
            # Return sprite at chunk boundaries
            if offset in [0x0FF0, 0x1000, 0x1FF0]:  # Near and at chunk boundaries
                return {
                    'decompressed_size': 512,
                    'tile_count': 16,
                    'compressed_size': 256
                }
            return None

        with patch('builtins.open', mock_open(read_data=mock_rom_data)):
            with patch.object(finder.sprite_finders[0], 'find_sprite_at_offset', side_effect=mock_find_sprite):
                # Mock quick check to always pass
                with patch.object(finder, '_quick_sprite_check', return_value=True):
                    # Search from 0 to 0x2000 (two chunks)
                    results = finder.search_parallel(
                        'test.rom',
                        start_offset=0,
                        end_offset=0x2000
                    )

        # Verify chunk boundaries are checked
        # With chunk_size=0x1000, chunks are [0, 0x1000) and [0x1000, 0x2000)
        # The boundary at 0x1000 should be checked by the second chunk
        assert any(offset >= 0x1000 for offset in checked_offsets), \
            f"No offsets >= 0x1000 were checked! Checked: {[hex(o) for o in checked_offsets]}"

        # Should find sprites at the boundaries
        assert len(results) >= 2, f"Should find at least 2 sprites but found {len(results)}"

    def test_scan_worker_cache_resume_uses_correct_step(self):
        """Test that scan worker uses correct step size when resuming from cache."""
        from ui.rom_extraction.workers.scan_worker import SpriteScanWorker

        # Create worker with custom step size
        worker = SpriteScanWorker(
            rom_path='test.rom',
            extractor=Mock(),
            use_cache=True
        )

        # The parallel finder should have step_size attribute
        assert hasattr(worker._parallel_finder, 'step_size')

        # Mock cache with partial results
        last_scanned_offset = 0xD0000
        mock_partial_cache = {
            'found_sprites': [],
            'current_offset': last_scanned_offset
        }

        with patch('ui.rom_extraction.workers.scan_worker.get_rom_cache') as mock_get_cache:
            mock_cache = Mock()
            mock_cache.get_partial_scan_results.return_value = mock_partial_cache
            mock_get_cache.return_value = mock_cache

            with patch.object(worker._parallel_finder, 'search_parallel', return_value=[]) as mock_search:
                worker.run()

                # Verify that search was called with correct start offset
                # It should resume from last_offset + step_size (not hardcoded 0x100)
                call_args = mock_search.call_args
                actual_start = call_args[1]['start_offset']
                expected_start = last_scanned_offset + worker._parallel_finder.step_size

                assert actual_start == expected_start, \
                    f"Resume offset should be {hex(expected_start)} but was {hex(actual_start)}"

def mock_open(read_data=None):
    """Create a mock file object."""
    mock = MagicMock()
    mock.read.return_value = read_data
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = None
    return mock
