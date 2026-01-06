"""
Tests for KeyboardShortcutManager.

Tests shortcut detection and signal emission for all supported shortcuts.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

from ui.managers.keyboard_shortcut_manager import KeyboardShortcutManager


def test_tab_switch_ctrl_1(qtbot):
    """Test Ctrl+1 emits tab_switch_requested with index 0."""
    manager = KeyboardShortcutManager()

    with qtbot.waitSignal(manager.tab_switch_requested) as blocker:
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
        handled = manager.handle_key_press(event)

    assert handled is True
    assert blocker.args == [0]


def test_tab_switch_ctrl_2(qtbot):
    """Test Ctrl+2 emits tab_switch_requested with index 1."""
    manager = KeyboardShortcutManager()

    with qtbot.waitSignal(manager.tab_switch_requested) as blocker:
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
        handled = manager.handle_key_press(event)

    assert handled is True
    assert blocker.args == [1]


def test_tab_switch_ctrl_3(qtbot):
    """Test Ctrl+3 emits tab_switch_requested with index 2."""
    manager = KeyboardShortcutManager()

    with qtbot.waitSignal(manager.tab_switch_requested) as blocker:
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_3, Qt.KeyboardModifier.ControlModifier)
        handled = manager.handle_key_press(event)

    assert handled is True
    assert blocker.args == [2]


def test_tab_next_ctrl_tab(qtbot):
    """Test Ctrl+Tab emits tab_next_requested."""
    manager = KeyboardShortcutManager()

    with qtbot.waitSignal(manager.tab_next_requested):
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
        handled = manager.handle_key_press(event)

    assert handled is True


def test_tab_previous_ctrl_shift_tab(qtbot):
    """Test Ctrl+Shift+Tab emits tab_previous_requested."""
    manager = KeyboardShortcutManager()

    with qtbot.waitSignal(manager.tab_previous_requested):
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Backtab,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        handled = manager.handle_key_press(event)

    assert handled is True


def test_extract_f5(qtbot):
    """Test F5 emits extract_requested."""
    manager = KeyboardShortcutManager()

    with qtbot.waitSignal(manager.extract_requested):
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier)
        handled = manager.handle_key_press(event)

    assert handled is True


def test_mesen_capture_f6(qtbot):
    """Test F6 emits mesen_capture_requested."""
    manager = KeyboardShortcutManager()

    with qtbot.waitSignal(manager.mesen_capture_requested):
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_F6, Qt.KeyboardModifier.NoModifier)
        handled = manager.handle_key_press(event)

    assert handled is True


def test_manual_offset_ctrl_m(qtbot):
    """Test Ctrl+M emits manual_offset_requested."""
    manager = KeyboardShortcutManager()

    with qtbot.waitSignal(manager.manual_offset_requested):
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier)
        handled = manager.handle_key_press(event)

    assert handled is True


def test_focus_output_alt_n(qtbot):
    """Test Alt+N emits focus_output_requested."""
    manager = KeyboardShortcutManager()

    with qtbot.waitSignal(manager.focus_output_requested):
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_N, Qt.KeyboardModifier.AltModifier)
        handled = manager.handle_key_press(event)

    assert handled is True


def test_unhandled_key():
    """Test that unhandled keys return False."""
    manager = KeyboardShortcutManager()

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
    handled = manager.handle_key_press(event)

    assert handled is False


def test_f5_with_modifier_not_handled():
    """Test that F5 with modifiers is not handled."""
    manager = KeyboardShortcutManager()

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_F5, Qt.KeyboardModifier.ControlModifier)
    handled = manager.handle_key_press(event)

    assert handled is False


def test_f6_with_modifier_not_handled():
    """Test that F6 with modifiers is not handled."""
    manager = KeyboardShortcutManager()

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_F6, Qt.KeyboardModifier.ShiftModifier)
    handled = manager.handle_key_press(event)

    assert handled is False


def test_digit_without_ctrl_not_handled():
    """Test that digit keys without Ctrl are not handled."""
    manager = KeyboardShortcutManager()
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier)
    handled = manager.handle_key_press(event)
    assert handled is False


def test_signal_connections(qtbot):
    """Test that all signals can be connected to slots."""
    manager = KeyboardShortcutManager()

    # Track which signals fired
    signals_fired = []

    manager.tab_switch_requested.connect(lambda idx: signals_fired.append(("tab_switch", idx)))
    manager.tab_next_requested.connect(lambda: signals_fired.append("tab_next"))
    manager.tab_previous_requested.connect(lambda: signals_fired.append("tab_previous"))
    manager.extract_requested.connect(lambda: signals_fired.append("extract"))
    manager.mesen_capture_requested.connect(lambda: signals_fired.append("mesen_capture"))
    manager.manual_offset_requested.connect(lambda: signals_fired.append("manual_offset"))
    manager.focus_output_requested.connect(lambda: signals_fired.append("focus_output"))

    # Trigger each shortcut
    shortcuts = [
        (Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier, ("tab_switch", 0)),
        (Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier, "tab_next"),
        (Qt.Key.Key_Backtab, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier, "tab_previous"),
        (Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier, "extract"),
        (Qt.Key.Key_F6, Qt.KeyboardModifier.NoModifier, "mesen_capture"),
        (Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier, "manual_offset"),
        (Qt.Key.Key_N, Qt.KeyboardModifier.AltModifier, "focus_output"),
    ]

    for key, modifiers, expected_signal in shortcuts:
        event = QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers)
        manager.handle_key_press(event)

    assert signals_fired == [
        ("tab_switch", 0),
        "tab_next",
        "tab_previous",
        "extract",
        "mesen_capture",
        "manual_offset",
        "focus_output",
    ]
