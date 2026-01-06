"""
Keyboard shortcut manager for MainWindow.

Centralizes keyboard shortcut handling and provides signals for action dispatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal

if TYPE_CHECKING:
    from PySide6.QtGui import QKeyEvent


class KeyboardShortcutManager(QObject):
    """Manages keyboard shortcuts for MainWindow.

    Handles shortcut detection and emits signals for MainWindow to connect
    to appropriate action handlers. This separates the keyboard event handling
    logic from the action implementation logic.

    Signals:
        tab_switch_requested(int): Request switch to specific tab index (0-2)
        tab_next_requested(): Request switch to next tab
        tab_previous_requested(): Request switch to previous tab
        extract_requested(): Request extraction action (F5)
        mesen_capture_requested(): Request jump to Mesen capture (F6)
        manual_offset_requested(): Request manual offset dialog (Ctrl+M)
        focus_output_requested(): Request focus on output name field (Alt+N)
    """

    # Signals for actions
    tab_switch_requested = Signal(int)  # tab index (0-2)
    tab_next_requested = Signal()
    tab_previous_requested = Signal()
    extract_requested = Signal()
    mesen_capture_requested = Signal()
    manual_offset_requested = Signal()
    focus_output_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize keyboard shortcut manager.

        Args:
            parent: Parent QObject for memory management
        """
        super().__init__(parent)

    def handle_key_press(self, event: QKeyEvent) -> bool:
        """Process key event and emit appropriate signals.

        Args:
            event: The key event to process

        Returns:
            True if the event was handled, False otherwise
        """
        modifiers = event.modifiers()
        key = event.key()

        # Tab navigation: Ctrl+Tab
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_Tab:
                self.tab_next_requested.emit()
                return True

            # Ctrl+1/2/3: Direct tab switching
            if key == Qt.Key.Key_1:
                self.tab_switch_requested.emit(0)  # ROM Extraction
                return True
            if key == Qt.Key.Key_2:
                self.tab_switch_requested.emit(1)  # VRAM Extraction
                return True
            if key == Qt.Key.Key_3:
                self.tab_switch_requested.emit(2)  # Sprite Editor
                return True

            # Ctrl+M: Manual offset dialog
            if key == Qt.Key.Key_M:
                self.manual_offset_requested.emit()
                return True

        # Ctrl+Shift+Tab: Navigate to previous tab
        elif modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            if key == Qt.Key.Key_Backtab:
                self.tab_previous_requested.emit()
                return True

        # Alt+N: Focus output name field
        elif modifiers == Qt.KeyboardModifier.AltModifier:
            if key == Qt.Key.Key_N:
                self.focus_output_requested.emit()
                return True

        # F5: Extract (no modifiers)
        if key == Qt.Key.Key_F5 and modifiers == Qt.KeyboardModifier.NoModifier:
            self.extract_requested.emit()
            return True

        # F6: Jump to Mesen capture (no modifiers)
        if key == Qt.Key.Key_F6 and modifiers == Qt.KeyboardModifier.NoModifier:
            self.mesen_capture_requested.emit()
            return True

        return False
