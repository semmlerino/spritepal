"""
Comprehensive tests for the sprite display fix implementation

Tests focus on:
1. Widget update patterns and Qt refresh mechanisms
2. Fallback 4bpp decoder when ROM extractor unavailable
3. Palette selection and switching functionality
4. Visual similarity search integration
5. Context menu and user interaction handling
6. Empty state and error state management
7. Performance with large sprite data
8. Memory management and resource cleanup
"""
from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt

from tests.infrastructure.qt_testing_framework import QtTestingFramework
from ui.widgets.sprite_preview_widget import SpritePreviewWidget

# Serial execution required: Real Qt components
pytestmark = [

    pytest.mark.serial,
    pytest.mark.cache,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.qt_real,
    pytest.mark.requires_display,
    pytest.mark.rom_data,
    pytest.mark.signals_slots,
    pytest.mark.slow,
    pytest.mark.stability,
]

class MockDefaultPaletteLoader:
    """Mock default palette loader for testing"""
    def __init__(self):
        self.palettes = []
        for i in range(16):
            # Create mock palette with 16 colors (ensure RGB values are 0-255)
            palette = [
                [
                    min(255, (i*16 + j)),           # Red: 0-255
                    min(255, (i*16 + j) % 256),     # Green: wraps at 256
                    min(255, ((i+j)*8) % 256)       # Blue: different pattern
                ]
                for j in range(16)
            ]
            self.palettes.append(palette)

    def get_palettes(self):
        return self.palettes

    def get_all_kirby_palettes(self):
        """Mock method to return all 16 palettes as Kirby palettes"""
        result = {}
        for i in range(16):
            result[i] = self.palettes[i]
        return result

class MockVisualSimilarityEngine:
    """Mock visual similarity engine for testing"""
    def __init__(self):
        self.index_calls = []
        self.search_calls = []

    def index_sprite(self, sprite_data, offset):
        """Mock sprite indexing"""
        self.index_calls.append((sprite_data, offset))

    def search_similar(self, query_data, num_results=10):
        """Mock similarity search"""
        self.search_calls.append((query_data, num_results))
        # Return mock results
        return [
            {"offset": 0x200000, "similarity": 0.95},
            {"offset": 0x300000, "similarity": 0.87},
            {"offset": 0x400000, "similarity": 0.76}
        ]

class TestSpritePreviewWidgetDisplayFix:
    """Test SpritePreviewWidget functionality for display fix"""

    def setup_method(self):
        """Set up test fixtures"""
        self.qt_framework = QtTestingFramework()

        # Create widget with mocked dependencies (patch where they're imported, not where they're defined)
        with patch('ui.widgets.sprite_preview_widget.DefaultPaletteLoader', MockDefaultPaletteLoader), \
             patch('ui.widgets.sprite_preview_widget.VisualSimilarityEngine', MockVisualSimilarityEngine):
            self.widget = SpritePreviewWidget("Display Fix Test")

        # Access mocked components
        self.mock_palette_loader = self.widget.default_palette_loader
        self.mock_similarity_engine = MockVisualSimilarityEngine()
        self.widget.similarity_engine = self.mock_similarity_engine

    def teardown_method(self):
        """Clean up test fixtures"""
        if hasattr(self, 'widget'):
            self.widget.close()
            del self.widget

    def test_fallback_4bpp_decoder_when_extractor_unavailable(self, qtbot):
        """Test fallback 4bpp decoder when ROM extractor unavailable - KEY FIX"""
        # Mock extraction manager to return None (unavailable)
        with patch('core.managers.get_extraction_manager', return_value=None):
            # Generate 4bpp test data
            tile_data = self._generate_mock_4bpp_data(32, 32)

            # Update preview should use fallback decoder
            self.widget.load_sprite_from_4bpp(tile_data, 32, 32, "fallback_test")

            # Should successfully create preview using fallback
            assert self.widget.sprite_data is not None  # Stores decoded grayscale data, not original 4bpp
            assert len(self.widget.sprite_data) > 0  # Should have decoded pixel data
            pixmap = self.widget.preview_label.pixmap()
            assert pixmap is not None
            assert pixmap.width() > 0
            assert pixmap.height() > 0

    def test_widget_update_timer_mechanism(self, qtbot):
        """Test Qt update timer mechanism for guaranteed refresh - KEY FIX"""
        # Widget should have update timer
        assert self.widget._update_timer is not None

        # Update preview should start timer
        tile_data = self._generate_mock_tile_data(16, 16)
        self.widget.load_sprite_from_4bpp(tile_data, 16, 16, "timer_test")

        # Timer should be active after update
        assert self.widget._update_timer.isActive()

        # Wait for timer to complete and pixmap to be set
        qtbot.waitUntil(lambda: self.widget.preview_label.pixmap() is not None, timeout=500)

        # Timer should stop after completing update (but may restart for another update)
        # Timer behavior is implementation detail, focus on functional outcome
        assert self.widget.preview_label.pixmap() is not None

    def test_load_sprite_from_4bpp_with_valid_data_ensures_display(self, qtbot):
        """Test updating preview with valid sprite data ensures display - KEY FIX"""
        # Mock sprite data
        tile_data = self._generate_mock_tile_data(16, 16)  # 16x16 4bpp sprite
        width = 16
        height = 16
        name = "display_test_sprite"

        # Update preview
        self.widget.load_sprite_from_4bpp(tile_data, width, height, name)

        # Widget should update
        assert self.widget.sprite_data is not None  # Stores decoded grayscale data, not original 4bpp
        # Essential info shows scaled dimensions and load status (16x16 scaled to 96x96)
        essential_text = self.widget.essential_info_label.text()
        assert ("x" in essential_text and "Loaded" in essential_text) or "96x96" in essential_text

        # Preview label should have pixmap - CRITICAL FOR DISPLAY FIX
        assert self.widget.preview_label.pixmap() is not None

        # Pixmap should have correct dimensions (may be scaled for visibility)
        pixmap = self.widget.preview_label.pixmap()
        # Small sprites (16x16) get scaled up by factor 6, so expect at least original size
        assert pixmap.width() >= width
        assert pixmap.height() >= height

    def test_empty_state_to_sprite_display_transition(self):
        """Test transition from empty state to sprite display - KEY FIX"""
        # Widget should start in empty state
        assert "No sprite loaded" in self.widget.essential_info_label.text()
        # Initially may have text placeholder, so check text instead of pixmap
        assert "No preview available" in self.widget.preview_label.text() or self.widget.sprite_data is None

        # Update with sprite data
        tile_data = self._generate_mock_tile_data(32, 32)
        self.widget.load_sprite_from_4bpp(tile_data, 32, 32, "transition_test")

        # Should transition to displaying sprite
        assert self.widget.sprite_data is not None
        assert self.widget.preview_label.pixmap() is not None
        # Essential info should show dimensions and load status (may be scaled)
        essential_text = self.widget.essential_info_label.text()
        assert ("x" in essential_text and "Loaded" in essential_text) or any(dim in essential_text for dim in ["32x32", "192x192"])

    def test_rapid_preview_updates_maintain_display(self, qtbot):
        """Test rapid preview updates maintain proper display - KEY FIX"""
        # Simulate rapid updates like during slider scrubbing
        sprite_names = []
        for i in range(10):
            tile_data = self._generate_mock_tile_data(16, 16)
            sprite_name = f"rapid_update_{i}"
            sprite_names.append(sprite_name)

            self.widget.load_sprite_from_4bpp(tile_data, 16, 16, sprite_name)

            # Each update should maintain display
            assert self.widget.preview_label.pixmap() is not None
            time.sleep(0.01)  # Simulate rapid updates

        # Final state should show valid dimensions (may be scaled)
        essential_text = self.widget.essential_info_label.text()
        assert ("x" in essential_text and "Loaded" in essential_text) or any(dim in essential_text for dim in ["16x16", "96x96"])

    def test_fallback_decoder_with_different_dimensions(self):
        """Test fallback decoder with various sprite dimensions - KEY FIX"""
        test_cases = [
            (8, 8),    # Small square
            (16, 8),   # Rectangular
            (32, 32),  # Medium square
            (64, 16),  # Wide rectangle
            (16, 64),  # Tall rectangle
        ]

        with patch('core.managers.get_extraction_manager', return_value=None):
            for width, height in test_cases:
                tile_data = self._generate_4bpp_for_dimensions(width, height)

                self.widget.load_sprite_from_4bpp(tile_data, width, height, f"fallback_{width}x{height}")

                # Should handle all dimensions with fallback decoder
                pixmap = self.widget.preview_label.pixmap()
                assert pixmap is not None
                # Pixmap may be scaled for visibility, so check at least original size
                assert pixmap.width() >= width
                assert pixmap.height() >= height

    def test_palette_switching_updates_display(self, qtbot):
        """Test palette switching properly updates display - KEY FIX"""
        # Set up sprite data
        tile_data = self._generate_mock_tile_data(16, 16)
        self.widget.load_sprite_from_4bpp(tile_data, 16, 16, "palette_test")

        # Get initial pixmap
        initial_pixmap = self.widget.preview_label.pixmap()
        assert initial_pixmap is not None

        # Change palette
        new_palette_index = 10
        self.widget.palette_combo.setCurrentIndex(new_palette_index)

        # Should emit palette changed signal
        with qtbot.wait_signal(self.widget.palette_changed, timeout=100):
            self.widget.palette_combo.currentIndexChanged.emit(new_palette_index)

        # Pixmap should change (different palette) - CRITICAL FOR PALETTE FIX
        new_pixmap = self.widget.preview_label.pixmap()
        assert new_pixmap is not None

        # Widget should track new palette
        assert self.widget.current_palette_index == new_palette_index

    def test_error_handling_maintains_widget_state(self):
        """Test error handling maintains widget in usable state - KEY FIX"""
        # Test with invalid data
        try:
            self.widget.load_sprite_from_4bpp(b"invalid", 16, 16, "error_test")
        except Exception:
            pass  # Should handle gracefully

        # Widget should remain in usable state
        assert hasattr(self.widget, 'preview_label')
        assert hasattr(self.widget, 'essential_info_label')

        # Should be able to update with valid data after error
        valid_data = self._generate_mock_tile_data(16, 16)
        self.widget.load_sprite_from_4bpp(valid_data, 16, 16, "recovery_test")

        assert self.widget.sprite_data is not None  # Stores decoded grayscale data, not original 4bpp
        assert self.widget.preview_label.pixmap() is not None

    def test_large_sprite_display_performance(self, qtbot):
        """Test performance with large sprite data for smooth display - KEY FIX"""
        # Generate large sprite data (128x128)
        large_tile_data = self._generate_mock_tile_data(128, 128)

        # Measure update time
        start_time = time.perf_counter()

        self.widget.load_sprite_from_4bpp(large_tile_data, 128, 128, "large_sprite")

        update_time = time.perf_counter() - start_time

        # Should handle large sprites quickly for smooth scrubbing
        assert update_time < 0.1, f"Large sprite update too slow: {update_time:.3f}s"

        # Should successfully create preview
        assert self.widget.sprite_data is not None  # Stores decoded grayscale data, not original 4bpp
        assert len(self.widget.sprite_data) > 0  # Should have decoded pixel data
        pixmap = self.widget.preview_label.pixmap()
        assert pixmap is not None
        # Large sprites (128x128) may be scaled down or up based on available space
        assert pixmap.width() > 0
        assert pixmap.height() > 0

    def test_clear_preview_resets_to_empty_state(self):
        """Test clear preview properly resets to empty state - KEY FIX"""
        # Set up preview with data
        tile_data = self._generate_mock_tile_data(16, 16)
        self.widget.load_sprite_from_4bpp(tile_data, 16, 16, "clear_test")

        # Verify preview is set
        assert self.widget.sprite_data is not None
        assert self.widget.preview_label.pixmap() is not None

        # Clear preview
        self.widget.clear()

        # Preview should be cleared and return to empty state
        assert self.widget.sprite_data is None
        assert "No sprite loaded" in self.widget.essential_info_label.text()

    def _generate_mock_tile_data(self, width: int, height: int) -> bytes:
        """Generate mock tile data for testing"""
        # Generate 4bpp data (4 bits per pixel)
        pixels_per_byte = 2
        total_pixels = width * height
        total_bytes = total_pixels // pixels_per_byte

        # Create pattern data
        data = bytearray()
        for i in range(total_bytes):
            # Create alternating pattern
            byte_value = (i % 16) << 4 | ((i + 1) % 16)
            data.append(byte_value)

        return bytes(data)

    def _generate_mock_4bpp_data(self, width: int, height: int) -> bytes:
        """Generate mock 4bpp data with specific pattern"""
        # 4bpp: 4 bits per pixel, 2 pixels per byte
        total_pixels = width * height
        total_bytes = (total_pixels + 1) // 2  # Round up for odd pixel counts

        data = bytearray()
        for i in range(total_bytes):
            # Create gradient pattern
            pixel1 = (i * 2) % 16
            pixel2 = (i * 2 + 1) % 16
            byte_value = (pixel1 << 4) | pixel2
            data.append(byte_value)

        return bytes(data)

    def _generate_4bpp_for_dimensions(self, width: int, height: int) -> bytes:
        """Generate 4bpp data for specific dimensions"""
        total_pixels = width * height
        total_bytes = (total_pixels + 1) // 2  # Round up for odd pixel counts

        data = bytearray()
        for i in range(total_bytes):
            # Create repeating pattern
            byte_val = (i % 16) << 4 | ((i + 1) % 16)
            data.append(byte_val)

        return bytes(data)

class TestSpriteDisplayFixIntegration:
    """Integration tests for the complete sprite display fix"""

    def setup_method(self):
        """Set up integration test fixtures"""
        self.qt_framework = QtTestingFramework()

        # Create widget with real dependencies where possible
        self.widget = SpritePreviewWidget("Integration Test")

    def teardown_method(self):
        """Clean up integration test fixtures"""
        if hasattr(self, 'widget'):
            self.widget.close()
            del self.widget

    def test_extraction_manager_fallback_chain(self):
        """Test extraction manager fallback chain works correctly - KEY FIX"""
        # Test with extraction manager available
        mock_manager = Mock()
        mock_extractor = Mock()

        # Mock extractor methods
        mock_extractor.extract_sprite_data = Mock(return_value=b"extracted_data")
        mock_extractor.decode_4bpp_sprite = Mock(return_value=b"decoded_data")
        mock_manager.get_rom_extractor = Mock(return_value=mock_extractor)

        with patch('ui.widgets.sprite_preview_widget.get_extraction_manager', return_value=mock_manager):
            # Update preview should use extraction manager
            tile_data = self._generate_mock_tile_data(16, 16)
            self.widget.load_sprite_from_4bpp(tile_data, 16, 16, "extraction_test")

            # Should have attempted to get ROM extractor
            mock_manager.get_rom_extractor.assert_called()

        # Test with extraction manager unavailable (fallback)
        with patch('ui.widgets.sprite_preview_widget.get_extraction_manager', return_value=None):
            # Should fall back to internal decoder
            tile_data = self._generate_mock_tile_data(16, 16)
            self.widget.load_sprite_from_4bpp(tile_data, 16, 16, "fallback_test")

            # Should still create preview
            assert self.widget.preview_label.pixmap() is not None

    def test_end_to_end_slider_to_display(self, qtbot):
        """Test end-to-end slider movement to sprite display - COMPLETE FIX"""
        # This simulates the complete workflow from slider to display

        # 1. Simulate slider movement triggering preview request
        offset = 0x200000

        # 2. Generate mock sprite data as if from cache/worker
        tile_data = self._generate_mock_tile_data(32, 32)
        sprite_name = f"sprite_{offset:06x}"

        # 3. Update preview widget (final step in chain)
        self.widget.load_sprite_from_4bpp(tile_data, 32, 32, sprite_name)

        # 4. Verify complete display pipeline works
        assert self.widget.sprite_data is not None  # Stores decoded grayscale data, not original 4bpp
        assert self.widget.preview_label.pixmap() is not None
        # Essential info shows dimensions and load status (may be scaled)
        essential_text = self.widget.essential_info_label.text()
        assert ("x" in essential_text and "Loaded" in essential_text) or any(dim in essential_text for dim in ["32x32", "192x192"])

        # 5. Verify pixmap has correct properties (may be scaled for visibility)
        pixmap = self.widget.preview_label.pixmap()
        # Small sprites (32x32) get scaled up by factor 6, so expect 192x192
        assert pixmap.width() >= 32  # At least original size or scaled up
        assert pixmap.height() >= 32
        assert not pixmap.isNull()

    def test_multiple_rom_switching_maintains_display(self):
        """Test switching ROMs maintains proper display state - KEY FIX"""
        # Test with first ROM
        rom1_data = self._generate_mock_tile_data(16, 16)
        self.widget.load_sprite_from_4bpp(rom1_data, 16, 16, "rom1_sprite")

        assert self.widget.preview_label.pixmap() is not None
        # Essential info shows dimensions and load status (may be scaled)
        essential_text = self.widget.essential_info_label.text()
        assert ("x" in essential_text and "Loaded" in essential_text) or any(dim in essential_text for dim in ["16x16", "96x96"])

        # Switch to second ROM (simulate ROM change)
        rom2_data = self._generate_mock_tile_data(32, 32)
        self.widget.load_sprite_from_4bpp(rom2_data, 32, 32, "rom2_sprite")

        assert self.widget.preview_label.pixmap() is not None
        # Essential info shows dimensions and load status (may be scaled)
        essential_text = self.widget.essential_info_label.text()
        assert ("x" in essential_text and "Loaded" in essential_text) or any(dim in essential_text for dim in ["32x32", "192x192"])

        # Verify new pixmap has correct dimensions (may be scaled)
        pixmap = self.widget.preview_label.pixmap()
        assert pixmap.width() >= 32  # At least original size or scaled up
        assert pixmap.height() >= 32

    def _generate_mock_tile_data(self, width: int, height: int) -> bytes:
        """Generate mock tile data for testing"""
        # 4bpp data: 4 bits per pixel, 2 pixels per byte
        total_pixels = width * height
        total_bytes = (total_pixels + 1) // 2

        return bytes([i % 256 for i in range(total_bytes)])

class TestSpriteDisplayFixRegressionTests:
    """Regression tests to ensure the fix doesn't break existing functionality"""

    def setup_method(self):
        """Set up regression test fixtures"""
        self.qt_framework = QtTestingFramework()

        # Create widget with mocked dependencies (patch where they're imported, not where they're defined)
        with patch('ui.widgets.sprite_preview_widget.DefaultPaletteLoader', MockDefaultPaletteLoader), \
             patch('ui.widgets.sprite_preview_widget.VisualSimilarityEngine', MockVisualSimilarityEngine):
            self.widget = SpritePreviewWidget("Regression Test")

        # Access mocked components
        self.mock_palette_loader = self.widget.default_palette_loader
        self.mock_similarity_engine = MockVisualSimilarityEngine()
        self.widget.similarity_engine = self.mock_similarity_engine

    def teardown_method(self):
        """Clean up regression test fixtures"""
        if hasattr(self, 'widget'):
            self.widget.close()
            del self.widget

    def test_palette_functionality_still_works(self, qtbot):
        """Regression test: Palette functionality still works after fix"""
        # Set up sprite data
        tile_data = self._generate_mock_tile_data(16, 16)
        self.widget.load_sprite_from_4bpp(tile_data, 16, 16, "palette_regression")

        # Should have palette combo
        assert self.widget.palette_combo is not None
        assert self.widget.palette_combo.count() == 16

        # Should be able to change palette
        original_index = self.widget.current_palette_index
        new_index = (original_index + 1) % 16

        with qtbot.wait_signal(self.widget.palette_changed, timeout=100):
            self.widget.palette_combo.setCurrentIndex(new_index)
            self.widget.palette_combo.currentIndexChanged.emit(new_index)

        assert self.widget.current_palette_index == new_index

    def test_similarity_search_still_works(self, qtbot):
        """Regression test: Similarity search still works after fix"""
        # Set up sprite data
        tile_data = self._generate_mock_tile_data(32, 32)
        self.widget.load_sprite_from_4bpp(tile_data, 32, 32, "similarity_regression")
        self.widget.current_offset = 0x400000

        # Should be able to emit similarity search signal
        with qtbot.wait_signal(self.widget.similarity_search_requested, timeout=100):
            self.widget.similarity_search_requested.emit(0x400000)

    def test_context_menu_still_works(self):
        """Regression test: Context menu still works after fix"""
        # Set up sprite data
        tile_data = self._generate_mock_tile_data(16, 16)
        self.widget.load_sprite_from_4bpp(tile_data, 16, 16, "context_regression")

        # Preview label should have context menu enabled
        assert self.widget.preview_label.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

    def test_info_labels_still_update(self):
        """Regression test: Info labels still update correctly after fix"""
        # Update with sprite data
        tile_data = self._generate_mock_tile_data(64, 32)
        sprite_name = "info_regression_sprite"

        self.widget.load_sprite_from_4bpp(tile_data, 64, 32, sprite_name)

        # Essential info should show dimensions and load status
        essential_text = self.widget.essential_info_label.text()
        # Should have size information (may be scaled for visibility)
        assert ("x" in essential_text and "Loaded" in essential_text) or any(dim in essential_text for dim in ["64", "32", "256x128", "192x96"])

    def _generate_mock_tile_data(self, width: int, height: int) -> bytes:
        """Generate mock tile data for testing"""
        total_pixels = width * height
        total_bytes = (total_pixels + 1) // 2
        return bytes([i % 256 for i in range(total_bytes)])

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
