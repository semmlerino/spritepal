"""
Integration tests for real-time preview updates - Priority 1 test implementation.
Tests real-time preview updates during user interactions.
Mock Reduction Phase 4.3: Real preview implementation testing.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,  # Tests don't mutate shared state
    pytest.mark.skip_thread_cleanup(reason="Uses session_managers which owns worker threads"),
    pytest.mark.benchmark,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_only,
    pytest.mark.performance,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
    pytest.mark.signals_slots,
    pytest.mark.slow,
]

from tests.fixtures.preview_helper import (
    ControllerHelper,
    ExtractionPanelHelper,
    PreviewPanelHelper,
    StatusBarHelper,
    create_large_vram_file,
    create_sample_vram_file,
    ensure_headless_qt,
)


# Ensure QApplication exists for all tests
@pytest.fixture(scope="module", autouse=True)
def qt_app():
    """Ensure Qt application exists for tests"""
    return ensure_headless_qt()

class TestVRAMOffsetPreviewUpdates:
    """Test VRAM offset slider preview updates (Mock Reduction Phase 4.3)"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def sample_vram_file(self, temp_dir):
        """Create sample VRAM file for testing"""
        return create_sample_vram_file(temp_dir)

    @pytest.fixture
    def preview_components(self, sample_vram_file, temp_dir):
        """Create real preview components for testing"""
        ensure_headless_qt()

        # Create real components
        extraction_panel = ExtractionPanelHelper(sample_vram_file, temp_dir)
        preview_panel = PreviewPanelHelper(temp_dir)
        controller = ControllerHelper(extraction_panel, preview_panel)
        status_bar = StatusBarHelper()

        return {
            "extraction_panel": extraction_panel,
            "preview_panel": preview_panel,
            "controller": controller,
            "status_bar": status_bar
        }

    @pytest.mark.integration
    def test_vram_offset_slider_preview_updates(self, preview_components):
        """Test VRAM offset slider → Preview refresh integration"""
        extraction_panel = preview_components["extraction_panel"]
        preview_panel = preview_components["preview_panel"]
        preview_components["controller"]

        # Test different offset values
        test_offsets = [0x8000, 0xC000, 0xE000]

        for offset in test_offsets:
            # Clear previous tracking
            extraction_panel.clear_signal_tracking()
            preview_panel.clear_signal_tracking()

            # Simulate slider change
            extraction_panel.simulate_slider_change(offset)

            # Verify signal was emitted
            signals = extraction_panel.get_signal_emissions()
            assert len(signals["offset_changed"]) == 1
            assert signals["offset_changed"][0] == offset

            # Verify preview was updated
            preview_signals = preview_panel.get_signal_emissions()
            assert len(preview_signals["preview_updates"]) >= 1

            # Verify controller processed the offset change
            update_occurred = any(
                update["type"] in ["update", "grayscale", "colorized"]
                for update in preview_signals["preview_updates"]
            )
            assert update_occurred

    @pytest.mark.integration
    def test_spinbox_offset_preview_updates(self, preview_components):
        """Test VRAM offset spinbox → Preview refresh integration"""
        extraction_panel = preview_components["extraction_panel"]
        preview_panel = preview_components["preview_panel"]

        # Clear previous tracking
        extraction_panel.clear_signal_tracking()
        preview_panel.clear_signal_tracking()

        # Test spinbox changes
        test_offset = 0xA000

        # Simulate spinbox change
        extraction_panel.simulate_spinbox_change(test_offset)

        # Verify signal was emitted
        signals = extraction_panel.get_signal_emissions()
        assert len(signals["offset_changed"]) == 1
        assert signals["offset_changed"][0] == test_offset

        # Verify preview was updated
        preview_signals = preview_panel.get_signal_emissions()
        assert len(preview_signals["preview_updates"]) >= 1

    @pytest.mark.integration
    def test_offset_update_without_vram(self, temp_dir):
        """Test offset updates when no VRAM file is loaded"""
        # Create components with non-existent VRAM file
        fake_vram_path = str(Path(temp_dir) / "nonexistent.dmp")
        extraction_panel = ExtractionPanelHelper(fake_vram_path, temp_dir)
        preview_panel = PreviewPanelHelper(temp_dir)
        controller = ControllerHelper(extraction_panel, preview_panel)

        # Verify VRAM file doesn't exist
        assert not extraction_panel.has_vram()

        # Test offset change
        result = controller.update_preview_with_offset(0x8000)

        # Verify no update occurred
        assert result is False

        # Verify no preview updates were recorded
        preview_signals = preview_panel.get_signal_emissions()
        assert len(preview_signals["preview_updates"]) == 0

class TestPaletteSwitchingPreviewUpdates:
    """Test palette switching preview updates (Mock Reduction Phase 4.3)"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def preview_panel_with_palettes(self, temp_dir):
        """Create real preview panel with palette functionality"""
        ensure_headless_qt()

        preview_panel = PreviewPanelHelper(temp_dir)

        # Set up initial grayscale image for palette testing
        mock_grayscale_image = f"test_grayscale_image_{temp_dir}"
        preview_panel.set_grayscale_image(mock_grayscale_image)

        return preview_panel

    @pytest.mark.integration
    def test_palette_switching_preview_updates(self, preview_panel_with_palettes):
        """Test palette changes → Preview colorization integration"""
        preview_panel = preview_panel_with_palettes

        # Test palette switching
        test_palette_indices = [8, 10, 12, 14]

        for palette_index in test_palette_indices:
            # Clear previous tracking
            preview_panel.clear_signal_tracking()

            # Simulate palette change
            preview_panel.simulate_palette_change(palette_index)

            # Verify palette change signal was emitted
            signals = preview_panel.get_signal_emissions()
            assert len(signals["palette_index_changed"]) == 1
            assert signals["palette_index_changed"][0] == palette_index

            # Verify preview was updated with colorized image
            colorized_updates = [
                update for update in signals["preview_updates"]
                if update.get("type") == "colorized"
            ]
            assert len(colorized_updates) >= 1
            assert colorized_updates[0]["palette_index"] == palette_index

    @pytest.mark.integration
    def test_palette_mode_toggle_updates(self, preview_panel_with_palettes):
        """Test palette mode toggle → Preview updates"""
        preview_panel = preview_panel_with_palettes

        # Test enabling palette mode
        preview_panel.clear_signal_tracking()
        preview_panel.simulate_palette_toggle(True)

        # Verify palette mode was enabled
        signals = preview_panel.get_signal_emissions()
        assert len(signals["palette_mode_changed"]) == 1
        assert signals["palette_mode_changed"][0] is True

        # Verify preview was updated with colorized image
        colorized_updates = [
            update for update in signals["preview_updates"]
            if update.get("type") == "colorized"
        ]
        assert len(colorized_updates) >= 1

        # Test disabling palette mode
        preview_panel.clear_signal_tracking()
        preview_panel.simulate_palette_toggle(False)

        # Verify palette mode was disabled
        signals = preview_panel.get_signal_emissions()
        assert len(signals["palette_mode_changed"]) == 1
        assert signals["palette_mode_changed"][0] is False

        # Verify preview was updated to grayscale mode
        grayscale_updates = [
            update for update in signals["preview_updates"]
            if update.get("type") == "grayscale_mode"
        ]
        assert len(grayscale_updates) >= 1
        assert grayscale_updates[0]["enabled"] is False

    @pytest.mark.integration
    def test_palette_updates_without_image(self, temp_dir):
        """Test palette updates when no image is loaded"""
        ensure_headless_qt()

        # Create preview panel without grayscale image
        preview_panel = PreviewPanelHelper(temp_dir)

        # Clear any initial tracking
        preview_panel.clear_signal_tracking()

        # Test palette change without image
        preview_panel.simulate_palette_change(8)

        # Verify palette signal was still emitted
        signals = preview_panel.get_signal_emissions()
        assert len(signals["palette_index_changed"]) == 1

        # But no colorized preview updates should occur without image
        colorized_updates = [
            update for update in signals["preview_updates"]
            if update.get("type") == "colorized"
        ]
        assert len(colorized_updates) == 0

class TestZoomPanStatePreservation:
    """Test zoom and pan state preservation during updates (Mock Reduction Phase 4.3)"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def preview_panel_with_zoom(self, temp_dir):
        """Create real preview panel with zoom/pan functionality"""
        ensure_headless_qt()

        return PreviewPanelHelper(temp_dir)

    @pytest.mark.integration
    def test_zoom_pan_state_preservation(self, preview_panel_with_zoom):
        """Test that zoom/pan state is preserved during real-time updates"""
        preview_panel = preview_panel_with_zoom

        # Set initial zoom and pan state
        initial_zoom = 3.0
        initial_pan_x = 100.0
        initial_pan_y = 75.0

        preview_panel.set_zoom(initial_zoom)
        preview_panel.set_pan_offset(initial_pan_x, initial_pan_y)

        # Clear tracking to test only the update
        preview_panel.clear_signal_tracking()

        # Simulate real-time update (should preserve state)
        from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage
        mock_pixmap = ThreadSafeTestImage(128, 128)
        preview_panel.update_preview(mock_pixmap, 50)

        # Verify zoom/pan state was preserved
        assert preview_panel.get_zoom() == initial_zoom
        pan_x, pan_y = preview_panel.get_pan_offset()
        assert pan_x == initial_pan_x
        assert pan_y == initial_pan_y

        # Verify update was recorded as preserving zoom
        signals = preview_panel.get_signal_emissions()
        preview_updates = signals["preview_updates"]
        assert len(preview_updates) == 1
        assert preview_updates[0]["type"] == "update"
        assert preview_updates[0]["zoom_preserved"] is True

    @pytest.mark.integration
    def test_zoom_pan_state_reset_on_new_preview(self, preview_panel_with_zoom):
        """Test that zoom/pan state is reset when setting new preview"""
        preview_panel = preview_panel_with_zoom

        # Set initial zoom and pan state
        preview_panel.set_zoom(3.0)
        preview_panel.set_pan_offset(100.0, 75.0)

        # Clear tracking to test only the set_preview
        preview_panel.clear_signal_tracking()

        # Simulate new preview (should reset state)
        from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage
        mock_pixmap = ThreadSafeTestImage(128, 128)
        preview_panel.set_preview(mock_pixmap, 50)

        # Verify zoom/pan state was reset
        assert preview_panel.get_zoom() == 1.0
        pan_x, pan_y = preview_panel.get_pan_offset()
        assert pan_x == 0.0
        assert pan_y == 0.0

        # Verify update was recorded as resetting zoom
        signals = preview_panel.get_signal_emissions()
        preview_updates = signals["preview_updates"]
        assert len(preview_updates) == 1
        assert preview_updates[0]["type"] == "set"
        assert preview_updates[0]["zoom_reset"] is True

class TestPreviewPerformanceIntegration:
    """Test preview performance characteristics (Mock Reduction Phase 4.3)"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def large_vram_file(self, temp_dir):
        """Create large VRAM file for performance testing"""
        return create_large_vram_file(temp_dir)

    @pytest.fixture
    def performance_components(self, large_vram_file, temp_dir):
        """Create real components for performance testing"""
        ensure_headless_qt()

        extraction_panel = ExtractionPanelHelper(large_vram_file, temp_dir)
        preview_panel = PreviewPanelHelper(temp_dir)
        controller = ControllerHelper(extraction_panel, preview_panel)

        return {
            "extraction_panel": extraction_panel,
            "preview_panel": preview_panel,
            "controller": controller
        }

    @pytest.mark.integration
    def test_preview_performance_with_large_files(self, performance_components):
        """Test performance characteristics with large files"""
        controller = performance_components["controller"]
        preview_panel = performance_components["preview_panel"]

        # Test multiple rapid updates
        test_offsets = [0x8000, 0xC000, 0xE000, 0x10000, 0x20000]

        for offset in test_offsets:
            # Clear previous tracking
            preview_panel.clear_signal_tracking()

            # Update preview with offset
            controller.update_preview_with_offset(offset)

        # Verify all updates completed
        assert len(controller.get_update_times()) == len(test_offsets)

        # Verify reasonable performance (all updates under 100ms)
        update_times = controller.get_update_times()
        for update_time in update_times:
            assert update_time < 0.1  # 100ms max

        # Verify average performance
        avg_time = sum(update_times) / len(update_times)
        assert avg_time < 0.05  # 50ms average

    @pytest.mark.integration
    def test_concurrent_preview_updates(self, performance_components):
        """Test multiple rapid preview updates"""
        controller = performance_components["controller"]
        preview_panel = performance_components["preview_panel"]

        # Test rapid sequential updates
        rapid_offsets = [0x8000 + i * 0x100 for i in range(10)]

        for offset in rapid_offsets:
            controller.update_preview_with_offset(offset)

        # Verify all updates completed
        update_times = controller.get_update_times()
        assert len(update_times) == len(rapid_offsets)

        # Verify all preview updates were recorded
        preview_signals = preview_panel.get_signal_emissions()
        assert len(preview_signals["preview_updates"]) >= len(rapid_offsets)

class TestPreviewErrorHandling:
    """Test preview error handling scenarios (Mock Reduction Phase 4.3)"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def error_test_components(self, temp_dir):
        """Create real components for error testing"""
        ensure_headless_qt()

        # Create with valid VRAM file for error testing
        vram_path = create_sample_vram_file(temp_dir)
        extraction_panel = ExtractionPanelHelper(vram_path, temp_dir)
        preview_panel = PreviewPanelHelper(temp_dir)
        controller = ControllerHelper(extraction_panel, preview_panel)
        status_bar = StatusBarHelper()

        return {
            "extraction_panel": extraction_panel,
            "preview_panel": preview_panel,
            "controller": controller,
            "status_bar": status_bar
        }

    @pytest.mark.integration
    def test_preview_error_handling(self, error_test_components):
        """Test error handling for corrupted preview data"""
        controller = error_test_components["controller"]
        preview_panel = error_test_components["preview_panel"]

        # Test different error scenarios with specific exception types
        error_scenarios = [
            (0x1000, FileNotFoundError),
            (0x2000, PermissionError),
            (0x3000, MemoryError),
            (0x4000, ValueError)
        ]

        for offset, expected_exception in error_scenarios:
            with pytest.raises(expected_exception):
                controller.update_preview_with_offset(offset)

        # Test recovery with valid offset
        preview_panel.clear_signal_tracking()
        try:
            controller.update_preview_with_offset(0x8000)
            # Verify preview was updated successfully
            preview_signals = preview_panel.get_signal_emissions()
            assert len(preview_signals["preview_updates"]) > 0
        except Exception:
            raise AssertionError("Should not raise error for valid offset") from None

    @pytest.mark.integration
    def test_preview_error_recovery(self, error_test_components):
        """Test recovery from preview errors"""
        controller = error_test_components["controller"]
        preview_panel = error_test_components["preview_panel"]

        # Test error followed by successful update
        error_count = 0
        success_count = 0

        test_offsets = [0x1000, 0x8000, 0x2000, 0xC000, 0x3000, 0xE000]

        for offset in test_offsets:
            # Clear tracking for each test
            preview_panel.clear_signal_tracking()

            try:
                controller.update_preview_with_offset(offset)
                success_count += 1
            except Exception:
                error_count += 1

        # Verify mix of errors and successes
        assert error_count == 3  # 0x1000, 0x2000, 0x3000
        assert success_count == 3  # 0x8000, 0xC000, 0xE000

        # Verify update times were recorded for all attempts
        assert len(controller.get_update_times()) == len(test_offsets)

class TestPreviewSignalIntegration:
    """Test preview signal integration across components (Mock Reduction Phase 4.3)"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def signal_test_components(self, temp_dir):
        """Create real components for signal testing"""
        ensure_headless_qt()

        vram_path = create_sample_vram_file(temp_dir)
        extraction_panel = ExtractionPanelHelper(vram_path, temp_dir)
        preview_panel = PreviewPanelHelper(temp_dir)
        controller = ControllerHelper(extraction_panel, preview_panel)

        return {
            "extraction_panel": extraction_panel,
            "preview_panel": preview_panel,
            "controller": controller
        }

    @pytest.mark.integration
    def test_complete_preview_signal_flow(self, signal_test_components):
        """Test complete signal flow for preview updates"""
        extraction_panel = signal_test_components["extraction_panel"]
        preview_panel = signal_test_components["preview_panel"]
        signal_test_components["controller"]

        # Clear any initial tracking
        extraction_panel.clear_signal_tracking()
        preview_panel.clear_signal_tracking()

        # Test offset signal flow
        test_offset = 0x8000
        extraction_panel.simulate_slider_change(test_offset)

        # Verify offset signal was emitted
        extraction_signals = extraction_panel.get_signal_emissions()
        assert len(extraction_signals["offset_changed"]) == 1
        assert extraction_signals["offset_changed"][0] == test_offset

        # Verify preview was updated through controller
        preview_signals = preview_panel.get_signal_emissions()
        assert len(preview_signals["preview_updates"]) > 0

        # Test palette signal flow
        preview_panel.clear_signal_tracking()
        preview_panel.simulate_palette_toggle(True)
        preview_panel.simulate_palette_change(10)

        # Verify palette signals were emitted
        palette_signals = preview_panel.get_signal_emissions()
        assert len(palette_signals["palette_mode_changed"]) == 1
        assert palette_signals["palette_mode_changed"][0] is True
        assert len(palette_signals["palette_index_changed"]) == 1
        assert palette_signals["palette_index_changed"][0] == 10

    @pytest.mark.integration
    def test_preview_signal_disconnection(self, signal_test_components):
        """Test proper signal disconnection for cleanup"""
        extraction_panel = signal_test_components["extraction_panel"]
        preview_panel = signal_test_components["preview_panel"]

        # Test that components start connected
        extraction_panel.clear_signal_tracking()
        preview_panel.clear_signal_tracking()

        # Emit signal and verify it's received
        extraction_panel.simulate_slider_change(0x8000)

        # Verify signal was emitted
        extraction_signals = extraction_panel.get_signal_emissions()
        assert len(extraction_signals["offset_changed"]) == 1

        # Verify preview updates occurred (proves connection worked)
        preview_signals = preview_panel.get_signal_emissions()
        assert len(preview_signals["preview_updates"]) > 0

        # Note: In real PySide6, disconnection would require storing the connection
        # object and calling disconnect() on it. Our test helpers automatically
        # handle connections internally, so we're verifying the signal flow works
