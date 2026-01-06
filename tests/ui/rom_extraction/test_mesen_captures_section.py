"""Tests for MesenCapturesSection widget."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from core.mesen_integration.log_watcher import CapturedOffset
from tests.fixtures.timeouts import signal_timeout
from ui.rom_extraction.widgets.mesen_captures_section import MesenCapturesSection


@pytest.fixture
def captures_section(app_context, qtbot):
    """Create a MesenCapturesSection widget for testing."""
    widget = MesenCapturesSection()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def sample_capture():
    """Create a sample CapturedOffset for testing."""
    return CapturedOffset(
        offset=0x3C6EF1,
        frame=1800,
        timestamp=datetime.now(),
        raw_line="FILE OFFSET: 0x3C6EF1 frame=1800",
    )


@pytest.fixture
def sample_captures():
    """Create multiple sample captures for testing."""
    return [
        CapturedOffset(
            offset=0x3C6EF1,
            frame=1800,
            timestamp=datetime.now(),
            raw_line="FILE OFFSET: 0x3C6EF1 frame=1800",
        ),
        CapturedOffset(
            offset=0x3C7000,
            frame=1900,
            timestamp=datetime.now(),
            raw_line="FILE OFFSET: 0x3C7000 frame=1900",
        ),
        CapturedOffset(
            offset=0x3C7200,
            frame=2000,
            timestamp=datetime.now(),
            raw_line="FILE OFFSET: 0x3C7200 frame=2000",
        ),
    ]


class TestMesenCapturesSection:
    """Test suite for MesenCapturesSection widget."""

    def test_initialization(self, captures_section):
        """Test widget initializes correctly."""
        assert captures_section is not None
        assert captures_section._captures_widget is not None

    def test_add_capture(self, captures_section, sample_capture):
        """Test adding a capture to the widget."""
        # Initially no selected offset
        assert captures_section.get_selected_offset() is None

        # Add a capture
        captures_section.add_capture(sample_capture)

        # Verify the internal widget received it
        assert captures_section._captures_widget._list_widget.count() == 1

    def test_add_multiple_captures(self, captures_section, sample_captures):
        """Test adding multiple captures."""
        for capture in sample_captures:
            captures_section.add_capture(capture)

        # Verify all captures were added
        assert captures_section._captures_widget._list_widget.count() == len(sample_captures)

    def test_load_persistent(self, captures_section, sample_captures):
        """Test loading persistent captures."""
        captures_section.load_persistent(sample_captures)

        # Verify captures were loaded
        assert captures_section._captures_widget._list_widget.count() == len(sample_captures)

    def test_load_persistent_empty_list(self, captures_section):
        """Test loading empty persistent captures list."""
        captures_section.load_persistent([])

        # Should handle gracefully with no crashes
        assert captures_section._captures_widget._list_widget.count() == 0

    def test_clear(self, captures_section, sample_captures):
        """Test clearing all captures."""
        # Add some captures
        for capture in sample_captures:
            captures_section.add_capture(capture)
        assert captures_section._captures_widget._list_widget.count() > 0

        # Clear
        captures_section.clear()

        # Verify cleared
        assert captures_section._captures_widget._list_widget.count() == 0
        assert captures_section.get_selected_offset() is None

    def test_get_selected_offset_none(self, captures_section):
        """Test getting selected offset when nothing is selected."""
        assert captures_section.get_selected_offset() is None

    def test_get_selected_offset(self, captures_section, sample_capture, qtbot):
        """Test getting selected offset after user selection."""
        # Add a capture
        captures_section.add_capture(sample_capture)

        # Simulate user clicking on the item
        list_widget = captures_section._captures_widget._list_widget
        item = list_widget.item(0)
        list_widget.setCurrentItem(item)

        # Verify we can get the selected offset
        selected = captures_section.get_selected_offset()
        assert selected == sample_capture.offset

    def test_set_watching_true(self, captures_section, qtbot):
        """Test setting watching state to True."""
        with qtbot.waitSignal(captures_section.watching_changed, timeout=signal_timeout()) as blocker:
            captures_section.set_watching(True)

        # Verify signal emitted with correct value
        assert blocker.args == [True]

    def test_set_watching_false(self, captures_section, qtbot):
        """Test setting watching state to False."""
        with qtbot.waitSignal(captures_section.watching_changed, timeout=signal_timeout()) as blocker:
            captures_section.set_watching(False)

        # Verify signal emitted with correct value
        assert blocker.args == [False]

    def test_offset_selected_signal_forwarding(self, captures_section, sample_capture, qtbot):
        """Test that offset_selected signal is forwarded from RecentCapturesWidget."""
        # Add a capture
        captures_section.add_capture(sample_capture)

        # Simulate user clicking on the item
        list_widget = captures_section._captures_widget._list_widget
        item = list_widget.item(0)

        with qtbot.waitSignal(captures_section.offset_selected, timeout=signal_timeout()) as blocker:
            list_widget.itemClicked.emit(item)

        # Verify signal was forwarded with correct offset
        assert blocker.args == [sample_capture.offset]

    def test_offset_activated_signal_forwarding(self, captures_section, sample_capture, qtbot):
        """Test that offset_activated signal is forwarded from RecentCapturesWidget."""
        # Add a capture
        captures_section.add_capture(sample_capture)

        # Simulate user double-clicking on the item
        list_widget = captures_section._captures_widget._list_widget
        item = list_widget.item(0)

        with qtbot.waitSignal(captures_section.offset_activated, timeout=signal_timeout()) as blocker:
            list_widget.itemDoubleClicked.emit(item)

        # Verify signal was forwarded with correct offset
        assert blocker.args == [sample_capture.offset]

    def test_save_to_library_requested_signal_forwarding(self, captures_section, sample_capture, qtbot):
        """Test that save_to_library_requested signal is forwarded from RecentCapturesWidget."""
        # Add a capture
        captures_section.add_capture(sample_capture)

        # Directly emit the signal from the internal widget (simulates context menu action)
        with qtbot.waitSignal(captures_section.save_to_library_requested, timeout=signal_timeout()) as blocker:
            captures_section._captures_widget.save_to_library_requested.emit(sample_capture.offset)

        # Verify signal was forwarded with correct offset
        assert blocker.args == [sample_capture.offset]

    def test_no_app_context_access(self, captures_section):
        """Test that widget does not access AppContext directly."""
        # Read the widget source code to verify no get_app_context calls
        import inspect

        source = inspect.getsource(MesenCapturesSection)
        assert "get_app_context" not in source, "Widget should not access AppContext directly"

    def test_parent_wiring_pattern(self, app_context, qtbot, sample_capture):
        """Test the expected parent wiring pattern for log_watcher integration.

        This test demonstrates how ROMExtractionPanel should wire up the widget.
        """
        # Create widget
        widget = MesenCapturesSection()
        qtbot.addWidget(widget)

        # Parent would get log_watcher from AppContext
        log_watcher = app_context.log_watcher

        # Parent connects log_watcher signals to widget methods
        log_watcher.offset_discovered.connect(widget.add_capture)
        log_watcher.watch_started.connect(lambda: widget.set_watching(True))
        log_watcher.watch_stopped.connect(lambda: widget.set_watching(False))

        # Parent also connects widget signals to its own handlers
        widget.offset_selected.connect(Mock())
        widget.offset_activated.connect(Mock())

        # Simulate log_watcher emitting a signal
        log_watcher.offset_discovered.emit(sample_capture)

        # Verify the widget received it
        assert widget._captures_widget._list_widget.count() == 1
