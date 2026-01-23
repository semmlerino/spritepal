#!/usr/bin/env python3
"""
Delta-based undo/redo system using Command pattern for indexed image editing.

This module implements a memory-efficient undo/redo system that stores only the
changes (deltas) rather than full image copies. Commands can be compressed for
long-term storage to further reduce memory usage.
"""

from __future__ import annotations

import pickle
import zlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, override

import numpy as np

if TYPE_CHECKING:
    from .indexed_image_model import IndexedImageModel


class UndoCommand(ABC):
    """Abstract base class for all undo commands.

    Each command represents a reversible operation on the canvas.
    Commands can be compressed to reduce memory usage for older operations.
    """

    def __init__(self) -> None:
        """Initialize command with timestamp and compression state."""
        self.timestamp: datetime = datetime.now(UTC)
        self.compressed: bool = False
        self._compressed_data: bytes | None = None

    @abstractmethod
    def execute(self, model: IndexedImageModel) -> None:
        """Apply this command to the canvas."""

    @abstractmethod
    def unexecute(self, model: IndexedImageModel) -> None:
        """Revert this command on the canvas."""

    @abstractmethod
    def get_memory_size(self) -> int:
        """Return approximate memory usage in bytes."""

    def compress(self) -> None:
        """Compress command data for long-term storage."""
        if not self.compressed:
            data = self._get_compress_data()
            self._compressed_data = zlib.compress(pickle.dumps(data))
            self._clear_uncompressed_data()
            self.compressed = True

    def decompress(self) -> None:
        """Decompress command data for execution."""
        if self.compressed and self._compressed_data:
            data = pickle.loads(zlib.decompress(self._compressed_data))
            self._restore_from_compressed(data)
            self._compressed_data = None
            self.compressed = False

    @abstractmethod
    def _get_compress_data(self) -> Any:  # type: ignore[reportExplicitAny]
        """Get data to be compressed."""

    @abstractmethod
    def _clear_uncompressed_data(self) -> None:
        """Clear uncompressed data after compression."""

    @abstractmethod
    def _restore_from_compressed(self, data: Any) -> None:  # type: ignore[reportExplicitAny]
        """Restore state from compressed data."""

    def to_dict(self) -> dict[str, Any]:  # type: ignore[reportExplicitAny]
        """Serialize command to dictionary for save/load support."""
        return {
            "type": self.__class__.__name__,
            "timestamp": self.timestamp.isoformat(),
            "compressed": self.compressed,
            "data": self._get_compress_data() if not self.compressed else None,
            "compressed_data": (self._compressed_data.hex() if self._compressed_data else None),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UndoCommand:  # type: ignore[reportExplicitAny]
        """Deserialize command from dictionary."""
        raise NotImplementedError("Subclasses must implement from_dict")


@dataclass
class DrawPixelCommand(UndoCommand):
    """Command for single pixel changes."""

    x: int = 0
    y: int = 0
    old_color: int = 0
    new_color: int = 0

    def __post_init__(self) -> None:
        """Initialize parent class after dataclass initialization."""
        super().__init__()

    @override
    def execute(self, model: IndexedImageModel) -> None:
        """Apply pixel color change."""
        if 0 <= self.x < model.data.shape[1] and 0 <= self.y < model.data.shape[0]:
            model.data[self.y, self.x] = self.new_color

    @override
    def unexecute(self, model: IndexedImageModel) -> None:
        """Restore original pixel color."""
        if 0 <= self.x < model.data.shape[1] and 0 <= self.y < model.data.shape[0]:
            model.data[self.y, self.x] = self.old_color

    @override
    def get_memory_size(self) -> int:
        """Calculate memory usage."""
        if self.compressed and self._compressed_data:
            return len(self._compressed_data) + 64
        return 4 * 4 + 64  # ~80 bytes

    @override
    def _get_compress_data(self) -> tuple[int, int, int, int]:
        """Get pixel data for compression."""
        return (self.x, self.y, self.old_color, self.new_color)

    @override
    def _clear_uncompressed_data(self) -> None:
        """No need to clear primitive types."""

    @override
    def _restore_from_compressed(self, data: tuple[int, int, int, int]) -> None:
        """Restore pixel data from compressed format."""
        self.x, self.y, self.old_color, self.new_color = data

    @classmethod
    @override
    def from_dict(cls, data: dict[str, Any]) -> DrawPixelCommand:  # type: ignore[reportExplicitAny]
        """Create command from dictionary."""
        cmd = cls()
        cmd.timestamp = datetime.fromisoformat(data["timestamp"])
        cmd.compressed = data["compressed"]

        if data["compressed"]:
            cmd._compressed_data = bytes.fromhex(data["compressed_data"])
        else:
            cmd.x, cmd.y, cmd.old_color, cmd.new_color = data["data"]

        return cmd


@dataclass
class FloodFillCommand(UndoCommand):
    """Command for flood fill operations."""

    x: int = 0
    y: int = 0
    old_color: int = 0
    new_color: int = 0
    affected_region: tuple[int, int, int, int] = (0, 0, 0, 0)
    old_data: np.ndarray | None = None
    _fill_executed: bool = False

    def __post_init__(self) -> None:
        """Initialize parent class after dataclass initialization."""
        super().__init__()

    @override
    def execute(self, model: IndexedImageModel) -> None:
        """Apply flood fill operation."""
        if not self._fill_executed:
            self._perform_flood_fill(model)
            self._fill_executed = True
        else:
            self._apply_stored_changes(model)

    @override
    def unexecute(self, model: IndexedImageModel) -> None:
        """Restore original data in affected region."""
        if self.old_data is None:
            return

        x, y, w, h = self.affected_region

        for dy in range(h):
            for dx in range(w):
                px, py = x + dx, y + dy
                if (0 <= px < model.data.shape[1] and 0 <= py < model.data.shape[0]) and self.old_data[dy, dx] != 255:
                    model.data[py, px] = self.old_data[dy, dx]

    def _perform_flood_fill(self, model: IndexedImageModel) -> None:
        """Perform the actual flood fill operation."""
        if self.old_color == self.new_color:
            return

        if self.x < 0 or self.x >= model.data.shape[1] or self.y < 0 or self.y >= model.data.shape[0]:
            return

        if model.data[self.y, self.x] != self.old_color:
            return

        filled_pixels = self._flood_fill_pixels(model, self.x, self.y, self.old_color)

        if not filled_pixels:
            return

        min_x = min(px for px, _ in filled_pixels)
        max_x = max(px for px, _ in filled_pixels)
        min_y = min(py for _, py in filled_pixels)
        max_y = max(py for _, py in filled_pixels)

        self.affected_region = (min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)

        w, h = max_x - min_x + 1, max_y - min_y + 1
        self.old_data = np.full((h, w), 255, dtype=np.uint8)

        for px, py in filled_pixels:
            model.data[py, px] = self.new_color
            self.old_data[py - min_y, px - min_x] = self.old_color

    def _apply_stored_changes(self, model: IndexedImageModel) -> None:
        """Apply stored changes (for redo)."""
        if self.old_data is None:
            return

        x, y, w, h = self.affected_region

        for dy in range(h):
            for dx in range(w):
                px, py = x + dx, y + dy
                if (0 <= px < model.data.shape[1] and 0 <= py < model.data.shape[0]) and self.old_data[dy, dx] != 255:
                    model.data[py, px] = self.new_color

    def _flood_fill_pixels(
        self, model: IndexedImageModel, start_x: int, start_y: int, target_color: int
    ) -> list[tuple[int, int]]:
        """Find all connected pixels of the target color using flood fill algorithm."""
        filled: list[tuple[int, int]] = []
        stack = [(start_x, start_y)]
        visited: set[tuple[int, int]] = set()

        while stack:
            x, y = stack.pop()

            if (x, y) in visited:
                continue

            if x < 0 or x >= model.data.shape[1] or y < 0 or y >= model.data.shape[0]:
                continue

            if model.data[y, x] != target_color:
                continue

            visited.add((x, y))
            filled.append((x, y))

            stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

        return filled

    @override
    def get_memory_size(self) -> int:
        """Calculate memory usage."""
        if self.compressed and self._compressed_data:
            return len(self._compressed_data) + 64
        if self.old_data is not None:
            return self.old_data.nbytes + 64
        return 64

    @override
    def _get_compress_data(
        self,
    ) -> tuple[int, int, int, int, tuple[int, int, int, int], np.ndarray | None, bool]:
        """Get flood fill data for compression."""
        return (
            self.x,
            self.y,
            self.old_color,
            self.new_color,
            self.affected_region,
            self.old_data,
            self._fill_executed,
        )

    @override
    def _clear_uncompressed_data(self) -> None:
        """Clear numpy array after compression."""
        self.old_data = None

    @override
    def _restore_from_compressed(
        self,
        data: tuple[int, int, int, int, tuple[int, int, int, int], np.ndarray | None, bool],
    ) -> None:
        """Restore flood fill data from compressed format."""
        (
            self.x,
            self.y,
            self.old_color,
            self.new_color,
            self.affected_region,
            self.old_data,
            self._fill_executed,
        ) = data

    @classmethod
    @override
    def from_dict(cls, data: dict[str, Any]) -> FloodFillCommand:  # type: ignore[reportExplicitAny]
        """Create command from dictionary."""
        cmd = cls()
        cmd.timestamp = datetime.fromisoformat(data["timestamp"])
        cmd.compressed = data["compressed"]

        if data["compressed"]:
            cmd._compressed_data = bytes.fromhex(data["compressed_data"])
        else:
            x, y, old_color, new_color, region, old_data_list, fill_executed = data["data"]
            cmd.x = x
            cmd.y = y
            cmd.old_color = old_color
            cmd.new_color = new_color
            cmd.affected_region = tuple(region)
            cmd._fill_executed = fill_executed
            if old_data_list is not None:
                _, _, w, h = cmd.affected_region
                cmd.old_data = np.array(old_data_list, dtype=np.uint8).reshape((h, w))

        return cmd


@dataclass
class SelectionPaintCommand(UndoCommand):
    """Command for painting all pixels in a selection with a single color.

    Stores old colors for each affected pixel to support undo.
    """

    new_color: int = 0
    # Store pixels as list of (x, y, old_color) tuples
    affected_pixels: list[tuple[int, int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize parent class after dataclass initialization."""
        super().__init__()

    @override
    def execute(self, model: IndexedImageModel) -> None:
        """Apply new color to all affected pixels."""
        for x, y, _ in self.affected_pixels:
            if 0 <= x < model.data.shape[1] and 0 <= y < model.data.shape[0]:
                model.data[y, x] = self.new_color

    @override
    def unexecute(self, model: IndexedImageModel) -> None:
        """Restore original colors to all affected pixels."""
        for x, y, old_color in self.affected_pixels:
            if 0 <= x < model.data.shape[1] and 0 <= y < model.data.shape[0]:
                model.data[y, x] = old_color

    @override
    def get_memory_size(self) -> int:
        """Calculate memory usage."""
        if self.compressed and self._compressed_data:
            return len(self._compressed_data) + 64
        # Each tuple is 3 ints, plus list overhead
        return len(self.affected_pixels) * 12 + 64

    @override
    def _get_compress_data(self) -> tuple[int, list[tuple[int, int, int]]]:
        """Get data for compression."""
        return (self.new_color, self.affected_pixels)

    @override
    def _clear_uncompressed_data(self) -> None:
        """Clear pixel list after compression."""
        self.affected_pixels = []

    @override
    def _restore_from_compressed(self, data: tuple[int, list[tuple[int, int, int]]]) -> None:
        """Restore from compressed format."""
        self.new_color, self.affected_pixels = data

    @classmethod
    @override
    def from_dict(cls, data: dict[str, Any]) -> SelectionPaintCommand:  # type: ignore[reportExplicitAny]
        """Create command from dictionary."""
        cmd = cls()
        cmd.timestamp = datetime.fromisoformat(data["timestamp"])
        cmd.compressed = data["compressed"]

        if data["compressed"]:
            cmd._compressed_data = bytes.fromhex(data["compressed_data"])
        else:
            cmd.new_color, pixels = data["data"]
            cmd.affected_pixels = [tuple(p) for p in pixels]

        return cmd

    @classmethod
    def from_selection(
        cls, selection: set[tuple[int, int]], new_color: int, model: IndexedImageModel
    ) -> SelectionPaintCommand:
        """Create a SelectionPaintCommand from a selection set.

        Args:
            selection: Set of (x, y) coordinates to paint
            new_color: The new color index to apply
            model: The image model (to read old colors)

        Returns:
            A SelectionPaintCommand ready to execute
        """
        affected = [
            (x, y, int(model.data[y, x])) for x, y in selection if 0 <= x < model.width and 0 <= y < model.height
        ]
        cmd = cls(new_color=new_color, affected_pixels=affected)
        return cmd


class BatchCommand(UndoCommand):
    """Groups multiple commands executed together."""

    def __init__(self, commands: list[UndoCommand] | None = None) -> None:
        """Initialize with optional list of commands."""
        super().__init__()
        self.commands: list[UndoCommand] = commands or []

    def add_command(self, command: UndoCommand) -> None:
        """Add a command to the batch."""
        self.commands.append(command)

    @override
    def execute(self, model: IndexedImageModel) -> None:
        """Execute all commands in order."""
        for cmd in self.commands:
            if cmd.compressed:
                cmd.decompress()
            cmd.execute(model)

    @override
    def unexecute(self, model: IndexedImageModel) -> None:
        """Undo all commands in reverse order."""
        for cmd in reversed(self.commands):
            if cmd.compressed:
                cmd.decompress()
            cmd.unexecute(model)

    @override
    def get_memory_size(self) -> int:
        """Calculate total memory usage of all commands."""
        return sum(cmd.get_memory_size() for cmd in self.commands) + 64

    @override
    def compress(self) -> None:
        """Compress all individual commands."""
        for cmd in self.commands:
            if not cmd.compressed:
                cmd.compress()
        super().compress()

    @override
    def _get_compress_data(self) -> list[UndoCommand]:
        """Get command list for compression."""
        return self.commands

    @override
    def _clear_uncompressed_data(self) -> None:
        """Commands are already compressed individually."""

    @override
    def _restore_from_compressed(self, data: list[UndoCommand]) -> None:
        """Restore command list from compressed format."""
        self.commands = data

    @override
    def to_dict(self) -> dict[str, Any]:  # type: ignore[reportExplicitAny]
        """Serialize batch command to dictionary."""
        base_dict = super().to_dict()
        if not self.compressed:
            base_dict["commands"] = [cmd.to_dict() for cmd in self.commands]
        return base_dict

    @classmethod
    @override
    def from_dict(cls, data: dict[str, Any]) -> BatchCommand:  # type: ignore[reportExplicitAny]
        """Create batch command from dictionary."""
        cmd = cls()
        cmd.timestamp = datetime.fromisoformat(data["timestamp"])
        cmd.compressed = data["compressed"]

        if data["compressed"]:
            cmd._compressed_data = bytes.fromhex(data["compressed_data"])
        else:
            cmd.commands = []
            for cmd_data in data.get("commands", []):
                cmd_type = cmd_data["type"]
                if cmd_type == "DrawPixelCommand":
                    cmd.commands.append(DrawPixelCommand.from_dict(cmd_data))
                elif cmd_type == "FloodFillCommand":
                    cmd.commands.append(FloodFillCommand.from_dict(cmd_data))
                elif cmd_type == "SelectionPaintCommand":
                    cmd.commands.append(SelectionPaintCommand.from_dict(cmd_data))
                elif cmd_type == "BatchCommand":
                    cmd.commands.append(BatchCommand.from_dict(cmd_data))

        return cmd
