#!/usr/bin/env python3
"""
Tool selection panel for the pixel editor.
Provides UI for selecting drawing tools.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ToolPanel(QWidget):
    """Panel for tool selection (pencil, fill, picker)."""

    # Signals
    toolChanged = Signal(str)  # Emits tool name when changed
    brushSizeChanged = Signal(int)  # Emits brush size when changed

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the tool panel UI."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tool group box
        tool_group = QGroupBox("Tools")
        tool_layout = QVBoxLayout()

        # Create button group for radio buttons
        self.tool_group = QButtonGroup()

        # Tool buttons
        self.pencil_btn = QRadioButton("Pencil")
        self.pencil_btn.setChecked(True)
        self.fill_btn = QRadioButton("Fill")
        self.picker_btn = QRadioButton("Picker")

        # Add buttons to group with IDs
        self.tool_group.addButton(self.pencil_btn, 0)
        self.tool_group.addButton(self.fill_btn, 1)
        self.tool_group.addButton(self.picker_btn, 2)

        # Add to layout
        tool_layout.addWidget(self.pencil_btn)
        tool_layout.addWidget(self.fill_btn)
        tool_layout.addWidget(self.picker_btn)
        tool_group.setLayout(tool_layout)

        # Connect signal
        self.tool_group.buttonClicked.connect(self._on_tool_changed)

        # Add to main layout
        layout.addWidget(tool_group)

        # Brush size group box
        brush_group = QGroupBox("Brush Size")
        brush_layout = QHBoxLayout()

        self.brush_size_label = QLabel("Size:")
        self.brush_size_spinbox = QSpinBox()
        self.brush_size_spinbox.setRange(1, 5)
        self.brush_size_spinbox.setValue(1)
        self.brush_size_spinbox.setToolTip("Brush size in pixels")
        self.brush_size_spinbox.valueChanged.connect(self._on_brush_size_changed)

        brush_layout.addWidget(self.brush_size_label)
        brush_layout.addWidget(self.brush_size_spinbox)
        brush_group.setLayout(brush_layout)

        # Add to main layout
        layout.addWidget(brush_group)

    def _on_tool_changed(self, button: QRadioButton) -> None:
        """Handle tool selection change."""
        tool_map = {0: "pencil", 1: "fill", 2: "picker"}
        tool_id = self.tool_group.id(button)
        tool_name = tool_map.get(tool_id, "pencil")
        self.toolChanged.emit(tool_name)

    def _on_brush_size_changed(self, size: int) -> None:
        """Handle brush size change."""
        self.brushSizeChanged.emit(size)

    def get_current_tool(self) -> str:
        """Get the currently selected tool name."""
        tool_map = {0: "pencil", 1: "fill", 2: "picker"}
        checked_id = self.tool_group.checkedId()
        return tool_map.get(checked_id, "pencil")

    def set_tool(self, tool_name: str) -> None:
        """Set the current tool by name."""
        tool_buttons = {
            "pencil": self.pencil_btn,
            "fill": self.fill_btn,
            "picker": self.picker_btn,
        }

        if tool_name in tool_buttons:
            tool_buttons[tool_name].setChecked(True)
            # Emit the signal to notify controller
            self.toolChanged.emit(tool_name)

    def get_brush_size(self) -> int:
        """Get the current brush size."""
        return self.brush_size_spinbox.value()

    def set_brush_size(self, size: int) -> None:
        """Set the brush size."""
        self.brush_size_spinbox.setValue(size)

    def update_brush_size_display(self) -> None:
        """Update the brush size display (for external updates)."""
        # This method can be called when brush size changes via keyboard shortcuts
        pass
