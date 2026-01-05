#!/usr/bin/env python3
"""
Tool management for the pixel editor.
Provides drawing tools and manages tool state.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum, auto
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..models.image_model import ImageModel


class ToolType(Enum):
    """Available drawing tools."""

    PENCIL = auto()
    FILL = auto()
    PICKER = auto()


class Tool(ABC):
    """Abstract base class for drawing tools."""

    @abstractmethod
    def on_press(self, x: int, y: int, color: int, image_model: ImageModel) -> Any:
        """Handle mouse press event."""

    @abstractmethod
    def on_move(self, x: int, y: int, color: int, image_model: ImageModel) -> Any:
        """Handle mouse move event."""

    @abstractmethod
    def on_release(self, x: int, y: int, color: int, image_model: ImageModel) -> Any:
        """Handle mouse release event."""


class PencilTool(Tool):
    """Basic drawing tool with line interpolation."""

    def __init__(self) -> None:
        self.last_x: int | None = None
        self.last_y: int | None = None

    def on_press(self, x: int, y: int, color: int, image_model: ImageModel) -> bool:
        """Draw a single pixel and start tracking position."""
        self.last_x = x
        self.last_y = y
        return image_model.set_pixel(x, y, color)

    def on_move(
        self, x: int, y: int, color: int, image_model: ImageModel
    ) -> list[tuple[int, int]]:
        """Continue drawing with line interpolation."""
        if self.last_x is None or self.last_y is None:
            self.last_x = x
            self.last_y = y
            return [(x, y)]

        line_points = self._get_line_points(self.last_x, self.last_y, x, y)
        self.last_x = x
        self.last_y = y
        return line_points

    def on_release(
        self, x: int, y: int, color: int, image_model: ImageModel
    ) -> None:
        """Clear tracking state."""
        self.last_x = None
        self.last_y = None

    def _get_line_points(
        self, x0: int, y0: int, x1: int, y1: int
    ) -> list[tuple[int, int]]:
        """Get all points on a line using Bresenham's algorithm."""
        points: list[tuple[int, int]] = []

        dx = abs(x1 - x0)
        dy = abs(y1 - y0)

        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1

        err = dx - dy
        x, y = x0, y0

        while True:
            points.append((x, y))

            if x == x1 and y == y1:
                break

            e2 = 2 * err

            if e2 > -dy:
                err -= dy
                x += sx

            if e2 < dx:
                err += dx
                y += sy

        return points


class FillTool(Tool):
    """Flood fill tool."""

    def on_press(
        self, x: int, y: int, color: int, image_model: ImageModel
    ) -> list[tuple[int, int]]:
        """Perform flood fill."""
        return image_model.fill(x, y, color)

    def on_move(self, x: int, y: int, color: int, image_model: ImageModel) -> None:
        """No action on move."""

    def on_release(self, x: int, y: int, color: int, image_model: ImageModel) -> None:
        """Nothing to do on release."""


class ColorPickerTool(Tool):
    """Color picker tool."""

    def __init__(self) -> None:
        self.picked_callback: Callable[[int], None] | None = None

    def on_press(self, x: int, y: int, color: int, image_model: ImageModel) -> int:
        """Pick color at position."""
        picked_color = image_model.get_color_at(x, y)
        if self.picked_callback:
            self.picked_callback(picked_color)
        return picked_color

    def on_move(self, x: int, y: int, color: int, image_model: ImageModel) -> None:
        """No action on move."""

    def on_release(self, x: int, y: int, color: int, image_model: ImageModel) -> None:
        """Nothing to do on release."""


class ToolManager(QObject):
    """Manages drawing tools and tool state."""

    # Signals
    tool_changed = Signal(object)  # Emits ToolType
    color_changed = Signal(int)
    brush_size_changed = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.tools: dict[ToolType, Tool] = {
            ToolType.PENCIL: PencilTool(),
            ToolType.FILL: FillTool(),
            ToolType.PICKER: ColorPickerTool(),
        }
        self._current_tool = ToolType.PENCIL
        self.current_color = 0
        self.current_brush_size = 1
        self.max_brush_size = 5

    @property
    def current_tool(self) -> ToolType:
        """Get the current tool type."""
        return self._current_tool

    @property
    def current_tool_type(self) -> ToolType:
        """Get the current tool type (alias for current_tool)."""
        return self._current_tool

    @current_tool.setter
    def current_tool(self, value: ToolType) -> None:
        """Set the current tool type."""
        if value != self._current_tool:
            self._current_tool = value
            self.tool_changed.emit(value)

    def set_tool(self, tool_type: ToolType | str) -> None:
        """Set the current tool (accepts ToolType enum or string)."""
        if isinstance(tool_type, str):
            tool_map = {
                "pencil": ToolType.PENCIL,
                "fill": ToolType.FILL,
                "picker": ToolType.PICKER,
            }
            mapped_type = tool_map.get(tool_type.lower())
            if not mapped_type:
                return
            tool_type = mapped_type

        if tool_type in self.tools:
            self.current_tool = tool_type  # Uses property setter, emits signal

    @property
    def current_tool_name(self) -> str:
        """Get the name of the current tool."""
        return self._current_tool.name.lower()

    def get_tool(self, tool_type: ToolType | str | None = None) -> Tool | None:
        """Get tool instance (current tool if no type specified)."""
        if tool_type is None:
            return self.tools[self._current_tool]

        if isinstance(tool_type, str):
            tool_map = {
                "pencil": ToolType.PENCIL,
                "fill": ToolType.FILL,
                "picker": ToolType.PICKER,
            }
            orig_tool_type = tool_type
            tool_type = tool_map.get(orig_tool_type.lower())
            if not tool_type:
                raise ValueError(f"Unknown tool: {orig_tool_type}")

        return self.tools.get(tool_type) if tool_type else None

    def set_color(self, color: int) -> None:
        """Set the current drawing color."""
        new_color = max(0, min(15, color))
        if new_color != self.current_color:
            self.current_color = new_color
            self.color_changed.emit(new_color)

    def set_brush_size(self, size: int) -> None:
        """Set brush size with validation."""
        if 1 <= size <= self.max_brush_size and size != self.current_brush_size:
            self.current_brush_size = size
            self.brush_size_changed.emit(size)

    def get_brush_size(self) -> int:
        """Get current brush size."""
        return self.current_brush_size

    def get_brush_pixels(
        self, center_x: int, center_y: int
    ) -> list[tuple[int, int]]:
        """Calculate pixels affected by brush at given position."""
        pixels: list[tuple[int, int]] = []
        size = self.current_brush_size

        for dy in range(size):
            for dx in range(size):
                pixels.append((center_x + dx, center_y + dy))

        return pixels

    def set_color_picked_callback(self, callback: Callable[[int], None]) -> None:
        """Set callback for color picker tool."""
        picker = self.tools[ToolType.PICKER]
        if isinstance(picker, ColorPickerTool):
            picker.picked_callback = callback
