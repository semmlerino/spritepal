"""
Keyboard shortcut handling for MainWindow
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QKeyEvent

if TYPE_CHECKING:
    from ui.managers.output_settings_manager import OutputSettingsManager
    from ui.managers.tab_coordinator import TabCoordinator
    from ui.managers.toolbar_manager import ToolbarManager

class KeyboardActionsProtocol(Protocol):
    """Protocol defining the interface for keyboard actions"""

    def on_extract_clicked(self) -> None:
        """Handle extract action"""
        ...

    def can_open_manual_offset_dialog(self) -> bool:
        """Check if manual offset dialog can be opened"""
        ...

    def open_manual_offset_dialog(self) -> None:
        """Open manual offset dialog"""
        ...

class KeyboardShortcutHandler(QObject):
    """Handles keyboard shortcuts for MainWindow"""

    def __init__(
        self,
        tab_coordinator: TabCoordinator,
        output_settings_manager: OutputSettingsManager,
        toolbar_manager: ToolbarManager,
        actions_handler: KeyboardActionsProtocol
    ) -> None:
        """Initialize keyboard shortcut handler

        Args:
            tab_coordinator: Tab coordinator for tab navigation
            output_settings_manager: Output settings manager for focus shortcuts
            toolbar_manager: Toolbar manager for button state checks
            actions_handler: Handler for keyboard actions
        """
        super().__init__()
        self.tab_coordinator = tab_coordinator
        self.output_settings_manager = output_settings_manager
        self.toolbar_manager = toolbar_manager
        self.actions_handler = actions_handler

    def handle_key_press_event(self, event: QKeyEvent) -> bool:
        """Handle keyboard shortcut events

        Args:
            event: Key press event

        Returns:
            True if event was handled, False otherwise
        """
        # Tab navigation
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_Tab:
                # Ctrl+Tab: Next tab
                self._navigate_to_next_tab()
                event.accept()
                return True
        elif event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            if event.key() == Qt.Key.Key_Backtab:
                # Ctrl+Shift+Tab: Previous tab
                self._navigate_to_previous_tab()
                event.accept()
                return True

        # F5 as alternative to Extract
        if event.key() == Qt.Key.Key_F5 and self.toolbar_manager.extract_button.isEnabled():
            self.actions_handler.on_extract_clicked()
            event.accept()
            return True

        # Ctrl+M: Open Manual Offset Control (if in ROM extraction mode)
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_M:
                if self.actions_handler.can_open_manual_offset_dialog():
                    self.actions_handler.open_manual_offset_dialog()
                    event.accept()
                    return True

        # Focus shortcuts
        if event.modifiers() == Qt.KeyboardModifier.AltModifier:
            if event.key() == Qt.Key.Key_N:
                # Alt+N: Focus output name field (if inline UI exists)
                output_edit = getattr(self.output_settings_manager, "output_name_edit", None)
                if output_edit is not None:
                    output_edit.setFocus()
                    output_edit.selectAll()
                    event.accept()
                    return True

        return False

    def _navigate_to_next_tab(self) -> None:
        """Navigate to next tab"""
        current = self.tab_coordinator.get_current_tab_index()
        tab_count = self.tab_coordinator.extraction_tabs.count()
        next_tab = (current + 1) % tab_count
        self.tab_coordinator.extraction_tabs.setCurrentIndex(next_tab)

    def _navigate_to_previous_tab(self) -> None:
        """Navigate to previous tab"""
        current = self.tab_coordinator.get_current_tab_index()
        tab_count = self.tab_coordinator.extraction_tabs.count()
        prev_tab = (current - 1) % tab_count
        self.tab_coordinator.extraction_tabs.setCurrentIndex(prev_tab)
