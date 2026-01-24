#!/usr/bin/env python3
"""Tests for PaletteColorCommand.

Verifies undo/redo of palette color changes.
"""

from unittest.mock import Mock

import pytest

from core.editing.commands import PaletteColorCommand


def test_palette_color_command_execute():
    """Execute should apply new color to palette."""
    # Create a mock palette as a list of colors
    colors = [(i * 10, i * 10, i * 10) for i in range(16)]

    cmd = PaletteColorCommand(palette_index=5, old_color=(50, 50, 50), new_color=(255, 0, 0))
    cmd.set_palette(colors)

    # Execute the command (model parameter unused for palette commands)
    cmd.execute(Mock())

    # Color at index 5 should now be the new color
    assert colors[5] == (255, 0, 0)


def test_palette_color_command_unexecute():
    """Unexecute should restore old color to palette."""
    # Create a mock palette
    colors = [(i * 10, i * 10, i * 10) for i in range(16)]

    cmd = PaletteColorCommand(palette_index=5, old_color=(50, 50, 50), new_color=(255, 0, 0))
    cmd.set_palette(colors)

    # Execute then unexecute
    cmd.execute(Mock())
    assert colors[5] == (255, 0, 0)

    cmd.unexecute(Mock())
    assert colors[5] == (50, 50, 50)


def test_palette_color_command_protects_index_0():
    """Index 0 (transparent) should not be modifiable via command."""
    colors = [(0, 0, 0)] + [(i * 10, i * 10, i * 10) for i in range(1, 16)]

    cmd = PaletteColorCommand(palette_index=0, old_color=(0, 0, 0), new_color=(255, 255, 255))
    cmd.set_palette(colors)

    # Execute should not change index 0
    cmd.execute(Mock())
    assert colors[0] == (0, 0, 0)


def test_palette_color_command_without_palette():
    """Command should handle missing palette gracefully."""
    cmd = PaletteColorCommand(palette_index=5, old_color=(50, 50, 50), new_color=(255, 0, 0))
    # Don't call set_palette

    # Should not raise
    cmd.execute(Mock())
    cmd.unexecute(Mock())


def test_palette_color_command_compression():
    """Command should support compression/decompression."""
    cmd = PaletteColorCommand(palette_index=5, old_color=(50, 50, 50), new_color=(255, 0, 0))

    # Compress
    cmd.compress()
    assert cmd.compressed is True
    assert cmd._compressed_data is not None

    # Decompress
    cmd.decompress()
    assert cmd.compressed is False
    assert cmd.palette_index == 5
    assert cmd.old_color == (50, 50, 50)
    assert cmd.new_color == (255, 0, 0)


def test_palette_color_command_memory_size():
    """get_memory_size should return reasonable size."""
    cmd = PaletteColorCommand(palette_index=5, old_color=(50, 50, 50), new_color=(255, 0, 0))

    size = cmd.get_memory_size()
    assert size > 0
    assert size < 1024  # Should be small for a single color change


def test_palette_color_command_to_dict():
    """Command should serialize to dictionary."""
    cmd = PaletteColorCommand(palette_index=5, old_color=(50, 50, 50), new_color=(255, 0, 0))

    d = cmd.to_dict()

    assert d["type"] == "PaletteColorCommand"
    assert "timestamp" in d
    assert d["compressed"] is False
    assert d["data"] == (5, (50, 50, 50), (255, 0, 0))


def test_palette_color_command_from_dict():
    """Command should deserialize from dictionary."""
    original = PaletteColorCommand(palette_index=5, old_color=(50, 50, 50), new_color=(255, 0, 0))

    d = original.to_dict()
    restored = PaletteColorCommand.from_dict(d)

    assert restored.palette_index == 5
    assert restored.old_color == (50, 50, 50)
    assert restored.new_color == (255, 0, 0)
