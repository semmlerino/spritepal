#!/usr/bin/env python3
"""
Manager classes for the unified sprite editor.
Handle coordination between models and provide business logic.
"""

# Re-export UndoManager from core.editing for backward compatibility
# The core version supports SelectionPaintCommand
from core.editing import UndoManager

from .tool_manager import (
    ColorPickerTool,
    FillTool,
    PencilTool,
    Tool,
    ToolManager,
    ToolType,
)

__all__ = [
    "ColorPickerTool",
    "FillTool",
    "PencilTool",
    "Tool",
    "ToolManager",
    "ToolType",
    "UndoManager",
]
