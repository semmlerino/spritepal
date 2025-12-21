"""
Widget factory utilities for common UI patterns

Provides factory methods for creating standardized widgets with consistent
styling and behavior throughout the SpritePal application.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.common.file_dialogs import FileDialogHelper
from ui.styles import get_muted_text_style
from ui.styles.theme import COLORS


class WidgetFactory:
    """
    Factory class for creating standardized UI widgets

    Provides methods for creating common widget patterns used throughout
    SpritePal with consistent styling and behavior.
    """

    @staticmethod
    def create_checkbox_with_tooltip(
        text: str,
        tooltip: str = "",
        checked: bool = False,
        enabled: bool = True,
        on_changed: Callable[[bool], None] | None = None
    ) -> QCheckBox:
        """
        Create a checkbox with standardized styling and tooltip

        Args:
            text: Checkbox label text
            tooltip: Tooltip text (optional)
            checked: Initial checked state
            enabled: Initial enabled state
            on_changed: Callback for state changes

        Returns:
            Configured QCheckBox widget
        """
        checkbox = QCheckBox(text)
        checkbox.setChecked(checked)
        checkbox.setEnabled(enabled)

        if tooltip:
            checkbox.setToolTip(tooltip)

        if on_changed:
            checkbox.toggled.connect(on_changed)

        return checkbox

    @staticmethod
    def create_browse_layout(
        label_text: str,
        placeholder: str = "",
        browse_text: str = "Browse...",
        initial_path: str = "",
        read_only: bool = False,
        on_path_changed: Callable[[str], None] | None = None,
        browse_callback: Callable[[QLineEdit], None] | None = None
    ) -> tuple[QWidget, QLineEdit, QPushButton]:
        """
        Create a standardized browse layout (label + input + browse button)

        Args:
            label_text: Label text
            placeholder: Placeholder text for input
            browse_text: Browse button text
            initial_path: Initial path value
            read_only: Whether input is read-only
            on_path_changed: Callback for path changes
            browse_callback: Custom browse callback (receives line edit)

        Returns:
            Tuple of (container_widget, line_edit, browse_button)
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Label
        if label_text:
            label = QLabel(label_text)
            layout.addWidget(label)

        # Path input
        path_edit = QLineEdit(initial_path)
        path_edit.setPlaceholderText(placeholder)
        path_edit.setReadOnly(read_only)

        if on_path_changed:
            path_edit.textChanged.connect(on_path_changed)

        layout.addWidget(path_edit, 1)  # Stretch factor 1

        # Browse button
        browse_button = QPushButton(browse_text)

        if browse_callback:
            browse_button.clicked.connect(lambda: browse_callback(path_edit))
        else:
            # Default browse behavior
            browse_button.clicked.connect(
                lambda: WidgetFactory._default_browse_action(path_edit)
            )

        layout.addWidget(browse_button)

        return container, path_edit, browse_button

    @staticmethod
    def create_info_label(
        text: str,
        word_wrap: bool = True,
        color_level: str = "medium"
    ) -> QLabel:
        """
        Create an info label with muted styling

        Args:
            text: Label text
            word_wrap: Whether to enable word wrapping
            color_level: Color level for muted text ("light", "medium", "dark")

        Returns:
            Styled QLabel widget
        """
        label = QLabel(text)
        label.setWordWrap(word_wrap)
        label.setStyleSheet(get_muted_text_style(color_level=color_level))
        return label

    @staticmethod
    def create_path_input_with_validation(
        placeholder: str = "",
        initial_path: str = "",
        validate_exists: bool = True,
        on_validation_changed: Callable[[bool, str], None] | None = None
    ) -> tuple[QLineEdit, Callable[[], bool]]:
        """
        Create a path input with built-in validation

        Args:
            placeholder: Placeholder text
            initial_path: Initial path value
            validate_exists: Whether to validate file/directory existence
            on_validation_changed: Callback for validation state changes

        Returns:
            Tuple of (line_edit, validation_function)
        """

        path_edit = QLineEdit(initial_path)
        path_edit.setPlaceholderText(placeholder)

        def validate() -> bool:
            """Validate the current path"""
            path = path_edit.text().strip()

            if not path:
                # Empty path is valid (optional field)
                is_valid = True
                message = ""
            elif validate_exists:
                is_valid = Path(path).exists()
                message = f"Path does not exist: {path}" if not is_valid else ""
            else:
                # Just check if path format is reasonable
                is_valid = len(path) > 0
                message = ""

            if on_validation_changed:
                on_validation_changed(is_valid, message)

            return is_valid

        # Connect validation to text changes
        path_edit.textChanged.connect(lambda: validate())

        return path_edit, validate

    @staticmethod
    def create_labeled_widget(
        label_text: str,
        widget: QWidget,
        orientation: str = "horizontal",
        label_width: int | None = None
    ) -> QWidget:
        """
        Create a labeled widget container

        Args:
            label_text: Label text
            widget: Widget to label
            orientation: "horizontal" or "vertical"
            label_width: Fixed width for label (horizontal only)

        Returns:
            Container widget with label and widget
        """

        container = QWidget()

        if orientation == "horizontal":
            layout = QHBoxLayout(container)
            label = QLabel(label_text)

            if label_width:
                label.setMinimumWidth(label_width)
                label.setMaximumWidth(label_width)

            label.setAlignment(Qt.AlignmentFlag.AlignTop)
            layout.addWidget(label)
            layout.addWidget(widget, 1)
        else:
            layout = QVBoxLayout(container)
            label = QLabel(label_text)
            layout.addWidget(label)
            layout.addWidget(widget)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        return container

    @staticmethod
    def _default_browse_action(path_edit: QLineEdit) -> None:
        """Default browse action for browse layouts"""
        current_path = path_edit.text()

        # Try to determine if this should be a file or directory dialog
        # based on the placeholder text or current content
        placeholder = path_edit.placeholderText().lower()

        if "directory" in placeholder or "folder" in placeholder:
            # Directory dialog
            directory = FileDialogHelper.browse_directory(
                parent=path_edit.parentWidget(),
                initial_dir=current_path
            )
            if directory:
                path_edit.setText(directory)
        else:
            # File dialog
            filename = FileDialogHelper.browse_open_file(
                parent=path_edit.parentWidget(),
                initial_path=current_path
            )
            if filename:
                path_edit.setText(filename)


def create_section_title(text: str) -> QLabel:
    """Create a styled section title label.

    Args:
        text: Title text

    Returns:
        Styled label widget
    """
    title = QLabel(text)
    title_font = QFont()
    title_font.setBold(True)
    title_font.setPointSize(11)
    title.setFont(title_font)
    title.setStyleSheet(f"color: {COLORS['highlight']}; padding: 2px 4px; border-radius: 3px;")
    return title
