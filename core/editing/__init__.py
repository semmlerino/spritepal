"""
Core editing module for indexed image manipulation.

This module provides the foundation for palette-based image editing,
including the image model, undo/redo commands, and undo management.

Extracted from ui/sprite_editor for reuse across different editing contexts.
"""

from .commands import (
    BatchCommand,
    DrawPixelCommand,
    FloodFillCommand,
    SelectionPaintCommand,
    UndoCommand,
)
from .indexed_image_model import IndexedImageModel
from .selection_mask import SelectionMask
from .undo_manager import UndoManager

__all__ = [
    "BatchCommand",
    "DrawPixelCommand",
    "FloodFillCommand",
    "IndexedImageModel",
    "SelectionMask",
    "SelectionPaintCommand",
    "UndoCommand",
    "UndoManager",
]
