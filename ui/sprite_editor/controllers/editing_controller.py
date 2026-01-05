#!/usr/bin/env python3
"""
Editing controller for the pixel editor functionality.
Manages the pixel editing workflow, tools, and undo/redo.
"""

from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QObject, Signal

from ..commands.pixel_commands import BatchCommand, DrawPixelCommand, FloodFillCommand
from ..managers import ToolManager, ToolType, UndoManager
from ..models import ImageModel, PaletteModel

if TYPE_CHECKING:
    from ..views.tabs import EditTab


class EditingController(QObject):
    """Controller for pixel editing operations."""

    # Signals
    imageChanged = Signal()
    paletteChanged = Signal()
    toolChanged = Signal(str)
    colorChanged = Signal(int)
    undoStateChanged = Signal(bool, bool)  # can_undo, can_redo

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        # Create models and managers
        self.image_model = ImageModel()
        self.palette_model = PaletteModel()  # Use model instead of inline list
        self.tool_manager = ToolManager()
        self.undo_manager = UndoManager()

        # Selected color index
        self._selected_color = 1

        # View reference
        self._view: EditTab | None = None

        # Current stroke batch for undo (accumulated during press/move/release)
        self._current_stroke: BatchCommand | None = None

        # Last save path for Save operation
        self._last_save_path: str = ""

        # Connect tool manager signals
        self.tool_manager.tool_changed.connect(self._on_tool_changed)

    def set_view(self, view: "EditTab") -> None:
        """Set the edit tab view."""
        self._view = view
        view.set_controller(self)

    def has_image(self) -> bool:
        """Check if an image is loaded (always true - model has default data)."""
        return True

    def get_image_size(self) -> tuple[int, int]:
        """Get the current image size (width, height)."""
        height, width = self.image_model.data.shape
        return (width, height)

    def get_current_colors(self) -> list[tuple[int, int, int]]:
        """Get the current palette colors."""
        return list(self.palette_model.colors)

    def get_current_tool_name(self) -> str:
        """Get the name of the current tool."""
        tool_type = self.tool_manager.current_tool_type
        return {
            ToolType.PENCIL: "pencil",
            ToolType.FILL: "fill",
            ToolType.PICKER: "picker",
        }.get(tool_type, "pencil")

    def get_selected_color(self) -> int:
        """Get the currently selected color index."""
        return self._selected_color

    def set_tool(self, tool_name: str) -> None:
        """Set the current tool by name."""
        tool_map = {
            "pencil": ToolType.PENCIL,
            "fill": ToolType.FILL,
            "picker": ToolType.PICKER,
        }
        tool_type = tool_map.get(tool_name, ToolType.PENCIL)
        self.tool_manager.set_tool(tool_type)

    def set_brush_size(self, size: int) -> None:
        """Set the brush size."""
        self.tool_manager.set_brush_size(size)

    def set_selected_color(self, index: int) -> None:
        """Set the selected color index."""
        if 0 <= index < 16:
            self._selected_color = index
            self.tool_manager.set_color(index)
            self.colorChanged.emit(index)

    def set_palette(self, colors: list[tuple[int, int, int]], name: str = "") -> None:
        """Set the palette colors."""
        self.palette_model.from_rgb_list(colors)
        if name:
            self.palette_model.name = name
        self.paletteChanged.emit()

    def load_image(self, data: np.ndarray, palette: list[tuple[int, int, int]] | None = None) -> None:
        """Load an image into the editor.

        Args:
            data: 2D numpy array of palette indices
            palette: Optional palette colors
        """
        self.image_model.set_data(data)
        if palette:
            self.set_palette(palette)

        # Clear undo history
        self.undo_manager.clear()

        self.imageChanged.emit()

    def _on_tool_changed(self, tool_type: ToolType) -> None:
        """Handle tool change from manager."""
        tool_name = {
            ToolType.PENCIL: "pencil",
            ToolType.FILL: "fill",
            ToolType.PICKER: "picker",
        }.get(tool_type, "pencil")
        self.toolChanged.emit(tool_name)

    # Drawing operations

    def handle_pixel_press(self, x: int, y: int) -> None:
        """Handle pixel press event from canvas."""
        if not self.has_image():
            return

        tool = self.tool_manager.get_tool()
        if tool is None:
            return

        tool_type = self.tool_manager.current_tool_type

        # Handle color picker - no undo needed
        if tool_type == ToolType.PICKER:
            color = self.image_model.get_pixel(x, y)
            if 0 <= color < 16:
                self.set_selected_color(color)
            return

        # Handle fill tool - single command
        if tool_type == ToolType.FILL:
            old_color = self.image_model.get_pixel(x, y)
            result = tool.on_press(x, y, self._selected_color, self.image_model)
            if result:
                # Record fill command with old/new color info
                cmd = FloodFillCommand(x=x, y=y, old_color=old_color, new_color=self._selected_color)
                self.undo_manager.record_command(cmd)
                self.imageChanged.emit()
                self._emit_undo_state()
            return

        # Handle pencil tool - start a stroke batch
        old_color = self.image_model.get_pixel(x, y)
        result = tool.on_press(x, y, self._selected_color, self.image_model)

        if result:
            # Start new batch for this stroke
            self._current_stroke = BatchCommand()
            cmd = DrawPixelCommand(x=x, y=y, old_color=old_color, new_color=self._selected_color)
            self._current_stroke.add_command(cmd)
            self.imageChanged.emit()

    def handle_pixel_move(self, x: int, y: int) -> None:
        """Handle pixel move event from canvas."""
        if not self.has_image():
            return

        tool = self.tool_manager.get_tool()
        if tool is None:
            return

        tool_type = self.tool_manager.current_tool_type

        # Only pencil tool uses move for continuous drawing
        if tool_type != ToolType.PENCIL:
            return

        # Get line points from tool (for interpolation)
        line_points = tool.on_move(x, y, self._selected_color, self.image_model)

        if not line_points:
            return

        # Draw each point and record for undo
        any_changed = False
        for px, py in line_points:
            old_color = self.image_model.get_pixel(px, py)
            if self.image_model.set_pixel(px, py, self._selected_color):
                any_changed = True
                if self._current_stroke is not None:
                    cmd = DrawPixelCommand(x=px, y=py, old_color=old_color, new_color=self._selected_color)
                    self._current_stroke.add_command(cmd)

        if any_changed:
            self.imageChanged.emit()

    def handle_pixel_release(self, x: int, y: int) -> None:
        """Handle pixel release event from canvas."""
        if not self.has_image():
            return

        tool = self.tool_manager.get_tool()
        if tool is None:
            return

        # Notify tool of release (for state cleanup)
        tool.on_release(x, y, self._selected_color, self.image_model)

        # Finalize stroke batch for undo
        if self._current_stroke is not None and self._current_stroke.commands:
            self.undo_manager.record_command(self._current_stroke)
            self._emit_undo_state()
        self._current_stroke = None

    # Color picker callback

    def pick_color_at(self, x: int, y: int) -> int | None:
        """Pick color at the given position."""
        color = self.image_model.get_pixel(x, y)
        if 0 <= color < 16:
            self.set_selected_color(color)
            return color
        return None

    # Undo/Redo

    def undo(self) -> None:
        """Undo the last operation."""
        if self.undo_manager.can_undo():
            self.undo_manager.undo(self.image_model)
            self.imageChanged.emit()
            self._emit_undo_state()

    def redo(self) -> None:
        """Redo the last undone operation."""
        if self.undo_manager.can_redo():
            self.undo_manager.redo(self.image_model)
            self.imageChanged.emit()
            self._emit_undo_state()

    def _emit_undo_state(self) -> None:
        """Emit undo state changed signal."""
        self.undoStateChanged.emit(
            self.undo_manager.can_undo(),
            self.undo_manager.can_redo(),
        )

    # Image export

    def get_image_data(self) -> np.ndarray | None:
        """Get the current image data."""
        return self.image_model.data

    def get_flat_palette(self) -> list[int]:
        """Get the palette as a flat list for PIL."""
        return self.palette_model.to_flat_list()

    # File operations

    def save_image(self, file_path: str | None = None) -> bool:
        """Save current image to file. Returns True if successful."""
        if file_path is None and not self._last_save_path:
            # No path known - delegate to save_as
            return self.save_image_as() is not None

        path = file_path or self._last_save_path
        data = self.get_image_data()
        if data is None:
            return False

        from PIL import Image

        # Create PIL image with palette
        img = Image.fromarray(data, mode="P")
        img.putpalette(self.get_flat_palette())
        img.save(path, "PNG")

        self._last_save_path = path
        return True

    def save_image_as(self) -> str | None:
        """Show save dialog and save. Returns path if successful, None if cancelled."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self._view,
            "Save Sprite Image",
            "sprite.png",
            "PNG Images (*.png);;All Files (*)",
        )

        if file_path:
            if self.save_image(file_path):
                return file_path
        return None
