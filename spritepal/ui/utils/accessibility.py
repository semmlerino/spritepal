"""
Accessibility utilities for SpritePal UI components.
Provides helpers for keyboard navigation, screen reader support, and focus management.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QToolBar,
    QWidget,
)

from ui.styles.theme import COLORS


class AccessibilityHelper:
    """Helper class for adding accessibility features to Qt widgets."""

    # Standard keyboard shortcuts for common actions
    STANDARD_SHORTCUTS = {
        'open': QKeySequence.StandardKey.Open,
        'save': QKeySequence.StandardKey.Save,
        'save_as': QKeySequence.StandardKey.SaveAs,
        'close': QKeySequence.StandardKey.Close,
        'quit': QKeySequence.StandardKey.Quit,
        'undo': QKeySequence.StandardKey.Undo,
        'redo': QKeySequence.StandardKey.Redo,
        'cut': QKeySequence.StandardKey.Cut,
        'copy': QKeySequence.StandardKey.Copy,
        'paste': QKeySequence.StandardKey.Paste,
        'find': QKeySequence.StandardKey.Find,
        'refresh': QKeySequence.StandardKey.Refresh,
        'help': QKeySequence.StandardKey.HelpContents,
        'fullscreen': 'F11',
        'escape': 'Escape',
        'extract': 'Ctrl+E',
        'inject': 'Ctrl+I',
        'scan': 'Ctrl+Shift+S',
        'export': 'Ctrl+Shift+E',
        'goto': 'Ctrl+G',
        'preview': 'Ctrl+P',
        'settings': 'Ctrl+,',
        'zoom_in': 'Ctrl++',
        'zoom_out': 'Ctrl+-',
        'zoom_reset': 'Ctrl+0',
    }

    @staticmethod
    def make_accessible(
        widget: QWidget,
        name: str,
        description: str = "",
        shortcut: str | None = None,
        role: str | None = None
    ) -> QWidget:
        """
        Make a widget accessible with proper naming and descriptions.

        Args:
            widget: The widget to make accessible
            name: Accessible name for screen readers
            description: Longer description of the widget's purpose
            shortcut: Keyboard shortcut (if applicable)
            role: Accessibility role (if needed to override default)

        Returns:
            The widget with accessibility features added
        """
        # Set accessible name and description
        widget.setAccessibleName(name)
        if description:
            widget.setAccessibleDescription(description)
        elif shortcut:
            widget.setAccessibleDescription(f"{name} ({shortcut})")

        # Enable keyboard focus for interactive widgets
        if isinstance(widget, (QPushButton, QLineEdit, QSpinBox, QComboBox,
                               QSlider, QCheckBox, QRadioButton, QTextEdit,
                               QPlainTextEdit)):
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Add keyboard shortcut if provided
        if shortcut:
            try:
                widget.setShortcut(shortcut)  # type: ignore[attr-defined]
            except AttributeError:
                pass  # Widget doesn't support shortcuts

        # Add tooltip with shortcut info
        if shortcut:
            current_tooltip = widget.toolTip()
            if current_tooltip:
                widget.setToolTip(f"{current_tooltip} ({shortcut})")
            else:
                widget.setToolTip(f"{name} ({shortcut})")

        return widget

    @staticmethod
    def create_label_input_pair(
        label_text: str,
        input_widget: QWidget,
        description: str = "",
        mnemonic_char: str | None = None
    ) -> tuple[QLabel, QWidget]:
        """
        Create a properly linked label-input pair for accessibility.

        Args:
            label_text: Text for the label
            input_widget: The input widget to link to
            description: Description for screen readers
            mnemonic_char: Character to use for Alt+key access (auto-detected if None)

        Returns:
            Tuple of (label, input_widget) with accessibility features
        """
        # Add mnemonic if not present
        if '&' not in label_text:
            if mnemonic_char:
                # Use specified character
                idx = label_text.lower().find(mnemonic_char.lower())
                if idx >= 0:
                    label_text = label_text[:idx] + '&' + label_text[idx:]
                else:
                    label_text = f"&{label_text}"
            else:
                # Auto-add using first letter
                label_text = f"&{label_text}"

        label = QLabel(label_text)
        label.setBuddy(input_widget)

        # Make input accessible
        clean_name = label_text.replace('&', '').replace(':', '').strip()
        AccessibilityHelper.make_accessible(
            input_widget,
            clean_name,
            description or f"Enter {clean_name.lower()}"
        )

        return label, input_widget

    @staticmethod
    def add_focus_indicators(widget: QWidget, color: str | None = None):
        """
        Add visual focus indicators to a widget.

        Args:
            widget: Widget to add focus indicators to
            color: Color for the focus border (defaults to theme border_focus)
        """
        if color is None:
            color = COLORS["border_focus"]
        current_style = widget.styleSheet()
        focus_style = f"""
        QWidget:focus {{
            border: 2px solid {color};
            outline: none;
        }}
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border: 2px solid {color};
        }}
        QPushButton:focus {{
            border: 2px solid {color};
            padding: 3px;
        }}
        """
        widget.setStyleSheet(current_style + focus_style)

    @staticmethod
    def setup_tab_order(widgets: list[QWidget]):
        """
        Set up logical tab order for a list of widgets.

        Args:
            widgets: List of widgets in desired tab order
        """
        if len(widgets) < 2:
            return

        for i in range(len(widgets) - 1):
            QWidget.setTabOrder(widgets[i], widgets[i + 1])

    @staticmethod
    def add_action_with_shortcut(
        parent: QMainWindow | QDialog | QWidget,
        name: str,
        text: str,
        shortcut: str,
        callback: Callable[..., None],
        description: str = "",
        icon: QIcon | None = None,
        checkable: bool = False
    ) -> QAction:
        """
        Add an action with keyboard shortcut and accessibility info.

        Args:
            parent: Parent widget for the action
            name: Internal name for the action
            text: Display text (can include mnemonic with &)
            shortcut: Keyboard shortcut
            callback: Function to call when triggered
            description: Status tip / accessibility description
            icon: Optional icon for the action
            checkable: Whether the action is checkable

        Returns:
            The created QAction
        """
        action = QAction(text, parent)
        action.setObjectName(name)

        # Set shortcut
        if shortcut in AccessibilityHelper.STANDARD_SHORTCUTS:
            action.setShortcut(AccessibilityHelper.STANDARD_SHORTCUTS[shortcut])
        else:
            action.setShortcut(shortcut)

        # Set description
        if description:
            action.setStatusTip(description)
            action.setToolTip(f"{text.replace('&', '')} ({shortcut})\n{description}")
        else:
            action.setToolTip(f"{text.replace('&', '')} ({shortcut})")

        # Set icon if provided
        if icon:
            action.setIcon(icon)

        # Make checkable if needed
        if checkable:
            action.setCheckable(True)

        # Connect callback
        action.triggered.connect(callback)

        # Set accessible name
        clean_text = text.replace('&', '')
        action.setAccessibleName(clean_text)  # type: ignore[attr-defined]
        action.setAccessibleDescription(description or clean_text)  # type: ignore[attr-defined]

        return action

    @staticmethod
    def setup_dialog_buttons(
        dialog: QDialog,
        accept_text: str = "&OK",
        reject_text: str = "&Cancel",
        accept_shortcut: str = "Return",
        reject_shortcut: str = "Escape"
    ):
        """
        Set up standard dialog buttons with proper keyboard shortcuts.

        Args:
            dialog: The dialog to set up
            accept_text: Text for accept button
            reject_text: Text for reject button
            accept_shortcut: Shortcut for accept
            reject_shortcut: Shortcut for reject
        """
        # Find or create buttons
        from PySide6.QtWidgets import QDialogButtonBox

        button_box = dialog.findChild(QDialogButtonBox)
        if button_box:
            # Update existing button box
            ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
            if ok_button:
                ok_button.setText(accept_text)
                ok_button.setShortcut(accept_shortcut)
                AccessibilityHelper.make_accessible(
                    ok_button,
                    accept_text.replace('&', ''),
                    "Accept changes and close dialog"
                )

            cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if cancel_button:
                cancel_button.setText(reject_text)
                cancel_button.setShortcut(reject_shortcut)
                AccessibilityHelper.make_accessible(
                    cancel_button,
                    reject_text.replace('&', ''),
                    "Cancel changes and close dialog"
                )

    @staticmethod
    def add_group_box_navigation(group_box: QGroupBox):
        """
        Add keyboard navigation support to a group box.

        Args:
            group_box: The group box to enhance
        """
        # Make the group box focusable
        group_box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Set accessible name from title
        title = group_box.title().replace('&', '')
        group_box.setAccessibleName(title)
        group_box.setAccessibleDescription(f"Group: {title}")

    @staticmethod
    def enhance_toolbar(toolbar: QToolBar):
        """
        Enhance toolbar accessibility with keyboard navigation.

        Args:
            toolbar: The toolbar to enhance
        """
        toolbar.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        toolbar.setAccessibleName("Main Toolbar")
        toolbar.setAccessibleDescription("Application toolbar with main actions")

        # Make all actions keyboard accessible
        for action in toolbar.actions():
            if action.text() and not action.shortcut():
                # Add default shortcuts for common actions
                text_lower = action.text().lower()
                if 'open' in text_lower:
                    action.setShortcut('Ctrl+O')
                elif 'save' in text_lower:
                    action.setShortcut('Ctrl+S')
                elif 'export' in text_lower:
                    action.setShortcut('Ctrl+E')

    @staticmethod
    def announce_to_screen_reader(widget: QWidget, message: str):
        """
        Announce a message to screen readers.

        Args:
            widget: Widget context for the announcement
            message: Message to announce
        """
        # This would typically use QAccessible.updateAccessibility
        # For now, we'll update the widget's accessible description
        widget.setAccessibleDescription(message)

        # Also show as status tip if it's a main window
        if isinstance(widget, QMainWindow):
            widget.statusBar().showMessage(message, 5000)

def apply_global_accessibility_styles():
    """Apply global accessibility styles to the application."""
    from typing import cast

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if not app:
        return

    # Cast to QApplication for type checker
    app = cast(QApplication, app)

    # Global focus indicator styles - using theme colors for dark theme compatibility
    focus_color = COLORS["border_focus"]
    global_style = f"""
    /* Focus indicators for all focusable widgets */
    QWidget:focus {{
        outline: 2px solid {focus_color};
        outline-offset: 2px;
    }}

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 2px solid {focus_color};
    }}

    QPushButton:focus {{
        border: 2px solid {focus_color};
        padding: 3px;
    }}

    QComboBox:focus, QSpinBox:focus {{
        border: 2px solid {focus_color};
    }}

    QSlider:focus {{
        border: 1px solid {focus_color};
    }}

    QCheckBox:focus, QRadioButton:focus {{
        color: {focus_color};
    }}

    /* High contrast for better visibility - dark theme compatible */
    QToolTip {{
        background-color: {COLORS["panel_background"]};
        color: {COLORS["text_primary"]};
        border: 1px solid {COLORS["border"]};
        padding: 5px;
    }}

    /* Keyboard navigation hints */
    QMenuBar::item:selected {{
        background-color: {focus_color};
        color: {COLORS["text_primary"]};
    }}

    QMenu::item:selected {{
        background-color: {focus_color};
        color: {COLORS["text_primary"]};
    }}
    """

    current_style = app.styleSheet()
    app.setStyleSheet(current_style + global_style)
