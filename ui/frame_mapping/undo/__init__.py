"""Undo/Redo infrastructure for frame mapping operations.

This module provides a command-pattern based undo/redo system for the
FrameMappingController, supporting all mapping and alignment operations.
"""

from ui.frame_mapping.undo.command_context import CommandContext, CommandSignalEmitter
from ui.frame_mapping.undo.commands import (
    ApplyTransformsToAllCommand,
    CreateMappingCommand,
    RemoveMappingCommand,
    RenameAIFrameCommand,
    RenameCaptureCommand,
    ReorderAIFrameCommand,
    ToggleFrameTagCommand,
    UpdateAlignmentCommand,
)
from ui.frame_mapping.undo.undo_stack import FrameMappingCommand, UndoRedoStack

__all__ = [
    "ApplyTransformsToAllCommand",
    "CommandContext",
    "CommandSignalEmitter",
    "CreateMappingCommand",
    "FrameMappingCommand",
    "RemoveMappingCommand",
    "RenameAIFrameCommand",
    "RenameCaptureCommand",
    "ReorderAIFrameCommand",
    "ToggleFrameTagCommand",
    "UndoRedoStack",
    "UpdateAlignmentCommand",
]
