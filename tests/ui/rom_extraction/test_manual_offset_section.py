"""Tests for ManualOffsetSection widget."""

from __future__ import annotations

from PySide6.QtCore import Qt

from ui.rom_extraction.widgets.manual_offset_section import ManualOffsetSection


def test_initial_state(qtbot):
    """Test widget initial state."""
    widget = ManualOffsetSection()
    qtbot.addWidget(widget)

    # Should start collapsed
    assert not widget.is_expanded()

    # Browse button should be hidden
    assert not widget._browse_button.isVisible()

    # Offset display should be hidden
    assert not widget._offset_display.isVisible()

    # Toggle button should have right arrow
    assert widget._toggle_button.arrowType() == Qt.ArrowType.RightArrow


def test_toggle_expand_collapse(qtbot):
    """Test expanding and collapsing the section."""
    widget = ManualOffsetSection()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)

    # Expand the section
    widget.set_expanded(True)
    assert widget.is_expanded()
    assert widget._browse_button.isVisible()
    assert widget._toggle_button.arrowType() == Qt.ArrowType.DownArrow

    # Collapse the section
    widget.set_expanded(False)
    assert not widget.is_expanded()
    assert not widget._browse_button.isVisible()
    assert widget._toggle_button.arrowType() == Qt.ArrowType.RightArrow


def test_toggle_signal_emission(qtbot):
    """Test that toggled signal is emitted correctly."""
    widget = ManualOffsetSection()
    qtbot.addWidget(widget)

    # Connect signal spy
    with qtbot.waitSignal(widget.toggled, timeout=1000) as blocker:
        widget.set_expanded(True)

    # Check signal was emitted with correct value
    assert blocker.args == [True]

    # Test collapse signal
    with qtbot.waitSignal(widget.toggled, timeout=1000) as blocker:
        widget.set_expanded(False)

    assert blocker.args == [False]


def test_browse_button_click(qtbot):
    """Test browse button click emits signal."""
    widget = ManualOffsetSection()
    qtbot.addWidget(widget)

    # Expand section to show button
    widget.set_expanded(True)

    # Click browse button
    with qtbot.waitSignal(widget.browse_clicked, timeout=1000):
        qtbot.mouseClick(widget._browse_button, Qt.MouseButton.LeftButton)


def test_offset_display_update(qtbot):
    """Test offset display updates correctly."""
    widget = ManualOffsetSection()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)

    # Initially hidden
    assert not widget._offset_display.isVisible()

    # Set offset text
    widget.set_offset_display("0x200000")
    assert widget._offset_display.isVisible()
    assert widget._offset_display.text() == "0x200000"

    # Clear offset text
    widget.set_offset_display("")
    assert not widget._offset_display.isVisible()


def test_browse_enabled_state(qtbot):
    """Test browse button enable/disable."""
    widget = ManualOffsetSection()
    qtbot.addWidget(widget)

    # Expand to access button
    widget.set_expanded(True)

    # Should start enabled
    assert widget._browse_button.isEnabled()

    # Disable button
    widget.set_browse_enabled(False)
    assert not widget._browse_button.isEnabled()

    # Re-enable button
    widget.set_browse_enabled(True)
    assert widget._browse_button.isEnabled()


def test_user_toggle_interaction(qtbot):
    """Test user clicking the toggle button."""
    widget = ManualOffsetSection()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)

    # User clicks toggle button
    with qtbot.waitSignal(widget.toggled, timeout=1000) as blocker:
        qtbot.mouseClick(widget._toggle_button, Qt.MouseButton.LeftButton)

    # Section should expand
    assert widget.is_expanded()
    assert blocker.args == [True]
    assert widget._browse_button.isVisible()

    # User clicks toggle button again
    with qtbot.waitSignal(widget.toggled, timeout=1000) as blocker:
        qtbot.mouseClick(widget._toggle_button, Qt.MouseButton.LeftButton)

    # Section should collapse
    assert not widget.is_expanded()
    assert blocker.args == [False]
    assert not widget._browse_button.isVisible()


def test_programmatic_vs_user_toggle(qtbot):
    """Test that both programmatic and user toggles work correctly."""
    widget = ManualOffsetSection()
    qtbot.addWidget(widget)

    # Programmatic expand
    widget.set_expanded(True)
    assert widget.is_expanded()

    # User collapse
    qtbot.mouseClick(widget._toggle_button, Qt.MouseButton.LeftButton)
    assert not widget.is_expanded()

    # User expand
    qtbot.mouseClick(widget._toggle_button, Qt.MouseButton.LeftButton)
    assert widget.is_expanded()

    # Programmatic collapse
    widget.set_expanded(False)
    assert not widget.is_expanded()


def test_offset_display_persists_across_toggle(qtbot):
    """Test that offset display persists when toggling section."""
    widget = ManualOffsetSection()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)

    # Set offset
    widget.set_offset_display("0x300000")
    assert widget._offset_display.isVisible()
    assert widget._offset_display.text() == "0x300000"

    # Expand/collapse should not affect offset display
    widget.set_expanded(True)
    assert widget._offset_display.isVisible()
    assert widget._offset_display.text() == "0x300000"

    widget.set_expanded(False)
    assert widget._offset_display.isVisible()
    assert widget._offset_display.text() == "0x300000"
