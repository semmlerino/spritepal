#!/usr/bin/env python3
"""
Undo/Redo manager for indexed image editing.
Manages command history with automatic compression.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .commands import (
    BatchCommand,
    DrawPixelCommand,
    FloodFillCommand,
    SelectionPaintCommand,
    UndoCommand,
)

if TYPE_CHECKING:
    from .indexed_image_model import IndexedImageModel


class UndoManager:
    """Manages undo/redo operations with automatic compression.

    Maintains a stack of commands with a current index pointer.
    Automatically compresses older commands to reduce memory usage.
    """

    def __init__(self, max_commands: int = 100, compression_age: int = 20) -> None:
        """Initialize the undo manager.

        Args:
            max_commands: Maximum number of commands to retain
            compression_age: Commands older than this many steps are compressed
        """
        self.command_stack: list[UndoCommand] = []
        self.current_index: int = -1
        self.max_commands: int = max_commands
        self.compression_age: int = compression_age

    def execute_command(self, command: UndoCommand, model: IndexedImageModel) -> None:
        """Execute a new command and add to history."""
        # Remove any commands after current index (clear redo stack)
        if self.current_index < len(self.command_stack) - 1:
            self.command_stack = self.command_stack[: self.current_index + 1]

        # Execute the command
        command.execute(model)

        # Add to stack
        self.command_stack.append(command)
        self.current_index += 1

        # Enforce maximum size
        if len(self.command_stack) > self.max_commands:
            self.command_stack.pop(0)
            self.current_index -= 1

        # Compress old commands
        self._compress_old_commands()

    def record_command(self, command: UndoCommand) -> None:
        """Record a command that has already been executed (by tools).

        Use this when the tool has already modified the image and you
        just need to record the command for undo/redo purposes.
        """
        # Remove any commands after current index (clear redo stack)
        if self.current_index < len(self.command_stack) - 1:
            self.command_stack = self.command_stack[: self.current_index + 1]

        # Add to stack (command already executed)
        self.command_stack.append(command)
        self.current_index += 1

        # Enforce maximum size
        if len(self.command_stack) > self.max_commands:
            self.command_stack.pop(0)
            self.current_index -= 1

        # Compress old commands
        self._compress_old_commands()

    def undo(self, model: IndexedImageModel) -> bool:
        """Undo the last command. Returns True if successful."""
        if self.current_index >= 0:
            command = self.command_stack[self.current_index]

            if command.compressed:
                command.decompress()

            command.unexecute(model)
            self.current_index -= 1
            return True
        return False

    def redo(self, model: IndexedImageModel) -> bool:
        """Redo the next command. Returns True if successful."""
        if self.current_index < len(self.command_stack) - 1:
            self.current_index += 1
            command = self.command_stack[self.current_index]

            if command.compressed:
                command.decompress()

            command.execute(model)
            return True
        return False

    def _compress_old_commands(self) -> None:
        """Compress commands older than compression_age."""
        compress_before = max(0, self.current_index - self.compression_age)

        for i in range(compress_before):
            if not self.command_stack[i].compressed:
                self.command_stack[i].compress()

    def get_memory_usage(self) -> dict[str, int | float | bool]:
        """Get current memory usage statistics."""
        total = sum(cmd.get_memory_size() for cmd in self.command_stack)
        compressed = sum(1 for cmd in self.command_stack if cmd.compressed)

        return {
            "total_bytes": total,
            "total_mb": total / (1024 * 1024),
            "command_count": len(self.command_stack),
            "compressed_count": compressed,
            "current_index": self.current_index,
            "can_undo": self.current_index >= 0,
            "can_redo": self.current_index < len(self.command_stack) - 1,
        }

    def can_undo(self) -> bool:
        """Check if undo is available."""
        return self.current_index >= 0

    def can_redo(self) -> bool:
        """Check if redo is available."""
        return self.current_index < len(self.command_stack) - 1

    def clear(self) -> None:
        """Clear all undo/redo history."""
        self.command_stack.clear()
        self.current_index = -1

    def save_history(self) -> list[dict[str, Any]]:  # pyright: ignore[reportExplicitAny]
        """Serialize command history for saving."""
        return [cmd.to_dict() for cmd in self.command_stack]

    def load_history(self, history: list[dict[str, Any]], model: IndexedImageModel) -> None:  # pyright: ignore[reportExplicitAny]
        """Load command history from serialized data."""
        self.clear()

        for cmd_data in history:
            cmd_type = cmd_data["type"]

            if cmd_type == "DrawPixelCommand":
                cmd = DrawPixelCommand.from_dict(cmd_data)
            elif cmd_type == "FloodFillCommand":
                cmd = FloodFillCommand.from_dict(cmd_data)
            elif cmd_type == "SelectionPaintCommand":
                cmd = SelectionPaintCommand.from_dict(cmd_data)
            elif cmd_type == "BatchCommand":
                cmd = BatchCommand.from_dict(cmd_data)
            else:
                continue

            self.command_stack.append(cmd)

        self.current_index = len(self.command_stack) - 1
