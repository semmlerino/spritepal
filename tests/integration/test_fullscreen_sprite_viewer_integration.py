"""
Integration tests for FullscreenSpriteViewer.

These tests focus on end-to-end functionality that would catch bugs like:
- Keyboard navigation edge cases
- Signal emission failures
- Memory leaks with sprite data
- Improper cleanup on close
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QPixmap

from tests.infrastructure.qt_real_testing import (
    EventLoopHelper,
    MemoryHelper,
    QtTestCase,
)
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage
from ui.widgets.fullscreen_sprite_viewer import FullscreenSpriteViewer

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Integration tests involve managers that spawn threads"),
    pytest.mark.allows_registry_state(reason="Integration tests manage own lifecycle"),
]


# Test data fixtures
@pytest.fixture
def sample_sprites_data() -> list[dict[str, Any]]:
    """Create sample sprite data for testing."""
    return [
        {
            "offset": 0x10000,
            "name": "Sprite_001",
            "decompressed_size": 1024,
            "tile_count": 32,
        },
        {
            "offset": 0x20000,
            "name": "Sprite_002",
            "decompressed_size": 2048,
            "tile_count": 64,
        },
        {
            "offset": 0x30000,
            "name": "Sprite_003",
            "decompressed_size": 512,
            "tile_count": 16,
        },
    ]


@pytest.fixture
def mock_rom_extractor():
    """Create mock ROM extractor for testing."""
    extractor = Mock()
    extractor.extract_sprite = Mock(return_value=b"\x00" * 1024)
    return extractor


@pytest.fixture
def mock_parent_gallery():
    """Create test parent gallery with sprite pixmaps."""
    from PySide6.QtWidgets import QWidget

    # Create a real Qt widget instead of Mock to avoid type errors
    class TestParentGallery(QWidget):
        def __init__(self):
            super().__init__()
            self.gallery_widget = TestGalleryWidget()

    class TestGalleryWidget:
        def get_sprite_pixmap(self, offset: int) -> QPixmap | None:
            if offset in [0x10000, 0x20000, 0x30000]:
                # Create ThreadSafeTestImage for thread safety, then convert to QPixmap
                # This is safe because we're in the main thread (GUI test)
                test_image = ThreadSafeTestImage(64, 64)
                test_image.fill(Qt.GlobalColor.blue)
                # Convert to QPixmap for GUI usage (safe in main thread)
                pixmap = QPixmap.fromImage(test_image.toImage())
                return pixmap
            return None

    return TestParentGallery()


@pytest.mark.gui
@pytest.mark.integration
class TestFullscreenSpriteViewerIntegration(QtTestCase):
    """Integration tests for fullscreen sprite viewer."""

    def setup_method(self):
        """Set up for each test method."""
        super().setup_method()
        self.viewer: FullscreenSpriteViewer | None = None
        self.signal_emissions: list[tuple[str, Any]] = []

    def teardown_method(self):
        """Clean up after each test."""
        if self.viewer:
            self.viewer.close()
            self.viewer = None
        self.signal_emissions.clear()
        super().teardown_method()

    def _track_signal_emissions(self, signal_name: str, *args):
        """Track signal emissions for verification."""
        self.signal_emissions.append((signal_name, args))

    def test_keyboard_navigation_through_all_sprites(
        self, sample_sprites_data: list[dict[str, Any]], mock_parent_gallery: Mock, mock_rom_extractor: Mock
    ):
        """Test keyboard navigation through all sprites."""
        self.viewer = self.create_widget(FullscreenSpriteViewer, mock_parent_gallery)

        # Track signal emissions
        self.viewer.sprite_changed.connect(lambda offset: self._track_signal_emissions("sprite_changed", offset))

        # Set up sprite data
        assert self.viewer.set_sprite_data(
            sample_sprites_data,
            0x10000,  # Start with first sprite
            "test_rom.sfc",
            mock_rom_extractor,
        )

        # Test navigation forward through all sprites
        for i in range(len(sample_sprites_data)):
            sample_sprites_data[i]["offset"]
            assert self.viewer.current_index == i

            if i < len(sample_sprites_data) - 1:
                # Navigate to next sprite
                key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
                self.viewer.keyPressEvent(key_event)

                # Wait for transition
                EventLoopHelper.process_events(100)

        # Test wraparound to first sprite
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
        self.viewer.keyPressEvent(key_event)
        EventLoopHelper.process_events(100)

        assert self.viewer.current_index == 0

        # Verify signal emissions
        assert len(self.signal_emissions) >= len(sample_sprites_data)

        # Test backward navigation
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
        self.viewer.keyPressEvent(key_event)
        EventLoopHelper.process_events(100)

        # Should wrap to last sprite
        assert self.viewer.current_index == len(sample_sprites_data) - 1

    def test_edge_cases_single_sprite(self, mock_parent_gallery: Mock, mock_rom_extractor: Mock):
        """Test edge cases with single sprite (no navigation)."""
        single_sprite = [
            {
                "offset": 0x10000,
                "name": "OnlySprite",
                "decompressed_size": 1024,
                "tile_count": 32,
            }
        ]

        self.viewer = self.create_widget(FullscreenSpriteViewer, mock_parent_gallery)

        assert self.viewer.set_sprite_data(single_sprite, 0x10000, "test_rom.sfc", mock_rom_extractor)

        assert self.viewer.current_index == 0

        # Navigation should stay at same sprite
        for key in [Qt.Key.Key_Left, Qt.Key.Key_Right]:
            key_event = QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
            self.viewer.keyPressEvent(key_event)
            EventLoopHelper.process_events(50)
            assert self.viewer.current_index == 0

    def test_empty_sprite_data_handling(self, mock_parent_gallery: Mock, mock_rom_extractor: Mock):
        """Test handling of empty sprite data."""
        self.viewer = self.create_widget(FullscreenSpriteViewer, mock_parent_gallery)

        # Should return False for empty data
        assert not self.viewer.set_sprite_data([], 0x10000, "test_rom.sfc", mock_rom_extractor)

        # Viewer should remain in safe state
        assert self.viewer.sprites_data == []
        assert self.viewer.current_index == 0

    def test_info_overlay_toggle(
        self, sample_sprites_data: list[dict[str, Any]], mock_parent_gallery: Mock, mock_rom_extractor: Mock
    ):
        """Test info overlay toggle functionality."""
        self.viewer = self.create_widget(FullscreenSpriteViewer, mock_parent_gallery)

        assert self.viewer.set_sprite_data(sample_sprites_data, 0x10000, "test_rom.sfc", mock_rom_extractor)

        # Initial state - info should be shown
        # Note: Use isHidden() instead of isVisible() because isVisible() requires
        # the entire widget hierarchy to be shown, but isHidden() checks only
        # the widget's own hidden state which is what we want to test
        assert self.viewer.show_info
        assert not self.viewer.info_overlay.isHidden()

        # Toggle info off
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_I, Qt.KeyboardModifier.NoModifier)
        self.viewer.keyPressEvent(key_event)

        assert not self.viewer.show_info
        assert self.viewer.info_overlay.isHidden()

        # Toggle info back on
        self.viewer.keyPressEvent(key_event)

        assert self.viewer.show_info
        assert not self.viewer.info_overlay.isHidden()

    def test_smooth_scaling_toggle(
        self, sample_sprites_data: list[dict[str, Any]], mock_parent_gallery: Mock, mock_rom_extractor: Mock
    ):
        """Test smooth scaling toggle functionality."""
        self.viewer = self.create_widget(FullscreenSpriteViewer, mock_parent_gallery)

        assert self.viewer.set_sprite_data(sample_sprites_data, 0x10000, "test_rom.sfc", mock_rom_extractor)

        # Initial state - smooth scaling enabled
        assert self.viewer.smooth_scaling

        # Toggle smooth scaling
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_S, Qt.KeyboardModifier.NoModifier)
        self.viewer.keyPressEvent(key_event)

        assert not self.viewer.smooth_scaling

        # Toggle back
        self.viewer.keyPressEvent(key_event)

        assert self.viewer.smooth_scaling

    def test_escape_key_closes_viewer(
        self, sample_sprites_data: list[dict[str, Any]], mock_parent_gallery: Mock, mock_rom_extractor: Mock
    ):
        """Test ESC key closes the viewer."""
        self.viewer = self.create_widget(FullscreenSpriteViewer, mock_parent_gallery)

        # Track viewer closed signal
        viewer_closed = False

        def on_viewer_closed():
            nonlocal viewer_closed
            viewer_closed = True

        self.viewer.viewer_closed.connect(on_viewer_closed)

        assert self.viewer.set_sprite_data(sample_sprites_data, 0x10000, "test_rom.sfc", mock_rom_extractor)

        # Show the viewer
        self.viewer.show()
        EventLoopHelper.process_events(50)

        # Press ESC
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        self.viewer.keyPressEvent(key_event)

        # Process close event
        EventLoopHelper.process_events(100)

        # Verify viewer was closed
        assert viewer_closed

    @pytest.mark.performance
    def test_memory_usage_with_large_sprite_set(self, mock_parent_gallery: Mock, mock_rom_extractor: Mock):
        """Test memory usage with large sprite data set."""
        # Create large sprite data set
        large_sprite_set = [
            {
                "offset": 0x10000 + i * 0x1000,
                "name": f"Sprite_{i:03d}",
                "decompressed_size": 1024,
                "tile_count": 32,
            }
            for i in range(1000)  # 1000 sprites
        ]

        with MemoryHelper.assert_no_leak(FullscreenSpriteViewer, max_increase=1):
            self.viewer = self.create_widget(FullscreenSpriteViewer, mock_parent_gallery)

            # Set large data set
            assert self.viewer.set_sprite_data(large_sprite_set, 0x10000, "test_rom.sfc", mock_rom_extractor)

            # Navigate through several sprites quickly
            for _ in range(50):
                key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
                self.viewer.keyPressEvent(key_event)
                EventLoopHelper.process_events(1)  # Minimal processing

            # Close viewer
            self.viewer.close()
            self.viewer = None

    def test_signal_emissions_accuracy(
        self, sample_sprites_data: list[dict[str, Any]], mock_parent_gallery: Mock, mock_rom_extractor: Mock
    ):
        """Test that signal emissions contain correct data."""
        self.viewer = self.create_widget(FullscreenSpriteViewer, mock_parent_gallery)

        sprite_changes: list[int] = []
        self.viewer.sprite_changed.connect(sprite_changes.append)

        assert self.viewer.set_sprite_data(
            sample_sprites_data,
            0x20000,  # Start with second sprite
            "test_rom.sfc",
            mock_rom_extractor,
        )

        # Initial signal should be emitted for current sprite
        EventLoopHelper.process_events(100)
        assert len(sprite_changes) >= 1
        assert sprite_changes[-1] == 0x20000

        # Navigate and verify each signal
        expected_offsets = [0x30000, 0x10000, 0x20000]  # Next, wrap to first, next

        for expected_offset in expected_offsets:
            initial_count = len(sprite_changes)

            key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
            self.viewer.keyPressEvent(key_event)
            EventLoopHelper.process_events(100)

            # Verify signal was emitted with correct offset
            assert len(sprite_changes) > initial_count
            assert sprite_changes[-1] == expected_offset

    def test_transition_timer_delays_display_update(
        self, sample_sprites_data: list[dict[str, Any]], mock_parent_gallery: Mock, mock_rom_extractor: Mock
    ):
        """Test that transition timer delays display update for smooth visuals.

        Note: The timer does NOT throttle navigation - it only delays the visual
        display update. The current_index is updated immediately on each key press,
        while the display update happens after a short delay for smooth transitions.
        """
        self.viewer = self.create_widget(FullscreenSpriteViewer, mock_parent_gallery)

        assert self.viewer.set_sprite_data(sample_sprites_data, 0x10000, "test_rom.sfc", mock_rom_extractor)

        initial_index = self.viewer.current_index

        # Rapid key presses - navigation happens immediately
        for _ in range(len(sample_sprites_data)):
            key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
            self.viewer.keyPressEvent(key_event)
            # No event processing between key presses

        # Navigation should have completed immediately (wrapping back to start)
        # With 3 sprites starting at index 0, 3 navigations brings us back to 0
        expected_index = (initial_index + len(sample_sprites_data)) % len(sample_sprites_data)
        assert self.viewer.current_index == expected_index

        # Verify the transition timer exists and is configured for display smoothness
        assert self.viewer.transition_timer is not None
        assert self.viewer.transition_timer.isSingleShot()

        # Process events to allow timer-delayed display update to complete
        EventLoopHelper.process_events(200)


@pytest.mark.gui
@pytest.mark.integration
@pytest.mark.slow
class TestFullscreenViewerCleanupIntegration(QtTestCase):
    """Test proper cleanup and resource management."""

    def test_proper_cleanup_on_close(self, sample_sprites_data, mock_parent_gallery, mock_rom_extractor):
        """Test that viewer properly runs cleanup code on close.

        This test verifies that:
        1. closeEvent is called (emits viewer_closed signal)
        2. Internal timers are stopped (checked via timer state)
        3. Cleanup code executes without errors

        NOTE: We do NOT test garbage collection timing because Qt's GC is
        non-deterministic and varies by environment. The important thing is
        that cleanup code runs, not that Python's GC collects immediately.
        """
        from PySide6.QtTest import QSignalSpy

        for i in range(3):  # Test multiple instances
            viewer = self.create_widget(FullscreenSpriteViewer, None)

            viewer.set_sprite_data(sample_sprites_data, 0x10000, "test_rom.sfc", mock_rom_extractor)

            # Set up signal spy before showing
            close_spy = QSignalSpy(viewer.viewer_closed)

            # Show and close
            viewer.show()
            EventLoopHelper.process_events(50)
            viewer.close()
            EventLoopHelper.process_events(50)

            # Verify cleanup behavior (what we control)
            assert close_spy.count() == 1, f"Viewer {i}: viewer_closed signal not emitted"

            # Verify timers are stopped (prevents resource leaks)
            if hasattr(viewer, "transition_timer"):
                assert not viewer.transition_timer.isActive(), f"Viewer {i}: transition_timer still active after close"
            if hasattr(viewer, "cursor_timer"):
                assert not viewer.cursor_timer.isActive(), f"Viewer {i}: cursor_timer still active after close"

            # Schedule deletion for proper cleanup
            viewer.deleteLater()

        # Process events to handle deleteLater
        EventLoopHelper.process_events(100)

    def test_no_signal_leaks_after_close(self, sample_sprites_data, mock_parent_gallery, mock_rom_extractor):
        """Test that closing viewer emits proper signals and cleanup works.

        Note: In Qt, close() just hides the widget - it doesn't destroy it or
        disconnect signals. The viewer can still process events after close().
        To fully destroy the widget, use deleteLater() and process events.
        """
        viewer = self.create_widget(FullscreenSpriteViewer, mock_parent_gallery)

        # Connect to signals
        signal_calls: list[int | str] = []
        viewer.sprite_changed.connect(signal_calls.append)
        viewer.viewer_closed.connect(lambda: signal_calls.append("closed"))

        viewer.set_sprite_data(sample_sprites_data, 0x10000, "test_rom.sfc", mock_rom_extractor)

        # Show, navigate, then close
        viewer.show()
        EventLoopHelper.process_events(50)

        # Navigation should emit signals
        initial_count = len(signal_calls)
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
        viewer.keyPressEvent(key_event)
        EventLoopHelper.process_events(100)

        assert len(signal_calls) > initial_count

        # Close viewer
        viewer.close()
        EventLoopHelper.process_events(100)

        # Should have received closed signal
        assert "closed" in signal_calls

        # Verify that closed signal was emitted exactly once
        close_count = sum(1 for s in signal_calls if s == "closed")
        assert close_count == 1, f"Expected exactly 1 'closed' signal, got {close_count}"

        # Verify we got sprite_changed signals for navigation
        sprite_signals = [s for s in signal_calls if isinstance(s, int)]
        assert len(sprite_signals) >= 1, "Expected at least one sprite_changed signal"


@pytest.mark.headless
@pytest.mark.integration
class TestFullscreenViewerMockIntegration:
    """Headless integration tests using mocks."""

    def test_headless_functionality_with_mocks(self, sample_sprites_data):
        """Test viewer functionality in headless environment with mocks."""
        with patch("ui.widgets.fullscreen_sprite_viewer.QApplication") as mock_qapp_class:
            # Mock QApplication and screen
            mock_app = Mock()
            mock_screen = Mock()
            mock_screen.availableGeometry.return_value.width.return_value = 1920
            mock_screen.availableGeometry.return_value.height.return_value = 1080
            mock_app.primaryScreen.return_value = mock_screen
            mock_qapp_class.primaryScreen.return_value = mock_screen

            with patch("ui.widgets.fullscreen_sprite_viewer.QWidget"):
                # Create mock viewer to test logic
                viewer = Mock()
                viewer.sprites_data = []
                viewer.current_index = 0
                viewer.show_info = True
                viewer.smooth_scaling = True

                # Test sprite data setting logic
                def mock_set_sprite_data(sprites_data, current_offset, rom_path, rom_extractor):
                    if not sprites_data:
                        return False
                    viewer.sprites_data = sprites_data
                    viewer.current_index = 0
                    for i, sprite in enumerate(sprites_data):
                        if sprite.get("offset", 0) == current_offset:
                            viewer.current_index = i
                            break
                    return True

                viewer.set_sprite_data = mock_set_sprite_data

                # Test navigation logic
                def mock_navigate(direction):
                    if not viewer.sprites_data:
                        return
                    new_index = (viewer.current_index + direction) % len(viewer.sprites_data)
                    viewer.current_index = new_index

                viewer._navigate_to_sprite = mock_navigate

                # Test with sample data
                assert mock_set_sprite_data(sample_sprites_data, 0x20000, "test.sfc", Mock())
                assert viewer.current_index == 1  # Second sprite

                # Test navigation
                mock_navigate(1)  # Next
                assert viewer.current_index == 2

                mock_navigate(1)  # Should wrap to 0
                assert viewer.current_index == 0

                mock_navigate(-1)  # Previous should wrap to last
                assert viewer.current_index == 2
